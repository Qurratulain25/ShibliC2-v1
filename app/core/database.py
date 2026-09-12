"""Encrypted SQLite database — users, settings, recordings metadata, audit logs."""
from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from .connection_mode import (
    camera_matches_mode,
    normalize_camera_mode,
)
from .db_engine import (
    SQLCIPHER_AVAILABLE,
    backup_database,
    collect_legacy_db_paths,
    connect,
    is_encrypted_db,
    migrate_plain_to_encrypted,
    plain_sqlite_readable,
    require_sqlcipher,
    verify_encrypted,
)
from .paths import data_dir

DB_PATH = data_dir() / "shibli_c2.db"
SCHEMA_VERSION = 3

# Reuse one SQLCipher connection per thread — PRAGMA key / KDF on every open is very slow.
_local = threading.local()
_tls_lock = threading.Lock()

ROLE_PERMISSIONS: Dict[str, List[str]] = {
    "ADMINISTRATOR": [
        "register-user", "get-users", "get-roles", "manage-users",
        "add-stream", "get-streams", "control-camera", "control-ptz",
        "edit-user", "delete-user", "manage-recordings", "delete-recordings",
        "manage-settings", "reset-settings", "view-audit-logs", "manage-layouts",
        "manage-cameras",
    ],
    "OPERATOR": ["get-streams", "control-camera", "control-ptz", "manage-recordings"],
    "VIEWER": ["get-streams"],
}


def _thread_conn() -> Any:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        return conn
    with _tls_lock:
        conn = getattr(_local, "conn", None)
        if conn is None:
            conn = connect(DB_PATH)
            try:
                conn.execute("PRAGMA busy_timeout = 5000")
            except Exception:
                pass
            _local.conn = conn
    return conn


@contextmanager
def get_db() -> Generator[Any, None, None]:
    conn = _thread_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


def init_db() -> None:
    _run_migrations()
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                full_name TEXT DEFAULT '',
                password_hash TEXT NOT NULL,
                role_name TEXT NOT NULL DEFAULT 'VIEWER',
                permissions TEXT NOT NULL DEFAULT '[]',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                camera_name TEXT NOT NULL,
                camera_id TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                duration_sec REAL DEFAULT 0,
                file_size_bytes INTEGER DEFAULT 0,
                recording_type TEXT NOT NULL DEFAULT 'Manual',
                recorded_by TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS layouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                config TEXT NOT NULL,
                is_global INTEGER NOT NULL DEFAULT 1,
                owner_username TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                role_name TEXT,
                action TEXT NOT NULL,
                module TEXT,
                detail TEXT,
                success INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS user_cameras (
                username TEXT NOT NULL,
                camera_id INTEGER NOT NULL,
                PRIMARY KEY (username, camera_id)
            );
            CREATE TABLE IF NOT EXISTS local_cameras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                camera_type TEXT NOT NULL DEFAULT 'Day',
                ip_address TEXT DEFAULT '',
                rtsp_url TEXT DEFAULT '',
                onvif_port INTEGER DEFAULT 80,
                username TEXT DEFAULT '',
                password TEXT DEFAULT '',
                ptz_mapping TEXT DEFAULT 'none',
                camera_group TEXT DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                connection_mode TEXT NOT NULL DEFAULT 'lan',
                created_at TEXT NOT NULL,
                updated_at TEXT
            );
            """
        )
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)",
            ("version", str(SCHEMA_VERSION)),
        )
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)",
            ("encrypted", "1"),
        )
        for col_sql in (
            "ALTER TABLE users ADD COLUMN full_name TEXT DEFAULT ''",
            "ALTER TABLE users ADD COLUMN updated_at TEXT",
            "ALTER TABLE audit_log ADD COLUMN role_name TEXT",
            "ALTER TABLE audit_log ADD COLUMN module TEXT",
            "ALTER TABLE audit_log ADD COLUMN success INTEGER DEFAULT 1",
        ):
            try:
                conn.execute(col_sql)
            except Exception:
                pass
        try:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS user_cameras (
                    username TEXT NOT NULL,
                    camera_id INTEGER NOT NULL,
                    PRIMARY KEY (username, camera_id)
                )"""
            )
        except Exception:
            pass
        _ensure_camera_connection_mode(conn)


