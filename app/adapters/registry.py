"""Adapter factory — register new device drivers without changing core API."""
from __future__ import annotations

import os
from typing import Dict, Type

from .base import DeviceAdapter
from .shibli_controls import ShibliControlsAdapter

_REGISTRY: Dict[str, Type[DeviceAdapter]] = {
    "shibli_controls": ShibliControlsAdapter,
    "simulator": ShibliControlsAdapter,
}


def register_adapter(name: str, cls: Type[DeviceAdapter]) -> None:
    _REGISTRY[name] = cls


def build_adapter(name: str | None = None) -> DeviceAdapter:
    adapter_name = name or os.getenv("DEVICE_ADAPTER", "shibli_controls")
    cls = _REGISTRY.get(adapter_name, ShibliControlsAdapter)
    if cls is ShibliControlsAdapter:
        from ..core.config import resolve_jwt_secret

        url = os.getenv("SHIBLI_CONTROLS_URL", "http://127.0.0.1:8001")
        secret = resolve_jwt_secret()
        token = os.getenv("SHIBLI_API_TOKEN", "")
        return ShibliControlsAdapter(url, secret, token)
    return cls()  # type: ignore[call-arg]
