"""Resolve SHIBLI-controls camera IDs for day / thermal / LRF."""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from ..core.database import list_local_cameras


def controls_camera_id(camera: Dict[str, Any] | None) -> Optional[str]:
    if not camera:
        return None
    ip = str(camera.get("ipAddress") or "").strip()
    if not ip:
        return None
    return f"{ip}:{camera.get('onvifPort') or 80}"


def lrf_camera_id(camera_id: str | None) -> Optional[str]:
    if not camera_id:
        return None
    if camera_id.endswith("-lrf"):
        return camera_id
    return f"{camera_id}-lrf"


def _typed_cameras(channel: str) -> list[Dict[str, Any]]:
    want = (channel or "").strip().lower()
    return [
        c
        for c in list_local_cameras()
        if c.get("enabled") and str(c.get("cameraType") or "").lower() == want
    ]


def resolve_channel_camera_id(
    channel: str | None,
    camera_id: str | None,
    ptz_id: str | None,
) -> Tuple[Optional[str], Optional[str]]:
    """Thermal commands must target the thermal camera, not the day PTZ id."""
    want = (channel or "").strip().lower()
    if want != "thermal":
        return camera_id, None

    typed = _typed_cameras("thermal")
    if not typed:
        return None, "No thermal camera configured"

    mapped = [c for c in typed if ptz_id and c.get("ptzMapping") == ptz_id]
    if not mapped and camera_id:
        cameras = [c for c in list_local_cameras() if c.get("enabled")]
        anchor = next((c for c in cameras if controls_camera_id(c) == camera_id), None)
        mapping = (anchor or {}).get("ptzMapping")
        if mapping and mapping != "none":
            mapped = [c for c in typed if c.get("ptzMapping") == mapping]
    pick = (mapped or typed)[0]
    cid = controls_camera_id(pick)
    if cid:
        return cid, None
    return None, "No IP configured for the thermal camera"


def day_camera_for_ptz(ptz_id: str | None) -> Optional[Dict[str, Any]]:
    cameras = [c for c in list_local_cameras() if c.get("enabled")]
    if ptz_id:
        mapped = [c for c in cameras if c.get("ptzMapping") == ptz_id]
        day = next((c for c in mapped if str(c.get("cameraType") or "").lower() == "day"), None)
        if day:
            return day
        if mapped:
            return mapped[0]
    return next((c for c in cameras if str(c.get("cameraType") or "").lower() == "day"), cameras[0] if cameras else None)
