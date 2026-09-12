#Requires -Version 5.1
# Build ShibliC2-Setup-v1.0.exe on a Windows build host. Never packages live data.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path (Join-Path $Root "launcher.py"))) {
    $Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}
Set-Location $Root

function Fail([string]$Message) {
    Write-Error $Message
    exit 1
}

$Inno = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
if (-not $Inno) {
    $guess = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if (Test-Path $guess) { $Inno = @{ Source = $guess } }
}
if (-not $Inno) { Fail "Inno Setup 6 (ISCC.exe) is required. This script does not invent an .exe." }

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }

& $Py (Join-Path $Root "deployment\scripts\generate-icons.py")

$Runtime = Join-Path $Root "deployment\runtime\windows"
New-Item -ItemType Directory -Force -Path $Runtime | Out-Null

function Get-FileIfMissing([string]$Url, [string]$Dest) {
    if (Test-Path $Dest) { return }
    Write-Host "Downloading build-time sidecar $(Split-Path $Dest -Leaf)"
    Invoke-WebRequest -Uri $Url -OutFile $Dest
}

# Pinned go2rtc 1.9.14 — build machine only, never at client runtime.
$Pins = Get-Content (Join-Path $Root "deployment\runtime\pins.json") -Raw | ConvertFrom-Json
function Assert-Sha256([string]$Path, [string]$Expected) {
    if (-not $Expected) { return }
    $actual = (Get-FileHash $Path -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $Expected.ToLower()) { Fail "SHA256 mismatch for $(Split-Path $Path -Leaf)" }
}
$Go2rtcZip = Join-Path $Runtime "go2rtc_win64.zip"
if (-not (Test-Path (Join-Path $Runtime "go2rtc.exe"))) {
    Get-FileIfMissing $Pins.go2rtc.win64_url $Go2rtcZip
    Assert-Sha256 $Go2rtcZip $Pins.go2rtc.win64_sha256
    Expand-Archive -Path $Go2rtcZip -DestinationPath $Runtime -Force
}
if (-not (Test-Path (Join-Path $Runtime "go2rtc.exe"))) {
    Fail "go2rtc.exe is required in deployment/runtime/windows (download at build time, not client runtime)."
}

$FfmpegZip = Join-Path $Runtime "ffmpeg-7.1.1-essentials_build.zip"
if (-not (Test-Path (Join-Path $Runtime "ffmpeg.exe"))) {
    Get-FileIfMissing $Pins.ffmpeg.windows_url $FfmpegZip
    Assert-Sha256 $FfmpegZip $Pins.ffmpeg.windows_sha256
    $ffOut = Join-Path $Runtime "ffmpeg-extract"
    if (Test-Path $ffOut) { Remove-Item $ffOut -Recurse -Force }
    Expand-Archive -Path $FfmpegZip -DestinationPath $ffOut -Force
    $found = Get-ChildItem $ffOut -Recurse -Filter ffmpeg.exe | Select-Object -First 1
    if (-not $found) { Fail "ffmpeg.exe not found in the downloaded archive" }
    Copy-Item $found.FullName (Join-Path $Runtime "ffmpeg.exe")
}

# Offline WebView2 Evergreen Standalone (no internet on the client).
$WebView2 = Join-Path $Runtime "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
if (-not (Test-Path $WebView2)) {
    Get-FileIfMissing "https://go.microsoft.com/fwlink/?linkid=2124701" $WebView2
}
if (-not (Test-Path $WebView2)) {
    Fail "Offline WebView2 installer is required in deployment/runtime/windows."
}
$VcRedist = Join-Path $Runtime "vc_redist.x64.exe"
if (-not (Test-Path $VcRedist)) {
    Get-FileIfMissing "https://aka.ms/vs/17/release/vc_redist.x64.exe" $VcRedist
}

& $Py -m pip install -q -r (Join-Path $Root "requirements.txt") "pywebview==5.4" pyinstaller
& $Py -m PyInstaller --noconfirm --distpath (Join-Path $Root "dist") --workpath (Join-Path $Root "build") (Join-Path $Root "ShibliC2.spec")
if (-not (Test-Path (Join-Path $Root "dist\ShibliC2\ShibliC2.exe"))) {
    Fail "PyInstaller did not produce dist\ShibliC2\ShibliC2.exe"
}

$ControlsDir = $env:SHIBLI_CONTROLS_SOURCE
if (-not $ControlsDir) { $ControlsDir = Join-Path $Root "deployment\runtime\controls" }
if (-not (Test-Path (Join-Path $ControlsDir "server.py"))) {
    Fail "SHIBLI-controls source missing. Populate deployment/runtime/controls or set SHIBLI_CONTROLS_SOURCE."
}
$Src = Join-Path $env:TEMP "shibli-controls-src"
if (Test-Path $Src) { Remove-Item $Src -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Src | Out-Null
robocopy $ControlsDir $Src /E /XD venv venv_old .venv data logs __pycache__ .git /XF .env /NFL /NDL /NJH /NJS | Out-Null
$CtrlVenv = Join-Path $env:TEMP "shibli-controls-venv"
if (-not (Test-Path (Join-Path $CtrlVenv "Scripts\python.exe"))) {
    & $Py -m venv $CtrlVenv
}
$CtrlPy = Join-Path $CtrlVenv "Scripts\python.exe"
& $CtrlPy -m pip install -q pyinstaller
if (Test-Path (Join-Path $ControlsDir "requirements.txt")) {
    & $CtrlPy -m pip install -q -r (Join-Path $ControlsDir "requirements.txt")
}
$env:SHIBLI_CONTROLS_SRC = $Src
& $CtrlPy -m PyInstaller --noconfirm --distpath (Join-Path $Root "dist") --workpath (Join-Path $Root "build") (Join-Path $Root "deployment\scripts\ShibliControls.spec")
Remove-Item Env:SHIBLI_CONTROLS_SRC -ErrorAction SilentlyContinue
if (-not (Test-Path (Join-Path $Root "dist\ShibliControls\ShibliControls.exe"))) {
    Fail "SHIBLI-controls freeze failed. Refusing to ship without hardware controls."
}

& $Py (Join-Path $Root "deployment\scripts\write_runtime_manifest.py")

$Out = Join-Path $Root "release\v1.0"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$Iss = Join-Path $Root "deployment\windows\installer\shibli-c2.iss"
& $Inno.Source $Iss
$Setup = Join-Path $Out "ShibliC2-Setup-v1.0.exe"
if (-not (Test-Path $Setup)) { Fail "Installer was not created: $Setup" }
Write-Host "Built $Setup"
