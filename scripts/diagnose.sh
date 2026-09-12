#!/usr/bin/env bash
# Print why video / PTZ / cameras look offline. Run from the ShibliC2 folder.
# Never prints RTSP passwords or DB keys.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ok() { echo "  OK   $*"; }
bad() { echo "  FAIL $*"; }
info() { echo "  --   $*"; }

tcp_open() {
  local host="$1" port="$2"
  timeout 1 bash -c "echo >/dev/tcp/${host}/${port}" 2>/dev/null
}

redact_rtsp() {
  sed -E 's#(rtsp://)[^/@]+@#\1***:***@#g'
}

echo "=== SHIBLI C2 diagnose ==="
echo "Folder: $ROOT"
echo
echo "[0] This PC network"
if command -v ip >/dev/null 2>&1; then
  ip -4 addr show | awk '/inet /{print "  --   "$2"  "$NF}'
  ip -4 route | awk '/default/{print "  --   default via "$3" dev "$5}'
else
  hostname -I 2>/dev/null | awk '{print "  --   "$0}'
fi
echo

echo "[1] Files"
if [[ -f "$ROOT/go2rtc.yaml" ]]; then
  ok "go2rtc.yaml present"
else
  bad "go2rtc.yaml missing"
fi
if [[ -f "$ROOT/data/.env" ]]; then
  ok "data/.env present"
else
  info "data/.env missing"
fi
if [[ -f "$ROOT/data/shibli_c2.db" ]]; then
  sz="$(wc -c < "$ROOT/data/shibli_c2.db" | tr -d ' ')"
  if [[ "$sz" == "0" ]]; then
    bad "data/shibli_c2.db is 0 bytes — run python3 scripts/recover_runtime.py"
  else
    ok "data/shibli_c2.db size=${sz}"
  fi
fi
echo

echo "[2] Processes / ports (HTTP, not just a PID)"
if curl -fsS --max-time 2 "http://127.0.0.1:8080/api/health" >/dev/null 2>&1; then
  ok "SHIBLI C2 UI health on :8080"
else
  bad "C2 not healthy on :8080"
fi
if curl -fsS --max-time 2 "http://127.0.0.1:1984/api/streams" >/dev/null 2>&1 \
   || curl -fsS --max-time 2 "http://127.0.0.1:1984/" >/dev/null 2>&1; then
  ok "go2rtc on :1984"
else
  bad "go2rtc not on :1984"
fi
if curl -fsS --max-time 2 "http://127.0.0.1:8001/health" >/dev/null 2>&1; then
  ok "SHIBLI-controls on :8001"
else
  bad "controls not on :8001 — HW: OFFLINE"
fi
echo

echo "[3] go2rtc binary"
if command -v go2rtc >/dev/null 2>&1; then
  ok "go2rtc on PATH: $(command -v go2rtc)"
elif [[ -x "$ROOT/bin/go2rtc" ]]; then
  ok "go2rtc at $ROOT/bin/go2rtc"
else
  bad "go2rtc binary not installed"
fi
echo

echo "[4] Configured stream aliases (credentials redacted)"
if [[ -f "$ROOT/go2rtc.yaml" ]]; then
  grep -E "day:|thermal:" "$ROOT/go2rtc.yaml" | redact_rtsp | sed "s/^/  /"
fi
echo "  Historical LAN addresses (keep supported even if currently unplugged):"
for ip in "${SHIBLI_DIAG_DAY_IP:-}" "${SHIBLI_DIAG_THERMAL_IP:-}"; do
  [ -n "$ip" ] || continue
  if ping -c 1 -W 1 "$ip" >/dev/null 2>&1; then
    ok "ping $ip"
  else
    info "ping $ip failed (LAN hardware BLOCKED until the device is on this subnet)"
  fi
  if tcp_open "$ip" 554; then
    ok "TCP 554 (RTSP) $ip"
  else
    info "TCP 554 closed $ip"
  fi
done
echo

echo "[5] SHIBLI-controls folder"
if [[ -f "$ROOT/data/.env" ]]; then
  set -a
  source <(sed "s/\r$//" "$ROOT/data/.env") 2>/dev/null || true
  set +a
fi
CONTROLS_DIR="${SHIBLI_CONTROLS_DIR:-}"
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
FOUND="$(find "$HOME/Desktop" "$HOME/Downloads" "$ROOT/.." -maxdepth 5 -type f -name server.py 2>/dev/null | grep -i controls | head -5 || true)"
if [[ -n "$CONTROLS_DIR" && -f "$CONTROLS_DIR/server.py" ]]; then
  ok "controls source: $CONTROLS_DIR"
elif [[ -n "$FOUND" ]]; then
  bad "SHIBLI_CONTROLS_DIR not set; possible matches:"
  echo "$FOUND" | sed "s/^/  --   /"
  info "Add to data/.env: SHIBLI_CONTROLS_DIR=<that folder>"
else
  bad "SHIBLI-controls not found — set SHIBLI_CONTROLS_DIR in data/.env"
fi
echo
echo "=== done ==="
