#!/usr/bin/env bash
# Audit a staged SHIBLI Linux tree or an extracted .deb. Fails on missing libs,
# GLIBC newer than the Ubuntu 22.04 baseline, bundled glibc, or development leftovers.
# Does not print secrets.
set -euo pipefail

fail() { echo "AUDIT FAIL: $*" >&2; exit 1; }
warn() { echo "AUDIT WARN: $*" >&2; }

MAX_GLIBC="${SHIBLI_MAX_GLIBC:-2.35}"

version_gt() {
  local a="$1" b="$2"
  [[ "$(printf '%s\n' "$a" "$b" | sort -V | tail -n 1)" == "$a" && "$a" != "$b" ]]
}

PKG=""
ROOT=""
if [[ "${1:-}" == "--deb" ]]; then
  [[ -f "${2:-}" ]] || fail "usage: $0 --deb <package.deb> | $0 <extract-or-stage-dir>"
  WORK="$(mktemp -d /tmp/shibli-audit-XXXXXX)"
  trap 'rm -rf "$WORK"' EXIT
  dpkg-deb -x "$2" "$WORK"
  dpkg-deb -e "$2" "$WORK/DEBIAN" 2>/dev/null || true
  PKG="$WORK"
  ROOT="$WORK/opt/shiblic2"
elif [[ -n "${1:-}" ]]; then
  PKG="$1"
  ROOT="$1"
  if [[ -d "$ROOT/opt/shiblic2" ]]; then
    ROOT="$ROOT/opt/shiblic2"
  fi
else
  fail "usage: $0 --deb <package.deb> | $0 <extract-or-stage-dir>"
fi

[[ -d "$ROOT" ]] || fail "application directory not found: $ROOT"

echo "==> Auditing $ROOT"
echo "==> Maximum allowed GLIBC: $MAX_GLIBC (Ubuntu 22.04)"

[[ -x "$ROOT/ShibliC2" ]] || fail "missing frozen ShibliC2"
[[ -x "$ROOT/bin/go2rtc" ]] || fail "missing bundled go2rtc"
[[ -x "$ROOT/bin/ffmpeg.bin" || -x "$ROOT/bin/ffmpeg" ]] || fail "missing bundled ffmpeg"
[[ -x "$ROOT/controls/ShibliControls" ]] || fail "missing frozen SHIBLI-controls"
[[ -f "$ROOT/go2rtc.example.yaml" ]] || fail "missing sanitized go2rtc.example.yaml"
[[ -x "$ROOT/bin/shibli-c2" ]] || fail "missing launcher"

if [[ -d "$ROOT/.venv" ]] || find "$PKG" -name '.venv' | grep -q .; then
  fail "development .venv is present"
fi
if find "$PKG" \( -name '.git' -o -name '.cursor' \) | grep -q .; then
  fail "Git or Cursor metadata is present"
fi
if find "$PKG" \( -name '*.db' -o -name '*verify_backup*' \) | grep -q .; then
  fail "database files are present"
fi
if find "$PKG" -name '.env' ! -name '.env.example' | grep -q .; then
  fail "live .env is present"
fi
if [[ -f "$ROOT/go2rtc.yaml" ]]; then
  fail "live go2rtc.yaml must not be packaged"
fi
if find "$PKG" -name 'libc.so.6' | grep -q .; then
  fail "glibc must not be bundled"
fi
if find "$PKG" \( -path '*/tests/*' -o -name 'ShibliC2.spec' -o -name 'requirements.txt' \) \
    | grep -v '/opt/shiblic2/_internal/' | grep -q .; then
  fail "development tests or build files are present"
fi

if grep -R -l --binary-files=without-match -E '/home/uavlab|/home/qurrat' \
  "$PKG" --exclude-dir=_internal --exclude-dir=lib --exclude-dir=controls 2>/dev/null | grep -q .; then
  fail "developer home paths found outside freeze internals"
fi

