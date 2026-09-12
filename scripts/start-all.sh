#!/usr/bin/env bash
# Start all ShibliC2 sidecars + main app (controls, go2rtc, C2 UI).
# Reports PASS/FAIL from live HTTP checks, not from background PIDs.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOG_DIR="${ROOT}/data/logs"
mkdir -p "$LOG_DIR"

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
FAIL=0

http_ok() {
  local url="$1"
  curl -fsS --max-time 2 "$url" >/dev/null 2>&1
}

wait_http() {
  local url="$1"
  local tries="${2:-25}"
  local i
  for i in $(seq 1 "${tries}"); do
    if http_ok "$url"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

start_bg() {
  local name="$1"
  shift
  echo "==> Launching ${name} (log: data/logs/${name}.log)"
  nohup "$@" >>"${LOG_DIR}/${name}.log" 2>&1 &
  echo "$!" >"${LOG_DIR}/${name}.pid"
}

echo "==> SHIBLI C2 stack start"
echo

if [[ ! -f "${ROOT}/data/.env" ]]; then
  echo "  FAIL data/.env missing — copy .env.example only on a true first install"
  FAIL=1
else
  echo "  PASS data/.env present"
fi

if [[ -z "${SHIBLI_DB_KEY:-}" ]]; then
  echo "  FAIL SHIBLI_DB_KEY is not set in data/.env"
  FAIL=1
else
  echo "  PASS SHIBLI_DB_KEY is set"
fi

if [[ -f "${ROOT}/data/shibli_c2.db" && ! -s "${ROOT}/data/shibli_c2.db" ]]; then
  echo "  FAIL data/shibli_c2.db is 0 bytes — refuse new-key init. Run: python3 scripts/recover_runtime.py"
  FAIL=1
fi

"${ROOT}/scripts/ensure-ready.sh" || true

if http_ok "http://127.0.0.1:${CONTROLS_PORT}/health"; then
  echo "  PASS SHIBLI-controls already healthy on :${CONTROLS_PORT}"
else
  start_bg controls "${ROOT}/scripts/start-controls.sh"
  if wait_http "http://127.0.0.1:${CONTROLS_PORT}/health" 20; then
    echo "  PASS SHIBLI-controls http://127.0.0.1:${CONTROLS_PORT}/health"
  else
    echo "  FAIL SHIBLI-controls did not respond on http://127.0.0.1:${CONTROLS_PORT}/health"
    echo "       Set SHIBLI_CONTROLS_DIR in data/.env to the folder containing server.py"
    FAIL=1
  fi
fi

if http_ok "http://127.0.0.1:${GO2RTC_PORT}/api/streams" || http_ok "http://127.0.0.1:${GO2RTC_PORT}/"; then
  echo "  PASS go2rtc already healthy on :${GO2RTC_PORT}"
else
  if command -v "${GO2RTC_BIN:-go2rtc}" >/dev/null 2>&1 || [[ -x /usr/local/bin/go2rtc ]] || [[ -x "${ROOT}/bin/go2rtc" ]]; then
    start_bg go2rtc "${ROOT}/scripts/start-go2rtc.sh"
    if wait_http "http://127.0.0.1:${GO2RTC_PORT}/api/streams" 15 || wait_http "http://127.0.0.1:${GO2RTC_PORT}/" 2; then
      echo "  PASS go2rtc http://127.0.0.1:${GO2RTC_PORT}"
    else
      echo "  FAIL go2rtc did not respond on http://127.0.0.1:${GO2RTC_PORT}"
      FAIL=1
    fi
  else
    echo "  FAIL go2rtc binary not found"
    FAIL=1
  fi
fi

if http_ok "http://127.0.0.1:${VMS_PORT}/api/health"; then
  echo "  PASS SHIBLI C2 already healthy on :${VMS_PORT}"
else
  start_bg shiblic2 "${ROOT}/scripts/start.sh"
  if wait_http "http://127.0.0.1:${VMS_PORT}/api/health" 25; then
    echo "  PASS SHIBLI C2 http://127.0.0.1:${VMS_PORT}/api/health"
  else
    echo "  FAIL SHIBLI C2 did not respond on http://127.0.0.1:${VMS_PORT}/api/health"
    FAIL=1
  fi
fi

echo ""
echo "Health summary:"
echo "  C2       http://127.0.0.1:${VMS_PORT}"
echo "  Controls http://127.0.0.1:${CONTROLS_PORT}/health"
echo "  go2rtc   http://127.0.0.1:${GO2RTC_PORT}"
echo "Logs: ${LOG_DIR}/"
echo "Stop: ./scripts/stop-all.sh"

if [[ "${FAIL}" -ne 0 ]]; then
  echo "STARTUP: FAIL"
  exit 1
fi
echo "STARTUP: PASS"
exit 0
