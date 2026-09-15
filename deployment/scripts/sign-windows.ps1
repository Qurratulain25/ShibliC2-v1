#Requires -Version 5.1
# Authenticode signing for SHIBLI C2 Windows artifacts.
# Certificates and private keys must NEVER be committed to git.
#
# Internal SHIBLI PKI (not trusted by arbitrary Windows PCs):
#   Root (PUBLIC only): CN=SHIBLI C2 Internal Root CA
#   Leaf:               CN=SHIBLI C2 Code Signing  EKU=Code Signing
# Client/QA machines must explicitly trust the public root CA.
# CI never installs the CA into the Windows trust store. Verification uses
# X509Chain CustomRootTrust against the temporary public root file only.
#
# Enable with SHIBLI_SIGN_ENABLED=true and:
#   SHIBLI_SIGN_PFX_BASE64          (or SHIBLI_SIGN_PFX path)
#   SHIBLI_SIGN_PFX_PASSWORD
#   SHIBLI_SIGN_ROOT_CERT_BASE64    PUBLIC root .cer only — no private key
# Optional:
#   SHIBLI_SIGN_TIMESTAMP_URL       default http://timestamp.digicert.com
#
# When signing is disabled this is a no-op so unsigned CI can still build.
# When signing is enabled, missing material or a failed verification is fatal.
# Never Write-Host PFX bytes, passwords, or private keys.

$ErrorActionPreference = "Stop"

$script:ShibliInternalRootCn = "SHIBLI C2 Internal Root CA"
$script:ShibliCodeSigningCn = "SHIBLI C2 Code Signing"
$script:ShibliCodeSigningEkuOid = "1.3.6.1.5.5.7.3.3"

function Test-ShibliSignEnabled {
    $raw = [string]$env:SHIBLI_SIGN_ENABLED
    return $raw.Trim().ToLowerInvariant() -in @("1", "true", "yes", "on")
}

function Get-ShibliSignTool {
    $cmd = Get-Command "signtool.exe" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $kits = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
    if (Test-Path $kits) {
        $found = Get-ChildItem -Path $kits -Recurse -Filter "signtool.exe" -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match "\\x64\\signtool\.exe$" } |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    throw "signtool.exe not found. Install the Windows 10/11 SDK (Signing Tools)."
}

function Get-ShibliTimestampUrl {
    $url = [string]$env:SHIBLI_SIGN_TIMESTAMP_URL
    if ([string]::IsNullOrWhiteSpace($url)) {
        return "http://timestamp.digicert.com"
    }
    return $url.Trim()
}

function Get-ShibliSignTempPath {
    param([string]$Name)
    $root = $env:RUNNER_TEMP
    if ([string]::IsNullOrWhiteSpace($root)) {
        $root = [System.IO.Path]::GetTempPath()
    }
    return (Join-Path $root $Name)
}

function Assert-ShibliSigningSecrets {
    if (-not (Test-ShibliSignEnabled)) {
        return
    }
    $pfxPath = [string]$env:SHIBLI_SIGN_PFX
    $pfxB64 = [string]$env:SHIBLI_SIGN_PFX_BASE64
    $password = [string]$env:SHIBLI_SIGN_PFX_PASSWORD
    $rootB64 = [string]$env:SHIBLI_SIGN_ROOT_CERT_BASE64
    $rootPath = [string]$env:SHIBLI_SIGN_ROOT_CERT_PATH
    if ([string]::IsNullOrWhiteSpace($pfxPath) -and [string]::IsNullOrWhiteSpace($pfxB64)) {
        throw "Signing is enabled but SHIBLI_SIGN_PFX_BASE64 (or SHIBLI_SIGN_PFX) is missing. Refusing unsigned 'signed' release."
    }
    if ([string]::IsNullOrWhiteSpace($password)) {
        throw "Signing is enabled but SHIBLI_SIGN_PFX_PASSWORD is missing. Refusing unsigned 'signed' release."
    }
    if ([string]::IsNullOrWhiteSpace($rootB64) -and [string]::IsNullOrWhiteSpace($rootPath)) {
        throw "Signing is enabled but SHIBLI_SIGN_ROOT_CERT_BASE64 is missing. Refusing unsigned 'signed' release."
    }
}

