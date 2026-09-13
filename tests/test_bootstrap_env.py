"""First-run production bootstrap must persist secrets and remain retryable."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.bootstrap_env import (
    bootstrap_completed,
    bootstrap_environment,
    reset_bootstrap_state,
)
from app.core.config import resolve_jwt_secret
from app.core.paths import reset_data_dir_cache
from app.core.runtime_recovery import parse_env_file


_SECRET_ENV = (
    "SHIBLI_JWT_SECRET",
    "JWT_SECRET",
    "SHIBLI_DB_KEY",
    "SHIBLI_ENV",
    "SHIBLI_INSTALL_LAYOUT",
    "SHIBLI_PERSISTENT_ROOT",
    "SHIBLI_DATA_DIR",
)


class BootstrapEnvTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {name: os.environ.get(name) for name in _SECRET_ENV}
        for name in _SECRET_ENV:
            os.environ.pop(name, None)
        reset_bootstrap_state()
        reset_data_dir_cache()

    def tearDown(self) -> None:
        reset_bootstrap_state()
        reset_data_dir_cache()
        for name in _SECRET_ENV:
            os.environ.pop(name, None)
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def _production_root(self, tmp: str) -> Path:
        root = Path(tmp)
        os.environ["SHIBLI_INSTALL_LAYOUT"] = "system"
        os.environ["SHIBLI_ENV"] = "production"
        os.environ["SHIBLI_PERSISTENT_ROOT"] = str(root)
        os.environ.pop("SHIBLI_DATA_DIR", None)
        os.environ.pop("SHIBLI_JWT_SECRET", None)
        os.environ.pop("JWT_SECRET", None)
        os.environ.pop("SHIBLI_DB_KEY", None)
        reset_data_dir_cache()
        reset_bootstrap_state()
        (root / "data").mkdir(parents=True, exist_ok=True)
        template = Path(__file__).resolve().parents[1] / ".env.example"
        (root / "data" / ".env").write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        return root

    def test_first_production_bootstrap_generates_and_persists_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._production_root(tmp)
            bootstrap_environment()
            self.assertTrue(bootstrap_completed())
            env_file = root / "data" / ".env"
            values = parse_env_file(env_file)
            jwt = values.get("SHIBLI_JWT_SECRET") or ""
            db_key = values.get("SHIBLI_DB_KEY") or ""
            self.assertEqual(len(jwt), 64)
            self.assertEqual(len(db_key), 64)
            self.assertTrue(all(c in "0123456789abcdef" for c in jwt))
            self.assertTrue(all(c in "0123456789abcdef" for c in db_key))
            self.assertNotEqual(jwt, db_key)
            self.assertEqual(os.environ.get("SHIBLI_JWT_SECRET"), jwt)
            self.assertEqual(os.environ.get("SHIBLI_DB_KEY"), db_key)
            self.assertEqual(resolve_jwt_secret(), jwt)

    def test_second_bootstrap_preserves_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._production_root(tmp)
            bootstrap_environment()
            first = parse_env_file(root / "data" / ".env")
            bootstrap_environment()
            self.assertTrue(bootstrap_completed())
            again = parse_env_file(root / "data" / ".env")
            self.assertEqual(first.get("SHIBLI_JWT_SECRET"), again.get("SHIBLI_JWT_SECRET"))
            self.assertEqual(first.get("SHIBLI_DB_KEY"), again.get("SHIBLI_DB_KEY"))
            reset_bootstrap_state()
            bootstrap_environment()
            reopened = parse_env_file(root / "data" / ".env")
            self.assertEqual(first.get("SHIBLI_JWT_SECRET"), reopened.get("SHIBLI_JWT_SECRET"))
            self.assertEqual(first.get("SHIBLI_DB_KEY"), reopened.get("SHIBLI_DB_KEY"))

    def test_failed_bootstrap_leaves_flag_false_and_can_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._production_root(tmp)
            with patch(
                "app.core.bootstrap_env._upsert_env_line",
                side_effect=PermissionError("denied"),
            ):
                with self.assertRaises(PermissionError):
                    bootstrap_environment()
            self.assertFalse(bootstrap_completed())
            bootstrap_environment()
            self.assertTrue(bootstrap_completed())
            values = parse_env_file(Path(tmp) / "data" / ".env")
            self.assertEqual(len(values.get("SHIBLI_JWT_SECRET") or ""), 64)
            self.assertEqual(len(values.get("SHIBLI_DB_KEY") or ""), 64)

    def test_production_jwt_resolution_fails_closed(self) -> None:
        os.environ["SHIBLI_ENV"] = "production"
        os.environ.pop("SHIBLI_JWT_SECRET", None)
        os.environ.pop("JWT_SECRET", None)
        with self.assertRaises(RuntimeError) as ctx:
            resolve_jwt_secret()
        self.assertIn("SHIBLI_JWT_SECRET", str(ctx.exception))

    def test_controls_adapter_has_no_hardcoded_jwt_fallback(self) -> None:
        src = (Path(__file__).resolve().parents[1] / "app" / "adapters" / "shibli_controls.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('os.getenv("SHIBLI_JWT_SECRET", "abracadabra")', src)
        self.assertIn("resolve_jwt_secret()", src)

    def test_production_launcher_does_not_swallow_bootstrap_failure(self) -> None:
        os.environ["SHIBLI_INSTALL_LAYOUT"] = "system"
        os.environ["SHIBLI_ENV"] = "production"
        import launcher

        with patch(
            "app.core.bootstrap_env.bootstrap_environment",
            side_effect=PermissionError("denied"),
        ):
            with self.assertRaises(PermissionError):
                launcher._prepare_environment()

    def test_development_launcher_may_fallback(self) -> None:
        os.environ["SHIBLI_INSTALL_LAYOUT"] = "dev"
        os.environ["SHIBLI_ENV"] = "development"
        import launcher

        with patch(
            "app.core.bootstrap_env.bootstrap_environment",
            side_effect=PermissionError("denied"),
        ):
            host, port = launcher._prepare_environment()
        self.assertEqual(host, "127.0.0.1")
        self.assertEqual(port, 8080)


if __name__ == "__main__":
    unittest.main()
