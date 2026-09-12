"""Recovery helpers must never expose secrets and must classify LAN vs remote hosts."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.runtime_recovery import (
    classify_host,
    key_fingerprint,
    parse_env_file,
    redact_rtsp,
    rtsp_host_port_path,
    upsert_env_value,
)


class RuntimeRecoveryTests(unittest.TestCase):
    def test_fingerprint_is_ten_hex_chars(self) -> None:
        fp = key_fingerprint("example-key")
        self.assertEqual(len(fp), 10)
        self.assertTrue(all(c in "0123456789abcdef" for c in fp))

    def test_redact_rtsp_strips_userinfo(self) -> None:
        url = "rtsp://user:pass@192.0.2.10:554/Streaming/Channels/102"
        redacted = redact_rtsp(url)
        self.assertNotIn("secret", redacted)
        self.assertNotIn("admin", redacted)
        self.assertIn("192.0.2.10", redacted)
        self.assertIn("/Streaming/Channels/102", redacted)

    def test_host_kinds(self) -> None:
        self.assertEqual(classify_host("192.0.2.10"), "lan")
        self.assertEqual(classify_host("192.0.2.30"), "lan")
        self.assertEqual(classify_host("camera.example.invalid"), "hostname")
        self.assertEqual(classify_host("8.8.8.8"), "public_ip")

    def test_thermal_path_preserved_without_credentials(self) -> None:
        url = "rtsp://user:pass@host.example:5554/live?channel=0&subtype=0&proto=Onvif"
        info = rtsp_host_port_path(url)
        self.assertEqual(info["host"], "host.example")
        self.assertEqual(info["port"], 5554)
        self.assertEqual(info["path"], "/live?channel=0&subtype=0&proto=Onvif")

    def test_parse_env_does_not_require_printing_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("SHIBLI_DB_KEY=super-secret\nSHIBLI_CONTROLS_DIR=/opt/controls\n", encoding="utf-8")
            values = parse_env_file(path)
            self.assertTrue(values["SHIBLI_DB_KEY"])
            self.assertEqual(values["SHIBLI_CONTROLS_DIR"], "/opt/controls")
            self.assertEqual(key_fingerprint(values["SHIBLI_DB_KEY"]), key_fingerprint("super-secret"))

    def test_upsert_env_preserves_other_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("SHIBLI_DB_KEY=keep-me\nVMS_PORT=8080\n", encoding="utf-8")
            upsert_env_value(path, "SHIBLI_CONTROLS_DIR", "/opt/SHIBLI-controls")
            text = path.read_text(encoding="utf-8")
            self.assertIn("SHIBLI_DB_KEY=keep-me", text)
            self.assertIn("SHIBLI_CONTROLS_DIR=/opt/SHIBLI-controls", text)


if __name__ == "__main__":
    unittest.main()
