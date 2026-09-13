from __future__ import annotations

import logging
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict
from urllib.parse import quote

import httpx

from .base import DeviceAdapter

logger = logging.getLogger(__name__)

PTZ_ROUTES = {
    "up": "pan-top",
    "down": "pan-bottom",
    "left": "pan-left",
    "right": "pan-right",
    "up_left": "pan-up-left",
    "up_right": "pan-up-right",
    "down_left": "pan-down-left",
    "down_right": "pan-down-right",
    "home": "home",
    "stop": "stop",
}

PTZ_START_ROUTES = {
    "up": "start-pan-top",
    "down": "start-pan-bottom",
    "left": "start-pan-left",
    "right": "start-pan-right",
    "up_left": "start-pan-up-left",
    "up_right": "start-pan-up-right",
    "down_left": "start-pan-down-left",
    "down_right": "start-pan-down-right",
    "zoom_in": "start-zoom-in",
    "zoom_out": "start-zoom-out",
}

LENS_ROUTES = {
    "zoom_in": "zoom-in",
    "zoom_out": "zoom-out",
    "focus_plus": "focus/far",
    "focus_minus": "focus/near",
}

SPEED_PCT = {"low": 20, "medium": 50, "high": 80}
INTENSITY_PCT = {"low": 25, "med": 50, "high": 100}
BEAM_FOV = {"narrow": 20, "medium": 45, "wide": 90}

ADMIN_PERMISSIONS = [
    "register-user",
    "get-users",
    "get-roles",
    "add-stream",
    "get-streams",
    "control-camera",
    "edit-user",
    "delete-user",
    "manage-recordings",
]


@dataclass
class HardwareState:
    ptz_speed: str = "medium"
    ptz_mode: str = "abs"
    active_ptz: str = "ptz-1"
    active_camera_id: str = ""
    lrf_mode: str = "single"
    lrf_continuous: bool = False
    lrf_range_m: int = 0
    illumination_enabled: bool = False
    illumination_source: str = "ir"
    illumination_intensity: str = "med"
    illumination_beam: str = "narrow"
    illumination_brightness: int = 50
    illumination_fov: int = 45
    motor_speed_pct: int = 50
    day_auto_focus: bool = False
    thermal_auto_focus: bool = False
    thermal_polarity: str = "white_hot"
    thermal_brightness: int = 50
    thermal_contrast: int = 50
    active_lrf_id: str = ""
    wiper: bool = False
    heater: bool = False
    nuc_active: bool = False
    agc_active: bool = False
    last_command: str = "boot"
    cursor_x: int = 1280
    cursor_y: int = 720
    azimuth: float = 34.2
    elevation: float = -2.1
    zoom: float = 1.0
    auto_pan: bool = False
    custom_buttons: Dict[str, str] = field(default_factory=lambda: {
        "button_1": "unassigned",
        "button_2": "unassigned",
        "button_3": "unassigned",
        "button_4": "unassigned",
    })