if grep -R --binary-files=without-match -E 'rtsp://[^:/]+:[^@]+@' \
  "$PKG" --exclude-dir=_internal --exclude-dir=lib --exclude-dir=controls 2>/dev/null | grep -q .; then
  fail "RTSP userinfo found in packaged text"
fi

if [[ -f "$PKG/DEBIAN/control" ]]; then
  echo "==> Package control"
  grep -E '^(Package|Version|Architecture|Depends):' "$PKG/DEBIAN/control" || true
fi

export LD_LIBRARY_PATH="$ROOT/lib:$ROOT/lib/gui:$ROOT/lib/webkit2gtk-4.0${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

ALLOWED_SYSTEM_RE='^(ld-linux|linux-vdso|libc\.so|libm\.so|libpthread\.so|libdl\.so|librt\.so|libresolv\.so|libanl\.so|libutil\.so|libgcc_s\.so|libstdc\+\+\.so|libgomp\.so|libGL\.so|libOpenGL\.so|libEGL\.so|libGLdispatch\.so|libGLX\.so|libdrm\.so|libcuda\.so|libnvidia)'

missing=0
needed_missing=0

audit_needed() {
  local bin="$1"
  [[ -f "$bin" ]] || return 0
  file -b "$bin" | grep -q ELF || return 0
  command -v readelf >/dev/null || return 0
  local need
  while read -r need; do
    [[ -n "$need" ]] || continue
    if echo "$need" | grep -Eq "$ALLOWED_SYSTEM_RE"; then
      continue
    fi
    if find "$ROOT" -name "$need" | grep -q .; then
      continue
    fi
    echo "Unbundled NEEDED $need from ${bin#$ROOT/}"
    needed_missing=1
  done < <(readelf -d "$bin" 2>/dev/null | sed -n 's/.*NEEDED.*\[\(.*\)\]/\1/p')
}

audit_elf() {
  local bin="$1"
  [[ -f "$bin" ]] || return 0
  if ! file -b "$bin" | grep -q ELF; then
    return 0
  fi
  audit_needed "$bin"
  if ldd "$bin" 2>/dev/null | grep -q 'not found'; then
    echo "Unresolved libraries in $bin:"
    ldd "$bin" | grep 'not found' || true
    missing=1
  fi
}

audit_elf "$ROOT/ShibliC2"
audit_elf "$ROOT/bin/go2rtc"
audit_elf "$ROOT/bin/ffmpeg.bin"
audit_elf "$ROOT/controls/ShibliControls"
while IFS= read -r so; do
  audit_elf "$so"
done < <(find "$ROOT/lib" -name '*.so*' -type f 2>/dev/null | head -n 120)

if [[ "$needed_missing" -ne 0 ]]; then
  fail "one or more ELF files need libraries that are not bundled and not a base-OS ABI library"
fi
if [[ "$missing" -ne 0 ]]; then
  fail "one or more binaries have unresolved ldd dependencies"
fi

glibc_fail=0
if command -v objdump >/dev/null; then
  echo "==> Highest GLIBC symbols"
  while IFS= read -r bin; do
    file -b "$bin" | grep -q ELF || continue
    high="$(objdump -T "$bin" 2>/dev/null | grep -o 'GLIBC_[0-9.]*' | sed 's/GLIBC_//' | sort -V | tail -1 || true)"
    [[ -n "$high" ]] || continue
    echo "  ${bin#$ROOT/}: GLIBC_$high"
    if version_gt "$high" "$MAX_GLIBC"; then
      echo "AUDIT FAIL: $bin requires GLIBC_$high (max $MAX_GLIBC)"
      glibc_fail=1
    fi
  done < <(find "$ROOT" -type f \( -name 'ShibliC2' -o -name 'ShibliControls' -o -name 'ffmpeg.bin' -o -name 'go2rtc' -o -name '*.so*' \) | head -n 80)
fi
if [[ "$glibc_fail" -ne 0 ]]; then
  fail "one or more binaries require GLIBC newer than Ubuntu 22.04 ($MAX_GLIBC)"
fi

echo "AUDIT PASS: $ROOT"
