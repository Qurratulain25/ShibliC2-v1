#!/usr/bin/env bash
# Build standalone Linux binary (optional — same as Windows one-file deploy)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -r requirements.txt -q
pyinstaller --noconfirm ShibliC2.spec

echo ""
echo "Build complete: $ROOT/dist/ShibliC2"
echo "Run: ./dist/ShibliC2"
