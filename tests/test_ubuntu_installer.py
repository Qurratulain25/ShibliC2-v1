"""Ubuntu .deb wrapper and postinst must not force a root-owned runtime."""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER_SCRIPTS = (
    ROOT / "deployment" / "ubuntu" / "build-inside-2204.sh",
    ROOT / "deployment" / "scripts" / "build-ubuntu.sh",
)
POSTINST = ROOT / "deployment" / "ubuntu" / "installer" / "postinst"
CONTROL = ROOT / "deployment" / "ubuntu" / "installer" / "control.in"


def _embedded_wrapper(script: Path) -> str:
    text = script.read_text(encoding="utf-8")
    match = re.search(
        r"cat > \"\$STAGE/opt/shiblic2/bin/shibli-c2\" <<'EOF'\n(.*)\nEOF",
        text,
        re.S,
    )
    if not match:
        raise AssertionError(f"wrapper heredoc missing in {script}")
    return match.group(1)


class UbuntuInstallerTests(unittest.TestCase):
    def test_wrappers_do_not_force_var_lib_persistent_root(self) -> None:
        for script in WRAPPER_SCRIPTS:
            wrapper = _embedded_wrapper(script)
            self.assertNotIn("SHIBLI_PERSISTENT_ROOT", wrapper, msg=str(script))
            self.assertNotIn("/var/lib/shiblic2", wrapper, msg=str(script))
            self.assertIn('export SHIBLI_INSTALL_LAYOUT="${SHIBLI_INSTALL_LAYOUT:-system}"', wrapper)
            self.assertIn('export SHIBLI_ENV="${SHIBLI_ENV:-production}"', wrapper)
            self.assertIn('export SHIBLI_DESKTOP="${SHIBLI_DESKTOP:-1}"', wrapper)
            self.assertIn("GO2RTC_BIN", wrapper)
            self.assertIn("FFMPEG_BIN", wrapper)
            self.assertIn("LD_LIBRARY_PATH", wrapper)
            self.assertIn("GI_TYPELIB_PATH", wrapper)
            self.assertIn("exec /opt/shiblic2/ShibliC2", wrapper)

    def test_postinst_does_not_rely_on_sudo_user(self) -> None:
        postinst = POSTINST.read_text(encoding="utf-8")
        executable = "\n".join(
            line for line in postinst.splitlines() if line.strip() and not line.lstrip().startswith("#")
        )
        self.assertNotIn("SUDO_USER", postinst)
        self.assertNotRegex(executable, r"\bchown\b")
        self.assertNotIn("chmod 777", postinst)
        self.assertNotRegex(postinst, r"chmod\s+-R\s+[0-7]*7")
        self.assertNotRegex(postinst, r"chmod\s+.*o\+w")
        self.assertIn("mkdir -p", postinst)
        self.assertIn("/var/lib/shiblic2", postinst)
        self.assertIn("if [ ! -f /var/lib/shiblic2/data/.env ]", postinst)
        self.assertIn("if [ ! -f /var/lib/shiblic2/config/go2rtc.yaml ]", postinst)
        self.assertIn("chmod 755 /opt/shiblic2/bin/shibli-c2", postinst)
        self.assertIn("chmod 755 /opt/shiblic2/ShibliC2", postinst)

    def test_package_does_not_ship_live_env(self) -> None:
        control = CONTROL.read_text(encoding="utf-8")
        self.assertNotIn(".env\n", control)
        for script in WRAPPER_SCRIPTS:
            text = script.read_text(encoding="utf-8")
            self.assertIn(".env.example", text)
            self.assertRegex(text, r"find .* -name '\.env'")

    def test_opt_tree_is_application_code_not_writable_data(self) -> None:
        desktop = (ROOT / "deployment" / "ubuntu" / "installer" / "shibli-c2.desktop").read_text(
            encoding="utf-8"
        )
        self.assertIn("Exec=/opt/shiblic2/bin/shibli-c2", desktop)
        for script in WRAPPER_SCRIPTS:
            wrapper = _embedded_wrapper(script)
            self.assertIn("cd /opt/shiblic2", wrapper)
            self.assertNotIn("chmod 777 /opt/shiblic2", wrapper)


if __name__ == "__main__":
    unittest.main()
