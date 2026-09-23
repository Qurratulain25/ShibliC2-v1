from __future__ import annotations

from collections import defaultdict

from .models import Track, TrackState


VISIBLE_TRACK_STATES = (
    TrackState.ACTIVE,
    TrackState.REACQUIRED,
)

VISIBLE_STATE_NAMES = {
    state.value for state in VISIBLE_TRACK_STATES
}


def track_state_name(track: Track | dict) -> str:
    if isinstance(track, dict):
        state = track.get("state", "")
        return getattr(state, "value", state) or ""

    state = getattr(track, "state", "")
    return getattr(state, "value", state) or ""


def is_current_visible_track(track: Track | dict) -> bool:
    return track_state_name(track) in VISIBLE_STATE_NAMES


def current_visible_tracks(
    tracks: list[Track] | list[dict],
) -> list:
    return [
        track
        for track in tracks
        if is_current_visible_track(track)
    ]


def current_history_tracks(
    tracks: list[Track] | list[dict],
) -> list:
    return [
        track
        for track in tracks
        if track_state_name(track) == TrackState.LOST.value
    ]


def current_class_counts(
    tracks: list[Track] | list[dict],
) -> dict[str, int]:
    counts = {
        "person": 0,
        "vehicle": 0,
        "drone": 0,
        "helicopter": 0,
    }

    for track in current_visible_tracks(tracks):
        class_name = (
            track.get("class_name")
            if isinstance(track, dict)
            else track.class_name
        )

        if class_name in counts:
            counts[class_name] += 1

    return counts


def can_select_follow(track: Track | dict) -> bool:
    return is_current_visible_track(track)


def group_records_by_frame(
    records: list[dict],
) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = defaultdict(list)

    for record in records:
        frame = record.get("frame")

        if frame is None:
            continue

        grouped[int(frame)].append(record)

    return dict(grouped)


def records_for_frame(
    records_by_frame: dict[int, list[dict]],
    frame_index: int,
) -> list[dict]:
    return list(records_by_frame.get(frame_index, []))


def overlay_records_for_frame(
    records_by_frame: dict[int, list[dict]],
    frame_index: int,
) -> list[dict]:
    return current_visible_tracks(
        records_for_frame(records_by_frame, frame_index)
    )


def table_records_for_frame(
    records_by_frame: dict[int, list[dict]],
    frame_index: int,
) -> list[dict]:
    return overlay_records_for_frame(
        records_by_frame,
        frame_index,
    )


def format_drone_event(
    clock: str,
    track_id: int,
    confidence: float,
) -> str:
    percent = round(confidence * 100)

    return (
        f"{clock} | DRONE | ID {track_id} | {percent}% | DETECTED"
    )


class PlaybackAlertState:
    """
    Playback-time drone alert gate.

    Alerts only when the current displayed frame contains a confirmed
    ACTIVE or REACQUIRED drone that has not already been announced.
    Historical tracks.json must not be preloaded into alerted IDs.
    """

    def __init__(self) -> None:
        self.alerted_ids: set[int] = set()
        self.alert_active = False
        self.events: list[str] = []
        self.beep_count = 0
        self.latest_new: dict | Track | None = None

    def reset(self) -> None:
        self.alerted_ids.clear()
        self.alert_active = False
        self.events.clear()
        self.beep_count = 0
        self.latest_new = None

    def update(
        self,
        tracks: list[Track] | list[dict],
        *,
        clock: str = "00:00:00",
    ) -> list:
        visible = [
            track
            for track in current_visible_tracks(tracks)
            if (
                (
                    track.get("class_name")
                    if isinstance(track, dict)
                    else track.class_name
                )
                == "drone"
            )
        ]

        self.alert_active = bool(visible)

        newly_detected: list = []

        for track in visible:
            track_id = (
                int(track["track_id"])
                if isinstance(track, dict)
                else int(track.track_id)
            )

            if track_id in self.alerted_ids:
                continue

            confidence = (
                float(track["confidence"])
                if isinstance(track, dict)
                else float(track.confidence)
            )

            self.alerted_ids.add(track_id)
            newly_detected.append(track)
            self.beep_count += 1
            self.events.append(
                format_drone_event(
                    clock,
                    track_id,
                    confidence,
                )
            )

        self.latest_new = (
            newly_detected[0] if newly_detected else None
        )

        return newly_detected


def _class_name(track: Track | dict) -> str:
    if isinstance(track, dict):
        return str(track.get("class_name") or "")

    return str(track.class_name or "")


def operator_overlay_label(track: Track | dict) -> str:
    if _class_name(track) == "drone":
        return "AERIAL TARGET"
    return _class_name(track).upper()


def operator_threat_status(
    tracks: list[Track] | list[dict],
) -> str:
    for track in current_visible_tracks(tracks):
        if _class_name(track) == "drone":
            return "DRONE DETECTED"

    return "NO THREAT"


def operator_ptz_label(
    *,
    following: bool,
    command: str | None,
) -> str:
    text = str(command or "STOP").strip().upper()

    if text in {"", "STOP"}:
        return "FOLLOWING TARGET" if following else "STOPPED"

    return text


def follow_button_available(
    tracks: list[Track] | list[dict],
) -> bool:
    return any(can_select_follow(track) for track in tracks)


def keep_video_paused(status: str | None) -> bool:
    return str(status or "").upper() in {
        "QUEUED",
        "PROCESSING",
    }


def records_to_tracks(records: list[dict]) -> list[Track]:
    tracks: list[Track] = []

    for record in records:
        bbox = [
            float(value)
            for value in record.get("bbox") or [0, 0, 0, 0]
        ]
        center = record.get("center")

        if not center and len(bbox) == 4:
            center = [
                (bbox[0] + bbox[2]) / 2.0,
                (bbox[1] + bbox[3]) / 2.0,
            ]

        tracks.append(
            Track(
                track_id=int(record["track_id"]),
                class_id=int(record["class_id"]),
                class_name=record["class_name"],
                confidence=float(record["confidence"]),
                bbox=bbox,
                center=[float(value) for value in center],
                state=TrackState(record["state"]),
            )
        )

    return tracks
