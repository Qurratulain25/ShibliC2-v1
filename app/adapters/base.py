from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class DeviceAdapter(ABC):
    """Hook for Phase 1+ device drivers. New sensors implement this interface."""

    name: str = "base"

    @abstractmethod
    def move_ptz(self, direction: str, speed: str, mode: str, ptz_id: str | None = None) -> Dict[str, Any]:
        ...

    @abstractmethod
    def lens(self, action: str, ptz_id: str | None = None) -> Dict[str, Any]:
        ...

    @abstractmethod
    def preset(self, action: str, preset: str, ptz_id: str | None = None) -> Dict[str, Any]:
        ...

    @abstractmethod
    def measure_lrf(self, mode: str) -> Dict[str, Any]:
        ...

    @abstractmethod
    def set_illumination(self, **kwargs: Any) -> Dict[str, Any]:
        ...

    @abstractmethod
    def quick_action(self, group: str, action: str) -> Dict[str, Any]:
        ...

    @abstractmethod
    def snapshot(self) -> Dict[str, Any]:
        ...
