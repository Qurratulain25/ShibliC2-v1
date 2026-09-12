"""Register local cameras with SHIBLI-controls for PTZ/LRF/illumination."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import quote

from ..auth.service import create_access_token
from ..core.database import get_local_camera_credentials, list_local_cameras
from .shibli_client import controls_request, probe_controls_online


def _register_payload(cam: Dict[str, Any], password: str) -> Dict[str, Any]:
    controls_id = f"{cam['ipAddress']}:{cam.get('onvifPort') or 80}"
    payload: Dict[str, Any] = {
        "camera_ip": cam["ipAddress"],
        "camera_port": cam.get("onvifPort") or 80,
        "username": cam.get("username") or "admin",
        "password": password,
        "onvif_port": cam.get("onvifPort") or 80,
        "camera_id": controls_id,
    }
    cam_type = str(cam.get("cameraType") or cam.get("camera_type") or "").lower()
    if cam_type != "thermal":
        payload["illuminator_ip"] = cam.get("ipAddress")
        payload["illuminator_tcp_port"] = 8234
        payload["illuminator_username"] = cam.get("username") or "admin"
        payload["illuminator_password"] = password or "admin"
    return payload


async def _register_lrf(token: str, cam: Dict[str, Any], password: str, controls_id: str) -> Dict[str, Any]:
    from ..adapters import gateway

    lrf_ip = cam.get("ipAddress") or ""
    if not lrf_ip:
        return {"ok": False, "error": "No IP for LRF"}
    if hasattr(gateway, "register_lrf"):
        return gateway.register_lrf(
            lrf_ip,
            8234,
            cam.get("username") or "admin",
            password or "admin",
            controls_id,
        )
    return await controls_request(
        "POST",
        "/api/camera/lrf/register",
        token,
        json={
            "lrf_ip": lrf_ip,
            "lrf_port": 8234,
            "username": cam.get("username") or "admin",
            "password": password or "admin",
            "camera_id": f"{controls_id}-lrf",
        },
    )


async def _connect_camera(token: str, controls_id: str) -> Dict[str, Any]:
    encoded = quote(controls_id, safe="")
    return await controls_request(
        "POST",
        f"/api/camera/cameras/{encoded}/connect",
        token,
    )


async def _set_default_camera(token: str, controls_id: str) -> None:
    await controls_request(
        "POST",
        "/api/camera/cameras/default",
        token,
        json={"camera_id": controls_id},
    )


async def register_local_camera(
    camera_id: int,
    token: str,
) -> Dict[str, Any]:
    cams = [c for c in list_local_cameras() if c.get("id") == camera_id]
    if not cams:
        return {"ok": False, "error": "Camera not found"}
    cam = cams[0]
    if not cam.get("enabled") or not cam.get("ipAddress"):
        return {"ok": False, "error": "Camera disabled or missing IP"}

    online, detail = await probe_controls_online()
    if not online:
        return {
            "ok": False,
            "error": f"SHIBLI-controls offline ({detail}). Run ./scripts/start-controls.sh",
            "controls_online": False,
        }

    creds = get_local_camera_credentials(camera_id)
    payload = _register_payload(cam, creds.get("password", ""))
    reg = await controls_request(
        "POST",
        "/api/camera/cameras/register",
        token,
        json=payload,
    )
    if reg.get("ok"):
        from ..adapters import gateway

        if hasattr(gateway, "set_active_camera"):
            gateway.set_active_camera(payload["camera_id"])
        return {
            "ok": True,
            "camera_id": payload["camera_id"],
            "name": cam.get("name"),
            "controls_online": True,
        }
    return {
        "ok": False,
        "error": str(reg.get("data") or reg.get("error") or reg.get("status")),
        "controls_online": True,
    }


async def sync_local_cameras_to_controls(token: str) -> Dict[str, Any]:
    """Register all enabled local cameras into SHIBLI-controls."""
    online, detail = await probe_controls_online()
    if not online:
        return {
            "ok": False,
            "error": f"SHIBLI-controls offline ({detail}). Run ./scripts/start-controls.sh",
            "synced": [],
            "errors": [detail],
            "controls_online": False,
        }

    synced: List[Dict[str, Any]] = []
    errors: List[str] = []
    seen_ids: set[str] = set()
    for cam in list_local_cameras():
        if not cam.get("enabled") or not cam.get("ipAddress"):
            continue
        creds = get_local_camera_credentials(int(cam["id"]))
        payload = _register_payload(cam, creds.get("password", ""))
        controls_id = payload["camera_id"]
        if controls_id in seen_ids:
            continue
        seen_ids.add(controls_id)
        reg = await controls_request(
            "POST",
            "/api/camera/cameras/register",
            token,
            json=payload,
        )
        if reg.get("ok"):
            conn = await _connect_camera(token, controls_id)
            lrf = {}
            cam_type = str(cam.get("cameraType") or "").lower()
            if cam_type != "thermal":
                lrf = await _register_lrf(token, cam, creds.get("password", ""), controls_id)
            entry: Dict[str, Any] = {
                "name": cam.get("name"),
                "camera_id": controls_id,
                "connected": bool(conn.get("ok")),
                "lrf": bool(lrf.get("ok")) if lrf else None,
            }
            if not conn.get("ok"):
                detail = conn.get("data") or conn.get("error")
                if detail:
                    entry["connect_error"] = str(detail)
                    errors.append(f"{cam.get('name')}: connect failed — {detail}")
            synced.append(entry)
        else:
            errors.append(f"{cam.get('name')}: {reg.get('data') or reg.get('status')}")

    if synced:
        from ..adapters import gateway

        first = synced[0].get("camera_id")
        if first:
            await _set_default_camera(token, first)
            if hasattr(gateway, "set_active_camera"):
                gateway.set_active_camera(first)
            if hasattr(gateway, "warm_camera"):
                gateway.warm_camera(first)

    return {
        "ok": True,
        "synced": synced,
        "errors": errors,
        "total": len(list_local_cameras()),
        "controls_online": True,
    }


async def auto_sync_local_cameras(user: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Best-effort sync after camera save when controls is online."""
    token = create_access_token(user)
    result = await sync_local_cameras_to_controls(token)
    if result.get("synced"):
        return result
    return None
