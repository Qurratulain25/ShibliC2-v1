"""Phase 1 acceptance verification — writes PHASE1_VERIFICATION.log."""
from __future__ import annotations

import json
import os
import sqlite3 as std_sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

LOG = ROOT / "PHASE1_VERIFICATION.log"
lines: list[str] = []


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    lines.append(line)
    print(line)


def main() -> int:
    log("=== SHIBLI C2 Phase 1 Verification ===")
    log(f"Project: {ROOT}")

    from dotenv import load_dotenv

    from app.core.paths import data_dir, project_root
    from app.core.db_engine import (
        SQLCIPHER_AVAILABLE,
        is_encrypted_db,
        plain_sqlite_readable,
        verify_encrypted,
    )
    from app.core.database import init_db, db_info, user_count
    from app.auth.service import startup_auth, login_user
    from app.services.recordings_local import start_recording

    env_file = data_dir() / ".env"
    load_dotenv(env_file)
    log(f"SHIBLI_DB_KEY set: {bool(os.getenv('SHIBLI_DB_KEY'))}")
    log(f"sqlcipher3 installed: {SQLCIPHER_AVAILABLE}")

    init_db()
    info = db_info()
    db_path = Path(info["path"])
    log("--- Database ---")
    log(json.dumps(info, indent=2))
    log(f"dataDir: {data_dir().resolve()}")
    log(f"projectRoot: {project_root().resolve()}")

    ok, detail = verify_encrypted(db_path)
    log(f"verify_encrypted: ok={ok} detail={detail}")
    log(f"is_encrypted_db (non-SQLite header): {is_encrypted_db(db_path)}")
    log(f"plainSqliteReadable (must be False): {plain_sqlite_readable(db_path)}")

    try:
        conn = std_sqlite3.connect(str(db_path))
        conn.execute("SELECT name FROM sqlite_master LIMIT 1")
        conn.close()
        log("PLAIN SQLITE READ TEST: FAIL — std sqlite3 could read sqlite_master")
    except Exception as exc:
        log(f"PLAIN SQLITE READ TEST: PASS — {type(exc).__name__}: {exc}")

    if user_count() == 0:
        startup_auth()
    user = os.getenv("SHIBLI_DEFAULT_ADMIN_USER", "admin")
    password = os.getenv("SHIBLI_DEFAULT_ADMIN_PASSWORD", "")
    if not password:
        log("--- Login: FAIL — set SHIBLI_DEFAULT_ADMIN_PASSWORD explicitly for verification ---")
        return 1
    try:
        login = login_user(user, password)
    except Exception:
        log("--- Login: FAIL — supplied verification credentials were rejected ---")
        return 1
    log("--- Login ---")
    log(json.dumps({
        "ok": True,
        "username": login["user"]["username"],
        "role": login["user"]["roleName"],
        "passwordSource": "environment",
    }))

    rec = start_recording("DayCam01", "CAM01", "Manual", user)
    log("--- Recording ---")
    log(json.dumps(rec, indent=2))
    rec_file = Path(rec["file_path"])
    log(f"Recording on disk: {rec_file.exists()} — {rec_file}")

    appdata_db = Path(os.environ.get("LOCALAPPDATA", "")) / "ShibliC2" / "shibli_c2.db"
    log("--- AppData DB (must not be active) ---")
    log(f"appdataDbPath: {appdata_db}")
    log(f"appdataDbExists: {appdata_db.exists()}")
    if appdata_db.exists():
        log(f"appdataDbIsActiveTarget: {appdata_db.resolve() == db_path.resolve()}")

    log("--- DB reset simulation (fresh encrypted DB + env default login) ---")
    import subprocess

    python_exe = sys.executable
    proc = subprocess.run(
        [python_exe, str(ROOT / "scripts" / "verify_reset_db.py")],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    if proc.returncode == 0 and proc.stdout.strip():
        log(proc.stdout.strip())
    else:
        log(f"reset test failed: {proc.stderr.strip() or proc.stdout.strip()}")

    log("--- EXE path simulation (frozen) ---")
    sys.frozen = True  # type: ignore[attr-defined]
    sys.executable = str(ROOT / "dist" / "ShibliC2.exe")
    from importlib import reload
    import app.core.paths as paths_mod

    reload(paths_mod)
    exe_data = paths_mod.data_dir()
    log(json.dumps({
        "exeSimDataDir": str(exe_data.resolve()),
        "matchesDevDb": str(exe_data / "shibli_c2.db") == str(db_path),
    }, indent=2))

    rec_dir = ROOT / "data" / "recordings"
    mp4s = list(rec_dir.glob("SHIBLI_*.mp4"))
    log(f"--- Recordings folder: {len(mp4s)} file(s) ---")
    for f in mp4s[:10]:
        log(f"  {f.name} ({f.stat().st_size} bytes)")

    log("=== Verification complete ===")
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"Log written: {LOG}")

    return 0 if info.get("encrypted") and info.get("verificationOk") else 1


if __name__ == "__main__":
    raise SystemExit(main())
