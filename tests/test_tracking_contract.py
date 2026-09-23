import pytest
import numpy as np
import json

from pydantic import ValidationError
from tracking_v1_1 import Track, TrackState, TrackingProvider
from tracking_v1_1.providers import MockTrackingProvider
from tracking_v1_1.processor import VideoProcessor
from tracking_v1_1.follow import FollowManager
from tracking_v1_1.adapters import SimulatedPTZAdapter
from tracking_v1_1.follow import PTZFollowController
from tracking_v1_1.adapters import ShibliPTZAdapter
from tracking_v1_1.output import TrackLogger
from tracking_v1_1.output import TrackOverlay
from tracking_v1_1.output.overlay import DroneAlertGate

def test_track_contract():
    track = Track(
        track_id=7,
        class_id=2,
        class_name="drone",
        confidence=0.91,
        bbox=[10.0, 20.0, 110.0, 120.0],
        center=[60.0, 70.0],
        state=TrackState.ACTIVE,
    )

    assert track.track_id == 7
    assert track.class_id == 2
    assert track.class_name == "drone"
    assert track.confidence == 0.91
    assert track.bbox == [10.0, 20.0, 110.0, 120.0]
    assert track.center == [60.0, 70.0]
    assert track.state == TrackState.ACTIVE


def test_tracking_provider_returns_tracks():
    provider = MockTrackingProvider()

    tracks = provider.process_frame(None)

    assert isinstance(tracks, list)
    assert all(isinstance(track, Track) for track in tracks)


def test_provider_is_replaceable():
    class AnotherProvider(TrackingProvider):
        def process_frame(self, frame):
            return [
                Track(
                    track_id=99,
                    class_id=1,
                    class_name="vehicle",
                    confidence=0.88,
                    bbox=[1.0, 2.0, 3.0, 4.0],
                    center=[2.0, 3.0],
                    state=TrackState.REACQUIRED,
                )
            ]

    provider = AnotherProvider()

    tracks = provider.process_frame(None)

    assert tracks[0].track_id == 99
    assert tracks[0].class_name == "vehicle"


def test_canonical_class_ids():
    expected = {
        "person": 0,
        "vehicle": 1,
        "drone": 2,
        "helicopter": 3,
    }

    for class_name, class_id in expected.items():
        track = Track(
            track_id=1,
            class_id=class_id,
            class_name=class_name,
            confidence=0.9,
            bbox=[10.0, 20.0, 110.0, 120.0],
            center=[60.0, 70.0],
            state=TrackState.ACTIVE,
        )

        assert track.class_name == class_name
        assert track.class_id == class_id


def test_invalid_class_id_name_pair_is_rejected():
    with pytest.raises(ValidationError):
        Track(
            track_id=1,
            class_id=0,
            class_name="drone",
            confidence=0.9,
            bbox=[10.0, 20.0, 110.0, 120.0],
            center=[60.0, 70.0],
            state=TrackState.ACTIVE,
        )

def test_provider_reset_is_available():
    provider = MockTrackingProvider()

    result = provider.reset()

    assert result is None
    

def test_mock_provider_returns_all_four_canonical_classes():
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


def test_mock_provider_returns_distinct_track_ids():
    provider = MockTrackingProvider()

    tracks = provider.process_frame(None)

    track_ids = [track.track_id for track in tracks]

    assert len(track_ids) == len(set(track_ids))


def test_mock_provider_moves_tracks():
    provider = MockTrackingProvider()

    first = provider.process_frame(None)
    second = provider.process_frame(None)

    first_centers = {
        track.track_id: track.center
        for track in first
    }

    second_centers = {
        track.track_id: track.center
        for track in second
    }

    assert first_centers != second_centers

    for track_id in first_centers:
        assert first_centers[track_id] != second_centers[track_id]


def test_mock_provider_simulates_lost_and_reacquired_state():
    provider = MockTrackingProvider()

    states = []

    for _ in range(27):
        tracks = provider.process_frame(None)

        drone = next(
            track for track in tracks
            if track.track_id == 3
        )

        states.append(drone.state)

    assert TrackState.LOST in states
    assert TrackState.REACQUIRED in states


def test_lost_track_does_not_stop_other_tracks():
    provider = MockTrackingProvider()

    for _ in range(21):
        tracks = provider.process_frame(None)

    states = {
        track.track_id: track.state
        for track in tracks
    }

    assert states[3] == TrackState.LOST

    assert states[1] == TrackState.ACTIVE
    assert states[2] == TrackState.ACTIVE
    assert states[4] == TrackState.ACTIVE


