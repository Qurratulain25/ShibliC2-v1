# Deployment Guide — Windows & Ubuntu

## What to copy to the target machine

Copy the **ShibliC2** folder excluding build artifacts:

```
ShibliC2/
├── app/
├── static/
├── scripts/
├── deploy/
├── launcher.py
├── requirements.txt
├── config.example.json
├── .env.example
├── go2rtc.yaml.example
├── README.md
├── ARCHITECTURE.md
├── DEPLOYMENT.md
└── DATABASE.md
```

Do **not** copy: `.venv/`, `build/`, `dist/` (unless deploying a pre-built binary), `data/*.db`.

---

## Ubuntu (recommended for edge towers)

### Quick start

```bash
cd ShibliC2
chmod +x scripts/*.sh
./scripts/install-ubuntu.sh
./scripts/ensure-ready.sh
# copy .env.example → data/.env and set SHIBLI_DB_KEY
./scripts/start.sh
```

Open: **http://127.0.0.1:8080**  
Fresh installations create the first Administrator during initial setup. No default password is shipped.

### Headless / LAN access (observation post PC)

Edit `data/.env`:

```env
VMS_HOST=0.0.0.0
VMS_PORT=8080
SHIBLI_NO_BROWSER=1
```

Restart with `./scripts/start.sh`. Other machines on the LAN use `http://<ubuntu-ip>:8080`.

### Optional: standalone Linux binary

```bash
./scripts/build-linux.sh
./dist/ShibliC2
```

Config stored in `~/.local/share/ShibliC2/`.

### Optional: systemd service

```bash
sudo useradd -r -s /bin/false shibli || true
sudo mkdir -p /opt/shibli-c2
sudo cp -r . /opt/shibli-c2/
cd /opt/shibli-c2 && ./scripts/build-linux.sh
sudo cp deploy/shibli-c2.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now shibli-c2
```

### Ubuntu dependencies (manual)

```bash
sudo apt install python3 python3-venv python3-pip
```

For local recording (FFmpeg) and optional go2rtc:

```bash
sudo apt install ffmpeg
```

---

## Windows

### Option A — Single EXE (field deploy)

Copy only:

```
dist/ShibliC2.exe
```

Double-click. Config: `%LOCALAPPDATA%\ShibliC2\config.json`

Rebuild on dev machine:

```powershell
.\build.ps1
```

### Option B — From source

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python launcher.py
```

---

## Hardware integration (both platforms)

1. Run **SHIBLI-controls** natively for ONVIF / USR LRF / illuminator (port 8001).
2. Set in `data/.env`:

```env
SHIBLI_CONTROLS_URL=http://127.0.0.1:8001
SHIBLI_JWT_SECRET=<unique-secret>
```

In production (`SHIBLI_ENV=production`) a unique `SHIBLI_JWT_SECRET` is required.

3. Add cameras in the UI (Cameras page). go2rtc uses `go2rtc.yaml` (Day `<DAY_CAMERA_IP>`, Thermal `<THERMAL_CAMERA_IP>`). Run `./scripts/start-go2rtc.sh`.

Field camera worksheet: **CAMERA_INTEGRATION_CHECKLIST.md**.

---

## Health check

```bash
curl http://127.0.0.1:8080/api/health
```

Expected: `{"status":"ok","version":"1.2.0-phase1","phase":1}`
