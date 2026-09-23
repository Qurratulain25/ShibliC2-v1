from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

import cv2
import numpy as np

from .models import Track
from .providers.base import TrackingProvider


class OverlaySink(Protocol):
    """
    Optional consumer responsible for drawing tracks onto a frame.
    """

    def render(
        self,
        frame: np.ndarray,
        tracks: list[Track],
        frame_index: int,
        follow_target_id: int | None = None,
    ) -> np.ndarray:
        ...


class FollowSink(Protocol):
    """
    Optional consumer responsible for follow-target logic.

    The processor passes tracks only. The follow implementation decides
    what to do with them.
    """

    def update(
        self,
        tracks: list[Track],
    ) -> Any:
        ...


class LoggerSink(Protocol):
    """
    Optional consumer for structured frame/track logging.
    """

    def record(
        self,
        frame_index: int,
        timestamp_s: float,
        tracks: list[Track],
        follow_target_id: int | None = None,
    ) -> None:
        ...


@dataclass
class ProcessingFrame:
    frame_index: int
    timestamp_s: float
    fps: float
    frame: np.ndarray
    tracks: list[Track]


@dataclass
class ProcessingResult:
    input_path: Path
    output_path: Path | None
    frame_count: int
    fps: float
    width: int
    height: int
    duration_s: float


class VideoProcessor:
    """
    Application-layer video processing pipeline.

    Pipeline:

        MP4
         ↓
        OpenCV
         ↓
        frame
         ↓
        TrackingProvider.process_frame(frame)
         ↓
        list[Track]
         ↓
        overlay / follow / logger
         ↓
        optional output MP4

    The processor never knows which detector/tracker produced the tracks.
    """

    def __init__(
        self,
        provider: TrackingProvider,
        *,
        overlay: OverlaySink | None = None,
        follow_manager: FollowSink | None = None,
        logger: LoggerSink | None = None,
    ) -> None:
        self.provider = provider
        self.overlay = overlay
        self.follow_manager = follow_manager
        self.logger = logger

    def process_file(
        self,
        input_path: str | Path,
        output_path: str | Path | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> ProcessingResult:
        input_file = Path(input_path)

        if not input_file.is_file():
            raise FileNotFoundError(
                f"Input video not found: {input_file}"
            )

        capture = cv2.VideoCapture(str(input_file))

        if not capture.isOpened():
            raise RuntimeError(
                f"Could not open input video: {input_file}"
            )

        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

        if width <= 0 or height <= 0:
            capture.release()
            raise RuntimeError(
                f"Could not determine video dimensions: {input_file}"
            )

        writer = None

        try:
            self.provider.reset()

            if output_path is not None:
                from .output.video_writer import VideoWriter

                writer = VideoWriter(
                    output_path,
                    fps,
                    (width, height),
                )

            frame_count = 0
            total_frames = int(
                capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            )

            while True:
                ok, frame = capture.read()

                if not ok:
                    break

                timestamp_s = (
                    frame_count / fps
                    if fps > 0
                    else 0.0
                )

                tracks = self.provider.process_frame(frame)

                if self.follow_manager is not None:
                    self.follow_manager.update(
                        tracks
                    )

                if self.logger is not None:
                    follow_target_id = None

                    if self.follow_manager is not None:
                        follow_target_id = getattr(
                            self.follow_manager,
                            "active_follow_id",
                            None,
                        )

                    self.logger.record(
                        frame_count,
                        timestamp_s,
                        tracks,
                        follow_target_id,
                    )

                output_frame = frame

                if self.overlay is not None:
                    follow_target_id = None

                    if self.follow_manager is not None:
                        follow_target_id = getattr(
                            self.follow_manager,
                            "active_follow_id",
                            None,
                        )

                    output_frame = self.overlay.render(
                        frame,
                        tracks,
                        frame_count,
                        follow_target_id,
                    )

                if writer is not None:
                    writer.write(output_frame)

                frame_count += 1

                if on_progress is not None:
                    reported_total = max(
                        total_frames,
                        frame_count,
                    )
                    on_progress(
                        frame_count,
                        reported_total,
                    )

            duration_s = (
                frame_count / fps
                if fps > 0
                else 0.0
            )

            return ProcessingResult(
                input_path=input_file,
                output_path=(
                    Path(output_path)
                    if output_path is not None
                    else None
                ),
                frame_count=frame_count,
                fps=fps,
                width=width,
                height=height,
                duration_s=duration_s,
            )

        finally:
            capture.release()

            if writer is not None:
                writer.close()

            if self.logger is not None:
                close = getattr(self.logger, "close", None)

                if callable(close):
                    close()

            self.provider.reset()