def test_video_processor_passes_frames_to_provider(monkeypatch, tmp_path):
    class FakeCapture:
        def __init__(self):
            self.index = 0
            self.frames = [
                np.zeros((480, 640, 3), dtype=np.uint8),
                np.zeros((480, 640, 3), dtype=np.uint8),
                np.zeros((480, 640, 3), dtype=np.uint8),
            ]

        def isOpened(self):
            return True

        def get(self, property_id):
            import cv2

            if property_id == cv2.CAP_PROP_FPS:
                return 30.0

            if property_id == cv2.CAP_PROP_FRAME_WIDTH:
                return 640.0

            if property_id == cv2.CAP_PROP_FRAME_HEIGHT:
                return 480.0

            return 0.0

        def read(self):
            if self.index >= len(self.frames):
                return False, None

            frame = self.frames[self.index]
            self.index += 1
            return True, frame

        def release(self):
            pass

    fake_capture = FakeCapture()

    monkeypatch.setattr(
        "tracking_v1_1.processor.cv2.VideoCapture",
        lambda _: fake_capture,
    )

    provider = MockTrackingProvider()
    processor = VideoProcessor(provider)

    input_path = tmp_path / "input.mp4"
    input_path.touch()

    result = processor.process_file(input_path)

    assert result.frame_count == 3
    assert result.width == 640
    assert result.height == 480
    assert result.fps == 30.0
    assert result.duration_s == 0.1


def test_video_processor_reports_progress(monkeypatch, tmp_path):
    class FakeCapture:
        def __init__(self):
            self.frames = [
                np.zeros((480, 640, 3), dtype=np.uint8)
                for _ in range(4)
            ]
            self.index = 0

        def isOpened(self):
            return True

        def get(self, property_id):
            import cv2

            if property_id == cv2.CAP_PROP_FPS:
                return 30.0

            if property_id == cv2.CAP_PROP_FRAME_COUNT:
                return float(len(self.frames))

            if property_id == cv2.CAP_PROP_FRAME_WIDTH:
                return 640.0

            if property_id == cv2.CAP_PROP_FRAME_HEIGHT:
                return 480.0

            return 0.0

        def read(self):
            if self.index >= len(self.frames):
                return False, None

            frame = self.frames[self.index]
            self.index += 1
            return True, frame

        def release(self):
            pass

    monkeypatch.setattr(
        "tracking_v1_1.processor.cv2.VideoCapture",
        lambda _: FakeCapture(),
    )

    seen: list[tuple[int, int]] = []

    processor = VideoProcessor(MockTrackingProvider())
    input_path = tmp_path / "input.mp4"
    input_path.touch()

    processor.process_file(
        input_path,
        on_progress=lambda processed, total: seen.append(
            (processed, total)
        ),
    )

    assert seen == [(1, 4), (2, 4), (3, 4), (4, 4)]

def test_mock_tracks_api_route_exists():
    from app.main import app

    paths = {
        route.path
        for route in app.routes
        if hasattr(route, "path")
    }

    assert "/api/v1.1/tracking/mock-tracks" in paths
    assert "/api/v1.1/tracking/ui" in paths


def test_follow_manager_selects_one_track_without_removing_others():
    provider = MockTrackingProvider()
    tracks = provider.process_frame(None)

    manager = FollowManager()
    manager.update(tracks)

    target = manager.select(3)

    assert target.track_id == 3
    assert manager.active_follow_id == 3

    stored_tracks = manager.tracks

    assert len(stored_tracks) == 4
    assert {
        track.track_id
        for track in stored_tracks
    } == {1, 2, 3, 4}


def test_follow_manager_can_switch_target_without_resetting_tracks():
    provider = MockTrackingProvider()
    tracks = provider.process_frame(None)

    manager = FollowManager()
    manager.update(tracks)

    manager.select(3)

    assert manager.active_follow_id == 3
    assert len(manager.tracks) == 4

    manager.select(4)

    assert manager.active_follow_id == 4
    assert len(manager.tracks) == 4
    assert {
        track.track_id
        for track in manager.tracks
    } == {1, 2, 3, 4}


