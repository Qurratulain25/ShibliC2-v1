# Approved SHIBLI-controls runtime input

This folder is the **only** approved source used by the Ubuntu and Windows
packagers. It contains Python modules only.

It must never contain:

- `venv/`
- `.env`
- live `data/`
- recordings or logs
- developer home paths

Entry point: `server.py`

Build scripts fail if `server.py` is missing. Set `SHIBLI_CONTROLS_SOURCE` only
when pointing at another approved tree with the same layout.
