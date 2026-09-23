from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import TextIO

from ..models import Track


class TrackLogger:
    """
    Structured JSON + CSV logger for the v1.1 tracking pipeline.

    One record is emitted for every track on every processed frame.

    Required fields:
        frame
        timestamp
        track_id
        class_id
        class_name
        confidence
        bbox
        state
        follow_target
    """

    CSV_FIELDS = [
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
    ]

    def __init__(
        self,
        *,
        json_path: str | Path,
        csv_path: str | Path,
    ) -> None:
        self.json_path = Path(json_path)
        self.csv_path = Path(csv_path)

        self.json_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        self.csv_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._json_file: TextIO | None = None
        self._csv_file: TextIO | None = None
        self._csv_writer: csv.DictWriter | None = None
        self._json_first_record = True
        self._closed = False

        self._open()

    def _open(self) -> None:
        self._json_file = self.json_path.open(
            "w",
            encoding="utf-8",
        )

        self._csv_file = self.csv_path.open(
            "w",
            newline="",
            encoding="utf-8",
        )

        self._csv_writer = csv.DictWriter(
            self._csv_file,
            fieldnames=self.CSV_FIELDS,
        )

        self._csv_writer.writeheader()

        self._json_file.write("[\n")

    def record(
        self,
        frame_index: int,
        timestamp_s: float,
        tracks: list[Track],
        follow_target_id: int | None = None,
    ) -> None:
        if self._closed:
            raise RuntimeError("TrackLogger is already closed")

        if self._json_file is None or self._csv_writer is None:
            raise RuntimeError("TrackLogger is not initialized")

        for track in tracks:
            x1, y1, x2, y2 = track.bbox

            record = {
                "frame": frame_index,
                "timestamp": timestamp_s,
                "track_id": track.track_id,
                "class_id": track.class_id,
                "class_name": track.class_name,
                "confidence": track.confidence,
                "bbox": [
                    x1,
                    y1,
                    x2,
                    y2,
                ],
                "state": track.state.value,
                "follow_target": (
                    track.track_id == follow_target_id
                ),
            }

            if not self._json_first_record:
                self._json_file.write(",\n")

            json.dump(
                record,
                self._json_file,
                ensure_ascii=False,
            )

            self._json_first_record = False

            self._csv_writer.writerow(
                {
                    "frame": frame_index,
                    "timestamp": timestamp_s,
                    "track_id": track.track_id,
                    "class_id": track.class_id,
                    "class_name": track.class_name,
                    "confidence": track.confidence,
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "state": track.state.value,
                    "follow_target": (
                        track.track_id == follow_target_id
                    ),
                }
            )

    def flush(self) -> None:
        if self._json_file is not None:
            self._json_file.flush()

        if self._csv_file is not None:
            self._csv_file.flush()

    def close(self) -> None:
        if self._closed:
            return

        if self._json_file is not None:
            self._json_file.write("\n]\n")
            self._json_file.close()
            self._json_file = None

        if self._csv_file is not None:
            self._csv_file.close()
            self._csv_file = None

        self._closed = True

    def __enter__(self) -> "TrackLogger":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()