#!/usr/bin/env bash
# Create a clean tarball for Ubuntu deployment (no venv/build)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAME="ShibliC2-phase1"
OUT="$ROOT/../${NAME}.tar.gz"

tar -czf "$OUT" \
  --exclude='.venv' \
  --exclude='build' \
  --exclude='dist' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  -C "$(dirname "$ROOT")" \
  "$(basename "$ROOT")/app" \
  "$(basename "$ROOT")/static" \
  "$(basename "$ROOT")/scripts" \
  "$(basename "$ROOT")/deploy" \
  "$(basename "$ROOT")/launcher.py" \
  "$(basename "$ROOT")/requirements.txt" \
  "$(basename "$ROOT")/config.example.json" \
  "$(basename "$ROOT")/.env.example" \
  "$(basename "$ROOT")/go2rtc.yaml.example" \
  "$(basename "$ROOT")/README.md" \
  "$(basename "$ROOT")/ARCHITECTURE.md" \
  "$(basename "$ROOT")/DEPLOYMENT.md" \
  "$(basename "$ROOT")/DATABASE.md" \
  "$(basename "$ROOT")/CAMERA_INTEGRATION_CHECKLIST.md" \
  "$(basename "$ROOT")/ShibliC2.spec" \
  "$(basename "$ROOT")/build.ps1"

echo "Created: $OUT"
echo "On Ubuntu: tar -xzf ${NAME}.tar.gz && cd ShibliC2 && ./scripts/install-ubuntu.sh"
