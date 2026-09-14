"""Optional USR/LRF hardware must not take down SHIBLI-controls."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
USR_PATH = ROOT / "deployment" / "runtime" / "controls" / "services" / "usr_connection.py"


def _load_usr():
    spec = importlib.util.spec_from_file_location("usr_connection_audit", USR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {USR_PATH}")
    import sys

    sys.modules.pop("usr_connection_audit", None)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OptionalHardwareTests(unittest.TestCase):
    def tearDown(self) -> None:
        usr = _load_usr()
        usr.USRConnectionManager._instance = None

    def test_winerror_10049_is_treated_as_address_not_available(self) -> None:
        usr = _load_usr()
        exc = OSError("WinError 10049")
        exc.winerror = 10049
        self.assertTrue(usr.USRConnectionManager._address_not_available(exc))

    def test_missing_site_ip_falls_back_to_wildcard(self) -> None:
        usr = _load_usr()
        manager = usr.USRConnectionManager.__new__(usr.USRConnectionManager)
        manager.server_ip = "192.168.0.50"
        missing = OSError("WinError 10049")
        missing.winerror = 10049

        class FakeSocket:
            def __init__(self) -> None:
                self.bound = None

            def setsockopt(self, *args, **kwargs) -> None:
                return None

            def bind(self, addr) -> None:
                if addr[0] == "192.168.0.50":
                    raise missing
                self.bound = addr

            def close(self) -> None:
                return None

        sockets = [FakeSocket(), FakeSocket()]

        def fake_socket(*_args, **_kwargs):
            return sockets.pop(0)

        with patch.object(usr.socket, "socket", side_effect=fake_socket):
            sock = manager._create_listen_socket("192.168.0.50", 8234)
        self.assertEqual(manager.server_ip, "0.0.0.0")
        self.assertEqual(sock.bound, ("0.0.0.0", 8234))

    def test_controls_server_reports_unavailable_not_fatal(self) -> None:
        src = (ROOT / "deployment" / "runtime" / "controls" / "server.py").read_text(encoding="utf-8")
        self.assertIn("[UNAVAILABLE]", src)
        self.assertIn("Camera/PTZ API is still running", src)
        self.assertNotIn("sys.exit", src)


if __name__ == "__main__":
    unittest.main()
