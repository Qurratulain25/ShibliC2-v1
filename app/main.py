from __future__ import annotations

import asyncio
import os
import shutil
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .core.bootstrap_env import bootstrap_environment
from .core.paths import project_root

bootstrap_environment(project_root())

from .auth.service import create_access_token, get_current_user, require_permission, startup_auth
from .core.config import is_production, load_config
from .core.database import list_local_cameras, log_action
from .core.logging_setup import configure_logging
from .core.modules import list_modules
from .core.paths import data_dir, recordings_dir, static_dir
from .core.version import APP_VERSION_DISPLAY, APP_VERSION_PACKAGE, PRODUCT_NAME
from .hardware import gateway
from .models import (
    AutoPanRequest,
    IlluminationRequest,
    LayoutRequest,
    LRFRequest,
    OSDConfigRequest,
    OSDRequest,
    PTZLensRequest,
    PTZMoveRequest,
    PresetRequest,
    QuickActionRequest,
    RecordingMode,
    RecordingRequest,
)
from .routes.auth import router as auth_router
from .routes.backend import router as backend_router
from .routes.cameras_route import router as cameras_router
from .routes.media_route import router as media_router
from .routes.settings_route import recordings_router, router as settings_router

APP_VERSION = APP_VERSION_DISPLAY

runtime_state: Dict[str, Any] = {
    "system_online": True,
    "recording": RecordingMode.off,
    "osd_enabled": False,
    "osd_config": {
        "show_telemetry": True,
        "show_logo": True,
        "logo_text": "SHIBLI C2",
        "custom_text": "",
        "position": "bottom-left",
    },
    "layout": "day_thermal",
    "selected_module": "dashboard",
    "selected_ptz": "ptz-1",
}
_cached_services: Dict[str, Any] = {}
_services_tick: int = 0


def _resolve_camera_id(
    ptz_id: str | None,
    camera_id: str | None,
    connection_mode: str | None = None,
) -> str | None:
    if camera_id:
        return camera_id
    if not ptz_id:
        return None
    for cam in list_local_cameras(connection_mode=connection_mode):
        if cam.get("enabled") and cam.get("ptzMapping") == ptz_id and cam.get("ipAddress"):
            return f"{cam['ipAddress']}:{cam.get('onvifPort') or 80}"
    return None