def test_follow_manager_rejects_lost_track():
    provider = MockTrackingProvider()

    for _ in range(21):
        tracks = provider.process_frame(None)

    drone = next(
        track
        for track in tracks
        if track.track_id == 3
    )

    assert drone.state == TrackState.LOST

    manager = FollowManager()
    manager.update(tracks)

    with pytest.raises(ValueError):
        manager.select(3)


def test_follow_manager_owns_follow_configuration():
    manager = FollowManager()

    assert manager.active_track_id is None
    assert manager.follow_mode == "MANUAL"
    assert manager.auto_follow_enabled is False
    assert manager.lost_timeout == 2.0
    assert manager.selection_policy == "MANUAL"


def test_follow_manager_select_track_sets_active_track_id():
    provider = MockTrackingProvider()
    tracks = provider.process_frame(None)

    manager = FollowManager()
    manager.update(tracks)

    target = manager.select_track(3)

    assert target.track_id == 3
    assert manager.active_track_id == 3
    assert manager.active_follow_id == 3
    assert manager.follow_mode == "MANUAL"


def test_follow_manager_clear_target_removes_only_follow_selection():
    provider = MockTrackingProvider()
    tracks = provider.process_frame(None)

    manager = FollowManager()
    manager.update(tracks)
    manager.select_track(3)

    manager.clear_target()

    assert manager.active_track_id is None
    assert len(manager.tracks) == 4
    assert {
        track.track_id
        for track in manager.tracks
    } == {1, 2, 3, 4}


def test_follow_manager_get_follow_target_does_not_filter_tracks():
    provider = MockTrackingProvider()
    tracks = provider.process_frame(None)

    manager = FollowManager()
    manager.update(tracks)
    manager.select_track(3)

    target = manager.get_follow_target(tracks)

    assert target is not None
    assert target.track_id == 3
    assert len(tracks) == 4
    assert {
        track.track_id
        for track in tracks
    } == {1, 2, 3, 4}


def test_follow_manager_rejects_negative_lost_timeout():
    with pytest.raises(ValueError):
        FollowManager(lost_timeout=-1.0)


def test_ptz_controller_stops_when_target_is_centered():
    controller = PTZFollowController()

    target = Track(
        track_id=1,
        class_id=0,
        class_name="person",
        confidence=0.95,
        bbox=[440.0, 240.0, 520.0, 300.0],
        center=[480.0, 270.0],
        state=TrackState.ACTIVE,
    )

    command = controller.update(
        target,
        frame_width=960,
        frame_height=540,
    )

    assert command.command_text == "STOP"
    assert command.pan == "STOP"
    assert command.tilt == "STOP"
    assert command.norm_x == 0.0
    assert command.norm_y == 0.0


def test_ptz_controller_pans_left_and_tilts_up():
    controller = PTZFollowController()

    target = Track(
        track_id=2,
        class_id=2,
        class_name="drone",
        confidence=0.9,
        bbox=[0.0, 0.0, 120.0, 60.0],
        center=[60.0, 30.0],
        state=TrackState.ACTIVE,
    )

    command = controller.update(
        target,
        frame_width=960,
        frame_height=540,
    )

    assert command.pan == "LEFT"
    assert command.tilt == "UP"
    assert command.command_text == "PAN LEFT + TILT UP"
    assert command.norm_x < 0
    assert command.norm_y < 0
    assert command.pan_speed > 0
    assert command.tilt_speed > 0


def test_ptz_controller_pans_right_and_tilts_down():
    controller = PTZFollowController()

    target = Track(
        track_id=3,
        class_id=1,
        class_name="vehicle",
        confidence=0.9,
        bbox=[840.0, 480.0, 960.0, 540.0],
        center=[900.0, 510.0],
        state=TrackState.ACTIVE,
    )

    command = controller.update(
        target,
        frame_width=960,
        frame_height=540,
    )

    assert command.pan == "RIGHT"
    assert command.tilt == "DOWN"
    assert command.command_text == "PAN RIGHT + TILT DOWN"
    assert command.norm_x > 0
    assert command.norm_y > 0


def test_ptz_controller_respects_deadband():
    controller = PTZFollowController(deadband=0.08)

    target = Track(
        track_id=4,
        class_id=3,
        class_name="helicopter",
        confidence=0.9,
        bbox=[470.0, 255.0, 530.0, 285.0],
        center=[500.0, 270.0],
        state=TrackState.ACTIVE,
    )

    command = controller.update(
        target,
        frame_width=960,
        frame_height=540,
    )

    assert abs(command.norm_x) < 0.08
    assert abs(command.norm_y) < 0.08
    assert command.command_text == "STOP"


