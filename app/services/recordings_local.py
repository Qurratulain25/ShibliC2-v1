"""Local recording file naming and storage on D: data folder."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from ..core.database import insert_recording, log_action
from ..core.settings_store import get_all_settings
from ..core.paths import resolve_recording_path


def recording_storage_path() -> Path:
    settings = get_all_settings()
    return resolve_recording_path(settings.get("recording_path"), repair_db=True)


def build_filename(
    camera_name: str,
    camera_id: str,
    recording_type: str = "Manual",
    when: Optional[datetime] = None,
) -> str:
    ts = when or datetime.now()
    safe_cam = "".join(c if c.isalnum() else "_" for c in camera_name)[:32]
    safe_id = "".join(c if c.isalnum() else "_" for c in camera_id)[:16]
    date_part = ts.strftime("%Y-%m-%d")
    time_part = ts.strftime("%H-%M-%S")
    rtype = recording_type.replace(" ", "")
    return f"SHIBLI_{safe_cam}_{safe_id}_{date_part}_{time_part}_{rtype}.mp4"


def start_recording(
    camera_name: str,
    camera_id: str,
    recording_type: str,
    username: str,
) -> Dict[str, Any]:
    root = recording_storage_path()
    when = datetime.now()
    file_name = build_filename(camera_name, camera_id, recording_type, when)
    file_path = root / file_name
    file_path.touch(exist_ok=True)
    meta = {
        "file_name": file_name,
        "file_path": str(file_path),
        "camera_name": camera_name,
        "camera_id": camera_id,
        "recorded_at": when.isoformat(),
        "recording_type": recording_type,
        "recorded_by": username,
        "file_size_bytes": file_path.stat().st_size if file_path.exists() else 0,
    }
    rec_id = insert_recording(meta)
    log_action(username, "recording_start", file_name, module="recordings")
    return {"id": rec_id, **meta}


def finalize_recording(recording_id: int, duration_sec: float, username: str) -> None:
    from ..core.database import get_db
    with get_db() as conn:
        row = conn.execute("SELECT file_path FROM recordings WHERE id = ?", (recording_id,)).fetchone()
        size = 0
        if row and Path(row["file_path"]).exists():
            size = Path(row["file_path"]).stat().st_size
        conn.execute(
            "UPDATE recordings SET duration_sec = ?, file_size_bytes = ? WHERE id = ?",
            (duration_sec, size, recording_id),
        )
    log_action(username, "recording_stop", str(recording_id), module="recordings")
