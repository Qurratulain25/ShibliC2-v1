#!/usr/bin/env bash
# Build the production Ubuntu package against the Ubuntu 22.04 LTS ABI.
# The development workstation may be newer. This script must not freeze
# using the host Python or host FFmpeg.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

fail() { echo "ERROR: $*" >&2; exit 1; }

[[ -f "$ROOT/deployment/runtime/controls/server.py" ]] || fail "SHIBLI-controls source missing at deployment/runtime/controls. Refusing to build."
[[ -f "$ROOT/deployment/runtime/pins.json" ]] || fail "deployment/runtime/pins.json missing"
[[ -f "$ROOT/go2rtc.example.yaml" ]] || fail "go2rtc.example.yaml missing"
[[ -f "$ROOT/deployment/ubuntu/Dockerfile.ubuntu2204" ]] || fail "Dockerfile.ubuntu2204 missing"
[[ -f "$ROOT/deployment/ubuntu/build-inside-2204.sh" ]] || fail "build-inside-2204.sh missing"

if [[ -n "${SHIBLI_CONTROLS_SOURCE:-}" ]]; then
  fail "SHIBLI_CONTROLS_SOURCE is not used. Place approved controls in deployment/runtime/controls only."
fi

ENGINE=""
if command -v docker >/dev/null 2>&1; then
  ENGINE="docker"
  if [[ -z "${DOCKER_HOST:-}" && -S /var/run/docker.sock && ! -S "${HOME}/.docker/desktop/docker.sock" ]]; then
    export DOCKER_HOST="unix:///var/run/docker.sock"
  fi
elif command -v podman >/dev/null 2>&1; then
  ENGINE="podman"
else
  fail "Docker or Podman is required to build against ubuntu:22.04"
fi

if ! "$ENGINE" info >/dev/null 2>&1; then
  fail "$ENGINE is installed but the daemon is not reachable. If Docker Desktop is unused, set DOCKER_HOST=unix:///var/run/docker.sock"
fi

chmod +x "$ROOT/deployment/ubuntu/build-inside-2204.sh" "$ROOT/deployment/scripts/audit-linux-runtime.sh"

OUT_DIR="$ROOT/release/v1.0"
WORK_DIR="$ROOT/deployment/ubuntu/build"
IMAGE="shibli-c2-ubuntu2204:1.0"
DEB="$OUT_DIR/shibli-c2_v1.0_amd64.deb"
PREV_DEB="$OUT_DIR/shibli-c2_v1.0_amd64.ubuntu2510.deb"

mkdir -p "$OUT_DIR" "$WORK_DIR"

if [[ -f "$DEB" ]] && [[ ! -f "$PREV_DEB" ]]; then
  echo "==> Keeping previous candidate as $PREV_DEB until the 22.04 build succeeds"
  cp -n "$DEB" "$PREV_DEB" || true
fi

echo "==> Building Ubuntu 22.04 builder image"
"$ENGINE" build \
  --file "$ROOT/deployment/ubuntu/Dockerfile.ubuntu2204" \
  --tag "$IMAGE" \
  "$ROOT/deployment/ubuntu"

echo "==> Freezing and packaging inside ubuntu:22.04"
# Source is read-only. Writable mounts: work, release, and a narrow rw path for the manifest.
"$ENGINE" run --rm \
  --name shibli-c2-ubuntu2204-build \
  -e HOME=/tmp \
  -e SHIBLI_SRC=/src \
  -e SHIBLI_WORK=/work \
  -e SHIBLI_OUT=/out/v1.0 \
  -e SHIBLI_MAX_GLIBC=2.35 \
  -e SHIBLI_REUSE_FREEZE="${SHIBLI_REUSE_FREEZE:-}" \
  -v "$ROOT:/src:ro" \
  -v "$WORK_DIR:/work" \
  -v "$ROOT/release:/out" \
  -v "$ROOT/deployment:/src-rw/deployment" \
  "$IMAGE" \
  /bin/bash /src/deployment/ubuntu/build-inside-2204.sh

[[ -f "$DEB" ]] || fail "22.04 builder did not produce $DEB"

# Host-side audit of the new package (GLIBC symbols do not require executing the binary).
"$ROOT/deployment/scripts/audit-linux-runtime.sh" --deb "$DEB"

{
  echo "# SHIBLI C2 v1.0 — Ubuntu 22.04 LTS production candidate"
  sha256sum "$DEB" | awk '{print $1"  shibli-c2_v1.0_amd64.deb"}'
} > "$OUT_DIR/SHA256SUMS.txt"

echo
echo "Production candidate: $DEB"
ls -lh "$DEB"
echo "Previous 25.10 candidate retained at: $PREV_DEB"
echo "SHA256:"
cat "$OUT_DIR/SHA256SUMS.txt"