def test_ptz_controller_stops_for_lost_target():
    controller = PTZFollowController()

    target = Track(
        track_id=3,
        class_id=2,
        class_name="drone",
        confidence=0.9,
        bbox=[800.0, 100.0, 860.0, 140.0],
        center=[830.0, 120.0],
        state=TrackState.LOST,
    )

    command = controller.update(
        target,
        frame_width=960,
        frame_height=540,
    )

    assert command.command_text == "STOP"
    assert command.norm_x == 0.0
    assert command.norm_y == 0.0


def test_ptz_controller_stops_without_target():
    controller = PTZFollowController()

    command = controller.update(
        None,
        frame_width=960,
        frame_height=540,
    )

    assert command.command_text == "STOP"


def test_ptz_command_speed_scales_with_error():
    controller = PTZFollowController()

    near_target = Track(
        track_id=1,
        class_id=0,
        class_name="person",
        confidence=0.9,
        bbox=[700.0, 250.0, 760.0, 290.0],
        center=[730.0, 270.0],
        state=TrackState.ACTIVE,
    )

    far_target = Track(
        track_id=2,
        class_id=0,
        class_name="person",
        confidence=0.9,
        bbox=[900.0, 250.0, 960.0, 290.0],
        center=[930.0, 270.0],
        state=TrackState.ACTIVE,
    )

    near_command = controller.update(
        near_target,
        frame_width=960,
        frame_height=540,
    )

    far_command = controller.update(
        far_target,
        frame_width=960,
        frame_height=540,
    )

    assert far_command.pan_speed > near_command.pan_speed


def test_simulated_ptz_adapter_move():
    adapter = SimulatedPTZAdapter()

    result = adapter.move(
        pan="RIGHT",
        tilt="UP",
        speed=0.42,
    )

    assert result.pan == "RIGHT"
    assert result.tilt == "UP"
    assert result.speed == 0.42
    assert adapter.last_command == result
    assert adapter.history[-1] == result


def test_simulated_ptz_adapter_stop():
    adapter = SimulatedPTZAdapter()

    result = adapter.stop()

    assert result.pan == "STOP"
    assert result.tilt == "STOP"
    assert result.speed == 0.0
    assert adapter.last_command == result
    assert len(adapter.history) == 1


def test_simulated_ptz_adapter_reset():
    adapter = SimulatedPTZAdapter()

    adapter.move("RIGHT", "UP", 0.42)
    adapter.reset()

    assert adapter.last_command is None
    assert adapter.history == []

def test_ptz_route_exists():
    from app.main import app

    paths = {
        route.path
        for route in app.routes
        if hasattr(route, "path")
    }

    assert "/api/v1.1/tracking/follow/ptz" in paths


# These tests use only the fake gateway. They cannot move a real camera.
class FakeShibliGateway:
    def __init__(self):
        self.calls = []

    def move_ptz(
        self,
        direction,
        speed,
        mode,
        ptz_id=None,
        camera_id=None,
    ):
        call = {
            "operation": "move_ptz",
            "direction": direction,
            "speed": speed,
            "mode": mode,
            "ptz_id": ptz_id,
            "camera_id": camera_id,
        }

        self.calls.append(call)

        return {
            "ok": True,
            **call,
        }

    def stop_ptz(self, camera_id=None):
        call = {
            "operation": "stop_ptz",
            "camera_id": camera_id,
        }

        self.calls.append(call)

        return {
            "ok": True,
            **call,
        }


def test_shibli_ptz_adapter_maps_combined_direction():
    gateway = FakeShibliGateway()

    adapter = ShibliPTZAdapter(
        gateway=gateway,
        ptz_id="ptz-1",
        camera_id="camera-1",
    )

    result = adapter.move(
        pan="RIGHT",
        tilt="UP",
        speed=0.42,
    )

    assert result["ok"] is True
    assert result["direction"] == "up_right"
    assert result["speed"] == "medium"
    assert result["mode"] == "rel"
    assert result["ptz_id"] == "ptz-1"
    assert result["camera_id"] == "camera-1"


def test_shibli_ptz_adapter_maps_pan_only():
    gateway = FakeShibliGateway()

    adapter = ShibliPTZAdapter(gateway=gateway)

    adapter.move(
        pan="LEFT",
        tilt="STOP",
        speed=0.80,
    )

    assert gateway.calls[-1]["direction"] == "left"
    assert gateway.calls[-1]["speed"] == "high"


