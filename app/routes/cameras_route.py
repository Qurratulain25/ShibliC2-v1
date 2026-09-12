from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..auth.service import get_current_user, require_permission
from ..core.connection_mode import normalize_camera_mode, normalize_session_mode
from ..core.database import (
    delete_local_camera,
    get_local_camera,
    insert_local_camera,
    list_local_cameras,
    log_action,
    update_local_camera,
)
from ..services.camera_test import test_camera_connection

router = APIRouter(prefix="/api/cameras/local", tags=["cameras"])


class CameraPayload(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    camera_type: str = Field(default="Day", pattern="^(Day|Thermal|Other)$")
    ip_address: str = ""
    rtsp_url: str = ""
    onvif_port: int = Field(default=80, ge=1, le=65535)
    username: str = ""
    password: str = ""
    ptz_mapping: str = Field(default="none", pattern="^(none|ptz-1|ptz-2)$")
    camera_group: str = ""
    enabled: bool = True
    connection_mode: Optional[str] = Field(default=None, max_length=32)


@router.get("")
def list_cameras(
    include_all: bool = Query(default=False),
    connection_mode: str | None = Query(default=None),
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    perms = user.get("permissions") or []
    if include_all:
        if "manage-cameras" not in perms:
            raise HTTPException(status_code=403, detail="Missing permission: manage-cameras")
        cams = list_local_cameras(include_rtsp=True)
        return {"cameras": cams, "count": len(cams), "connectionMode": None}

    if "get-streams" not in perms and "manage-cameras" not in perms:
        raise HTTPException(status_code=403, detail="Missing permission: get-streams")
    mode = normalize_session_mode(connection_mode or user.get("connectionMode") or "lan")
    include_rtsp = "manage-cameras" in perms
    cams = list_local_cameras(connection_mode=mode, include_rtsp=include_rtsp)
    return {"cameras": cams, "count": len(cams), "connectionMode": mode}


@router.post("")
async def create_camera(
    payload: CameraPayload,
    user: Dict[str, Any] = Depends(require_permission("manage-cameras")),
) -> Dict[str, Any]:
    from ..services.controls_sync import auto_sync_local_cameras

    payload_data = payload.model_dump()
    payload_data["connection_mode"] = normalize_camera_mode(payload.connection_mode, default="lan")
    cam = insert_local_camera(payload_data)
    log_action(user["username"], "camera_create", cam["name"], role_name=user["roleName"], module="cameras")
    sync = await auto_sync_local_cameras(user)
    return {"camera": cam, "sync": sync}


@router.put("/{camera_id}")
async def save_camera(
    camera_id: int,
    payload: CameraPayload,
    user: Dict[str, Any] = Depends(require_permission("manage-cameras")),
) -> Dict[str, Any]:
    from ..services.controls_sync import auto_sync_local_cameras

    payload_data = payload.model_dump()
    if payload.connection_mode:
        payload_data["connection_mode"] = normalize_camera_mode(payload.connection_mode, default="lan")
    else:
        payload_data.pop("connection_mode", None)
    cam = update_local_camera(camera_id, payload_data)
    if not cam:
        raise HTTPException(404, "Camera not found")
    log_action(user["username"], "camera_update", cam["name"], role_name=user["roleName"], module="cameras")
    sync = await auto_sync_local_cameras(user)
    return {"camera": cam, "sync": sync}


@router.delete("/{camera_id}")
def remove_camera(
    camera_id: int,
    user: Dict[str, Any] = Depends(require_permission("manage-cameras")),
) -> Dict[str, Any]:
    cam = get_local_camera(camera_id)
    if not cam or not delete_local_camera(camera_id):
        raise HTTPException(404, "Camera not found")
    log_action(user["username"], "camera_delete", cam["name"], role_name=user["roleName"], module="cameras")
    return {"ok": True}


@router.post("/test")
async def test_connection(
    payload: CameraPayload,
    user: Dict[str, Any] = Depends(require_permission("manage-cameras")),
) -> Dict[str, Any]:
    result = await test_camera_connection(payload.model_dump())
    log_action(
        user["username"],
        "camera_test",
        result.get("message", ""),
        role_name=user["roleName"],
        module="cameras",
        success=bool(result.get("ok")),
    )
    return result
