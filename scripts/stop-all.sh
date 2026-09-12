#!/usr/bin/env bash
# Stop ShibliC2, go2rtc, and SHIBLI-controls started by start-all.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${ROOT}/data/logs"

# shellcheck disable=SC1091
source "${ROOT}/scripts/_venv.sh"

if [[ -f "${ROOT}/data/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source <(sed 's/\r$//' "${ROOT}/data/.env")
  set +a
fi

CONTROLS_PORT="${SHIBLI_CONTROLS_PORT:-8001}"
GO2RTC_PORT="${GO2RTC_API_URL:-http://127.0.0.1:1984}"
GO2RTC_PORT="${GO2RTC_PORT##*:}"
GO2RTC_PORT="${GO2RTC_PORT%%/*}"
VMS_PORT="${VMS_PORT:-8080}"

stop_pidfile() {
  local name="$1"
  local file="${LOG_DIR}/${name}.pid"
  if [[ -f "$file" ]]; then
    local pid
    pid="$(cat "$file")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "Stopping ${name} (PID ${pid})"
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$file"
  fi
}

stop_pidfile shiblic2
stop_pidfile go2rtc
stop_pidfile controls

"${ROOT}/scripts/stop.sh" 2>/dev/null || true

for port in "${VMS_PORT}" "${GO2RTC_PORT}" "${CONTROLS_PORT}"; do
  if port_has_listener "${port}" 2>/dev/null; then
    kill_port "${port}" "${ROOT}" 2>/dev/null || true
  fi
done

echo "All services stopped."