function Resolve-ShibliPfxPath {
    $pfx = [string]$env:SHIBLI_SIGN_PFX
    if (-not [string]::IsNullOrWhiteSpace($pfx)) {
        if (-not (Test-Path $pfx)) {
            throw "SHIBLI_SIGN_PFX does not exist: $pfx"
        }
        return (Resolve-Path $pfx).Path
    }
    $b64 = [string]$env:SHIBLI_SIGN_PFX_BASE64
    if ([string]::IsNullOrWhiteSpace($b64)) {
        return $null
    }
    $dest = Get-ShibliSignTempPath "shibli-codesign.pfx"
    Write-Host "Decoding PFX"
    $bytes = [Convert]::FromBase64String($b64.Trim())
    Write-Host "Writing temporary PFX"
    [System.IO.File]::WriteAllBytes($dest, $bytes)
    $env:SHIBLI_SIGN_PFX = $dest
    return $dest
}

function Resolve-ShibliRootCertPath {
    $cer = [string]$env:SHIBLI_SIGN_ROOT_CERT_PATH
    if (-not [string]::IsNullOrWhiteSpace($cer) -and (Test-Path $cer)) {
        return (Resolve-Path $cer).Path
    }
    $b64 = [string]$env:SHIBLI_SIGN_ROOT_CERT_BASE64
    if ([string]::IsNullOrWhiteSpace($b64)) {
        throw "Signing is enabled but SHIBLI_SIGN_ROOT_CERT_BASE64 is missing. Refusing unsigned 'signed' release."
    }
    $cer = Get-ShibliSignTempPath "shibli-internal-root.cer"
    Write-Host "Decoding public root"
    $bytes = [Convert]::FromBase64String($b64.Trim())
    Write-Host "Writing temporary root"
    [System.IO.File]::WriteAllBytes($cer, $bytes)
    $env:SHIBLI_SIGN_ROOT_CERT_PATH = $cer
    return $cer
}

function Get-ShibliPublicRootCertificate {
    $cer = Resolve-ShibliRootCertPath
    $cert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($cer)
    if ($cert.HasPrivateKey) {
        $cert.Dispose()
        throw "SHIBLI_SIGN_ROOT_CERT_BASE64 must be the PUBLIC root certificate only. Private root key is never required and must not be present."
    }
    if ($cert.Subject -notlike "*$($script:ShibliInternalRootCn)*") {
        $cert.Dispose()
        throw "Public root certificate subject is not CN=$($script:ShibliInternalRootCn)."
    }
    $env:SHIBLI_SIGN_ROOT_THUMBPRINT = $cert.Thumbprint
    return $cert
}

function Initialize-ShibliSigning {
    if (-not (Test-ShibliSignEnabled)) {
        Write-Host "Authenticode signing disabled for this run."
        return
    }
    Assert-ShibliSigningSecrets
    $rootCert = $null
    try {
        $pfx = Resolve-ShibliPfxPath
        if (-not $pfx) {
            throw "Signing is enabled but the PFX could not be materialized."
        }
        $null = Resolve-ShibliRootCertPath
        $rootCert = Get-ShibliPublicRootCertificate
        if ($env:GITHUB_ENV) {
            Add-Content -Path $env:GITHUB_ENV -Value "SHIBLI_SIGN_ENABLED=true"
            Add-Content -Path $env:GITHUB_ENV -Value "SHIBLI_SIGN_PFX=$pfx"
            Add-Content -Path $env:GITHUB_ENV -Value "SHIBLI_SIGN_ROOT_CERT_PATH=$($env:SHIBLI_SIGN_ROOT_CERT_PATH)"
            if ($env:SHIBLI_SIGN_ROOT_THUMBPRINT) {
                Add-Content -Path $env:GITHUB_ENV -Value "SHIBLI_SIGN_ROOT_THUMBPRINT=$($env:SHIBLI_SIGN_ROOT_THUMBPRINT)"
            }
        }
        Write-Host "Signing material initialization complete"
    } finally {
        if ($null -ne $rootCert) {
            $rootCert.Dispose()
        }
    }
}

function Import-ShibliInternalRoot {
    # Workflow compatibility: materialize the public root CER only. Does not
    # change any Windows trust store.
    if (-not (Test-ShibliSignEnabled)) {
        return
    }
    $rootCert = $null
    try {
        $null = Resolve-ShibliRootCertPath
        $rootCert = Get-ShibliPublicRootCertificate
    } finally {
        if ($null -ne $rootCert) {
            $rootCert.Dispose()
        }
    }
}

function Clear-ShibliSignMaterial {
    $candidates = @(
        [string]$env:SHIBLI_SIGN_PFX,
        [string]$env:SHIBLI_SIGN_ROOT_CERT_PATH,
        (Get-ShibliSignTempPath "shibli-codesign.pfx"),
        (Get-ShibliSignTempPath "shibli-internal-root.cer")
    )
    foreach ($path in $candidates) {
        if ([string]::IsNullOrWhiteSpace($path)) { continue }
        if (Test-Path $path) {
            Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
        }
    }
}

