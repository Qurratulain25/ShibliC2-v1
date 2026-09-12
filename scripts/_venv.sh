# Shared venv resolution for SHIBLI C2 shell scripts.
# Prefer .venv-linux (local dev name) then standard .venv from install-ubuntu.sh.
resolve_shibli_python() {
  local root="${1:?project root required}"
  if [[ -x "${root}/.venv-linux/bin/python" ]]; then
    echo "${root}/.venv-linux/bin/python"
  elif [[ -x "${root}/.venv/bin/python" ]]; then
    echo "${root}/.venv/bin/python"
  else
    echo "ERROR: Python venv not found. Expected .venv-linux or .venv under ${root}" >&2
    echo "  Create one: python3 -m venv .venv-linux && .venv-linux/bin/pip install -r requirements.txt" >&2
    return 1
  fi
}

# True if something is LISTENING on the TCP port (not TIME_WAIT).
port_has_listener() {
  local port="${1:-8080}"
  if command -v ss >/dev/null 2>&1; then
    ss -H -lt "sport = :${port}" 2>/dev/null | grep -q .
    return $?
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi
  return 1
}

pids_on_port() {
  local port="${1:-8080}"
  local pids=""

  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -t -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
  fi
  if [[ -z "${pids}" ]] && command -v ss >/dev/null 2>&1; then
    pids="$(ss -H -ltnp "sport = :${port}" 2>/dev/null | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | sort -u | tr '\n' ' ')"
  fi
  if [[ -z "${pids}" ]] && command -v fuser >/dev/null 2>&1; then
    pids="$(fuser "${port}/tcp" 2>/dev/null | tr -s ' \n' '\n' | grep -E '^[0-9]+$' | tr '\n' ' ')"
  fi
  echo "${pids}" | xargs echo
}

kill_port() {
  local port="${1:-8080}"
  local root="${2:-}"
  local pids

  if [[ -n "${root}" ]]; then
    pkill -f "${root}/launcher.py" 2>/dev/null || true
  fi
  pkill -f "[l]auncher.py" 2>/dev/null || true

  pids="$(pids_on_port "${port}")"
  if [[ -n "${pids// }" ]]; then
    echo "Stopping port ${port} listener(s): ${pids}"
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
    sleep 1
    # shellcheck disable=SC2086
    kill -9 ${pids} 2>/dev/null || true
  fi

  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" 2>/dev/null || true
  fi
}

wait_port_free() {
  local port="${1:-8080}"
  local i
  for i in $(seq 1 12); do
    if ! port_has_listener "${port}"; then
      return 0
    fi
    sleep 1
  done
  return 1
}
