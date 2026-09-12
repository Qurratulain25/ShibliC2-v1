from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from ..auth.service import (
    admin_create_user,
    admin_reset_password,
    deactivate_user,
    forgot_password,
    get_current_user,
    list_users,
    login_user,
    register_first_admin,
    require_roles,
    set_session_connection_mode,
    update_user_role,
    user_count,
)
from ..core.database import (
    ROLE_PERMISSIONS,
    get_user_by_username,
    get_user_camera_ids,
    list_local_cameras,
    log_action,
    set_user_camera_ids,
    update_user_permissions,
    update_user_profile,
)
from ..models import (
    ConnectionModeRequest,
    CreateUserRequest,
    ForgotPasswordRequest,
    LoginRequest,
    ResetPasswordRequest,
    UpdateUserRequest,
    UserCamerasRequest,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/setup-required")
def setup_required() -> Dict[str, bool]:
    return {"setupRequired": user_count() == 0}


@router.post("/login")
def login(payload: LoginRequest) -> Dict[str, Any]:
    result = login_user(payload.username, payload.password, payload.connection_mode)
    try:
        from ..services.go2rtc import apply_streams_for_mode

        apply_streams_for_mode(result.get("connectionMode") or "lan")
    except Exception:
        pass
    return result


@router.post("/connection-mode")
def change_connection_mode(
    payload: ConnectionModeRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    result = set_session_connection_mode(user, payload.connection_mode)
    try:
        from ..services.go2rtc import apply_streams_for_mode

        apply_streams_for_mode(result.get("connectionMode") or "lan")
    except Exception:
        pass
    return result


@router.post("/create-first-admin")
def create_first_admin(payload: LoginRequest) -> Dict[str, Any]:
    return register_first_admin(payload.username, payload.password)


@router.post("/forgot-password")
def forgot_password_route(payload: ForgotPasswordRequest) -> Dict[str, Any]:
    forgot_password(payload.username, payload.recovery_code, payload.new_password)
    return {"ok": True, "message": "Password updated — you can sign in now"}


@router.get("/verify")
def verify(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return {"user": user}


@router.post("/logout")
def logout(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    log_action(user["username"], "logout", "session ended", role_name=user["roleName"], module="auth")
    return {"ok": True}


@router.get("/role-permissions")
def role_permissions(_: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return {"roles": ROLE_PERMISSIONS}


@router.get("/users")
def get_users(_: Dict[str, Any] = Depends(require_roles("ADMINISTRATOR"))) -> Dict[str, Any]:
    users = [
        {
            "username": u["username"],
            "fullName": u.get("fullName", ""),
            "roleName": u["roleName"],
            "permissions": u.get("permissions", []),
            "active": u.get("active", True),
            "createdAt": u["createdAt"],
            "cameraIds": get_user_camera_ids(u["username"]),
        }
        for u in list_users(include_inactive=True)
    ]
    return {"users": users}


@router.post("/users")
def create_user(
    payload: CreateUserRequest,
    admin: Dict[str, Any] = Depends(require_roles("ADMINISTRATOR")),
) -> Dict[str, Any]:
    return admin_create_user(
        payload.username, payload.password, payload.role,
        payload.full_name, payload.permissions,
    )


@router.put("/users/{username}")
def update_user(
    username: str,
    payload: UpdateUserRequest,
    admin: Dict[str, Any] = Depends(require_roles("ADMINISTRATOR")),
) -> Dict[str, Any]:
    if admin["username"] == username and payload.active is False:
        raise HTTPException(status_code=400, detail="Cannot disable yourself")
    user = get_user_by_username(username, include_inactive=True)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.full_name is not None or payload.active is not None:
        update_user_profile(username, full_name=payload.full_name, active=payload.active)
        if payload.active is False:
            log_action(admin["username"], "user_disable", username, role_name=admin["roleName"], module="users")
    if payload.role:
        update_user_role(username, payload.role, payload.permissions)
        log_action(admin["username"], "user_role_update", username, role_name=admin["roleName"], module="users")
    elif payload.permissions is not None:
        update_user_permissions(username, payload.permissions)
        log_action(admin["username"], "user_permissions_update", username, role_name=admin["roleName"], module="users")
    updated = get_user_by_username(username, include_inactive=True)
    return {
        "ok": True,
        "user": {
            "username": updated["username"],
            "fullName": updated.get("fullName", ""),
            "roleName": updated["roleName"],
            "permissions": updated.get("permissions", []),
            "active": updated.get("active", True),
            "cameraIds": get_user_camera_ids(username),
        },
    }


@router.put("/users/{username}/role")
def set_role(
    username: str,
    role: str,
    _: Dict[str, Any] = Depends(require_roles("ADMINISTRATOR")),
) -> Dict[str, Any]:
    update_user_role(username, role)
    return {"ok": True, "username": username, "role": role.upper()}


@router.get("/users/{username}/cameras")
def get_user_cameras(
    username: str,
    _: Dict[str, Any] = Depends(require_roles("ADMINISTRATOR")),
) -> Dict[str, Any]:
    if not get_user_by_username(username, include_inactive=True):
        raise HTTPException(status_code=404, detail="User not found")
    return {"username": username, "cameraIds": get_user_camera_ids(username)}


@router.put("/users/{username}/cameras")
def put_user_cameras(
    username: str,
    payload: UserCamerasRequest,
    admin: Dict[str, Any] = Depends(require_roles("ADMINISTRATOR")),
) -> Dict[str, Any]:
    if not get_user_by_username(username, include_inactive=True):
        raise HTTPException(status_code=404, detail="User not found")
    set_user_camera_ids(username, payload.camera_ids)
    log_action(
        admin["username"],
        "user_cameras_assign",
        f"{username}:{payload.camera_ids}",
        role_name=admin["roleName"],
        module="users",
    )
    return {"ok": True, "username": username, "cameraIds": get_user_camera_ids(username)}


@router.post("/users/{username}/disable")
def disable_user(
    username: str,
    admin: Dict[str, Any] = Depends(require_roles("ADMINISTRATOR")),
) -> Dict[str, Any]:
    if admin["username"] == username:
        raise HTTPException(status_code=400, detail="Cannot disable yourself")
    deactivate_user(username)
    log_action(admin["username"], "user_disable", username, role_name=admin["roleName"], module="users")
    return {"ok": True, "username": username}


@router.post("/users/{username}/reset-password")
def reset_user_password(
    username: str,
    payload: ResetPasswordRequest,
    admin: Dict[str, Any] = Depends(require_roles("ADMINISTRATOR")),
) -> Dict[str, Any]:
    admin_reset_password(username, payload.password)
    log_action(admin["username"], "user_password_reset", username, role_name=admin["roleName"], module="users")
    return {"ok": True, "username": username}


@router.delete("/users/{username}")
def delete_user(
    username: str,
    admin: Dict[str, Any] = Depends(require_roles("ADMINISTRATOR")),
) -> Dict[str, Any]:
    if admin["username"] == username:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    deactivate_user(username)
    log_action(admin["username"], "user_delete", username, role_name=admin["roleName"], module="users")
    return {"ok": True}
