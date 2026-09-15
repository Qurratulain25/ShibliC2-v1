"""Windows Authenticode pipeline must sign and verify against the internal SHIBLI PKI."""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SIGN = ROOT / "deployment" / "scripts" / "sign-windows.ps1"
BUILD = ROOT / "deployment" / "scripts" / "build-windows.ps1"
AUDIT = ROOT / "deployment" / "scripts" / "audit-windows-sqlcipher.ps1"
WORKFLOW = ROOT / ".github" / "workflows" / "windows-installer.yml"

REQUIRED_SIGNED = (
    r"dist\ShibliC2\ShibliC2.exe",
    r"dist\ShibliControls\ShibliControls.exe",
    r"release\v1.0\ShibliC2-Setup-v1.0.exe",
)

FORBIDDEN_STORE = (
    "Import-Certificate",
    "X509Store",
    "Store.Add",
    "certutil",
    "TrustedPublisher",
    r"CurrentUser\Root",
    r"LocalMachine\Root",
)


class WindowsSigningReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sign = SIGN.read_text(encoding="utf-8")
        self.build = BUILD.read_text(encoding="utf-8")
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_workflow_expects_internal_root_and_pfx_secrets(self) -> None:
        self.assertIn("secrets.SHIBLI_SIGN_PFX_BASE64", self.workflow)
        self.assertIn("secrets.SHIBLI_SIGN_PFX_PASSWORD", self.workflow)
        self.assertIn("secrets.SHIBLI_SIGN_ROOT_CERT_BASE64", self.workflow)
        self.assertNotIn("SHIBLI_SIGN_ROOT_KEY", self.workflow)
        self.assertNotIn("BEGIN CERTIFICATE", self.workflow)
        self.assertNotIn("PRIVATE KEY", self.workflow)
        self.assertNotIn("BEGIN RSA", self.workflow)

    def test_ci_does_not_touch_windows_certificate_stores(self) -> None:
        for needle in FORBIDDEN_STORE:
            self.assertNotIn(needle, self.sign, msg=needle)
        self.assertIsNone(re.search(r"Store\.Add", self.sign))
        self.assertNotIn("Get-PfxCertificate", self.sign)
        self.assertNotIn("Read-Host", self.sign)

    def test_custom_root_trust_verification_literals(self) -> None:
        for needle in (
            "CustomRootTrust",
            "CustomTrustStore",
            "Get-AuthenticodeSignature",
            "HashMismatch",
            "NotSigned",
        ):
            self.assertIn(needle, self.sign)
        self.assertIn("X509ChainTrustMode", self.sign)
        self.assertIn("chain.Build", self.sign)
        self.assertIn("HasPrivateKey", self.sign)
        self.assertIn("SHIBLI C2 Internal Root CA", self.sign)
        self.assertIn("SHIBLI C2 Code Signing", self.sign)
        self.assertIn("1.3.6.1.5.5.7.3.3", self.sign)

    def test_initialize_only_materializes_files(self) -> None:
        self.assertIn("function Initialize-ShibliSigning", self.sign)
        self.assertIn("Decoding PFX", self.sign)
        self.assertIn("Writing temporary PFX", self.sign)
        self.assertIn("Decoding public root", self.sign)
        self.assertIn("Writing temporary root", self.sign)
        self.assertIn("Signing material initialization complete", self.sign)
        self.assertIn("SHIBLI_SIGN_ROOT_CERT_PATH", self.sign)
        init = self.sign.split("function Initialize-ShibliSigning", 1)[1].split("function ", 1)[0]
        self.assertNotIn("X509Store", init)
        self.assertNotIn("Import-Certificate", init)

    def test_signing_fails_if_root_pfx_or_password_missing(self) -> None:
        self.assertIn("function Assert-ShibliSigningSecrets", self.sign)
        self.assertIn("SHIBLI_SIGN_PFX_PASSWORD is missing", self.sign)
        self.assertIn("SHIBLI_SIGN_ROOT_CERT_BASE64 is missing", self.sign)
        self.assertIn("SHIBLI_SIGN_PFX_BASE64 (or SHIBLI_SIGN_PFX) is missing", self.sign)
        self.assertIn("Refusing unsigned 'signed' release", self.sign)
        self.assertIn("Assert-ShibliSigningSecrets", self.sign.split("function Invoke-ShibliAuthenticode", 1)[1])

    def test_all_three_binaries_are_signature_verified(self) -> None:
        self.assertIn(r"dist\ShibliC2\ShibliC2.exe", self.build)
        self.assertIn(r"dist\ShibliControls\ShibliControls.exe", self.build)
        self.assertIn("ShibliC2-Setup-v1.0.exe", self.build)
        self.assertIn("Assert-ShibliAuthenticode -Path (Join-Path $Root \"dist\\ShibliC2\\ShibliC2.exe\")", self.build)
        self.assertIn(
            "Assert-ShibliAuthenticode -Path (Join-Path $Root \"dist\\ShibliControls\\ShibliControls.exe\")",
            self.build,
        )
        self.assertIn("Assert-ShibliAuthenticode -Path $Setup", self.build)
        for path in REQUIRED_SIGNED:
            self.assertIn(path, self.workflow)
        self.assertIn("Get-AuthenticodeSignature", self.sign)
        self.assertIn("NotSigned", self.sign)
        self.assertIn("HashMismatch", self.sign)
        self.assertGreater(
            self.build.find("Assert-ShibliAuthenticode -Path $Setup"),
            self.build.find("Invoke-ShibliAuthenticode -Path $Setup"),
        )
        self.assertIn("Assert-ShibliAuthenticode -Path $path", self.workflow)

    def test_windows_build_signs_in_required_order(self) -> None:
        sqlcipher = self.build.find("audit-windows-sqlcipher.ps1")
        sign_c2 = self.build.find(
            'Invoke-ShibliAuthenticode -Path (Join-Path $Root "dist\\ShibliC2\\ShibliC2.exe")'
        )
        sign_controls = self.build.find(
            'Invoke-ShibliAuthenticode -Path (Join-Path $Root "dist\\ShibliControls\\ShibliControls.exe")'
        )
        iscc = self.build.find("& $Inno.Source $Iss")
        sign_setup = self.build.find("Invoke-ShibliAuthenticode -Path $Setup")
        verify_setup = self.build.find("Assert-ShibliAuthenticode -Path $Setup")
        checksum = self.build.find("SHA256SUMS-windows.txt")
        self.assertGreater(sqlcipher, 0)
        self.assertGreater(sign_c2, sqlcipher)
        self.assertGreater(sign_controls, sign_c2)
        self.assertGreater(iscc, sign_controls)
        self.assertGreater(sign_setup, iscc)
        self.assertGreater(verify_setup, sign_setup)
        self.assertGreater(checksum, verify_setup)
        self.assertIn("Initialize-ShibliSigning", self.build)
        self.assertIn("/tr", self.sign)
        self.assertIn("timestamp.digicert.com", self.sign)

    def test_cleanup_deletes_only_temp_pfx_and_cer_files(self) -> None:
        self.assertIn("function Clear-ShibliSignMaterial", self.sign)
        self.assertIn("shibli-codesign.pfx", self.sign)
        self.assertIn("shibli-internal-root.cer", self.sign)
        self.assertIn("Remove-Item", self.sign)
        self.assertNotIn("function Remove-ShibliInternalRootFromCurrentUserStore", self.sign)
        cleanup = self.sign.split("function Clear-ShibliSignMaterial", 1)[1].split("function ", 1)[0]
        self.assertNotIn("X509Store", cleanup)
        self.assertIn("Remove temporary signing files", self.workflow)
        self.assertIn("if: always()", self.workflow)
        self.assertIn("Clear-ShibliSignMaterial", self.workflow)

    def test_private_signing_material_not_committed_or_logged(self) -> None:
        self.assertNotIn("BEGIN CERTIFICATE", self.sign)
        self.assertNotIn("PRIVATE KEY", self.sign)
        self.assertNotIn("Write-Host $password", self.sign)
        self.assertNotIn("Write-Host $b64", self.sign)
        self.assertNotIn("Write-Host $pfxB64", self.sign)
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

    def test_internal_ca_is_not_claimed_universally_trusted(self) -> None:
        self.assertIn("explicitly trust the public root CA", self.sign)
        self.assertIn("never installs the CA into the Windows trust store", self.sign)


if __name__ == "__main__":
    unittest.main()
