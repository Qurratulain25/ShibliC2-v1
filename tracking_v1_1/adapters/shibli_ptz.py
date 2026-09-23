from __future__ import annotations

from typing import Any, Protocol

from ..follow.controller import PTZCommand


class DeviceGateway(Protocol):
    """
    Minimal interface required from the existing SHIBLI PTZ gateway.

    The adapter deliberately depends only on these existing operations.
    """

    def move_ptz(
        self,
        direction: str,
        speed: str,
        mode: str,
        ptz_id: str | None = None,
        camera_id: str | None = None,
    ) -> dict[str, Any]:
        ...

    def stop_ptz(
        self,
        camera_id: str | None = None,
    ) -> dict[str, Any]:
        ...


class ShibliPTZAdapter:
    """
    Bridge between the v1.1 PTZFollowController and the existing
    SHIBLI hardware gateway.

    This class does not implement PTZ behavior itself. It translates
    v1.1 commands into the existing SHIBLI gateway API.
    """

    def __init__(
        self,
        gateway: DeviceGateway | None = None,
        *,
        ptz_id: str | None = None,
        camera_id: str | None = None,
        mode: str = "rel",
    ) -> None:
        self._gateway = gateway
        self.ptz_id = ptz_id
        self.camera_id = camera_id
        self.mode = mode

    @property
    def gateway(self) -> DeviceGateway:
        """
        Resolve the existing SHIBLI gateway lazily.

        Lazy resolution keeps this isolated adapter from initializing
        the hardware layer merely by importing the module.
        """
        if self._gateway is None:
            from app.hardware import gateway

            self._gateway = gateway

        return self._gateway

    def move(
        self,
        pan: str,
        tilt: str,
        speed: float,
    ) -> dict[str, Any]:
        """
        Translate a normalized v1.1 pan/tilt command into the
        existing SHIBLI gateway direction vocabulary.
        """

        direction = self._direction(pan, tilt)

        if direction == "stop":
            return self.stop()

        speed_name = self._speed_name(speed)

        return self.gateway.move_ptz(
            direction=direction,
            speed=speed_name,
            mode=self.mode,
            ptz_id=self.ptz_id,
            camera_id=self.camera_id,
        )

    def stop(self) -> dict[str, Any]:
        """
        Forward STOP to the existing SHIBLI PTZ gateway.
        """
        return self.gateway.stop_ptz(
            camera_id=self.camera_id,
        )

    @staticmethod
    def _direction(
        pan: str,
        tilt: str,
    ) -> str:
        pan = pan.upper()
        tilt = tilt.upper()

        mapping = {
            ("LEFT", "STOP"): "left",
            ("RIGHT", "STOP"): "right",
            ("STOP", "UP"): "up",
            ("STOP", "DOWN"): "down",
            ("LEFT", "UP"): "up_left",
            ("RIGHT", "UP"): "up_right",
            ("LEFT", "DOWN"): "down_left",
            ("RIGHT", "DOWN"): "down_right",
            ("STOP", "STOP"): "stop",
        }

        try:
            return mapping[(pan, tilt)]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported PTZ combination: pan={pan}, tilt={tilt}"
            ) from exc

    @staticmethod
    def _speed_name(speed: float) -> str:
        """
        Convert the controller's normalized 0..1 speed into
        the speed vocabulary already used by SHIBLI.
        """
        speed = max(0.0, min(1.0, float(speed)))

        if speed < 0.34:
            return "low"

        if speed < 0.67:
            return "medium"

        return "high"