def _table_columns(conn: Any, table: str) -> List[str]:
    try:
        return [str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    except Exception:
        return []


def _ensure_camera_connection_mode(conn: Any) -> None:
    """Add connection_mode without rewriting the table or dropping cameras.

    Existing rows receive 'legacy' so they stay visible in both LAN and IP
    modes until an administrator classifies them. Mode is never inferred from IP.
    """
    cols = _table_columns(conn, "local_cameras")
    if not cols or "connection_mode" in cols:
        return
    if DB_PATH.exists() and DB_PATH.stat().st_size > 0:
        backup_database(DB_PATH, reason="schema-v3")
    conn.execute(
        "ALTER TABLE local_cameras ADD COLUMN connection_mode TEXT NOT NULL DEFAULT 'legacy'"
    )


def _run_migrations() -> None:
    require_sqlcipher()
    target = DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists() and not is_encrypted_db(target):
        backup_database(target, reason="encrypt")
        plain_copy = target.with_suffix(".db.plain")
        target.rename(plain_copy)
        ok, msg = migrate_plain_to_encrypted(plain_copy, target)
        if not ok:
            plain_copy.rename(target)
            raise RuntimeError(f"Failed to encrypt database: {msg}")

    skip_legacy = os.getenv("SHIBLI_SKIP_LEGACY_MIGRATION", "").lower() in ("1", "true", "yes")
    target_ready = target.exists() and target.stat().st_size > 0
    if not skip_legacy and not target_ready:
        import shutil

        for legacy in collect_legacy_db_paths(target):
            if is_encrypted_db(legacy):
                shutil.copy2(legacy, target)
            else:
                migrate_plain_to_encrypted(legacy, target)
            break


def get_setting(key: str) -> Any:
    with get_db() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return row["value"]


def set_setting(key: str, value: Any) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps(value), now),
        )


def user_count() -> int:
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
        return int(row["c"])


def get_user_by_username(username: str, include_inactive: bool = False) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        q = "SELECT * FROM users WHERE username = ?"
        if not include_inactive:
            q += " AND active = 1"
        row = conn.execute(q, (username,)).fetchone()
        return _row_to_user(row) if row else None


def list_users(include_inactive: bool = False) -> List[Dict[str, Any]]:
    with get_db() as conn:
        q = "SELECT * FROM users"
        if not include_inactive:
            q += " WHERE active = 1"
        q += " ORDER BY username"
        return [_row_to_user(r) for r in conn.execute(q).fetchall()]


def create_user(
    username: str,
    password_hash: str,
    role_name: str,
    full_name: str = "",
    permissions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    perms = permissions or ROLE_PERMISSIONS.get(role_name.upper(), ROLE_PERMISSIONS["VIEWER"])
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO users (username, full_name, password_hash, role_name, permissions, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (username, full_name, password_hash, role_name.upper(), json.dumps(perms), now, now),
        )
    return get_user_by_username(username)  # type: ignore


def update_user_role(username: str, role_name: str, permissions: Optional[List[str]] = None) -> None:
    perms = permissions or ROLE_PERMISSIONS.get(role_name.upper(), ROLE_PERMISSIONS["VIEWER"])
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET role_name = ?, permissions = ?, updated_at = ? WHERE username = ?",
            (role_name.upper(), json.dumps(perms), now, username),
        )


def update_user_password(username: str, password_hash: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE username = ?",
            (password_hash, now, username),
        )


def update_user_profile(username: str, full_name: Optional[str] = None, active: Optional[bool] = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        if full_name is not None:
            conn.execute(
                "UPDATE users SET full_name = ?, updated_at = ? WHERE username = ?",
                (full_name, now, username),
            )
        if active is not None:
            conn.execute(
                "UPDATE users SET active = ?, updated_at = ? WHERE username = ?",
                (1 if active else 0, now, username),
            )


def deactivate_user(username: str) -> None:
    update_user_profile(username, active=False)


def update_user_permissions(username: str, permissions: List[str]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET permissions = ?, updated_at = ? WHERE username = ?",
            (json.dumps(permissions), now, username),
        )


def get_user_camera_ids(username: str) -> List[int]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT camera_id FROM user_cameras WHERE username = ? ORDER BY camera_id",
            (username,),
        ).fetchall()
        return [int(r["camera_id"]) for r in rows]


def set_user_camera_ids(username: str, camera_ids: List[int]) -> None:
    with get_db() as conn:
        conn.execute("DELETE FROM user_cameras WHERE username = ?", (username,))
        for cid in camera_ids:
            conn.execute(
                "INSERT OR IGNORE INTO user_cameras (username, camera_id) VALUES (?, ?)",
                (username, int(cid)),
            )


