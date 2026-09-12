"""go2rtc yaml is generated from camera records; aliases stay day/thermal."""
from __future__ import annotations

import unittest

from app.services.go2rtc import cameras_to_stream_map, render_config_text, resolve_stream_id


class Go2rtcRenderTests(unittest.TestCase):
    def test_day_and_thermal_aliases(self) -> None:
        cameras = [
            {"enabled": True, "cameraType": "Day", "rtspUrl": "rtsp://u:p@192.0.2.10:554/Streaming/Channels/102"},
            {
                "enabled": True,
                "cameraType": "Thermal",
                "rtspUrl": "rtsp://u:p@host.example:5554/live?channel=0&subtype=0&proto=Onvif",
            },
        ]
        streams = cameras_to_stream_map(cameras)
        self.assertEqual(set(streams), {"day", "thermal"})
        self.assertIn("192.0.2.10:554/Streaming/Channels/102", streams["day"])
        self.assertIn(":5554/live?channel=0&subtype=0&proto=Onvif", streams["thermal"])
        self.assertNotIn("201", streams["thermal"])

    def test_hostname_and_lan_both_accepted(self) -> None:
        cameras = [
            {"enabled": True, "cameraType": "Day", "rtspUrl": "rtsp://u:p@camera.example.invalid:554/Streaming/Channels/102"},
        ]
        text = render_config_text(cameras)
        self.assertIn("camera.example.invalid", text)
        self.assertIn("listen: \":1984\"", text)
        self.assertNotIn("203.0.113.26", text)

    def test_disabled_cameras_are_skipped(self) -> None:
        cameras = [{"enabled": False, "cameraType": "Day", "rtspUrl": "rtsp://u:p@192.0.2.30/stream"}]
        self.assertEqual(cameras_to_stream_map(cameras), {})

    def test_resolve_prefers_named_aliases(self) -> None:
        name = resolve_stream_id("thermal", [], {"day": {}, "thermal": {}})
        self.assertEqual(name, "thermal")


if __name__ == "__main__":
    unittest.main()