def test_shibli_ptz_adapter_maps_tilt_only():
    gateway = FakeShibliGateway()

    adapter = ShibliPTZAdapter(gateway=gateway)

    adapter.move(
        pan="STOP",
        tilt="DOWN",
        speed=0.20,
    )

    assert gateway.calls[-1]["direction"] == "down"
    assert gateway.calls[-1]["speed"] == "low"


def test_shibli_ptz_adapter_stop():
    gateway = FakeShibliGateway()

    adapter = ShibliPTZAdapter(
        gateway=gateway,
        camera_id="camera-1",
    )

    result = adapter.stop()

    assert result["ok"] is True
    assert gateway.calls[-1] == {
        "operation": "stop_ptz",
        "camera_id": "camera-1",
    }


def test_follow_manager_waits_during_brief_target_loss():
    current_time = [100.0]

    def clock():
        return current_time[0]

    provider = MockTrackingProvider()
    tracks = provider.process_frame(None)

    manager = FollowManager(
        lost_timeout=2.0,
        clock=clock,
    )

    manager.update(tracks)
    manager.select_track(3)

    # Target disappears.
    current_time[0] = 100.5
    manager.update(
        [
            track
            for track in tracks
            if track.track_id != 3
        ]
    )

    assert manager.active_track_id == 3
    assert manager.last_seen_time == 100.0
    assert manager.lost_since == 100.5
    assert manager.target_is_waiting is True
    assert manager.get_active_track() is None


def test_follow_manager_reacquires_target_before_timeout():
    current_time = [100.0]

    def clock():
        return current_time[0]

    provider = MockTrackingProvider()
    tracks = provider.process_frame(None)

    manager = FollowManager(
        lost_timeout=2.0,
        clock=clock,
    )

    manager.update(tracks)
    manager.select_track(3)

    # Temporary loss.
    current_time[0] = 100.5
    manager.update(
        [
            track
            for track in tracks
            if track.track_id != 3
        ]
    )

    assert manager.active_track_id == 3

    # Target returns before timeout.
    reacquired = [
        track.model_copy(
            update={"state": TrackState.REACQUIRED}
        )
        if track.track_id == 3
        else track
        for track in tracks
    ]

    current_time[0] = 101.0
    manager.update(reacquired)

    target = manager.get_active_track()

    assert target is not None
    assert target.track_id == 3
    assert target.state == TrackState.REACQUIRED
    assert manager.active_track_id == 3
    assert manager.lost_since is None
    assert manager.target_is_waiting is False


def test_follow_manager_clears_target_after_timeout():
    current_time = [100.0]

    def clock():
        return current_time[0]

    provider = MockTrackingProvider()
    tracks = provider.process_frame(None)

    manager = FollowManager(
        lost_timeout=2.0,
        clock=clock,
    )

    manager.update(tracks)
    manager.select_track(3)

    # Target disappears.
    current_time[0] = 100.5
    manager.update(
        [
            track
            for track in tracks
            if track.track_id != 3
        ]
    )

    assert manager.active_track_id == 3

    # Timeout expires.
    current_time[0] = 102.6
    manager.update(
        [
            track
            for track in tracks
            if track.track_id != 3
        ]
    )

    assert manager.active_track_id is None
    assert manager.last_seen_time is None
    assert manager.lost_since is None
    assert manager.get_active_track() is None


def test_follow_manager_lost_state_waits_then_times_out():
    current_time = [100.0]

    def clock():
        return current_time[0]

    provider = MockTrackingProvider()
    tracks = provider.process_frame(None)

    manager = FollowManager(
        lost_timeout=2.0,
        clock=clock,
    )

    manager.update(tracks)
    manager.select_track(3)

    lost_tracks = [
        track.model_copy(
            update={"state": TrackState.LOST}
        )
        if track.track_id == 3
        else track
        for track in tracks
    ]

    current_time[0] = 100.5
    manager.update(lost_tracks)

    assert manager.active_track_id == 3
    assert manager.target_is_waiting is True
    assert manager.get_active_track() is None

    current_time[0] = 102.6
    manager.update(lost_tracks)

    assert manager.active_track_id is None


