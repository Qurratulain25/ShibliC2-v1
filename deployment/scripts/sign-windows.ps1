#Requires -Version 5.1
# Authenticode signing for SHIBLI C2 Windows artifacts.
# Certificates and private keys must NEVER be committed to git.
#
# Enable with SHIBLI_SIGN_ENABLED=true and one of:
#   SHIBLI_SIGN_PFX              path to .pfx/.p12
#   SHIBLI_SIGN_PFX_BASE64       base64-encoded PFX (CI secret)
#   SHIBLI_SIGN_CERT_THUMBPRINT  certificate already in the Windows cert store
#   SHIBLI_SIGN_CERT_SHA1        alias for thumbprint
# Optional:
#   SHIBLI_SIGN_PFX_PASSWORD
#   SHIBLI_SIGN_TIMESTAMP_URL    default http://timestamp.digicert.com
#   SHIBLI_SIGN_SUBJECT          optional subject filter for store certs
#
# When signing is disabled this is a no-op so unsigned CI can still build.
# When signing is enabled, missing material or a failed verification is fatal.

$ErrorActionPreference = "Stop"

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
    $dest = Join-Path ([System.IO.Path]::GetTempPath()) "shibli-codesign.pfx"
    $bytes = [Convert]::FromBase64String($b64.Trim())
    [System.IO.File]::WriteAllBytes($dest, $bytes)
    return $dest
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

    $signTool = Get-ShibliSignTool
    $timestamp = Get-ShibliTimestampUrl
    $pfx = Resolve-ShibliPfxPath
    $thumb = [string]$env:SHIBLI_SIGN_CERT_THUMBPRINT
    if ([string]::IsNullOrWhiteSpace($thumb)) {
        $thumb = [string]$env:SHIBLI_SIGN_CERT_SHA1
    }
    $password = [string]$env:SHIBLI_SIGN_PFX_PASSWORD

    $args = @(
        "sign",
        "/fd", "SHA256",
        "/td", "SHA256",
        "/tr", $timestamp,
        "/v"
    )
    if ($pfx) {
        $args += @("/f", $pfx)
        if (-not [string]::IsNullOrWhiteSpace($password)) {
            $args += @("/p", $password)
        }
    } elseif (-not [string]::IsNullOrWhiteSpace($thumb)) {
        $args += @("/sha1", $thumb.Trim())
    } else {
        throw "Signing is enabled but no certificate was provided. Set SHIBLI_SIGN_PFX, SHIBLI_SIGN_PFX_BASE64, or SHIBLI_SIGN_CERT_THUMBPRINT."
    }

    Write-Host "Signing $Path"
    & $signTool @args $Path
    if ($LASTEXITCODE -ne 0) {
        throw "signtool sign failed for $Path with exit code $LASTEXITCODE"
    }
    Assert-ShibliAuthenticode -Path $Path
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
    Write-Host "Verified Authenticode signature on $Path ($($sig.SignerCertificate.Subject))"
}
