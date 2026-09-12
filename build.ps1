$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
}

.\.venv\Scripts\pip install -r requirements.txt -q
.\.venv\Scripts\pyinstaller --noconfirm ShibliC2.spec

Write-Host ""
Write-Host "Build complete: $Root\dist\ShibliC2.exe" -ForegroundColor Green
Write-Host "Deploy by copying only dist\ShibliC2.exe to the target machine." -ForegroundColor Cyan