def test_follow_manager_keeps_other_tracks_during_target_loss():
    current_time = [100.0]

    def clock():
        return current_time[0]

    provider = MockTrackingProvider()
    tracks = provider.process_frame(None)

    manager = FollowManager(
        lost_timeout=2.0,
        clock=clock,
    )

    manager.update(tracks)
    manager.select_track(3)

    current_time[0] = 100.5

    remaining_tracks = [
        track
        for track in tracks
        if track.track_id != 3
    ]

    manager.update(remaining_tracks)

    assert {
        track.track_id
        for track in manager.tracks
    } == {1, 2, 4}

    assert manager.active_track_id == 3
    assert manager.get_active_track() is None


def test_ptz_controller_stops_when_follow_target_is_temporarily_missing():
    controller = PTZFollowController()

    command = controller.update(
        None,
        frame_width=960,
        frame_height=540,
    )

    assert command.command_text == "STOP"
    assert command.pan == "STOP"
    assert command.tilt == "STOP"

def test_auto_follow_first_active_selects_first_active_track():
    provider = MockTrackingProvider()
    tracks = provider.process_frame(None)

    manager = FollowManager(
        auto_follow_enabled=False,
        selection_policy="FIRST_ACTIVE",
    )

    manager.update(tracks)
    manager.enable_auto_follow()

    assert manager.auto_follow_enabled is True
    assert manager.follow_mode == "AUTO"
    assert manager.selection_policy == "FIRST_ACTIVE"
    assert manager.active_track_id == 1

def test_auto_follow_does_not_discard_other_tracks():
    provider = MockTrackingProvider()
    tracks = provider.process_frame(None)

    manager = FollowManager(
        auto_follow_enabled=False,
        selection_policy="FIRST_ACTIVE",
    )

    manager.update(tracks)
    manager.enable_auto_follow()

    assert len(manager.tracks) == 4
    assert {
        track.track_id
        for track in manager.tracks
    } == {1, 2, 3, 4}


def test_auto_follow_rejects_unknown_policy():
    with pytest.raises(ValueError):
        FollowManager(
            selection_policy="DRONE_FIRST",
        )


def test_auto_follow_reselects_after_target_timeout():
    current_time = [100.0]

    def clock():
        return current_time[0]

    provider = MockTrackingProvider()
    tracks = provider.process_frame(None)

    manager = FollowManager(
        auto_follow_enabled=False,
        selection_policy="FIRST_ACTIVE",
        lost_timeout=2.0,
        clock=clock,
    )

    manager.update(tracks)
    manager.enable_auto_follow()

    assert manager.active_track_id == 1

    # Remove Track 1.
    current_time[0] = 100.5
    remaining = [
        track
        for track in tracks
        if track.track_id != 1
    ]
    manager.update(remaining)

    assert manager.active_track_id == 1

    # Timeout expires.
    current_time[0] = 102.6
    manager.update(remaining)

    assert manager.active_track_id == 2
    assert manager.follow_mode == "AUTO"


def test_track_logger_writes_json_and_csv(tmp_path):
    json_path = tmp_path / "tracks.json"
    csv_path = tmp_path / "tracks.csv"

    provider = MockTrackingProvider()
    tracks = provider.process_frame(None)

    with TrackLogger(
        json_path=json_path,
        csv_path=csv_path,
    ) as logger:
        logger.record(
            frame_index=463,
            timestamp_s=15.433,
            tracks=tracks,
            follow_target_id=3,
        )

    assert json_path.exists()
    assert csv_path.exists()

    json_records = json.loads(
        json_path.read_text(encoding="utf-8")
    )

    assert len(json_records) == 4

    drone_record = next(
        record
        for record in json_records
        if record["track_id"] == 3
    )

    assert drone_record["frame"] == 463
    assert drone_record["timestamp"] == 15.433
    assert drone_record["class_id"] == 2
    assert drone_record["class_name"] == "drone"
    assert drone_record["follow_target"] is True

    vehicle_record = next(
        record
        for record in json_records
        if record["track_id"] == 2
    )

    assert vehicle_record["follow_target"] is False


