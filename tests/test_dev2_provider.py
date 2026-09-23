from __future__ import annotations

import pytest 
from types import SimpleNamespace

import numpy as np

from tracking_v1_1.models import (
    CLASS_ID_BY_NAME,
    TrackState,
)
from tracking_v1_1.providers.dev2 import (
    Dev2TrackingProvider,
)
from tracking_v1_1.follow import FollowManager

class FakeValue:
    def __init__(self, value):
        self._value = value

    def item(self):
        return self._value

    def tolist(self):
        return self._value


class FakeBoxes:
    def __init__(
        self,
        track_ids,
        xyxy,
        confidences,
        class_ids,
    ):
        if track_ids is None:
            self.id = None
        else:
            self.id = np.array(
                track_ids,
                dtype=np.float32,
            )

        self.xyxy = np.array(
            xyxy,
            dtype=np.float32,
        )

        self.conf = np.array(
            confidences,
            dtype=np.float32,
        )

        self.cls = np.array(
            class_ids,
            dtype=np.float32,
        )


class FakeResult:
    def __init__(self, boxes):
        self.boxes = boxes
        self.names = {
            0: "drone",
            1: "helicopter",
        }


class FakeYOLO:
    def __init__(self, frames):
        self.frames = iter(frames)
        self.names = {
            0: "drone",
            1: "helicopter",
        }
        self.predictor = None
        self.track_calls = []

    def track(
        self,
        *,
        source,
        persist,
        tracker,
        verbose,
        classes=None,
        conf=None,
        imgsz=None,
    ):
        self.track_calls.append(
            {
                "source": source,
                "persist": persist,
                "tracker": tracker,
                "verbose": verbose,
                "classes": classes,
                "conf": conf,
                "imgsz": imgsz,
            }
        )

        return [next(self.frames)]


def make_result(track_id, class_id=0, confidence=0.85, xyxy=None):
    if xyxy is None:
        xyxy = [10.0, 20.0, 30.0, 40.0]

    return FakeResult(
        FakeBoxes(
            track_ids=[track_id],
            xyxy=[xyxy],
            confidences=[confidence],
            class_ids=[class_id],
        )
    )


def make_multi_result(detections):
    return FakeResult(
        FakeBoxes(
            track_ids=[
                item["track_id"]
                for item in detections
            ],
            xyxy=[
                item["xyxy"]
                for item in detections
            ],
            confidences=[
                item["confidence"]
                for item in detections
            ],
            class_ids=[
                item.get("class_id", 0)
                for item in detections
            ],
        )
    )


def make_provider(monkeypatch, tmp_path, frames):
    fake_model = FakeYOLO(frames)

    monkeypatch.setattr(
        "tracking_v1_1.providers.dev2.YOLO",
        lambda _: fake_model,
    )

    model_path = tmp_path / "rgb_best_v1.pt"
    model_path.touch()

    provider = Dev2TrackingProvider(
        "rgb",
        model_dir=tmp_path,
    )

    return provider, fake_model


def blank_frame():
    return np.zeros(
        (100, 100, 3),
        dtype=np.uint8,
    )


def make_empty_result():
    return FakeResult(
        FakeBoxes(
            track_ids=[],
            xyxy=[],
            confidences=[],
            class_ids=[],
        )
    )


def make_result_without_id(class_id=0, confidence=0.85):
    return FakeResult(
        FakeBoxes(
            track_ids=None,
            xyxy=[
                [10.0, 20.0, 30.0, 40.0]
            ],
            confidences=[confidence],
            class_ids=[class_id],
        )
    )


def test_dev2_track_contract(monkeypatch, tmp_path):
    frames = [
        make_result(7, class_id=0),
        make_result(7, class_id=0),
    ]

    provider, _ = make_provider(
        monkeypatch,
        tmp_path,
        frames,
    )

    frame = blank_frame()

    assert provider.process_frame(frame) == []

    tracks = provider.process_frame(frame)

    assert len(tracks) == 1

    track = tracks[0]

    assert track.track_id == 7
    assert track.class_id == CLASS_ID_BY_NAME["drone"]
    assert track.class_id == 2
    assert track.class_name == "drone"
    assert track.confidence == pytest.approx(0.85)
    assert track.bbox == [10.0, 20.0, 30.0, 40.0]
    assert track.center == [20.0, 30.0]
    assert track.state == TrackState.ACTIVE


