#!/usr/bin/env python3
"""Reset admin password to SHIBLI_DEFAULT_ADMIN_PASSWORD from data/.env."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from app.core.bootstrap_env import bootstrap_environment, env_str
from app.core.paths import project_root
from app.auth.service import hash_password
from app.core.database import get_user_by_username, init_db, update_user_password

bootstrap_environment(project_root())

username = env_str("SHIBLI_DEFAULT_ADMIN_USER", "admin")
password = os.environ["SHIBLI_DEFAULT_ADMIN_PASSWORD"]

init_db()
user = get_user_by_username(username, include_inactive=True)
if not user:
    print(f"ERROR: user '{username}' not found. Delete data/shibli_c2.db and restart to seed defaults.")
    sys.exit(1)

update_user_password(username, hash_password(password))
print(f"Password reset for '{username}' -> value from data/.env (SHIBLI_DEFAULT_ADMIN_PASSWORD)")
print(f"Login with: {username} / {password}")
