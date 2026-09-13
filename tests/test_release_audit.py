"""Release-blocker checks for packaged first-run, secrets, and writable paths."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import launcher
from app.core.bootstrap_env import reset_bootstrap_state
from app.core.paths import go2rtc_config_path, reset_data_dir_cache
from app.core.sidecars import _CHILDREN, _controls_child_env, start_sidecars


ROOT = Path(__file__).resolve().parents[1]


class ReleaseAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {
            name: os.environ.get(name)
            for name in (
                "SHIBLI_JWT_SECRET",
                "JWT_SECRET",
                "SHIBLI_DB_KEY",
                "SHIBLI_ENV",
                "SHIBLI_INSTALL_LAYOUT",
                "SHIBLI_PERSISTENT_ROOT",
                "SHIBLI_DATA_DIR",
            )
        }
        reset_bootstrap_state()
        reset_data_dir_cache()

    def tearDown(self) -> None:
        reset_bootstrap_state()
        reset_data_dir_cache()
        _CHILDREN.clear()
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_no_packaged_live_env_or_db(self) -> None:
        spec = (ROOT / "ShibliC2.spec").read_text(encoding="utf-8")
        iss = (ROOT / "deployment" / "windows" / "installer" / "shibli-c2.iss").read_text(encoding="utf-8")
        self.assertIn(".env.example", spec)
        self.assertNotIn('root / ".env")', spec)
        self.assertNotIn("shibli_c2.db", spec)
        self.assertIn(".env.example", iss)
        self.assertNotIn("shibli_c2.db", iss)

    def test_no_hardcoded_production_jwt_fallback_in_app(self) -> None:
        forbidden = (
            'os.getenv("SHIBLI_JWT_SECRET", "abracadabra")',
            "os.getenv('SHIBLI_JWT_SECRET', 'abracadabra')",
            'os.getenv("JWT_SECRET", "abracadabra")',
        )
        for path in (ROOT / "app").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for needle in forbidden:
                self.assertNotIn(needle, text, msg=str(path))
        auth = (ROOT / "app" / "auth" / "service.py").read_text(encoding="utf-8")
        self.assertNotIn("JWT_SECRET = resolve_jwt_secret()", auth)

    def test_controls_env_passes_log_dir_and_jwt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp) / "logs"
            logs.mkdir()
            os.environ["SHIBLI_JWT_SECRET"] = "a" * 64
            env = _controls_child_env(logs)
            self.assertEqual(env["SHIBLI_LOG_DIR"], str(logs))
            self.assertEqual(env["JWT_SECRET"], "a" * 64)

    def test_controls_immediate_exit_fails_closed_in_production(self) -> None:
        os.environ["SHIBLI_INSTALL_LAYOUT"] = "system"
        os.environ["SHIBLI_ENV"] = "production"
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp) / "logs"
            logs.mkdir()
            child = MagicMock()
            child.poll.return_value = 1
            with patch("app.core.sidecars.logs_dir", return_value=logs):
                with patch("app.core.sidecars._port_open", side_effect=lambda host, port: port != 8001):
                    with patch("app.core.sidecars.resolve_controls_cmd", return_value=["ShibliControls"]):
                        with patch("app.core.sidecars.subprocess.Popen", return_value=child):
                            with self.assertRaises(RuntimeError) as ctx:
                                start_sidecars()
            self.assertIn("SHIBLI-controls failed to start", str(ctx.exception))

    def test_backend_not_listening_does_not_open_webview(self) -> None:
        with patch.object(launcher, "_wait_for_listen", return_value=False):
            with patch.object(launcher, "_fatal", side_effect=SystemExit(1)) as fatal:
                with patch("app.core.sidecars.stop_sidecars"):
                    with self.assertRaises(SystemExit):
                        launcher._ensure_backend_listening("127.0.0.1", 8080, "http://127.0.0.1:8080")
        self.assertTrue(fatal.called)
        message = fatal.call_args.args[0]
        self.assertIn("did not start listening", message)

    def test_ubuntu_go2rtc_uses_writable_persistent_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["SHIBLI_INSTALL_LAYOUT"] = "system"
            os.environ["SHIBLI_PERSISTENT_ROOT"] = str(root)
            os.environ.pop("SHIBLI_DATA_DIR", None)
            reset_data_dir_cache()
            cfg = go2rtc_config_path()
            self.assertEqual(cfg, root / "config" / "go2rtc.yaml")
            self.assertTrue(cfg.is_file())
            first = cfg.read_text(encoding="utf-8")
            cfg.write_text(first + "# keep\n", encoding="utf-8")
            reset_data_dir_cache()
            again = go2rtc_config_path()
            self.assertIn("# keep", again.read_text(encoding="utf-8"))

    def test_auth_import_does_not_require_jwt_before_bootstrap(self) -> None:
        auth = (ROOT / "app" / "auth" / "service.py").read_text(encoding="utf-8")
        self.assertNotIn("JWT_SECRET = resolve_jwt_secret()", auth)
        self.assertIn("return jwt.encode(payload, resolve_jwt_secret(), algorithm=\"HS256\")", auth)
        self.assertIn("return jwt.decode(token, resolve_jwt_secret(), algorithms=[\"HS256\"])", auth)

    def test_example_env_has_no_live_secrets(self) -> None:
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("SHIBLI_JWT_SECRET=", example)
        self.assertIn("SHIBLI_DB_KEY=", example)
        self.assertNotIn("abracadabra", example)
        for line in example.splitlines():
            if line.startswith("SHIBLI_JWT_SECRET="):
                self.assertEqual(line, "SHIBLI_JWT_SECRET=")
            if line.startswith("SHIBLI_DB_KEY="):
                self.assertEqual(line, "SHIBLI_DB_KEY=")
            if line.startswith("SHIBLI_DEFAULT_ADMIN_PASSWORD="):
                self.assertEqual(line, "SHIBLI_DEFAULT_ADMIN_PASSWORD=")

    def test_no_chmod_777_in_packaging(self) -> None:
        for rel in (
            "deployment/ubuntu/installer/postinst",
            "deployment/ubuntu/installer/preinst",
            "deployment/windows/installer/shibli-c2.iss",
            "app/core/sidecars.py",
            "deployment/runtime/controls/utils/logger.py",
        ):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("chmod 777", text)
            self.assertNotIn("o+w", text)


if __name__ == "__main__":
    unittest.main()
