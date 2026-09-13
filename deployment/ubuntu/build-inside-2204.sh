#!/usr/bin/env bash
# Runs inside the Ubuntu 22.04 builder. Never reads or writes the live development database.
set -euo pipefail

fail() { echo "ERROR: $*" >&2; exit 1; }

SRC="${SHIBLI_SRC:-/src}"
WORK="${SHIBLI_WORK:-/work}"
OUT_DIR="${SHIBLI_OUT:-/out/v1.0}"
STAGE="$WORK/stage/shibli-c2"
VERSION="1.0.0"
DEB="$OUT_DIR/shibli-c2_v1.0_amd64.deb"

[[ -f /etc/os-release ]] || fail "os-release missing"
OS_VERSION_ID="$(. /etc/os-release && printf '%s' "${VERSION_ID:-}")"
[[ "${OS_VERSION_ID}" == "22.04" ]] || fail "This script must run on Ubuntu 22.04 (found ${OS_VERSION_ID:-unknown})"
[[ "$(uname -m)" == "x86_64" ]] || fail "Ubuntu 22.04 builder must be x86-64"

[[ -f "$SRC/ShibliC2.spec" ]] || fail "Source tree missing at $SRC"
[[ -f "$SRC/deployment/runtime/controls/server.py" ]] || fail "SHIBLI-controls source missing at $SRC/deployment/runtime/controls"
[[ -f "$SRC/deployment/runtime/pins.json" ]] || fail "pins.json missing"
[[ -f "$SRC/go2rtc.example.yaml" ]] || fail "sanitized go2rtc.example.yaml missing"
[[ -f "$SRC/.env.example" ]] || fail ".env.example missing"

command -v python3 >/dev/null || fail "python3 missing in builder"
command -v dpkg-deb >/dev/null || fail "dpkg-deb missing in builder"
command -v ffmpeg >/dev/null || fail "ffmpeg missing in Ubuntu 22.04 builder"
command -v ldd >/dev/null || fail "ldd missing"

mkdir -p "$WORK" "$OUT_DIR" "$WORK/dist" "$WORK/build" "$WORK/venv" "$WORK/controls-venv"

# Never touch development persistent data (even if the source mount is writable).
[[ ! -e "$SRC/data/shibli_c2.db" ]] || echo "==> Development DB is present on the source mount and will not be packaged"

echo "==> Builder baseline"
cat /etc/shibli-build-baseline.txt 2>/dev/null || true
{ ldd --version || true; } | head -n 1 || true

is_elf() { [[ -f "$1" ]] && file -b "$1" | grep -q 'ELF'; }

# --- go2rtc: pinned official linux/amd64 binary (build-time only) ---
PINNED_GO2RTC_SHA="$(python3 - <<'PY'
import json,sys
print(json.load(open("/src/deployment/runtime/pins.json"))["go2rtc"]["linux_amd64_sha256"])
PY
)"
PINNED_GO2RTC_URL="$(python3 - <<'PY'
import json
print(json.load(open("/src/deployment/runtime/pins.json"))["go2rtc"]["linux_amd64_url"])
PY
)"
GO2RTC_BIN="$WORK/runtime/go2rtc"
mkdir -p "$WORK/runtime"
if [[ -f "$SRC/deployment/runtime/linux/go2rtc" ]] && is_elf "$SRC/deployment/runtime/linux/go2rtc"; then
  cp "$SRC/deployment/runtime/linux/go2rtc" "$GO2RTC_BIN"
else
  echo "==> Downloading pinned go2rtc 1.9.14 (build-time)"
  wget -q -O "$GO2RTC_BIN" "$PINNED_GO2RTC_URL" || fail "go2rtc download failed"
fi
chmod +x "$GO2RTC_BIN"
is_elf "$GO2RTC_BIN" || fail "go2rtc is not an ELF binary"
ACTUAL_GO2RTC_SHA="$(sha256sum "$GO2RTC_BIN" | awk '{print $1}')"
[[ "$ACTUAL_GO2RTC_SHA" == "$PINNED_GO2RTC_SHA" ]] || fail "go2rtc SHA256 mismatch (expected pinned 1.9.14)"

