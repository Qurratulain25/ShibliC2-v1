from __future__ import annotations

from typing import Any

from .base import TrackingProvider
from ..models import Track, TrackState


class MockTrackingProvider(TrackingProvider):
    """
    Deterministic development provider for the v1.1 POC.

    This provider does not perform AI detection or tracking. It simulates
    four tracked objects whose bounding boxes move over successive frames.

    Canonical objects:
        1 -> person
        2 -> vehicle
        3 -> drone
        4 -> helicopter

    Track 3 periodically transitions:
        ACTIVE -> LOST -> REACQUIRED

    Other tracks continue independently while track 3 is lost.
    """

    def __init__(self) -> None:
        self._frame_index = 0

    def reset(self) -> None:
        self._frame_index = 0

    def process_frame(self, frame: Any) -> list[Track]:
        """
        Return simulated tracks for the current frame and advance
        the internal simulation state.

        When a real frame is supplied, its dimensions are used so the
        simulated boxes remain inside that frame.

        Some existing contract tests intentionally pass None, so a
        deterministic fallback frame size is used in that case.
        """
        frame_index = self._frame_index
        self._frame_index += 1

        frame_width = 640
        frame_height = 480

        if frame is not None:
            shape = getattr(frame, "shape", None)

            if shape is not None and len(shape) >= 2:
                frame_height = int(shape[0])
                frame_width = int(shape[1])

        return [
            self._person(
                frame_index,
                frame_width,
                frame_height,
            ),
            self._vehicle(
                frame_index,
                frame_width,
                frame_height,
            ),
            self._drone(
                frame_index,
                frame_width,
                frame_height,
            ),
            self._helicopter(
                frame_index,
                frame_width,
                frame_height,
            ),
        ]

    def _person(
        self,
        frame_index: int,
        frame_width: int,
        frame_height: int,
    ) -> Track:
        width = 80.0
        height = 180.0

        x1 = self._ping_pong(
            frame_index,
            20.0,
            max(20.0, frame_width - width - 20.0),
            3.0,
        )

        y1 = self._ping_pong(
            frame_index,
            20.0,
            max(20.0, frame_height - height - 20.0),
            1.0,
        )

        return self._make_track(
            track_id=1,
            class_id=0,
            class_name="person",
            confidence=0.91,
            x1=x1,
            y1=y1,
            width=width,
            height=height,
            state=TrackState.ACTIVE,
        )


    def _vehicle(
        self,
        frame_index: int,
        frame_width: int,
        frame_height: int,
    ) -> Track:
        width = 160.0
        height = 90.0

        x1 = self._ping_pong(
            frame_index,
            20.0,
            max(20.0, frame_width - width - 20.0),
            2.0,
        )

        y1 = self._ping_pong(
            frame_index,
            20.0,
            max(20.0, frame_height - height - 20.0),
            1.5,
        )

        return self._make_track(
            track_id=2,
            class_id=1,
            class_name="vehicle",
            confidence=0.88,
            x1=x1,
            y1=y1,
            width=width,
            height=height,
            state=TrackState.ACTIVE,
        )


    def _drone(
        self,
        frame_index: int,
        frame_width: int,
        frame_height: int,
    ) -> Track:
        width = 80.0
        height = 60.0

        x1 = self._ping_pong(
            frame_index,
            20.0,
            max(20.0, frame_width - width - 20.0),
            2.5,
        )

        y1 = self._ping_pong(
            frame_index,
            20.0,
            max(20.0, frame_height - height - 20.0),
            0.5,
        )

        state = self._drone_state(frame_index)

        return self._make_track(
            track_id=3,
            class_id=2,
            class_name="drone",
            confidence=0.87,
            x1=x1,
            y1=y1,
            width=width,
            height=height,
            state=state,
        )


    def _helicopter(
        self,
        frame_index: int,
        frame_width: int,
        frame_height: int,
    ) -> Track:
        width = 180.0
        height = 100.0

        x1 = self._ping_pong(
            frame_index,
            20.0,
            max(20.0, frame_width - width - 20.0),
            1.5,
        )

        y1 = self._ping_pong(
            frame_index,
            20.0,
            max(20.0, frame_height - height - 20.0),
            1.0,
        )

        return self._make_track(
            track_id=4,
            class_id=3,
            class_name="helicopter",
            confidence=0.93,
            x1=x1,
            y1=y1,
            width=width,
            height=height,
            state=TrackState.ACTIVE,
        )

    @staticmethod
    def _ping_pong(
        frame_index: int,
        minimum: float,
        maximum: float,
        speed: float,
    ) -> float:
        """
        Move smoothly between minimum and maximum forever.
        """

        if maximum <= minimum:
            return minimum

        distance = maximum - minimum
        cycle = distance * 2.0

        position = (
            frame_index * speed
        ) % cycle

        if position <= distance:
            return minimum + position

        return maximum - (position - distance)
        
    @staticmethod
    def _drone_state(frame_index: int) -> TrackState:
        """
        Simulate:
            ACTIVE -> LOST -> REACQUIRED

        Frames 20-24 are LOST.
        Frame 25 is REACQUIRED.
        All other frames are ACTIVE.
        """
        cycle_position = frame_index % 40

        if 20 <= cycle_position <= 24:
            return TrackState.LOST

        if cycle_position == 25:
            return TrackState.REACQUIRED

        return TrackState.ACTIVE

    @staticmethod
    def _make_track(
        *,
        track_id: int,
        class_id: int,
        class_name: str,
        confidence: float,
        x1: float,
        y1: float,
        width: float,
        height: float,
        state: TrackState,
    ) -> Track:
        x2 = x1 + width
        y2 = y1 + height

        return Track(
            track_id=track_id,
            class_id=class_id,
            class_name=class_name,
            confidence=confidence,
            bbox=[x1, y1, x2, y2],
            center=[
                (x1 + x2) / 2.0,
                (y1 + y2) / 2.0,
            ],
            state=state,
        )