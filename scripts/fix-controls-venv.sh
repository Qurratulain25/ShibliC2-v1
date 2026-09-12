#!/usr/bin/env bash
# Repair SHIBLI-controls venv after copying from another PC (stale paths in venv/bin/activate).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -f "${ROOT}/data/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source <(sed 's/\r$//' "${ROOT}/data/.env")
  set +a
fi

CONTROLS_DIR="${SHIBLI_CONTROLS_DIR:-}"
if [[ -z "$CONTROLS_DIR" ]]; then
  for candidate in \
    "${ROOT}/../SHIBLI-controls" \
    "${HOME}/Downloads/Quest_Shibli_Setup/Shibli_packaged/SHIBLI/SHIBLI-controls" \
    "${HOME}/SHIBLI-controls"; do
    if [[ -f "${candidate}/server.py" ]]; then
      CONTROLS_DIR="$candidate"
      break
    fi
  done
fi

if [[ -z "$CONTROLS_DIR" ]] || [[ ! -d "${CONTROLS_DIR}/venv" ]]; then
  echo "SHIBLI-controls venv not found. Set SHIBLI_CONTROLS_DIR in data/.env"
  exit 1
fi

VENV="${CONTROLS_DIR}/venv"
echo "==> Fixing venv paths in ${VENV}"

for f in bin/activate bin/activate.csh bin/activate.fish; do
  target="${VENV}/${f}"
  [[ -f "$target" ]] || continue
  sed -i 's/\r$//' "$target"
  sed -i "s|export VIRTUAL_ENV=.*|export VIRTUAL_ENV=${VENV}|g" "$target"
  sed -i "s|cygpath /home/[^/]*/Quest_Shibli_Setup|cygpath ${VENV}|g" "$target"
  sed -i 's|\$VIRTUAL_ENV/"bin"|\$VIRTUAL_ENV/bin|g' "$target"
done

# Ensure python shim exists in venv/bin
if [[ ! -e "${VENV}/bin/python" ]] && [[ -x "${VENV}/bin/python3" ]]; then
  ln -sf python3 "${VENV}/bin/python"
fi

echo "Done. Start controls with:"
echo "  cd \"${ROOT}\" && ./scripts/start-controls.sh"
echo "Or manually:"
echo "  \"${VENV}/bin/python3\" \"${CONTROLS_DIR}/server.py\""
