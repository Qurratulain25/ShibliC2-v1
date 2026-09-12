#!/usr/bin/env bash
# Stop SHIBLI-controls (ports 8001 + USR 8234).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_venv.sh"

if [[ -f "${ROOT}/data/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source <(sed 's/\r$//' "${ROOT}/data/.env")
  set +a
fi

PORT="${SHIBLI_CONTROLS_PORT:-8001}"
USR_PORT="${USR_SERVER_PORT:-8234}"

pkill -f "SHIBLI-controls.*server.py" 2>/dev/null || true
pkill -f "/SHIBLI-controls/venv/bin/python3 server.py" 2>/dev/null || true

for p in "${PORT}" "${USR_PORT}"; do
  if port_has_listener "${p}"; then
    kill_port "${p}"
  fi
  if wait_port_free "${p}"; then
    echo "Port ${p} is free."
  else
    echo "Port ${p} still busy — try: fuser -k ${p}/tcp"
  fi
done