# --- FFmpeg: Ubuntu 22.04 package, never a 25.10 host binary ---
FFMPEG_BIN="$(command -v ffmpeg)"
is_elf "$FFMPEG_BIN" || fail "builder ffmpeg is not ELF"
case "$(readlink -f "$FFMPEG_BIN")" in
  /usr/bin/ffmpeg|/bin/ffmpeg) ;;
  *) fail "ffmpeg must be the Ubuntu 22.04 system binary, not a host-copied 25.10 runtime" ;;
esac
FFMPEG_SHA="$(sha256sum "$(readlink -f "$FFMPEG_BIN")" | awk '{print $1}')"
FFMPEG_VER="$({ ffmpeg -version || true; } | head -n 1 || true)"

# --- Python freeze environment (system-site-packages for PyGObject) ---
VENV="$WORK/venv"
if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv --system-site-packages "$VENV"
fi
PY="$VENV/bin/python"
"$PY" -m pip install -q -U pip
"$PY" -m pip install -q -r "$SRC/requirements.txt"
[[ -x "$VENV/bin/pyinstaller" ]] || fail "PyInstaller missing after requirements install"

echo "==> Copying sanitized sources (excludes data, venv, git, live config)"
BUILD_SRC="$WORK/src"
rm -rf "$BUILD_SRC"
mkdir -p "$BUILD_SRC"
rsync -a \
  --exclude '.venv/' \
  --exclude '.git/' \
  --exclude '.cursor/' \
  --exclude 'data/' \
  --exclude 'dist/' \
  --exclude 'build/' \
  --exclude 'release/' \
  --exclude 'client-release/' \
  --exclude 'deployment/ubuntu/build/' \
  --exclude 'deployment/runtime/.controls-src-path' \
  --exclude 'deployment/runtime/linux/ffmpeg' \
  --exclude 'go2rtc.yaml' \
  --exclude '.env' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  "$SRC/" "$BUILD_SRC/"
[[ ! -f "$BUILD_SRC/data/shibli_c2.db" ]] || fail "live database leaked into sanitized source copy"
[[ ! -f "$BUILD_SRC/go2rtc.yaml" ]] || fail "live go2rtc.yaml leaked into sanitized source copy"

if [[ "${SHIBLI_REUSE_FREEZE:-}" == "1" && -x "$WORK/dist/ShibliC2/ShibliC2" && -x "$WORK/dist/ShibliControls/ShibliControls" ]]; then
  echo "==> Reusing existing Ubuntu 22.04 freeze (SHIBLI_REUSE_FREEZE=1)"
else
echo "==> Freezing SHIBLI C2 (onedir) with Ubuntu 22.04 Python"
rm -rf "$WORK/dist/ShibliC2" "$WORK/build/ShibliC2"
"$VENV/bin/pyinstaller" --noconfirm --distpath "$WORK/dist" --workpath "$WORK/build" "$BUILD_SRC/ShibliC2.spec"
[[ -x "$WORK/dist/ShibliC2/ShibliC2" ]] || fail "PyInstaller did not produce ShibliC2"
fi

if [[ "${SHIBLI_REUSE_FREEZE:-}" == "1" && -x "$WORK/dist/ShibliControls/ShibliControls" ]]; then
  echo "==> Reusing existing SHIBLI-controls freeze"
else
echo "==> Freezing SHIBLI-controls from approved source"
CONTROLS_DIR="$BUILD_SRC/deployment/runtime/controls"
[[ -f "$CONTROLS_DIR/server.py" ]] || fail "controls source missing after sanitize"
CTRL_SRC="$WORK/controls-src"
rm -rf "$CTRL_SRC"
mkdir -p "$CTRL_SRC"
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
  "$CONTROLS_DIR/" "$CTRL_SRC/"
rm -f "$CTRL_SRC/.env" "$CTRL_SRC/.env."*
CTRL_VENV="$WORK/controls-venv"
if [[ ! -x "$CTRL_VENV/bin/python" ]]; then
  python3 -m venv "$CTRL_VENV"
