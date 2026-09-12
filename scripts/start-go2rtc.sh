#!/usr/bin/env bash
# Start go2rtc for WebRTC camera streams (optional sidecar)
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

if PYTHON="$(resolve_shibli_python "$ROOT" 2>/dev/null)"; then
  "${PYTHON}" "${ROOT}/scripts/render_go2rtc.py" || echo "go2rtc yaml render skipped"
fi

CONFIG="${GO2RTC_CONFIG:-$ROOT/go2rtc.yaml}"
if [[ ! -f "$CONFIG" ]]; then
  if [[ -f "$ROOT/go2rtc.yaml.example" ]]; then
    cp "$ROOT/go2rtc.yaml.example" "$CONFIG"
    echo "Created $CONFIG from go2rtc.yaml.example"
  else
    echo "Missing go2rtc config: $CONFIG"
    exit 1
  fi
fi

GO2RTC_BIN="${GO2RTC_BIN:-go2rtc}"
if ! command -v "$GO2RTC_BIN" >/dev/null 2>&1; then
  for candidate in "$ROOT/bin/go2rtc" "$ROOT/go2rtc" /usr/local/bin/go2rtc "$HOME/go/bin/go2rtc"; do
    if [[ -x "$candidate" ]]; then
      GO2RTC_BIN="$candidate"
      break
    fi
  done
fi
if ! command -v "$GO2RTC_BIN" >/dev/null 2>&1 && [[ ! -x "$GO2RTC_BIN" ]]; then
  echo "go2rtc not found. Install from https://github.com/AlexxIT/go2rtc/releases"
  echo "Place the binary on PATH, or set GO2RTC_BIN=/path/to/go2rtc"
  exit 1
fi

export GO2RTC_API_URL="${GO2RTC_API_URL:-http://127.0.0.1:1984}"
echo "Starting go2rtc with $CONFIG"
exec "$GO2RTC_BIN" -config "$CONFIG"
