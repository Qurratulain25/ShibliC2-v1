"""Thermal autofocus: channel must target the thermal camera and the real controls path."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.adapters.shibli_controls import ShibliControlsAdapter
from app.routes.media_route import resolve_focus_camera_id


def _cam(ip: str, ctype: str, ptz: str = "ptz-1", port: int = 80, enabled: bool = True) -> dict:
    return {
        "enabled": enabled,
        "cameraType": ctype,
        "ipAddress": ip,
        "onvifPort": port,
        "ptzMapping": ptz,
    }


class ResolveFocusCameraIdTests(unittest.TestCase):
    def test_day_keeps_request_camera_id(self) -> None:
        cid, err = resolve_focus_camera_id("day", "10.0.0.1:80", "ptz-1")
        self.assertIsNone(err)
        self.assertEqual(cid, "10.0.0.1:80")

    def test_thermal_uses_thermal_ip_not_day(self) -> None:
        cameras = [
            _cam("10.0.0.1", "day"),
            _cam("10.0.0.2", "thermal"),
        ]
        with patch("app.routes.media_route.list_local_cameras", return_value=cameras):
            cid, err = resolve_focus_camera_id("thermal", "10.0.0.1:80", "ptz-1")
        self.assertIsNone(err)
        self.assertEqual(cid, "10.0.0.2:80")

    def test_thermal_missing_config_is_error(self) -> None:
        with patch("app.routes.media_route.list_local_cameras", return_value=[_cam("10.0.0.1", "day")]):
            cid, err = resolve_focus_camera_id("thermal", "10.0.0.1:80", "ptz-1")
        self.assertIsNone(cid)
        self.assertEqual(err, "No thermal camera configured")

    def test_thermal_without_ip_is_error(self) -> None:
        cameras = [_cam("", "thermal")]
        with patch("app.routes.media_route.list_local_cameras", return_value=cameras):
            cid, err = resolve_focus_camera_id("thermal", "10.0.0.1:80", "ptz-1")
        self.assertIsNone(cid)
        self.assertEqual(err, "No IP configured for the thermal camera")


class FocusAutoAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = ShibliControlsAdapter("http://127.0.0.1:8001", "secret", "token")
        self.adapter.simulate = False
        self.calls: list[dict] = []

        def fake_post(path, camera_id=None, json_body=None):
            self.calls.append({"path": path, "camera_id": camera_id, "json_body": json_body})
            return True, None

        self.adapter._post = fake_post  # type: ignore[method-assign]
        self.adapter.warm_camera = lambda camera_id=None: {"ok": True}  # type: ignore[method-assign]

    def test_day_still_uses_focus_auto(self) -> None:
        result = self.adapter.focus_auto("10.0.0.1:80", channel="day")
        self.assertTrue(result["ok"])
        self.assertEqual(self.calls, [{"path": "focus/auto", "camera_id": "10.0.0.1:80", "json_body": None}])

    def test_thermal_uses_focus_mode_on_thermal_id(self) -> None:
        result = self.adapter.focus_auto("10.0.0.2:80", channel="thermal")
        self.assertTrue(result["ok"])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0]["path"], "focus/mode")
        self.assertEqual(self.calls[0]["camera_id"], "10.0.0.2:80")
        self.assertEqual(self.calls[0]["json_body"], {"auto": True, "camera_id": "10.0.0.2:80"})

    def test_thermal_does_not_call_nonexistent_thermal_auto_route(self) -> None:
        self.adapter.focus_auto("10.0.0.2:80", channel="thermal")
        self.assertFalse(any("thermal/auto" in (c["path"] or "") for c in self.calls))

    def test_thermal_reports_controls_failure(self) -> None:
        self.adapter._post = lambda *a, **k: (False, "Imaging service not available")  # type: ignore[method-assign]
        self.adapter.warm_camera = lambda camera_id=None: {"ok": False, "error": "offline"}  # type: ignore[method-assign]
        result = self.adapter.focus_auto("10.0.0.2:80", channel="thermal")
        self.assertFalse(result["ok"])
        self.assertIn("Imaging service not available", result["error"])
        self.assertNotIn("simulated", result)

    def test_thermal_without_camera_id_fails(self) -> None:
        result = self.adapter.focus_auto(None, channel="thermal")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "No thermal camera selected")
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
