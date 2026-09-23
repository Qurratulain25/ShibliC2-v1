from __future__ import annotations

import cv2
import numpy as np

from ..models import Track, TrackState
from ..playback import (
    VISIBLE_TRACK_STATES,
    current_class_counts,
    current_visible_tracks,
    is_current_visible_track,
    operator_overlay_label,
)

__all__ = [
    "VISIBLE_TRACK_STATES",
    "current_class_counts",
    "current_visible_tracks",
    "is_current_visible_track",
    "DroneAlertGate",
    "TrackOverlay",
]


class DroneAlertGate:
    """
    Emits one alert per newly confirmed visible drone track.

    Repeated ACTIVE/REACQUIRED frames for the same ID do not alert again.
    LOST tracks never alert.
    """

    def __init__(self) -> None:
        self._alerted_ids: set[int] = set()
        self.alert_active = False

    def reset(self) -> None:
        self._alerted_ids.clear()
        self.alert_active = False

    def update(self, tracks: list[Track]) -> list[Track]:
        visible: list[Track] = [
            track
            for track in tracks
            if (
                track.class_name == "drone"
                and track.state in (
                    TrackState.ACTIVE,
                    TrackState.REACQUIRED,
                )
            )
        ]

        self.alert_active = bool(visible)

        newly_detected: list[Track] = []

        for track in visible:
            if track.track_id in self._alerted_ids:
                continue

            self._alerted_ids.add(track.track_id)
            newly_detected.append(track)

        return newly_detected


class TrackOverlay:
    """
    Renders confirmed visible tracks onto a video frame.

    LOST tracks remain in the Track list for diagnostics but are not drawn.
    """

    def __init__(self) -> None:
        self.alert_gate = DroneAlertGate()

    def reset(self) -> None:
        self.alert_gate.reset()

    def render(
        self,
        frame: np.ndarray,
        tracks: list[Track],
        frame_index: int,
        follow_target_id: int | None = None,
    ) -> np.ndarray:
        output = frame.copy()
        self.alert_gate.update(tracks)
        visible_tracks = current_visible_tracks(tracks)

        for track in visible_tracks:
            x1, y1, x2, y2 = map(int, track.bbox)

            is_follow_target = (
                track.track_id == follow_target_id
            )

            if is_follow_target:
                color = (0, 215, 255)
                thickness = 4
            else:
                color = (80, 220, 120)
                thickness = 2

            cv2.rectangle(
                output,
                (x1, y1),
                (x2, y2),
                color,
                thickness,
            )

            label = operator_overlay_label(track)
            label_y = max(20, y1 - 8)

            cv2.putText(
                output,
                label,
                (x1, label_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2,
                cv2.LINE_AA,
            )

        return output
