"""Recording retention — delete files older than policy; circular space guard."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from ..core.config import load_config
from ..core.database import delete_recording, list_local_recordings
from ..core.settings_store import get_all_settings
from ..services.recordings_local import recording_storage_path

logger = logging.getLogger(__name__)

STORAGE_WARN_GB = float(os.getenv("SHIBLI_STORAGE_WARN_GB", "5"))


def retention_days() -> int:
    settings = get_all_settings()
    cfg = load_config()
    return int(settings.get("retention_days") or cfg.get("recording", {}).get("retention_days", 30))


def _all_recordings() -> List[dict]:
    items: List[dict] = []
    page = 1
    while True:
        batch = list_local_recordings(page=page, page_size=500)
        rows = batch.get("items") or []
        if not rows:
            break
        items.extend(rows)
        if len(items) >= batch.get("total", 0):
            break
        page += 1
    return items


def enforce_retention() -> Dict[str, Any]:
    """Remove recordings older than retention_days from disk and DB."""
    days = retention_days()
    if days <= 0:
        return {"ok": True, "deleted": 0, "days": days}

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    deleted = 0
    for rec in _all_recordings():
        recorded_at = rec.get("recordedAt") or rec.get("recorded_at")
        if not recorded_at:
            continue
        try:
            ts = datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if ts >= cutoff:
            continue
        rid = rec.get("id")
        if rid is not None:
            delete_recording(int(rid))
            deleted += 1

    freed = _enforce_disk_cap()
    return {"ok": True, "deleted": deleted, "days": days, **freed}


def _enforce_disk_cap() -> Dict[str, Any]:
    """If free space below threshold, delete oldest recordings until above warn level."""
    root = recording_storage_path()
    try:
        import shutil
        usage = shutil.disk_usage(root)
        free_gb = usage.free / (1024 ** 3)
    except OSError:
        return {"circular_deleted": 0, "free_gb": None}

    if free_gb >= STORAGE_WARN_GB:
        return {"circular_deleted": 0, "free_gb": round(free_gb, 2)}

    circular_deleted = 0
    rows = sorted(_all_recordings(), key=lambda r: r.get("recordedAt") or r.get("recorded_at") or "")
    for rec in rows:
        if free_gb >= STORAGE_WARN_GB:
            break
        path = Path(rec.get("filePath") or rec.get("file_path") or "")
        size = 0
        try:
            if path.is_file():
                size = path.stat().st_size
        except OSError:
            pass
        rid = rec.get("id")
        if rid is not None:
            delete_recording(int(rid))
            circular_deleted += 1
            free_gb += size / (1024 ** 3)

    return {"circular_deleted": circular_deleted, "free_gb": round(free_gb, 2)}


def storage_status() -> Dict[str, Any]:
    import shutil
    root = recording_storage_path()
    usage = shutil.disk_usage(root)
    free_gb = usage.free / (1024 ** 3)
    return {
        "free_gb": round(free_gb, 1),
        "total_gb": round(usage.total / (1024 ** 3), 1),
        "warn_gb": STORAGE_WARN_GB,
        "low": free_gb < STORAGE_WARN_GB,
        "retention_days": retention_days(),
    }
