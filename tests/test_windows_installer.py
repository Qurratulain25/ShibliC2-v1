"""Windows installer must grant user modify on ProgramData and never ship a live .env."""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ISS = ROOT / "deployment" / "windows" / "installer" / "shibli-c2.iss"

RUNTIME_DIRS = (
    r"{commonappdata}\ShibliC2\config",
    r"{commonappdata}\ShibliC2\data",
    r"{commonappdata}\ShibliC2\logs",
    r"{commonappdata}\ShibliC2\recordings",
    r"{commonappdata}\ShibliC2\snapshots",
    r"{commonappdata}\ShibliC2\exports",
    r"{commonappdata}\ShibliC2\backups",
)


class WindowsInstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.iss = ISS.read_text(encoding="utf-8")

    def test_programdata_dirs_allow_users_modify(self) -> None:
        for rel in RUNTIME_DIRS:
            pattern = rf'Name:\s*"{re.escape(rel)}";\s*Permissions:\s*users-modify'
            self.assertRegex(self.iss, pattern, msg=f"missing users-modify for {rel}")

    def test_program_files_app_dir_is_not_user_writable(self) -> None:
        for line in self.iss.splitlines():
            if line.strip().startswith("Name:") and "{app}" in line:
                self.assertNotIn("users-modify", line)
                self.assertNotIn("users-full", line)

    def test_existing_env_is_not_overwritten(self) -> None:
        self.assertIn("if (not FileExists(EnvFile)) and FileExists(Example) then", self.iss)
        self.assertIn("FileCopy(Example, EnvFile, True);", self.iss)
        self.assertNotIn("FileCopy(Example, EnvFile, False);", self.iss)

    def test_installer_does_not_package_live_env(self) -> None:
        files_section = self.iss.split("[Files]", 1)[1].split("[Dirs]", 1)[0]
        self.assertIn(".env.example", files_section)
        self.assertNotIn("data\\.env", files_section)
        self.assertNotIn("data/.env", files_section)
        packaged_env = [
            line for line in files_section.splitlines()
            if ".env" in line and ".env.example" not in line
        ]
        self.assertEqual(packaged_env, [])


if __name__ == "__main__":
    unittest.main()
