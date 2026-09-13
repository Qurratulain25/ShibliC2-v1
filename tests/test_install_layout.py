"""System install layout keeps binaries separate from writable data."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class InstallLayoutTests(unittest.TestCase):
    def tearDown(self) -> None:
        from app.core.paths import reset_data_dir_cache

        reset_data_dir_cache()
        os.environ.pop("SHIBLI_INSTALL_LAYOUT", None)
        os.environ.pop("SHIBLI_PERSISTENT_ROOT", None)
        os.environ.pop("SHIBLI_DATA_DIR", None)
        os.environ.pop("XDG_DATA_HOME", None)

    def test_system_layout_uses_persistent_siblings(self) -> None:
        from app.core.paths import (
            backups_dir,
            data_dir,
            go2rtc_config_path,
            logs_dir,
            recordings_dir,
            reset_data_dir_cache,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["SHIBLI_INSTALL_LAYOUT"] = "system"
            os.environ["SHIBLI_PERSISTENT_ROOT"] = str(root)
            os.environ.pop("SHIBLI_DATA_DIR", None)
            reset_data_dir_cache()
            self.assertEqual(data_dir(), root / "data")
            self.assertEqual(logs_dir(), root / "logs")
            self.assertEqual(recordings_dir(), root / "recordings")
            self.assertEqual(backups_dir(), root / "backups")
            cfg = go2rtc_config_path()
            self.assertEqual(cfg, root / "config" / "go2rtc.yaml")
            self.assertTrue(cfg.exists())

    def test_dev_layout_keeps_project_data(self) -> None:
        from app.core.paths import data_dir, project_root, reset_data_dir_cache

        os.environ["SHIBLI_INSTALL_LAYOUT"] = "dev"
        os.environ.pop("SHIBLI_DATA_DIR", None)
        os.environ.pop("SHIBLI_PERSISTENT_ROOT", None)
        reset_data_dir_cache()
        self.assertEqual(data_dir(), project_root() / "data")

    def test_linux_unwritable_var_lib_falls_back_to_xdg(self) -> None:
        from app.core.paths import persistent_root, reset_data_dir_cache

        with tempfile.TemporaryDirectory() as tmp:
            xdg = Path(tmp) / "xdg-data"
            os.environ["SHIBLI_INSTALL_LAYOUT"] = "system"
            os.environ["XDG_DATA_HOME"] = str(xdg)
            os.environ.pop("SHIBLI_PERSISTENT_ROOT", None)
            os.environ.pop("SHIBLI_DATA_DIR", None)
            reset_data_dir_cache()
            with patch("app.core.paths.sys.platform", "linux"):
                with patch(
                    "app.core.paths._dir_writable",
                    side_effect=lambda p: "/var/lib/shiblic2" not in str(p),
                ):
                    root = persistent_root()
            self.assertEqual(root, xdg / "ShibliC2")
            self.assertTrue(root.is_dir())

    def test_linux_unwritable_var_lib_falls_back_to_home_share(self) -> None:
        from app.core.paths import persistent_root, reset_data_dir_cache

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            os.environ["SHIBLI_INSTALL_LAYOUT"] = "system"
            os.environ.pop("XDG_DATA_HOME", None)
            os.environ.pop("SHIBLI_PERSISTENT_ROOT", None)
            os.environ.pop("SHIBLI_DATA_DIR", None)
            reset_data_dir_cache()
            with patch("app.core.paths.sys.platform", "linux"):
                with patch.object(Path, "home", return_value=home):
                    with patch(
                        "app.core.paths._dir_writable",
                        side_effect=lambda p: "/var/lib/shiblic2" not in str(p),
                    ):
                        root = persistent_root()
            self.assertEqual(root, home / ".local" / "share" / "ShibliC2")

    def test_explicit_persistent_root_is_not_replaced_by_fallback(self) -> None:
        from app.core.paths import persistent_root, reset_data_dir_cache

        with tempfile.TemporaryDirectory() as tmp:
            forced = Path(tmp) / "forced-root"
            xdg = Path(tmp) / "xdg-data"
            os.environ["SHIBLI_INSTALL_LAYOUT"] = "system"
            os.environ["SHIBLI_PERSISTENT_ROOT"] = str(forced)
            os.environ["XDG_DATA_HOME"] = str(xdg)
            os.environ.pop("SHIBLI_DATA_DIR", None)
            reset_data_dir_cache()
            with patch("app.core.paths.sys.platform", "linux"):
                root = persistent_root()
            self.assertEqual(root, forced)
            self.assertNotEqual(root, xdg / "ShibliC2")

    def test_explicit_unwritable_persistent_root_does_not_fall_back(self) -> None:
        from app.core.paths import persistent_root, reset_data_dir_cache

        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "blocker"
            blocker.write_text("not-a-directory", encoding="utf-8")
            forced = blocker / "root"
            xdg = Path(tmp) / "xdg-data"
            os.environ["SHIBLI_INSTALL_LAYOUT"] = "system"
            os.environ["SHIBLI_PERSISTENT_ROOT"] = str(forced)
            os.environ["XDG_DATA_HOME"] = str(xdg)
            os.environ.pop("SHIBLI_DATA_DIR", None)
            reset_data_dir_cache()
            with self.assertRaises(OSError):
                persistent_root()
            self.assertFalse((xdg / "ShibliC2").exists())

    def test_fallback_persistent_root_creates_runtime_tree(self) -> None:
        from app.core.paths import (
            backups_dir,
            data_dir,
            exports_dir,
            logs_dir,
            recordings_dir,
            reset_data_dir_cache,
            snapshots_dir,
        )

        with tempfile.TemporaryDirectory() as tmp:
            xdg = Path(tmp) / "xdg-data"
            os.environ["SHIBLI_INSTALL_LAYOUT"] = "system"
            os.environ["XDG_DATA_HOME"] = str(xdg)
            os.environ.pop("SHIBLI_PERSISTENT_ROOT", None)
            os.environ.pop("SHIBLI_DATA_DIR", None)
            reset_data_dir_cache()
            with patch("app.core.paths.sys.platform", "linux"):
                with patch(
                    "app.core.paths._dir_writable",
                    side_effect=lambda p: "/var/lib/shiblic2" not in str(p),
                ):
                    self.assertEqual(data_dir(), xdg / "ShibliC2" / "data")
                    self.assertEqual(logs_dir(), xdg / "ShibliC2" / "logs")
                    self.assertEqual(recordings_dir(), xdg / "ShibliC2" / "recordings")
                    self.assertEqual(snapshots_dir(), xdg / "ShibliC2" / "snapshots")
                    self.assertEqual(exports_dir(), xdg / "ShibliC2" / "exports")
                    self.assertEqual(backups_dir(), xdg / "ShibliC2" / "backups")


if __name__ == "__main__":
    unittest.main()