def log_action(
    username: str | None,
    action: str,
    detail: str = "",
    *,
    role_name: str = "",
    module: str = "",
    success: bool = True,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO audit_log (username, role_name, action, module, detail, success, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (username, role_name, action, module, detail, 1 if success else 0, now),
        )


def list_audit_logs(limit: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]


def insert_recording(meta: Dict[str, Any]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO recordings
               (file_name, file_path, camera_name, camera_id, recorded_at, duration_sec,
                file_size_bytes, recording_type, recorded_by, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                meta["file_name"], meta["file_path"], meta["camera_name"], meta["camera_id"],
                meta["recorded_at"], meta.get("duration_sec", 0), meta.get("file_size_bytes", 0),
                meta.get("recording_type", "Manual"), meta.get("recorded_by"), now,
            ),
        )
        return int(cur.lastrowid)


def list_local_recordings(
    search: str = "",
    sort: str = "date_desc",
    page: int = 1,
    page_size: int = 20,
    date_from: str = "",
    date_to: str = "",
) -> Dict[str, Any]:
    clauses: List[str] = []
    params: List[Any] = []
    if search:
        clauses.append(
            "(file_name LIKE ? OR camera_name LIKE ? OR camera_id LIKE ? OR recording_type LIKE ?)"
        )
        like = f"%{search}%"
        params.extend([like, like, like, like])
    if date_from:
        clauses.append("recorded_at >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("recorded_at <= ?")
        params.append(date_to + "T23:59:59")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    order = {
        "date_desc": "recorded_at DESC",
        "date_asc": "recorded_at ASC",
        "name_asc": "file_name ASC",
        "name_desc": "file_name DESC",
        "camera_asc": "camera_name ASC",
        "size_desc": "file_size_bytes DESC",
        "duration_desc": "duration_sec DESC",
    }.get(sort, "recorded_at DESC")
    offset = max(0, (page - 1) * page_size)
    with get_db() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS c FROM recordings {where}", params).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM recordings {where} ORDER BY {order} LIMIT ? OFFSET ?",
            [*params, page_size, offset],
        ).fetchall()
    items = []
    for r in rows:
        items.append({
            "id": r["id"],
            "fileName": r["file_name"],
            "filePath": r["file_path"],
            "cameraName": r["camera_name"],
            "cameraId": r["camera_id"],
            "recordedAt": r["recorded_at"],
            "duration": r["duration_sec"],
            "fileSizeBytes": r["file_size_bytes"],
            "recordingType": r["recording_type"],
            "recordedBy": r["recorded_by"],
        })
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


def get_recording(recording_id: int) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM recordings WHERE id = ?", (recording_id,)).fetchone()
        if not row:
            return None
        return dict(row)


def delete_recording(recording_id: int) -> bool:
    with get_db() as conn:
        row = conn.execute("SELECT file_path FROM recordings WHERE id = ?", (recording_id,)).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM recordings WHERE id = ?", (recording_id,))
    path = Path(row["file_path"])
    if path.exists():
        path.unlink()
    return True


def rename_recording(recording_id: int, new_name: str) -> bool:
    with get_db() as conn:
        row = conn.execute("SELECT file_path FROM recordings WHERE id = ?", (recording_id,)).fetchone()
        if not row:
            return False
        old = Path(row["file_path"])
        new_path = old.parent / new_name
        if old.exists() and old != new_path:
            old.rename(new_path)
        conn.execute(
            "UPDATE recordings SET file_name = ?, file_path = ? WHERE id = ?",
            (new_name, str(new_path), recording_id),
        )
    return True


def sync_role_permissions_for_user(username: str, role_name: str) -> None:
    perms = ROLE_PERMISSIONS.get(role_name.upper(), ROLE_PERMISSIONS["VIEWER"])
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET permissions = ?, updated_at = ? WHERE username = ?",
            (json.dumps(perms), now, username),
        )


def sync_all_role_permissions() -> int:
    updated = 0
    with get_db() as conn:
        rows = conn.execute("SELECT username, role_name FROM users").fetchall()
    for row in rows:
        sync_role_permissions_for_user(row["username"], row["role_name"])
        updated += 1
    return updated


def list_local_cameras(
    connection_mode: Optional[str] = None,
    *,
    include_rtsp: bool = True,
) -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM local_cameras ORDER BY name"
        ).fetchall()
    cameras = [_row_to_camera(r, include_rtsp=include_rtsp) for r in rows]
    if connection_mode:
        cameras = [c for c in cameras if camera_matches_mode(c, connection_mode)]
    return cameras


def get_local_camera(camera_id: int) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM local_cameras WHERE id = ?", (camera_id,)).fetchone()
    return _row_to_camera(row) if row else None


