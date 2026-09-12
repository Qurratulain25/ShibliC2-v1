#!/usr/bin/env bash
# Stop SHIBLI C2 if it is listening on the app port.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_venv.sh"
PORT="${VMS_PORT:-8080}"

if ! port_has_listener "${PORT}"; then
  echo "Port ${PORT} is free (no listener)."
  exit 0
fi

kill_port "${PORT}" "${ROOT}"
if wait_port_free "${PORT}"; then
  echo "Port ${PORT} is free."
else
  pids="$(pids_on_port "${PORT}")"
  echo "Port ${PORT} still has a listener${pids:+ (PID ${pids})}."
  echo "Try: kill ${pids:-<pid>}   or   sudo fuser -k ${PORT}/tcp"
  exit 1
fi