def test_dev2_track_lifecycle_across_multiple_lost_frames(
    monkeypatch,
    tmp_path,
):
    frames = [
        make_result(7, class_id=0),
        make_result(7, class_id=0),
        make_empty_result(),
        make_empty_result(),
        make_empty_result(),
        make_result(7, class_id=0),
        make_result(7, class_id=0),
    ]

    provider, _ = make_provider(
        monkeypatch,
        tmp_path,
        frames,
    )

    frame = blank_frame()

    first_hidden = provider.process_frame(frame)
    first = provider.process_frame(frame)
    lost_1 = provider.process_frame(frame)
    lost_2 = provider.process_frame(frame)
    lost_3 = provider.process_frame(frame)
    reacquired = provider.process_frame(frame)
    active_again = provider.process_frame(frame)

    assert first_hidden == []

    assert first[0].state == TrackState.ACTIVE

    assert lost_1[0].track_id == 7
    assert lost_1[0].state == TrackState.LOST

    assert lost_2[0].track_id == 7
    assert lost_2[0].state == TrackState.LOST

    assert lost_3[0].track_id == 7
    assert lost_3[0].state == TrackState.LOST

    assert reacquired[0].track_id == 7
    assert reacquired[0].state == TrackState.REACQUIRED

    assert active_again[0].track_id == 7
    assert active_again[0].state == TrackState.ACTIVE


def test_dev2_thermal_provider_uses_thermal_checkpoint(
    monkeypatch,
    tmp_path,
):
    model_path = (
        tmp_path / "thermal_best_v1.pt"
    )
    model_path.touch()

    captured = {}

    def fake_yolo(path):
        captured["path"] = path

        return FakeYOLO([])

    monkeypatch.setattr(
        "tracking_v1_1.providers.dev2.YOLO",
        fake_yolo,
    )

    Dev2TrackingProvider(
        "thermal",
        model_dir=tmp_path,
    )

    assert captured["path"] == str(
        model_path.resolve()
    )


def test_dev2_lost_state_allows_follow_manager_to_wait_and_reacquire(
    monkeypatch,
    tmp_path,
):
    frames = [
        make_result(7, class_id=0),
        make_result(7, class_id=0),
        make_empty_result(),
        make_result(7, class_id=0),
        make_result(7, class_id=0),
    ]

    provider, _ = make_provider(
        monkeypatch,
        tmp_path,
        frames,
    )

    current_time = [100.0]

    def clock():
        return current_time[0]

    manager = FollowManager(
        lost_timeout=2.0,
        clock=clock,
    )

    frame = blank_frame()

    assert provider.process_frame(frame) == []

    active = provider.process_frame(frame)
    manager.update(active)
    manager.select_track(7)

    current_time[0] = 100.5

    lost = provider.process_frame(frame)
    manager.update(lost)

    assert lost[0].state == TrackState.LOST
    assert manager.active_track_id == 7
    assert manager.target_is_waiting is True
    assert manager.get_active_track() is None

    current_time[0] = 101.0

    reacquired = provider.process_frame(frame)
    manager.update(reacquired)

    assert reacquired[0].state == TrackState.REACQUIRED
    assert manager.active_track_id == 7
    assert manager.target_is_waiting is False
    assert manager.get_active_track() is not None
    assert manager.get_active_track().track_id == 7


def test_dev2_uses_bytetrack(
    monkeypatch,
    tmp_path,
):
    frames = [
        make_result(7, class_id=0),
    ]

    provider, fake_model = make_provider(
        monkeypatch,
        tmp_path,
        frames,
    )

    frame = blank_frame()

    provider.process_frame(frame)

    assert len(fake_model.track_calls) == 1

    call = fake_model.track_calls[0]

    assert call["persist"] is True
    assert call["verbose"] is False
    assert call["classes"] == [0]
    assert call["conf"] == pytest.approx(0.15)
    assert call["imgsz"] == 960
    assert call["tracker"] == "bytetrack.yaml"
    assert provider.tracker == "bytetrack.yaml"


def test_local_class_0_maps_to_shibli_drone(
    monkeypatch,
    tmp_path,
):
    frames = [
        make_result(11, class_id=0),
        make_result(11, class_id=0),
    ]

    provider, _ = make_provider(
        monkeypatch,
        tmp_path,
        frames,
    )

    frame = blank_frame()

    provider.process_frame(frame)
    tracks = provider.process_frame(frame)

    assert len(tracks) == 1
    assert tracks[0].class_id == 2
    assert tracks[0].class_name == "drone"


