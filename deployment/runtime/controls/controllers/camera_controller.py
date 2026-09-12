# controllers/camera_controller.py
from fastapi import Response
from fastapi.responses import JSONResponse
import logging
from typing import Optional, List
from pydantic import BaseModel
from services.camera_service import camera_manager, CameraManager

logger = logging.getLogger(__name__)

# Request models
class MotorSpeedRequest(BaseModel):
    speed: int  # 0-100
    camera_id: Optional[str] = None

class FocusModeRequest(BaseModel):
    auto: bool
    camera_id: Optional[str] = None

class FocusPositionRequest(BaseModel):
    position: float  # 0-100
    camera_id: Optional[str] = None

class IlluminatorRequest(BaseModel):
    enabled: bool
    camera_id: Optional[str] = None

class IlluminatorBrightnessRequest(BaseModel):
    brightness: int  # 0-100
    camera_id: Optional[str] = None

class IlluminatorFOVRequest(BaseModel):
    fov: int  # 5-90 degrees
    camera_id: Optional[str] = None

class PresetCreateRequest(BaseModel):
    name: str
    zoom: Optional[int] = None  # If None, uses actual camera zoom level
    fov: int = 30
    camera_id: Optional[str] = None

class PresetUpdateRequest(BaseModel):
    name: Optional[str] = None
    zoom: Optional[int] = None
    fov: Optional[int] = None
    camera_id: Optional[str] = None

class AutoPanRequest(BaseModel):
    preset_ids: List[int]
    interval: int = 10  # seconds
    camera_id: Optional[str] = None

class StreamUriRequest(BaseModel):
    protocol: str = "RTSP"  # RTSP, UDP, or HTTP
    camera_id: Optional[str] = None

class CameraRegistrationRequest(BaseModel):
    camera_ip: str
    camera_port: int = 80
    username: str = "admin"
    password: str
    onvif_port: int = 80
    camera_id: Optional[str] = None
    # Illuminator configuration (choose either serial or network)
    illuminator_port: Optional[str] = None  # Serial port (e.g., 'COM3' or '/dev/ttyUSB0')
    illuminator_ip: Optional[str] = None  # Network IP (e.g., '192.168.0.50')
    illuminator_tcp_port: Optional[int] = 8234  # Network TCP port (SHIBLI uses 8234)
    illuminator_username: Optional[str] = ""
    illuminator_password: Optional[str] = ""

class CameraIdRequest(BaseModel):
    camera_id: str

class TrackingRequest(BaseModel):
    enabled: bool
    camera_id: Optional[str] = None

class BrightnessRequest(BaseModel):
    brightness: float  # 0-100
    camera_id: Optional[str] = None

class ContrastRequest(BaseModel):
    contrast: float  # 0-100
    camera_id: Optional[str] = None

class PolarityRequest(BaseModel):
    polarity: str  # 'white_hot' or 'black_hot'
    camera_id: Optional[str] = None


