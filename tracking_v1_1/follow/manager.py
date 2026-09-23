from __future__ import annotations

import time
from typing import Callable, Literal

from .controller import FollowTarget
from ..models import Track, TrackState
from ..config import AUTO_FOLLOW_POLICY, AUTO_FOLLOW_POLICIES


FollowMode = Literal["MANUAL", "AUTO"]


class FollowManager:
    """
    Owns follow-selection and target-loss state.

    The TrackingProvider always supplies the complete list[Track].
    FollowManager keeps one selected Track ID without discarding
    any other tracks.

    Target-loss behavior:

        selected track seen
              ↓
        target temporarily missing / LOST
              ↓
        remember loss time
              ↓
        before timeout -> keep target selected, PTZ layer may STOP
              ↓
        target REACQUIRED -> continue following
              ↓
        timeout exceeded -> clear target
    """

    def __init__(
        self,
        *,
        follow_mode: FollowMode = "MANUAL",
        auto_follow_enabled: bool = False,
        lost_timeout: float = 2.0,
        selection_policy: str = "MANUAL",
        clock: Callable[[], float] | None = None,
    ) -> None:
        if lost_timeout < 0:
            raise ValueError("lost_timeout must be >= 0")

        if (
            selection_policy != "MANUAL"
            and selection_policy not in AUTO_FOLLOW_POLICIES
        ):
            raise ValueError(
                f"Unsupported follow selection policy: {selection_policy}"
            )

        self.active_track_id: int | None = None
        self.follow_mode: FollowMode = follow_mode
        self.auto_follow_enabled: bool = auto_follow_enabled
        self.lost_timeout: float = lost_timeout
        self.selection_policy: str = selection_policy

        self.last_seen_time: float | None = None
        self._lost_since: float | None = None
        self._tracks: list[Track] = []

        # Injectable clock makes loss-timeout behavior deterministic in tests.
        self._clock = clock or time.monotonic

    @property
    def active_follow_id(self) -> int | None:
        """
        Backwards-compatible name used by the current v1.1 API/UI.
        """
        return self.active_track_id

    @property
    def tracks(self) -> list[Track]:
        """
        Return all currently known tracks.

        Never returns only the selected target.
        """
        return list(self._tracks)

    @property
    def lost_since(self) -> float | None:
        return self._lost_since

    @property
    def target_is_waiting(self) -> bool:
        """
        True while the selected target is temporarily lost but has
        not yet exceeded lost_timeout.
        """
        if self.active_track_id is None:
            return False

        if self._lost_since is None:
            return False

        return self._elapsed_since_loss() <= self.lost_timeout

    def update(self, tracks: list[Track]) -> None:
        """
        Store the complete current tracking result and update
        selected-target loss state.

        No filtering of the track list occurs here.
        """
        self._tracks = list(tracks)

        if self.active_track_id is None:
            return

        now = self._clock()

        target = next(
            (
                track
                for track in self._tracks
                if track.track_id == self.active_track_id
            ),
            None,
        )

        if target is None:
            # Track is absent from this frame.
            if self.last_seen_time is None:
                self.last_seen_time = now

            if self._lost_since is None:
                self._lost_since = now

            self._clear_if_timeout_expired(now)
            return

        if target.state in (
            TrackState.ACTIVE,
            TrackState.REACQUIRED,
        ):
            self.last_seen_time = now
            self._lost_since = None
            return

        if target.state == TrackState.LOST:
            if self.last_seen_time is None:
                self.last_seen_time = now

            if self._lost_since is None:
                self._lost_since = now

            self._clear_if_timeout_expired(now)

    def select_track(self, track_id: int) -> FollowTarget:
        """
        Manually select one ACTIVE or REACQUIRED Track as the
        current follow target.
        """
        track = next(
            (
                item
                for item in self._tracks
                if item.track_id == track_id
            ),
            None,
        )

        if track is None:
            raise ValueError(
                f"Track ID {track_id} is not available"
            )

        if track.state not in (
            TrackState.ACTIVE,
            TrackState.REACQUIRED,
        ):
            raise ValueError(
                f"Track ID {track_id} is not active "
                "and cannot be followed"
            )

        now = self._clock()

        self.active_track_id = track_id
        self.auto_follow_enabled = False
        self.follow_mode = "MANUAL"
        self.last_seen_time = now
        self._lost_since = None

        return FollowTarget(track_id=track_id)

    def select(self, track_id: int) -> FollowTarget:
        """
        Backwards-compatible alias for the existing v1.1 API/tests.
        """
        return self.select_track(track_id)

    def clear_target(self) -> None:
        """
        Clear the selected follow target and its loss state.
        """
        self.active_track_id = None
        self.last_seen_time = None
        self._lost_since = None

    def clear(self) -> None:
        """
        Backwards-compatible alias for existing reset logic.
        """
        self.clear_target()

    def get_follow_target(
        self,
        tracks: list[Track],
    ) -> Track | None:
        """
        Return the selected Track only when it is currently available
        and followable.

        During a temporary loss this returns None, causing the PTZ
        controller to issue STOP, while the active_track_id is retained
        so a REACQUIRED track can resume follow.

        Once lost_timeout expires, the target is cleared.
        """
        if self.active_track_id is None:
            return None

        self.update(tracks)

        target = next(
            (
                track
                for track in tracks
                if track.track_id == self.active_track_id
            ),
            None,
        )

        if target is None:
            return None

        if target.state == TrackState.LOST:
            return None

        if target.state in (
            TrackState.ACTIVE,
            TrackState.REACQUIRED,
        ):
            return target

        return None

    def get_active_track(self) -> Track | None:
        """
        Return the currently selected followable Track from the manager's
        latest stored list.
        """
        return self.get_follow_target(self._tracks)

    def _elapsed_since_loss(self) -> float:
        if self._lost_since is None:
            return 0.0

        return max(0.0, self._clock() - self._lost_since)

    def _clear_if_timeout_expired(self, now: float) -> None:
        if self._lost_since is None:
            return

        if now - self._lost_since > self.lost_timeout:
            self.clear_target()

            if self.auto_follow_enabled:
                self._select_auto_target(self._tracks)

    def enable_auto_follow(self) -> None:
        self.auto_follow_enabled = True
        self.follow_mode = "AUTO"

        # MANUAL means no Auto Follow policy has been explicitly selected yet.
        # Use the configured default Auto Follow policy in that case.
        if self.selection_policy == "MANUAL":
            self.selection_policy = AUTO_FOLLOW_POLICY

        if self.active_track_id is None:
            self._select_auto_target(self._tracks)

    def disable_auto_follow(self) -> None:
        self.auto_follow_enabled = False
        self.follow_mode = "MANUAL"


    def set_selection_policy(self, policy: str) -> None:
        if policy not in AUTO_FOLLOW_POLICIES:
            raise ValueError(
                f"Unsupported auto-follow policy: {policy}"
            )

        self.selection_policy = policy

        if self.auto_follow_enabled:
            self.clear_target()
            self._select_auto_target(self._tracks)


    def _select_auto_target(
        self,
        tracks: list[Track],
    ) -> Track | None:
        """
        Select one active/reacquired track according to the configured
        policy.

        FIRST_ACTIVE is the only policy implemented for this POC.
        """
        candidates = [
            track
            for track in tracks
            if track.state in (
                TrackState.ACTIVE,
                TrackState.REACQUIRED,
            )
        ]

        if not candidates:
            return None

        if self.selection_policy == "FIRST_ACTIVE":
            target = candidates[0]

        elif self.selection_policy == "HIGHEST_CONFIDENCE":
            target = max(
                candidates,
                key=lambda track: track.confidence,
            )

        elif self.selection_policy == "LARGEST_BBOX":
            target = max(
                candidates,
                key=lambda track: (
                    max(0.0, track.bbox[2] - track.bbox[0])
                    * max(0.0, track.bbox[3] - track.bbox[1])
                ),
            )

        else:
            raise ValueError(
                f"Unsupported auto-follow policy: "
                f"{self.selection_policy}"
            )

        now = self._clock()

        self.active_track_id = target.track_id
        self.follow_mode = "AUTO"
        self.last_seen_time = now
        self._lost_since = None

        return target