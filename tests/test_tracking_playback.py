from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tracking_v1_1 import Track, TrackState
from tracking_v1_1.follow import FollowManager
from tracking_v1_1.output import TrackOverlay
from tracking_v1_1.playback import (
    PlaybackAlertState,
    can_select_follow,
    current_class_counts,
    current_history_tracks,
    current_visible_tracks,
    group_records_by_frame,
    overlay_records_for_frame,
    table_records_for_frame,
)
from tracking_v1_1.processor import ProcessingResult
from tracking_v1_1 import routes as tracking_routes


def _track_record(
    *,
    frame: int,
    track_id: int,
    state: str,
    class_name: str = "drone",
    class_id: int = 2,
    confidence: float = 0.32,
) -> dict:
    return {
        "frame": frame,
        "track_id": track_id,
        "class_id": class_id,
        "class_name": class_name,
        "confidence": confidence,
        "bbox": [10.0, 10.0, 40.0, 40.0],
        "center": [25.0, 25.0],
        "state": state,
    }


def _make_track(
    *,
    track_id: int,
    state: TrackState,
    class_name: str = "drone",
    class_id: int = 2,
    confidence: float = 0.32,
) -> Track:
    return Track(
        track_id=track_id,
        class_id=class_id,
        class_name=class_name,
        confidence=confidence,
        bbox=[40.0, 40.0, 140.0, 120.0],
        center=[90.0, 80.0],
        state=state,
    )


def test_active_current_frame_track_is_rendered():
    records = [
        _track_record(frame=4, track_id=6, state="ACTIVE"),
        _track_record(frame=4, track_id=7, state="LOST"),
    ]
    grouped = group_records_by_frame(records)
    visible = overlay_records_for_frame(grouped, 4)

    assert [item["track_id"] for item in visible] == [6]
    assert current_visible_tracks(records)[0]["state"] == "ACTIVE"

    overlay = TrackOverlay()
    frame = np.zeros((180, 240, 3), dtype=np.uint8)
    blank = overlay.render(frame.copy(), [], 4)
    drawn = overlay.render(
        frame.copy(),
        [_make_track(track_id=6, state=TrackState.ACTIVE)],
        4,
    )

    assert not np.array_equal(drawn, blank)


def test_reacquired_current_frame_track_is_rendered():
    records = [
        _track_record(frame=8, track_id=6, state="REACQUIRED"),
    ]
    grouped = group_records_by_frame(records)

    assert overlay_records_for_frame(grouped, 8)[0]["state"] == "REACQUIRED"

    overlay = TrackOverlay()
    frame = np.zeros((180, 240, 3), dtype=np.uint8)
    blank = overlay.render(frame.copy(), [], 8)
    drawn = overlay.render(
        frame.copy(),
        [_make_track(track_id=6, state=TrackState.REACQUIRED)],
        8,
    )

    assert not np.array_equal(drawn, blank)


def test_lost_current_frame_track_is_not_rendered():
    records = [
        _track_record(frame=9, track_id=6, state="LOST", confidence=0.91),
    ]
    grouped = group_records_by_frame(records)

    assert overlay_records_for_frame(grouped, 9) == []
    assert current_history_tracks(records)[0]["track_id"] == 6

    overlay = TrackOverlay()
    frame = np.zeros((180, 240, 3), dtype=np.uint8)
    lost = _make_track(track_id=6, state=TrackState.LOST, confidence=0.91)
    blank = overlay.render(frame.copy(), [], 9)
    drawn = overlay.render(frame.copy(), [lost], 9)

    assert np.array_equal(drawn, blank)


def test_old_frame_boxes_disappear_when_playback_advances():
    records = [
        _track_record(frame=0, track_id=6, state="ACTIVE"),
        _track_record(frame=1, track_id=6, state="LOST"),
    ]
    grouped = group_records_by_frame(records)

    assert [
        item["track_id"]
        for item in overlay_records_for_frame(grouped, 0)
    ] == [6]
    assert overlay_records_for_frame(grouped, 1) == []

    overlay = TrackOverlay()
    frame = np.zeros((180, 240, 3), dtype=np.uint8)
    first = overlay.render(
        frame.copy(),
        [_make_track(track_id=6, state=TrackState.ACTIVE)],
        0,
    )
    next_frame = overlay.render(
        frame.copy(),
        [_make_track(track_id=6, state=TrackState.LOST)],
        1,
    )
    empty = overlay.render(frame.copy(), [], 1)

    assert not np.array_equal(first, empty)
    assert np.array_equal(next_frame, empty)