def get_local_camera_credentials(camera_id: int) -> Dict[str, str]:
    """Internal — ONVIF credentials for controls sync (never expose via list API)."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT username, password FROM local_cameras WHERE id = ?",
            (camera_id,),
        ).fetchone()
    if not row:
        return {"username": "", "password": ""}
    return {
        "username": row["username"] or "",
        "password": row["password"] or "",
    }


def insert_local_camera(data: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO local_cameras
               (name, camera_type, ip_address, rtsp_url, onvif_port, username, password,
                ptz_mapping, camera_group, enabled, connection_mode, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data["name"], data.get("camera_type", "Day"), data.get("ip_address", ""),
                data.get("rtsp_url", ""), int(data.get("onvif_port") or 80),
                data.get("username", ""), data.get("password", ""),
                data.get("ptz_mapping", "none"), data.get("camera_group", ""),
                1 if data.get("enabled", True) else 0,
                normalize_camera_mode(data.get("connection_mode") or data.get("connectionMode"), default="lan"),
                now, now,
            ),
        )
        cid = cur.lastrowid
    return get_local_camera(int(cid))  # type: ignore


def update_local_camera(camera_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    existing = get_local_camera(camera_id)
    if not existing:
        return None
    now = datetime.now(timezone.utc).isoformat()
    password = data.get("password")
    if password is None or password == "":
        password = get_local_camera_credentials(camera_id).get("password", "")
    incoming_mode = data.get("connection_mode") if "connection_mode" in data else data.get("connectionMode")
    if incoming_mode in (None, ""):
        connection_mode = existing.get("connectionMode") or "legacy"
    else:
        connection_mode = normalize_camera_mode(incoming_mode, default="lan")
    with get_db() as conn:
        conn.execute(
            """UPDATE local_cameras SET name=?, camera_type=?, ip_address=?, rtsp_url=?,
               onvif_port=?, username=?, password=?, ptz_mapping=?, camera_group=?,
               enabled=?, connection_mode=?, updated_at=? WHERE id=?""",
            (
                data.get("name", existing["name"]),
                data.get("camera_type", existing.get("cameraType")),
                data.get("ip_address", existing.get("ipAddress", "")),
                data.get("rtsp_url", existing.get("rtspUrl", "")),
                int(data.get("onvif_port") or existing.get("onvifPort") or 80),
                data.get("username", existing.get("username", "")),
                password,
                data.get("ptz_mapping", existing.get("ptzMapping", "none")),
                data.get("camera_group", existing.get("cameraGroup", "")),
                1 if data.get("enabled", existing.get("enabled", True)) else 0,
                connection_mode,
                now, camera_id,
            ),
        )
    return get_local_camera(camera_id)


def delete_local_camera(camera_id: int) -> bool:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM local_cameras WHERE id = ?", (camera_id,))
    return cur.rowcount > 0


def _row_to_camera(row: Any, *, include_rtsp: bool = True) -> Dict[str, Any]:
    keys = set()
    try:
        keys = set(row.keys())
    except Exception:
        pass
    raw_mode = row["connection_mode"] if "connection_mode" in keys else "legacy"
    rtsp = row["rtsp_url"] or ""
    return {
        "id": row["id"],
        "name": row["name"],
        "cameraType": row["camera_type"],
        "ipAddress": row["ip_address"] or "",
        "rtspUrl": rtsp if include_rtsp else "",
        "hasRtsp": bool(rtsp),
        "onvifPort": row["onvif_port"] or 80,
        "username": row["username"] or "",
        "password": "",  # never expose in list API
        "hasPassword": bool(row["password"]),
        "ptzMapping": row["ptz_mapping"] or "none",
        "cameraGroup": row["camera_group"] or "",
        "enabled": bool(row["enabled"]),
        "connectionMode": normalize_camera_mode(raw_mode, default="legacy"),
        "createdAt": row["created_at"],
    }


def db_info() -> Dict[str, Any]:
    ok, verification = verify_encrypted(DB_PATH)
    return {
        "path": str(DB_PATH.resolve()),
        "encrypted": is_encrypted_db(DB_PATH) and SQLCIPHER_AVAILABLE,
        "plainSqliteReadable": plain_sqlite_readable(DB_PATH),
        "verificationOk": ok,
        "verificationDetail": verification,
        "schemaVersion": SCHEMA_VERSION,
        "sqlcipherInstalled": SQLCIPHER_AVAILABLE,
    }


def _row_to_user(row: Any) -> Dict[str, Any]:
    keys = row.keys() if hasattr(row, "keys") else []
    full_name = row["full_name"] if "full_name" in keys else ""
    perms = json.loads(row["permissions"])
    return {
        "id": row["id"],
        "username": row["username"],
        "fullName": full_name or "",
        "password_hash": row["password_hash"],
        "roleName": row["role_name"],
        "permissions": perms,
        "active": bool(row["active"]),
        "createdAt": row["created_at"],
    }
