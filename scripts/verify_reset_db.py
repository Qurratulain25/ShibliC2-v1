"""Isolated DB reset test — separate process, no web server."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESET = ROOT / "data" / "_verify_reset"


def main() -> int:
    if RESET.exists():
        shutil.rmtree(RESET, ignore_errors=True)
    RESET.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "data" / ".env", RESET / ".env")
    os.environ["SHIBLI_DATA_DIR"] = str(RESET)
    os.environ["SHIBLI_SKIP_LEGACY_MIGRATION"] = "1"
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)

    from dotenv import load_dotenv

    load_dotenv(RESET / ".env")

    # Import after SHIBLI_DATA_DIR is set (DB_PATH resolves under RESET)
    import importlib

    import app.core.database as db_mod

    importlib.reload(db_mod)
    import app.auth.service as auth_mod

    importlib.reload(auth_mod)

    db_mod.init_db()
    if db_mod.user_count() == 0:
        auth_mod.startup_auth()
    user = os.getenv("SHIBLI_DEFAULT_ADMIN_USER", "admin")
    pwd = os.environ["SHIBLI_DEFAULT_ADMIN_PASSWORD"]
    login = auth_mod.login_user(user, pwd)
    hdr = open(db_mod.DB_PATH, "rb").read(16)
    print(
        json.dumps(
            {
                "resetDbPath": str(db_mod.DB_PATH.resolve()),
                "encryptedHeader": not hdr.startswith(b"SQLite format 3"),
                "loginOk": True,
                "username": login["user"]["username"],
                "password": "SHIBLI_DEFAULT_ADMIN_PASSWORD",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
