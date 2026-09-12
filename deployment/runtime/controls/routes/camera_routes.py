# routes/camera_routes.py
from fastapi import APIRouter, Depends, Query
from typing import Optional
from controllers.camera_controller import (
    camera_controller,
    MotorSpeedRequest,
    FocusModeRequest,
    FocusPositionRequest,
    IlluminatorRequest,
    IlluminatorBrightnessRequest,
    IlluminatorFOVRequest,
    PresetCreateRequest,
    PresetUpdateRequest,
    AutoPanRequest,
    StreamUriRequest,
    CameraRegistrationRequest,
    CameraIdRequest,
    TrackingRequest,
    BrightnessRequest,
    ContrastRequest,
    PolarityRequest
)
from controllers.lrf_controller import (
    lrf_controller,
    LRFRegistrationRequest
)
from middleware.auth import allowed_roles_and_required_permission

router = APIRouter()

# Define auth dependency for camera control
auth_dependency = Depends(allowed_roles_and_required_permission(["OPERATOR", "ADMINISTRATOR"], "control-camera"))
view_dependency = Depends(allowed_roles_and_required_permission(["OPERATOR", "ADMINISTRATOR"], "control-camera"))
admin_dependency = Depends(allowed_roles_and_required_permission(["ADMINISTRATOR"], "control-camera"))


# ==================== Camera Management Routes ====================

@router.get("/cameras")
async def list_cameras(current_user: dict = view_dependency):
    """List all registered cameras"""
    return await camera_controller.list_cameras(current_user)

@router.post("/cameras/register")
async def register_camera(request: CameraRegistrationRequest, current_user: dict = admin_dependency):
    """Register a new camera"""
    return await camera_controller.register_camera(request, current_user)

@router.delete("/cameras/{camera_id}")
async def unregister_camera(camera_id: str, current_user: dict = admin_dependency):
    """Unregister a camera"""
    return await camera_controller.unregister_camera(camera_id, current_user)

@router.post("/cameras/{camera_id}/connect")
async def connect_camera(camera_id: str, current_user: dict = auth_dependency):
    """Connect to a camera"""
    return await camera_controller.connect_camera(camera_id, current_user)

@router.post("/cameras/{camera_id}/disconnect")
async def disconnect_camera(camera_id: str, current_user: dict = auth_dependency):
    """Disconnect from a camera"""
    return await camera_controller.disconnect_camera(camera_id, current_user)

@router.get("/cameras/{camera_id}/status")
async def get_camera_status(camera_id: str, current_user: dict = view_dependency):
    """Get camera connection status"""
    return await camera_controller.get_camera_status(camera_id, current_user)

@router.post("/cameras/default")
async def set_default_camera(request: CameraIdRequest, current_user: dict = admin_dependency):
    """Set the default camera"""
    return await camera_controller.set_default_camera(request, current_user)


# ==================== PTZ Control Routes ====================

