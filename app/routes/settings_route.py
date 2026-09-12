from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..auth.service import get_current_user, require_permission, require_roles
from ..core.database import (
    delete_recording,
    list_audit_logs,
    list_local_recordings,
    log_action,
    rename_recording,
    db_info,
)
from ..core.paths import resolve_recording_path
from ..core.settings_store import get_all_settings, reset_to_defaults, update_settings
from ..services.recordings_local import recording_storage_path, start_recording

router = APIRouter(tags=["settings"])


class SettingsPatch(BaseModel):
    theme: Optional[str] = None
    recording_path: Optional[str] = None
    keyboard_enabled: Optional[bool] = None
    keyboard_map: Optional[Dict[str, str]] = None
    ptz_systems: Optional[list] = None
    default_page_size: Optional[int] = None
    app_port: Optional[int] = None
    service_urls: Optional[Dict[str, str]] = None
    device_drivers: Optional[Dict[str, str]] = None
    ptz_method: Optional[str] = None
    lrf_method: Optional[str] = None
    illuminator_method: Optional[str] = None
    hw_simulate: Optional[bool] = None
    osd_config: Optional[Dict[str, Any]] = None
    default_layout: Optional[str] = None
    retention_days: Optional[int] = None


class RenameRecordingRequest(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)


class StartRecordingRequest(BaseModel):
    camera_name: str
    camera_id: str
    recording_type: str = "Manual"


@router.get("/api/db/verify")
def verify_db(_: Dict[str, Any] = Depends(require_roles("ADMINISTRATOR"))) -> Dict[str, Any]:
    from ..core.database import db_info
    from ..core.paths import data_dir, project_root
    info = db_info()
    appdata = os.environ.get("LOCALAPPDATA", "")
    stale = str(Path(appdata) / "ShibliC2" / "shibli_c2.db") if appdata else ""
    return {
        **info,
        "dataDir": str(data_dir().resolve()),
        "projectRoot": str(project_root().resolve()),
        "appdataDbExists": Path(stale).exists() if stale else False,
        "appdataDbPath": stale,
    }

@router.get("/api/settings")
def get_settings(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return {"settings": get_all_settings(), "database": db_info(), "user": user["username"]}


@router.put("/api/settings")
def patch_settings(
    payload: SettingsPatch,
    user: Dict[str, Any] = Depends(require_permission("manage-settings")),
) -> Dict[str, Any]:
    patch = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    if "recording_path" in patch:
        requested = Path(str(patch["recording_path"]).strip()).expanduser()
        resolved = resolve_recording_path(requested, repair_db=False)
        if resolved.resolve() != requested.resolve():
            raise HTTPException(
                status_code=400,
                detail=f"Recording path is not writable on this machine: {requested}",
            )
        patch["recording_path"] = str(resolved)
    if "service_urls" in patch and isinstance(patch["service_urls"], dict):
        urls = patch["service_urls"]
        if urls.get("core"):
            os.environ["SHIBLI_CORE_URL"] = urls["core"]
        if urls.get("controls"):
            os.environ["SHIBLI_CONTROLS_URL"] = urls["controls"]
        if urls.get("vss"):
            os.environ["SHIBLI_VSS_URL"] = urls["vss"]
    result = update_settings(patch)
    if "hw_simulate" in patch:
        from ..hardware import gateway
        if hasattr(gateway, "set_simulate"):
            gateway.set_simulate(bool(patch["hw_simulate"]))
    if "osd_config" in patch:
        from .. import main as main_mod
        main_mod.runtime_state["osd_config"] = patch["osd_config"]
    log_action(user["username"], "settings_update", str(list(patch.keys())), role_name=user["roleName"], module="settings")
    return {"settings": result}


@router.post("/api/settings/reset")
def reset_settings(user: Dict[str, Any] = Depends(require_permission("manage-settings"))) -> Dict[str, Any]:
    result = reset_to_defaults()
    resolve_recording_path(result["recording_path"], repair_db=True)
    log_action(user["username"], "settings_reset", "defaults", role_name=user["roleName"], module="settings")
    return {"settings": result, "message": "Settings reset to default"}


@router.get("/api/audit-logs")
def audit_logs(
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    _: Dict[str, Any] = Depends(require_permission("view-audit-logs")),
) -> Dict[str, Any]:
    return {"logs": list_audit_logs(limit, offset)}


recordings_router = APIRouter(prefix="/api/recordings/local", tags=["recordings"])


@recordings_router.get("")
def list_recordings(
    search: str = "",
    sort: str = "date_desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    date_from: str = "",
    date_to: str = "",
    user: Dict[str, Any] = Depends(require_permission("get-streams")),
) -> Dict[str, Any]:
    default_ps = get_all_settings().get("default_page_size", 20)
    if page_size == 20:
        page_size = default_ps
    return list_local_recordings(search, sort, page, page_size, date_from, date_to)


@recordings_router.post("/start")
def record_start(
    payload: StartRecordingRequest,
    user: Dict[str, Any] = Depends(require_permission("manage-recordings")),
) -> Dict[str, Any]:
    return start_recording(payload.camera_name, payload.camera_id, payload.recording_type, user["username"])


@recordings_router.get("/{recording_id}/file")
def play_recording(
    recording_id: int,
    user: Dict[str, Any] = Depends(require_permission("get-streams")),
):
    from ..core.database import get_recording
    rec = get_recording(recording_id)
    if not rec:
        raise HTTPException(404, "Recording not found")
    path = Path(rec["file_path"])
    if not path.exists():
        raise HTTPException(404, "File not found on disk")
    return FileResponse(path, media_type="video/mp4", filename=rec["file_name"])


@recordings_router.delete("/{recording_id}")
def remove_recording(
    recording_id: int,
    user: Dict[str, Any] = Depends(require_permission("delete-recordings")),
) -> Dict[str, Any]:
    if not delete_recording(recording_id):
        raise HTTPException(404, "Recording not found")
    log_action(user["username"], "recording_delete", str(recording_id), role_name=user["roleName"], module="recordings")
    return {"ok": True}


@recordings_router.put("/{recording_id}/rename")
def rename_rec(
    recording_id: int,
    payload: RenameRecordingRequest,
    user: Dict[str, Any] = Depends(require_permission("manage-recordings")),
) -> Dict[str, Any]:
    if not rename_recording(recording_id, payload.file_name):
        raise HTTPException(404, "Recording not found")
    log_action(user["username"], "recording_rename", payload.file_name, role_name=user["roleName"], module="recordings")
    return {"ok": True}


@recordings_router.get("/storage-path")
def storage_path(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, str]:
    return {"path": str(recording_storage_path())}
