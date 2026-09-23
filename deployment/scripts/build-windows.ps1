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

$PinsFile = Join-Path $Root "deployment\runtime\pins.json"
if (-not (Test-Path $PinsFile)) { Fail "deployment/runtime/pins.json is required." }
$Pins = Get-Content $PinsFile -Raw | ConvertFrom-Json

function Assert-Sha256([string]$Path, [string]$Expected) {
    $name = Split-Path $Path -Leaf
    if ([string]::IsNullOrWhiteSpace($Expected)) {
        Fail "Missing required SHA256 pin for $name"
    }
    if (-not (Test-Path $Path)) {
        Fail "Cannot verify SHA256; missing file $name"
    }
    $actual = (Get-FileHash $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $Expected.Trim().ToLowerInvariant()) {
        Fail "SHA256 mismatch for $name"
    }
}

function Get-PinnedFile([string]$Url, [string]$Dest, [string]$Expected) {
    $name = Split-Path $Dest -Leaf
    if ([string]::IsNullOrWhiteSpace($Url)) {
        Fail "Missing download URL pin for $name"
    }
    if (-not (Test-Path $Dest)) {
        Write-Host "Downloading build-time sidecar $name"
        Invoke-WebRequest -Uri $Url -OutFile $Dest
    }
    if (-not (Test-Path $Dest)) {
        Fail "Download failed for $name"
    }
    Assert-Sha256 $Dest $Expected
}

function Require-File([string]$Path, [string]$Reason) {
    if (-not (Test-Path $Path)) { Fail $Reason }
}

# Pinned Windows sidecars — build machine only, never downloaded on the client.
$Go2rtcZip = Join-Path $Runtime "go2rtc_win64.zip"
$Go2rtcExe = Join-Path $Runtime "go2rtc.exe"
Get-PinnedFile $Pins.go2rtc.win64_url $Go2rtcZip $Pins.go2rtc.win64_sha256
Expand-Archive -Path $Go2rtcZip -DestinationPath $Runtime -Force
Require-File $Go2rtcExe "go2rtc.exe is required in deployment/runtime/windows after extracting the verified archive."

$FfmpegZip = Join-Path $Runtime "ffmpeg-7.1.1-essentials_build.zip"
$FfmpegExe = Join-Path $Runtime "ffmpeg.exe"
Get-PinnedFile $Pins.ffmpeg.windows_url $FfmpegZip $Pins.ffmpeg.windows_sha256
$ffOut = Join-Path $Runtime "ffmpeg-extract"
if (Test-Path $ffOut) { Remove-Item $ffOut -Recurse -Force }
Expand-Archive -Path $FfmpegZip -DestinationPath $ffOut -Force
$found = Get-ChildItem $ffOut -Recurse -Filter ffmpeg.exe | Select-Object -First 1
if (-not $found) { Fail "ffmpeg.exe not found in the downloaded archive" }
Copy-Item $found.FullName $FfmpegExe -Force
Require-File $FfmpegExe "ffmpeg.exe is required in deployment/runtime/windows after extracting the verified archive."

$WebView2 = Join-Path $Runtime "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
Get-PinnedFile $Pins.webview2.windows_url $WebView2 $Pins.webview2.windows_sha256
Require-File $WebView2 "Offline WebView2 installer is required in deployment/runtime/windows."

$VcRedist = Join-Path $Runtime "vc_redist.x64.exe"
Get-PinnedFile $Pins.vc_redist.windows_url $VcRedist $Pins.vc_redist.windows_sha256
Require-File $VcRedist "Offline VC++ Redistributable is required in deployment/runtime/windows."

& $Py -m pip install -q -r (Join-Path $Root "requirements.txt") "pywebview==5.4" "pyinstaller==6.11.1"
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
& $CtrlPy -m pip install -q "pyinstaller==6.11.1"
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

Require-File $Go2rtcExe "Refusing Inno Setup packaging: missing deployment/runtime/windows/go2rtc.exe"
Require-File $FfmpegExe "Refusing Inno Setup packaging: missing deployment/runtime/windows/ffmpeg.exe"
Require-File $WebView2 "Refusing Inno Setup packaging: missing deployment/runtime/windows/MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
Require-File $VcRedist "Refusing Inno Setup packaging: missing deployment/runtime/windows/vc_redist.x64.exe"
Require-File (Join-Path $Root "dist\ShibliC2\ShibliC2.exe") "Refusing Inno Setup packaging: missing dist/ShibliC2/ShibliC2.exe"
Require-File (Join-Path $Root "dist\ShibliControls\ShibliControls.exe") "Refusing Inno Setup packaging: missing dist/ShibliControls/ShibliControls.exe"

$Out = Join-Path $Root "release\v1.0"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$Iss = Join-Path $Root "deployment\windows\installer\shibli-c2.iss"
& $Inno.Source $Iss
if ($LASTEXITCODE -ne 0) {
    Fail "Inno Setup compiler failed with exit code $LASTEXITCODE"
}
$Setup = Join-Path $Out "ShibliC2-Setup-v1.0.exe"
Require-File $Setup "Installer was not created: $Setup"
$SetupHash = (Get-FileHash $Setup -Algorithm SHA256).Hash.ToLowerInvariant()
$Sums = Join-Path $Out "SHA256SUMS-windows.txt"
Set-Content -Path $Sums -Value "$SetupHash  ShibliC2-Setup-v1.0.exe" -Encoding ascii
Require-File $Sums "SHA256SUMS-windows.txt was not created: $Sums"
Write-Host "Built $Setup"
Write-Host "SHA256SUMS-windows.txt $SetupHash"
