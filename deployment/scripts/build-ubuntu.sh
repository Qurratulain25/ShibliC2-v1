#!/usr/bin/env bash
# Host-native Ubuntu packager. NOT the production builder.
# Production packages must be built with build-ubuntu-2204.sh (ubuntu:22.04).
# Never copies .venv or live data.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
VERSION="1.0.0"
OUT_DIR="$ROOT/release/v1.0"
STAGE="$ROOT/deployment/ubuntu/build/shibli-c2"
DEB="$OUT_DIR/shibli-c2_v1.0_amd64.deb"
PY="${ROOT}/.venv/bin/python"
PYI="${ROOT}/.venv/bin/pyinstaller"
RUNTIME_LINUX="$ROOT/deployment/runtime/linux"

fail() { echo "ERROR: $*" >&2; exit 1; }

command -v dpkg-deb >/dev/null || fail "dpkg-deb is required"
[[ -x "$PY" ]] || fail "Development .venv is required on the build machine only"

"$PY" "$ROOT/deployment/scripts/generate-icons.py" || true

mkdir -p "$RUNTIME_LINUX" "$OUT_DIR"

is_elf() { [[ -f "$1" ]] && file -b "$1" | grep -q 'ELF'; }

# Ignore wrapper scripts left in the environment by prior tests.
if [[ -n "${GO2RTC_BIN:-}" ]] && ! is_elf "$GO2RTC_BIN"; then
  unset GO2RTC_BIN
fi
if [[ -n "${FFMPEG_BIN:-}" ]] && ! is_elf "$FFMPEG_BIN"; then
  unset FFMPEG_BIN
fi

GO2RTC_BIN="${GO2RTC_BIN:-}"
if [[ -z "$GO2RTC_BIN" ]]; then
  for candidate in "$RUNTIME_LINUX/go2rtc" "$ROOT/bin/go2rtc" "$(command -v go2rtc || true)"; do
    if [[ -n "$candidate" ]] && is_elf "$candidate"; then
      GO2RTC_BIN="$candidate"
      break
    fi
  done
fi
FFMPEG_BIN="${FFMPEG_BIN:-}"
if [[ -z "$FFMPEG_BIN" ]]; then
  for candidate in "$RUNTIME_LINUX/ffmpeg" "$(command -v ffmpeg || true)" /usr/bin/ffmpeg; do
    if [[ -n "$candidate" ]] && is_elf "$candidate"; then
      FFMPEG_BIN="$candidate"
      break
    fi
  done
fi

