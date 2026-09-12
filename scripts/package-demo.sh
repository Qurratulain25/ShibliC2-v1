#!/usr/bin/env bash
# Build a portable demo copy — no dev database, no machine-specific paths.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PARENT="$(dirname "$ROOT")"
DEST="${1:-$PARENT/ShibliC2-Demo}"

echo "==> Building demo package: $DEST"

rm -rf "$DEST"
mkdir -p "$DEST/data/recordings"

copy_tree() {
  local src="$1"
  local name="$2"
  if [[ -d "$ROOT/$src" ]]; then
    cp -a "$ROOT/$src" "$DEST/$name"
  fi
}

for item in app static scripts deploy; do
  copy_tree "$item" "$item"
done

for f in launcher.py requirements.txt config.example.json go2rtc.yaml.example; do
  [[ -f "$ROOT/$f" ]] && cp "$ROOT/$f" "$DEST/"
done

for doc in README.md DEPLOYMENT.md DATABASE.md CAMERA_INTEGRATION_CHECKLIST.md; do
  [[ -f "$ROOT/$doc" ]] && cp "$ROOT/$doc" "$DEST/"
done

# Fresh portable config — never copy dev data/ DB or recordings
cp "$ROOT/.env.example" "$DEST/data/.env"
cp "$ROOT/config.example.json" "$DEST/data/config.json"
cp "$ROOT/.env.example" "$DEST/.env"

# Demo-specific .env (relative paths only)
cat > "$DEST/data/.env" <<'EOF'
VMS_HOST=127.0.0.1
VMS_PORT=8080
SHIBLI_NO_BROWSER=1
SHIBLI_CONTROLS_URL=http://127.0.0.1:8001
SHIBLI_CORE_URL=http://127.0.0.1:3000
SHIBLI_VSS_URL=http://127.0.0.1:8000
SHIBLI_JWT_SECRET=abracadabra
SHIBLI_DB_KEY=ShibliC2-Demo-Portable-2026
SHIBLI_DEFAULT_ADMIN_USER=admin
: "${SHIBLI_DEFAULT_ADMIN_PASSWORD:?Set SHIBLI_DEFAULT_ADMIN_PASSWORD explicitly for demo use}"
SHIBLI_PASSWORD_RECOVERY_CODE=ShibliRecover2026
GO2RTC_ENABLED=1
GO2RTC_API_URL=http://127.0.0.1:1984
GO2RTC_STREAM_DAY=day
GO2RTC_STREAM_THERMAL=thermal
SHIBLI_STORAGE_WARN_GB=5
EOF

cp "$DEST/data/.env" "$DEST/.env"

chmod +x "$DEST"/scripts/*.sh 2>/dev/null || true
if command -v sed >/dev/null 2>&1; then
  for f in "$DEST"/scripts/*.sh; do
    sed -i 's/\r$//' "$f" 2>/dev/null || true
  done
fi

cat > "$DEST/DEMO_START.md" <<'EOF'
# SHIBLI C2 — Demo PC Quick Start

This copy is **portable**: no dev database, no hardcoded user paths.
Recordings go to `data/recordings/` on this machine.

## First run (Ubuntu)

```bash
cd ShibliC2-Demo
chmod +x scripts/*.sh
./scripts/ensure-ready.sh
./scripts/install-ubuntu.sh
./scripts/start.sh
```

Open: **http://127.0.0.1:8080**  
Administrator credentials must be supplied explicitly for demo use.

## LAN access (other PCs on site)

Edit `data/.env`:

```env
VMS_HOST=0.0.0.0
```

Restart: `./scripts/restart-shibli.sh`

## Live video (optional)

```bash
cp go2rtc.yaml.example go2rtc.yaml
# edit RTSP URLs
./scripts/start-go2rtc.sh
```

## Do NOT copy from dev PC

- Do **not** copy `data/shibli_c2.db` from another machine
- Each demo PC keeps its own `data/` folder

## Troubleshooting

```bash
./scripts/ensure-ready.sh
sudo chown -R $(whoami) data/    # if permission errors
./scripts/restart-shibli.sh
```
EOF

echo ""
echo "Demo package ready: $DEST"
echo "  Size: $(du -sh "$DEST" | cut -f1)"
echo "  Next: cd \"$DEST\" && ./scripts/install-ubuntu.sh && ./scripts/start.sh"
echo ""
echo "Copy this entire folder to the demo PC (USB / scp / zip)."