def test_active_counter_ignores_lost():
    records = [
        _track_record(frame=3, track_id=6, state="ACTIVE"),
        _track_record(frame=3, track_id=7, state="LOST"),
        _track_record(
            frame=3,
            track_id=8,
            state="REACQUIRED",
            class_name="person",
            class_id=0,
        ),
    ]

    counts = current_class_counts(records)

    assert counts["drone"] == 1
    assert counts["person"] == 1
    assert counts["vehicle"] == 0


def test_track_table_shows_current_visible_tracks_only():
    records = [
        _track_record(frame=2, track_id=6, state="ACTIVE"),
        _track_record(frame=2, track_id=7, state="LOST"),
        _track_record(frame=2, track_id=8, state="REACQUIRED"),
    ]
    grouped = group_records_by_frame(records)
    table = table_records_for_frame(grouped, 2)
    history = current_history_tracks(records)

    assert [item["track_id"] for item in table] == [6, 8]
    assert [item["track_id"] for item in history] == [7]


def test_follow_cannot_select_lost_track():
    lost = _track_record(frame=5, track_id=6, state="LOST")
    active = _track_record(frame=5, track_id=8, state="ACTIVE")

    assert can_select_follow(lost) is False
    assert can_select_follow(active) is True

    manager = FollowManager()
    manager.update(
        [
            _make_track(track_id=6, state=TrackState.LOST),
            _make_track(track_id=8, state=TrackState.ACTIVE),
        ]
    )

    with pytest.raises(ValueError):
        manager.select(6)

    target = manager.select(8)
    assert target.track_id == 8


def test_confirmed_active_drone_triggers_visible_alert():
    gate = PlaybackAlertState()
    track = _track_record(frame=12, track_id=6, state="ACTIVE")

    newly = gate.update([track], clock="12:01:09")

    assert [item["track_id"] for item in newly] == [6]
    assert gate.alert_active is True
    assert gate.beep_count == 1
    assert gate.events == [
        "12:01:09 | DRONE | ID 6 | 32% | DETECTED"
    ]
    assert gate.latest_new["track_id"] == 6


def test_same_id_does_not_repeatedly_alert_every_frame():
    gate = PlaybackAlertState()
    track = _track_record(frame=12, track_id=6, state="ACTIVE")

    first = gate.update([track], clock="12:01:09")
    later = []

    for frame in range(13, 21):
        later.extend(
            gate.update(
                [_track_record(frame=frame, track_id=6, state="ACTIVE")],
                clock="12:01:10",
            )
        )

    assert [item["track_id"] for item in first] == [6]
    assert later == []
    assert gate.beep_count == 1
    assert len(gate.events) == 1


def test_lost_does_not_alert():
    gate = PlaybackAlertState()
    lost = _track_record(frame=14, track_id=6, state="LOST", confidence=0.91)

    assert gate.update([lost], clock="12:01:11") == []
    assert gate.alert_active is False
    assert gate.beep_count == 0
    assert gate.events == []


def test_new_session_resets_alert_state():
    gate = PlaybackAlertState()
    track = _track_record(frame=1, track_id=6, state="ACTIVE")

    gate.update([track], clock="12:01:09")
    gate.reset()

    assert gate.alerted_ids == set()
    assert gate.alert_active is False
    assert gate.events == []
    assert gate.beep_count == 0
    assert gate.latest_new is None

    newly = gate.update([track], clock="12:02:00")

    assert [item["track_id"] for item in newly] == [6]
    assert gate.beep_count == 1


def test_event_log_is_added_once_per_new_confirmed_drone():
    gate = PlaybackAlertState()
    historical = [
        _track_record(frame=0, track_id=6, state="LOST"),
        _track_record(frame=10, track_id=6, state="ACTIVE"),
        _track_record(frame=11, track_id=6, state="ACTIVE"),
    ]
    grouped = group_records_by_frame(historical)

    # Playback starts at frame 0. Historical JSON is not preloaded.
    assert gate.update(grouped.get(0, []), clock="12:00:00") == []
    assert gate.events == []

    first_visible = gate.update(
        grouped.get(10, []),
        clock="12:00:10",
    )
    second_visible = gate.update(
        grouped.get(11, []),
        clock="12:00:11",
    )

    assert [item["track_id"] for item in first_visible] == [6]
    assert second_visible == []
    assert gate.events == [
        "12:00:10 | DRONE | ID 6 | 32% | DETECTED"
    ]


