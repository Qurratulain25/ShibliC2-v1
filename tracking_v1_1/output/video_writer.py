from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


class VideoWriter:
    """
    Small output sink used by the v1.1 processing pipeline.

    It knows about video frames, but knows nothing about YOLO,
    tracking implementations, or PTZ control.
    """

    def __init__(
        self,
        output_path: str | Path,
        fps: float,
        frame_size: tuple[int, int],
    ) -> None:
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        width, height = frame_size

        self._writer = cv2.VideoWriter(
            str(self.output_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps if fps > 0 else 30.0,
            (width, height),
        )

        if not self._writer.isOpened():
            raise RuntimeError(
                f"Could not open video writer: {self.output_path}"
            )

    def write(self, frame: np.ndarray) -> None:
        self._writer.write(frame)

    def close(self) -> None:
        if self._writer is not None:
            self._writer.release()
            self._writer = None