"""Media, diagnostics, PTZ telemetry, LRF continuous — Phase 1 hardware readiness."""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth.service import get_current_user, require_permission
from ..core.database import list_local_cameras
from ..hardware import gateway
from ..models import FocusAutoRequest, FocusHoldRequest, FocusModeRequest, LRFRequest, MotorSpeedRequest, ThermalImageRequest
from ..services.camera_ids import resolve_channel_camera_id
from ..services.go2rtc import build_config, fetch_streams, go2rtc_enabled, probe_go2rtc

router = APIRouter(tags=["media"])


def _controls_camera_id(camera: Dict[str, Any] | None) -> str | None:
    if not camera:
        return None
    ip = str(camera.get("ipAddress") or "").strip()
    if not ip:
        return None
    return f"{ip}:{camera.get('onvifPort') or 80}"


def resolve_focus_camera_id(
    channel: str | None,
    camera_id: str | None,
    ptz_id: str | None,
    connection_mode: str | None = None,
) -> tuple[str | None, str | None]:
    """Thermal AFC must target the thermal camera. Day AFC keeps the request camera_id."""
    want = (channel or "").strip().lower()
    if want != "thermal":
        return camera_id, None

    cameras = [c for c in list_local_cameras(connection_mode=connection_mode) if c.get("enabled")]
    typed = [c for c in cameras if str(c.get("cameraType") or "").lower() == "thermal"]
    if not typed:
        return None, "No thermal camera configured"

    mapped = [c for c in typed if ptz_id and c.get("ptzMapping") == ptz_id]
    if not mapped and camera_id:
        anchor = next((c for c in cameras if _controls_camera_id(c) == camera_id), None)
        mapping = (anchor or {}).get("ptzMapping")
        if mapping and mapping != "none":
            mapped = [c for c in typed if c.get("ptzMapping") == mapping]
    pick = (mapped or typed)[0]
    cid = _controls_camera_id(pick)
    if cid:
        return cid, None
    return None, "No IP configured for the thermal camera"


