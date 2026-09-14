"""Frozen Windows backend must log startup failures and keep persisted secrets."""
from __future__ import annotations

import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import launcher
from app.core.bootstrap_env import (
    bootstrap_completed,
    bootstrap_environment,
    reset_bootstrap_state,
)
from app.core.logging_setup import configure_logging, persist_startup_exception
from app.core.paths import data_dir, reset_data_dir_cache
from app.core.runtime_recovery import parse_env_file


ROOT = Path(__file__).resolve().parents[1]
_SECRET_ENV = (
    "SHIBLI_JWT_SECRET",
    "JWT_SECRET",
    "SHIBLI_DB_KEY",
    "SHIBLI_ENV",
    "SHIBLI_INSTALL_LAYOUT",
    "SHIBLI_PERSISTENT_ROOT",
    "SHIBLI_DATA_DIR",
)


class BackendStartupTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {name: os.environ.get(name) for name in _SECRET_ENV}
        for name in _SECRET_ENV:
            os.environ.pop(name, None)
        reset_bootstrap_state()
        reset_data_dir_cache()
        self._cwd = os.getcwd()

    def tearDown(self) -> None:
        os.chdir(self._cwd)
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
        reset_data_dir_cache()
        reset_bootstrap_state()
        (root / "data").mkdir(parents=True, exist_ok=True)
        (root / "logs").mkdir(parents=True, exist_ok=True)
        template = ROOT / ".env.example"
        (root / "data" / ".env").write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        return root

    def test_spawn_safe_reload_keeps_persisted_db_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._production_root(tmp)
            bootstrap_environment()
            first = parse_env_file(root / "data" / ".env")
            jwt = first.get("SHIBLI_JWT_SECRET") or ""
            key = first.get("SHIBLI_DB_KEY") or ""
            self.assertEqual(len(key), 64)
            reset_bootstrap_state()
            os.environ.pop("SHIBLI_DB_KEY", None)
            os.environ.pop("SHIBLI_JWT_SECRET", None)
            os.environ.pop("JWT_SECRET", None)
            bootstrap_environment()
            self.assertEqual(os.environ.get("SHIBLI_DB_KEY"), key)
            self.assertEqual(os.environ.get("SHIBLI_JWT_SECRET"), jwt)
            again = parse_env_file(root / "data" / ".env")
            self.assertEqual(again.get("SHIBLI_DB_KEY"), key)
            self.assertEqual(again.get("SHIBLI_JWT_SECRET"), jwt)

    def test_db_path_is_persistent_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._production_root(tmp)
            reset_data_dir_cache()
            self.assertEqual(data_dir() / "shibli_c2.db", root / "data" / "shibli_c2.db")
            self.assertNotIn("Program Files", str(data_dir()))
            self.assertNotIn("/opt/shiblic2", str(data_dir()))

    def test_launcher_uses_thread_not_multiprocessing(self) -> None:
        src = (ROOT / "launcher.py").read_text(encoding="utf-8")
        self.assertIn("def run_backend(", src)
        self.assertIn("threading.Thread(target=run_backend", src)
        self.assertNotIn("import multiprocessing", src)
        self.assertNotIn("multiprocessing.Process", src)
        self.assertNotIn("multiprocessing.freeze_support", src)
        self.assertIn("log_config=None", src)
        self.assertIn("install_signal_handlers = lambda: None", src)
        self.assertNotIn("webview", launcher.run_backend.__code__.co_names)

    def test_backend_exception_is_written_to_shibli_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._production_root(tmp)
            os.environ["SHIBLI_PERSISTENT_ROOT"] = str(root)
            reset_data_dir_cache()
            configure_logging(force=True)
            try:
                raise RuntimeError("SQLCipher failed to load (unit-test probe)")
            except RuntimeError as exc:
                persist_startup_exception("Backend failed during startup", exc)
            log_text = (root / "logs" / "shibli-c2.log").read_text(encoding="utf-8")
            self.assertIn("Backend failed during startup", log_text)
            self.assertIn("SQLCipher failed to load (unit-test probe)", log_text)
            self.assertIn("RuntimeError", log_text)
            self.assertNotIn(os.environ.get("SHIBLI_JWT_SECRET") or "not-present-jwt", log_text)

    def test_init_db_runs_after_bootstrap_in_lifespan(self) -> None:
        main_src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertLess(main_src.find("bootstrap_environment("), main_src.find("startup_auth()"))
        self.assertLess(main_src.find("require_sqlcipher()"), main_src.find("startup_auth()"))
        self.assertIn("startup_auth()", main_src)
        auth_src = (ROOT / "app" / "auth" / "service.py").read_text(encoding="utf-8")
        self.assertIn("init_db()", auth_src)
        self.assertLess(auth_src.find("resolve_jwt_secret()"), auth_src.find("init_db()"))

    def test_missing_db_on_first_run_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._production_root(tmp)
            self.assertFalse((root / "data" / "shibli_c2.db").exists())
            bootstrap_environment()
            self.assertTrue(bootstrap_completed())
            self.assertFalse((root / "data" / "shibli_c2.db").exists())
            self.assertEqual(len(parse_env_file(root / "data" / ".env").get("SHIBLI_DB_KEY") or ""), 64)

    def test_existing_db_missing_key_still_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._production_root(tmp)
            (root / "data" / "shibli_c2.db").write_bytes(b"encrypted-placeholder-db")
            with self.assertRaises(RuntimeError):
                bootstrap_environment()
            self.assertFalse(bootstrap_completed())

    def test_sqlcipher_spec_includes_native_components(self) -> None:
        spec = (ROOT / "ShibliC2.spec").read_text(encoding="utf-8")
        hook = ROOT / "deployment" / "scripts" / "pyi_rth_sqlcipher.py"
        self.assertTrue(hook.is_file())
        self.assertIn("collect_dynamic_libs(\"sqlcipher3\")", spec)
        self.assertIn("collect_all(\"sqlcipher3\")", spec)
        self.assertIn("_sqlcipher_sqlite", spec)
        self.assertIn("sqlcipher3.dbapi2", spec)
        self.assertIn("pyi_rth_sqlcipher.py", spec)
        engine = (ROOT / "app" / "core" / "db_engine.py").read_text(encoding="utf-8")
        self.assertIn("_prepare_sqlcipher_dll_search", engine)
        self.assertIn('os.environ["PATH"]', engine)
        hook_src = hook.read_text(encoding="utf-8")
        self.assertIn('os.environ["PATH"]', hook_src)
        self.assertIn("sqlcipher3", hook_src)
        self.assertLess(
            engine.find("import sqlcipher3.dbapi2"),
            engine.find("import sqlite3 as std_sqlite3"),
        )

    def test_run_backend_does_not_open_desktop_window(self) -> None:
        with patch.object(launcher, "bootstrap_environment", create=True):
            src = launcher.run_backend.__code__.co_names
            self.assertNotIn("create_window", src)
            self.assertNotIn("webview", src)


if __name__ == "__main__":
    unittest.main()
