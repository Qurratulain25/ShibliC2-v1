"""Phase 1 UI module registry."""
from __future__ import annotations

from typing import Any, Dict, List

PHASE_MODULES: List[Dict[str, Any]] = [
    {
        "id": "dashboard",
        "label": "Operations Dashboard",
        "phase": 1,
        "enabled": True,
        "icon": "grid",
    },
    {
        "id": "recordings",
        "label": "Recordings",
        "phase": 1,
        "enabled": True,
        "icon": "film",
    },
    {
        "id": "cameras",
        "label": "Cameras",
        "phase": 1,
        "enabled": True,
        "icon": "camera",
    },
    {
        "id": "users",
        "label": "User Management",
        "phase": 1,
        "enabled": True,
        "icon": "users",
        "admin_only": True,
    },
    {
        "id": "audit",
        "label": "Audit Logs",
        "phase": 1,
        "enabled": True,
        "icon": "audit",
        "admin_only": True,
    },
    {
        "id": "settings",
        "label": "System Settings",
        "phase": 1,
        "enabled": True,
        "icon": "gear",
    },
]


def list_modules(current_phase: int = 1) -> List[Dict[str, Any]]:
    return [
        {
            **module,
            "available": module["phase"] <= current_phase and module.get("enabled", False),
            "admin_only": module.get("admin_only", False),
        }
        for module in PHASE_MODULES
        if module["phase"] <= current_phase
    ]
