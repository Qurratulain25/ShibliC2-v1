"""go2rtc integration — stream discovery and health for WebRTC playback."""
from __future__ import annotations

import logging
import os
import json
from typing import Any, Dict, Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

GO2RTC_API_URL = os.getenv("GO2RTC_API_URL", "http://127.0.0.1:1984").rstrip("/")


def go2rtc_enabled() -> bool:
    return os.getenv("GO2RTC_ENABLED", "1").lower() not in ("0", "false", "no")


def probe_go2rtc(timeout: float = 2.0) -> bool:
    if not go2rtc_enabled():
        return False
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{GO2RTC_API_URL}/api/streams")
            return response.status_code == 200
    except Exception as exc:
        logger.debug("go2rtc probe failed: %s", exc)
        return False


def fetch_streams(timeout: float = 2.0) -> Optional[Dict[str, Any]]:
    if not go2rtc_enabled():
        return None
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{GO2RTC_API_URL}/api/streams")
            if response.status_code == 200:
                return response.json()
    except Exception as exc:
        logger.debug("go2rtc streams fetch failed: %s", exc)
    return None


def _stream_producers(streams: Dict[str, Any], name: str) -> list:
    entry = streams.get(name) or {}
    producers = entry.get("producers") or []
    if isinstance(producers, list):
        return producers
    return []


def resolve_stream_id(channel: str, local_cameras: list, streams_data: Optional[Dict[str, Any]]) -> str:
    """Map day/thermal channel to go2rtc stream name."""
    defaults = {"day": "day", "thermal": "thermal"}
    preferred = os.getenv(f"GO2RTC_STREAM_{channel.upper()}", defaults.get(channel, channel))

    if streams_data and preferred in streams_data:
        return preferred

    cam = None
    want = "day" if channel == "day" else "thermal"
    for c in local_cameras:
        if not c.get("enabled"):
            continue
        ctype = (c.get("cameraType") or "").lower()
        if ctype == want or (channel == "day" and ctype == "day") or (channel == "thermal" and ctype == "thermal"):
            cam = c
            break

    if streams_data and cam:
        ip = (cam.get("ipAddress") or "").strip()
        for name, meta in streams_data.items():
            for prod in _stream_producers(streams_data, name):
                url = str(prod.get("url") or prod.get("remote_addr") or "")
                if ip and ip in url:
                    return name

    if streams_data:
        for name in streams_data:
            if channel in name.lower():
                return name
        if streams_data:
            return next(iter(streams_data.keys()), preferred)

    return preferred


def build_config(local_cameras: list) -> Dict[str, Any]:
    streams_data = fetch_streams()
    online = streams_data is not None
    return {
        "enabled": go2rtc_enabled(),
        "online": online,
        "api_url": GO2RTC_API_URL,
        "streams": {
            "day": resolve_stream_id("day", local_cameras, streams_data),
            "thermal": resolve_stream_id("thermal", local_cameras, streams_data),
        },
        "raw": streams_data or {},
    }


def encode_rtsp_credentials(rtsp_url: str) -> str:
    """URL-encode special chars in RTSP credentials for go2rtc.yaml."""
    if "://" not in rtsp_url or "@" not in rtsp_url:
        return rtsp_url
    scheme, rest = rtsp_url.split("://", 1)
    auth, host = rest.rsplit("@", 1)
    if ":" in auth:
        user, password = auth.split(":", 1)
        return f"{scheme}://{quote(user, safe='')}:{quote(password, safe='')}@{host}"
    return rtsp_url


def _yaml_scalar(value: str) -> str:
    if any(ch in value for ch in ":#{}[]&*?|>!%@`'\""):
        return json.dumps(value)
    return value


def stream_alias_for_camera(cam: Dict[str, Any]) -> str | None:
    ctype = (cam.get("cameraType") or cam.get("camera_type") or "").strip().lower()
    if ctype == "day":
        return "day"
    if ctype == "thermal":
        return "thermal"
    return None


def cameras_to_stream_map(local_cameras: list, connection_mode: str | None = None) -> Dict[str, str]:
    """Map enabled Day/Thermal cameras to go2rtc aliases. First of each type wins."""
    streams: Dict[str, str] = {}
    for cam in local_cameras:
        if not cam.get("enabled", True):
            continue
        if connection_mode and not _mode_ok(cam, connection_mode):
            continue
        alias = stream_alias_for_camera(cam)
        if not alias or alias in streams:
            continue
        url = (cam.get("rtspUrl") or cam.get("rtsp_url") or "").strip()
        if not url:
            continue
        streams[alias] = encode_rtsp_credentials(url)
    return streams


def _mode_ok(cam: Dict[str, Any], connection_mode: str) -> bool:
    from ..core.connection_mode import camera_matches_mode

    return camera_matches_mode(cam, connection_mode)


def render_config_text(local_cameras: list, connection_mode: str | None = None) -> str:
    """Build go2rtc.yaml from camera records. Host may be LAN IP or hostname."""
    streams = cameras_to_stream_map(local_cameras, connection_mode)
    lines = [
        "# Generated from Cameras page records. Do not commit live URLs.",
        "# Day/Thermal aliases stay fixed; the host inside each RTSP URL is configuration.",
        "",
        "api:",
        '  listen: ":1984"',
        '  origin: "*"',
        "",
        "rtsp:",
        '  listen: ":8554"',
        "",
        "webrtc:",
        '  listen: ":8555"',
        "  candidates:",
        "    - stun:stun.l.google.com:19302",
        "",
        "streams:",
    ]
    if not streams:
        lines.append("  {}")
    else:
        for name in ("day", "thermal"):
            if name in streams:
                lines.append(f"  {name}: {_yaml_scalar(streams[name])}")
    return "\n".join(lines) + "\n"


def apply_streams_for_mode(connection_mode: str) -> Dict[str, Any]:
    """Push the active-mode Day/Thermal RTSP sources into go2rtc. Never logs URLs."""
    from ..core.database import list_local_cameras
    from ..core.paths import go2rtc_config_path

    cameras = list_local_cameras(connection_mode=connection_mode)
    wanted = cameras_to_stream_map(cameras)
    yaml_text = render_config_text(cameras)
    dest = go2rtc_config_path()
    try:
        existing = dest.read_text(encoding="utf-8") if dest.exists() else ""
        if existing != yaml_text:
            dest.write_text(yaml_text, encoding="utf-8")
    except OSError as exc:
        logger.debug("Could not write go2rtc.yaml: %s", exc)

    live: Dict[str, Any] = {"updated": list(wanted.keys()), "removed": []}
    if not go2rtc_enabled():
        return live
    try:
        with httpx.Client(timeout=httpx.Timeout(3.0, connect=1.0)) as client:
            current = client.get(f"{GO2RTC_API_URL}/api/streams")
            names = set()
            if current.status_code == 200:
                body = current.json() or {}
                if isinstance(body, dict):
                    names = set(body.keys())
            for name, url in wanted.items():
                try:
                    client.put(
                        f"{GO2RTC_API_URL}/api/streams",
                        params={"name": name, "src": url},
                    )
                except Exception as exc:
                    logger.debug("go2rtc stream update failed for %s: %s", name, exc)
            for name in ("day", "thermal"):
                if name not in wanted and name in names:
                    try:
                        client.delete(f"{GO2RTC_API_URL}/api/streams", params={"src": name})
                        live["removed"].append(name)
                    except Exception as exc:
                        logger.debug("go2rtc stream delete failed for %s: %s", name, exc)
    except Exception as exc:
        logger.debug("go2rtc live apply skipped: %s", exc)
    return live
