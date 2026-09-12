#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_venv.sh"
PYTHON="$(resolve_shibli_python "$ROOT")"
exec "${PYTHON}" scripts/reset-admin-password.py
