"""Connection mode is administrator-selected, never inferred from IP ranges."""
from __future__ import annotations

import unittest

from app.core.connection_mode import (
    camera_matches_mode,
    normalize_camera_mode,
    normalize_session_mode,
)


class ConnectionModeTests(unittest.TestCase):
    def test_session_defaults_to_lan(self) -> None:
        self.assertEqual(normalize_session_mode(None), "lan")
        self.assertEqual(normalize_session_mode("LAN"), "lan")

    def test_session_ip_aliases(self) -> None:
        self.assertEqual(normalize_session_mode("IP / Online"), "ip")
        self.assertEqual(normalize_session_mode("online"), "ip")

    def test_does_not_classify_from_private_ip(self) -> None:
        cam = {"connectionMode": "legacy", "ipAddress": "192.0.2.10"}
        self.assertTrue(camera_matches_mode(cam, "lan"))
        self.assertTrue(camera_matches_mode(cam, "ip"))

    def test_lan_only_hidden_in_ip_mode(self) -> None:
        cam = {"connectionMode": "lan", "ipAddress": "10.0.0.5"}
        self.assertTrue(camera_matches_mode(cam, "lan"))
        self.assertFalse(camera_matches_mode(cam, "ip"))

    def test_ip_only_hidden_in_lan_mode(self) -> None:
        cam = {"connectionMode": "ip", "ipAddress": "192.168.1.10"}
        self.assertFalse(camera_matches_mode(cam, "lan"))
        self.assertTrue(camera_matches_mode(cam, "ip"))

    def test_new_camera_default_lan(self) -> None:
        self.assertEqual(normalize_camera_mode("", default="lan"), "lan")


if __name__ == "__main__":
    unittest.main()