@router.post("/zoom-in")
async def zoom_in(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    return await camera_controller.zoom_in(current_user, camera_id)

@router.post("/zoom-out")
async def zoom_out(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    return await camera_controller.zoom_out(current_user, camera_id)

@router.post("/pan-left")
async def pan_left(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    return await camera_controller.pan_left(current_user, camera_id)

@router.post("/pan-right")
async def pan_right(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    return await camera_controller.pan_right(current_user, camera_id)

@router.post("/pan-top")
async def pan_top(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    return await camera_controller.pan_top(current_user, camera_id)

@router.post("/pan-bottom")
async def pan_bottom(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    return await camera_controller.pan_bottom(current_user, camera_id)

@router.post("/stop")
async def stop(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    return await camera_controller.stop(current_user, camera_id)

@router.post("/home")
async def go_home(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    return await camera_controller.go_home(current_user, camera_id)

@router.get("/status")
async def get_status(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = view_dependency
):
    return await camera_controller.get_status(current_user, camera_id)

@router.get("/zoom-level")
async def get_zoom_level(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = view_dependency
):
    return await camera_controller.get_zoom_level(current_user, camera_id)


# ==================== Start/Stop PTZ Routes (for press-and-hold controls) ====================

@router.post("/start-pan-left")
async def start_pan_left(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    """Start panning left (call /stop to stop). Use for press-and-hold controls."""
    return await camera_controller.start_pan_left(current_user, camera_id)

@router.post("/start-pan-right")
async def start_pan_right(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    """Start panning right (call /stop to stop). Use for press-and-hold controls."""
    return await camera_controller.start_pan_right(current_user, camera_id)

@router.post("/start-pan-top")
async def start_pan_top(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    """Start tilting up (call /stop to stop). Use for press-and-hold controls."""
    return await camera_controller.start_pan_top(current_user, camera_id)

@router.post("/start-pan-bottom")
async def start_pan_bottom(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    """Start tilting down (call /stop to stop). Use for press-and-hold controls."""
    return await camera_controller.start_pan_bottom(current_user, camera_id)

@router.post("/pan-up-left")
async def pan_up_left(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    return await camera_controller.pan_up_left(current_user, camera_id)

@router.post("/pan-up-right")
async def pan_up_right(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    return await camera_controller.pan_up_right(current_user, camera_id)

@router.post("/pan-down-left")
async def pan_down_left(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    return await camera_controller.pan_down_left(current_user, camera_id)

@router.post("/pan-down-right")
async def pan_down_right(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    return await camera_controller.pan_down_right(current_user, camera_id)

@router.post("/start-pan-up-left")
async def start_pan_up_left(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    """Start diagonal up-left (call /stop to stop)."""
    return await camera_controller.start_pan_up_left(current_user, camera_id)

@router.post("/start-pan-up-right")
async def start_pan_up_right(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    """Start diagonal up-right (call /stop to stop)."""
    return await camera_controller.start_pan_up_right(current_user, camera_id)

@router.post("/start-pan-down-left")
async def start_pan_down_left(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    """Start diagonal down-left (call /stop to stop)."""
    return await camera_controller.start_pan_down_left(current_user, camera_id)

@router.post("/start-pan-down-right")
async def start_pan_down_right(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    """Start diagonal down-right (call /stop to stop)."""
    return await camera_controller.start_pan_down_right(current_user, camera_id)

@router.post("/start-zoom-in")
async def start_zoom_in(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    """Start zooming in (call /stop to stop). Use for press-and-hold controls."""
    return await camera_controller.start_zoom_in(current_user, camera_id)

@router.post("/start-zoom-out")
async def start_zoom_out(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    """Start zooming out (call /stop to stop). Use for press-and-hold controls."""
    return await camera_controller.start_zoom_out(current_user, camera_id)


# ==================== Motor Speed Routes ====================

@router.post("/motor-speed")
async def set_motor_speed(request: MotorSpeedRequest, current_user: dict = auth_dependency):
    return await camera_controller.set_motor_speed(request, current_user)

@router.get("/motor-speed")
async def get_motor_speed(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = view_dependency
):
    return await camera_controller.get_motor_speed(current_user, camera_id)


# ==================== Focus Control Routes ====================

@router.post("/focus/mode")
async def set_focus_mode(request: FocusModeRequest, current_user: dict = auth_dependency):
    return await camera_controller.set_focus_mode(request, current_user)

@router.post("/focus/position")
async def set_focus_position(request: FocusPositionRequest, current_user: dict = auth_dependency):
    return await camera_controller.set_focus_position(request, current_user)

@router.post("/focus/near")
async def focus_near(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    return await camera_controller.focus_near(current_user, camera_id)

@router.post("/focus/far")
async def focus_far(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    return await camera_controller.focus_far(current_user, camera_id)

@router.post("/focus/stop")
async def focus_stop(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    return await camera_controller.focus_stop(current_user, camera_id)


# ==================== Illuminator Control Routes ====================

@router.post("/illuminator")
async def set_illuminator(request: IlluminatorRequest, current_user: dict = auth_dependency):
    return await camera_controller.set_illuminator(request, current_user)

@router.get("/illuminator/status")
async def get_illuminator_status(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = view_dependency
):
    return await camera_controller.get_illuminator_status(current_user, camera_id)

@router.post("/illuminator/brightness")
async def set_illuminator_brightness(request: IlluminatorBrightnessRequest, current_user: dict = auth_dependency):
    return await camera_controller.set_illuminator_brightness(request, current_user)

@router.get("/illuminator/brightness")
async def get_illuminator_brightness(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = view_dependency
):
    return await camera_controller.get_illuminator_brightness(current_user, camera_id)

@router.post("/illuminator/brightness/increase")
async def increase_illuminator_brightness(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    return await camera_controller.increase_illuminator_brightness(current_user, camera_id)

@router.post("/illuminator/brightness/decrease")
async def decrease_illuminator_brightness(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    return await camera_controller.decrease_illuminator_brightness(current_user, camera_id)

@router.post("/illuminator/fov")
async def set_illuminator_fov(request: IlluminatorFOVRequest, current_user: dict = auth_dependency):
    return await camera_controller.set_illuminator_fov(request, current_user)

@router.get("/illuminator/fov")
async def get_illuminator_fov(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = view_dependency
):
    return await camera_controller.get_illuminator_fov(current_user, camera_id)

@router.post("/illuminator/reset")
async def reset_illuminator(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    return await camera_controller.reset_illuminator(current_user, camera_id)


# ==================== Preset Routes ====================

@router.get("/presets")
async def get_presets(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = view_dependency
):
    return await camera_controller.get_presets(current_user, camera_id)

@router.post("/presets")
async def create_preset(request: PresetCreateRequest, current_user: dict = auth_dependency):
    return await camera_controller.create_preset(request, current_user)

@router.put("/presets/{preset_id}")
async def update_preset(preset_id: int, request: PresetUpdateRequest, current_user: dict = auth_dependency):
    return await camera_controller.update_preset(preset_id, request, current_user)

@router.delete("/presets/{preset_id}")
async def delete_preset(
    preset_id: int, 
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    return await camera_controller.delete_preset(preset_id, current_user, camera_id)

@router.post("/presets/{preset_id}/go")
async def go_to_preset(
    preset_id: int, 
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    return await camera_controller.go_to_preset(preset_id, current_user, camera_id)

@router.post("/presets/{preset_id}/update-position")
async def update_preset_position(
    preset_id: int, 
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    """Update a preset's PTZ position to the current camera position"""
    return await camera_controller.update_preset_position(preset_id, current_user, camera_id)


# ==================== Auto-Pan Routes ====================

@router.post("/autopan/start")
async def start_auto_pan(request: AutoPanRequest, current_user: dict = auth_dependency):
    return await camera_controller.start_auto_pan(request, current_user)

@router.post("/autopan/stop")
async def stop_auto_pan(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    return await camera_controller.stop_auto_pan(current_user, camera_id)

@router.get("/autopan/status")
async def get_auto_pan_status(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = view_dependency
):
    return await camera_controller.get_auto_pan_status(current_user, camera_id)


# ==================== Tracking Routes ====================

@router.post("/tracking")
async def set_tracking(request: TrackingRequest, current_user: dict = auth_dependency):
    """Enable or disable auto-tracking"""
    return await camera_controller.set_tracking(request, current_user)

@router.get("/tracking/status")
async def get_tracking_status(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = view_dependency
):
    """Get tracking status"""
    return await camera_controller.get_tracking_status(current_user, camera_id)


# ==================== Image Quality Routes ====================

@router.post("/brightness")
async def set_brightness(request: BrightnessRequest, current_user: dict = auth_dependency):
    """Set image brightness (0-100)"""
    return await camera_controller.set_brightness(request, current_user)

@router.get("/brightness")
async def get_brightness(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = view_dependency
):
    """Get current brightness"""
    return await camera_controller.get_brightness(current_user, camera_id)

@router.post("/contrast")
async def set_contrast(request: ContrastRequest, current_user: dict = auth_dependency):
    """Set image contrast (0-100)"""
    return await camera_controller.set_contrast(request, current_user)

@router.get("/contrast")
async def get_contrast(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = view_dependency
):
    """Get current contrast"""
    return await camera_controller.get_contrast(current_user, camera_id)

@router.post("/polarity")
async def set_polarity(request: PolarityRequest, current_user: dict = auth_dependency):
    """Set thermal camera polarity (white_hot or black_hot)"""
    return await camera_controller.set_polarity(request, current_user)

@router.get("/polarity")
async def get_polarity(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = view_dependency
):
    """Get current polarity"""
    return await camera_controller.get_polarity(current_user, camera_id)


# ==================== Device Info Route ====================

@router.get("/info")
async def get_device_info(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = view_dependency
):
    return await camera_controller.get_device_info(current_user, camera_id)


# ==================== Stream URI Routes ====================

@router.get("/stream-uri")
async def get_stream_uri(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = view_dependency
):
    return await camera_controller.get_stream_uri(None, current_user, camera_id)

@router.post("/stream-uri")
async def get_stream_uri_with_protocol(request: StreamUriRequest, current_user: dict = view_dependency):
    return await camera_controller.get_stream_uri(request, current_user)

@router.get("/snapshot-uri")
async def get_snapshot_uri(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = view_dependency
):
    return await camera_controller.get_snapshot_uri(current_user, camera_id)

@router.get("/streams")
async def get_all_stream_uris(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = view_dependency
):
    """Get all available stream profiles with their URIs and resolutions"""
    return await camera_controller.get_all_stream_uris(current_user, camera_id)


# ==================== USR Connection Status ====================

@router.get("/usr/status")
async def get_usr_connection_status(current_user: dict = view_dependency):
    """Get USR device connection status (shared by LRF and Illuminator)"""
    from services.usr_connection import get_usr_connection
    conn = get_usr_connection()
    return conn.get_status()


@router.post("/illuminator/test/{command}")
async def test_illuminator_direct(command: str, current_user: dict = auth_dependency):
    """
    Direct test endpoint for illuminator commands (bypasses camera service).
    Commands: on, off, brightness_up, brightness_down
    """
    from services.illuminator_service import IlluminatorService
    from services.usr_connection import get_usr_connection
    
    # Get connection status first
    conn = get_usr_connection()
    status = conn.get_status()
    
    # Create a direct illuminator service
    illuminator = IlluminatorService()
    
    result = {
        "command": command,
        "usr_status": status,
        "illuminator_connected": conn.is_device_connected("illuminator")
    }
    
    if command == "on":
        cmd_result = illuminator.turn_on()
        result["command_result"] = cmd_result
    elif command == "off":
        cmd_result = illuminator.turn_off()
        result["command_result"] = cmd_result
    elif command == "brightness_up":
        cmd_result = illuminator.increase_brightness()
        result["command_result"] = cmd_result
    elif command == "brightness_down":
        cmd_result = illuminator.decrease_brightness()
        result["command_result"] = cmd_result
    elif command == "status":
        cmd_result = illuminator.get_cached_state()
        result["command_result"] = cmd_result
    else:
        result["error"] = f"Unknown command: {command}. Use: on, off, brightness_up, brightness_down, status"
    
    return result


# ==================== LRF (Laser Range Finder) Routes ====================

@router.post("/lrf/register")
async def register_lrf(request: LRFRegistrationRequest, current_user: dict = admin_dependency):
    """Register an LRF device for control"""
    return lrf_controller.register_lrf(request)

@router.post("/lrf/single-range")
async def lrf_single_range(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    """Perform single range measurement"""
    return lrf_controller.single_range(camera_id)

# @router.post("/lrf/start-continuous")
# async def lrf_start_continuous(
#     camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
#     current_user: dict = auth_dependency
# ):
#     """Start continuous ranging mode"""
#     return lrf_controller.start_continuous(camera_id)

# @router.post("/lrf/stop-continuous")
# async def lrf_stop_continuous(
#     camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
#     current_user: dict = auth_dependency
# ):
#     """Stop continuous ranging mode"""
#     return lrf_controller.stop_continuous(camera_id)
@router.post("/lrf/start-continuous")
@router.post("/lrf/continuous/start")
async def lrf_start_continuous(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    """Start continuous ranging mode"""
    return lrf_controller.start_continuous(camera_id)

@router.post("/lrf/stop-continuous")
@router.post("/lrf/continuous/stop")
async def lrf_stop_continuous(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = auth_dependency
):
    """Stop continuous ranging mode"""
    return lrf_controller.stop_continuous(camera_id)
@router.get("/lrf/get-distance")
async def lrf_get_distance(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = view_dependency
):
    """Get current distance reading (during continuous mode)"""
    return lrf_controller.get_distance(camera_id)

@router.get("/lrf/status")
async def lrf_get_status(
    camera_id: Optional[str] = Query(None, description="Camera ID (uses default if not specified)"),
    current_user: dict = view_dependency
):
    """Get LRF status"""
    return lrf_controller.get_status(camera_id)
