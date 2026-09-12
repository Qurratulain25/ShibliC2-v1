"""Camera test accepts hostname or LAN IP; RTSP success is not faked."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.camera_test import rtsp_target, test_camera_connection


class CameraHostTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_host_message(self) -> None:
        result = await test_camera_connection({"rtsp_url": "not-a-url"})
        self.assertFalse(result["ok"])
        self.assertIn("Host or IP", result["message"])

    async def test_rtsp_unreachable_is_failure(self) -> None:
        payload = {
            "ip_address": "192.0.2.10",
            "rtsp_url": "rtsp://user:pass@192.0.2.10:554/Streaming/Channels/102",
            "onvif_port": 80,
        }
        with patch("app.services.camera_test._tcp_open", return_value=False):
            result = await test_camera_connection(payload)
        self.assertFalse(result["ok"])
        self.assertFalse(result["rtsp_ok"])

    async def test_hostname_rtsp_ok_without_onvif(self) -> None:
        payload = {
            "ip_address": "camera.example.invalid",
            "rtsp_url": "rtsp://user:pass@camera.example.invalid:5554/live?channel=0&subtype=0&proto=Onvif",
            "username": "user",
            "password": "pass",
            "onvif_port": 80,
        }

        def fake_tcp(host, port, timeout=3.0):
            return host == "camera.example.invalid" and port == 5554

        with patch("app.services.camera_test._tcp_open", side_effect=fake_tcp):
            result = await test_camera_connection(payload)
        self.assertTrue(result["ok"])
        self.assertTrue(result["rtsp_ok"])
        self.assertFalse(result["onvif_ok"])

    def test_thermal_remote_port(self) -> None:
        host, port = rtsp_target(
            "rtsp://u:p@camera.example.invalid:5554/live?channel=0&subtype=0&proto=Onvif",
            "camera.example.invalid",
        )
        self.assertEqual(host, "camera.example.invalid")
        self.assertEqual(port, 5554)


if __name__ == "__main__":
    unittest.main()