def test_helicopter_class_suppressed_in_drone_only_mode(
    monkeypatch,
    tmp_path,
):
    frames = [
        make_result(8, class_id=1),
        make_result(8, class_id=1),
        make_result(8, class_id=1),
        make_result(8, class_id=1),
        make_result(8, class_id=1),
    ]

    provider, fake_model = make_provider(
        monkeypatch,
        tmp_path,
        frames,
    )

    frame = blank_frame()

    for _ in range(5):
        tracks = provider.process_frame(frame)
        assert tracks == []

    assert fake_model.track_calls[0]["classes"] == [0]


def test_confidence_below_threshold_is_rejected(
    monkeypatch,
    tmp_path,
):
    frames = [
        make_result(9, class_id=0, confidence=0.14),
        make_result(9, class_id=0, confidence=0.14),
        make_result(9, class_id=0, confidence=0.10),
        make_result(9, class_id=0, confidence=0.14),
        make_result(9, class_id=0, confidence=0.14),
    ]

    provider, _ = make_provider(
        monkeypatch,
        tmp_path,
        frames,
    )

    frame = blank_frame()

    for _ in range(5):
        tracks = provider.process_frame(frame)
        assert tracks == []


def test_confidence_at_threshold_is_accepted_as_candidate(
    monkeypatch,
    tmp_path,
):
    frames = [
        make_result(9, class_id=0, confidence=0.15),
        make_result(9, class_id=0, confidence=0.15),
    ]

    provider, _ = make_provider(
        monkeypatch,
        tmp_path,
        frames,
    )

    frame = blank_frame()

    first = provider.process_frame(frame)
    second = provider.process_frame(frame)

    assert first == []
    assert len(second) == 1
    assert second[0].confidence == pytest.approx(0.15)
    assert second[0].state == TrackState.ACTIVE
    assert second[0].class_name == "drone"


def test_one_candidate_hit_remains_tentative(
    monkeypatch,
    tmp_path,
):
    frames = [
        make_result(7, class_id=0),
    ]

    provider, _ = make_provider(
        monkeypatch,
        tmp_path,
        frames,
    )

    tracks = provider.process_frame(blank_frame())

    assert tracks == []


def test_second_hit_within_window_confirms(
    monkeypatch,
    tmp_path,
):
    frames = [
        make_result(7, class_id=0),
        make_result(7, class_id=0),
    ]

    provider, _ = make_provider(
        monkeypatch,
        tmp_path,
        frames,
    )

    frame = blank_frame()

    assert provider.process_frame(frame) == []

    tracks = provider.process_frame(frame)

    assert len(tracks) == 1
    assert tracks[0].track_id == 7
    assert tracks[0].state == TrackState.ACTIVE
    assert tracks[0].class_name == "drone"


def test_one_missing_frame_between_hits_still_confirms(
    monkeypatch,
    tmp_path,
):
    # frame 100 observed, 101 missing, 102 observed -> confirmed
    frames = [
        make_result(7, class_id=0),
        make_empty_result(),
        make_result(7, class_id=0),
    ]

    provider, _ = make_provider(
        monkeypatch,
        tmp_path,
        frames,
    )

    frame = blank_frame()

    assert provider.process_frame(frame) == []
    assert provider.process_frame(frame) == []

    tracks = provider.process_frame(frame)

    assert len(tracks) == 1
    assert tracks[0].track_id == 7
    assert tracks[0].state == TrackState.ACTIVE
    assert 7 not in provider._tentative_hits
    assert 7 in provider._confirmed_track_ids


def test_expired_tentative_candidate_does_not_confirm(
    monkeypatch,
    tmp_path,
):
    # frame 100 hit, frames 101-104 missing, frame 105 hit.
    # current_frame - hit_frame >= 4 expires the first hit.
    frames = [
        make_result(7, class_id=0),
        make_empty_result(),
        make_empty_result(),
        make_empty_result(),
        make_empty_result(),
        make_result(7, class_id=0),
    ]

    provider, _ = make_provider(
        monkeypatch,
        tmp_path,
        frames,
    )

    frame = blank_frame()

    assert provider.process_frame(frame) == []
    assert list(provider._tentative_hits[7]) == [0]

    assert provider.process_frame(frame) == []
    assert provider.process_frame(frame) == []
    assert provider.process_frame(frame) == []
    assert provider.process_frame(frame) == []
    assert 7 not in provider._tentative_hits

    assert provider.process_frame(frame) == []
    assert list(provider._tentative_hits[7]) == [5]
    assert 7 not in provider._confirmed_track_ids


