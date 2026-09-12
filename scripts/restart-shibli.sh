#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
"${ROOT}/scripts/ensure-ready.sh"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_venv.sh"
PYTHON="$(resolve_shibli_python "$ROOT")"

echo "=== SHIBLI C2 Restart ==="
PORT="${VMS_PORT:-8080}"
kill_port "${PORT}" "${ROOT}"
if ! wait_port_free "${PORT}"; then
  pids="$(pids_on_port "${PORT}")"
  echo "ERROR: Could not free port ${PORT}${pids:+ (PID ${pids})}."
  echo "Run: ./scripts/stop.sh"
  exit 1
fi
sleep 1
unset SHIBLI_DATA_DIR || true
export SHIBLI_NO_BROWSER=1

"${PYTHON}" -c "
from app.core.bootstrap_env import bootstrap_environment
from app.core.paths import project_root
from app.core.database import db_info
bootstrap_environment(project_root())
print('DB:', db_info()['path'])
print('Encrypted:', db_info()['encrypted'])
"
echo "Starting…"
exec "${PYTHON}" launcher.py