# Controller for camera controls
class CameraController:
    def __init__(self):
        # Use the global camera manager - no immediate connection
        self.camera_manager = camera_manager
        logger.info("CameraController initialized (no camera connection required)")
    
    def _get_camera(self, camera_id: str = None):
        """Get camera service by ID, using default if not specified"""
        return self.camera_manager.get_camera(camera_id)
    
    def _get_camera_or_error(self, camera_id: str = None):
        """Get camera service or return error response if not found"""
        camera = self.camera_manager.get_camera(camera_id)
        if camera is None:
            return None, JSONResponse(
                {
                    "success": False, 
                    "error": "No camera registered. Please add a camera with RGB settings via Settings → Camera Configuration, or register one via POST /api/camera/cameras/register",
                    "camera_id": camera_id
                }, 
                status_code=404
            )
        return camera, None
    
    def _log_user_action(self, current_user: dict, action: str, camera_id: str = None):
        """Log user action"""
        cam_info = f" on camera {camera_id}" if camera_id else ""
        logger.info(f"User {current_user.get('username', 'unknown')} with role {current_user.get('roleName', 'unknown')} requested {action}{cam_info}")
    
    # ==================== Camera Management ====================
    
    async def register_camera(self, request: CameraRegistrationRequest, current_user: dict):
        """Register a new camera for PTZ control"""
        self._log_user_action(current_user, "register-camera")
        
        # Get illuminator port from config if not provided in request
        from config import ILLUMINATOR_SERIAL_PORT
        illuminator_port = request.illuminator_port or ILLUMINATOR_SERIAL_PORT
        
        camera = self.camera_manager.register_camera(
            camera_ip=request.camera_ip,
            camera_port=request.camera_port,
            username=request.username,
            password=request.password,
            onvif_port=request.onvif_port,
            camera_id=request.camera_id,
            illuminator_port=illuminator_port,
            illuminator_ip=request.illuminator_ip,
            illuminator_tcp_port=request.illuminator_tcp_port,
            illuminator_username=request.illuminator_username,
            illuminator_password=request.illuminator_password
        )
        
        # Determine illuminator connection info
        illum_info = "none"
        if camera.illuminator:
            if camera.illuminator.connection_type == 'network':
                illum_info = f"network ({request.illuminator_ip}:{request.illuminator_tcp_port})"
            elif camera.illuminator.connection_type == 'serial':
                illum_info = f"serial ({illuminator_port})"
        
        return JSONResponse({
            "success": True,
            "camera_id": camera.camera_id,
            "message": f"Camera registered for PTZ control: {camera.camera_id}",
            "has_illuminator": camera.illuminator is not None,
            "illuminator_connection": illum_info
        })
    
    async def unregister_camera(self, camera_id: str, current_user: dict):
        """Unregister a camera"""
        self._log_user_action(current_user, f"unregister-camera {camera_id}")
        success = self.camera_manager.unregister_camera(camera_id)
        if success:
            return JSONResponse({"success": True, "message": f"Camera unregistered: {camera_id}"})
        return JSONResponse({"success": False, "error": f"Camera not found: {camera_id}"}, status_code=404)
    
    async def list_cameras(self, current_user: dict):
        """List all registered cameras"""
        self._log_user_action(current_user, "list-cameras")
        cameras = self.camera_manager.list_cameras()
        return JSONResponse({"success": True, "cameras": cameras})
    
    async def connect_camera(self, camera_id: str, current_user: dict):
        """Explicitly connect to a camera"""
        self._log_user_action(current_user, f"connect-camera {camera_id}")
        result = self.camera_manager.connect_camera(camera_id)
        return JSONResponse(result)
    
    async def disconnect_camera(self, camera_id: str, current_user: dict):
        """Disconnect from a camera"""
        self._log_user_action(current_user, f"disconnect-camera {camera_id}")
        result = self.camera_manager.disconnect_camera(camera_id)
        return JSONResponse(result)
    
    async def get_camera_status(self, camera_id: str, current_user: dict):
        """Get connection status for a camera"""
        self._log_user_action(current_user, f"get-camera-status {camera_id}")
        camera = self._get_camera(camera_id)
        if camera:
            return JSONResponse(camera.get_connection_status())
        return JSONResponse({"success": False, "error": f"Camera not found: {camera_id}"}, status_code=404)
    
    async def set_default_camera(self, request: CameraIdRequest, current_user: dict):
        """Set the default camera"""
        self._log_user_action(current_user, f"set-default-camera {request.camera_id}")
        success = self.camera_manager.set_default_camera(request.camera_id)
        if success:
            return JSONResponse({"success": True, "default_camera": request.camera_id})
        return JSONResponse({"success": False, "error": f"Camera not found: {request.camera_id}"}, status_code=404)
    
    # ==================== PTZ Controls ====================
    
    async def zoom_in(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "zoom-in", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.zoom_in()
        return JSONResponse(result)
    
    async def zoom_out(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "zoom-out", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.zoom_out()
        return JSONResponse(result)
    
    async def pan_left(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "pan-left", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.pan_left()
        return JSONResponse(result)
    
    async def pan_right(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "pan-right", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.pan_right()
        return JSONResponse(result)
    
    async def pan_top(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "pan-top", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.pan_top()
        return JSONResponse(result)
    
    async def pan_bottom(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "pan-bottom", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.pan_bottom()
        return JSONResponse(result)
    
    async def stop(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "stop", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.stop_movement()
        return JSONResponse(result)
    
    async def go_home(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "go-home", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.go_to_home()
        return JSONResponse(result)
    
    async def get_status(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "get-status", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.get_ptz_status()
        return JSONResponse(result)
    
    async def get_zoom_level(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "get-zoom-level", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.get_zoom_level()
        return JSONResponse(result)
    
    # ==================== Start/Stop PTZ Controls (for press-and-hold) ====================
    
    async def start_pan_left(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "start-pan-left", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.start_pan_left()
        return JSONResponse(result)
    
    async def start_pan_right(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "start-pan-right", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.start_pan_right()
        return JSONResponse(result)
    
    async def start_pan_top(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "start-pan-top", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.start_pan_top()
        return JSONResponse(result)
    
    async def start_pan_bottom(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "start-pan-bottom", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.start_pan_bottom()
        return JSONResponse(result)

    async def pan_up_left(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "pan-up-left", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        return JSONResponse(camera.pan_up_left())

    async def pan_up_right(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "pan-up-right", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        return JSONResponse(camera.pan_up_right())

    async def pan_down_left(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "pan-down-left", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        return JSONResponse(camera.pan_down_left())

    async def pan_down_right(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "pan-down-right", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        return JSONResponse(camera.pan_down_right())

    async def start_pan_up_left(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "start-pan-up-left", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        return JSONResponse(camera.start_pan_up_left())

    async def start_pan_up_right(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "start-pan-up-right", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        return JSONResponse(camera.start_pan_up_right())

    async def start_pan_down_left(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "start-pan-down-left", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        return JSONResponse(camera.start_pan_down_left())

    async def start_pan_down_right(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "start-pan-down-right", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        return JSONResponse(camera.start_pan_down_right())
    
    async def start_zoom_in(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "start-zoom-in", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.start_zoom_in()
        return JSONResponse(result)
    
    async def start_zoom_out(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "start-zoom-out", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.start_zoom_out()
        return JSONResponse(result)
    
    # ==================== Motor Speed ====================
    
    async def set_motor_speed(self, request: MotorSpeedRequest, current_user: dict):
        self._log_user_action(current_user, f"set-motor-speed to {request.speed}", request.camera_id)
        camera, error = self._get_camera_or_error(request.camera_id)
        if error:
            return error
        result = camera.set_motor_speed(request.speed)
        return JSONResponse(result)
    
    async def get_motor_speed(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "get-motor-speed", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.get_motor_speed()
        return JSONResponse(result)
    
    # ==================== Focus Controls ====================
    
    async def set_focus_mode(self, request: FocusModeRequest, current_user: dict):
        self._log_user_action(current_user, f"set-focus-mode to {'auto' if request.auto else 'manual'}", request.camera_id)
        camera, error = self._get_camera_or_error(request.camera_id)
        if error:
            return error
        result = camera.set_focus_mode(request.auto)
        return JSONResponse(result)
    
    async def set_focus_position(self, request: FocusPositionRequest, current_user: dict):
        self._log_user_action(current_user, f"set-focus-position to {request.position}", request.camera_id)
        camera, error = self._get_camera_or_error(request.camera_id)
        if error:
            return error
        result = camera.set_focus_position(request.position)
        return JSONResponse(result)
    
    async def focus_near(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "focus-near", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.focus_near()
        return JSONResponse(result)
    
    async def focus_far(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "focus-far", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.focus_far()
        return JSONResponse(result)
    
    async def focus_stop(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "focus-stop", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.focus_stop()
        return JSONResponse(result)
    
    # ==================== Illuminator Controls ====================
    
    async def set_illuminator(self, request: IlluminatorRequest, current_user: dict):
        self._log_user_action(current_user, f"set-illuminator to {'on' if request.enabled else 'off'}", request.camera_id)
        camera, error = self._get_camera_or_error(request.camera_id)
        if error:
            return error
        result = camera.set_illuminator(request.enabled)
        return JSONResponse(result)
    
    async def get_illuminator_status(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "get-illuminator-status", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.get_illuminator_status()
        return JSONResponse(result)
    
    async def set_illuminator_brightness(self, request: IlluminatorBrightnessRequest, current_user: dict):
        self._log_user_action(current_user, f"set-illuminator-brightness to {request.brightness}", request.camera_id)
        camera, error = self._get_camera_or_error(request.camera_id)
        if error:
            return error
        result = camera.set_illuminator_brightness(request.brightness)
        return JSONResponse(result)
    
    async def get_illuminator_brightness(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "get-illuminator-brightness", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.get_illuminator_brightness()
        return JSONResponse(result)
    
    async def increase_illuminator_brightness(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "increase-illuminator-brightness", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.increase_illuminator_brightness()
        return JSONResponse(result)
    
    async def decrease_illuminator_brightness(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "decrease-illuminator-brightness", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.decrease_illuminator_brightness()
        return JSONResponse(result)
    
    async def set_illuminator_fov(self, request: IlluminatorFOVRequest, current_user: dict):
        self._log_user_action(current_user, f"set-illuminator-fov to {request.fov}", request.camera_id)
        camera, error = self._get_camera_or_error(request.camera_id)
        if error:
            return error
        result = camera.set_illuminator_fov(request.fov)
        return JSONResponse(result)
    
    async def get_illuminator_fov(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "get-illuminator-fov", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.get_illuminator_fov()
        return JSONResponse(result)
    
    async def reset_illuminator(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "reset-illuminator", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.reset_illuminator()
        return JSONResponse(result)
    
    # ==================== Presets ====================
    
    async def get_presets(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "get-presets", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        presets = camera.get_presets()
        return JSONResponse({"success": True, "presets": presets})
    
    async def create_preset(self, request: PresetCreateRequest, current_user: dict):
        self._log_user_action(current_user, f"create-preset '{request.name}'", request.camera_id)
        camera, error = self._get_camera_or_error(request.camera_id)
        if error:
            return error
        result = camera.create_preset(request.name, request.zoom, request.fov)
        return JSONResponse(result)
    
    async def update_preset(self, preset_id: int, request: PresetUpdateRequest, current_user: dict):
        self._log_user_action(current_user, f"update-preset {preset_id}", request.camera_id)
        camera, error = self._get_camera_or_error(request.camera_id)
        if error:
            return error
        result = camera.update_preset(preset_id, request.name, request.zoom, request.fov)
        return JSONResponse(result)
    
    async def delete_preset(self, preset_id: int, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, f"delete-preset {preset_id}", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.delete_preset(preset_id)
        return JSONResponse(result)
    
    async def go_to_preset(self, preset_id: int, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, f"go-to-preset {preset_id}", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.go_to_preset(preset_id)
        return JSONResponse(result)
    
    async def update_preset_position(self, preset_id: int, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, f"update-preset-position {preset_id}", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.update_preset_position(preset_id)
        return JSONResponse(result)
    
    # ==================== Auto-Pan ====================
    
    async def start_auto_pan(self, request: AutoPanRequest, current_user: dict):
        self._log_user_action(current_user, f"start-auto-pan with {len(request.preset_ids)} presets", request.camera_id)
        camera, error = self._get_camera_or_error(request.camera_id)
        if error:
            return error
        result = camera.start_auto_pan(request.preset_ids, request.interval)
        return JSONResponse(result)
    
    async def stop_auto_pan(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "stop-auto-pan", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.stop_auto_pan()
        return JSONResponse(result)
    
    async def get_auto_pan_status(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "get-auto-pan-status", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.get_auto_pan_status()
        return JSONResponse(result)
    
    # ==================== Tracking ====================
    
    async def set_tracking(self, request: TrackingRequest, current_user: dict):
        self._log_user_action(current_user, f"set-tracking to {'enabled' if request.enabled else 'disabled'}", request.camera_id)
        camera, error = self._get_camera_or_error(request.camera_id)
        if error:
            return error
        result = camera.set_tracking(request.enabled)
        return JSONResponse(result)
    
    async def get_tracking_status(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "get-tracking-status", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.get_tracking_status()
        return JSONResponse(result)
    
    # ==================== Image Quality Controls ====================
    
    async def set_brightness(self, request: BrightnessRequest, current_user: dict):
        self._log_user_action(current_user, f"set-brightness to {request.brightness}", request.camera_id)
        camera, error = self._get_camera_or_error(request.camera_id)
        if error:
            return error
        result = camera.set_brightness(request.brightness)
        return JSONResponse(result)
    
    async def get_brightness(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "get-brightness", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.get_brightness()
        return JSONResponse(result)
    
    async def set_contrast(self, request: ContrastRequest, current_user: dict):
        self._log_user_action(current_user, f"set-contrast to {request.contrast}", request.camera_id)
        camera, error = self._get_camera_or_error(request.camera_id)
        if error:
            return error
        result = camera.set_contrast(request.contrast)
        return JSONResponse(result)
    
    async def get_contrast(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "get-contrast", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.get_contrast()
        return JSONResponse(result)
    
    async def set_polarity(self, request: PolarityRequest, current_user: dict):
        self._log_user_action(current_user, f"set-polarity to {request.polarity}", request.camera_id)
        camera, error = self._get_camera_or_error(request.camera_id)
        if error:
            return error
        result = camera.set_polarity(request.polarity)
        return JSONResponse(result)
    
    async def get_polarity(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "get-polarity", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.get_polarity()
        return JSONResponse(result)
    
    # ==================== Device Info ====================
    
    async def get_device_info(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "get-device-info", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.get_device_info()
        return JSONResponse(result)
    
    # ==================== Stream URI ====================
    
    async def get_stream_uri(self, request: Optional['StreamUriRequest'], current_user: dict, camera_id: str = None):
        protocol = request.protocol if request else "RTSP"
        cam_id = request.camera_id if request else camera_id
        self._log_user_action(current_user, f"get-stream-uri (protocol: {protocol})", cam_id)
        camera, error = self._get_camera_or_error(cam_id)
        if error:
            return error
        result = camera.get_stream_uri(protocol=protocol)
        return JSONResponse(result)
    
    async def get_snapshot_uri(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "get-snapshot-uri", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.get_snapshot_uri()
        return JSONResponse(result)
    
    async def get_all_stream_uris(self, current_user: dict, camera_id: str = None):
        self._log_user_action(current_user, "get-all-stream-uris", camera_id)
        camera, error = self._get_camera_or_error(camera_id)
        if error:
            return error
        result = camera.get_all_stream_uris()
        return JSONResponse(result)


# Global controller instance - safe to create at import time now
camera_controller = CameraController()
