from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from shutil import copyfileobj
from uuid import uuid4

import cv2
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .adapters import SimulatedPTZAdapter
from .follow import FollowManager, PTZFollowController
from .output import TrackLogger
from .output.export import write_annotated_mp4
from .processor import ProcessingResult, VideoProcessor
from .providers import Dev2TrackingProvider, MockTrackingProvider

router = APIRouter(
    prefix="/api/v1.1/tracking",
    tags=["v1.1 tracking"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"

_MOCK_PROVIDER = MockTrackingProvider()
_FOLLOW_MANAGER = FollowManager()
_PTZ_CONTROLLER = PTZFollowController(deadband=0.08)
_SIMULATED_PTZ = SimulatedPTZAdapter()

_ASSETS = {
    "tracking.js": STATIC_DIR / "tracking.js",
    "tracking.css": STATIC_DIR / "tracking.css",
}

OUTPUT_ROOT = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "tracking_outputs"
)

OUTPUT_ROOT.mkdir(
    parents=True,
    exist_ok=True,
)

_SESSION_LOCK = threading.Lock()
_SESSIONS: dict[str, dict[str, object]] = {}

@router.get("/health")
def tracking_health() -> dict[str, str]:
    return {
        "status": "ok",
        "module": "tracking_v1_1",
    }


@router.get("/ui")
def tracking_ui() -> FileResponse:
    return FileResponse(STATIC_DIR / "tracking.html")


@router.get("/assets/{asset_name}")
def tracking_asset(asset_name: str) -> FileResponse:
    path = _ASSETS.get(asset_name)

    if path is None:
        raise HTTPException(status_code=404, detail="Tracking asset not found")

    return FileResponse(path)


@router.get("/mock-tracks")
def mock_tracks() -> list[dict]:
    tracks = _MOCK_PROVIDER.process_frame(None)

    _FOLLOW_MANAGER.update(tracks)

    return [
        track.model_dump(mode="json")
        for track in tracks
    ]


@router.post("/mock/reset")
def reset_mock_tracks() -> dict[str, bool]:
    _MOCK_PROVIDER.reset()
    _FOLLOW_MANAGER.clear()
    _FOLLOW_MANAGER.update([])
    _SIMULATED_PTZ.reset()

    return {
        "ok": True,
    }


@router.get("/follow")
def follow_status() -> dict[str, int | None]:
    return {
        "active_follow_id": _FOLLOW_MANAGER.active_follow_id,
    }


@router.delete("/follow")
def clear_follow_track() -> dict[str, bool]:
    _FOLLOW_MANAGER.clear()

    return {
        "ok": True,
    }


@router.get("/follow/ptz")
def follow_ptz(
    frame_width: int = 960,
    frame_height: int = 540,
) -> dict[str, object]:
    target = _FOLLOW_MANAGER.get_active_track()

    command = _PTZ_CONTROLLER.update(
        target,
        frame_width,
        frame_height,
    )

    if command.command_text == "STOP":
        simulated_command = _SIMULATED_PTZ.stop()
    else:
        speed = max(command.pan_speed, command.tilt_speed)

        simulated_command = _SIMULATED_PTZ.move(
            pan=command.pan,
            tilt=command.tilt,
            speed=speed,
        )

    return {
        "track_id": (
            target.track_id
            if target is not None
            else None
        ),
        **command.as_dict(),
        "simulated_ptz": {
            "pan": simulated_command.pan,
            "tilt": simulated_command.tilt,
            "speed": simulated_command.speed,
        },
    }

@router.get("/follow/config")
def follow_config() -> dict[str, object]:
    return {
        "mode": _FOLLOW_MANAGER.follow_mode,
        "auto_follow_enabled": _FOLLOW_MANAGER.auto_follow_enabled,
        "selection_policy": _FOLLOW_MANAGER.selection_policy,
        "active_follow_id": _FOLLOW_MANAGER.active_follow_id,
        "lost_timeout": _FOLLOW_MANAGER.lost_timeout,
    }


@router.post("/follow/auto")
def enable_auto_follow() -> dict[str, object]:
    _FOLLOW_MANAGER.enable_auto_follow()

    return {
        "mode": _FOLLOW_MANAGER.follow_mode,
        "auto_follow_enabled": _FOLLOW_MANAGER.auto_follow_enabled,
        "selection_policy": _FOLLOW_MANAGER.selection_policy,
        "active_follow_id": _FOLLOW_MANAGER.active_follow_id,
    }


@router.delete("/follow/auto")
def disable_auto_follow() -> dict[str, object]:
    _FOLLOW_MANAGER.disable_auto_follow()

    return {
        "mode": _FOLLOW_MANAGER.follow_mode,
        "auto_follow_enabled": _FOLLOW_MANAGER.auto_follow_enabled,
        "selection_policy": _FOLLOW_MANAGER.selection_policy,
        "active_follow_id": _FOLLOW_MANAGER.active_follow_id,
    }

@router.post("/follow/{track_id}")
def select_follow_track(track_id: int) -> dict[str, int]:
    try:
        target = _FOLLOW_MANAGER.select(track_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return {
        "active_follow_id": target.track_id,
    }

@router.post("/follow/policy/{policy}")
def set_follow_policy(policy: str) -> dict[str, object]:
    try:
        _FOLLOW_MANAGER.set_selection_policy(policy)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return {
        "selection_policy": _FOLLOW_MANAGER.selection_policy,
        "auto_follow_enabled": _FOLLOW_MANAGER.auto_follow_enabled,
        "active_follow_id": _FOLLOW_MANAGER.active_follow_id,
    }


def _create_session_directory() -> tuple[str, Path]:
    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    session_id = (
        f"{timestamp}_{uuid4().hex[:8]}"
    )

    session_dir = OUTPUT_ROOT / session_id
    session_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    return session_id, session_dir


def _session_urls(session_id: str) -> dict[str, str]:
    base = f"/api/v1.1/tracking/sessions/{session_id}"

    return {
        "input": f"{base}/input.mp4",
        "annotated": f"{base}/annotated.mp4",
        "json": f"{base}/tracks.json",
        "csv": f"{base}/tracks.csv",
        "status": (
            f"/api/v1.1/tracking/session/{session_id}/status"
        ),
    }


def _write_session_status(
    session_id: str,
    **fields: object,
) -> dict[str, object]:
    with _SESSION_LOCK:
        current = dict(_SESSIONS.get(session_id, {}))
        current.update(fields)
        current["session_id"] = session_id

        processed = int(current.get("frames_processed") or 0)
        total = int(current.get("total_frames") or 0)

        if total > 0:
            current["percent"] = round(
                min(100.0, (processed / total) * 100.0),
                1,
            )
        elif current.get("status") == "READY":
            current["percent"] = 100.0
        else:
            current["percent"] = 0.0

        _SESSIONS[session_id] = current

        status_path = OUTPUT_ROOT / session_id / "status.json"
        status_path.write_text(
            json.dumps(current, indent=2),
            encoding="utf-8",
        )

        return current


def _read_session_status(session_id: str) -> dict[str, object] | None:
    with _SESSION_LOCK:
        cached = _SESSIONS.get(session_id)

        if cached is not None:
            return dict(cached)

    status_path = OUTPUT_ROOT / session_id / "status.json"

    if not status_path.is_file():
        return None

    try:
        loaded = json.loads(
            status_path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError:
        return None

    if not isinstance(loaded, dict):
        return None

    with _SESSION_LOCK:
        _SESSIONS[session_id] = loaded

    return dict(loaded)


def _probe_video(
    path: Path,
) -> tuple[int, float, int, int]:
    capture = cv2.VideoCapture(str(path))

    if not capture.isOpened():
        return 0, 0.0, 0, 0

    try:
        return (
            int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0),
            float(capture.get(cv2.CAP_PROP_FPS) or 0.0),
            int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0),
            int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0),
        )
    finally:
        capture.release()


