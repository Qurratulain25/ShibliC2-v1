# SHIBLI C2 v1.0

Offline Command & Control for live video, PTZ, LRF, and illuminator control.  
**Cross-platform:** Windows installer and Ubuntu `.deb`.

See **ARCHITECTURE.md** for design.  
See **DEPLOYMENT.md** for field installation.  
See **DATABASE.md** for SQLCipher paths and encryption.  
See **deployment/README.md** for client installer builds.

**Before first run:** copy `.env.example` to `data/.env` and set `SHIBLI_DB_KEY`.

On a new database the login screen creates the first administrator. Existing
installations keep their current users and camera configuration.

---

## Quick start

### Ubuntu

```bash
cd ShibliC2
chmod +x scripts/*.sh
./scripts/install-ubuntu.sh
./scripts/ensure-ready.sh   # fixes permissions / Windows line endings on demo PCs
./scripts/start.sh
```

**Permission error on demo PC?** Run `./scripts/ensure-ready.sh` first. If `data/` was created by root: `sudo chown -R $(whoami) data/`

### Windows (source)

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python launcher.py
```

### Windows (single file deploy)

```powershell
.\build.ps1
# Copy dist\ShibliC2.exe to target PC
```

**UI:** http://127.0.0.1:8080

---

## Project structure

| Path | Purpose |
|------|---------|
| `app/` | FastAPI core, auth, adapters, routes, services |
| `static/` | Operator console UI |
| `scripts/` | Ubuntu install / start / build |
| `deploy/` | systemd service template |
| `config.example.json` | Site / stream / PTZ template (copied to `data/config.json` on first run) |

Phase 2 (AI Analytics) and Phase 3 (GIS) scaffolding is **not** in this tree. It lives on branch `cursor/phase-2-3-future-2648` under `future/`.

---

## Configuration

- `data/config.json` — site name, streams, PTZ systems, retention (created from `config.example.json`)
- `data/.env` — host, port, JWT secret, SQLCipher key, SHIBLI-controls URL

**Linux data dir (binary):** `~/.local/share/ShibliC2/`  
**Windows data dir (exe):** `%LOCALAPPDATA%\ShibliC2\`  
**Dev:** `./data/`
