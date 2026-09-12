"""Lightweight camera connection test for Phase 1 hardware readiness."""
from __future__ import annotations

import socket
from typing import Any, Dict, Tuple
from urllib.parse import urlparse

import httpx


def _host_from_rtsp(rtsp_url: str) -> str:
    try:
        parsed = urlparse(rtsp_url)
        return parsed.hostname or ""
    except Exception:
        return ""


def _tcp_open(host: str, port: int, timeout: float = 3.0) -> bool:
    if not host or not port:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, TimeoutError, OSError):
        return False


def rtsp_target(rtsp_url: str, fallback_host: str) -> Tuple[str, int]:
    host = _host_from_rtsp(rtsp_url) or fallback_host
    port = 554
    try:
        parsed = urlparse(rtsp_url)
        if parsed.port:
            port = parsed.port
    except Exception:
        pass
    return host, port


async def test_camera_connection(payload: Dict[str, Any]) -> Dict[str, Any]:
    rtsp_url = (payload.get("rtsp_url") or payload.get("rtspUrl") or "").strip()
    ip = (payload.get("ip_address") or payload.get("ipAddress") or "").strip()
    if not rtsp_url:
        return {"ok": False, "message": "RTSP URL missing."}
    if not ip:
        ip = _host_from_rtsp(rtsp_url)
    if not ip:
        return {"ok": False, "message": "Host or IP address required (LAN IP or remote hostname)."}
    if not rtsp_url.lower().startswith("rtsp://"):
        return {"ok": False, "message": "RTSP URL missing or invalid (must start with rtsp://)."}

    onvif_port = int(payload.get("onvif_port") or payload.get("onvifPort") or 80)
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""

    rtsp_host, rtsp_port = rtsp_target(rtsp_url, ip)
    rtsp_ok = _tcp_open(rtsp_host, rtsp_port)
    if not rtsp_ok:
        return {
            "ok": False,
            "rtsp_ok": False,
            "onvif_ok": False,
            "message": "RTSP stream unavailable (port not reachable).",
        }

    onvif_ok = False
    if username:
        if _tcp_open(ip, onvif_port):
            try:
                async with httpx.AsyncClient(timeout=4.0) as client:
                    r = await client.get(
                        f"http://{ip}:{onvif_port}/onvif/device_service",
                        auth=(username, password),
                    )
                    if r.status_code == 401:
                        return {
                            "ok": False,
                            "rtsp_ok": True,
                            "onvif_ok": False,
                            "message": "Authentication failed.",
                        }
                    onvif_ok = r.status_code < 500
            except Exception:
                onvif_ok = False
    else:
        onvif_ok = _tcp_open(ip, onvif_port)

    if onvif_ok:
        return {
            "ok": True,
            "rtsp_ok": True,
            "onvif_ok": True,
            "message": "Camera connected successfully (reachability check passed).",
        }
    return {
        "ok": True,
        "rtsp_ok": True,
        "onvif_ok": False,
        "message": (
            "RTSP port reachable. ONVIF/control not confirmed — "
            "expected for some remote/NAT streams. Hardware control stays blocked until ONVIF answers."
        ),
    }
