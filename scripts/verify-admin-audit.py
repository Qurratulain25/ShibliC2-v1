"""Verify admin can access audit logs API."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
from app.core.paths import data_dir
from app.auth.service import login_user
from app.core.database import list_audit_logs, sync_all_role_permissions

load_dotenv(data_dir() / ".env")
sync_all_role_permissions()
user = os.getenv("SHIBLI_DEFAULT_ADMIN_USER", "admin")
pwd = os.environ["SHIBLI_DEFAULT_ADMIN_PASSWORD"]
login = login_user(user, pwd)
perms = login["user"]["permissions"]
assert "view-audit-logs" in perms, f"Missing view-audit-logs: {perms}"
logs = list_audit_logs(5)
print(json.dumps({
    "loginOk": True,
    "role": login["user"]["roleName"],
    "hasViewAuditLogs": True,
    "auditLogSample": len(logs),
}, indent=2))
