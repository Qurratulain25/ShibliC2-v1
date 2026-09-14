#Requires -Version 5.1
# Fail the Windows freeze if SQLCipher native files are missing from dist.
# Does not print secrets. Safe to run on a clean build agent.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path (Join-Path $Root "launcher.py"))) {
    $Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

$Internal = Join-Path $Root "dist\ShibliC2\_internal"
if (-not (Test-Path $Internal)) {
    throw "Frozen tree missing: dist\ShibliC2\_internal"
}

$SqlDir = Join-Path $Internal "sqlcipher3"
$Pyds = @()
if (Test-Path $SqlDir) {
    $Pyds = @(Get-ChildItem -Path $SqlDir -Filter "_sqlite3*.pyd" -ErrorAction SilentlyContinue)
}
if ($Pyds.Count -eq 0) {
    $Pyds = @(Get-ChildItem -Path $Internal -Recurse -Filter "_sqlite3*.pyd" -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "sqlcipher3" })
}
if ($Pyds.Count -eq 0) {
    throw "SQLCipher native extension missing (sqlcipher3/_sqlite3*.pyd). Refusing to package."
}

$StdPyd = Join-Path $Internal "_sqlite3.pyd"
$StdDll = Join-Path $Internal "sqlite3.dll"
Write-Host "SQLCipher pyd: $($Pyds[0].FullName)"
if (Test-Path $StdPyd) {
    Write-Host "CPython _sqlite3.pyd is also present (plaintext-detection only)."
}
if (Test-Path $StdDll) {
    Write-Host "CPython sqlite3.dll is present; runtime hook must load sqlcipher3 first."
}

$Dumpbin = Get-Command "dumpbin.exe" -ErrorAction SilentlyContinue
if (-not $Dumpbin) {
    $kits = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
    if (Test-Path $kits) {
        $found = Get-ChildItem -Path $kits -Recurse -Filter "dumpbin.exe" -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match "\\x64\\dumpbin\.exe$" } |
            Select-Object -First 1
        if ($found) { $Dumpbin = $found }
    }
}
if ($Dumpbin) {
    $dumpPath = if ($Dumpbin.Source) { $Dumpbin.Source } else { $Dumpbin.FullName }
    $deps = & $dumpPath /DEPENDENTS $Pyds[0].FullName 2>$null | Out-String
    Write-Host "SQLCipher pyd dependents:"
    $deps -split "`r?`n" | Where-Object { $_ -match "\.dll" } | ForEach-Object { Write-Host "  $_" }
    if ($deps -match "sqlite3\.dll" -and -not (Test-Path (Join-Path $SqlDir "sqlite3.dll"))) {
        throw "SQLCipher pyd dynamically links sqlite3.dll but sqlcipher3\sqlite3.dll is missing. Vanilla _internal\sqlite3.dll would be loaded instead."
    }
} else {
    Write-Host "dumpbin.exe not available; skipped DLL-dependency inspection."
}

$Crypto = @(Get-ChildItem -Path $Internal -Filter "libcrypto*.dll" -ErrorAction SilentlyContinue)
$Ssl = @(Get-ChildItem -Path $Internal -Filter "libssl*.dll" -ErrorAction SilentlyContinue)
if ($Crypto.Count -eq 0) {
    Write-Host "WARNING: libcrypto*.dll not found next to the frozen app. SQLCipher may still be statically linked."
} else {
    Write-Host "Found $($Crypto[0].Name)"
}
if ($Ssl.Count -gt 0) {
    Write-Host "Found $($Ssl[0].Name)"
}

Write-Host "SQLCipher Windows packaging audit passed."
