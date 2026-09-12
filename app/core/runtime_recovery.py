"""Read-only recovery helpers. Never print secrets (DB keys, passwords, RTSP userinfo)."""
from __future__ import annotations

import hashlib
import ipaddress
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

KNOWN_ENV_CANDIDATES = [
    "Desktop/Abdullah_Shibli_C2/ShibliC2/data/.env",
    "Desktop/new/ShibliC2-Demo/data/.env",
    "Desktop/ShibliC2-Demo/data/.env",
    "Desktop/ShibliC2_Demo/data/.env",
    "ShibliC2(2)/data/.env",
    "ShibliC2/data/.env",
    "Shibli c2 new-7.2.2026/ShibliC2/data/.env",
    "ShibliC2(1)/data/.env",
    "ShibliC2-Demo/data/.env",
    "Desktop/ShibliC2/data/.env",
]

KNOWN_CONTROLS_CANDIDATES = [
    "Desktop/Abdullah_Shibli_C2/ShibliC2/SHIBLI-controls",
    "Quest_Shibli_Setup/Shibli_packaged/SHIBLI/SHIBLI-controls",
    "Desktop/SHIBLI-controls",
    "Desktop/Shibli_packaged/SHIBLI/SHIBLI-controls",
    "Downloads/Quest_Shibli_Setup/Shibli_packaged/SHIBLI/SHIBLI-controls",
    "SHIBLI-controls",
]

SAFE_ENV_NAMES = {
    "VMS_HOST",
    "VMS_PORT",
    "SHIBLI_CONTROLS_DIR",
    "SHIBLI_CONTROLS_URL",
    "SHIBLI_CONTROLS_PORT",
    "GO2RTC_ENABLED",
    "GO2RTC_API_URL",
    "SHIBLI_ENV",
    "SHIBLI_NO_BROWSER",
    "SHIBLI_HW_SIMULATE",
}

CAMERA_COPY_COLUMNS = (
    "name",
    "camera_type",
    "ip_address",
    "rtsp_url",
    "onvif_port",
    "username",
    "password",
    "ptz_mapping",
    "camera_group",
    "enabled",
    "connection_mode",
    "created_at",
    "updated_at",
)


def key_fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]


def parse_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return values
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    for raw in text.splitlines():
        line = raw.strip().lstrip("\ufeff")
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def redact_rtsp(url: str) -> str:
    if not url:
        return ""
    return re.sub(r"(rtsp://)([^/@]+)@", r"\1***:***@", url, flags=re.IGNORECASE)


def classify_host(host: str) -> str:
    host = (host or "").strip()
    if not host:
        return "empty"
    try:
        ip = ipaddress.ip_address(host)
        return "lan" if ip.is_private else "public_ip"
    except ValueError:
        return "hostname"


def rtsp_host_port_path(url: str) -> Dict[str, Any]:
    safe = {"host": "", "port": None, "path": ""}
    if not url:
        return safe
    try:
        parsed = urlparse(redact_rtsp(url).replace("***:***@", "user:pass@"))
        path = parsed.path or ""
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return {"host": parsed.hostname or "", "port": parsed.port, "path": path}
    except Exception:
        return safe