def _run_session_processing(
    session_id: str,
    *,
    modality: str,
    filename: str,
    input_path: Path,
    annotated_path: Path,
    json_path: Path,
    csv_path: Path,
    session_json: Path,
) -> None:
    try:
        _write_session_status(
            session_id,
            status="PROCESSING",
        )

        logger = TrackLogger(
            json_path=json_path,
            csv_path=csv_path,
        )

        provider = Dev2TrackingProvider(modality)
        processor = VideoProcessor(
            provider,
            overlay=None,
            follow_manager=None,
            logger=logger,
        )

        def on_progress(
            frames_processed: int,
            total_frames: int,
        ) -> None:
            _write_session_status(
                session_id,
                status="PROCESSING",
                frames_processed=frames_processed,
                total_frames=total_frames,
            )

        result: ProcessingResult = processor.process_file(
            input_path,
            None,
            on_progress=on_progress,
        )

        session_data = {
            "session_id": session_id,
            "status": "READY",
            "input_filename": filename,
            "modality": modality,
            "frame_count": result.frame_count,
            "frames_processed": result.frame_count,
            "total_frames": result.frame_count,
            "percent": 100.0,
            "fps": result.fps,
            "width": result.width,
            "height": result.height,
            "duration_s": result.duration_s,
            "active_follow_id": (
                _FOLLOW_MANAGER.active_follow_id
            ),
            "files": {
                "input": "input.mp4",
                "annotated": "annotated.mp4",
                "json": "tracks.json",
                "csv": "tracks.csv",
            },
            "urls": _session_urls(session_id),
        }

        session_json.write_text(
            json.dumps(session_data, indent=2),
            encoding="utf-8",
        )

        _write_session_status(**session_data)

    except Exception as exc:
        _write_session_status(
            session_id,
            status="FAILED",
            error=str(exc),
        )