@router.get("/api/go2rtc/config")
def go2rtc_config(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return build_config(list_local_cameras(connection_mode=user.get("connectionMode")))


@router.get("/api/go2rtc/streams")
def go2rtc_streams(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    data = fetch_streams()
    return {"online": data is not None, "streams": data or {}}


@router.get("/api/ptz/status")
async def ptz_status(
    camera_id: str | None = None,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    if getattr(gateway, "simulate", False):
        snap = gateway.snapshot()
        tel = snap.get("telemetry") or {}
        return {
            "ok": True,
            "simulated": True,
            "azimuth": tel.get("azimuth"),
            "elevation": tel.get("elevation"),
            "zoom": tel.get("zoom", 1),
        }
    if hasattr(gateway, "fetch_ptz_status"):
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(gateway.fetch_ptz_status, camera_id),
                timeout=1.0,
            )
        except Exception:
            snap = gateway.snapshot()
            tel = snap.get("telemetry") or {}
            return {
                "ok": True,
                "stale": True,
                "azimuth": tel.get("azimuth"),
                "elevation": tel.get("elevation"),
                "zoom": tel.get("zoom", 1),
            }
    snap = gateway.snapshot()
    tel = snap.get("telemetry") or {}
    return {
        "ok": True,
        "azimuth": tel.get("azimuth"),
        "elevation": tel.get("elevation"),
        "zoom": tel.get("zoom", 1),
    }


@router.post("/api/ptz/focus/auto")
def ptz_focus_auto(
    payload: FocusAutoRequest,
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
) -> Dict[str, Any]:
    cam, err = resolve_focus_camera_id(
        payload.channel, payload.camera_id, payload.ptz_id, user.get("connectionMode")
    )
    if err:
        return {"ok": False, "error": err, "command": f"focus:auto:{payload.channel}"}
    if payload.auto is not None and hasattr(gateway, "set_focus_mode"):
        return gateway.set_focus_mode(bool(payload.auto), cam, channel=payload.channel)
    if not hasattr(gateway, "focus_auto"):
        raise HTTPException(status_code=501, detail="Auto-focus not available")
    return gateway.focus_auto(cam, channel=payload.channel)


@router.post("/api/ptz/focus/mode")
def ptz_focus_mode(
    payload: FocusModeRequest,
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
) -> Dict[str, Any]:
    cam, err = resolve_focus_camera_id(
        payload.channel, payload.camera_id, payload.ptz_id, user.get("connectionMode")
    )
    if err:
        return {"ok": False, "error": err}
    return gateway.set_focus_mode(payload.auto, cam, channel=payload.channel)


@router.post("/api/ptz/focus/start")
def ptz_focus_start(
    payload: FocusHoldRequest,
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
) -> Dict[str, Any]:
    cam, err = resolve_focus_camera_id(
        payload.channel, payload.camera_id, payload.ptz_id, user.get("connectionMode")
    )
    if err:
        return {"ok": False, "error": err}
    return gateway.start_focus(payload.direction, cam)


@router.post("/api/ptz/focus/stop")
def ptz_focus_stop(
    payload: FocusHoldRequest,
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
) -> Dict[str, Any]:
    cam, err = resolve_focus_camera_id(
        payload.channel, payload.camera_id, payload.ptz_id, user.get("connectionMode")
    )
    if err:
        return {"ok": False, "error": err}
    return gateway.stop_focus(cam)


@router.post("/api/ptz/speed")
def ptz_speed(
    payload: MotorSpeedRequest,
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
) -> Dict[str, Any]:
    return gateway.apply_motor_speed(payload.speed, payload.camera_id)


@router.get("/api/ptz/zoom-level")
def ptz_zoom_level(
    camera_id: str | None = None,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    if hasattr(gateway, "fetch_zoom_level"):
        return gateway.fetch_zoom_level(camera_id)
    return {"ok": True, "zoom_level": None}


@router.post("/api/thermal/image")
def thermal_image(
    payload: ThermalImageRequest,
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
) -> Dict[str, Any]:
    cam, err = resolve_channel_camera_id("thermal", payload.camera_id, payload.ptz_id)
    if err:
        return {"ok": False, "error": err}
    data = payload.model_dump(exclude_unset=True)
    data.pop("camera_id", None)
    data.pop("ptz_id", None)
    return gateway.set_thermal_image(cam, **data)


@router.post("/api/lrf/continuous/start")
def lrf_continuous_start(
    payload: LRFRequest,
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
) -> Dict[str, Any]:
    if hasattr(gateway, "lrf_continuous_start"):
        return gateway.lrf_continuous_start(payload.camera_id)
    return gateway.measure_lrf("continuous", payload.camera_id)


@router.post("/api/lrf/continuous/stop")
def lrf_continuous_stop(
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
) -> Dict[str, Any]:
    if hasattr(gateway, "lrf_continuous_stop"):
        return gateway.lrf_continuous_stop()
    return {"ok": True}


@router.get("/api/lrf/distance")
def lrf_distance(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    snap = gateway.snapshot()
    lrf = snap.get("lrf") or {}
    return {
        "range_m": lrf.get("range_m"),
        "mode": lrf.get("mode"),
        "cursor": lrf.get("cursor"),
    }


@router.get("/api/diag")
async def system_diag(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    from ..services.retention import storage_status
    from ..services.shibli_client import backend_status

    local = list_local_cameras()
    enabled = [c for c in local if c.get("enabled")]
    services = await backend_status()
    go2rtc_on = False
    if go2rtc_enabled():
        try:
            go2rtc_on = await asyncio.wait_for(asyncio.to_thread(probe_go2rtc), timeout=0.5)
        except Exception:
            go2rtc_on = False
    snap = gateway.snapshot()

    day_cam = next((c for c in enabled if (c.get("cameraType") or "").lower() == "day"), None)
    th_cam = next((c for c in enabled if (c.get("cameraType") or "").lower() == "thermal"), None)

    return {
        "ok": True,
        "go2rtc": {"online": bool(go2rtc_on)},
        "controls": services.get("controls") or {"online": False},
        "vss": services.get("vss") or {"online": False},
        "core": services.get("core") or {"online": False},
        "day_camera": {
            "configured": day_cam is not None,
            "reachable": False,
            "ip": (day_cam or {}).get("ipAddress") or "",
        },
        "thermal_camera": {
            "configured": th_cam is not None,
            "reachable": False,
            "ip": (th_cam or {}).get("ipAddress") or "",
        },
        "lrf": {"online": bool(snap.get("connected"))},
        "illuminator": {"online": bool(snap.get("connected"))},
        "storage": storage_status(),
        "cameras_enabled": len(enabled),
        "simulate": bool(snap.get("simulated")),
    }


@router.post("/api/hardware/self-test")
async def hardware_self_test(
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
) -> Dict[str, Any]:
    from ..services.hardware_self_test import run_hardware_self_test

    return await run_hardware_self_test(user)


@router.post("/api/hardware/simulate")
def hardware_simulate(
    enabled: bool = Query(True),
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
) -> Dict[str, Any]:
    from ..core.settings_store import update_settings

    update_settings({"hw_simulate": bool(enabled)})
    if hasattr(gateway, "set_simulate"):
        gateway.set_simulate(bool(enabled))
    return {"ok": True, "simulate": bool(getattr(gateway, "simulate", enabled))}