def test_tentative_track_never_reaches_follow_manager(
    monkeypatch,
    tmp_path,
):
    frames = [
        make_result(7, class_id=0),
        make_result(7, class_id=0),
    ]

    provider, _ = make_provider(
        monkeypatch,
        tmp_path,
        frames,
    )

    manager = FollowManager()
    frame = blank_frame()

    first = provider.process_frame(frame)
    manager.update(first)

    assert first == []
    assert manager.tracks == []
    assert manager.active_track_id is None

    manager.enable_auto_follow()
    assert manager.active_track_id is None

    second = provider.process_frame(frame)
    manager.update(second)

    assert len(second) == 1
    assert second[0].state == TrackState.ACTIVE
    assert manager.tracks[0].track_id == 7


def test_confirmed_lost_and_reacquired_behavior_still_works(
    monkeypatch,
    tmp_path,
):
    frames = [
        make_result(7, class_id=0),
        make_result(7, class_id=0),
        make_empty_result(),
        make_result(7, class_id=0),
        make_result(7, class_id=0),
    ]

    provider, _ = make_provider(
        monkeypatch,
        tmp_path,
        frames,
    )

    frame = blank_frame()

    assert provider.process_frame(frame) == []

    confirmed = provider.process_frame(frame)
    lost = provider.process_frame(frame)
    reacquired = provider.process_frame(frame)
    active_again = provider.process_frame(frame)

    assert confirmed[0].state == TrackState.ACTIVE
    assert lost[0].state == TrackState.LOST
    assert lost[0].track_id == 7
    assert reacquired[0].state == TrackState.REACQUIRED
    assert reacquired[0].track_id == 7
    assert active_again[0].state == TrackState.ACTIVE
    assert active_again[0].track_id == 7


def test_detections_without_track_id_are_not_returned(
    monkeypatch,
    tmp_path,
):
    frames = [
        make_result_without_id(),
        make_result_without_id(),
        make_result_without_id(),
    ]

    provider, _ = make_provider(
        monkeypatch,
        tmp_path,
        frames,
    )

    frame = blank_frame()

    for _ in range(3):
        assert provider.process_frame(frame) == []


def test_reset_clears_confirmation_state(
    monkeypatch,
    tmp_path,
):
    frames = [
        make_result(7, class_id=0),
        make_result(7, class_id=0),
        make_result(7, class_id=0),
        make_result(7, class_id=0),
    ]

    provider, fake_model = make_provider(
        monkeypatch,
        tmp_path,
        frames,
    )

    class FakeTracker:
        def __init__(self):
            self.reset_calls = 0

        def reset(self):
            self.reset_calls += 1

    fake_tracker = FakeTracker()
    fake_model.predictor = SimpleNamespace(
        trackers=[fake_tracker],
        vid_path="clip.mp4",
    )

    frame = blank_frame()

    assert provider.process_frame(frame) == []
    tracks = provider.process_frame(frame)

    assert tracks[0].state == TrackState.ACTIVE
    assert 7 in provider._confirmed_track_ids

    provider.reset()

    assert provider._tentative_hits == {}
    assert provider._confirmed_track_ids == set()
    assert provider._lost_track_ids == set()
    assert provider._previous_track_ids == set()
    assert provider._last_tracks == {}
    assert provider._frame_index == -1
    assert fake_tracker.reset_calls == 1
    assert fake_model.predictor.vid_path is None

    assert provider.process_frame(frame) == []


OVERLAPPING_DRONE_A = {
    "track_id": 1,
    "class_id": 0,
    "confidence": 0.4655,
    "xyxy": [130.85, 23.50, 193.44, 63.75],
}

OVERLAPPING_DRONE_B = {
    "track_id": 2,
    "class_id": 0,
    "confidence": 0.2270,
    "xyxy": [136.33, 27.47, 187.86, 60.73],
}

SEPARATE_DRONE_A = {
    "track_id": 1,
    "class_id": 0,
    "confidence": 0.80,
    "xyxy": [10.0, 10.0, 50.0, 50.0],
}

SEPARATE_DRONE_B = {
    "track_id": 2,
    "class_id": 0,
    "confidence": 0.70,
    "xyxy": [200.0, 180.0, 250.0, 230.0],
}


