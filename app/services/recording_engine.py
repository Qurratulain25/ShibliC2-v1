"""Live recording via ffmpeg (RTSP copy or local test pattern when no camera)."""
from __future__ import annotations

import logging
import shutil
import signal
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ..core.database import list_local_cameras
from ..models import RecordingMode
from .recordings_local import finalize_recording, start_recording

logger = logging.getLogger(__name__)


class RecordingEngine:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: Dict[str, Dict[str, Any]] = {}

    def set_mode(self, mode: RecordingMode, username: str) -> Dict[str, Any]:
        if mode == RecordingMode.off:
            return self._stop_all(username)

        want: set[str] = set()
        if mode in (RecordingMode.ch1, RecordingMode.both):
            want.add("day")
        if mode in (RecordingMode.ch2, RecordingMode.both):
            want.add("thermal")

        with self._lock:
            for channel in list(self._jobs):
                if channel not in want:
                    self._stop_channel(channel, username)
            started = []
            for channel in want:
                if channel not in self._jobs:
                    job = self._start_channel(channel, username)
                    if job:
                        started.append(job)
            return {"ok": True, "active": list(self._jobs.keys()), "started": started}

    def stop_all(self, username: str = "system") -> None:
        self._stop_all(username)

    def _camera_for_channel(self, channel: str) -> Optional[Dict[str, Any]]:
        for cam in list_local_cameras():
            if not cam.get("enabled"):
                continue
            ctype = (cam.get("cameraType") or "").lower()
            if ctype == channel or (channel == "day" and ctype == "day") or (channel == "thermal" and ctype == "thermal"):
                return cam
        return None

    def _ffmpeg_cmd(self, rtsp: str, path: Path, channel: str) -> Optional[list[str]]:
        from ..core.sidecars import resolve_ffmpeg_bin

        ffmpeg = resolve_ffmpeg_bin()
        if not ffmpeg:
            return None
        ffmpeg_bin = str(ffmpeg)
        if rtsp:
            return [
                ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "error",
                "-rtsp_transport", "tcp",
                "-i", rtsp,
                "-c", "copy",
                "-movflags", "+faststart",
                "-f", "mp4",
                str(path),
            ]
        label = channel.upper()
        return [
            ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=15",
            "-vf", f"drawtext=text='SHIBLI {label}':x=40:y=40:fontsize=28:fontcolor=white",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(path),
        ]

    def _start_channel(self, channel: str, username: str) -> Optional[Dict[str, Any]]:
        cam = self._camera_for_channel(channel)
        cam_name = (cam or {}).get("name") or f"{channel.title()} Camera"
        cam_id = channel.upper()
        if cam:
            if cam.get("ipAddress"):
                cam_id = f"{cam['ipAddress']}:{cam.get('onvifPort') or 80}"
            else:
                cam_id = str(cam.get("id", cam_id))

        meta = start_recording(cam_name, cam_id, "Live", username)
        path = Path(meta["file_path"])
        rtsp = (cam or {}).get("rtspUrl") or ""
        cmd = self._ffmpeg_cmd(rtsp, path, channel)

        proc = None
        placeholder = False
        if cmd:
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as exc:
                logger.warning("ffmpeg start failed for %s: %s", channel, exc)
                placeholder = True
        else:
            placeholder = True

        self._jobs[channel] = {
            "rec_id": meta["id"],
            "process": proc,
            "path": path,
            "started": datetime.now(timezone.utc),
        }
        return {
            "channel": channel,
            "recording_id": meta["id"],
            "file": meta["file_name"],
            "placeholder": placeholder,
            "rtsp": bool(rtsp),
        }

    def _stop_channel(self, channel: str, username: str) -> None:
        job = self._jobs.pop(channel, None)
        if not job:
            return
        proc = job.get("process")
        if proc and proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
        started = job.get("started") or datetime.now(timezone.utc)
        duration = max(0.1, (datetime.now(timezone.utc) - started).total_seconds())
        finalize_recording(int(job["rec_id"]), duration, username)

    def _stop_all(self, username: str) -> Dict[str, Any]:
        with self._lock:
            for channel in list(self._jobs):
                self._stop_channel(channel, username)
            return {"ok": True, "active": []}


recording_engine = RecordingEngine()
