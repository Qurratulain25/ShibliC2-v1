# Phase 1 verification — run from ShibliC2 folder
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if ($Root -match "scripts$") { $Root = Split-Path -Parent $Root }
Set-Location $Root
& (Join-Path $Root ".venv\Scripts\python.exe") (Join-Path $Root "scripts\verify_phase1.py")
exit $LASTEXITCODE
