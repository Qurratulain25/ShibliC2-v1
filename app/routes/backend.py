from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Header, Request

from ..auth.service import create_access_token, get_current_user, require_permission
from ..core.database import log_action
from ..services.backend_sync import build_bootstrap, sync_core_cameras_to_controls
from ..services.controls_sync import sync_local_cameras_to_controls
from ..services.shibli_client import backend_status, controls_request, core_request, vss_request

router = APIRouter(prefix="/api/backend", tags=["backend"])


def _token_from_header(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        return ""
    return authorization.split(" ", 1)[1]


@router.get("/bootstrap")
async def bootstrap(
    user: Dict[str, Any] = Depends(get_current_user),
    authorization: str | None = Header(default=None),
) -> Dict[str, Any]:
    token = _token_from_header(authorization)
    return await build_bootstrap(token, user)


@router.post("/sync")
async def sync_cameras(
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
    authorization: str | None = Header(default=None),
) -> Dict[str, Any]:
    from ..services.shibli_client import probe_controls_online

    token = _token_from_header(authorization) or create_access_token(user)
    online, detail = await probe_controls_online()
    if not online:
        return {
            "ok": False,
            "error": f"SHIBLI-controls offline ({detail}). Start it with ./scripts/start-controls.sh",
            "synced": [],
            "errors": [detail],
            "controls_online": False,
        }

    core_result = await sync_core_cameras_to_controls(token)
    local_result = await sync_local_cameras_to_controls(token)
    synced = (core_result.get("synced") or []) + (local_result.get("synced") or [])
    errors = (core_result.get("errors") or []) + (local_result.get("errors") or [])
    result = {
        "ok": bool(synced) or not errors,
        "synced": synced,
        "errors": errors,
        "core": core_result,
        "local": local_result,
        "controls_online": True,
    }
    if not synced and errors:
        result["error"] = "; ".join(errors[:3])
    log_action(
        user["username"],
        "camera_sync",
        f"synced={len(synced)} errors={len(errors)}",
        role_name=user["roleName"],
        module="cameras",
    )
    if result.get("synced"):
        from ..adapters import gateway
        first = result["synced"][0].get("camera_id")
        if first and hasattr(gateway, "set_active_camera"):
            gateway.set_active_camera(first)
    return result


@router.get("/status")
async def status() -> Dict[str, Any]:
    return await backend_status()


@router.get("/cameras")
async def list_cameras(
    user: Dict[str, Any] = Depends(require_permission("get-streams")),
    authorization: str | None = Header(default=None),
) -> Dict[str, Any]:
    token = _token_from_header(authorization)
    return await core_request("GET", "/api/camera/streams", token=token)


@router.get("/cameras/{camera_id}")
async def get_camera(
    camera_id: str,
    user: Dict[str, Any] = Depends(require_permission("get-streams")),
    authorization: str | None = Header(default=None),
) -> Dict[str, Any]:
    token = _token_from_header(authorization)
    return await core_request("GET", f"/api/camera/stream/{camera_id}", token=token)


@router.get("/recordings")
async def list_recordings(
    user: Dict[str, Any] = Depends(require_permission("get-streams")),
    authorization: str | None = Header(default=None),
) -> Dict[str, Any]:
    token = _token_from_header(authorization)
    return await core_request("GET", "/api/recording/", token=token)


@router.get("/recordings/stats")
async def recording_stats(
    user: Dict[str, Any] = Depends(require_permission("get-streams")),
    authorization: str | None = Header(default=None),
) -> Dict[str, Any]:
    token = _token_from_header(authorization)
    return await core_request("GET", "/api/recording/stats", token=token)


@router.get("/controls/cameras")
async def controls_cameras(
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
    authorization: str | None = Header(default=None),
) -> Dict[str, Any]:
    token = _token_from_header(authorization) or create_access_token(user)
    return await controls_request("GET", "/api/camera/cameras", token)


@router.get("/controls/usr")
async def controls_usr(
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
    authorization: str | None = Header(default=None),
) -> Dict[str, Any]:
    token = _token_from_header(authorization) or create_access_token(user)
    return await controls_request("GET", "/api/camera/usr/status", token)


@router.get("/vss/health")
async def vss_health(
    user: Dict[str, Any] = Depends(get_current_user),
    authorization: str | None = Header(default=None),
) -> Dict[str, Any]:
    token = _token_from_header(authorization) or create_access_token(user)
    return await vss_request("GET", "/api/health", token)