MISSING=()
[[ -n "$GO2RTC_BIN" && -x "$GO2RTC_BIN" ]] || MISSING+=("go2rtc")
[[ -n "$FFMPEG_BIN" && -x "$FFMPEG_BIN" ]] || MISSING+=("ffmpeg")
if [[ ${#MISSING[@]} -gt 0 ]]; then
  fail "Missing bundled runtime components: ${MISSING[*]}. Install them on the build machine; clients must not download them."
fi

if ! is_elf "$RUNTIME_LINUX/go2rtc"; then
  cp "$GO2RTC_BIN" "$RUNTIME_LINUX/go2rtc"
  chmod +x "$RUNTIME_LINUX/go2rtc"
fi
GO2RTC_BIN="$RUNTIME_LINUX/go2rtc"
if ! is_elf "$RUNTIME_LINUX/ffmpeg"; then
  cp "$FFMPEG_BIN" "$RUNTIME_LINUX/ffmpeg"
  chmod +x "$RUNTIME_LINUX/ffmpeg"
fi
FFMPEG_BIN="$RUNTIME_LINUX/ffmpeg"
is_elf "$GO2RTC_BIN" || fail "go2rtc is not an ELF binary"
is_elf "$FFMPEG_BIN" || fail "ffmpeg is not an ELF binary"
PINNED_GO2RTC_SHA="$("$PY" -c "import json; print(json.load(open('$ROOT/deployment/runtime/pins.json'))['go2rtc']['linux_amd64_sha256'])" 2>/dev/null || true)"
if [[ -n "$PINNED_GO2RTC_SHA" ]]; then
  ACTUAL_GO2RTC_SHA="$(sha256sum "$GO2RTC_BIN" | awk '{print $1}')"
  if [[ "$ACTUAL_GO2RTC_SHA" != "$PINNED_GO2RTC_SHA" ]]; then
    fail "go2rtc SHA256 mismatch (expected pinned 1.9.14 asset)"
  fi
fi

# Build-machine tools only — never packaged.
"$PY" -m pip install -q -r "$ROOT/requirements.txt" pywebview==5.4
[[ -x "$PYI" ]] || fail "PyInstaller is missing from the build venv"

# Delete ONLY previous packaging output (never runtime data/).
rm -rf "$STAGE" \
  "$ROOT/build/ShibliC2" \
  "$ROOT/build/ShibliControls" \
  "$ROOT/build/controls-src" \
  "$ROOT/dist/ShibliC2" \
  "$ROOT/dist/ShibliControls" \
  /tmp/shibli-c2-src \
  /tmp/shibli-controls-src

echo "==> Copying sanitized sources to /tmp (avoids embedding developer home paths)"
BUILD_SRC="/tmp/shibli-c2-src"
mkdir -p "$BUILD_SRC"
rsync -a \
  --exclude '.venv/' \
  --exclude '.git/' \
  --exclude '.cursor/' \
  --exclude 'data/' \
  --exclude 'dist/' \
  --exclude 'build/' \
  --exclude 'release/' \
  --exclude 'deployment/ubuntu/build/' \
  --exclude 'deployment/runtime/.controls-src-path' \
  --exclude 'go2rtc.yaml' \
  --exclude '.env' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  "$ROOT/" "$BUILD_SRC/"

echo "==> Freezing SHIBLI C2 (onedir)"
"$PYI" --noconfirm --distpath "$ROOT/dist" --workpath "$ROOT/build" "$BUILD_SRC/ShibliC2.spec"
[[ -x "$ROOT/dist/ShibliC2/ShibliC2" ]] || fail "PyInstaller did not produce dist/ShibliC2/ShibliC2"

CONTROLS_DIR="${SHIBLI_CONTROLS_SOURCE:-$ROOT/deployment/runtime/controls}"
if [[ ! -f "${CONTROLS_DIR}/server.py" ]]; then
  fail "SHIBLI-controls source missing at ${CONTROLS_DIR}. Populate deployment/runtime/controls or set SHIBLI_CONTROLS_SOURCE to an approved tree."
fi

CONTROLS_OK=0
if [[ -f "${CONTROLS_DIR}/server.py" ]]; then
  echo "==> Freezing SHIBLI-controls from approved source ${CONTROLS_DIR}"
  SRC="/tmp/shibli-controls-src"
  mkdir -p "$SRC"
  rsync -a \
    --exclude 'venv/' \
    --exclude 'venv_old/' \
    --exclude '.venv/' \
    --exclude '.env' \
    --exclude '.env.*' \
    --exclude 'data/' \
    --exclude 'logs/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.git/' \
    "${CONTROLS_DIR}/" "$SRC/"
  rm -f "$SRC/.env" "$SRC/.env."*
  CTRL_VENV="/tmp/shibli-controls-venv"
  if [[ ! -x "$CTRL_VENV/bin/python" ]]; then
    "$PY" -m venv "$CTRL_VENV"
  fi
  CTRL_PY="$CTRL_VENV/bin/python"
  "$CTRL_PY" -m pip install -q pyinstaller
  if [[ -f "${CONTROLS_DIR}/requirements.txt" ]]; then
    "$CTRL_PY" -m pip install -q -r "${CONTROLS_DIR}/requirements.txt"
  fi
  export SHIBLI_CONTROLS_SRC="$SRC"
  if ( cd "$SRC" && "$CTRL_PY" -m PyInstaller --noconfirm --distpath "$ROOT/dist" --workpath "$ROOT/build" "$BUILD_SRC/deployment/scripts/ShibliControls.spec" ); then
    if [[ -x "$ROOT/dist/ShibliControls/ShibliControls" ]]; then
      CONTROLS_OK=1
    fi
  fi
  unset SHIBLI_CONTROLS_SRC
fi
if [[ "$CONTROLS_OK" != "1" ]]; then
  fail "SHIBLI-controls freeze failed. Refusing to ship a package without hardware controls."
fi

echo "==> Staging Debian package"
mkdir -p "$STAGE/DEBIAN" \
  "$STAGE/opt/shiblic2/bin" \
  "$STAGE/opt/shiblic2/lib" \
  "$STAGE/opt/shiblic2/share/icons" \
  "$STAGE/usr/share/applications" \
  "$STAGE/usr/share/icons/hicolor/256x256/apps" \
  "$STAGE/var/lib/shiblic2/"{config,data,logs,recordings,snapshots,exports,backups}

rsync -a "$ROOT/dist/ShibliC2/" "$STAGE/opt/shiblic2/"
cp "$ROOT/go2rtc.example.yaml" "$STAGE/opt/shiblic2/go2rtc.example.yaml"
cp "$ROOT/.env.example" "$STAGE/opt/shiblic2/.env.example"
cp "$ROOT/config.example.json" "$STAGE/opt/shiblic2/config.example.json"
if [[ -f "$ROOT/deployment/assets/logo/shibli.ico" ]]; then
  cp "$ROOT/deployment/assets/logo/shibli.ico" "$STAGE/opt/shiblic2/shibli.ico"
fi
if [[ -f "$ROOT/deployment/assets/logo/shibli-256.png" ]]; then
  cp "$ROOT/deployment/assets/logo/shibli-256.png" "$STAGE/opt/shiblic2/share/icons/shibli.png"
  cp "$ROOT/deployment/assets/logo/shibli-256.png" "$STAGE/usr/share/icons/hicolor/256x256/apps/shibli-c2.png"
fi
cp "$ROOT/deployment/ubuntu/installer/shibli-c2.desktop" "$STAGE/usr/share/applications/"

cp "$GO2RTC_BIN" "$STAGE/opt/shiblic2/bin/go2rtc"
chmod +x "$STAGE/opt/shiblic2/bin/go2rtc"
cp "$FFMPEG_BIN" "$STAGE/opt/shiblic2/bin/ffmpeg.bin"
chmod +x "$STAGE/opt/shiblic2/bin/ffmpeg.bin"
is_elf "$STAGE/opt/shiblic2/bin/go2rtc" || fail "staged go2rtc is not ELF"
is_elf "$STAGE/opt/shiblic2/bin/ffmpeg.bin" || fail "staged ffmpeg.bin is not ELF"
if command -v ldd >/dev/null; then
  while read -r lib; do
    [[ -f "$lib" ]] || continue
    case "$lib" in
      /lib/*|/usr/lib/*) cp -n "$lib" "$STAGE/opt/shiblic2/lib/" || true ;;
    esac
  done < <(ldd "$FFMPEG_BIN" | awk '/=> \//{print $3}')
fi
cat > "$STAGE/opt/shiblic2/bin/ffmpeg" <<'EOF'
#!/bin/sh
HERE="$(cd "$(dirname "$0")/.." && pwd)"
export LD_LIBRARY_PATH="$HERE/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$HERE/bin/ffmpeg.bin" "$@"
EOF
chmod 755 "$STAGE/opt/shiblic2/bin/ffmpeg"

if [[ "$CONTROLS_OK" == "1" ]]; then
  mkdir -p "$STAGE/opt/shiblic2/controls"
  rsync -a "$ROOT/dist/ShibliControls/" "$STAGE/opt/shiblic2/controls/"
fi

echo "==> Bundling desktop GUI libraries (no apt at client install)"
GUI_LIB="$STAGE/opt/shiblic2/lib/gui"
TYPELIB="$STAGE/opt/shiblic2/lib/girepository-1.0"
mkdir -p "$GUI_LIB" "$TYPELIB"
for lib in /usr/lib/x86_64-linux-gnu/libwebkit2gtk-4.1.so.0 \
           /usr/lib/x86_64-linux-gnu/libjavascriptcoregtk-4.1.so.0 \
           /usr/lib/x86_64-linux-gnu/libgtk-3.so.0 \
           /usr/lib/x86_64-linux-gnu/libgdk-3.so.0 \
           /usr/lib/x86_64-linux-gnu/libjavascriptcoregtk-4.0.so.18 \
           /usr/lib/x86_64-linux-gnu/libwebkit2gtk-4.0.so.37; do
  if [[ -f "$lib" ]]; then
    cp -n "$lib" "$GUI_LIB/" || true
    while read -r dep; do
      [[ -f "$dep" ]] || continue
      cp -n "$dep" "$GUI_LIB/" || true
    done < <(ldd "$lib" | awk '/=> \//{print $3}')
  fi
done
if [[ -d /usr/lib/x86_64-linux-gnu/girepository-1.0 ]]; then
  cp -n /usr/lib/x86_64-linux-gnu/girepository-1.0/*.typelib "$TYPELIB/" || true
fi

cat > "$STAGE/opt/shiblic2/bin/shibli-c2" <<'EOF'
#!/bin/bash
set -euo pipefail
export SHIBLI_INSTALL_LAYOUT="${SHIBLI_INSTALL_LAYOUT:-system}"
export SHIBLI_PERSISTENT_ROOT="${SHIBLI_PERSISTENT_ROOT:-/var/lib/shiblic2}"
export SHIBLI_ENV="${SHIBLI_ENV:-production}"
export SHIBLI_DESKTOP="${SHIBLI_DESKTOP:-1}"
export GO2RTC_BIN="${GO2RTC_BIN:-/opt/shiblic2/bin/go2rtc}"
export FFMPEG_BIN="${FFMPEG_BIN:-/opt/shiblic2/bin/ffmpeg}"
export LD_LIBRARY_PATH="/opt/shiblic2/lib/gui:/opt/shiblic2/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export GI_TYPELIB_PATH="/opt/shiblic2/lib/girepository-1.0${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}"
if [[ -x /opt/shiblic2/controls/ShibliControls ]]; then
  export SHIBLI_CONTROLS_BIN="${SHIBLI_CONTROLS_BIN:-/opt/shiblic2/controls/ShibliControls}"
fi
cd /opt/shiblic2
if [[ ! -x /opt/shiblic2/ShibliC2 ]]; then
  echo "SHIBLI C2 runtime is missing." >&2
  exit 1
fi
exec /opt/shiblic2/ShibliC2 "$@"
EOF
chmod 755 "$STAGE/opt/shiblic2/bin/shibli-c2"

# Guard: never ship a development virtualenv or live lab data.
rm -rf "$STAGE/opt/shiblic2/.venv" "$STAGE/var/lib/shiblic2/data/"*.db || true
find "$STAGE" -name '.env' -not -name '.env.example' -delete || true

cp "$ROOT/deployment/ubuntu/installer/control.in" "$STAGE/DEBIAN/control"
cp "$ROOT/deployment/ubuntu/installer/postinst" "$STAGE/DEBIAN/postinst"
cp "$ROOT/deployment/ubuntu/installer/preinst" "$STAGE/DEBIAN/preinst"
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/preinst"

# Fail the build if the stage still contains development leftovers.
if find "$STAGE" -path '*/.venv/*' -o -name '.venv' | grep -q .; then
  fail "Staged package still contains .venv"
fi
if grep -R -l -E '/home/uavlab|/home/qurrat' "$STAGE/opt/shiblic2" --exclude-dir=_internal 2>/dev/null | head -n 1 | grep -q .; then
  echo "WARNING: developer path strings found in staged binaries (may be compiler paths)." >&2
fi

"$PY" "$ROOT/deployment/scripts/write_runtime_manifest.py" || true
cp "$ROOT/deployment/runtime-manifest.json" "$STAGE/opt/shiblic2/runtime-manifest.json" 2>/dev/null || true

dpkg-deb --root-owner-group --build "$STAGE" "$DEB"
"$ROOT/deployment/scripts/audit-linux-runtime.sh" --deb "$DEB"
echo "Built $DEB"
echo "CONTROLS_BUNDLED=$CONTROLS_OK"
