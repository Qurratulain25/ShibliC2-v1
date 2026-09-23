from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from tracking_v1_1.models import (
    CLASS_ID_BY_NAME,
    Track,
)
from tracking_v1_1.providers.dev2 import (
    Dev2TrackingProvider,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = PROJECT_ROOT / "models" / "dev2"


@pytest.mark.integration
@pytest.mark.parametrize(
    "modality,expected_filename",
    [
        ("rgb", "rgb_best_v1.pt"),
        ("thermal", "thermal_best_v1.pt"),
    ],
)
def test_real_dev2_model_loads(
    modality,
    expected_filename,
):
    provider = Dev2TrackingProvider(
        modality,
    )

    assert provider.model_path.name == expected_filename
    assert provider.model_path.is_file()
    assert provider.tracker_config_path.is_file()

    assert provider.tracker_config_path.name == (
        "tracktrack.yaml"
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "modality",
    [
        "rgb",
        "thermal",
    ],
)
def test_real_dev2_provider_processes_one_frame(
    modality,
):
    provider = Dev2TrackingProvider(
        modality,
    )

    frame = np.zeros(
        (512, 640, 3),
        dtype=np.uint8,
    )

    tracks = provider.process_frame(frame)

    assert isinstance(tracks, list)

    for track in tracks:
        assert isinstance(track, Track)

        assert (
            track.class_name
            in {"drone", "helicopter"}
        )

        assert track.class_id == (
            CLASS_ID_BY_NAME[
                track.class_name
            ]
        )

        assert 0.0 <= track.confidence <= 1.0

        x1, y1, x2, y2 = track.bbox

        assert x1 < x2
        assert y1 < y2

        assert 0 <= x1 <= 640
        assert 0 <= x2 <= 640

        assert 0 <= y1 <= 512
        assert 0 <= y2 <= 512


@pytest.mark.integration
def test_dev2_class_mapping():
    assert Dev2TrackingProvider._canonical_class_name(
        0,
        {
            0: "drone",
            1: "helicopter",
        },
    ) == "drone"

    assert Dev2TrackingProvider._canonical_class_name(
        1,
        {
            0: "drone",
            1: "helicopter",
        },
    ) == "helicopter"


@pytest.mark.integration
@pytest.mark.parametrize(
    "modality,expected_filename,wrong_filename",
    [
        (
            "rgb",
            "rgb_best_v1.pt",
            "thermal_best_v1.pt",
        ),
        (
            "thermal",
            "thermal_best_v1.pt",
            "rgb_best_v1.pt",
        ),
    ],
)
def test_rgb_thermal_model_isolation(
    modality,
    expected_filename,
    wrong_filename,
):
    provider = Dev2TrackingProvider(
        modality,
    )

    assert provider.model_path.name == (
        expected_filename
    )

    assert provider.model_path.name != (
        wrong_filename
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "modality",
    [
        "rgb",
        "thermal",
    ],
)
def test_real_dev2_reset_clears_provider_state(
    modality,
):
    provider = Dev2TrackingProvider(
        modality,
    )

    provider._previous_track_ids = {1, 2}
    provider._lost_track_ids = {2}

    provider.reset()

    assert provider._previous_track_ids == set()
    assert provider._lost_track_ids == set()
    assert provider._last_tracks == {}


@pytest.mark.integration
def test_real_dev2_track_ids_persist_across_video_frames():
    video_path = os.getenv("DEV2_TEST_VIDEO")

    if not video_path:
        pytest.skip(
            "Set DEV2_TEST_VIDEO to a real RGB test MP4."
        )

    provider = Dev2TrackingProvider("rgb")

    capture = cv2.VideoCapture(video_path)

    assert capture.isOpened(), (
        f"Could not open test video: {video_path}"
    )

    observed_ids = []

    try:
        for _ in range(30):
            ok, frame = capture.read()

            if not ok:
                break

            tracks = provider.process_frame(frame)

            for track in tracks:
                assert isinstance(track, Track)

            observed_ids.append(
                {
                    track.track_id
                    for track in tracks
                    if track.state.value != "LOST"
                }
            )

    finally:
        capture.release()

    all_ids = set()

    for ids in observed_ids:
        all_ids.update(ids)

    if not all_ids:
        pytest.skip(
            "No Dev2 detection was produced in the first 30 frames."
        )

    persistent = any(
        sum(track_id in ids for ids in observed_ids) >= 2
        for track_id in all_ids
    )

    assert persistent, (
        "No track ID persisted across at least two "
        "observed frames."
    )