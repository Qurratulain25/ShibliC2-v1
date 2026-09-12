"""System install layout keeps binaries separate from writable data."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class InstallLayoutTests(unittest.TestCase):
    def tearDown(self) -> None:
        from app.core.paths import reset_data_dir_cache

        reset_data_dir_cache()
        os.environ.pop("SHIBLI_INSTALL_LAYOUT", None)
        os.environ.pop("SHIBLI_PERSISTENT_ROOT", None)
        os.environ.pop("SHIBLI_DATA_DIR", None)

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


if __name__ == "__main__":
    unittest.main()