def test_track_logger_csv_contains_required_fields(tmp_path):
    json_path = tmp_path / "tracks.json"
    csv_path = tmp_path / "tracks.csv"

    provider = MockTrackingProvider()
    tracks = provider.process_frame(None)

    with TrackLogger(
        json_path=json_path,
        csv_path=csv_path,
    ) as logger:
        logger.record(
            frame_index=10,
            timestamp_s=0.333,
            tracks=tracks,
            follow_target_id=1,
        )

    import csv

    with csv_path.open(
        newline="",
        encoding="utf-8",
    ) as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 4

    required_columns = {
        "frame",
        "timestamp",
        "track_id",
        "class_id",
        "class_name",
        "confidence",
        "x1",
        "y1",
        "x2",
        "y2",
        "state",
        "follow_target",
    }

    assert required_columns.issubset(rows[0].keys())

    person_row = next(
        row
        for row in rows
        if row["track_id"] == "1"
    )

    assert person_row["follow_target"] == "True"


def test_video_processor_passes_follow_target_to_logger(
    monkeypatch,
    tmp_path,
):
    class FakeCapture:
        def __init__(self):
            self.index = 0
            self.frames = [
                np.zeros(
                    (480, 640, 3),
                    dtype=np.uint8,
                )
            ]

        def isOpened(self):
            return True

        def get(self, property_id):
            import cv2

            if property_id == cv2.CAP_PROP_FPS:
                return 30.0

            if property_id == cv2.CAP_PROP_FRAME_WIDTH:
                return 640.0

            if property_id == cv2.CAP_PROP_FRAME_HEIGHT:
                return 480.0

            return 0.0

        def read(self):
            if self.index >= len(self.frames):
                return False, None

            frame = self.frames[self.index]
            self.index += 1

            return True, frame

        def release(self):
            pass

    class FakeFollowManager:
        active_follow_id = 3

        def update(self, tracks):
            pass

    class FakeLogger:
        def __init__(self):
            self.calls = []

        def record(
            self,
            frame_index,
            timestamp_s,
            tracks,
            follow_target_id=None,
        ):
            self.calls.append(
                {
                    "frame": frame_index,
                    "target": follow_target_id,
                    "tracks": tracks,
                }
            )

        def close(self):
            pass

    fake_capture = FakeCapture()

    monkeypatch.setattr(
        "tracking_v1_1.processor.cv2.VideoCapture",
        lambda _: fake_capture,
    )

    logger = FakeLogger()

    processor = VideoProcessor(
        MockTrackingProvider(),
        follow_manager=FakeFollowManager(),
        logger=logger,
    )

    input_path = tmp_path / "input.mp4"
    input_path.touch()

    result = processor.process_file(input_path)

    assert result.frame_count == 1
    assert len(logger.calls) == 1
    assert logger.calls[0]["target"] == 3
    assert len(logger.calls[0]["tracks"]) == 4


def test_track_overlay_draws_tracks():
    frame = np.zeros(
        (540, 960, 3),
        dtype=np.uint8,
    )

    tracks = MockTrackingProvider().process_frame(None)

    overlay = TrackOverlay()

    result = overlay.render(
        frame,
        tracks,
        frame_index=10,
        follow_target_id=3,
    )

    assert result.shape == frame.shape
    assert not np.array_equal(result, frame)


def test_track_overlay_does_not_draw_lost_boxes():
    frame = np.zeros(
        (540, 960, 3),
        dtype=np.uint8,
    )

    lost = Track(
        track_id=7,
        class_id=2,
        class_name="drone",
        confidence=0.9,
        bbox=[80.0, 80.0, 180.0, 160.0],
        center=[130.0, 120.0],
        state=TrackState.LOST,
    )

    overlay = TrackOverlay()

    blank = overlay.render(
        frame.copy(),
        [],
        frame_index=4,
    )

    with_lost = overlay.render(
        frame.copy(),
        [lost],
        frame_index=4,
    )

    assert np.array_equal(blank, with_lost)


def test_track_overlay_draws_active_and_reacquired_boxes():
    frame = np.zeros(
        (540, 960, 3),
        dtype=np.uint8,
    )

    active = Track(
        track_id=6,
        class_id=2,
        class_name="drone",
        confidence=0.32,
        bbox=[40.0, 40.0, 140.0, 120.0],
        center=[90.0, 80.0],
        state=TrackState.ACTIVE,
    )
    reacquired = Track(
        track_id=9,
        class_id=2,
        class_name="drone",
        confidence=0.55,
        bbox=[200.0, 80.0, 300.0, 160.0],
        center=[250.0, 120.0],
        state=TrackState.REACQUIRED,
    )

    overlay = TrackOverlay()
    blank = overlay.render(frame.copy(), [], 1)

    with_active = overlay.render(
        frame.copy(),
        [active],
        1,
    )
    with_reacquired = overlay.render(
        frame.copy(),
        [reacquired],
        2,
    )

    assert not np.array_equal(with_active, blank)
    assert not np.array_equal(with_reacquired, blank)


