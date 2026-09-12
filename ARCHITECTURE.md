# SHIBLI C2 — System Architecture (Phase 1)

Offline-first Command & Control console for live video, PTZ, LRF, and illuminator control. Phase 1 is a **single process**. Later phases are not loaded here.

## Design principles

| Principle | Phase 1 implementation |
|-----------|------------------------|
| Offline-first | No cloud, no license servers |
| Lightweight | Single Python process, CPU-first |
| Modular | Device adapters + UI module registry |
| Cross-platform | Windows exe + Ubuntu source/binary |

## Layer diagram

```
┌─────────────────────────────────────────────────────────────┐
│  Operator UI (static/)                                       │
│  Dashboard · Recordings · Cameras · Users · Audit · Settings │
└───────────────────────────┬─────────────────────────────────┘
                            │ REST + WebSocket
┌───────────────────────────▼─────────────────────────────────┐
│  app/main.py — Core API                                      │
└───────┬─────────────────────┬────────────────────────────────┘
        │                     │
┌───────▼────────┐  ┌─────────▼─────────┐
│ app/adapters/  │  │ app/core/         │
│ Device drivers │  │ config, paths,    │
│ ONVIF via HTTP │  │ SQLCipher, modules│
└───────┬────────┘  └───────────────────┘
        │
┌───────▼──────────────────────────────────────────────────────┐
│  Hardware / external services                                 │
│  SHIBLI-controls :8001 · go2rtc :1984 · RTSP cameras          │
└──────────────────────────────────────────────────────────────┘
```

## Directory layout

```
ShibliC2/
├── launcher.py
├── app/
│   ├── main.py
│   ├── models.py
│   ├── core/          # config, paths, database, settings, modules
│   ├── adapters/      # DeviceAdapter + SHIBLI-controls driver
│   ├── auth/
│   ├── routes/
│   └── services/
├── static/
├── config.example.json
├── scripts/
└── deploy/
```

## Data locations

| Platform | Config, DB, recordings |
|----------|------------------------|
| Dev (Win/Linux) | `./data/` |
| Windows exe | `%LOCALAPPDATA%\ShibliC2/` |
| Linux binary | `~/.local/share/ShibliC2/` |

Override with `SHIBLI_DATA_DIR`.

## What is not in Phase 1

- AI analytics / GPU / ONNX
- GIS / tactical map
- Multi-sensor fusion
- Docker or PostgreSQL as a runtime requirement

Those stubs are archived on branch `cursor/phase-2-3-future-2648` in `future/phase-2-analytics/`, `future/phase-3-gis/`, and `future/phase-4-fusion/`.

## Device adapters

New hardware drivers implement `DeviceAdapter` in `app/adapters/`, then:

```python
register_adapter("my_radar", MyRadarAdapter)
```
