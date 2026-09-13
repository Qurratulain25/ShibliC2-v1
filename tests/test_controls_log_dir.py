"""SHIBLI-controls must log under the writable persistent logs directory."""
from __future__ import annotations

import importlib.util
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
LOGGER_PATH = ROOT / "deployment" / "runtime" / "controls" / "utils" / "logger.py"
SIDECARS_PATH = ROOT / "app" / "core" / "sidecars.py"


def _load_controls_logger():
    spec = importlib.util.spec_from_file_location("controls_utils_logger", LOGGER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {LOGGER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ControlsLogDirTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_log_dir = os.environ.get("SHIBLI_LOG_DIR")
        os.environ.pop("SHIBLI_LOG_DIR", None)
        self._root = logging.getLogger()
        self._saved_handlers = list(self._root.handlers)
        self._cwd = os.getcwd()

    def tearDown(self) -> None:
        os.chdir(self._cwd)
        for handler in list(self._root.handlers):
            if handler not in self._saved_handlers:
                self._root.removeHandler(handler)
                try:
                    handler.close()
                except OSError:
                    pass
        for handler in self._saved_handlers:
            if handler not in self._root.handlers:
                self._root.addHandler(handler)
        if self._saved_log_dir is None:
            os.environ.pop("SHIBLI_LOG_DIR", None)
        else:
            os.environ["SHIBLI_LOG_DIR"] = self._saved_log_dir
        from app.core import sidecars

        sidecars._CHILDREN.clear()

    def test_sidecars_passes_shibli_log_dir(self) -> None:
        from app.core.sidecars import _controls_child_env

        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp) / "persistent" / "logs"
            logs.mkdir(parents=True)
            env = _controls_child_env(logs)
            self.assertEqual(env["SHIBLI_LOG_DIR"], str(logs))
            self.assertNotEqual(Path(env["SHIBLI_LOG_DIR"]), Path("logs"))

    def test_start_sidecars_injects_log_dir_into_controls_process(self) -> None:
        from app.core import sidecars

        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp) / "ShibliC2" / "logs"
            logs.mkdir(parents=True)
            child = MagicMock()
            child.poll.return_value = None
            seen_8001 = {"n": 0}

            def fake_port(_host: str, port: int) -> bool:
                if port == 1984:
                    return True
                if port == 8001:
                    seen_8001["n"] += 1
                    return seen_8001["n"] > 1
                return False

            with patch.object(sidecars, "logs_dir", return_value=logs):
                with patch.object(sidecars, "_port_open", side_effect=fake_port):
                    with patch.object(
                        sidecars,
                        "resolve_controls_cmd",
                        return_value=[str(Path(tmp) / "ShibliControls")],
                    ):
                        with patch.object(sidecars.subprocess, "Popen", return_value=child) as popen:
                            sidecars.start_sidecars()
            self.assertTrue(popen.called)
            kwargs = popen.call_args.kwargs
            self.assertEqual(kwargs["env"]["SHIBLI_LOG_DIR"], str(logs))
            self.assertNotEqual(Path(kwargs["cwd"]), logs)
            source = SIDECARS_PATH.read_text(encoding="utf-8")
            self.assertNotIn("chmod", source)
            self.assertNotIn("777", source)
            self.assertNotIn("runas", source.lower())
            self.assertNotIn("Administrator", source)

    def test_logger_honors_shibli_log_dir(self) -> None:
        logger_mod = _load_controls_logger()
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "Program Files" / "ShibliC2"
            install.mkdir(parents=True)
            persistent = Path(tmp) / "ProgramData" / "ShibliC2" / "logs"
            os.environ["SHIBLI_LOG_DIR"] = str(persistent)
            os.chdir(install)
            self._root.handlers.clear()
            logger_mod.setup_logging()
            combined = persistent / "combined.log"
            error = persistent / "error.log"
            self.assertTrue(combined.is_file())
            self.assertTrue(error.is_file())
            self.assertFalse((install / "logs").exists())
            logging.getLogger("controls-test").error("runtime probe")
            self.assertIn("runtime probe", error.read_text(encoding="utf-8"))
            self.assertNotIn("SHIBLI_JWT_SECRET", error.read_text(encoding="utf-8"))

    def test_development_fallback_uses_relative_logs(self) -> None:
        logger_mod = _load_controls_logger()
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "src"
            work.mkdir()
            os.environ.pop("SHIBLI_LOG_DIR", None)
            os.chdir(work)
            self._root.handlers.clear()
            log_dir = logger_mod.resolve_log_dir()
            self.assertEqual(log_dir.resolve(), (work / "logs").resolve())
            logger_mod.setup_logging()
            self.assertTrue((work / "logs" / "combined.log").is_file())
            self.assertTrue((work / "logs" / "error.log").is_file())

    def test_logger_has_no_chmod_or_admin_workaround(self) -> None:
        source = LOGGER_PATH.read_text(encoding="utf-8")
        self.assertIn("SHIBLI_LOG_DIR", source)
        self.assertNotIn("chmod", source)
        self.assertNotIn("777", source)
        self.assertNotIn("runas", source.lower())
        self.assertNotIn("Administrator", source)
        self.assertNotIn('os.makedirs("logs"', source)
        self.assertNotIn("FileHandler('logs/", source)
        self.assertNotIn('FileHandler("logs/', source)


if __name__ == "__main__":
    unittest.main()