class ShibliControlsAdapter(DeviceAdapter):
    name = "shibli_controls"

    def __init__(self, controls_url: str, jwt_secret: str, api_token: str = "") -> None:
        self.controls_url = controls_url.rstrip("/")
        self.jwt_secret = jwt_secret
        self.api_token = api_token or self._dev_token()
        self.state = HardwareState()
        self._connected = False
        self._last_probe = 0.0
        self._warmed_cameras: set[str] = set()
        self._http: httpx.Client | None = None
        self.simulate = os.getenv("SHIBLI_HW_SIMULATE", "0").strip().lower() in ("1", "true", "yes", "on")

    def set_simulate(self, enabled: bool) -> None:
        self.simulate = bool(enabled)

    def _allow_sim_fallback(self) -> bool:
        return os.getenv("SHIBLI_HW_SIMULATE_FALLBACK", "0").strip().lower() in ("1", "true", "yes", "on")

    def _speed_step(self) -> float:
        return {"low": 0.5, "medium": 1.5, "high": 3.0}.get(self.state.ptz_speed, 1.5)

    def _apply_virtual_ptz(self, direction: str) -> None:
        step = self._speed_step()
        if direction in ("left", "up_left", "down_left"):
            self.state.azimuth = (self.state.azimuth - step) % 360
        if direction in ("right", "up_right", "down_right"):
            self.state.azimuth = (self.state.azimuth + step) % 360
        if direction in ("up", "up_left", "up_right"):
            self.state.elevation = min(90.0, self.state.elevation + step)
        if direction in ("down", "down_left", "down_right"):
            self.state.elevation = max(-90.0, self.state.elevation - step)
        if direction == "home":
            self.state.azimuth = 0.0
            self.state.elevation = 0.0
            self.state.zoom = 1.0
        if direction == "zoom_in":
            self.state.zoom = min(20.0, self.state.zoom + 0.1)
        if direction == "zoom_out":
            self.state.zoom = max(1.0, self.state.zoom - 0.1)

    def _sim_ok(self, command: str, **extra: Any) -> Dict[str, Any]:
        return {"ok": True, "simulated": True, "command": command, **extra}

    def _client(self, timeout_s: float = 3.0) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(
                base_url=self.controls_url,
                timeout=httpx.Timeout(2.0, connect=0.5),
                headers=self._headers(),
            )
        return self._http

    def warm_camera(self, camera_id: str | None = None) -> Dict[str, Any]:
        cam = self._camera_param(camera_id)
        if cam and cam in self._warmed_cameras:
            return {"ok": True, "camera_id": cam, "cached": True}
        ok, err = self._connect_camera(camera_id)
        if ok and cam:
            self._warmed_cameras.add(cam)
        return {"ok": ok, "error": err, "camera_id": cam}

    def probe_online(self, max_age_s: float = 5.0) -> bool:
        now = time.time()
        if now - self._last_probe < max_age_s and self._last_probe > 0:
            return self._connected
        self._last_probe = now
        if not self.controls_url:
            self._connected = False
            return False
        try:
            with httpx.Client(timeout=2.0) as client:
                response = client.get(f"{self.controls_url}/health")
                self._connected = response.status_code == 200
        except Exception:
            self._connected = False
        return self._connected

    def _dev_token(self) -> str:
        if not self.controls_url:
            return ""
        try:
            import jwt

            return jwt.encode(
                {
                    "username": "shibli-local",
                    "roleName": "ADMINISTRATOR",
                    "permissions": ADMIN_PERMISSIONS,
                },
                self.jwt_secret,
                algorithm="HS256",
            )
        except Exception as exc:
            logger.warning("JWT generation failed: %s", exc)
            return ""

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def set_active_camera(self, camera_id: str | None) -> None:
        if camera_id:
            self.state.active_camera_id = camera_id

    def _invalidate_camera(self, camera_id: str | None = None) -> None:
        cam = self._camera_param(camera_id)
        if cam:
            self._warmed_cameras.discard(cam)

    def _camera_param(self, camera_id: str | None = None) -> str | None:
        return camera_id or self.state.active_camera_id or None

    def _post(self, path: str, camera_id: str | None = None, json_body: Dict[str, Any] | None = None) -> tuple[bool, str | None]:
        if not self.controls_url or not self.api_token:
            return False, "Hardware controls not configured"
        cam = self._camera_param(camera_id)
        params = {"camera_id": cam} if cam else {}
        try:
            response = self._client().post(
                f"/api/camera/{path}",
                params=params,
                json=json_body,
            )
            response.raise_for_status()
            data = response.json() if response.content else {}
            if isinstance(data, dict) and data.get("success") is False:
                self._invalidate_camera(camera_id)
                return False, str(data.get("error") or "Command rejected by controls")
            return True, None
        except Exception as exc:
            self._invalidate_camera(camera_id)
            logger.warning("controls POST %s failed: %s", path, exc)
            return False, str(exc)

    def _connect_camera(self, camera_id: str | None = None) -> tuple[bool, str | None]:
        cam = self._camera_param(camera_id)
        if not cam or not self.controls_url or not self.api_token:
            return False, "No camera selected"
        encoded = quote(cam, safe="")
        try:
            response = httpx.post(
                f"{self.controls_url}/api/camera/cameras/{encoded}/connect",
                headers=self._headers(),
                timeout=httpx.Timeout(8.0, connect=1.5),
            )
            response.raise_for_status()
            data = response.json() if response.content else {}
            if isinstance(data, dict) and data.get("connected") is False:
                return False, str(data.get("error") or "Camera not reachable via ONVIF")
            return True, None
        except Exception as exc:
            logger.warning("controls connect %s failed: %s", cam, exc)
            return False, str(exc)

    def _get(self, path: str, camera_id: str | None = None) -> Dict[str, Any] | None:
        if not self.controls_url or not self.api_token:
            return None
        cam = self._camera_param(camera_id)
        params = {"camera_id": cam} if cam else {}
        try:
            response = self._client().get(
                f"/api/camera/{path}",
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.debug("controls GET %s failed: %s", path, exc)
            return None

    def _lrf_id(self, camera_id: str | None = None) -> str | None:
        cam = self._camera_param(camera_id)
        if not cam:
            return self.state.active_lrf_id or None
        if cam.endswith("-lrf"):
            return cam
        return f"{cam}-lrf"

    def apply_motor_speed(self, speed: str | int, camera_id: str | None = None) -> Dict[str, Any]:
        if isinstance(speed, str):
            self.state.ptz_speed = speed
            pct = SPEED_PCT.get(speed, 50)
        else:
            pct = max(1, min(100, int(speed)))
        self.state.motor_speed_pct = pct
        self.state.last_command = f"ptz:speed:{pct}"
        if self.simulate:
            return self._sim_ok(self.state.last_command, speed=pct)
        ok, err = self._post("motor-speed", camera_id=camera_id, json_body={"speed": pct})
        return {"ok": ok, "error": err, "speed": pct, "command": self.state.last_command}

    def set_focus_mode(self, auto: bool, camera_id: str | None = None, channel: str = "day") -> Dict[str, Any]:
        want = (channel or "day").strip().lower()
        self.state.last_command = f"focus:mode:{want}:{'on' if auto else 'off'}"
        if want == "thermal":
            self.state.thermal_auto_focus = auto
        else:
            self.state.day_auto_focus = auto
        if self.simulate:
            return self._sim_ok(self.state.last_command, auto=auto, channel=want)
        cam = self._camera_param(camera_id)
        body = {"auto": bool(auto)}
        if want == "thermal" and cam:
            body["camera_id"] = cam
        ok, err = self._post("focus/mode", camera_id=camera_id, json_body=body)
        if not ok:
            warm = self.warm_camera(camera_id)
            if warm.get("ok"):
                ok, err = self._post("focus/mode", camera_id=camera_id, json_body=body)
        if not ok:
            if self._allow_sim_fallback():
                return self._sim_ok(self.state.last_command, fallback=True, reason=err, auto=auto, channel=want)
            return {"ok": False, "error": err or "Focus mode failed", "auto": auto, "channel": want, "command": self.state.last_command}
        return {"ok": True, "auto": auto, "channel": want, "command": self.state.last_command}

    def start_focus(self, direction: str, camera_id: str | None = None) -> Dict[str, Any]:
        route = "focus/near" if direction in ("near", "focus_minus") else "focus/far"
        self.state.last_command = f"focus:start:{direction}"
        if self.simulate:
            return self._sim_ok(self.state.last_command)
        self.apply_motor_speed(self.state.ptz_speed, camera_id)
        ok, err = self._post(route, camera_id=camera_id)
        if not ok:
            warm = self.warm_camera(camera_id)
            if warm.get("ok"):
                ok, err = self._post(route, camera_id=camera_id)
        if not ok and self._allow_sim_fallback():
            return self._sim_ok(self.state.last_command, fallback=True, reason=err)
        return {"ok": ok, "error": err, "command": self.state.last_command}

    def stop_focus(self, camera_id: str | None = None) -> Dict[str, Any]:
        self.state.last_command = "focus:stop"
        if self.simulate:
            return self._sim_ok(self.state.last_command)
        ok, err = self._post("focus/stop", camera_id=camera_id)
        return {"ok": ok, "error": err, "command": self.state.last_command}

    def set_thermal_image(self, camera_id: str | None = None, **kwargs: Any) -> Dict[str, Any]:
        cam = self._camera_param(camera_id)
        if "polarity" in kwargs and kwargs["polarity"] is not None:
            polarity = kwargs["polarity"]
            self.state.thermal_polarity = polarity
            self.state.last_command = f"thermal:polarity:{polarity}"
            if self.simulate:
                return self._sim_ok(self.state.last_command, polarity=polarity)
            ok, err = self._post("polarity", camera_id=cam, json_body={"polarity": polarity})
            return {"ok": ok, "error": err, "polarity": polarity, "command": self.state.last_command}
        if "brightness" in kwargs and kwargs["brightness"] is not None:
            value = int(kwargs["brightness"])
            self.state.thermal_brightness = value
            self.state.last_command = f"thermal:brightness:{value}"
            if self.simulate:
                return self._sim_ok(self.state.last_command, brightness=value)
            ok, err = self._post("brightness", camera_id=cam, json_body={"brightness": value})
            return {"ok": ok, "error": err, "brightness": value, "command": self.state.last_command}
        if "contrast" in kwargs and kwargs["contrast"] is not None:
            value = int(kwargs["contrast"])
            self.state.thermal_contrast = value
            self.state.last_command = f"thermal:contrast:{value}"
            if self.simulate:
                return self._sim_ok(self.state.last_command, contrast=value)
            ok, err = self._post("contrast", camera_id=cam, json_body={"contrast": value})
            return {"ok": ok, "error": err, "contrast": value, "command": self.state.last_command}
        return {"ok": False, "error": "No thermal image field set"}

    def bump_illumination(self, kind: str, camera_id: str | None = None) -> Dict[str, Any]:
        cam = self._camera_param(camera_id)
        routes = {
            "brightness_up": "illuminator/brightness/increase",
            "brightness_down": "illuminator/brightness/decrease",
            "fov_up": "illuminator/fov/increase",
            "fov_down": "illuminator/fov/decrease",
        }
        route = routes.get(kind)
        if not route:
            return {"ok": False, "error": f"Unsupported illuminator bump: {kind}"}
        self.state.last_command = f"illumination:{kind}"
        if self.simulate:
            if kind.startswith("fov"):
                delta = 5 if kind.endswith("up") else -5
                self.state.illumination_fov = max(5, min(90, self.state.illumination_fov + delta))
            else:
                delta = 5 if kind.endswith("up") else -5
                self.state.illumination_brightness = max(0, min(100, self.state.illumination_brightness + delta))
            return {
                "ok": True,
                "simulated": True,
                "brightness": self.state.illumination_brightness,
                "fov": self.state.illumination_fov,
                "illumination": self.snapshot()["illumination"],
            }
        ok, err = self._post(route, camera_id=cam)
        if kind.startswith("fov"):
            data = self._get("illuminator/fov", camera_id=cam)
            if data and data.get("fov") is not None:
                self.state.illumination_fov = int(data["fov"])
        else:
            data = self._get("illuminator/brightness", camera_id=cam)
            if data and data.get("brightness") is not None:
                self.state.illumination_brightness = int(data["brightness"])
        return {
            "ok": ok,
            "error": err,
            "brightness": self.state.illumination_brightness,
            "fov": self.state.illumination_fov,
            "illumination": self.snapshot()["illumination"],
        }

    def register_lrf(self, lrf_ip: str, lrf_port: int = 8234, username: str = "admin", password: str = "admin", camera_id: str | None = None) -> Dict[str, Any]:
        lrf_id = self._lrf_id(camera_id) or f"{lrf_ip}:{lrf_port}"
        self.state.active_lrf_id = lrf_id
        self.state.last_command = f"lrf:register:{lrf_id}"
        if self.simulate:
            return {"ok": True, "simulated": True, "camera_id": lrf_id}
        if not self.controls_url or not self.api_token:
            return {"ok": False, "error": "Hardware controls not configured"}
        try:
            with httpx.Client(timeout=6.0) as client:
                response = client.post(
                    f"{self.controls_url}/api/camera/lrf/register",
                    headers={**self._headers(), "Content-Type": "application/json"},
                    json={
                        "lrf_ip": lrf_ip,
                        "lrf_port": lrf_port,
                        "username": username,
                        "password": password,
                        "camera_id": lrf_id,
                    },
                )
                response.raise_for_status()
                data = response.json() if response.content else {}
                if isinstance(data, dict) and data.get("success") is False:
                    return {"ok": False, "error": data.get("error") or "LRF register failed", "camera_id": lrf_id}
                return {"ok": True, "camera_id": lrf_id}
        except Exception as exc:
            logger.warning("LRF register failed: %s", exc)
            return {"ok": False, "error": str(exc), "camera_id": lrf_id}

    def start_ptz(self, direction: str, speed: str, mode: str, ptz_id: str | None = None, camera_id: str | None = None) -> Dict[str, Any]:
        self.state.ptz_speed = speed
        self.state.ptz_mode = mode
        if ptz_id:
            self.state.active_ptz = ptz_id
        if camera_id:
            self.state.active_camera_id = camera_id
        if not self.simulate:
            self.apply_motor_speed(speed, camera_id)
        self.state.last_command = f"ptz:start:{direction}"
        if self.simulate:
            self._apply_virtual_ptz(direction)
            return self._sim_ok(self.state.last_command, telemetry=self.snapshot()["telemetry"])
        route = PTZ_START_ROUTES.get(direction)
        if not route:
            return {"ok": False, "error": f"Unsupported PTZ direction: {direction}"}
        ok, err = self._post(route, camera_id=camera_id)
        if not ok:
            warm = self.warm_camera(camera_id)
            if warm.get("ok"):
                ok, err = self._post(route, camera_id=camera_id)
            elif self._allow_sim_fallback():
                # Opt-in only: SHIBLI_HW_SIMULATE_FALLBACK=1
                self._apply_virtual_ptz(direction)
                return self._sim_ok(
                    self.state.last_command,
                    fallback=True,
                    reason=warm.get("error") or err or "camera offline",
                    telemetry=self.snapshot()["telemetry"],
                )
        return {"ok": ok, "error": err, "command": self.state.last_command}

    def stop_ptz(self, camera_id: str | None = None) -> Dict[str, Any]:
        self.state.last_command = "ptz:stop"
        if self.simulate:
            return self._sim_ok(self.state.last_command)
        ok, err = self._post("stop", camera_id=camera_id)
        if not ok:
            if self._allow_sim_fallback():
                return self._sim_ok(self.state.last_command, fallback=True, reason=err)
            return {"ok": False, "error": err or "PTZ stop failed", "command": self.state.last_command}
        return {"ok": ok, "error": err, "command": self.state.last_command}

    def move_ptz(self, direction: str, speed: str, mode: str, ptz_id: str | None = None, camera_id: str | None = None) -> Dict[str, Any]:
        self.state.ptz_speed = speed
        self.state.ptz_mode = mode
        if ptz_id:
            self.state.active_ptz = ptz_id
        if camera_id:
            self.state.active_camera_id = camera_id
        self.state.last_command = f"ptz:{direction}"
        if self.simulate:
            self._apply_virtual_ptz(direction)
            return self._sim_ok(self.state.last_command, telemetry=self.snapshot()["telemetry"])
        if direction in ("stop", "home"):
            route = PTZ_ROUTES.get(direction)
            if not route:
                return {"ok": False, "error": f"Unsupported PTZ command: {direction}"}
            ok, err = self._post(route, camera_id=camera_id)
            if not ok:
                warm = self.warm_camera(camera_id)
                if warm.get("ok"):
                    ok, err = self._post(route, camera_id=camera_id)
                elif self._allow_sim_fallback():
                    self._apply_virtual_ptz(direction)
                    return self._sim_ok(
                        self.state.last_command,
                        fallback=True,
                        reason=warm.get("error") or err,
                        telemetry=self.snapshot()["telemetry"],
                    )
            return {"ok": ok, "error": err, "command": self.state.last_command}
        return self.start_ptz(direction, speed, mode, ptz_id, camera_id)

    def set_auto_pan(self, enabled: bool, camera_id: str | None = None, speed: str = "medium") -> Dict[str, Any]:
        self.state.ptz_speed = speed
        self.state.last_command = "ptz:auto_pan:on" if enabled else "ptz:auto_pan:off"
        if self.simulate:
            self.state.auto_pan = enabled
            return {"ok": True, "auto_pan": enabled, "command": self.state.last_command, "simulated": True}
        ok, err = self._post("autopan/start" if enabled else "autopan/stop", camera_id=camera_id)
        if not ok:
            if self._allow_sim_fallback():
                self.state.auto_pan = enabled
                return self._sim_ok(self.state.last_command, fallback=True, reason=err, auto_pan=enabled)
            return {"ok": False, "error": err or "Auto-pan command failed", "command": self.state.last_command}
        self.state.auto_pan = enabled
        return {"ok": True, "auto_pan": enabled, "command": self.state.last_command}

    def lens(self, action: str, ptz_id: str | None = None, camera_id: str | None = None) -> Dict[str, Any]:
        self.state.last_command = f"lens:{action}"
        if self.simulate:
            self._apply_virtual_ptz(action)
            return self._sim_ok(self.state.last_command, telemetry=self.snapshot()["telemetry"])
        route = LENS_ROUTES.get(action)
        if action == "focus_auto":
            ok, err = self._post("focus/auto", camera_id=camera_id)
            if not ok:
                if self._allow_sim_fallback():
                    return self._sim_ok(self.state.last_command, fallback=True, reason=err)
                return {"ok": False, "error": err or "Focus auto failed", "command": self.state.last_command}
            return {"ok": True, "command": self.state.last_command}
        elif route:
            ok, err = self._post(route, camera_id=camera_id)
            if not ok:
                if self._allow_sim_fallback():
                    self._apply_virtual_ptz(action)
                    return self._sim_ok(self.state.last_command, fallback=True, reason=err)
                return {"ok": False, "error": err or f"Lens {action} failed", "command": self.state.last_command}
            return {"ok": ok, "error": err, "command": self.state.last_command}
        start_route = PTZ_START_ROUTES.get(action)
        if start_route:
            ok, err = self._post(start_route, camera_id=camera_id)
            if not ok:
                warm = self.warm_camera(camera_id)
                if warm.get("ok"):
                    ok, err = self._post(start_route, camera_id=camera_id)
                elif self._allow_sim_fallback():
                    self._apply_virtual_ptz(action)
                    return self._sim_ok(self.state.last_command, fallback=True, reason=err)
            return {"ok": ok, "error": err, "command": self.state.last_command}
        return {"ok": False, "error": f"Unsupported lens action: {action}", "command": self.state.last_command}

    def focus_auto(self, camera_id: str | None = None, channel: str = "day") -> Dict[str, Any]:
        self.state.last_command = f"focus:auto:{channel}"
        if self.simulate:
            return self._sim_ok(self.state.last_command)
        want = (channel or "day").strip().lower()
        if want == "thermal":
            cam = self._camera_param(camera_id)
            if not cam:
                return {"ok": False, "error": "No thermal camera selected", "command": self.state.last_command}
            return self.set_focus_mode(True, cam, channel="thermal")
        ok, err = self._post("focus/auto", camera_id=camera_id)
        if not ok:
            if self._allow_sim_fallback():
                return self._sim_ok(self.state.last_command, fallback=True, reason=err)
            return {"ok": False, "error": err or "Focus auto failed", "command": self.state.last_command}
        return {"ok": True, "command": self.state.last_command}

    def preset(self, action: str, preset: str, ptz_id: str | None = None, camera_id: str | None = None) -> Dict[str, Any]:
        self.state.last_command = f"preset:{action}:{preset}"
        if self.simulate:
            return self._sim_ok(self.state.last_command)
        routes = {
            "set": f"preset/set/{preset}",
            "go": f"preset/go/{preset}",
            "delete": f"preset/delete/{preset}",
        }
        route = routes.get(action)
        if not route:
            return {"ok": False, "error": f"Unsupported preset action: {action}", "command": self.state.last_command}
        ok, err = self._post(route, camera_id=camera_id)
        if not ok:
            if self._allow_sim_fallback():
                return self._sim_ok(self.state.last_command, fallback=True, reason=err)
            return {"ok": False, "error": err or f"Preset {action} failed", "command": self.state.last_command}
        return {"ok": True, "command": self.state.last_command}

    def fetch_ptz_status(self, camera_id: str | None = None) -> Dict[str, Any]:
        data = self._get("status", camera_id=camera_id)
        if data:
            pos = data.get("position") or {}
            az = data.get("azimuth") or data.get("az") or pos.get("pan")
            el = data.get("elevation") or data.get("el") or pos.get("tilt")
            zm = data.get("zoom") or data.get("absoluteZoom") or pos.get("zoom")
            if az is not None:
                self.state.azimuth = float(az)
            if el is not None:
                self.state.elevation = float(el)
            if zm is not None:
                try:
                    self.state.zoom = float(zm)
                except (TypeError, ValueError):
                    pass
        return {
            "ok": bool(data and data.get("success", True)),
            "azimuth": round(self.state.azimuth, 2),
            "elevation": round(self.state.elevation, 2),
            "zoom": round(self.state.zoom, 3),
            "connected": bool(data and data.get("success")),
            "error": (data or {}).get("error"),
        }

    def lrf_continuous_start(self, camera_id: str | None = None) -> Dict[str, Any]:
        lrf_id = self._lrf_id(camera_id)
        self.state.active_lrf_id = lrf_id or ""
        self.state.lrf_mode = "continuous"
        self.state.last_command = "lrf:continuous:start"
        if self.simulate:
            self.state.lrf_continuous = True
            return {"ok": True, "mode": "continuous", "simulated": True}
        ok, err = self._post("lrf/continuous/start", camera_id=lrf_id)
        if not ok:
            if self._allow_sim_fallback():
                self.state.lrf_continuous = True
                return self._sim_ok(self.state.last_command, fallback=True, reason=err, mode="continuous")
            return {"ok": False, "error": err or "LRF continuous start failed", "mode": "continuous"}
        self.state.lrf_continuous = True
        return {"ok": True, "mode": "continuous"}

    def lrf_continuous_stop(self) -> Dict[str, Any]:
        self.state.last_command = "lrf:continuous:stop"
        if self.simulate:
            self.state.lrf_continuous = False
            self.state.lrf_mode = "single"
            return {"ok": True, "mode": "single", "simulated": True}
        ok, err = self._post("lrf/continuous/stop", camera_id=self.state.active_lrf_id or self._lrf_id())
        if not ok:
            if self._allow_sim_fallback():
                self.state.lrf_continuous = False
                self.state.lrf_mode = "single"
                return self._sim_ok(self.state.last_command, fallback=True, reason=err, mode="single")
            return {"ok": False, "error": err or "LRF continuous stop failed", "mode": "single"}
        self.state.lrf_continuous = False
        self.state.lrf_mode = "single"
        return {"ok": True, "mode": "single"}

    def poll_lrf_distance(self, camera_id: str | None = None) -> Dict[str, Any]:
        if not self.state.lrf_continuous:
            return self._lrf_result()
        data = self._get("lrf/distance", camera_id=self._lrf_id(camera_id) or self.state.active_lrf_id)
        if data:
            dist = data.get("distance") or data.get("range_m")
            if dist is not None:
                self.state.lrf_range_m = int(float(dist))
            cursor = data.get("cursor") or {}
            if cursor.get("x") is not None:
                self.state.cursor_x = int(cursor["x"])
            if cursor.get("y") is not None:
                self.state.cursor_y = int(cursor["y"])
        return self._lrf_result()

    def measure_lrf(self, mode: str, camera_id: str | None = None) -> Dict[str, Any]:
        lrf_id = self._lrf_id(camera_id)
        self.state.active_lrf_id = lrf_id or ""
        self.state.lrf_mode = mode
        self.state.last_command = f"lrf:{mode}"
        if self.simulate:
            self.state.lrf_range_m = random.randint(850, 2400)
            self.state.cursor_x = random.randint(900, 1500)
            self.state.cursor_y = random.randint(450, 850)
            return {**self._lrf_result(), "simulated": True}
        if mode == "continuous" or mode in ("scan", "cont"):
            return self.lrf_continuous_start(camera_id)
        if not self.controls_url or not self.api_token:
            return {"ok": False, "error": "Hardware controls not configured", "range_m": None, "cursor": {"x": self.state.cursor_x, "y": self.state.cursor_y}}
        try:
            params = {"camera_id": lrf_id} if lrf_id else {}
            with httpx.Client(timeout=4.0) as client:
                response = client.post(
                    f"{self.controls_url}/api/camera/lrf/single-range",
                    headers=self._headers(),
                    params=params,
                )
                response.raise_for_status()
                data = response.json()
                if isinstance(data, dict) and data.get("success") is False:
                    return {"ok": False, "error": data.get("error") or "LRF measurement failed", "range_m": None, "cursor": {"x": self.state.cursor_x, "y": self.state.cursor_y}}
                distance = data.get("distance") or data.get("range_m")
                if distance is None:
                    return {"ok": False, "error": "No distance returned", "range_m": None, "cursor": {"x": self.state.cursor_x, "y": self.state.cursor_y}}
                self.state.lrf_range_m = int(float(distance))
                return self._lrf_result()
        except Exception as exc:
            logger.warning("LRF hardware call failed: %s", exc)
            if self._allow_sim_fallback():
                return {**self._lrf_result(), "ok": False, "simulated": True, "fallback": True, "error": str(exc), "range_m": None}
            return {"ok": False, "error": str(exc) or "LRF measurement failed", "range_m": None, "cursor": {"x": self.state.cursor_x, "y": self.state.cursor_y}}

    def _lrf_result(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "range_m": self.state.lrf_range_m,
            "cursor": {"x": self.state.cursor_x, "y": self.state.cursor_y},
        }

    def set_illumination(self, camera_id: str | None = None, **kwargs: Any) -> Dict[str, Any]:
        for key, value in kwargs.items():
            if value is not None and hasattr(self.state, f"illumination_{key}"):
                setattr(self.state, f"illumination_{key}", value)
        self.state.last_command = "illumination:update"
        if self.simulate:
            if kwargs.get("intensity"):
                self.state.illumination_brightness = INTENSITY_PCT.get(str(kwargs["intensity"]), 50)
            if kwargs.get("beam"):
                self.state.illumination_fov = BEAM_FOV.get(str(kwargs["beam"]), 45)
            return {"ok": True, "simulated": True, "illumination": self.snapshot()["illumination"]}
        cam = self._camera_param(camera_id)
        errors: list[str] = []
        if "enabled" in kwargs:
            ok, err = self._post("illuminator", camera_id=cam, json_body={"enabled": bool(kwargs["enabled"])})
            if not ok and err:
                errors.append(str(err))
        if kwargs.get("intensity"):
            pct = INTENSITY_PCT.get(str(kwargs["intensity"]), 50)
            self.state.illumination_brightness = pct
            ok, err = self._post("illuminator/brightness", camera_id=cam, json_body={"brightness": pct})
            if not ok and err:
                errors.append(str(err))
        if kwargs.get("brightness") is not None:
            pct = max(0, min(100, int(kwargs["brightness"])))
            self.state.illumination_brightness = pct
            ok, err = self._post("illuminator/brightness", camera_id=cam, json_body={"brightness": pct})
            if not ok and err:
                errors.append(str(err))
        if kwargs.get("beam"):
            fov = BEAM_FOV.get(str(kwargs["beam"]), 45)
            self.state.illumination_fov = fov
            ok, err = self._post("illuminator/fov", camera_id=cam, json_body={"fov": fov})
            if not ok and err:
                errors.append(str(err))
        if kwargs.get("fov") is not None:
            fov = max(5, min(90, int(kwargs["fov"])))
            self.state.illumination_fov = fov
            ok, err = self._post("illuminator/fov", camera_id=cam, json_body={"fov": fov})
            if not ok and err:
                errors.append(str(err))
        if kwargs.get("fov_action") == "reset":
            ok, err = self._post("illuminator/reset", camera_id=cam)
            if ok:
                data = self._get("illuminator/fov", camera_id=cam)
                if data and data.get("fov") is not None:
                    self.state.illumination_fov = int(data["fov"])
            elif err:
                errors.append(str(err))
        if errors and self._allow_sim_fallback():
            return {"ok": True, "simulated": True, "fallback": True, "error": "; ".join(errors), "illumination": self.snapshot()["illumination"]}
        return {
            "ok": not errors,
            "error": "; ".join(errors) if errors else None,
            "illumination": self.snapshot()["illumination"],
        }

    def quick_action(self, group: str, action: str) -> Dict[str, Any]:
        self.state.last_command = f"quick:{group}:{action}"
        if group == "auxiliary":
            if action == "wiper":
                new_val = not self.state.wiper
                if self.simulate:
                    self.state.wiper = new_val
                    return self._sim_ok(self.state.last_command)
                ok, err = self._post("wiper", json_body={"enabled": new_val})
                if not ok:
                    if self._allow_sim_fallback():
                        self.state.wiper = new_val
                        return self._sim_ok(self.state.last_command, fallback=True, reason=err)
                    return {"ok": False, "error": err or "wiper command failed", "command": self.state.last_command}
                self.state.wiper = new_val
            elif action == "heater":
                new_val = not self.state.heater
                if self.simulate:
                    self.state.heater = new_val
                    return self._sim_ok(self.state.last_command)
                ok, err = self._post("heater", json_body={"enabled": new_val})
                if not ok:
                    if self._allow_sim_fallback():
                        self.state.heater = new_val
                        return self._sim_ok(self.state.last_command, fallback=True, reason=err)
                    return {"ok": False, "error": err or "heater command failed", "command": self.state.last_command}
                self.state.heater = new_val
            else:
                return {"ok": False, "error": f"Unsupported auxiliary action: {action}", "command": self.state.last_command}
        elif group == "day" and action == "nuc":
            new_val = not self.state.nuc_active
            if self.simulate:
                self.state.nuc_active = new_val
                return self._sim_ok(self.state.last_command)
            ok, err = self._post("nuc", json_body={"enabled": new_val})
            if not ok:
                if self._allow_sim_fallback():
                    self.state.nuc_active = new_val
                    return self._sim_ok(self.state.last_command, fallback=True, reason=err)
                return {"ok": False, "error": err or "nuc command failed", "command": self.state.last_command}
            self.state.nuc_active = new_val
        elif group == "thermal" and action == "agc":
            new_val = not self.state.agc_active
            if self.simulate:
                self.state.agc_active = new_val
                return self._sim_ok(self.state.last_command)
            ok, err = self._post("agc", json_body={"enabled": new_val})
            if not ok:
                if self._allow_sim_fallback():
                    self.state.agc_active = new_val
                    return self._sim_ok(self.state.last_command, fallback=True, reason=err)
                return {"ok": False, "error": err or "agc command failed", "command": self.state.last_command}
            self.state.agc_active = new_val
        else:
            return {"ok": False, "error": f"Unsupported quick action: {group}:{action}", "command": self.state.last_command}
        return {"ok": True, "command": self.state.last_command}

    def snapshot(self) -> Dict[str, Any]:
        if not self.simulate:
            self.probe_online()
        return {
            "time": int(time.time()),
            "connected": self._connected or self.simulate,
            "simulated": self.simulate,
            "active_ptz": self.state.active_ptz,
            "active_camera_id": self.state.active_camera_id,
            "ptz": {"speed": self.state.ptz_speed, "mode": self.state.ptz_mode},
            "telemetry": {
                "azimuth": round(self.state.azimuth, 1),
                "elevation": round(self.state.elevation, 1),
                "zoom": round(self.state.zoom, 3),
            },
            "lrf": {
                "mode": self.state.lrf_mode,
                "continuous": self.state.lrf_continuous,
                "range_m": self.state.lrf_range_m,
                "cursor": {"x": self.state.cursor_x, "y": self.state.cursor_y},
            },
            "illumination": {
                "enabled": self.state.illumination_enabled,
                "source": self.state.illumination_source,
                "intensity": self.state.illumination_intensity,
                "beam": self.state.illumination_beam,
                "brightness": self.state.illumination_brightness,
                "fov": self.state.illumination_fov,
            },
            "focus": {
                "day_auto": self.state.day_auto_focus,
                "thermal_auto": self.state.thermal_auto_focus,
            },
            "thermal": {
                "polarity": self.state.thermal_polarity,
                "brightness": self.state.thermal_brightness,
                "contrast": self.state.thermal_contrast,
            },
            "auxiliary": {
                "wiper": self.state.wiper,
                "heater": self.state.heater,
                "nuc": self.state.nuc_active,
                "agc": self.state.agc_active,
            },
            "custom_buttons": self.state.custom_buttons,
            "last_command": self.state.last_command,
        }


def build_adapter() -> DeviceAdapter:
    from ..core.config import resolve_jwt_secret

    url = os.getenv("SHIBLI_CONTROLS_URL", "http://127.0.0.1:8001")
    secret = resolve_jwt_secret()
    token = os.getenv("SHIBLI_API_TOKEN", "")
    adapter = ShibliControlsAdapter(url, secret, token)
    # Env-only at import time — avoid DB open during module import (causes startup lock/hang)
    if os.getenv("SHIBLI_HW_SIMULATE", "0").strip().lower() in ("1", "true", "yes", "on"):
        adapter.set_simulate(True)
    return adapter
