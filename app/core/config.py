from __future__ import annotations

import json
import os
from typing import Any, Dict

from .paths import config_path

DEFAULT_CONFIG: Dict[str, Any] = {
    "system_name": "SHIBLI Command & Control",
    "site_id": "edge-node-01",
    "site_label": "Border Tower Alpha",
    "phase": 1,
    "streams": {"day_camera": "", "thermal": "", "map": ""},
    "ptz_systems": [
        {"id": "ptz-1", "label": "PTZ System 1", "default": True},
        {"id": "ptz-2", "label": "PTZ System 2", "default": False},
    ],
    "recording": {"retention_days": 30, "mode": "both"},
    "devices": {
        "ptz": {"enabled": True, "adapter": "shibli_controls"},
        "lrf": {"enabled": True, "adapter": "shibli_controls"},
        "illumination": {"enabled": True, "adapter": "shibli_controls"},
    },
    "integrations": {
        "shibli_controls_url": "http://127.0.0.1:8001",
    },
}


def load_config() -> Dict[str, Any]:
    path = config_path()
    if not path.exists():
        return dict(DEFAULT_CONFIG)
    try:
        with path.open("r", encoding="utf-8") as handle:
            merged = {**DEFAULT_CONFIG, **json.load(handle)}
            merged["streams"] = {**DEFAULT_CONFIG["streams"], **merged.get("streams", {})}
            return merged
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_CONFIG)


# Documented development-only JWT fallback — never accepted when SHIBLI_ENV=production.
_DEV_JWT_SECRET = "abracadabra"
_INSECURE_JWT_SECRETS = frozenset({
    "",
    "abracadabra",
    "change-me",
    "change-me-dev-only",
    "replace-with-a-long-random-string",
})


def is_production() -> bool:
    env = (os.getenv("SHIBLI_ENV") or os.getenv("ENV") or "development").strip().lower()
    if env in ("production", "prod"):
        return True
    flag = (os.getenv("SHIBLI_PRODUCTION") or "").strip().lower()
    return flag in ("1", "true", "yes", "on")


def resolve_jwt_secret() -> str:
    """Return JWT signing secret. Fails closed in production if missing/insecure."""
    secret = (os.getenv("SHIBLI_JWT_SECRET") or os.getenv("JWT_SECRET") or "").strip()
    if is_production():
        if not secret or secret.lower() in _INSECURE_JWT_SECRETS or secret == _DEV_JWT_SECRET:
            raise RuntimeError(
                "Production startup refused: set SHIBLI_JWT_SECRET to a unique non-default value "
                "(SHIBLI_ENV=production). Do not use the development JWT secret."
            )
        return secret
    return secret or _DEV_JWT_SECRET
