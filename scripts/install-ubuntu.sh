#!/usr/bin/env bash
# Install SHIBLI C2 on Ubuntu / Debian edge nodes
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> SHIBLI C2 Ubuntu setup"
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip libsqlcipher-dev

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

mkdir -p data/recordings data/logs
if [[ -f data/.env ]]; then
  echo "Keeping existing data/.env (not overwritten)"
else
  cp -n .env.example data/.env 2>/dev/null || true
  echo "Created data/.env from .env.example — set SHIBLI_DB_KEY before first start"
fi
cp -n .env.example .env 2>/dev/null || true
cp -n config.example.json data/config.json 2>/dev/null || true

if [[ -f data/shibli_c2.db && ! -s data/shibli_c2.db ]]; then
  echo "ERROR: data/shibli_c2.db exists but is 0 bytes."
  echo "Do NOT generate a new SHIBLI_DB_KEY — that creates an empty camera database."
  echo "Restore data/shibli_c2.db.verify_backup with the original key, or run:"
  echo "  python3 scripts/recover_runtime.py"
  exit 1
fi
if [[ -f data/shibli_c2.db && -s data/shibli_c2.db ]]; then
  echo "Keeping existing encrypted database (not replaced)"
fi
chmod +x scripts/*.sh
if command -v sed >/dev/null 2>&1; then
  for f in scripts/*.sh .env.example; do
    sed -i 's/\r$//' "$f" 2>/dev/null || true
  done
fi
chown -R "$(id -u):$(id -g)" data 2>/dev/null || true

echo ""
echo "Setup complete."
echo "  Start:  ./scripts/start.sh"
echo "  Build:  ./scripts/build-linux.sh"
echo "  Reset admin password: ./scripts/reset-admin-password.sh"
echo "  UI:     http://127.0.0.1:8080"
echo "  Fresh installations require initial Administrator setup; no default password is shipped."
