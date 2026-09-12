"""Hardware self-test without requiring a live camera."""
from __future__ import annotations

from typing import Any, Dict, List

from ..auth.service import create_access_token
from ..hardware import gateway
from .shibli_client import controls_request, probe_controls_online


async def run_hardware_self_test(user: Dict[str, Any]) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    token = create_access_token(user)

    online, detail = await probe_controls_online()
    checks.append({
        "id": "controls_service",
        "label": "SHIBLI-controls service",
        "ok": online,
        "detail": detail if online else f"Offline — {detail}. Run ./scripts/start-controls.sh",
    })

    usr: Dict[str, Any] = {}
    if online:
        usr_res = await controls_request("GET", "/api/camera/usr/status", token)
        usr = usr_res.get("data") if isinstance(usr_res.get("data"), dict) else {}
        lrf_ok = bool(usr.get("lrf_connected") or usr.get("devices", {}).get("lrf", {}).get("connected"))
        illum_ok = bool(
            usr.get("illuminator_connected")
            or usr.get("devices", {}).get("illuminator", {}).get("connected")
        )
        checks.append({
            "id": "usr_lrf",
            "label": "USR LRF device",
            "ok": lrf_ok,
            "detail": "Connected" if lrf_ok else "Not connected (needs USR box 192.168.0.128 → PC:8234)",
        })
        checks.append({
            "id": "usr_illuminator",
            "label": "USR Illuminator device",
            "ok": illum_ok,
            "detail": "Connected" if illum_ok else "Not connected (needs USR box 192.168.0.7 → PC:8234)",
        })
        cams = await controls_request("GET", "/api/camera/cameras", token)
        cam_data = cams.get("data") or {}
        cam_list = cam_data.get("cameras") if isinstance(cam_data, dict) else cam_data
        if not isinstance(cam_list, list):
            cam_list = []
        connected = sum(1 for c in cam_list if c.get("connected"))
        checks.append({
            "id": "onvif_camera",
            "label": "ONVIF camera (PTZ)",
            "ok": connected > 0,
            "detail": f"{connected} connected / {len(cam_list)} registered"
            if cam_list
            else "No camera registered — Sync on Cameras page when camera is online",
        })
    else:
        checks.append({
            "id": "usr_lrf",
            "label": "USR LRF device",
            "ok": False,
            "detail": "Skipped — controls offline",
        })
        checks.append({
            "id": "usr_illuminator",
            "label": "USR Illuminator device",
            "ok": False,
            "detail": "Skipped — controls offline",
        })
        checks.append({
            "id": "onvif_camera",
            "label": "ONVIF camera (PTZ)",
            "ok": False,
            "detail": "Skipped — controls offline",
        })

    # Software path always testable (simulate / virtual PTZ + LRF)
    sim = bool(getattr(gateway, "simulate", False))
    if hasattr(gateway, "set_simulate") and not sim:
        # Temporary exercise without flipping persistent mode
        was = getattr(gateway, "simulate", False)
        gateway.set_simulate(True)
        ptz = gateway.start_ptz("left", "medium", "rel", "ptz-1", None)
        gateway.stop_ptz(None)
        lrf = gateway.measure_lrf("single", None)
        illum = gateway.set_illumination(None, enabled=True)
        gateway.set_illumination(None, enabled=False)
        gateway.set_simulate(was)
    else:
        ptz = gateway.start_ptz("left", "medium", "rel", "ptz-1", None)
        gateway.stop_ptz(None)
        lrf = gateway.measure_lrf("single", None)
        illum = gateway.set_illumination(None, enabled=True)
        gateway.set_illumination(None, enabled=False)

    checks.append({
        "id": "software_ptz",
        "label": "Software PTZ path (UI → C2)",
        "ok": bool(ptz.get("ok")),
        "detail": "Virtual PTZ OK — use Simulate mode without camera"
        if ptz.get("simulated") or ptz.get("fallback")
        else ("PTZ command OK" if ptz.get("ok") else str(ptz.get("error"))),
    })
    checks.append({
        "id": "software_lrf",
        "label": "Software LRF path",
        "ok": bool(lrf.get("ok")),
        "detail": f"Range {lrf.get('range_m')} m"
        + (" (simulated)" if lrf.get("simulated") else ""),
    })
    checks.append({
        "id": "software_illuminator",
        "label": "Software illuminator path",
        "ok": bool(illum.get("ok")),
        "detail": "State updated"
        + (" (simulated)" if illum.get("simulated") else ""),
    })

    passed = sum(1 for c in checks if c.get("ok"))
    return {
        "ok": True,
        "simulate_mode": bool(getattr(gateway, "simulate", False)),
        "controls_online": online,
        "passed": passed,
        "total": len(checks),
        "checks": checks,
        "usr": usr,
        "hint": (
            "Enable Simulate mode to exercise PTZ/LRF/Illuminator UI without camera. "
            "Connect USR boxes for real LRF/illuminator. Connect camera for real PTZ."
        ),
    }