@router.post("/process")
def process_uploaded_video(
    video: UploadFile = File(...),
    modality: str = Form(...),
) -> dict[str, object]:
    filename = video.filename or "input.mp4"

    modality = modality.strip().lower()

    if modality not in {"rgb", "thermal"}:
        raise HTTPException(
            status_code=400,
            detail="Modality must be 'rgb' or 'thermal'.",
        )

    if not filename.lower().endswith(".mp4"):
        raise HTTPException(
            status_code=400,
            detail="Only MP4 input is supported.",
        )

    session_id, session_dir = (
        _create_session_directory()
    )

    input_path = session_dir / "input.mp4"
    annotated_path = session_dir / "annotated.mp4"
    json_path = session_dir / "tracks.json"
    csv_path = session_dir / "tracks.csv"
    session_json = session_dir / "session.json"

    try:
        with input_path.open("wb") as handle:
            copyfileobj(video.file, handle)
    finally:
        video.file.close()

    total_frames, fps, width, height = _probe_video(
        input_path
    )

    status = _write_session_status(
        session_id,
        status="QUEUED",
        input_filename=filename,
        modality=modality,
        frames_processed=0,
        total_frames=total_frames,
        fps=fps,
        width=width,
        height=height,
        files={
            "input": "input.mp4",
            "annotated": "annotated.mp4",
            "json": "tracks.json",
            "csv": "tracks.csv",
        },
        urls=_session_urls(session_id),
    )

    worker = threading.Thread(
        target=_run_session_processing,
        kwargs={
            "session_id": session_id,
            "modality": modality,
            "filename": filename,
            "input_path": input_path,
            "annotated_path": annotated_path,
            "json_path": json_path,
            "csv_path": csv_path,
            "session_json": session_json,
        },
        daemon=True,
        name=f"tracking-session-{session_id}",
    )
    worker.start()

    return {
        **status,
        "status": status.get("status", "QUEUED"),
    }


@router.get("/session/{session_id}/status")
def tracking_session_status(
    session_id: str,
) -> dict[str, object]:
    status = _read_session_status(session_id)

    if status is None:
        raise HTTPException(
            status_code=404,
            detail="Tracking session not found.",
        )

    return status


@router.post("/session/{session_id}/export/mp4")
def export_annotated_session_mp4(
    session_id: str,
) -> FileResponse:
    session_dir = OUTPUT_ROOT / session_id
    input_path = session_dir / "input.mp4"
    json_path = session_dir / "tracks.json"
    annotated_path = session_dir / "annotated.mp4"
    status = _read_session_status(session_id)

    if status is None or not session_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail="Tracking session not found.",
        )

    if status.get("status") != "READY":
        raise HTTPException(
            status_code=409,
            detail="Tracking results are not ready yet.",
        )

    if not input_path.is_file() or not json_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Tracking results are not ready yet.",
        )

    try:
        if not annotated_path.is_file():
            write_annotated_mp4(
                input_path,
                json_path,
                annotated_path,
            )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not create the video export: {exc}",
        ) from exc

    return FileResponse(
        annotated_path,
        filename="annotated.mp4",
    )


@router.get(
    "/sessions/{session_id}/{filename}"
)
def tracking_session_file(
    session_id: str,
    filename: str,
) -> FileResponse:
    allowed_files = {
        "input.mp4",
        "annotated.mp4",
        "tracks.json",
        "tracks.csv",
        "session.json",
        "status.json",
    }

    if filename not in allowed_files:
        raise HTTPException(
            status_code=404,
            detail="Output file not found.",
        )

    session_dir = OUTPUT_ROOT / session_id

    if not session_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail="Tracking session not found.",
        )

    path = session_dir / filename

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Output file not found.",
        )

    return FileResponse(path)