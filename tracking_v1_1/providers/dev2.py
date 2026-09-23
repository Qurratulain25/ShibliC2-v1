from __future__ import annotations

import logging
from collections import deque
from pathlib import Path
from typing import Any, Literal

from ultralytics import YOLO

from .base import TrackingProvider
from ..config import (
    TRACKING_CONFIRM_WINDOW,
    TRACKING_DRONE_CONF,
    TRACKING_DRONE_ONLY,
    TRACKING_DUPLICATE_IOU,
    TRACKING_IMGSZ,
    TRACKING_MIN_CONFIRM_HITS,
    TRACKING_TRACKER,
)
from ..models import (
    CLASS_ID_BY_NAME,
    Track,
    TrackState,
)

logger = logging.getLogger(__name__)

# Dev2 checkpoint class IDs -> SHIBLI canonical class names.
_LOCAL_CLASS_TO_CANONICAL_NAME: dict[int, str] = {
    0: "drone",
    1: "drone",
    2: "drone",
}


Modality = Literal["rgb", "thermal"]


class Dev2TrackingProvider(TrackingProvider):
    """
    Real SHIBLI v1.1 tracking provider backed by the Dev2 Ultralytics
    checkpoints.

    One provider instance represents one processing session and therefore
    owns exactly one YOLO model/tracker instance.

    Supported modalities:

        rgb     -> models/dev2/rgb_best_v1.pt
        thermal -> models/dev2/thermal_best_v1.pt

    Local checkpoint classes:

        0 = drone
        1 = helicopter

    When TRACKING_DRONE_ONLY is enabled, only local class 0 is accepted.
    Tentative tracker IDs stay private until TRACKING_MIN_CONFIRM_HITS
    observations occur with current_frame - hit_frame <
    TRACKING_CONFIRM_WINDOW. Confirmed IDs then follow the existing
    ACTIVE / LOST / REACQUIRED lifecycle without reconfirmation.
    """

    _MODEL_FILENAMES: dict[Modality, str] = {
        "rgb": "rgb_best_v1.pt",
        "thermal": "thermal_best_v1.pt",
    }

    def __init__(
        self,
        modality: Modality,
        *,
        model_dir: str | Path | None = None,
    ) -> None:
        normalized_modality = modality.lower()

        if normalized_modality not in self._MODEL_FILENAMES:
            raise ValueError(
                "Unsupported tracking modality: "
                f"{modality!r}. Expected 'rgb' or 'thermal'."
            )

        self.modality: Modality = normalized_modality  # type: ignore[assignment]

        if model_dir is None:
            model_dir = (
                Path(__file__).resolve().parents[2]
                / "models"
                / "dev2"
            )

        self.model_path = (
            Path(model_dir)
            / self._MODEL_FILENAMES[self.modality]
        ).resolve()

        if not self.model_path.is_file():
            raise FileNotFoundError(
                f"Dev2 model checkpoint not found: "
                f"{self.model_path}"
            )

        self._model = YOLO(str(self.model_path))

        self.tracker = TRACKING_TRACKER

        # Project TrackTrack YAML is retained in the repository but is
        # not used for inference while TRACKING_TRACKER selects ByteTrack.
        self.tracker_config_path = (
            Path(__file__).resolve().parents[1]
            / "trackers"
            / "tracktrack.yaml"
        ).resolve()

        # Track IDs that were visible in the immediately preceding frame.
        self._previous_track_ids: set[int] = set()

        # Last known Track data for every persistent tracker ID.
        #
        # This is required so a missing target can still be represented
        # by a valid Track with state=LOST.
        self._last_tracks: dict[int, Track] = {}

        # Track IDs that are currently considered temporarily lost.
        #
        # FollowManager owns the timeout for the selected follow target.
        # The provider keeps supplying LOST for these IDs until YOLO
        # associates the same persistent ID with a new observation.
        self._lost_track_ids: set[int] = set()

        # Observed provider-frame indexes per unconfirmed tracker ID.
        #
        # A hit expires when:
        #     current_frame - hit_frame >= TRACKING_CONFIRM_WINDOW
        #
        # Example with window=4:
        #     frame 100 observed -> hits [100]
        #     frame 101 missing  -> hits [100]
        #     frame 102 observed -> hits [100, 102] -> confirmed
        self._tentative_hits: dict[int, deque[int]] = {}

        # Tracker IDs that have already passed confirmation.
        # These keep the ACTIVE / LOST / REACQUIRED lifecycle and are
        # never sent back through tentative confirmation.
        self._confirmed_track_ids: set[int] = set()

        # Monotonically increasing provider frame counter.
        self._frame_index = -1

    def reset(self) -> None:
        """
        Reset provider and underlying YOLO tracker state.
        """
        self._previous_track_ids.clear()
        self._last_tracks.clear()
        self._lost_track_ids.clear()
        self._tentative_hits.clear()
        self._confirmed_track_ids.clear()
        self._frame_index = -1

        predictor = getattr(
            self._model,
            "predictor",
            None,
        )

        if predictor is not None:
            trackers = getattr(
                predictor,
                "trackers",
                None,
            )

            if trackers:
                for tracker in trackers:
                    reset = getattr(
                        tracker,
                        "reset",
                        None,
                    )

                    if callable(reset):
                        reset()

            predictor.vid_path = None

    def process_frame(self, frame: Any) -> list[Track]:
        """
        Run Dev2 YOLO tracking on one OpenCV frame.

        State lifecycle:

            fewer than min_confirm unexpired hits
                -> tentative (not emitted)

            min_confirm unexpired hits
                -> ACTIVE; tentative history is discarded

            temporarily missing for one or more frames
                -> LOST (confirmed tracks only; no reconfirmation)

            same persistent tracker ID returns
                -> REACQUIRED

            following frames after reappearance
                -> ACTIVE
        """
        if frame is None:
            raise ValueError(
                "Dev2TrackingProvider.process_frame() requires "
                "an actual OpenCV frame."
            )

        self._frame_index += 1

        if TRACKING_DRONE_ONLY:
            results = self._model.track(
                source=frame,
                persist=True,
                tracker=TRACKING_TRACKER,
                classes=[0, 1, 2],
                conf=TRACKING_DRONE_CONF,
                imgsz=TRACKING_IMGSZ,
                verbose=False,
            )
        else:
            results = self._model.track(
                source=frame,
                persist=True,
                tracker=TRACKING_TRACKER,
                verbose=False,
            )

        if not results:
            self._prune_tentative_hits()
            return self._mark_missing_and_build_lost_tracks()

        result = results[0]

        boxes = getattr(
            result,
            "boxes",
            None,
        )

        if boxes is None:
            self._prune_tentative_hits()
            return self._mark_missing_and_build_lost_tracks()

        track_ids = getattr(
            boxes,
            "id",
            None,
        )

        if track_ids is None:
            self._log_missing_track_ids()
            self._prune_tentative_hits()
            return self._mark_missing_and_build_lost_tracks()

        xyxy = boxes.xyxy
        confidences = boxes.conf
        class_ids = boxes.cls

        names = getattr(
            result,
            "names",
            None,
        )

        if names is None:
            names = getattr(
                self._model,
                "names",
                {},
            )

        current_tracks: list[Track] = []
        current_track_ids: set[int] = set()
        candidates: list[dict[str, Any]] = []

        for index in range(len(track_ids)):
            track_id = int(
                track_ids[index].item()
            )

            source_class_id = int(
                class_ids[index].item()
            )

            x1, y1, x2, y2 = (
                float(value)
                for value in xyxy[index].tolist()
            )

            bbox = [
                x1,
                y1,
                x2,
                y2,
            ]

            confidence = float(
                confidences[index].item()
            )

            confidence = max(
                0.0,
                min(1.0, confidence),
            )

            if TRACKING_DRONE_ONLY and source_class_id not in (0, 1, 2):
                self._log_observation(
                    local_class=source_class_id,
                    confidence=confidence,
                    tracker_id=track_id,
                    bbox=bbox,
                    accepted=False,
                    reason="suppressed_local_class",
                    hit_count=self._tentative_hit_count(track_id),
                    confirmed=False,
                )
                continue

            if (
                TRACKING_DRONE_ONLY
                and confidence < TRACKING_DRONE_CONF
            ):
                self._log_observation(
                    local_class=source_class_id,
                    confidence=confidence,
                    tracker_id=track_id,
                    bbox=bbox,
                    accepted=False,
                    reason="low_confidence",
                    hit_count=self._tentative_hit_count(track_id),
                    confirmed=False,
                )
                continue

            class_name = self._canonical_class_name(
                source_class_id,
                names,
            )

            # Ignore detections that are not part of SHIBLI's
            # canonical class vocabulary.
            if class_name is None:
                self._log_observation(
                    local_class=source_class_id,
                    confidence=confidence,
                    tracker_id=track_id,
                    bbox=bbox,
                    accepted=False,
                    reason="non_canonical_class",
                    hit_count=self._tentative_hit_count(track_id),
                    confirmed=False,
                )
                continue

            candidates.append(
                {
                    "track_id": track_id,
                    "source_class_id": source_class_id,
                    "class_name": class_name,
                    "confidence": confidence,
                    "bbox": bbox,
                }
            )

        kept_candidates = self._suppress_duplicate_candidates(
            candidates
        )
        kept_ids = {
            candidate["track_id"]
            for candidate in kept_candidates
        }

        for candidate in candidates:
            if candidate["track_id"] in kept_ids:
                continue

            self._log_observation(
                local_class=candidate["source_class_id"],
                confidence=candidate["confidence"],
                tracker_id=candidate["track_id"],
                bbox=candidate["bbox"],
                accepted=False,
                reason="duplicate_iou",
                hit_count=self._tentative_hit_count(
                    candidate["track_id"]
                ),
                confirmed=False,
            )

        for candidate in kept_candidates:
            track_id = candidate["track_id"]
            source_class_id = candidate["source_class_id"]
            class_name = candidate["class_name"]
            confidence = candidate["confidence"]
            bbox = candidate["bbox"]
            x1, y1, x2, y2 = bbox

            if not self._is_confirmed(track_id):
                hit_count = self._record_tentative_hit(track_id)

                if hit_count < self._min_confirm_hits():
                    self._log_observation(
                        local_class=source_class_id,
                        confidence=confidence,
                        tracker_id=track_id,
                        bbox=bbox,
                        accepted=False,
                        reason="tentative",
                        hit_count=hit_count,
                        confirmed=False,
                    )
                    continue

                # Tentative history is discarded. Later LOST / REACQUIRED
                # uses the confirmed lifecycle only.
                self._confirmed_track_ids.add(track_id)
                self._tentative_hits.pop(track_id, None)

            canonical_class_id = CLASS_ID_BY_NAME[
                class_name
            ]

            center = [
                (x1 + x2) / 2.0,
                (y1 + y2) / 2.0,
            ]

            # A persistent ID that was previously lost has now
            # returned. This is the REACQUIRED event.
            if track_id in self._lost_track_ids:
                state = TrackState.REACQUIRED
                self._lost_track_ids.remove(track_id)
            else:
                state = TrackState.ACTIVE

            track = Track(
                track_id=track_id,
                class_id=canonical_class_id,
                class_name=class_name,
                confidence=confidence,
                bbox=bbox,
                center=center,
                state=state,
            )

            self._log_observation(
                local_class=source_class_id,
                confidence=confidence,
                tracker_id=track_id,
                bbox=bbox,
                accepted=True,
                reason=state.value,
                hit_count=self._min_confirm_hits(),
                confirmed=True,
            )

            current_tracks.append(track)
            current_track_ids.add(track_id)

        self._prune_tentative_hits()

        # Any track that was visible in the previous frame but is not
        # visible now has entered the LOST state.
        missing_from_current_frame = (
            self._previous_track_ids
            - current_track_ids
        )

        for track_id in missing_from_current_frame:
            if track_id in self._last_tracks:
                self._lost_track_ids.add(track_id)

        # Any track that was already lost remains LOST until its
        # persistent tracker ID appears again.
        for track_id in self._lost_track_ids:
            previous_track = self._last_tracks.get(
                track_id
            )

            if previous_track is None:
                continue

            current_tracks.append(
                previous_track.model_copy(
                    update={
                        "state": TrackState.LOST,
                    }
                )
            )

        # Only currently visible IDs become the previous-frame set.
        #
        # Lost IDs are deliberately NOT inserted here because they are
        # tracked separately in _lost_track_ids.
        self._previous_track_ids = current_track_ids

        # Save the latest authoritative geometry for currently visible
        # tracks. LOST tracks retain their last known geometry.
        for track in current_tracks:
            if track.state in (
                TrackState.ACTIVE,
                TrackState.REACQUIRED,
            ):
                self._last_tracks[
                    track.track_id
                ] = track

        return current_tracks

    def _mark_missing_and_build_lost_tracks(
        self,
    ) -> list[Track]:
        """
        Mark all previously visible IDs as LOST and continue returning
        their last known Track representation.

        This intentionally does NOT clear _lost_track_ids.

        FollowManager is responsible for deciding when a selected target
        has exceeded its configured loss timeout.
        """
        self._lost_track_ids.update(
            self._previous_track_ids
        )

        lost_tracks: list[Track] = []

        for track_id in self._lost_track_ids:
            previous_track = self._last_tracks.get(
                track_id
            )

            if previous_track is None:
                continue

            lost_tracks.append(
                previous_track.model_copy(
                    update={
                        "state": TrackState.LOST,
                    }
                )
            )

        self._previous_track_ids.clear()

        return lost_tracks

    def _min_confirm_hits(self) -> int:
        if not TRACKING_DRONE_ONLY:
            return 1

        return max(1, TRACKING_MIN_CONFIRM_HITS)

    def _confirm_window(self) -> int:
        if not TRACKING_DRONE_ONLY:
            return 1

        return max(1, TRACKING_CONFIRM_WINDOW)

    def _hit_has_expired(self, hit_frame: int) -> bool:
        return (
            self._frame_index - hit_frame
            >= self._confirm_window()
        )

    def _prune_hit_deque(self, hits: deque[int]) -> None:
        while hits and self._hit_has_expired(hits[0]):
            hits.popleft()

    def _is_confirmed(self, track_id: int) -> bool:
        return track_id in self._confirmed_track_ids

    def _tentative_hit_count(self, track_id: int) -> int:
        hits = self._tentative_hits.get(track_id)

        if not hits:
            return 0

        return sum(
            1
            for hit_frame in hits
            if not self._hit_has_expired(hit_frame)
        )

    def _record_tentative_hit(self, track_id: int) -> int:
        hits = self._tentative_hits.setdefault(
            track_id,
            deque(),
        )
        self._prune_hit_deque(hits)
        hits.append(self._frame_index)

        return len(hits)

    def _prune_tentative_hits(self) -> None:
        """
        Expire old tentative observations and delete IDs that have
        no remaining hits in the confirmation window.
        """
        stale_ids: list[int] = []

        for track_id, hits in self._tentative_hits.items():
            self._prune_hit_deque(hits)

            if not hits:
                stale_ids.append(track_id)

        for track_id in stale_ids:
            del self._tentative_hits[track_id]

    def _log_missing_track_ids(self) -> None:
        logger.debug(
            "frame_index=%s modality=%s tracker_id=None "
            "accepted=False reason=missing_track_id",
            self._frame_index,
            self.modality,
        )

    @staticmethod
    def _bbox_iou(
        bbox_a: list[float],
        bbox_b: list[float],
    ) -> float:
        ax1, ay1, ax2, ay2 = bbox_a
        bx1, by1, bx2, by2 = bbox_b

        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)

        inter_w = max(0.0, inter_x2 - inter_x1)
        inter_h = max(0.0, inter_y2 - inter_y1)
        intersection = inter_w * inter_h

        area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
        area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
        union = area_a + area_b - intersection

        if union <= 0.0:
            return 0.0

        return intersection / union

    @staticmethod
    def _suppress_duplicate_candidates(
        candidates: list[dict[str, Any]],
        iou_threshold: float = TRACKING_DUPLICATE_IOU,
    ) -> list[dict[str, Any]]:
        """
        Keep the highest-confidence box when same-class boxes overlap.
        """
        if len(candidates) < 2:
            return list(candidates)

        ranked = sorted(
            candidates,
            key=lambda item: (
                -item["confidence"],
                item["track_id"],
            ),
        )

        kept: list[dict[str, Any]] = []

        for candidate in ranked:
            duplicate = False

            for retained in kept:
                if retained["class_name"] != candidate["class_name"]:
                    continue

                iou = Dev2TrackingProvider._bbox_iou(
                    candidate["bbox"],
                    retained["bbox"],
                )

                if iou >= iou_threshold:
                    duplicate = True
                    break

            if not duplicate:
                kept.append(candidate)

        kept.sort(key=lambda item: item["track_id"])
        return kept

    def _log_observation(
        self,
        *,
        local_class: int,
        confidence: float,
        tracker_id: int,
        bbox: list[float],
        accepted: bool,
        reason: str,
        hit_count: int,
        confirmed: bool,
    ) -> None:
        bbox_width = bbox[2] - bbox[0]
        bbox_height = bbox[3] - bbox[1]

        logger.debug(
            "frame_index=%s tracker_id=%s confidence=%.4f "
            "bbox_width=%.2f bbox_height=%.2f tentative_hits=%s "
            "confirmed=%s modality=%s local_class=%s bbox=%s "
            "accepted=%s reason=%s",
            self._frame_index,
            tracker_id,
            confidence,
            bbox_width,
            bbox_height,
            hit_count,
            confirmed,
            self.modality,
            local_class,
            bbox,
            accepted,
            reason,
        )

    @staticmethod
    def _canonical_class_name(
        source_class_id: int,
        names: Any,
    ) -> str | None:
        """
        Convert a Dev2 source class to SHIBLI's canonical class name.

        Local class 0 is drone and local class 1 is helicopter.
        Model name tables are used only as a fallback.
        """
        mapped_name = _LOCAL_CLASS_TO_CANONICAL_NAME.get(
            source_class_id
        )

        if mapped_name is not None:
            return mapped_name

        if isinstance(names, dict):
            source_name = names.get(
                source_class_id
            )

        elif isinstance(names, list):
            if 0 <= source_class_id < len(names):
                source_name = names[source_class_id]
            else:
                source_name = None

        else:
            source_name = None

        if source_name is None:
            return None

        normalized_name = (
            str(source_name)
            .strip()
            .lower()
        )

        if normalized_name in CLASS_ID_BY_NAME:
            return normalized_name

        return None