def env_candidates(home: Path, extra: Iterable[Path] | None = None) -> List[Path]:
    found: List[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        try:
            resolved = str(path.resolve()) if path.exists() else str(path)
        except OSError:
            resolved = str(path)
        if resolved in seen:
            return
        seen.add(resolved)
        if path.is_file():
            found.append(path)

    for rel in KNOWN_ENV_CANDIDATES:
        add(home / rel)
    if extra:
        for path in extra:
            add(path)
    for base in (home / "Desktop", home / "Downloads"):
        if not base.is_dir():
            continue
        try:
            for pattern in ("*/data/.env", "*/*/data/.env", "*/*/*/data/.env"):
                for path in base.glob(pattern):
                    add(path)
        except OSError:
            pass
    return found


def controls_candidates(home: Path, project_root: Path) -> List[Path]:
    found: List[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        try:
            resolved = str(path.resolve()) if path.exists() else str(path)
        except OSError:
            resolved = str(path)
        if resolved in seen:
            return
        seen.add(resolved)
        if (path / "server.py").is_file():
            found.append(path)

    add(project_root / "SHIBLI-controls")
    add(project_root.parent / "SHIBLI-controls")
    for rel in KNOWN_CONTROLS_CANDIDATES:
        add(home / rel)
    return found


def open_sqlcipher(db_path: Path, key: str) -> Any:
    from .db_engine import connect

    conn = connect(db_path, key=key)
    conn.execute("SELECT name FROM sqlite_master LIMIT 1")
    return conn


def try_open(db_path: Path, key: str) -> Tuple[bool, str]:
    if not db_path.exists() or db_path.stat().st_size == 0:
        return False, "missing_or_empty"
    try:
        conn = open_sqlcipher(db_path, key)
        conn.close()
        return True, "ok"
    except Exception:
        return False, "wrong_key_or_corrupt"


def table_names(conn: Any) -> List[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1"
    ).fetchall()
    return [r[0] for r in rows]


def column_names(conn: Any, table: str) -> List[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def camera_summaries(conn: Any) -> List[Dict[str, Any]]:
    if "local_cameras" not in table_names(conn):
        return []
    cols = set(column_names(conn, "local_cameras"))
    select = ["name", "camera_type"]
    for extra in ("enabled", "ptz_mapping", "ip_address", "rtsp_url", "onvif_port"):
        if extra in cols:
            select.append(extra)
    rows = conn.execute(
        f"SELECT {', '.join(select)} FROM local_cameras ORDER BY name"
    ).fetchall()
    out: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        host = item.get("ip_address") or ""
        rtsp = rtsp_host_port_path(item.get("rtsp_url") or "")
        out.append(
            {
                "name": item.get("name"),
                "camera_type": item.get("camera_type"),
                "enabled": bool(item.get("enabled", 1)),
                "ptz_mapping": item.get("ptz_mapping") or "none",
                "host": host,
                "host_kind": classify_host(host),
                "onvif_port": item.get("onvif_port"),
                "rtsp_host": rtsp["host"],
                "rtsp_port": rtsp["port"],
                "rtsp_path": rtsp["path"],
            }
        )
    return out


def summarize_db(conn: Any) -> Dict[str, Any]:
    tables = table_names(conn)
    cameras = camera_summaries(conn)
    users = None
    if "users" in tables:
        users = int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
    ptz = sum(1 for c in cameras if (c.get("ptz_mapping") or "none") != "none")
    settings = "app_settings" in tables
    return {
        "tables": tables,
        "camera_count": len(cameras),
        "cameras": cameras,
        "ptz_mapping_count": ptz,
        "user_count": users,
        "has_settings": settings,
        "local_cameras_columns": column_names(conn, "local_cameras") if "local_cameras" in tables else [],
    }


def import_cameras(src: Any, dest: Any) -> int:
    src_cols = set(column_names(src, "local_cameras"))
    dest_cols = set(column_names(dest, "local_cameras"))
    fields = [c for c in CAMERA_COPY_COLUMNS if c in src_cols and c in dest_cols]
    if "name" not in fields:
        raise RuntimeError("Cannot import cameras: name column missing")
    placeholders = ", ".join("?" * len(fields))
    colnames = ", ".join(fields)
    copied = 0
    for row in src.execute(f"SELECT {colnames} FROM local_cameras").fetchall():
        dest.execute(f"INSERT INTO local_cameras ({colnames}) VALUES ({placeholders})", tuple(row))
        copied += 1
    dest.commit()
    return copied


def upsert_env_value(env_path: Path, name: str, value: str) -> None:
    """Set one env assignment without printing the file. Does not overwrite other keys."""
    if env_path.exists():
        text = env_path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
        lines = text.splitlines()
    else:
        lines = []
    pattern = re.compile(rf"^{re.escape(name)}=")
    replaced = False
    out: List[str] = []
    for line in lines:
        if pattern.match(line.strip().lstrip("\ufeff")):
            out.append(f"{name}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        if out and out[-1].strip():
            out.append("")
        out.append(f"{name}={value}")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")


def env_has_name(env_path: Path, name: str) -> bool:
    values = parse_env_file(env_path)
    return bool(values.get(name, "").strip())