fi
"$CTRL_VENV/bin/python" -m pip install -q -U pip
"$CTRL_VENV/bin/python" -m pip install -q pyinstaller==6.11.1
"$CTRL_VENV/bin/python" -m pip install -q -r "$CONTROLS_DIR/requirements.txt"
export SHIBLI_CONTROLS_SRC="$CTRL_SRC"
rm -rf "$WORK/dist/ShibliControls" "$WORK/build/ShibliControls"
( cd "$CTRL_SRC" && "$CTRL_VENV/bin/python" -m PyInstaller --noconfirm \
    --distpath "$WORK/dist" --workpath "$WORK/build" \
    "$BUILD_SRC/deployment/scripts/ShibliControls.spec" )
unset SHIBLI_CONTROLS_SRC
[[ -x "$WORK/dist/ShibliControls/ShibliControls" ]] || fail "SHIBLI-controls freeze failed. Refusing to ship without hardware controls."
fi

echo "==> Staging Debian package"
rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" \
  "$STAGE/opt/shiblic2/bin" \
  "$STAGE/opt/shiblic2/lib" \
  "$STAGE/opt/shiblic2/share/icons" \
  "$STAGE/usr/share/applications" \
  "$STAGE/usr/share/icons/hicolor/256x256/apps" \
  "$STAGE/var/lib/shiblic2/"{config,data,logs,recordings,snapshots,exports,backups}

rsync -a "$WORK/dist/ShibliC2/" "$STAGE/opt/shiblic2/"
cp "$BUILD_SRC/go2rtc.example.yaml" "$STAGE/opt/shiblic2/go2rtc.example.yaml"
cp "$BUILD_SRC/.env.example" "$STAGE/opt/shiblic2/.env.example"
cp "$BUILD_SRC/config.example.json" "$STAGE/opt/shiblic2/config.example.json"
if [[ -f "$BUILD_SRC/deployment/assets/logo/shibli.ico" ]]; then
  cp "$BUILD_SRC/deployment/assets/logo/shibli.ico" "$STAGE/opt/shiblic2/shibli.ico"
fi
if [[ -f "$BUILD_SRC/deployment/assets/logo/shibli-256.png" ]]; then
  cp "$BUILD_SRC/deployment/assets/logo/shibli-256.png" "$STAGE/opt/shiblic2/share/icons/shibli.png"
  cp "$BUILD_SRC/deployment/assets/logo/shibli-256.png" "$STAGE/usr/share/icons/hicolor/256x256/apps/shibli-c2.png"
fi
cp "$BUILD_SRC/deployment/ubuntu/installer/shibli-c2.desktop" "$STAGE/usr/share/applications/"

cp "$GO2RTC_BIN" "$STAGE/opt/shiblic2/bin/go2rtc"
chmod +x "$STAGE/opt/shiblic2/bin/go2rtc"
cp "$(readlink -f "$FFMPEG_BIN")" "$STAGE/opt/shiblic2/bin/ffmpeg.bin"
chmod +x "$STAGE/opt/shiblic2/bin/ffmpeg.bin"

# Copy application-specific shared libraries. Never copy glibc or GPU drivers.
# Use ".so" after the SONAME so libmfx is not treated as libm.
SYSTEM_LIB_RE='^(ld-linux|linux-vdso|libc\.so|libm\.so|libpthread\.so|libdl\.so|librt\.so|libresolv\.so|libanl\.so|libutil\.so|libBrokenLocale\.so|libthread_db\.so|libgcc_s\.so|libstdc\+\+\.so|libgomp\.so|libGL\.so|libOpenGL\.so|libEGL\.so|libGLdispatch\.so|libGLX\.so|libdrm\.so|libcuda\.so|libnvidia)'

copy_deps() {
  local bin="$1"
  local dest="$2"
  mkdir -p "$dest"
  ldd "$bin" 2>/dev/null | awk '/=> \//{print $3}' | while read -r lib; do
    [[ -f "$lib" ]] || continue
    local base
    base="$(basename "$lib")"
    if echo "$base" | grep -Eq "$SYSTEM_LIB_RE"; then
      continue
    fi
    if [[ ! -e "$dest/$base" ]]; then
      cp -n "$lib" "$dest/" || true
    fi
  done
}

copy_deps "$STAGE/opt/shiblic2/bin/ffmpeg.bin" "$STAGE/opt/shiblic2/lib"
cat > "$STAGE/opt/shiblic2/bin/ffmpeg" <<'EOF'
#!/bin/sh
HERE="$(cd "$(dirname "$0")/.." && pwd)"
export LD_LIBRARY_PATH="$HERE/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$HERE/bin/ffmpeg.bin" "$@"
EOF
chmod 755 "$STAGE/opt/shiblic2/bin/ffmpeg"

