"""HTTP client for SHIBLI-Core, SHIBLI-controls, and SHIBLI-VSS."""
from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, Optional

import httpx

CORE_URL = os.getenv("SHIBLI_CORE_URL", "http://127.0.0.1:3000").rstrip("/")
CONTROLS_URL = os.getenv("SHIBLI_CONTROLS_URL", "http://127.0.0.1:8001").rstrip("/")
VSS_URL = os.getenv("SHIBLI_VSS_URL", "http://127.0.0.1:8000").rstrip("/")
CORE_SERVICE_USER = os.getenv("SHIBLI_CORE_SERVICE_USER", "")
CORE_SERVICE_PASS = os.getenv("SHIBLI_CORE_SERVICE_PASSWORD", "")

_service_token: Optional[str] = None


async def _get_core_token() -> Optional[str]:
    global _service_token
    if _service_token:
        return _service_token
    if not CORE_SERVICE_USER or not CORE_SERVICE_PASS:
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(
                f"{CORE_URL}/api/auth/login",
                json={"username": CORE_SERVICE_USER, "password": CORE_SERVICE_PASS},
            )
            if r.status_code == 200:
                _service_token = r.json().get("accessToken")
                return _service_token
    except Exception:
        pass
    return None


async def core_request(
    method: str,
    path: str,
    token: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    auth = token or await _get_core_token()
    headers = kwargs.pop("headers", {})
    if auth:
        headers["Authorization"] = f"Bearer {auth}"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.request(method, f"{CORE_URL}{path}", headers=headers, **kwargs)
            if r.status_code == 401 and token and CORE_SERVICE_USER:
                service = await _get_core_token()
                if service and service != token:
                    headers["Authorization"] = f"Bearer {service}"
                    r = await client.request(method, f"{CORE_URL}{path}", headers=headers, **kwargs)
            return {"ok": r.is_success, "status": r.status_code, "data": _safe_json(r)}
    except httpx.ConnectError:
        return {"ok": False, "status": 503, "error": "SHIBLI-Core unreachable", "data": None}
    except httpx.TimeoutException:
        return {"ok": False, "status": 504, "error": "SHIBLI-Core timeout", "data": None}


async def controls_request(
    method: str,
    path: str,
    token: str,
    **kwargs: Any,
) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}", **kwargs.pop("headers", {})}
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.request(method, f"{CONTROLS_URL}{path}", headers=headers, **kwargs)
            return {"ok": r.is_success, "status": r.status_code, "data": _safe_json(r)}
    except httpx.ConnectError:
        return {"ok": False, "status": 503, "error": "SHIBLI-controls unreachable", "data": None}
    except httpx.TimeoutException:
        return {"ok": False, "status": 504, "error": "SHIBLI-controls timeout", "data": None}


async def vss_request(method: str, path: str, token: str, **kwargs: Any) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}", **kwargs.pop("headers", {})}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.request(method, f"{VSS_URL}{path}", headers=headers, **kwargs)
            return {"ok": r.is_success, "status": r.status_code, "data": _safe_json(r)}
    except httpx.ConnectError:
        return {"ok": False, "status": 503, "error": "SHIBLI-VSS unreachable", "data": None}


async def probe_controls_online() -> tuple[bool, str]:
    """Return whether SHIBLI-controls health endpoint responds."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{CONTROLS_URL}/health")
            if r.status_code == 200:
                return True, CONTROLS_URL
            return False, f"{CONTROLS_URL} returned HTTP {r.status_code}"
    except httpx.ConnectError:
        return False, f"cannot connect to {CONTROLS_URL}"
    except httpx.TimeoutException:
        return False, f"timeout connecting to {CONTROLS_URL}"
    except Exception as exc:
        return False, str(exc)


async def backend_status() -> Dict[str, Any]:
    """Probe Core / Controls / VSS in parallel with short timeouts (offline-friendly)."""
    async def _one(name: str, url: str) -> tuple[str, Dict[str, Any]]:
        path = "/health" if name == "controls" else "/api/health"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(0.6, connect=0.4)) as client:
                r = await client.get(f"{url}{path}")
                return name, {"online": r.status_code == 200, "url": url}
        except Exception:
            return name, {"online": False, "url": url}

    pairs = await asyncio.gather(
        _one("core", CORE_URL),
        _one("controls", CONTROLS_URL),
        _one("vss", VSS_URL),
    )
    return {name: info for name, info in pairs}

def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return {"raw": response.text}
