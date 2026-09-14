"""SQLCipher engine — encryption required; single DB on D: project data/."""
from __future__ import annotations

import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Tuple

logger = logging.getLogger(__name__)

_IMPORT_ERROR: Exception | None = None


def _prepare_sqlcipher_dll_search() -> None:
    """Windows frozen loads: prefer sqlcipher3's directory before stdlib sqlite3.dll."""
    if os.name != "nt":
        return
    folders: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        exe_dir = Path(sys.executable).resolve().parent
        folders.extend(
            [
                meipass / "sqlcipher3",
                meipass,
                exe_dir / "_internal" / "sqlcipher3",
                exe_dir / "_internal",
                exe_dir,
            ]
        )
    existing = [str(folder) for folder in folders if folder.is_dir()]
    if existing:
        os.environ["PATH"] = os.pathsep.join(existing) + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        for folder in existing:
            try:
                os.add_dll_directory(folder)
            except OSError:
                pass


_prepare_sqlcipher_dll_search()

try:
    import sqlcipher3.dbapi2 as sqlite3  # type: ignore

    SQLCIPHER_AVAILABLE = True
except Exception as exc:  # ImportError, OSError / DLL load failure on Windows
    SQLCIPHER_AVAILABLE = False
    _IMPORT_ERROR = exc
    sqlite3 = None  # type: ignore

import sqlite3 as std_sqlite3

if sqlite3 is None:
    sqlite3 = std_sqlite3  # type: ignore


def require_sqlcipher() -> None:
    if SQLCIPHER_AVAILABLE:
        return
    detail = ""
    if _IMPORT_ERROR is not None:
        detail = f"{type(_IMPORT_ERROR).__name__}: {_IMPORT_ERROR}"
        logger.error("SQLCipher failed to load: %s", detail)
    raise RuntimeError(
        "SQLCipher failed to load. SHIBLI C2 cannot open the encrypted database."
        + (f" ({detail})" if detail else "")
    ) from _IMPORT_ERROR


def db_key() -> str:
    key = os.getenv("SHIBLI_DB_KEY", "")
    key = key.strip().strip("\r\n")
    if not key:
        raise RuntimeError(
            "SHIBLI_DB_KEY must be set in data/.env before starting SHIBLI C2."
        )
    return key.replace("'", "''")


def refuse_empty_database(db_path: Path) -> None:
    """A 0-byte DB file must not be initialized with a new SQLCipher key.

    Connecting to an empty file mints a fresh encrypted database. That is how
    camera/PTZ configuration was lost after a new SHIBLI_DB_KEY was generated
    against a truncated data/shibli_c2.db.
    """
    if not db_path.exists():
        return
    try:
        size = db_path.stat().st_size
    except OSError:
        return
    if size > 0:
        return
    backup = db_path.parent / "shibli_c2.db.verify_backup"
    safe = db_path.parent / "shibli_c2.db.verify_backup.safe"
    hints = []
    if backup.exists():
        hints.append(str(backup))
    if safe.exists():
        hints.append(str(safe))
    extra = ""
    if hints:
        extra = " Found backup(s): " + ", ".join(hints) + "."
    raise RuntimeError(
        f"{db_path} exists but is empty (0 bytes). Refusing to create a new "
        "encrypted database with the current SHIBLI_DB_KEY — that would look "
        "like a fresh install (Local: 0 configured) and drop cameras. Restore "
        "the original key + backup, or run: python3 scripts/recover_runtime.py."
        + extra
    )


def connect(db_path: Path, key: str | None = None) -> Any:
    require_sqlcipher()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    refuse_empty_database(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    pragma_key = db_key() if key is None else key.replace("'", "''")
    conn.execute(f"PRAGMA key = '{pragma_key}'")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def is_encrypted_db(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        with open(path, "rb") as f:
            header = f.read(16)
        return not header.startswith(b"SQLite format 3")
    except OSError:
        return False


def plain_sqlite_readable(path: Path) -> bool:
    """True if file opens as unencrypted SQLite (should be False for production)."""
    if not path.exists():
        return False
    if is_encrypted_db(path):
        return False
    try:
        conn = std_sqlite3.connect(str(path))
        conn.execute("SELECT name FROM sqlite_master LIMIT 1")
        conn.close()
        return True
    except Exception:
        return False


def verify_encrypted(path: Path) -> Tuple[bool, str]:
    if not path.exists():
        return False, "database file missing"
    require_sqlcipher()
    if not is_encrypted_db(path):
        return False, "file header is plain SQLite format 3"
    if plain_sqlite_readable(path):
        return False, "plain SQLite can read this file — encryption not active"
    try:
        conn = connect(path)
        conn.execute("SELECT name FROM sqlite_master LIMIT 1")
        conn.close()
        return True, "SQLCipher active; plain SQLite cannot read"
    except Exception as exc:
        return False, str(exc)


MAX_AUTOMATIC_BACKUPS = 5


def _prune_automatic_backups(dest_dir: Path, keep: int = MAX_AUTOMATIC_BACKUPS) -> None:
    files = sorted(
        dest_dir.glob("shibli_c2_*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for stale in files[keep:]:
        try:
            stale.unlink()
        except OSError:
            logger.warning("Could not remove old backup %s", stale.name)


def backup_database(db_path: Path, *, reason: str = "migration") -> Path:
    """Copy the database once for a real migration/upgrade. Not called on ordinary startup."""
    if not db_path.exists() or db_path.stat().st_size == 0:
        raise FileNotFoundError(f"Refusing to backup missing or empty database: {db_path}")
    from .paths import backups_dir

    dest_dir = backups_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_reason = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in reason)[:32] or "migration"
    backup = dest_dir / f"shibli_c2_{safe_reason}_{ts}.db"
    shutil.copy2(db_path, backup)
    logger.info("Database backup created (%s): %s", safe_reason, backup.name)
    _prune_automatic_backups(dest_dir)
    return backup


def migrate_plain_to_encrypted(plain_path: Path, encrypted_path: Path) -> Tuple[bool, str]:
    require_sqlcipher()
    if not plain_path.exists():
        return False, "source database not found"
    backup_database(plain_path, reason="plain-to-sqlcipher")
    temp = encrypted_path.with_suffix(".db.migrating")
    if temp.exists():
        temp.unlink()
    try:
        src = std_sqlite3.connect(str(plain_path))
        src.row_factory = std_sqlite3.Row
        dst = connect(temp)
        for line in src.iterdump():
            if line.strip():
                dst.execute(line)
        dst.commit()
        src.close()
        dst.close()
        if encrypted_path.exists():
            backup_database(encrypted_path, reason="pre-replace")
            encrypted_path.unlink()
        temp.rename(encrypted_path)
        return True, "migrated to SQLCipher"
    except Exception as exc:
        logger.exception("Migration failed")
        if temp.exists():
            temp.unlink()
        return False, str(exc)


def collect_legacy_db_paths(target: Path) -> list[Path]:
    from .paths import bundle_dir

    candidates = [
        bundle_dir() / "shibli_c2.db",
        bundle_dir() / "data" / "shibli_c2.db",
    ]
    appdata = os.environ.get("LOCALAPPDATA")
    if appdata:
        candidates.append(Path(appdata) / "ShibliC2" / "shibli_c2.db")
    seen: set[str] = set()
    out: list[Path] = []
    for p in candidates:
        rp = str(p.resolve()) if p.exists() else ""
        if p.exists() and rp != str(target.resolve()) and rp not in seen:
            seen.add(rp)
            out.append(p)
    return out
