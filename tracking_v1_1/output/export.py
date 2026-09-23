from __future__ import annotations

import json
from pathlib import Path

import cv2

from ..playback import (
    group_records_by_frame,
    records_to_tracks,
)
from .overlay import TrackOverlay
from .video_writer import VideoWriter


def write_annotated_mp4(
    input_path: str | Path,
    json_path: str | Path,
    output_path: str | Path,
) -> Path:
    """
    Burn current-frame overlay boxes onto the original MP4.

    Tracking inference is not repeated. Only stored tracks.json records
    are drawn, and only when an operator requests an MP4 export.
    """
    input_file = Path(input_path)
    json_file = Path(json_path)
    output_file = Path(output_path)

    if not input_file.is_file():
        raise FileNotFoundError(
            f"Input video not found: {input_file}"
        )

    if not json_file.is_file():
        raise FileNotFoundError(
            f"Tracking data not found: {json_file}"
        )

    records = json.loads(
        json_file.read_text(encoding="utf-8")
    )

    if not isinstance(records, list):
        raise ValueError("Tracking data has an invalid format.")

    grouped = group_records_by_frame(records)
    overlay = TrackOverlay()
    capture = cv2.VideoCapture(str(input_file))

    if not capture.isOpened():
        raise RuntimeError(
            f"Could not open input video: {input_file}"
        )

    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

        if width <= 0 or height <= 0:
            raise RuntimeError(
                f"Could not determine video dimensions: {input_file}"
            )

        writer = VideoWriter(
            output_file,
            fps,
            (width, height),
        )

        try:
            frame_index = 0

            while True:
                ok, frame = capture.read()

                if not ok:
                    break

                tracks = records_to_tracks(
                    grouped.get(frame_index, [])
                )
                writer.write(
                    overlay.render(
                        frame,
                        tracks,
                        frame_index,
                    )
                )
                frame_index += 1
        finally:
            writer.close()
    finally:
        capture.release()

    return output_file
