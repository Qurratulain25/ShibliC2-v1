from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..core.config import is_production, resolve_jwt_secret
from ..core.connection_mode import normalize_session_mode
from ..core.database import (
    ROLE_PERMISSIONS,
    create_user,
    deactivate_user,
    get_user_by_username,
    init_db,
    list_users,
    log_action,
    update_user_role,
    user_count,
)

JWT_EXPIRES_MIN = int(os.getenv("JWT_EXPIRES_MIN", "60"))
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_access_token(user: Dict[str, Any], connection_mode: str = "lan") -> str:
    payload = {
        "username": user["username"],
        "roleName": user["roleName"],
        "permissions": user["permissions"],
        "connectionMode": normalize_session_mode(connection_mode),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRES_MIN),
    }
    return jwt.encode(payload, resolve_jwt_secret(), algorithm="HS256")


def decode_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, resolve_jwt_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Dict[str, Any]:
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(creds.credentials)
    username = payload.get("username")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = get_user_by_username(username)
    if not user or not user.get("active", True):
        raise HTTPException(status_code=401, detail="User inactive or not found")
    return {
        "username": user["username"],
        "roleName": user["roleName"],
        "permissions": user["permissions"],
        "fullName": user.get("fullName", ""),
        "connectionMode": normalize_session_mode(payload.get("connectionMode")),
    }


def require_roles(*roles: str):
    async def checker(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if user.get("roleName") not in roles:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user

    return checker


def require_permission(permission: str):
    async def checker(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if permission not in user.get("permissions", []):
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")
        return user

    return checker


def login_user(username: str, password: str, connection_mode: str = "lan") -> Dict[str, Any]:
    user = get_user_by_username(username)
    if not user or not verify_password(password, user["password_hash"]):
        log_action(username, "login_failed", success=False)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    from ..core.database import sync_role_permissions_for_user
    sync_role_permissions_for_user(username, user["roleName"])
    user = get_user_by_username(username)
    mode = normalize_session_mode(connection_mode)
    token = create_access_token(user, mode)
    log_action(username, "login_success", f"connection_mode={mode}", module="auth")
    return {
        "accessToken": token,
        "user": {
            "username": user["username"],
            "roleName": user["roleName"],
            "permissions": user["permissions"],
            "connectionMode": mode,
        },
        "connectionMode": mode,
    }


def set_session_connection_mode(user: Dict[str, Any], connection_mode: str) -> Dict[str, Any]:
    mode = normalize_session_mode(connection_mode)
    token = create_access_token(user, mode)
    log_action(user.get("username"), "connection_mode_change", mode, module="auth")
    updated = {**user, "connectionMode": mode}
    return {
        "accessToken": token,
        "user": {
            "username": updated["username"],
            "roleName": updated["roleName"],
            "permissions": updated.get("permissions", []),
            "connectionMode": mode,
        },
        "connectionMode": mode,
    }


def register_first_admin(username: str, password: str) -> Dict[str, Any]:
    if user_count() > 0:
        raise HTTPException(status_code=403, detail="Users already exist")
    user = create_user(username, hash_password(password), "ADMINISTRATOR")
    log_action(username, "first_admin_created")
    return {"message": "Admin created", "user": {"username": user["username"], "roleName": user["roleName"]}}


def admin_create_user(
    username: str,
    password: str,
    role: str,
    full_name: str = "",
    permissions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if get_user_by_username(username, include_inactive=True):
        raise HTTPException(status_code=400, detail="Username exists")
    if role.upper() not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=400, detail="Invalid role")
    user = create_user(username, hash_password(password), role, full_name, permissions)
    log_action(username, "user_created", role, role_name=role, module="users")
    return {"username": user["username"], "roleName": user["roleName"]}


def admin_reset_password(username: str, password: str) -> None:
    from ..core.database import get_user_by_username, update_user_password
    if not get_user_by_username(username, include_inactive=True):
        raise HTTPException(status_code=404, detail="User not found")
    update_user_password(username, hash_password(password))
    log_action(username, "password_reset", module="users")


def forgot_password(username: str, recovery_code: str, new_password: str) -> None:
    from ..core.bootstrap_env import env_str

    expected = env_str("SHIBLI_PASSWORD_RECOVERY_CODE", "")
    generic = "Password reset failed"
    if not expected:
        log_action(username, "forgot_password_failed", "recovery not configured", success=False)
        raise HTTPException(status_code=403, detail=generic)
    if recovery_code != expected:
        log_action(username, "forgot_password_failed", "invalid recovery code", success=False)
        raise HTTPException(status_code=403, detail=generic)
    user = get_user_by_username(username, include_inactive=True)
    if not user or not user.get("active", True):
        log_action(username, "forgot_password_failed", "account unavailable", success=False)
        raise HTTPException(status_code=403, detail=generic)
    from ..core.database import update_user_password
    update_user_password(username, hash_password(new_password))
    log_action(username, "forgot_password_reset", module="auth")


def startup_auth() -> None:
    from ..core.bootstrap_env import env_str

    resolve_jwt_secret()

    init_db()
    from ..core.settings_store import seed_defaults
    from ..core.database import sync_all_role_permissions
    seed_defaults()
    sync_all_role_permissions()
    if user_count() > 0:
        return
    # Existing installs keep their users. Empty databases use first-run admin creation
    # in the UI — do not seed a public default password.
    if is_production():
        log_action("system", "first_run_setup_required", module="auth")
        return
    password = env_str("SHIBLI_DEFAULT_ADMIN_PASSWORD", "")
    username = env_str("SHIBLI_DEFAULT_ADMIN_USER", "admin")
    if not password:
        log_action("system", "first_run_setup_required", module="auth")
        return
    create_user(username, hash_password(password), "ADMINISTRATOR")
    log_action(username, "default_admin_seeded")