mkdir -p "$STAGE/opt/shiblic2/controls"
rsync -a "$WORK/dist/ShibliControls/" "$STAGE/opt/shiblic2/controls/"

echo "==> Bundling Ubuntu 22.04 GTK/WebKit desktop libraries"
GUI_LIB="$STAGE/opt/shiblic2/lib/gui"
TYPELIB="$STAGE/opt/shiblic2/lib/girepository-1.0"
WEBKIT_DIR="$STAGE/opt/shiblic2/lib/webkit2gtk-4.0"
mkdir -p "$GUI_LIB" "$TYPELIB"
for lib in /usr/lib/x86_64-linux-gnu/libwebkit2gtk-4.0.so.37 \
           /usr/lib/x86_64-linux-gnu/libjavascriptcoregtk-4.0.so.18 \
           /usr/lib/x86_64-linux-gnu/libgtk-3.so.0 \
           /usr/lib/x86_64-linux-gnu/libgdk-3.so.0; do
  [[ -f "$lib" ]] || fail "required GUI library missing in 22.04 builder: $lib"
  cp -n "$lib" "$GUI_LIB/"
  copy_deps "$lib" "$GUI_LIB"
done
if [[ -d /usr/lib/x86_64-linux-gnu/webkit2gtk-4.0 ]]; then
  rsync -a /usr/lib/x86_64-linux-gnu/webkit2gtk-4.0/ "$WEBKIT_DIR/"
