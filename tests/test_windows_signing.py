"""Windows Authenticode pipeline must be ready without committing certificates."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SIGN = ROOT / "deployment" / "scripts" / "sign-windows.ps1"
BUILD = ROOT / "deployment" / "scripts" / "build-windows.ps1"
AUDIT = ROOT / "deployment" / "scripts" / "audit-windows-sqlcipher.ps1"
WORKFLOW = ROOT / ".github" / "workflows" / "windows-installer.yml"


class WindowsSigningReadinessTests(unittest.TestCase):
    def test_signing_script_is_gated_and_verifies(self) -> None:
        src = SIGN.read_text(encoding="utf-8")
        self.assertIn("function Invoke-ShibliAuthenticode", src)
        self.assertIn("function Assert-ShibliAuthenticode", src)
        self.assertIn("SHIBLI_SIGN_ENABLED", src)
        self.assertIn("SHIBLI_SIGN_PFX", src)
        self.assertIn("SHIBLI_SIGN_PFX_BASE64", src)
        self.assertIn("SHIBLI_SIGN_CERT_THUMBPRINT", src)
        self.assertIn("signtool", src)
        self.assertIn("Get-AuthenticodeSignature", src)
        self.assertNotIn("BEGIN CERTIFICATE", src)
        self.assertNotIn("PRIVATE KEY", src)

    def test_windows_build_signs_in_required_order(self) -> None:
        src = BUILD.read_text(encoding="utf-8")
        sign_c2 = src.find("Invoke-ShibliAuthenticode -Path (Join-Path $Root \"dist\\ShibliC2\\ShibliC2.exe\")")
        sign_controls = src.find("Invoke-ShibliAuthenticode -Path (Join-Path $Root \"dist\\ShibliControls\\ShibliControls.exe\")")
        iscc = src.find("& $Inno.Source $Iss")
        sign_setup = src.find("Invoke-ShibliAuthenticode -Path $Setup")
        self.assertGreater(sign_c2, 0)
        self.assertGreater(sign_controls, sign_c2)
        self.assertGreater(iscc, sign_controls)
        self.assertGreater(sign_setup, iscc)
        self.assertIn("audit-windows-sqlcipher.ps1", src)
        self.assertIn("import sqlcipher3.dbapi2", src)

    def test_workflow_uses_secrets_placeholders_only(self) -> None:
        src = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("secrets.SHIBLI_SIGN_PFX_BASE64", src)
        self.assertIn("secrets.SHIBLI_SIGN_PFX_PASSWORD", src)
        self.assertIn("Authenticode verification failed", src)
        self.assertNotIn("BEGIN CERTIFICATE", src)
        self.assertNotIn("PRIVATE KEY", src)

    def test_repo_does_not_contain_pfx_or_private_keys(self) -> None:
        forbidden = []
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if any(part in {".git", "dist", "build", ".venv", "venv", "node_modules"} for part in path.parts):
                continue
            if path.suffix.lower() in {".pfx", ".p12", ".pem", ".key"}:
                forbidden.append(str(path.relative_to(ROOT)))
        self.assertEqual(forbidden, [])
        self.assertTrue(AUDIT.is_file())
        audit = AUDIT.read_text(encoding="utf-8")
        self.assertIn("sqlcipher3", audit)
        self.assertIn("_sqlite3", audit)


if __name__ == "__main__":
    unittest.main()
