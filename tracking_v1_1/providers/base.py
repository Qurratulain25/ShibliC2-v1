from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models import Track


class TrackingProvider(ABC):
    """
    Stable v1.1 boundary between SHIBLI and the vision implementation.

    The application depends only on:
        provider.process_frame(frame) -> list[Track]

    The provider implementation may use any detector, tracker,
    inference runtime, model, or hardware acceleration.
    """

    @abstractmethod
    def process_frame(self, frame: Any) -> list[Track]:
        raise NotImplementedError

    def reset(self) -> None:
        """
        Reset provider/tracker state between processing sessions.

        Providers that maintain internal tracking state may override this.
        """
        pass