def test_overlapping_duplicate_keeps_highest_confidence():
    kept = Dev2TrackingProvider._suppress_duplicate_candidates(
        [
            {
                "track_id": OVERLAPPING_DRONE_A["track_id"],
                "class_name": "drone",
                "confidence": OVERLAPPING_DRONE_A["confidence"],
                "bbox": OVERLAPPING_DRONE_A["xyxy"],
            },
            {
                "track_id": OVERLAPPING_DRONE_B["track_id"],
                "class_name": "drone",
                "confidence": OVERLAPPING_DRONE_B["confidence"],
                "bbox": OVERLAPPING_DRONE_B["xyxy"],
            },
        ]
    )

    assert len(kept) == 1
    assert kept[0]["track_id"] == 1
    assert kept[0]["confidence"] == pytest.approx(0.4655)


def test_lower_confidence_duplicate_does_not_enter_confirmation(
    monkeypatch,
    tmp_path,
):
    frames = [
        make_multi_result(
            [
                OVERLAPPING_DRONE_A,
                OVERLAPPING_DRONE_B,
            ]
        ),
        make_multi_result(
            [
                OVERLAPPING_DRONE_A,
                OVERLAPPING_DRONE_B,
            ]
        ),
    ]

    provider, _ = make_provider(
        monkeypatch,
        tmp_path,
        frames,
    )

    frame = blank_frame()

    first = provider.process_frame(frame)

    assert first == []
    assert 1 in provider._tentative_hits
    assert 2 not in provider._tentative_hits

    second = provider.process_frame(frame)

    assert len(second) == 1
    assert second[0].track_id == 1
    assert second[0].class_name == "drone"
    assert second[0].state == TrackState.ACTIVE
    assert 2 not in provider._confirmed_track_ids


def test_spatially_separated_drones_both_survive(
    monkeypatch,
    tmp_path,
):
    frames = [
        make_multi_result(
            [
                SEPARATE_DRONE_A,
                SEPARATE_DRONE_B,
            ]
        ),
        make_multi_result(
            [
                SEPARATE_DRONE_A,
                SEPARATE_DRONE_B,
            ]
        ),
    ]

    provider, _ = make_provider(
        monkeypatch,
        tmp_path,
        frames,
    )

    frame = blank_frame()

    assert provider.process_frame(frame) == []

    tracks = provider.process_frame(frame)
    ids = {
        track.track_id
        for track in tracks
    }

    assert ids == {1, 2}
    assert all(
        track.state == TrackState.ACTIVE
        for track in tracks
    )


def test_retained_duplicate_winner_still_requires_confirmation(
    monkeypatch,
    tmp_path,
):
    frames = [
        make_multi_result(
            [
                OVERLAPPING_DRONE_A,
                OVERLAPPING_DRONE_B,
            ]
        ),
    ]

    provider, _ = make_provider(
        monkeypatch,
        tmp_path,
        frames,
    )

    tracks = provider.process_frame(blank_frame())

    assert tracks == []
    assert 1 in provider._tentative_hits
    assert 1 not in provider._confirmed_track_ids


def test_suppressed_duplicate_id_does_not_generate_another_alert(
    monkeypatch,
    tmp_path,
):
    from tracking_v1_1.output.overlay import DroneAlertGate

    frames = [
        make_multi_result(
            [
                OVERLAPPING_DRONE_A,
                OVERLAPPING_DRONE_B,
            ]
        ),
        make_multi_result(
            [
                OVERLAPPING_DRONE_A,
                OVERLAPPING_DRONE_B,
            ]
        ),
        make_multi_result(
            [
                OVERLAPPING_DRONE_A,
                OVERLAPPING_DRONE_B,
            ]
        ),
    ]

    provider, _ = make_provider(
        monkeypatch,
        tmp_path,
        frames,
    )

    gate = DroneAlertGate()
    frame = blank_frame()

    alerts = []

    for _ in range(3):
        tracks = provider.process_frame(frame)
        alerts.extend(gate.update(tracks))

    assert [track.track_id for track in alerts] == [1]
    assert 2 not in {
        track.track_id
        for track in alerts
    }


def test_mock_tracking_provider_behavior_remains_intact():
    from tracking_v1_1.providers.mock import MockTrackingProvider

    provider = MockTrackingProvider()

    tracks = provider.process_frame(None)

    assert len(tracks) == 4

    classes = {
        track.class_name: track.class_id
        for track in tracks
    }

    assert classes == {
        "person": 0,
        "vehicle": 1,
        "drone": 2,
        "helicopter": 3,
    }

    assert all(
        track.state == TrackState.ACTIVE
        for track in tracks
    )