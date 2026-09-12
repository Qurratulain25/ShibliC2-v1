"""Application settings persisted in encrypted SQLite."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List

from .database import get_db, set_setting
from .paths import data_dir, recordings_dir, resolve_recording_path

_seeded = False
_seed_lock = threading.Lock()
_settings_cache: Dict[str, Any] | None = None
_settings_lock = threading.Lock()

DEFAULT_SETTINGS: Dict[str, Any] = {
    "theme": "dark",
    "recording_path": str(recordings_dir()),
    "keyboard_enabled": True,
    "keyboard_map": {
        "w": "ptz_up", "s": "ptz_down", "a": "ptz_left", "d": "ptz_right",
        "q": "zoom_out", "e": "zoom_in", "r": "toggle_record", "f": "fullscreen",
        " ": "ptz_stop", "1": "ptz_system_1", "2": "ptz_system_2", "escape": "exit_fullscreen",
    },
    "ptz_systems": [
        {"id": "ptz-1", "label": "PTZ 1 - Day Camera", "default": True},
        {"id": "ptz-2", "label": "PTZ 2 - Thermal Camera", "default": False},
    ],
    "layouts": {
        "presets": ["day_thermal", "day_full", "thermal_full", "custom"],
        "custom": [],
    },
    "default_page_size": 20,
    "app_port": 8080,
    "service_urls": {
        "core": "http://127.0.0.1:3000",
        "controls": "http://127.0.0.1:8001",
        "vss": "http://127.0.0.1:8000",
    },
    "device_drivers": {
        "ptz": "shibli_controls",
        "lrf": "shibli_controls",
        "illumination": "shibli_controls",
    },
    "ptz_method": "onvif",
    "lrf_method": "none",
    "illuminator_method": "none",
    "hw_simulate": False,
    "default_layout": "day_thermal",
    "retention_days": 30,
    "osd_config": {
        "show_telemetry": True,
        "show_logo": True,
        "logo_text": "SHIBLI C2",
        "custom_text": "",
        "position": "bottom-left",
    },
    "database_path": str(data_dir() / "shibli_c2.db"),
}


def seed_defaults() -> None:
    """Idempotent — one DB pass, not N open/close cycles per key."""
    global _seeded
    if _seeded:
        return
    with _seed_lock:
        if _seeded:
            return
        now = datetime.now(timezone.utc).isoformat()
        with get_db() as conn:
            existing = {
                r["key"] for r in conn.execute("SELECT key FROM app_settings").fetchall()
            }
            for key, value in DEFAULT_SETTINGS.items():
                if key in existing:
                    continue
                conn.execute(
                    "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
                    (key, json.dumps(value), now),
                )
            path_row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                ("recording_path",),
            ).fetchone()
        configured = None
        if path_row:
            try:
                configured = json.loads(path_row["value"])
            except json.JSONDecodeError:
                configured = path_row["value"]
        if configured:
            resolve_recording_path(configured, repair_db=True)
        _seeded = True


def invalidate_settings_cache() -> None:
    global _settings_cache
    with _settings_lock:
        _settings_cache = None


def get_all_settings() -> Dict[str, Any]:
    global _settings_cache
    with _settings_lock:
        if _settings_cache is not None:
            return dict(_settings_cache)
    seed_defaults()
    result = dict(DEFAULT_SETTINGS)
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
        for row in rows:
            try:
                result[row["key"]] = json.loads(row["value"])
            except json.JSONDecodeError:
                result[row["key"]] = row["value"]
    result["database_path"] = str(data_dir() / "shibli_c2.db")
    configured = result.get("recording_path")
    result["recording_path"] = str(resolve_recording_path(configured, repair_db=True))
    with _settings_lock:
        _settings_cache = dict(result)
    return dict(result)


def update_settings(patch: Dict[str, Any]) -> Dict[str, Any]:
    allowed = set(DEFAULT_SETTINGS.keys()) - {"database_path"}
    for key, value in patch.items():
        if key in allowed:
            set_setting(key, value)
    invalidate_settings_cache()
    return get_all_settings()


def reset_to_defaults() -> Dict[str, Any]:
    global _seeded
    with get_db() as conn:
        conn.execute("DELETE FROM app_settings")
    _seeded = False
    invalidate_settings_cache()
    seed_defaults()
    return get_all_settings()
