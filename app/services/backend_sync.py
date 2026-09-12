"""Map SHIBLI-Core cameras into SHIBLI-controls for PTZ/LRF/illumination."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..services.shibli_client import controls_request, core_request


def _controls_camera_id(onvif: Dict[str, Any]) -> Optional[str]:
    ip = onvif.get("ip")
    if not ip:
        return None
    port = onvif.get("port") or 80
    return f"{ip}:{port}"


async def sync_core_cameras_to_controls(token: str) -> Dict[str, Any]:
    """Register each Core camera (with ONVIF creds) into SHIBLI-controls."""
    streams_res = await core_request("GET", "/api/camera/streams", token=token)
    if not streams_res.get("ok"):
        return {
            "ok": False,
            "error": streams_res.get("error") or "Cannot reach SHIBLI-Core",
            "synced": [],
        }

    streams: List[Dict[str, Any]] = streams_res.get("data", {}).get("streams") or []
    synced: List[Dict[str, Any]] = []
    errors: List[str] = []

    for stream in streams:
        cam_id = stream.get("id")
        if not cam_id:
            continue
        detail_res = await core_request("GET", f"/api/camera/stream/{cam_id}", token=token)
        if not detail_res.get("ok"):
            errors.append(f"{stream.get('name', cam_id)}: Core detail failed")
            continue

        data = detail_res.get("data") or {}
        onvif = data.get("onvifConfig") or {}
        illuminator = data.get("illuminatorConfig") or {}
        controls_id = _controls_camera_id(onvif)
        if not controls_id:
            errors.append(f"{stream.get('name', cam_id)}: no RGB/ONVIF IP in Core")
            continue

        payload: Dict[str, Any] = {
            "camera_ip": onvif["ip"],
            "camera_port": onvif.get("port") or 80,
            "username": onvif.get("username") or "admin",
            "password": onvif.get("password") or "",
            "onvif_port": onvif.get("port") or 80,
            "camera_id": controls_id,
        }
        if illuminator.get("ip"):
            payload["illuminator_ip"] = illuminator["ip"]
            payload["illuminator_tcp_port"] = illuminator.get("port") or 8234
            payload["illuminator_username"] = illuminator.get("username") or "admin"
            payload["illuminator_password"] = illuminator.get("password") or "admin"

        lrf = data.get("lrfConfig") or {}
        thermal = data.get("thermalConfig") or {}

        reg = await controls_request(
            "POST",
            "/api/camera/cameras/register",
            token,
            json=payload,
        )
        if reg.get("ok"):
            synced.append({"name": stream.get("name"), "camera_id": controls_id})
            if lrf.get("ip"):
                await controls_request(
                    "POST",
                    "/api/camera/lrf/register",
                    token,
                    json={
                        "lrf_ip": lrf["ip"],
                        "lrf_port": lrf.get("port") or 8234,
                        "username": lrf.get("username") or "admin",
                        "password": lrf.get("password") or "admin",
                        "camera_id": f"{controls_id}-lrf",
                    },
                )
            if thermal.get("ip"):
                thermal_id = f"{thermal['ip']}:{thermal.get('port') or 80}"
                await controls_request(
                    "POST",
                    "/api/camera/cameras/register",
                    token,
                    json={
                        "camera_ip": thermal["ip"],
                        "camera_port": thermal.get("port") or 80,
                        "username": thermal.get("username") or "admin",
                        "password": thermal.get("password") or "",
                        "onvif_port": thermal.get("port") or 80,
                        "camera_id": thermal_id,
                    },
                )
        else:
            errors.append(f"{stream.get('name', cam_id)}: {reg.get('data') or reg.get('status')}")

    return {"ok": True, "synced": synced, "errors": errors, "total": len(streams)}


async def build_bootstrap(token: str, user: Dict[str, Any]) -> Dict[str, Any]:
    from ..auth.service import create_access_token
    from ..services.shibli_client import backend_status

    ctrl_token = token or create_access_token(user)
    services = await backend_status()

    core_cameras: List[Dict[str, Any]] = []
    if services.get("core", {}).get("online"):
        core_res = await core_request("GET", "/api/camera/streams", token=token)
        if core_res.get("ok"):
            for cam in core_res.get("data", {}).get("streams") or []:
                rgb = cam.get("rgb") or {}
                thermal = cam.get("thermal") or {}
                controls_id = None
                if rgb.get("ip"):
                    controls_id = f"{rgb['ip']}:{rgb.get('port') or 80}"
                core_cameras.append({
                    "id": cam.get("id"),
                    "name": cam.get("name"),
                    "controlsId": controls_id,
                    "rgbIp": rgb.get("ip") or cam.get("ipAddress"),
                    "rgbStreamUrl": rgb.get("streamUrl") or cam.get("url"),
                    "thermalStreamUrl": thermal.get("streamUrl"),
                    "streamType": cam.get("streamType"),
                    "quality": cam.get("quality"),
                })

    controls_list: List[Dict[str, Any]] = []
    if services.get("controls", {}).get("online"):
        ctrl_res = await controls_request("GET", "/api/camera/cameras", ctrl_token)
        if ctrl_res.get("ok"):
            data = ctrl_res.get("data") or {}
            controls_list = data.get("cameras") if isinstance(data, dict) else data
            if not isinstance(controls_list, list):
                controls_list = []

    default_camera = controls_list[0].get("camera_id") if controls_list else (
        core_cameras[0].get("controlsId") if core_cameras else None
    )

    from ..core.database import list_local_cameras

    local_cams = list_local_cameras()
    local_enabled = [c for c in local_cams if c.get("enabled")]
    controls_online = bool(services.get("controls", {}).get("online"))
    needs_sync = controls_online and len(local_enabled) > 0 and len(controls_list) == 0
    if not needs_sync and controls_online and len(core_cameras) > 0 and len(controls_list) == 0:
        needs_sync = True

    return {
        "services": services,
        "cameras": core_cameras,
        "controlsCameras": controls_list,
        "defaultCameraId": default_camera,
        "mapping": {
            "coreOnline": services.get("core", {}).get("online", False),
            "controlsOnline": controls_online,
            "vssOnline": services.get("vss", {}).get("online", False),
            "coreCameraCount": len(core_cameras),
            "controlsCameraCount": len(controls_list),
            "localCameraCount": len(local_enabled),
            "localConfigured": len(local_cams),
            "needsSync": needs_sync,
            "controlsUrl": services.get("controls", {}).get("url"),
        },
    }
