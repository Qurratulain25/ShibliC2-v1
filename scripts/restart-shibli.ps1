# Restart SHIBLI C2 (Windows) - stop port 8080, start, verify health
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if ($Root -match "scripts$") { $Root = Split-Path -Parent $Root }
Set-Location $Root

Write-Host "=== SHIBLI C2 Restart ===" -ForegroundColor Cyan

$existing = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
if ($existing) {
  $existing | ForEach-Object {
    Write-Host "Stopping PID $($_.OwningProcess) on port 8080..." -ForegroundColor Yellow
    Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
  }
  Start-Sleep -Seconds 2
}

$still = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
if ($still) {
  $procId = ($still | Select-Object -First 1).OwningProcess
  Write-Host "ERROR: Port 8080 still in use by PID $procId" -ForegroundColor Red
  exit 1
}

Remove-Item Env:SHIBLI_DATA_DIR -ErrorAction SilentlyContinue
$env:SHIBLI_NO_BROWSER = "1"

& .\.venv\Scripts\python.exe -c @"
from app.core.database import db_info
print('DB:', db_info()['path'])
print('Encrypted:', db_info()['encrypted'])
"@

Write-Host "Starting launcher..." -ForegroundColor Green
Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "launcher.py" -WorkingDirectory $Root -WindowStyle Normal

$ok = $false
for ($i = 0; $i -lt 40; $i++) {
  Start-Sleep -Milliseconds 500
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8080/api/health" -UseBasicParsing -TimeoutSec 2
    if ($r.StatusCode -eq 200) { $ok = $true; break }
  } catch { }
}
if ($ok) {
  Write-Host "SHIBLI C2 is running at http://127.0.0.1:8080" -ForegroundColor Green
} else {
  Write-Host "Launcher started - waiting for bind. Open http://127.0.0.1:8080 when ready." -ForegroundColor Yellow
}