def _audit(user: Dict[str, Any], action: str, detail: str = "", module: str = "controls") -> None:
    log_action(
        user.get("username"),
        action,
        detail,
        role_name=user.get("roleName", ""),
        module=module,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    from .core.db_engine import require_sqlcipher, verify_encrypted
    from .core.paths import data_dir

    require_sqlcipher()
    # Create/migrate DB on first run before enforcing encrypted verification.
    startup_auth()
    db_path = data_dir() / "shibli_c2.db"
    ok, detail = verify_encrypted(db_path)
    if not ok:
        raise RuntimeError(
            f"SQLCipher database verification failed: {detail}. "
            "Check SHIBLI_DB_KEY in data/.env and restart."
        )
    from .core.settings_store import get_all_settings
    from .services.recording_engine import recording_engine

    settings = get_all_settings()
    runtime_state["osd_config"] = settings.get("osd_config") or runtime_state["osd_config"]
    runtime_state["layout"] = settings.get("default_layout") or runtime_state["layout"]
    if settings.get("hw_simulate") and hasattr(gateway, "set_simulate"):
        gateway.set_simulate(True)

    async def retention_loop() -> None:
        await asyncio.sleep(2)
        try:
            from .services.retention import enforce_retention
            await asyncio.to_thread(enforce_retention)
        except Exception as exc:
            print(f"Retention check skipped: {exc}")
        while True:
            await asyncio.sleep(3600)
            try:
                from .services.retention import enforce_retention
                await asyncio.to_thread(enforce_retention)
            except Exception:
                pass

    retention_task = asyncio.create_task(retention_loop())

    display_host = "127.0.0.1" if os.getenv("VMS_HOST", "127.0.0.1") in ("0.0.0.0", "::") else os.getenv("VMS_HOST", "127.0.0.1")
    port = int(os.getenv("VMS_PORT", "8080"))
    url = f"http://{display_host}:{port}"
    print(f"{PRODUCT_NAME} {APP_VERSION_DISPLAY} running at {url}", flush=True)
    if os.getenv("VMS_HOST", "127.0.0.1") in ("0.0.0.0", "::"):
        print(f"  Local UI: http://127.0.0.1:{port}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    yield
    retention_task.cancel()
    recording_engine.stop_all("system")


_docs = None if is_production() else "/api/docs"
app = FastAPI(
    title=PRODUCT_NAME,
    version=APP_VERSION_PACKAGE,
    docs_url=_docs,
    redoc_url=None if is_production() else "/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(backend_router)
app.include_router(cameras_router)
app.include_router(settings_router)
app.include_router(recordings_router)
app.include_router(media_router)
app.mount("/static", StaticFiles(directory=static_dir()), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(static_dir() / "index.html")


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "version": APP_VERSION_DISPLAY, "product": PRODUCT_NAME}


@app.get("/api/config")
def config(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return load_config()


@app.get("/api/modules")
def modules(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    cfg = load_config()
    return {"modules": list_modules(cfg.get("phase", 1))}


@app.get("/api/status")
async def status(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    from .services.shibli_client import backend_status
    from .core.database import list_local_cameras

    cfg = load_config()
    rec_root = recordings_dir()
    usage = shutil.disk_usage(rec_root)
    services = await backend_status()
    local_cams = list_local_cameras(connection_mode=user.get("connectionMode"))
    enabled_cams = [c for c in local_cams if c.get("enabled")]
    controls_online = bool(services.get("controls", {}).get("online"))
    vss_online = bool(services.get("vss", {}).get("online"))
    core_online = bool(services.get("core", {}).get("online"))
    return {
        **runtime_state,
        "version": APP_VERSION,
        "site_label": cfg.get("site_label", "Edge Node"),
        "user": {"username": user["username"], "roleName": user["roleName"]},
        "hardware": gateway.snapshot(),
        "storage": {
            "recordings_path": str(rec_root),
            "free_gb": round(usage.free / (1024 ** 3), 1),
            "total_gb": round(usage.total / (1024 ** 3), 1),
        },
        "services": {
            "app": {"online": True, "label": "App"},
            "controls": {"online": controls_online, "label": "Controls Service"},
            "vss": {"online": vss_online, "label": "VSS Service"},
            "core": {"online": core_online, "label": "Core Service"},
        },
        "cameras_mapped": len(enabled_cams),
        "recording_mode_label": "Local" if runtime_state.get("recording") != "off" else "Unavailable",
        "offline_mode": True,
    }


@app.post("/api/layout")
def set_layout(
    payload: LayoutRequest,
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
) -> Dict[str, Any]:
    runtime_state["layout"] = payload.layout
    _audit(user, "layout_change", payload.layout, module="dashboard")
    return {"ok": True, "layout": payload.layout}


@app.post("/api/recording")
def set_recording(
    payload: RecordingRequest,
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
) -> Dict[str, Any]:
    from .services.recording_engine import recording_engine

    runtime_state["recording"] = payload.mode
    rec_info = recording_engine.set_mode(payload.mode, user["username"])
    _audit(user, "recording_mode", str(payload.mode), module="recordings")
    return {"ok": True, "recording": payload.mode, **rec_info}


@app.post("/api/osd")
def set_osd(
    payload: OSDRequest,
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
) -> Dict[str, Any]:
    runtime_state["osd_enabled"] = payload.enabled
    _audit(user, "osd_toggle", "on" if payload.enabled else "off", module="dashboard")
    return {"ok": True, "osd_enabled": payload.enabled, "osd_config": runtime_state.get("osd_config")}


@app.post("/api/osd/config")
def set_osd_config(
    payload: OSDConfigRequest,
    user: Dict[str, Any] = Depends(require_permission("manage-settings")),
) -> Dict[str, Any]:
    from .core.settings_store import update_settings

    cfg = dict(runtime_state.get("osd_config") or {})
    patch = payload.model_dump(exclude_unset=True)
    cfg.update(patch)
    runtime_state["osd_config"] = cfg
    update_settings({"osd_config": cfg})
    _audit(user, "osd_config", str(list(patch.keys())), module="settings")
    return {"ok": True, "osd_config": cfg}


@app.post("/api/ptz/move")
def ptz_move(
    payload: PTZMoveRequest,
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
) -> Dict[str, Any]:
    cam = _resolve_camera_id(payload.ptz_id, payload.camera_id, user.get("connectionMode"))
    _audit(user, "ptz_move", f"{payload.direction} ptz={payload.ptz_id} cam={cam or '—'}")
    return gateway.move_ptz(payload.direction, payload.speed, payload.mode, payload.ptz_id, cam)


@app.post("/api/ptz/start")
def ptz_start(
    payload: PTZMoveRequest,
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
) -> Dict[str, Any]:
    cam = _resolve_camera_id(payload.ptz_id, payload.camera_id, user.get("connectionMode"))
    _audit(user, "ptz_start", f"{payload.direction} ptz={payload.ptz_id} cam={cam or '—'}")
    if hasattr(gateway, "start_ptz"):
        return gateway.start_ptz(payload.direction, payload.speed, payload.mode, payload.ptz_id, cam)
    return gateway.move_ptz(payload.direction, payload.speed, payload.mode, payload.ptz_id, cam)


@app.post("/api/ptz/stop")
def ptz_stop(
    payload: PTZMoveRequest,
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
) -> Dict[str, Any]:
    cam = _resolve_camera_id(payload.ptz_id, payload.camera_id, user.get("connectionMode"))
    _audit(user, "ptz_stop", f"ptz={payload.ptz_id} cam={cam or '—'}")
    if hasattr(gateway, "stop_ptz"):
        return gateway.stop_ptz(cam)
    return gateway.move_ptz("stop", payload.speed, payload.mode, payload.ptz_id, cam)


@app.post("/api/ptz/warm")
def ptz_warm(
    payload: PTZMoveRequest,
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
) -> Dict[str, Any]:
    cam = _resolve_camera_id(payload.ptz_id, payload.camera_id, user.get("connectionMode"))
    if hasattr(gateway, "warm_camera"):
        return gateway.warm_camera(cam)
    return {"ok": True, "camera_id": cam}


@app.post("/api/ptz/auto-pan")
def ptz_auto_pan(
    payload: AutoPanRequest,
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
) -> Dict[str, Any]:
    cam = _resolve_camera_id(None, payload.camera_id, user.get("connectionMode"))
    _audit(user, "ptz_auto_pan", f"enabled={payload.enabled} cam={cam or '—'}")
    if hasattr(gateway, "set_auto_pan"):
        return gateway.set_auto_pan(payload.enabled, cam, payload.speed)
    return {"ok": True, "auto_pan": payload.enabled}


@app.post("/api/ptz/lens")
def ptz_lens(
    payload: PTZLensRequest,
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
) -> Dict[str, Any]:
    cam = _resolve_camera_id(payload.ptz_id, payload.camera_id, user.get("connectionMode"))
    _audit(user, "ptz_lens", f"{payload.action} cam={cam or '—'}")
    return gateway.lens(payload.action, payload.ptz_id, cam)


@app.post("/api/ptz/preset/{action}")
def ptz_preset(
    action: str,
    payload: PresetRequest,
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
) -> Dict[str, Any]:
    if action not in {"set", "go", "delete"}:
        raise HTTPException(status_code=400, detail="action must be set, go, or delete")
    cam = _resolve_camera_id(payload.ptz_id, payload.camera_id, user.get("connectionMode"))
    _audit(user, f"preset_{action}", f"preset={payload.preset} cam={cam or '—'}")
    return gateway.preset(action, payload.preset, payload.ptz_id, cam)


@app.post("/api/lrf/measure")
def lrf_measure(
    payload: LRFRequest,
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
) -> Dict[str, Any]:
    cam = _resolve_camera_id(None, payload.camera_id, user.get("connectionMode"))
    _audit(user, "lrf_measure", f"mode={payload.mode} cam={cam or '—'}")
    return gateway.measure_lrf(payload.mode, cam)


@app.post("/api/illumination")
def illumination(
    payload: IlluminationRequest,
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
) -> Dict[str, Any]:
    data = payload.model_dump(exclude_unset=True)
    camera_id = _resolve_camera_id(None, data.pop("camera_id", None), user.get("connectionMode"))
    bump = data.pop("bump", None)
    _audit(user, "illumination", str({k: data.get(k) for k in sorted(data.keys())}))
    if bump:
        return gateway.bump_illumination(bump, camera_id)
    return gateway.set_illumination(camera_id, **data)


@app.post("/api/quick")
def quick(
    payload: QuickActionRequest,
    user: Dict[str, Any] = Depends(require_permission("control-camera")),
) -> Dict[str, Any]:
    _audit(user, "quick_action", f"{payload.group}:{payload.action}")
    return gateway.quick_action(payload.group, payload.action)


@app.websocket("/ws/status")
async def websocket_status(websocket: WebSocket) -> None:
    await websocket.accept()
    token = websocket.query_params.get("token")
    session_mode = "lan"
    try:
        if not token:
            await websocket.close(code=4401)
            return
        from .auth.service import decode_token
        payload = decode_token(token)
        session_mode = payload.get("connectionMode") or "lan"
    except Exception:
        await websocket.close(code=4401)
        return
    try:
        while True:
            global _cached_services, _services_tick
            _services_tick += 1
            if _services_tick == 1 or _services_tick % 5 == 0:
                from .services.shibli_client import backend_status
                _cached_services = await backend_status()
            # Never block the event loop on ONVIF/controls when simulating or offline
            if (
                hasattr(gateway, "fetch_ptz_status")
                and not getattr(gateway, "simulate", False)
                and getattr(gateway, "_connected", False)
            ):
                try:
                    await asyncio.wait_for(
                        asyncio.to_thread(gateway.fetch_ptz_status),
                        timeout=0.8,
                    )
                except Exception:
                    pass
            if getattr(getattr(gateway, "state", None), "lrf_continuous", False) and hasattr(gateway, "poll_lrf_distance"):
                try:
                    await asyncio.wait_for(
                        asyncio.to_thread(gateway.poll_lrf_distance),
                        timeout=0.8,
                    )
                except Exception:
                    pass
            cfg = load_config()
            rec_root = recordings_dir()
            usage = await asyncio.to_thread(shutil.disk_usage, rec_root)
            from .core.database import list_local_cameras
            try:
                cams = await asyncio.wait_for(
                    asyncio.to_thread(list_local_cameras, session_mode),
                    timeout=1.0,
                )
            except Exception:
                cams = []
            enabled = [c for c in cams if c.get("enabled")]
            await websocket.send_json({
                **runtime_state,
                "version": APP_VERSION,
                "site_label": cfg.get("site_label", "Edge Node"),
                "hardware": gateway.snapshot(),
                "storage": {
                    "free_gb": round(usage.free / (1024 ** 3), 1),
                    "total_gb": round(usage.total / (1024 ** 3), 1),
                },
                "services": _cached_services,
                "cameras_mapped": len(enabled),
                "recording_mode_label": "Local" if runtime_state.get("recording") != RecordingMode.off else "Unavailable",
                "offline_mode": True,
            })
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return
