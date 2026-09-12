#!/usr/bin/env bash
# Start SHIBLI-controls (PTZ/LRF/illuminator) for hardware integration.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

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
CONTROLS_DIR="${SHIBLI_CONTROLS_DIR:-}"

# Free ports from a previous controls instance (common after Ctrl+C missed the child)
for p in "${PORT}" "${USR_PORT}"; do
  if port_has_listener "${p}"; then
    echo "Port ${p} in use — stopping previous SHIBLI-controls…"
    kill_port "${p}"
    if ! wait_port_free "${p}"; then
      echo "ERROR: Port ${p} still busy. Run: fuser -k ${p}/tcp"
      exit 1
    fi
  fi
done

if [[ -z "$CONTROLS_DIR" ]]; then
  for candidate in \
    "${HOME}/Desktop/Abdullah_Shibli_C2/ShibliC2/SHIBLI-controls" \
    "${HOME}/Quest_Shibli_Setup/Shibli_packaged/SHIBLI/SHIBLI-controls" \
    "${ROOT}/../SHIBLI-controls" \
    "${ROOT}/SHIBLI-controls" \
    "${HOME}/Desktop/SHIBLI-controls" \
    "${HOME}/Desktop/Shibli_packaged/SHIBLI/SHIBLI-controls" \
    "${HOME}/Downloads/Quest_Shibli_Setup/Shibli_packaged/SHIBLI/SHIBLI-controls" \
    "${HOME}/SHIBLI-controls"; do
    if [[ -f "${candidate}/server.py" ]]; then
      CONTROLS_DIR="$candidate"
      break
    fi
  done
fi

if [[ -z "$CONTROLS_DIR" ]] || [[ ! -f "${CONTROLS_DIR}/server.py" ]]; then
  echo "SHIBLI-controls not found."
  echo "Set SHIBLI_CONTROLS_DIR in data/.env to the folder containing server.py"
  echo "Example:"
  echo "  SHIBLI_CONTROLS_DIR=/path/to/SHIBLI-controls"
  exit 1
fi

echo "==> Starting SHIBLI-controls from ${CONTROLS_DIR} on port ${PORT}"

if [[ -f "${CONTROLS_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source <(sed 's/\r$//' "${CONTROLS_DIR}/.env")
  set +a
fi

export JWT_SECRET="${JWT_SECRET:-${SHIBLI_JWT_SECRET:-abracadabra}}"
export PORT="${PORT:-$PORT}"

# USR LRF/illuminator TCP server — bind 0.0.0.0 if configured IP is not on this host
USR_BIND="${USR_SERVER_IP:-192.168.0.50}"
if [[ "$USR_BIND" == "0.0.0.0" ]]; then
  export USR_SERVER_IP="0.0.0.0"
elif command -v ip >/dev/null 2>&1; then
  if ip -4 addr show 2>/dev/null | grep -q "inet ${USR_BIND}/"; then
    export USR_SERVER_IP="$USR_BIND"
  else
    echo "Note: USR_SERVER_IP ${USR_BIND} not on this PC — binding 0.0.0.0 instead"
    export USR_SERVER_IP="0.0.0.0"
  fi
else
  export USR_SERVER_IP="$USR_BIND"
fi
export USR_SERVER_PORT="${USR_SERVER_PORT:-8234}"

# Use venv python directly — do not `source venv/bin/activate` (portable copies often
# have stale paths from another machine, so `python` is missing after activate).
PY=""
for candidate in \
  "${CONTROLS_DIR}/venv/bin/python3" \
  "${CONTROLS_DIR}/venv/bin/python"; do
  if [[ -x "$candidate" ]]; then
    PY="$candidate"
    break
  fi
done
if [[ -z "$PY" ]] && command -v python3 >/dev/null 2>&1; then
  PY="python3"
fi
if [[ -z "$PY" ]]; then
  echo "Python not found for SHIBLI-controls"
  echo "Try: cd \"$CONTROLS_DIR\" && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt"
  exit 1
fi

cd "$CONTROLS_DIR"
echo "Using: $PY"
exec "$PY" server.py