fi
if [[ -d /usr/lib/x86_64-linux-gnu/girepository-1.0 ]]; then
  cp -n /usr/lib/x86_64-linux-gnu/girepository-1.0/*.typelib "$TYPELIB/" || true
fi

# Close the shared-library set: copy deps of every staged ELF except glibc/GPU.
for _pass in 1 2 3 4; do
  find "$STAGE/opt/shiblic2" \( -type f -name '*.so*' -o -name 'ffmpeg.bin' -o -name 'ShibliC2' -o -name 'ShibliControls' -o -name 'WebKit*' \) \
    | while read -r so; do
        file -b "$so" 2>/dev/null | grep -q ELF || continue
        case "$so" in
          */lib/gui/*) copy_deps "$so" "$GUI_LIB" ;;
          */lib/webkit2gtk-4.0/*) copy_deps "$so" "$GUI_LIB" ;;
          *) copy_deps "$so" "$STAGE/opt/shiblic2/lib" ;;
        esac
      done
done

cat > "$STAGE/opt/shiblic2/bin/shibli-c2" <<'EOF'
#!/bin/bash
set -euo pipefail
export SHIBLI_INSTALL_LAYOUT="${SHIBLI_INSTALL_LAYOUT:-system}"
export SHIBLI_ENV="${SHIBLI_ENV:-production}"
export SHIBLI_DESKTOP="${SHIBLI_DESKTOP:-1}"
export GO2RTC_BIN="${GO2RTC_BIN:-/opt/shiblic2/bin/go2rtc}"
export FFMPEG_BIN="${FFMPEG_BIN:-/opt/shiblic2/bin/ffmpeg}"
export LD_LIBRARY_PATH="/opt/shiblic2/lib/gui:/opt/shiblic2/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export GI_TYPELIB_PATH="/opt/shiblic2/lib/girepository-1.0${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}"
if [[ -d /opt/shiblic2/lib/webkit2gtk-4.0 ]]; then
  export WEBKIT_EXEC_PATH="${WEBKIT_EXEC_PATH:-/opt/shiblic2/lib/webkit2gtk-4.0}"
fi
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

rm -rf "$STAGE/opt/shiblic2/.venv"
find "$STAGE/var/lib/shiblic2/data" -name '*.db' -delete 2>/dev/null || true
find "$STAGE" -name '.env' ! -name '.env.example' -delete || true
[[ ! -f "$STAGE/opt/shiblic2/go2rtc.yaml" ]] || fail "live go2rtc.yaml staged"
[[ ! -e "$STAGE/opt/shiblic2/.venv" ]] || fail "staged package contains .venv"
if find "$STAGE" -name 'libc.so.6' | grep -q .; then
  fail "glibc must not be bundled"
fi

cp "$BUILD_SRC/deployment/ubuntu/installer/control.in" "$STAGE/DEBIAN/control"
cp "$BUILD_SRC/deployment/ubuntu/installer/postinst" "$STAGE/DEBIAN/postinst"
cp "$BUILD_SRC/deployment/ubuntu/installer/preinst" "$STAGE/DEBIAN/preinst"
sed -i 's/\r$//' "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/preinst" "$STAGE/DEBIAN/control"
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/preinst"

# Runtime manifest from THIS builder, not the 25.10 host.
"$PY" - <<PY
import json, subprocess, sys
from pathlib import Path

def run(cmd):
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""

req = {}
for line in Path("$SRC/requirements.txt").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    req[line.split("==")[0].split(">=")[0]] = line
ctrl = " ".join(
    ln.strip()
    for ln in Path("$SRC/deployment/runtime/controls/requirements.txt").read_text(encoding="utf-8").splitlines()
    if ln.strip() and not ln.startswith("#")
)
baseline = Path("/etc/shibli-build-baseline.txt").read_text(encoding="utf-8") if Path("/etc/shibli-build-baseline.txt").is_file() else ""
manifest = {
    "product": "SHIBLI C2",
    "version": "1.0",
    "package_version": "$VERSION",
    "build_baseline": "Ubuntu 22.04 LTS x86-64",
    "build_os": "Ubuntu 22.04 LTS",
    "architecture": "amd64",
    "glibc_baseline": run(["bash", "-lc", "ldd --version | head -n 1"]),
    "python_runtime": run([sys.executable, "-c", "import sys; print(sys.version.split()[0])"]),
    "pyinstaller": run([sys.executable, "-c", "import PyInstaller; print(PyInstaller.__version__)"]),
    "desktop_runtime": run([sys.executable, "-c", "import webview; print(getattr(webview,'__version__','5.4'))"]),
    "gui_backend": "pywebview GTK + WebKit2GTK 4.0 (Ubuntu 22.04)",
    "sqlcipher": run([sys.executable, "-c", "import sqlcipher3; print(getattr(sqlcipher3,'__version__','present'))"]),
    "go2rtc": run(["$GO2RTC_BIN", "-version"]) or "go2rtc 1.9.14",
    "go2rtc_sha256": "$ACTUAL_GO2RTC_SHA",
    "ffmpeg": """$FFMPEG_VER""",
    "ffmpeg_sha256": "$FFMPEG_SHA",
    "controls": "deployment/runtime/controls (server.py)",
    "controls_requirements": ctrl,
    "application_requirements": req,
    "builder_baseline_file": baseline,
    "notes": [
        "Frozen inside ubuntu:22.04. Do not use Ubuntu 25.10 native libraries.",
        "glibc is not bundled. Client OS must provide Ubuntu 22.04+ glibc.",
    ],
}
dest = Path("$STAGE/opt/shiblic2/runtime-manifest.json")
dest.write_text(json.dumps(manifest, indent=2) + "\\n", encoding="utf-8")
Path("$WORK/runtime-manifest.json").write_text(json.dumps(manifest, indent=2) + "\\n", encoding="utf-8")
print("Wrote runtime-manifest.json")
PY

dpkg-deb --root-owner-group --build "$STAGE" "$DEB"
chmod 644 "$DEB" || true

export SHIBLI_MAX_GLIBC="${SHIBLI_MAX_GLIBC:-2.35}"
bash "$BUILD_SRC/deployment/scripts/audit-linux-runtime.sh" --deb "$DEB"

# Host-visible copies (optional mounts).
if [[ -d /src-rw/deployment ]]; then
  cp "$WORK/runtime-manifest.json" /src-rw/deployment/runtime-manifest.json
  cp /etc/shibli-build-baseline.txt /src-rw/deployment/ubuntu/BUILD_BASELINE.txt || true
fi

echo "Built $DEB"
ls -lh "$DEB"
sha256sum "$DEB"
echo "CONTROLS_BUNDLED=1"
echo "GO2RTC_SHA256=$ACTUAL_GO2RTC_SHA"
echo "FFMPEG_SHA256=$FFMPEG_SHA"