def test_overlay_counters_ignore_lost_tracks():
    from tracking_v1_1.output.overlay import current_class_counts

    tracks = [
        Track(
            track_id=6,
            class_id=2,
            class_name="drone",
            confidence=0.32,
            bbox=[10.0, 10.0, 40.0, 40.0],
            center=[25.0, 25.0],
            state=TrackState.ACTIVE,
        ),
        Track(
            track_id=7,
            class_id=2,
            class_name="drone",
            confidence=0.9,
            bbox=[80.0, 80.0, 180.0, 160.0],
            center=[130.0, 120.0],
            state=TrackState.LOST,
        ),
    ]

    assert current_class_counts(tracks)["drone"] == 1


def test_one_confirmed_drone_triggers_one_alert():
    gate = DroneAlertGate()

    track = Track(
        track_id=1,
        class_id=2,
        class_name="drone",
        confidence=0.46,
        bbox=[10.0, 10.0, 40.0, 40.0],
        center=[25.0, 25.0],
        state=TrackState.ACTIVE,
    )

    first = gate.update([track])
    second = gate.update([track])

    assert [item.track_id for item in first] == [1]
    assert second == []
    assert gate.alert_active is True


def test_repeated_active_frames_do_not_repeat_alert():
    gate = DroneAlertGate()

    track = Track(
        track_id=11,
        class_id=2,
        class_name="drone",
        confidence=0.8,
        bbox=[10.0, 10.0, 40.0, 40.0],
        center=[25.0, 25.0],
        state=TrackState.ACTIVE,
    )

    alerts = []

    for _ in range(8):
        alerts.extend(gate.update([track]))

    assert len(alerts) == 1
    assert alerts[0].track_id == 11


def test_lost_tracks_do_not_alert():
    gate = DroneAlertGate()

    lost = Track(
        track_id=7,
        class_id=2,
        class_name="drone",
        confidence=0.8,
        bbox=[10.0, 10.0, 40.0, 40.0],
        center=[25.0, 25.0],
        state=TrackState.LOST,
    )

    assert gate.update([lost]) == []
    assert gate.alert_active is False


def test_processed_video_routes_exist():
    from app.main import app

    paths = {
        route.path
        for route in app.routes
        if hasattr(route, "path")
    }

    assert "/api/v1.1/tracking/process" in paths
    assert (
        "/api/v1.1/tracking/session/{session_id}/status"
    ) in paths
    assert (
        "/api/v1.1/tracking/session/{session_id}/export/mp4"
    ) in paths
    assert (
        "/api/v1.1/tracking/"
        "sessions/{session_id}/{filename}"
    ) in paths


#After first round of changes 

def test_auto_follow_routes_are_registered_before_dynamic_track_route():
    from app.main import app

    paths = [
        route.path
        for route in app.routes
        if hasattr(route, "path")
    ]

    auto_route_index = paths.index(
        "/api/v1.1/tracking/follow/auto"
    )

    dynamic_route_index = paths.index(
        "/api/v1.1/tracking/follow/{track_id}"
    )

    assert auto_route_index < dynamic_route_index


def test_mock_provider_keeps_boxes_inside_frame():
    import numpy as np

    provider = MockTrackingProvider()

    frame = np.zeros(
        (768, 1024, 3),
        dtype=np.uint8,
    )

    for _ in range(5000):
        tracks = provider.process_frame(frame)

        for track in tracks:
            x1, y1, x2, y2 = track.bbox

            assert 0 <= x1 < 1024
            assert 0 <= y1 < 768
            assert 0 < x2 <= 1024
            assert 0 < y2 <= 768



def test_auto_follow_selects_one_active_track():
    provider = MockTrackingProvider()

    tracks = provider.process_frame(None)

    manager = FollowManager()
    manager.update(tracks)

    manager.enable_auto_follow()

    assert manager.auto_follow_enabled is True
    assert manager.follow_mode == "AUTO"
    assert manager.active_follow_id is not None

    active_ids = {
        track.track_id
        for track in tracks
        if track.state in (
            TrackState.ACTIVE,
            TrackState.REACQUIRED,
        )
    }

    assert manager.active_follow_id in active_ids
