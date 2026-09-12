"""LAN vs IP/Online connection mode. Administrator-selected — never inferred from IP ranges."""
from __future__ import annotations

from typing import Any, Optional

SESSION_MODES = ("lan", "ip")
CAMERA_MODES = ("lan", "ip", "legacy")
COMPAT_MODES = frozenset({"legacy", "both", ""})

_IP_ALIASES = frozenset({"ip", "online", "ip_online", "iponline", "ip/online"})
_LAN_ALIASES = frozenset({"lan", "local", "ethernet"})
_LEGACY_ALIASES = frozenset({"legacy", "both", "unassigned", "compat"})


def _canon(value: Any) -> str:
    raw = str(value or "").strip().lower()
    out = []
    prev_us = False
    for ch in raw:
        if ch.isalnum():
            out.append(ch)
            prev_us = False
        elif not prev_us:
            out.append("_")
            prev_us = True
    return "".join(out).strip("_")


def normalize_session_mode(value: Any) -> str:
    """Login / session mode. Only lan or ip."""
    v = _canon(value)
    if v in _IP_ALIASES:
        return "ip"
    return "lan"


def normalize_camera_mode(value: Any, *, default: str = "legacy") -> str:
    """Stored camera connection_mode. lan | ip | legacy."""
    v = _canon(value)
    if v in _IP_ALIASES:
        return "ip"
    if v in _LAN_ALIASES:
        return "lan"
    if v in _LEGACY_ALIASES:
        return "legacy"
    if default in CAMERA_MODES:
        return default
    return "legacy"


def camera_matches_mode(cam: Any, mode: Optional[str]) -> bool:
    """True if this camera should be available for the active session mode.

    Records without a reliable classification stay visible in both modes
    until an administrator assigns LAN or IP / Online.
    """
    if not mode:
        return True
    session = normalize_session_mode(mode)
    stored = ""
    if isinstance(cam, dict):
        stored = cam.get("connectionMode") or cam.get("connection_mode") or ""
    else:
        stored = str(cam or "")
    camera_mode = normalize_camera_mode(stored, default="legacy")
    if camera_mode in COMPAT_MODES or camera_mode == "legacy":
        return True
    return camera_mode == session


def connection_mode_label(value: Any) -> str:
    mode = normalize_camera_mode(value, default="legacy")
    if mode == "lan":
        return "LAN"
    if mode == "ip":
        return "IP / Online"
    return "Unassigned"
