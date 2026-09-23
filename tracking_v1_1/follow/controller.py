from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..models import Track, TrackState


@dataclass(frozen=True)
class FollowTarget:
    """
    Represents the application's currently selected follow target.
    """

    track_id: int


PanDirection = Literal["LEFT", "RIGHT", "STOP"]
TiltDirection = Literal["UP", "DOWN", "STOP"]


@dataclass(frozen=True)
class PTZCommand:
    """
    Simulated PTZ command produced by the follow controller.

    norm_x / norm_y are normalized target-position errors in
    approximately the range [-1.0, +1.0].

    pan_speed / tilt_speed scale with error magnitude.
    """

    pan: PanDirection
    tilt: TiltDirection
    norm_x: float
    norm_y: float
    pan_speed: float
    tilt_speed: float

    @property
    def command_text(self) -> str:
        parts: list[str] = []

        if self.pan != "STOP":
            parts.append(f"PAN {self.pan}")

        if self.tilt != "STOP":
            parts.append(f"TILT {self.tilt}")

        return " + ".join(parts) if parts else "STOP"

    def as_dict(self) -> dict[str, object]:
        return {
            "command": self.command_text,
            "pan": self.pan,
            "tilt": self.tilt,
            "norm_x": self.norm_x,
            "norm_y": self.norm_y,
            "pan_speed": self.pan_speed,
            "tilt_speed": self.tilt_speed,
        }


class PTZFollowController:
    """
    Converts the selected Track position into a PTZ command.

    This class knows only about Track geometry and frame dimensions.
    It does not know anything about YOLO, ByteTrack, or the detector.
    """

    def __init__(self, *, deadband: float = 0.08) -> None:
        if not 0.0 <= deadband < 1.0:
            raise ValueError("deadband must be in the range [0.0, 1.0)")

        self.deadband = deadband

    def update(
        self,
        target: Track | None,
        frame_width: int,
        frame_height: int,
    ) -> PTZCommand:
        """
        Calculate the simulated PTZ response for the selected target.

        A missing or LOST target always produces STOP.
        """

        if frame_width <= 0 or frame_height <= 0:
            raise ValueError("frame dimensions must be positive")

        if target is None or target.state == TrackState.LOST:
            return self._stop()

        x1, y1, x2, y2 = target.bbox

        frame_center_x = frame_width / 2.0
        frame_center_y = frame_height / 2.0

        target_x = (x1 + x2) / 2.0
        target_y = (y1 + y2) / 2.0

        error_x = target_x - frame_center_x
        error_y = target_y - frame_center_y

        norm_x = self._clamp(
            error_x / frame_center_x
        )

        norm_y = self._clamp(
            error_y / frame_center_y
        )

        pan: PanDirection
        tilt: TiltDirection

        if norm_x < -self.deadband:
            pan = "LEFT"
        elif norm_x > self.deadband:
            pan = "RIGHT"
        else:
            pan = "STOP"

        if norm_y < -self.deadband:
            tilt = "UP"
        elif norm_y > self.deadband:
            tilt = "DOWN"
        else:
            tilt = "STOP"

        return PTZCommand(
            pan=pan,
            tilt=tilt,
            norm_x=norm_x,
            norm_y=norm_y,
            pan_speed=abs(norm_x) if pan != "STOP" else 0.0,
            tilt_speed=abs(norm_y) if tilt != "STOP" else 0.0,
        )

    @staticmethod
    def _clamp(value: float) -> float:
        return max(-1.0, min(1.0, value))

    @staticmethod
    def _stop() -> PTZCommand:
        return PTZCommand(
            pan="STOP",
            tilt="STOP",
            norm_x=0.0,
            norm_y=0.0,
            pan_speed=0.0,
            tilt_speed=0.0,
        )