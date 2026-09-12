#!/usr/bin/env bash
# Fix common demo-machine issues: script permissions, CRLF, data directory ownership.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> SHIBLI C2 preflight"

# Executable scripts (zip copies often lose +x)
chmod +x scripts/*.sh 2>/dev/null || true

# Windows line endings break bash on Linux ("$'\r': command not found", bad env vars)
if command -v sed >/dev/null 2>&1; then
  for f in scripts/*.sh .env.example go2rtc.yaml.example; do
    [[ -f "$f" ]] && sed -i 's/\r$//' "$f" 2>/dev/null || true
  done
  for f in data/.env .env data/config.json config.json; do
    [[ -f "$f" ]] && sed -i 's/\r$//' "$f" 2>/dev/null || true
  done
fi

mkdir -p data/recordings data/logs
if [[ -f data/shibli_c2.db && ! -s data/shibli_c2.db ]]; then
  echo "ERROR: data/shibli_c2.db is 0 bytes. Do not mint a new SHIBLI_DB_KEY."
  echo "Run: python3 scripts/recover_runtime.py"
  exit 1
fi
if [[ ! -f go2rtc.yaml && -f go2rtc.yaml.example ]]; then
  cp go2rtc.yaml.example go2rtc.yaml
  echo "Created go2rtc.yaml from go2rtc.yaml.example (streams filled at start-go2rtc from the DB)"
fi

# If data/ was created by root (sudo), fix ownership for the current demo user
if [[ -d data ]] && [[ ! -w data ]]; then
  echo "data/ is not writable for $(whoami) — attempting fix…"
  if command -v sudo >/dev/null 2>&1; then
    sudo chown -R "$(id -u):$(id -g)" data 2>/dev/null || true
  fi
fi

if [[ ! -w data ]]; then
  echo "WARNING: data/ still not writable. App will use ~/.local/share/ShibliC2 instead."
  echo "  Or run: sudo chown -R \$(whoami):\$(whoami) \"$ROOT/data\""
fi

# shellcheck disable=SC1091
source "${ROOT}/scripts/_venv.sh"
if ! PYTHON="$(resolve_shibli_python "$ROOT" 2>/dev/null)"; then
  echo "Python venv missing. Run: ./scripts/install-ubuntu.sh"
  exit 1
fi

"${PYTHON}" -c "
import os
from app.core.bootstrap_env import bootstrap_environment
from app.core.paths import data_dir, project_root
bootstrap_environment(project_root())
d = data_dir()
print('Data directory:', d)
print('Writable:', d.exists() and os.access(d, os.W_OK))
" 2>/dev/null || "${PYTHON}" -c "
import os
from pathlib import Path
root = Path('${ROOT}')
for p in [root/'data', Path.home()/'.local'/'share'/'ShibliC2']:
    p.mkdir(parents=True, exist_ok=True)
    print('Data directory:', p, 'writable:', os.access(p, os.W_OK))
"

echo "Preflight OK."

if command -v curl >/dev/null 2>&1; then
  CONTROLS_URL="${SHIBLI_CONTROLS_URL:-http://127.0.0.1:8001}"
  if curl -fsS --max-time 2 "${CONTROLS_URL}/health" >/dev/null 2>&1; then
    echo "SHIBLI-controls: online (${CONTROLS_URL})"
  else
    echo "SHIBLI-controls: offline — start with ./scripts/start-controls.sh"
  fi
fi
