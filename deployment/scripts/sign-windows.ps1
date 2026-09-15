#Requires -Version 5.1
# Authenticode signing for SHIBLI C2 Windows artifacts.
# Certificates and private keys must NEVER be committed to git.
#
# Internal SHIBLI PKI (not trusted by arbitrary Windows PCs):
#   Root (PUBLIC only): CN=SHIBLI C2 Internal Root CA
#   Leaf:               CN=SHIBLI C2 Code Signing  EKU=Code Signing
# Client/QA machines must explicitly trust the public root CA.
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

function Import-ShibliInternalRoot {
    if (-not (Test-ShibliSignEnabled)) {
        return
    }
    $cert = $null
    $store = $null
    try {
        $cer = [string]$env:SHIBLI_SIGN_ROOT_CERT_PATH
        if ([string]::IsNullOrWhiteSpace($cer) -or -not (Test-Path $cer)) {
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
        }
        $cert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($cer)
        if ($cert.HasPrivateKey) {
            throw "SHIBLI_SIGN_ROOT_CERT_BASE64 must be the PUBLIC root certificate only. Private root key is never required and must not be present."
        }
        if ($cert.Subject -notlike "*$($script:ShibliInternalRootCn)*") {
            throw "Imported root certificate subject is not CN=$($script:ShibliInternalRootCn)."
        }
        $env:SHIBLI_SIGN_ROOT_THUMBPRINT = $cert.Thumbprint

        Write-Host "Opening CurrentUser Root store"
        $store = [System.Security.Cryptography.X509Certificates.X509Store]::new(
            [System.Security.Cryptography.X509Certificates.StoreName]::Root,
            [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
        )
        $store.Open(
            [System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite
        )
        $already = $store.Certificates.Find(
            [System.Security.Cryptography.X509Certificates.X509FindType]::FindByThumbprint,
            $cert.Thumbprint,
            $false
        )
        if ($already.Count -gt 0) {
            Write-Host "Root certificate already present in CurrentUser Root store; skipping add"
        } else {
            Write-Host "Adding root certificate"
            $store.Add($cert)
        }
        Write-Host "Root import complete"
        Write-Host "Imported SHIBLI public root CA into CurrentUser Root for this runner only. Arbitrary client PCs will not trust it until they import the same public root."
    } finally {
        if ($null -ne $store) {
            $store.Close()
            $store.Dispose()
        }
        if ($null -ne $cert) {
            $cert.Dispose()
        }
    }
}

function Initialize-ShibliSigning {
    if (-not (Test-ShibliSignEnabled)) {
        Write-Host "Authenticode signing disabled for this run."
        return
    }
    Assert-ShibliSigningSecrets
    $pfx = Resolve-ShibliPfxPath
    if (-not $pfx) {
        throw "Signing is enabled but the PFX could not be materialized."
    }
    Import-ShibliInternalRoot
    if ($env:GITHUB_ENV) {
        Add-Content -Path $env:GITHUB_ENV -Value "SHIBLI_SIGN_ENABLED=true"
        Add-Content -Path $env:GITHUB_ENV -Value "SHIBLI_SIGN_PFX=$pfx"
        if ($env:SHIBLI_SIGN_ROOT_CERT_PATH) {
            Add-Content -Path $env:GITHUB_ENV -Value "SHIBLI_SIGN_ROOT_CERT_PATH=$($env:SHIBLI_SIGN_ROOT_CERT_PATH)"
        }
        if ($env:SHIBLI_SIGN_ROOT_THUMBPRINT) {
            Add-Content -Path $env:GITHUB_ENV -Value "SHIBLI_SIGN_ROOT_THUMBPRINT=$($env:SHIBLI_SIGN_ROOT_THUMBPRINT)"
        }
    }
    Write-Host "Signing material initialization complete"
}

function Remove-ShibliInternalRootFromCurrentUserStore {
    $thumb = [string]$env:SHIBLI_SIGN_ROOT_THUMBPRINT
    if ([string]::IsNullOrWhiteSpace($thumb)) {
        return
    }
    $store = $null
    try {
        Write-Host "Opening CurrentUser Root store to remove CI-imported root by thumbprint"
        $store = [System.Security.Cryptography.X509Certificates.X509Store]::new(
            [System.Security.Cryptography.X509Certificates.StoreName]::Root,
            [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
        )
        $store.Open(
            [System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite
        )
        $matches = $store.Certificates.Find(
            [System.Security.Cryptography.X509Certificates.X509FindType]::FindByThumbprint,
            $thumb,
            $false
        )
        foreach ($item in $matches) {
            $store.Remove($item)
            $item.Dispose()
        }
        if ($matches.Count -gt 0) {
            Write-Host "Removed CI-imported SHIBLI public root from CurrentUser Root store"
        }
    } catch {
        Write-Host "Could not remove CI-imported root from CurrentUser Root store; temporary files are still deleted."
    } finally {
        if ($null -ne $store) {
            $store.Close()
            $store.Dispose()
        }
    }
}

function Clear-ShibliSignMaterial {
    Remove-ShibliInternalRootFromCurrentUserStore
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

function Test-ShibliChainsToInternalRoot {
    param(
        [Parameter(Mandatory = $true)]
        [System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate
    )
    $rootCn = $script:ShibliInternalRootCn
    if ($Certificate.Issuer -like "*$rootCn*") {
        return
    }
    $chain = New-Object System.Security.Cryptography.X509Certificates.X509Chain
    $chain.ChainPolicy.RevocationMode = [System.Security.Cryptography.X509Certificates.X509RevocationMode]::NoCheck
    [void]$chain.Build($Certificate)
    foreach ($element in $chain.ChainElements) {
        if ($element.Certificate.Subject -like "*$rootCn*") {
            return
        }
        if ($element.Certificate.Issuer -like "*$rootCn*") {
            return
        }
    }
    throw "Signing certificate does not chain to $rootCn."
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
    if ($sig.Status -ne "Valid") {
        throw "Authenticode verification failed for $Path (status=$($sig.Status) $($sig.StatusMessage))"
    }
    if (-not $sig.SignerCertificate) {
        throw "Authenticode signature on $Path has no signer certificate"
    }
    Test-ShibliChainsToInternalRoot -Certificate $sig.SignerCertificate
    if ($sig.SignerCertificate.Subject -notlike "*$($script:ShibliCodeSigningCn)*") {
        throw "Signer certificate is not CN=$($script:ShibliCodeSigningCn)."
    }
    Write-Host "Verified Authenticode signature on $Path (Status=Valid; chains to $($script:ShibliInternalRootCn))"
}