def _wait_for_status(
    client: TestClient,
    session_id: str,
    expected: str,
    timeout_s: float = 5.0,
) -> dict:
    deadline = time.time() + timeout_s
    payload: dict = {}

    while time.time() < deadline:
        response = client.get(
            f"/api/v1.1/tracking/session/{session_id}/status"
        )
        assert response.status_code == 200
        payload = response.json()

        if payload.get("status") == expected:
            return payload

        time.sleep(0.03)

    raise AssertionError(
        f"Session {session_id} did not reach {expected}: {payload}"
    )


def _install_fake_processor(
    monkeypatch,
    tmp_path: Path,
    *,
    block: threading.Event | None = None,
    fail: bool = False,
    total: int = 6,
    delay_s: float = 0.0,
    pause_at: int | None = None,
    pause_event: threading.Event | None = None,
):
    monkeypatch.setattr(tracking_routes, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(tracking_routes, "_SESSIONS", {})
    monkeypatch.setattr(
        tracking_routes,
        "_probe_video",
        lambda _path: (total, 30.0, 640, 480),
    )

    class DummyProvider:
        def __init__(self, modality: str) -> None:
            self.modality = modality

        def reset(self) -> None:
            return None

        def process_frame(self, frame):
            return []

    class FakeVideoProcessor:
        entered = threading.Event()

        def __init__(
            self,
            provider,
            *,
            overlay=None,
            follow_manager=None,
            logger=None,
        ) -> None:
            self.provider = provider
            self.overlay = overlay
            self.follow_manager = follow_manager
            self.logger = logger

        def process_file(
            self,
            input_path,
            output_path=None,
            on_progress=None,
        ) -> ProcessingResult:
            FakeVideoProcessor.entered.set()

            if block is not None:
                assert block.wait(timeout=8)

            if fail:
                raise RuntimeError("forced processing failure")

            for processed in range(1, total + 1):
                if on_progress is not None:
                    on_progress(processed, total)

                if (
                    pause_at is not None
                    and pause_event is not None
                    and processed == pause_at
                ):
                    assert pause_event.wait(timeout=8)

                if delay_s:
                    time.sleep(delay_s)

            if output_path is not None:
                Path(output_path).write_bytes(b"fake-annotated-mp4")

            if self.logger is not None:
                close = getattr(self.logger, "close", None)
                if callable(close):
                    close()

            return ProcessingResult(
                input_path=Path(input_path),
                output_path=(
                    Path(output_path)
                    if output_path is not None
                    else None
                ),
                frame_count=total,
                fps=30.0,
                width=640,
                height=480,
                duration_s=total / 30.0,
            )

    monkeypatch.setattr(
        tracking_routes,
        "Dev2TrackingProvider",
        DummyProvider,
    )
    monkeypatch.setattr(
        tracking_routes,
        "VideoProcessor",
        FakeVideoProcessor,
    )

    app = FastAPI()
    app.include_router(tracking_routes.router)
    return TestClient(app), FakeVideoProcessor


def _post_process(client: TestClient) -> tuple[object, dict]:
    started = time.perf_counter()
    response = client.post(
        "/api/v1.1/tracking/process",
        data={"modality": "rgb"},
        files={
            "video": (
                "clip.mp4",
                b"fake-mp4-bytes",
                "video/mp4",
            )
        },
    )
    elapsed = time.perf_counter() - started
    return response, {
        "elapsed": elapsed,
        "payload": response.json(),
    }


def test_process_returns_before_videoprocessor_completes(
    monkeypatch,
    tmp_path,
):
    block = threading.Event()
    client, fake = _install_fake_processor(
        monkeypatch,
        tmp_path,
        block=block,
        delay_s=0.0,
    )

    response, meta = _post_process(client)

    assert response.status_code == 200
    assert meta["elapsed"] < 1.0
    assert fake.entered.wait(timeout=2)
    payload = meta["payload"]
    assert payload["status"] in {"QUEUED", "PROCESSING"}
    assert payload["session_id"]
    assert payload["frames_processed"] == 0

    status = client.get(
        f"/api/v1.1/tracking/session/{payload['session_id']}/status"
    ).json()
    assert status["status"] in {"QUEUED", "PROCESSING"}
    assert status["percent"] < 100.0

    block.set()
    ready = _wait_for_status(client, payload["session_id"], "READY")
    assert ready["percent"] == 100.0


def test_session_starts_as_queued_or_processing(monkeypatch, tmp_path):
    block = threading.Event()
    client, _fake = _install_fake_processor(
        monkeypatch,
        tmp_path,
        block=block,
        delay_s=0.0,
    )

    response, meta = _post_process(client)
    payload = meta["payload"]

    assert payload["status"] in {"QUEUED", "PROCESSING"}
    assert payload["frames_processed"] == 0
    assert payload["total_frames"] == 6
    assert payload["percent"] == 0.0

    block.set()
    _wait_for_status(client, payload["session_id"], "READY")


def test_processing_progress_increases(monkeypatch, tmp_path):
    pause = threading.Event()
    client, _fake = _install_fake_processor(
        monkeypatch,
        tmp_path,
        total=8,
        pause_at=3,
        pause_event=pause,
    )

    _response, meta = _post_process(client)
    session_id = meta["payload"]["session_id"]

    mid = _wait_for_status(client, session_id, "PROCESSING")
    deadline = time.time() + 5
    while time.time() < deadline and int(mid.get("frames_processed") or 0) < 3:
        mid = client.get(
            f"/api/v1.1/tracking/session/{session_id}/status"
        ).json()
        time.sleep(0.02)

    assert mid["status"] == "PROCESSING"
    assert mid["frames_processed"] == 3
    assert mid["total_frames"] == 8
    assert mid["percent"] == 37.5

    pause.set()
    ready = _wait_for_status(client, session_id, "READY")
    assert ready["frames_processed"] == 8
    assert ready["percent"] == 100.0


def test_ready_is_set_on_successful_completion(monkeypatch, tmp_path):
    client, _fake = _install_fake_processor(
        monkeypatch,
        tmp_path,
        delay_s=0.0,
        total=5,
    )

    _response, meta = _post_process(client)
    ready = _wait_for_status(
        client,
        meta["payload"]["session_id"],
        "READY",
    )

    assert ready["status"] == "READY"
    assert ready["frames_processed"] == 5
    assert ready["total_frames"] == 5
    assert ready["percent"] == 100.0
    assert "error" not in ready or ready.get("error") in {None, ""}


def test_failed_is_set_on_processing_exception(monkeypatch, tmp_path):
    client, _fake = _install_fake_processor(
        monkeypatch,
        tmp_path,
        fail=True,
        delay_s=0.0,
    )

    _response, meta = _post_process(client)
    failed = _wait_for_status(
        client,
        meta["payload"]["session_id"],
        "FAILED",
    )

    assert failed["status"] == "FAILED"
    assert "forced processing failure" in failed["error"]


def test_original_video_remains_available_while_processing(
    monkeypatch,
    tmp_path,
):
    block = threading.Event()
    client, fake = _install_fake_processor(
        monkeypatch,
        tmp_path,
        block=block,
        delay_s=0.0,
    )

    _response, meta = _post_process(client)
    session_id = meta["payload"]["session_id"]

    assert fake.entered.wait(timeout=2)

    status = client.get(
        f"/api/v1.1/tracking/session/{session_id}/status"
    ).json()
    assert status["status"] in {"QUEUED", "PROCESSING"}

    original = client.get(
        f"/api/v1.1/tracking/sessions/{session_id}/input.mp4"
    )
    assert original.status_code == 200
    assert original.content == b"fake-mp4-bytes"

    block.set()
    _wait_for_status(client, session_id, "READY")


def test_exports_remain_functional_after_ready(monkeypatch, tmp_path):
    client, _fake = _install_fake_processor(
        monkeypatch,
        tmp_path,
        delay_s=0.0,
        total=4,
    )

    _response, meta = _post_process(client)
    session_id = meta["payload"]["session_id"]
    ready = _wait_for_status(client, session_id, "READY")

    annotated = client.get(
        f"/api/v1.1/tracking/sessions/{session_id}/annotated.mp4"
    )
    tracks_json = client.get(
        f"/api/v1.1/tracking/sessions/{session_id}/tracks.json"
    )
    tracks_csv = client.get(
        f"/api/v1.1/tracking/sessions/{session_id}/tracks.csv"
    )

    assert annotated.status_code == 404
    assert tracks_json.status_code == 200
    assert tracks_csv.status_code == 200
    assert json.loads(tracks_json.content) == []
    assert "track_id" in tracks_csv.text
    assert ready["urls"]["annotated"].endswith("annotated.mp4")
    assert ready["urls"]["json"].endswith("tracks.json")
    assert ready["urls"]["csv"].endswith("tracks.csv")

    def fake_export(input_path, json_path, output_path):
        Path(output_path).write_bytes(b"fake-annotated-mp4")
        return Path(output_path)

    monkeypatch.setattr(
        tracking_routes,
        "write_annotated_mp4",
        fake_export,
    )

    exported = client.post(
        f"/api/v1.1/tracking/session/{session_id}/export/mp4"
    )
    assert exported.status_code == 200
    assert exported.content == b"fake-annotated-mp4"

    annotated_after = client.get(
        f"/api/v1.1/tracking/sessions/{session_id}/annotated.mp4"
    )
    assert annotated_after.status_code == 200
    assert annotated_after.content == b"fake-annotated-mp4"


def test_operator_html_hides_technical_debug_views():
    html = (
        Path(__file__).resolve().parents[1]
        / "tracking_v1_1"
        / "static"
        / "tracking.html"
    ).read_text(encoding="utf-8")

    assert 'id="trackingFps"' not in html
    assert 'id="trackingFrame"' not in html
    assert "FPS" not in html
    assert "Frame:" not in html
    assert "TRACKS" not in html
    assert "TRACK HISTORY" not in html
    assert "trackingTrackTable" not in html
    assert "trackingHistoryTable" not in html
    assert "Error X" not in html
    assert "Error Y" not in html
    assert "tracking-state-active" not in html
    assert "tracking-state-lost" not in html
    assert "tracking-state-reacquired" not in html
    assert "Track History" not in html
    assert "PERSON / VEHICLE" not in html
    assert "trackingCountPerson" not in html
    assert "NO THREAT" in html
    assert "FOLLOW TARGET" in html
    assert "BROWSE VIDEO" in html
    assert 'id="trackingProcessPanel"' in html
    assert 'id="trackingProcessPercent"' in html


def test_operator_js_keeps_video_paused_until_ready():
    js = (
        Path(__file__).resolve().parents[1]
        / "tracking_v1_1"
        / "static"
        / "tracking.js"
    ).read_text(encoding="utf-8")

    assert "async function beginProcessing" in js
    assert "video.pause()" in js
    assert "video.currentTime = 0" in js
    assert "await video.play()" in js
    assert "async function startPlayback" in js
    begin = js.split("async function beginProcessing")[1].split(
        "async function startPlayback"
    )[0]
    assert "video.play()" not in begin


def test_operator_threat_and_follow_rules():
    from tracking_v1_1.playback import (
        follow_button_available,
        keep_video_paused,
        operator_overlay_label,
        operator_ptz_label,
        operator_threat_status,
    )

    active = _track_record(frame=1, track_id=6, state="ACTIVE")
    lost = _track_record(frame=1, track_id=6, state="LOST")
    heli = _track_record(
        frame=1,
        track_id=8,
        state="REACQUIRED",
        class_name="helicopter",
        class_id=3,
    )

    assert operator_overlay_label(active) == "DRONE"
    assert operator_overlay_label(heli) == "HELICOPTER"
    assert operator_threat_status([active]) == "DRONE DETECTED"
    assert operator_threat_status([lost]) == "NO THREAT"
    assert operator_threat_status([heli]) == "NO THREAT"
    assert follow_button_available([active]) is True
    assert follow_button_available([lost]) is False
    assert operator_ptz_label(following=False, command="STOP") == "STOPPED"
    assert operator_ptz_label(
        following=True,
        command="STOP",
    ) == "FOLLOWING TARGET"
    assert operator_ptz_label(
        following=True,
        command="PAN RIGHT + TILT UP",
    ) == "PAN RIGHT + TILT UP"
    assert keep_video_paused("PROCESSING") is True
    assert keep_video_paused("READY") is False


def test_operator_overlay_uses_class_label_only():
    overlay = TrackOverlay()
    frame = np.zeros((180, 240, 3), dtype=np.uint8)
    drawn = overlay.render(
        frame.copy(),
        [_make_track(track_id=6, state=TrackState.ACTIVE)],
        4,
    )

    assert not np.array_equal(drawn, frame)


def test_initial_processing_does_not_create_annotated_mp4(
    monkeypatch,
    tmp_path,
):
    client, _fake = _install_fake_processor(
        monkeypatch,
        tmp_path,
        delay_s=0.0,
        total=4,
    )

    _response, meta = _post_process(client)
    session_id = meta["payload"]["session_id"]
    _wait_for_status(client, session_id, "READY")

    annotated = client.get(
        f"/api/v1.1/tracking/sessions/{session_id}/annotated.mp4"
    )
    tracks_json = client.get(
        f"/api/v1.1/tracking/sessions/{session_id}/tracks.json"
    )

    assert annotated.status_code == 404
    assert tracks_json.status_code == 200
