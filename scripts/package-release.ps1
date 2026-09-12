# Create clean deployment zip (no venv/build) for Ubuntu or Windows source
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Out = Join-Path (Split-Path -Parent $ProjectRoot) "ShibliC2-phase1.zip"

$items = @(
    "app", "static", "scripts", "deploy",
    "launcher.py", "requirements.txt",
    "config.example.json", ".env.example", "go2rtc.yaml.example",
    "README.md", "ARCHITECTURE.md", "DEPLOYMENT.md", "DATABASE.md",
    "CAMERA_INTEGRATION_CHECKLIST.md",
    "ShibliC2.spec", "build.ps1", ".gitignore"
)

$staging = Join-Path $env:TEMP "ShibliC2-staging"
if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
$dest = Join-Path $staging "ShibliC2"
New-Item -ItemType Directory -Path $dest -Force | Out-Null

foreach ($item in $items) {
    $src = Join-Path $ProjectRoot $item
    if (Test-Path $src) {
        Copy-Item $src (Join-Path $dest $item) -Recurse -Force
    }
}

if (Test-Path $Out) { Remove-Item $Out -Force }
Compress-Archive -Path $dest -DestinationPath $Out -Force
Remove-Item $staging -Recurse -Force

Write-Host "Created: $Out" -ForegroundColor Green
Write-Host "Ubuntu: unzip ShibliC2-phase1.zip && cd ShibliC2 && chmod +x scripts/*.sh && ./scripts/install-ubuntu.sh" -ForegroundColor Cyan
