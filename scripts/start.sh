#!/usr/bin/env bash
# Start SHIBLI C2 (development or installed copy)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
"${ROOT}/scripts/ensure-ready.sh"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_venv.sh"
PYTHON="$(resolve_shibli_python "$ROOT")"

export VMS_HOST="${VMS_HOST:-127.0.0.1}"
export VMS_PORT="${VMS_PORT:-8080}"
export SHIBLI_NO_BROWSER="${SHIBLI_NO_BROWSER:-1}"

echo "Starting SHIBLI C2 on http://${VMS_HOST}:${VMS_PORT}"
exec "${PYTHON}" launcher.py