function Invoke-ShibliAuthenticode {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )
    if (-not (Test-ShibliSignEnabled)) {
        Write-Host "Authenticode signing skipped for $Path (SHIBLI_SIGN_ENABLED is not set)."
        return
    }
    if (-not (Test-Path $Path)) {
        throw "Cannot sign missing file: $Path"
    }
    Assert-ShibliSigningSecrets

    $signTool = Get-ShibliSignTool
    $timestamp = Get-ShibliTimestampUrl
    $pfx = Resolve-ShibliPfxPath
    $password = [string]$env:SHIBLI_SIGN_PFX_PASSWORD
    if (-not $pfx) {
        throw "Signing is enabled but SHIBLI_SIGN_PFX_BASE64 (or SHIBLI_SIGN_PFX) is missing. Refusing unsigned 'signed' release."
    }
    if ([string]::IsNullOrWhiteSpace($password)) {
        throw "Signing is enabled but SHIBLI_SIGN_PFX_PASSWORD is missing. Refusing unsigned 'signed' release."
    }

    $signArgs = @(
        "sign",
        "/fd", "SHA256",
        "/td", "SHA256",
        "/tr", $timestamp,
        "/f", $pfx,
        "/p", $password
    )

    Write-Host "Signing $Path"
    & $signTool @signArgs $Path
    if ($LASTEXITCODE -ne 0) {
        throw "signtool sign failed for $Path with exit code $LASTEXITCODE"
    }
    Assert-ShibliAuthenticode -Path $Path
}

function Test-ShibliCodeSigningEku {
    param(
        [Parameter(Mandatory = $true)]
        [System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate
    )
    foreach ($ext in $Certificate.Extensions) {
        if ($ext.Oid.Value -ne "2.5.29.37") {
            continue
        }
        $eku = [System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]$ext
        foreach ($oid in $eku.EnhancedKeyUsages) {
            if ($oid.Value -eq $script:ShibliCodeSigningEkuOid) {
                return
            }
        }
    }
    throw "Signer certificate EKU does not permit Code Signing."
}

function Test-ShibliChainsToInternalRoot {
    param(
        [Parameter(Mandatory = $true)]
        [System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate
    )
    $rootCert = $null
    $chain = $null
    try {
        $rootCert = Get-ShibliPublicRootCertificate
        $chain = [System.Security.Cryptography.X509Certificates.X509Chain]::new()
        $chain.ChainPolicy.TrustMode = [System.Security.Cryptography.X509Certificates.X509ChainTrustMode]::CustomRootTrust
        $customTrust = $chain.ChainPolicy.CustomTrustStore
        $customTrust.Add($rootCert)
        $chain.ChainPolicy.RevocationMode = [System.Security.Cryptography.X509Certificates.X509RevocationMode]::NoCheck
        $built = $chain.Build($Certificate)
        if (-not $built) {
            throw "CustomRootTrust chain.Build returned false for the Authenticode signer."
        }
        $chainRoot = $chain.ChainElements[$chain.ChainElements.Count - 1].Certificate
        if ($chainRoot.Thumbprint -ne $rootCert.Thumbprint) {
            throw "Chain root thumbprint does not match the supplied SHIBLI public root."
        }
        if ($chainRoot.Subject -notlike "*$($script:ShibliInternalRootCn)*") {
            throw "Chain root subject is not CN=$($script:ShibliInternalRootCn)."
        }
        if ($Certificate.Subject -notlike "*$($script:ShibliCodeSigningCn)*") {
            throw "Signer certificate is not CN=$($script:ShibliCodeSigningCn)."
        }
        Test-ShibliCodeSigningEku -Certificate $Certificate
    } finally {
        if ($null -ne $chain) {
            $chain.Dispose()
        }
        if ($null -ne $rootCert) {
            $rootCert.Dispose()
        }
    }
}

function Assert-ShibliAuthenticode {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )
    if (-not (Test-ShibliSignEnabled)) {
        return
    }
    $sig = Get-AuthenticodeSignature -FilePath $Path
    if ($null -eq $sig.SignerCertificate) {
        throw "Authenticode verification failed for $Path (SignerCertificate is null)."
    }
    if ($sig.Status -eq "NotSigned") {
        throw "Authenticode verification failed for $Path (NotSigned)."
    }
    if ($sig.Status -eq "HashMismatch") {
        throw "Authenticode verification failed for $Path (HashMismatch)."
    }
    Test-ShibliChainsToInternalRoot -Certificate $sig.SignerCertificate
    Write-Host "Verified Authenticode signature on $Path (custom-root chain; Windows Status=$($sig.Status) is not required to be Valid)."
}
