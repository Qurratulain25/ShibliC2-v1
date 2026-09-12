# services/camera_service.py
import logging
import time
import json
import os
from typing import Optional, Dict, List, Any
from onvif import ONVIFCamera
from config import DEFAULT_CAMERA_PORT, DEFAULT_ONVIF_PORT
from services.illuminator_service import IlluminatorService
from services.usr_connection import get_usr_connection

logger = logging.getLogger(__name__)

# Presets storage file
PRESETS_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'presets.json')


class CameraService:
    """
    Service for controlling a single ONVIF camera.
    Uses lazy connection - only connects when first needed.
    
    Camera configuration should be provided when creating the service.
    The camera_ip, username, and password are required for connection.
    """
    
    def __init__(self, camera_ip: str = None, camera_port: int = None, 
                 username: str = None, password: str = None, camera_id: str = None,
                 onvif_port: int = None, illuminator_port: str = None,
                 illuminator_ip: str = None, illuminator_tcp_port: int = None,
                 illuminator_username: str = None, illuminator_password: str = None):
        # Camera connection details - all should be provided explicitly
        self.camera_ip = camera_ip
        self.camera_port = camera_port or DEFAULT_CAMERA_PORT
        self.onvif_port = onvif_port or DEFAULT_ONVIF_PORT
        self.username = username
        self.password = password
        self.camera_id = camera_id or (f"{self.camera_ip}:{self.camera_port}" if self.camera_ip else "uninitialized")
        
        # Connection state - lazy initialization
        self.camera: Optional[ONVIFCamera] = None
        self.ptz_service = None
        self.imaging_service = None
        self.media_service = None
        self.profile_token = None
        self.video_source_token = None
        self.ptz_configuration_token = None
        self._connected = False
        self._connection_error: Optional[str] = None
        
        # Movement speed (0.0 to 1.0)
        self.pan_tilt_speed = 0.5
        self.zoom_speed = 0.5
        
        # Focus position tracking (0.0 to 1.0)
        self.focus_position = 0.5  # Start at middle
        
        # Illuminator service (serial or network communication)
        self.illuminator: Optional[IlluminatorService] = None
        if illuminator_ip:
            # Network connection (preferred if both IP and port are provided)
            try:
                self.illuminator = IlluminatorService(
                    ip=illuminator_ip,
                    tcp_port=illuminator_tcp_port or 8000,
                    username=illuminator_username,
                    password=illuminator_password
                )
                logger.info(f"Illuminator service initialized via network at {illuminator_ip}:{illuminator_tcp_port or 8000}")
            except Exception as e:
                logger.warning(f"Failed to initialize illuminator service via network: {e}")
        elif illuminator_port:
            # Serial connection (fallback)
            try:
                self.illuminator = IlluminatorService(port=illuminator_port)
                logger.info(f"Illuminator service initialized via serial on port {illuminator_port}")
            except Exception as e:
                logger.warning(f"Failed to initialize illuminator service via serial: {e}")
        
        # Default movement duration in seconds
        self.movement_duration = 0.3
        
        # Presets storage (per camera)
        self.presets: List[Dict] = []
        self._load_presets()
        
        # Auto-pan state
        self.auto_pan_enabled = False
        self.auto_pan_interval = 10
        self.auto_pan_presets: List[int] = []
        
        # Tracking state
        self.tracking_enabled = False
        
        # Note: We do NOT auto-connect here. Connection is lazy.
        logger.info(f"CameraService initialized for {self.camera_id} (not connected yet)")
    
    def _connect(self) -> bool:
        """
        Initialize connection to ONVIF camera.
        Returns True if successful, False otherwise.
        Does not raise exceptions - stores error for later retrieval.
        """
        if self._connected and self.camera is not None:
            return True
            
        try:
            logger.info(f"Connecting to ONVIF camera at {self.camera_ip}:{self.camera_port}")
            
            self.camera = ONVIFCamera(
                self.camera_ip,
                self.camera_port,
                self.username,
                self.password
            )
            
            # Get media service and profile
            self.media_service = self.camera.create_media_service()
            profiles = self.media_service.GetProfiles()
            
            if profiles:
                self.profile_token = profiles[0].token
                logger.info(f"Using media profile: {self.profile_token}")
                
                # Get video source token for imaging service
                video_sources = self.media_service.GetVideoSources()
                if video_sources:
                    self.video_source_token = video_sources[0].token
                    logger.info(f"Using video source: {self.video_source_token}")
            
            # Get PTZ service
            try:
                self.ptz_service = self.camera.create_ptz_service()
                
                # Get PTZ configuration
                ptz_configs = self.ptz_service.GetConfigurations()
                if ptz_configs:
                    self.ptz_configuration_token = ptz_configs[0].token
                    logger.info(f"PTZ service initialized with config: {self.ptz_configuration_token}")
            except Exception as e:
                logger.warning(f"PTZ service not available: {e}")
                self.ptz_service = None
            
            # Get imaging service
            try:
                self.imaging_service = self.camera.create_imaging_service()
                logger.info("Imaging service initialized")
            except Exception as e:
                logger.warning(f"Imaging service not available: {e}")
                self.imaging_service = None
            
            self._connected = True
            self._connection_error = None
            logger.info(f"ONVIF camera connection established successfully for {self.camera_id}")
            return True
            
        except Exception as e:
            self._connected = False
            self._connection_error = str(e)
            logger.error(f"Failed to connect to ONVIF camera {self.camera_id}: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the camera"""
        self.camera = None
        self.ptz_service = None
        self.imaging_service = None
        self.media_service = None
        self.profile_token = None
        self.video_source_token = None
        self.ptz_configuration_token = None
        self._connected = False
        logger.info(f"Disconnected from camera {self.camera_id}")
    
    def is_connected(self) -> bool:
        """Check if camera is connected"""
        return self._connected and self.camera is not None
    
    def get_connection_status(self) -> Dict:
        """Get current connection status"""
        return {
            "connected": self._connected,
            "camera_id": self.camera_id,
            "camera_ip": self.camera_ip,
            "camera_port": self.camera_port,
            "error": self._connection_error
        }
    
    def _ensure_connected(self) -> bool:
        """
        Ensure camera is connected, attempt to connect if not.
        Returns True if connected, False otherwise.
        """
        if self._connected and self.camera is not None:
            return True
        return self._connect()
    
    def _check_connection(self) -> Dict:
        """Check connection and return error dict if not connected"""
        if not self._ensure_connected():
            return {
                "success": False, 
                "error": f"Camera not connected: {self._connection_error or 'Unknown error'}",
                "camera_id": self.camera_id
            }
        return None
    
    def set_motor_speed(self, speed: float):
        """Set PTZ motor speed (0-100 converted to 0.0-1.0)"""
        self.pan_tilt_speed = max(0.01, min(1.0, speed / 100.0))
        self.zoom_speed = max(0.01, min(1.0, speed / 100.0))
        logger.info(f"Motor speed set to {speed}% (internal: {self.pan_tilt_speed})")
        return {"success": True, "speed": speed}
    
    def get_motor_speed(self) -> Dict:
        """Get current motor speed"""
        return {"speed": int(self.pan_tilt_speed * 100)}
    
    # ==================== PTZ Controls ====================
    
    def _start_continuous_move(self, pan: float = 0, tilt: float = 0, zoom: float = 0):
        """
        Start continuous move command (non-blocking).
        Camera will keep moving until stop_movement() is called.
        Use this for press-and-hold controls.
        """
        conn_error = self._check_connection()
        if conn_error:
            return conn_error
        
        if self.ptz_service is None:
            logger.error("PTZ service not available")
            return {"success": False, "error": "PTZ service not available"}
        
        try:
            # Create velocity request
            request = self.ptz_service.create_type('ContinuousMove')
            request.ProfileToken = self.profile_token
            
            # Set velocity (applying motor speed)
            pan_velocity = pan * self.pan_tilt_speed
            tilt_velocity = tilt * self.pan_tilt_speed
            zoom_velocity = zoom * self.zoom_speed
            
            request.Velocity = {
                'PanTilt': {'x': pan_velocity, 'y': tilt_velocity},
                'Zoom': {'x': zoom_velocity}
            }
            
            logger.debug(f"Starting continuous move - Pan: {pan_velocity:.2f}, Tilt: {tilt_velocity:.2f}, Zoom: {zoom_velocity:.2f} (Speed: {int(self.pan_tilt_speed * 100)}%)")
            
            # Execute movement (non-blocking - camera keeps moving until Stop is called)
            self.ptz_service.ContinuousMove(request)
            
            return {"success": True}
            
        except Exception as e:
            logger.error(f"Start continuous move failed: {e}")
            self._connected = False
            return {"success": False, "error": str(e)}
    
    def _continuous_move(self, pan: float = 0, tilt: float = 0, zoom: float = 0, duration: float = None):
        """
        Execute continuous move command for a fixed duration (blocking).
        Use this for discrete step movements (e.g., single button clicks).
        For press-and-hold controls, use _start_continuous_move() + stop_movement() instead.
        """
        conn_error = self._check_connection()
        if conn_error:
            return conn_error
        
        if self.ptz_service is None:
            logger.error("PTZ service not available")
            return {"success": False, "error": "PTZ service not available"}
        
        try:
            # Create velocity request
            request = self.ptz_service.create_type('ContinuousMove')
            request.ProfileToken = self.profile_token
            
            # Set velocity (applying motor speed)
            pan_velocity = pan * self.pan_tilt_speed
            tilt_velocity = tilt * self.pan_tilt_speed
            zoom_velocity = zoom * self.zoom_speed
            
            request.Velocity = {
                'PanTilt': {'x': pan_velocity, 'y': tilt_velocity},
                'Zoom': {'x': zoom_velocity}
            }
            
            logger.debug(f"Moving with velocity - Pan: {pan_velocity:.2f}, Tilt: {tilt_velocity:.2f}, Zoom: {zoom_velocity:.2f} (Speed: {int(self.pan_tilt_speed * 100)}%)")
            
            # Execute movement
            self.ptz_service.ContinuousMove(request)
            
            # Wait for duration then stop
            move_duration = duration if duration else self.movement_duration
            time.sleep(move_duration)
            
            # Stop movement
            self.stop_movement()
            
            return {"success": True}
            
        except Exception as e:
            logger.error(f"Continuous move failed: {e}")
            # Mark as disconnected on communication error
            self._connected = False
            return {"success": False, "error": str(e)}
    
    def stop_movement(self):
        """Stop all PTZ movement"""
        conn_error = self._check_connection()
        if conn_error:
            return conn_error
        
        if self.ptz_service is None:
            return {"success": False, "error": "PTZ service not available"}
        
        try:
            request = self.ptz_service.create_type('Stop')
            request.ProfileToken = self.profile_token
            request.PanTilt = True
            request.Zoom = True
            self.ptz_service.Stop(request)
            return {"success": True}
        except Exception as e:
            logger.error(f"Stop movement failed: {e}")
            return {"success": False, "error": str(e)}
    
    def pan_left(self):
        """Pan camera left"""
        logger.info("Camera pan-left command executed")
        return self._continuous_move(pan=-1, tilt=0)
    
    def pan_right(self):
        """Pan camera right"""
        logger.info("Camera pan-right command executed")
        return self._continuous_move(pan=1, tilt=0)
    
    def pan_top(self):
        """Tilt camera up"""
        logger.info("Camera pan-top (tilt up) command executed")
        return self._continuous_move(pan=0, tilt=1)
    
    def pan_bottom(self):
        """Tilt camera down"""
        logger.info("Camera pan-bottom (tilt down) command executed")
        return self._continuous_move(pan=0, tilt=-1)
    
    def zoom_in(self):
        """Zoom camera in"""
        logger.info("Camera zoom-in command executed")
        result = self._continuous_move(zoom=1)
        # Return updated zoom level
        if result.get("success"):
            zoom_status = self.get_zoom_level()
            result.update(zoom_status)
        return result
    
    def zoom_out(self):
        """Zoom camera out"""
        logger.info("Camera zoom-out command executed")
        result = self._continuous_move(zoom=-1)
        # Return updated zoom level
        if result.get("success"):
            zoom_status = self.get_zoom_level()
            result.update(zoom_status)
        return result
    
    # ==================== Start/Stop PTZ Controls (for press-and-hold) ====================
    
    def start_pan_left(self):
        """Start panning left (call stop_movement to stop)"""
        logger.info("Camera start-pan-left command executed")
        return self._start_continuous_move(pan=-1, tilt=0)
    
    def start_pan_right(self):
        """Start panning right (call stop_movement to stop)"""
        logger.info("Camera start-pan-right command executed")
        return self._start_continuous_move(pan=1, tilt=0)
    
    def start_pan_top(self):
        """Start tilting up (call stop_movement to stop)"""
        logger.info("Camera start-pan-top command executed")
        return self._start_continuous_move(pan=0, tilt=1)
    
    def start_pan_bottom(self):
        """Start tilting down (call stop_movement to stop)"""
        logger.info("Camera start-pan-bottom command executed")
        return self._start_continuous_move(pan=0, tilt=-1)

    def pan_up_left(self):
        """Pan camera up-left (diagonal)"""
        logger.info("Camera pan-up-left command executed")
        return self._continuous_move(pan=-1, tilt=1)

    def pan_up_right(self):
        """Pan camera up-right (diagonal)"""
        logger.info("Camera pan-up-right command executed")
        return self._continuous_move(pan=1, tilt=1)

    def pan_down_left(self):
        """Pan camera down-left (diagonal)"""
        logger.info("Camera pan-down-left command executed")
        return self._continuous_move(pan=-1, tilt=-1)

    def pan_down_right(self):
        """Pan camera down-right (diagonal)"""
        logger.info("Camera pan-down-right command executed")
        return self._continuous_move(pan=1, tilt=-1)

    def start_pan_up_left(self):
        """Start diagonal move up-left"""
        logger.info("Camera start-pan-up-left command executed")
        return self._start_continuous_move(pan=-1, tilt=1)

    def start_pan_up_right(self):
        """Start diagonal move up-right"""
        logger.info("Camera start-pan-up-right command executed")
        return self._start_continuous_move(pan=1, tilt=1)

    def start_pan_down_left(self):
        """Start diagonal move down-left"""
        logger.info("Camera start-pan-down-left command executed")
        return self._start_continuous_move(pan=-1, tilt=-1)

    def start_pan_down_right(self):
        """Start diagonal move down-right"""
        logger.info("Camera start-pan-down-right command executed")
        return self._start_continuous_move(pan=1, tilt=-1)
    
    def start_zoom_in(self):
        """Start zooming in (call stop_movement to stop)"""
        logger.info("Camera start-zoom-in command executed")
        return self._start_continuous_move(zoom=1)
    
    def start_zoom_out(self):
        """Start zooming out (call stop_movement to stop)"""
        logger.info("Camera start-zoom-out command executed")
        return self._start_continuous_move(zoom=-1)
    
    def go_to_home(self):
        """Move camera to home position"""
        conn_error = self._check_connection()
        if conn_error:
            return conn_error
        
        if self.ptz_service is None:
            return {"success": False, "error": "PTZ service not available"}
        
        try:
            request = self.ptz_service.create_type('GotoHomePosition')
            request.ProfileToken = self.profile_token
            self.ptz_service.GotoHomePosition(request)
            logger.info("Camera moved to home position")
            return {"success": True}
        except Exception as e:
            logger.error(f"Go to home failed: {e}")
            return {"success": False, "error": str(e)}
    
    def get_ptz_status(self) -> Dict:
        """Get current PTZ position"""
        conn_error = self._check_connection()
        if conn_error:
            return conn_error
        
        if self.ptz_service is None:
            return {"success": False, "error": "PTZ service not available"}
        
        try:
            status = self.ptz_service.GetStatus({'ProfileToken': self.profile_token})
            return {
                "success": True,
                "position": {
                    "pan": status.Position.PanTilt.x if status.Position else 0,
                    "tilt": status.Position.PanTilt.y if status.Position else 0,
                    "zoom": status.Position.Zoom.x if status.Position else 0
                }
            }
        except Exception as e:
            logger.error(f"Get PTZ status failed: {e}")
            return {"success": False, "error": str(e)}
    
    def get_zoom_level(self) -> Dict:
        """Get current zoom level as percentage (0-100)"""
        conn_error = self._check_connection()
        if conn_error:
            return conn_error
        
        if self.ptz_service is None:
            return {"success": False, "error": "PTZ service not available"}
        
        try:
            status = self.ptz_service.GetStatus({'ProfileToken': self.profile_token})
            # ONVIF zoom is typically 0.0 to 1.0
            zoom_value = status.Position.Zoom.x if status.Position and status.Position.Zoom else 0
            # Convert to percentage (0-100)
            zoom_percentage = int(zoom_value * 100)
            zoom_percentage = max(0, min(100, zoom_percentage))  # Clamp to 0-100
            
            return {
                "success": True,
                "zoom_level": zoom_percentage,
                "zoom_raw": zoom_value
            }
        except Exception as e:
            logger.error(f"Get zoom level failed: {e}")
            return {"success": False, "error": str(e), "zoom_level": 50}
    
    # ==================== Focus Controls ====================
    
    def set_focus_mode(self, auto: bool):
        """Set focus mode (auto or manual)"""
        conn_error = self._check_connection()
        if conn_error:
            return conn_error
        
        if self.imaging_service is None:
            return {"success": False, "error": "Imaging service not available"}
        
        try:
            # Get current imaging settings
            settings = self.imaging_service.GetImagingSettings({'VideoSourceToken': self.video_source_token})
            
            # Update focus mode
            request = self.imaging_service.create_type('SetImagingSettings')
            request.VideoSourceToken = self.video_source_token
            request.ImagingSettings = {
                'Focus': {
                    'AutoFocusMode': 'AUTO' if auto else 'MANUAL'
                }
            }
            
            self.imaging_service.SetImagingSettings(request)
            logger.info(f"Focus mode set to {'AUTO' if auto else 'MANUAL'}")
            return {"success": True, "autoFocus": auto}
            
        except Exception as e:
            logger.error(f"Set focus mode failed: {e}")
            return {"success": False, "error": str(e)}
    
    def set_focus_position(self, position: float):
        """Set manual focus position (0-100)"""
        conn_error = self._check_connection()
        if conn_error:
            return conn_error
        
        if self.imaging_service is None:
            return {"success": False, "error": "Imaging service not available"}
        
        try:
            # Convert 0-100 to camera's focus range
            focus_value = position / 100.0
            
            request = self.imaging_service.create_type('Move')
            request.VideoSourceToken = self.video_source_token
            request.Focus = {
                'Absolute': {
                    'Position': focus_value,
                    'Speed': 1.0
                }
            }
            
            self.imaging_service.Move(request)
            logger.info(f"Focus position set to {position}%")
            return {"success": True, "position": position}
            
        except Exception as e:
            logger.error(f"Set focus position failed: {e}")
            return {"success": False, "error": str(e)}
    
    def focus_near(self):
        """Start continuous focus towards near (call focus_stop to stop)"""
        logger.info("[FOCUS] focus_near() - starting continuous focus NEAR")
        conn_error = self._check_connection()
        if conn_error:
            logger.error(f"[FOCUS] Connection error: {conn_error}")
            return conn_error
        
        if self.imaging_service is None:
            logger.error("[FOCUS] Imaging service not available")
            return {"success": False, "error": "Imaging service not available"}
        
        try:
            request = self.imaging_service.create_type('Move')
            request.VideoSourceToken = self.video_source_token
            request.Focus = {
                'Continuous': {
                    'Speed': -1.0  # Negative = near, full speed
                }
            }
            self.imaging_service.Move(request)
            logger.info("[FOCUS] Continuous focus NEAR started (speed=-1.0)")
            return {"success": True}
        except Exception as e:
            logger.error(f"[FOCUS] Focus near failed: {e}")
            return {"success": False, "error": str(e)}
    
    def focus_far(self):
        """Start continuous focus towards far (call focus_stop to stop)"""
        logger.info("[FOCUS] focus_far() - starting continuous focus FAR")
        conn_error = self._check_connection()
        if conn_error:
            logger.error(f"[FOCUS] Connection error: {conn_error}")
            return conn_error
        
        if self.imaging_service is None:
            logger.error("[FOCUS] Imaging service not available")
            return {"success": False, "error": "Imaging service not available"}
        
        try:
            request = self.imaging_service.create_type('Move')
            request.VideoSourceToken = self.video_source_token
            request.Focus = {
                'Continuous': {
                    'Speed': 1.0  # Positive = far, full speed
                }
            }
            self.imaging_service.Move(request)
            logger.info("[FOCUS] Continuous focus FAR started (speed=1.0)")
            return {"success": True}
        except Exception as e:
            logger.error(f"[FOCUS] Focus far failed: {e}")
            return {"success": False, "error": str(e)}
    
    def focus_stop(self):
        """Stop continuous focus movement"""
        logger.info("[FOCUS] focus_stop() - stopping focus")
        conn_error = self._check_connection()
        if conn_error:
            logger.error(f"[FOCUS] Connection error: {conn_error}")
            return conn_error
        
        if self.imaging_service is None:
            logger.error("[FOCUS] Imaging service not available")
            return {"success": False, "error": "Imaging service not available"}
        
        try:
            self.imaging_service.Stop({'VideoSourceToken': self.video_source_token})
            logger.info("[FOCUS] Focus STOPPED")
            return {"success": True}
        except Exception as e:
            logger.error(f"[FOCUS] Focus stop failed: {e}")
            return {"success": False, "error": str(e)}
    
    # ==================== Illuminator Controls ====================
    
    # def set_illuminator(self, enabled: bool):
    #     """
    #     Turn IR illuminator on/off.
    #     Uses USR connection if available, falls back to ONVIF IR cut filter.
    #     """
    #     logger.info(f"[CAMERA] set_illuminator called with enabled={enabled}, has_illuminator={self.illuminator is not None}")
        
    #     # Try USR protocol first (hardware illuminator)
    #     if self.illuminator:
    #         logger.info(f"[CAMERA] Calling illuminator.set_enabled({enabled})")
    #         result = self.illuminator.set_enabled(enabled)
    #         logger.info(f"[CAMERA] Illuminator result: {result}")
    #         return result
        
    #     # Fall back to ONVIF IR cut filter control
    #     conn_error = self._check_connection()
    #     if conn_error:
    #         return conn_error
        
    #     if self.imaging_service is None:
    #         return {"success": False, "error": "Imaging service not available"}
        
    #     try:
    #         request = self.imaging_service.create_type('SetImagingSettings')
    #         request.VideoSourceToken = self.video_source_token
    #         request.ImagingSettings = {
    #             'IrCutFilter': 'OFF' if enabled else 'ON'  # IR cut filter OFF = IR mode ON
    #         }
            
    #         self.imaging_service.SetImagingSettings(request)
    #         logger.info(f"Illuminator {'enabled' if enabled else 'disabled'} (via ONVIF)")
    #         return {"success": True, "enabled": enabled}
            
    #     except Exception as e:
    #         logger.error(f"Set illuminator failed: {e}")
    #         return {"success": False, "error": str(e)}

    def _ensure_default_usr_illuminator(self) -> bool:
        if self.illuminator is not None:
            return True
        try:
            self.illuminator = IlluminatorService()
            logger.info("Default USR illuminator service attached dynamically")
            return True
        except Exception as e:
            logger.error("Failed to attach default USR illuminator service: %s", e)
            return False

    def set_illuminator(self, enabled: bool):
        """
        Turn external USR illuminator on/off.
        Do not report ONVIF success when USR path is expected.
        """
        logger.info(
            "[CAMERA] set_illuminator called enabled=%s has_illuminator=%s",
            enabled,
            self.illuminator is not None,
        )

        conn = get_usr_connection()
        usr_connected = conn.is_device_connected("illuminator")
        logger.info("[CAMERA] external USR illuminator connected=%s", usr_connected)

        if usr_connected and not self.illuminator:
            self._ensure_default_usr_illuminator()

        if self.illuminator:
            result = self.illuminator.set_enabled(enabled)
            logger.info("[CAMERA] illuminator USR result=%s", result)
            if not result.get("success"):
                return {"success": False, "error": result.get("error", "USR illuminator command failed")}
            return result

        logger.error("External USR illuminator not connected and no illuminator service available")
        return {
            "success": False,
            "error": "External USR illuminator is not connected; command not sent",
            "enabled": enabled,
        }


    
    def set_illuminator_brightness(self, brightness: int):
        """
        Set illuminator brightness (0-100).
        Uses USR connection if available.
        """
        logger.info(f"[CAMERA] set_illuminator_brightness called with brightness={brightness}, has_illuminator={self.illuminator is not None}")
        if self.illuminator:
            result = self.illuminator.set_brightness(brightness)
            logger.info(f"[CAMERA] Set brightness result: {result}")
            return result
        
        # No ONVIF fallback for brightness control
        logger.warning("Illuminator brightness control not available (no USR connection)")
        return {"success": False, "error": "Illuminator brightness control requires USR connection"}
    
    def set_illuminator_fov(self, fov: int):
        """
        Set illuminator FOV/angle (5-90 degrees).
        Uses serial protocol to control motor position.
        """
        if self.illuminator:
            return self.illuminator.set_motor_position(fov)
        
        # No ONVIF fallback for FOV control
        logger.warning("Illuminator FOV control not available (no serial connection)")
        return {"success": False, "error": "Illuminator FOV control requires serial connection"}
    
    def get_illuminator_status(self):
        """Query illuminator on/off status."""
        if self.illuminator:
            return self.illuminator.query_status()
        
        # Return cached/default state if no serial connection
        return {"success": True, "enabled": False, "source": "default"}
    
    def get_illuminator_brightness(self):
        """Query current illuminator brightness."""
        if self.illuminator:
            return self.illuminator.query_brightness()
        
        # Return cached/default state if no serial connection
        return {"success": True, "brightness": 75, "source": "default"}
    
    def get_illuminator_fov(self):
        """Query current illuminator FOV/motor position."""
        if self.illuminator:
            return self.illuminator.query_motor_position()
        
        # Return cached/default state if no serial connection
        return {"success": True, "fov": 30, "source": "default"}
    
    def increase_illuminator_brightness(self):
        """Increase illuminator brightness by one step."""
        logger.info(f"[CAMERA] increase_illuminator_brightness called, has_illuminator={self.illuminator is not None}")
        if self.illuminator:
            result = self.illuminator.increase_brightness()
            logger.info(f"[CAMERA] Increase brightness result: {result}")
            return result
        
        return {"success": False, "error": "Illuminator control requires USR connection"}
    
    def decrease_illuminator_brightness(self):
        """Decrease illuminator brightness by one step."""
        logger.info(f"[CAMERA] decrease_illuminator_brightness called, has_illuminator={self.illuminator is not None}")
        if self.illuminator:
            result = self.illuminator.decrease_brightness()
            logger.info(f"[CAMERA] Decrease brightness result: {result}")
            return result
        
        return {"success": False, "error": "Illuminator control requires USR connection"}
    
    def reset_illuminator(self):
        """Reset illuminator to default position (max FOV)."""
        if self.illuminator:
            return self.illuminator.reset_to_default()
        
        return {"success": False, "error": "Illuminator control requires serial connection"}
    
    # ==================== Image Quality Controls ====================
    
    def set_brightness(self, brightness: float) -> Dict:
        """Set image brightness (0-100)"""
        conn_error = self._check_connection()
        if conn_error:
            return conn_error
        
        if self.imaging_service is None:
            return {"success": False, "error": "Imaging service not available"}
        
        try:
            # Convert 0-100 to camera's brightness range (typically 0-100 or 0.0-1.0)
            # ONVIF typically uses 0-100 for brightness
            brightness_value = max(0, min(100, brightness))
            
            # Get current imaging settings first
            settings = self.imaging_service.GetImagingSettings({'VideoSourceToken': self.video_source_token})
            
            # Update brightness
            request = self.imaging_service.create_type('SetImagingSettings')
            request.VideoSourceToken = self.video_source_token
            request.ImagingSettings = settings
            request.ImagingSettings.Brightness = brightness_value
            
            self.imaging_service.SetImagingSettings(request)
            logger.info(f"Brightness set to {brightness_value}")
            return {"success": True, "brightness": brightness_value}
            
        except Exception as e:
            logger.error(f"Set brightness failed: {e}")
            return {"success": False, "error": str(e)}
    
    def get_brightness(self) -> Dict:
        """Get current image brightness"""
        conn_error = self._check_connection()
        if conn_error:
            return conn_error
        
        if self.imaging_service is None:
            return {"success": False, "error": "Imaging service not available"}
        
        try:
            settings = self.imaging_service.GetImagingSettings({'VideoSourceToken': self.video_source_token})
            brightness = getattr(settings, 'Brightness', 50)
            return {"success": True, "brightness": brightness}
        except Exception as e:
            logger.error(f"Get brightness failed: {e}")
            return {"success": False, "error": str(e), "brightness": 50}
    
    def set_contrast(self, contrast: float) -> Dict:
        """Set image contrast (0-100)"""
        conn_error = self._check_connection()
        if conn_error:
            return conn_error
        
        if self.imaging_service is None:
            return {"success": False, "error": "Imaging service not available"}
        
        try:
            # Convert 0-100 to camera's contrast range (typically 0-100)
            contrast_value = max(0, min(100, contrast))
            
            # Get current imaging settings first
            settings = self.imaging_service.GetImagingSettings({'VideoSourceToken': self.video_source_token})
            
            # Update contrast
            request = self.imaging_service.create_type('SetImagingSettings')
            request.VideoSourceToken = self.video_source_token
            request.ImagingSettings = settings
            request.ImagingSettings.Contrast = contrast_value
            
            self.imaging_service.SetImagingSettings(request)
            logger.info(f"Contrast set to {contrast_value}")
            return {"success": True, "contrast": contrast_value}
            
        except Exception as e:
            logger.error(f"Set contrast failed: {e}")
            return {"success": False, "error": str(e)}
    
    def get_contrast(self) -> Dict:
        """Get current image contrast"""
        conn_error = self._check_connection()
        if conn_error:
            return conn_error
        
        if self.imaging_service is None:
            return {"success": False, "error": "Imaging service not available"}
        
        try:
            settings = self.imaging_service.GetImagingSettings({'VideoSourceToken': self.video_source_token})
            contrast = getattr(settings, 'Contrast', 50)
            return {"success": True, "contrast": contrast}
        except Exception as e:
            logger.error(f"Get contrast failed: {e}")
            return {"success": False, "error": str(e), "contrast": 50}
    
    def set_polarity(self, polarity: str) -> Dict:
        """
        Set thermal camera polarity (white hot / black hot)
        
        Args:
            polarity: Either 'white_hot' or 'black_hot'
        
        Note: Different thermal cameras implement this differently via ONVIF.
        Common methods:
        1. ImageStabilization (ON = white hot, OFF = black hot)
        2. BacklightCompensation Mode
        3. Vendor-specific extension
        """
        conn_error = self._check_connection()
        if conn_error:
            return conn_error
        
        if self.imaging_service is None:
            return {"success": False, "error": "Imaging service not available"}
        
        try:
            # Get current imaging settings first
            settings = self.imaging_service.GetImagingSettings({'VideoSourceToken': self.video_source_token})
            
            # Create request
            request = self.imaging_service.create_type('SetImagingSettings')
            request.VideoSourceToken = self.video_source_token
            request.ImagingSettings = settings
            
            # Try different methods to set polarity
            # Method 1: Use ImageStabilization (common for thermal cameras)
            # ON typically means white hot, OFF means black hot
            if polarity == 'white_hot':
                if hasattr(request.ImagingSettings, 'ImageStabilization'):
                    request.ImagingSettings.ImageStabilization = 'ON'
                # Also try inverting color by setting ColorSaturation
                if hasattr(request.ImagingSettings, 'ColorSaturation'):
                    request.ImagingSettings.ColorSaturation = 100
            else:  # black_hot
                if hasattr(request.ImagingSettings, 'ImageStabilization'):
                    request.ImagingSettings.ImageStabilization = 'OFF'
                if hasattr(request.ImagingSettings, 'ColorSaturation'):
                    request.ImagingSettings.ColorSaturation = 0
            
            # Method 2: Try BacklightCompensation
            if hasattr(request.ImagingSettings, 'BacklightCompensation'):
                if polarity == 'white_hot':
                    request.ImagingSettings.BacklightCompensation.Mode = 'ON'
                else:
                    request.ImagingSettings.BacklightCompensation.Mode = 'OFF'
            
            self.imaging_service.SetImagingSettings(request)
            logger.info(f"Polarity set to {polarity}")
            return {"success": True, "polarity": polarity}
            
        except Exception as e:
            logger.error(f"Set polarity failed: {e}")
            return {"success": False, "error": str(e)}
    
    def get_polarity(self) -> Dict:
        """Get current thermal camera polarity"""
        conn_error = self._check_connection()
        if conn_error:
            return conn_error
        
        if self.imaging_service is None:
            return {"success": False, "error": "Imaging service not available"}
        
        try:
            settings = self.imaging_service.GetImagingSettings({'VideoSourceToken': self.video_source_token})
            
            # Try to detect polarity from settings
            polarity = 'white_hot'  # Default
            
            # Check ImageStabilization
            if hasattr(settings, 'ImageStabilization'):
                polarity = 'white_hot' if settings.ImageStabilization == 'ON' else 'black_hot'
            # Check ColorSaturation
            elif hasattr(settings, 'ColorSaturation'):
                polarity = 'white_hot' if settings.ColorSaturation >= 50 else 'black_hot'
            
            return {"success": True, "polarity": polarity}
        except Exception as e:
            logger.error(f"Get polarity failed: {e}")
            return {"success": False, "error": str(e), "polarity": "white_hot"}
    
    # ==================== Presets Management ====================
    
    def _get_presets_file(self) -> str:
        """Get the presets file path for this camera"""
        # Use camera-specific presets file
        base_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
        safe_camera_id = self.camera_id.replace(':', '_').replace('/', '_')
        return os.path.join(base_dir, f'presets_{safe_camera_id}.json')
    
    def _load_presets(self):
        """Load presets from file"""
        try:
            presets_file = self._get_presets_file()
            os.makedirs(os.path.dirname(presets_file), exist_ok=True)
            if os.path.exists(presets_file):
                with open(presets_file, 'r') as f:
                    self.presets = json.load(f)
            else:
                # Fall back to legacy file if exists
                if os.path.exists(PRESETS_FILE):
                    with open(PRESETS_FILE, 'r') as f:
                        self.presets = json.load(f)
                else:
                    self.presets = []
        except Exception as e:
            logger.error(f"Failed to load presets: {e}")
            self.presets = []
    
    def _save_presets(self):
        """Save presets to file"""
        try:
            presets_file = self._get_presets_file()
            os.makedirs(os.path.dirname(presets_file), exist_ok=True)
            with open(presets_file, 'w') as f:
                json.dump(self.presets, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save presets: {e}")
    
    def get_presets(self) -> List[Dict]:
        """Get all saved presets"""
        return self.presets
    
    def create_preset(self, name: str, zoom: int = None, fov: int = 30) -> Dict:
        """Create a new preset at current position"""
        try:
            # Get current PTZ position - MUST succeed to create preset
            status = self.get_ptz_status()
            if not status.get("success"):
                error_msg = status.get("error", "Failed to get current PTZ position")
                logger.error(f"Cannot create preset: {error_msg}")
                return {"success": False, "error": f"Cannot create preset: {error_msg}"}
            
            position = status.get("position", {})
            pan = position.get("pan", 0)
            tilt = position.get("tilt", 0)
            ptz_zoom = position.get("zoom", 0)
            
            # ALWAYS use actual camera zoom level (ignore any frontend value)
            # This ensures the preset captures the true camera state
            zoom_status = self.get_zoom_level()
            if zoom_status.get("success"):
                zoom = zoom_status.get("zoom_level", 0)
                logger.info(f"Got zoom from get_zoom_level: {zoom}% (raw: {zoom_status.get('zoom_raw')})")
            else:
                zoom = int(ptz_zoom * 100)
                logger.info(f"get_zoom_level failed, using ptz_zoom: {ptz_zoom} -> {zoom}%")
            
            logger.info(f"Creating preset '{name}' at position: pan={pan}, tilt={tilt}, ptz_zoom={ptz_zoom}, zoom_percent={zoom}%")
            
            # Create preset
            new_id = max([p.get("id", 0) for p in self.presets], default=0) + 1
            preset = {
                "id": new_id,
                "name": name,
                "zoom": zoom,
                "fov": fov,
                "pan": pan,
                "tilt": tilt,
                "ptz_zoom": ptz_zoom
            }
            
            # Also save to camera if PTZ service available and connected
            if self._connected and self.ptz_service:
                try:
                    request = self.ptz_service.create_type('SetPreset')
                    request.ProfileToken = self.profile_token
                    request.PresetName = name
                    result = self.ptz_service.SetPreset(request)
                    preset["camera_preset_token"] = result
                except Exception as e:
                    logger.warning(f"Could not save preset to camera: {e}")
            
            self.presets.append(preset)
            self._save_presets()
            
            logger.info(f"Created preset: {name}")
            return {"success": True, "preset": preset}
            
        except Exception as e:
            logger.error(f"Create preset failed: {e}")
            return {"success": False, "error": str(e)}
    
    def update_preset(self, preset_id: int, name: str = None, zoom: int = None, fov: int = None) -> Dict:
        """Update an existing preset"""
        try:
            for preset in self.presets:
                if preset.get("id") == preset_id:
                    if name is not None:
                        preset["name"] = name
                    if zoom is not None:
                        preset["zoom"] = zoom
                    if fov is not None:
                        preset["fov"] = fov
                    self._save_presets()
                    logger.info(f"Updated preset {preset_id}")
                    return {"success": True, "preset": preset}
            
            return {"success": False, "error": "Preset not found"}
            
        except Exception as e:
            logger.error(f"Update preset failed: {e}")
            return {"success": False, "error": str(e)}
    
    def update_preset_position(self, preset_id: int) -> Dict:
        """Update a preset's PTZ position to the current camera position"""
        try:
            # Get current PTZ position - MUST succeed
            status = self.get_ptz_status()
            if not status.get("success"):
                error_msg = status.get("error", "Failed to get current PTZ position")
                logger.error(f"Cannot update preset position: {error_msg}")
                return {"success": False, "error": f"Cannot update preset position: {error_msg}"}
            
            position = status.get("position", {})
            pan = position.get("pan", 0)
            tilt = position.get("tilt", 0)
            ptz_zoom = position.get("zoom", 0)
            
            # Get actual zoom level as percentage (0-100) from camera
            zoom_status = self.get_zoom_level()
            zoom_percent = zoom_status.get("zoom_level", 0) if zoom_status.get("success") else int(ptz_zoom * 100)
            
            # Find and update the preset
            for preset in self.presets:
                if preset.get("id") == preset_id:
                    preset["pan"] = pan
                    preset["tilt"] = tilt
                    preset["ptz_zoom"] = ptz_zoom
                    preset["zoom"] = zoom_percent  # Update zoom percentage too
                    
                    # Also update camera preset if available
                    if self._connected and self.ptz_service:
                        try:
                            request = self.ptz_service.create_type('SetPreset')
                            request.ProfileToken = self.profile_token
                            request.PresetName = preset.get("name", f"Preset {preset_id}")
                            if preset.get("camera_preset_token"):
                                request.PresetToken = preset["camera_preset_token"]
                            result = self.ptz_service.SetPreset(request)
                            preset["camera_preset_token"] = result
                        except Exception as e:
                            logger.warning(f"Could not update preset on camera: {e}")
                    
                    self._save_presets()
                    logger.info(f"Updated preset {preset_id} position: pan={pan}, tilt={tilt}, ptz_zoom={ptz_zoom}, zoom_percent={zoom_percent}")
                    return {"success": True, "preset": preset}
            
            return {"success": False, "error": "Preset not found"}
            
        except Exception as e:
            logger.error(f"Update preset position failed: {e}")
            return {"success": False, "error": str(e)}
    
    def delete_preset(self, preset_id: int) -> Dict:
        """Delete a preset"""
        try:
            for i, preset in enumerate(self.presets):
                if preset.get("id") == preset_id:
                    # Remove from camera if available
                    if self._connected and self.ptz_service and preset.get("camera_preset_token"):
                        try:
                            request = self.ptz_service.create_type('RemovePreset')
                            request.ProfileToken = self.profile_token
                            request.PresetToken = preset["camera_preset_token"]
                            self.ptz_service.RemovePreset(request)
                        except Exception as e:
                            logger.warning(f"Could not remove preset from camera: {e}")
                    
                    self.presets.pop(i)
                    self._save_presets()
                    logger.info(f"Deleted preset {preset_id}")
                    return {"success": True}
            
            return {"success": False, "error": "Preset not found"}
            
        except Exception as e:
            logger.error(f"Delete preset failed: {e}")
            return {"success": False, "error": str(e)}
    
    def go_to_preset(self, preset_id: int) -> Dict:
        """Move camera to a preset position"""
        conn_error = self._check_connection()
        if conn_error:
            return conn_error
        
        try:
            preset = None
            for p in self.presets:
                if p.get("id") == preset_id:
                    preset = p
                    break
            
            if not preset:
                return {"success": False, "error": "Preset not found"}
            
            if not self.ptz_service:
                return {"success": False, "error": "PTZ service not available"}
            
            # Get stored PTZ values
            pan = preset.get("pan", 0)
            tilt = preset.get("tilt", 0)
            
            # Use zoom percentage (what's shown in UI) converted to 0.0-1.0 range
            # This ensures what you see (e.g., "50%") is what gets applied
            zoom_percent = preset.get("zoom", 0)
            zoom_raw = zoom_percent / 100.0
            
            logger.info(f"Going to preset '{preset.get('name')}': pan={pan}, tilt={tilt}, zoom={zoom_percent}% (raw={zoom_raw})")
            
            # Always use AbsoluteMove to ensure our stored values are applied
            request = self.ptz_service.create_type('AbsoluteMove')
            request.ProfileToken = self.profile_token
            request.Position = {
                'PanTilt': {'x': pan, 'y': tilt},
                'Zoom': {'x': zoom_raw}
            }
            self.ptz_service.AbsoluteMove(request)
            logger.info(f"Moved to preset '{preset['name']}': pan={pan}, tilt={tilt}, zoom={zoom_percent}%")
            return {"success": True, "preset": preset}
            
        except Exception as e:
            logger.error(f"Go to preset failed: {e}")
            return {"success": False, "error": str(e)}
    
    # ==================== Auto-Pan Tour ====================
    
    def start_auto_pan(self, preset_ids: List[int], interval: int = 10) -> Dict:
        """Start auto-pan tour between presets"""
        self.auto_pan_enabled = True
        self.auto_pan_interval = interval
        self.auto_pan_presets = preset_ids
        logger.info(f"Auto-pan started with {len(preset_ids)} presets, interval: {interval}s")
        return {
            "success": True, 
            "enabled": True, 
            "presets": preset_ids, 
            "interval": interval
        }
    
    def stop_auto_pan(self) -> Dict:
        """Stop auto-pan tour"""
        self.auto_pan_enabled = False
        logger.info("Auto-pan stopped")
        return {"success": True, "enabled": False}
    
    def get_auto_pan_status(self) -> Dict:
        """Get auto-pan status"""
        return {
            "enabled": self.auto_pan_enabled,
            "interval": self.auto_pan_interval,
            "presets": self.auto_pan_presets
        }
    
    # ==================== Tracking ====================
    
    def set_tracking(self, enabled: bool) -> Dict:
        """Enable or disable auto-tracking feature"""
        conn_error = self._check_connection()
        if conn_error:
            return conn_error
        
        if self.ptz_service is None:
            return {"success": False, "error": "PTZ service not available"}
        
        try:
            # Try to use ONVIF PTZ tracking if available
            # Note: Not all cameras support this via ONVIF
            # Some cameras may require proprietary API calls
            request = self.ptz_service.create_type('SetConfiguration')
            request.PTZConfiguration = self.ptz_service.GetConfiguration({'PTZConfigurationToken': self.ptz_configuration_token})
            
            # Enable/disable move and position tracking
            # This is camera-specific and may not work on all cameras
            if hasattr(request.PTZConfiguration, 'MoveRamp'):
                request.PTZConfiguration.MoveRamp = 1 if enabled else 0
            
            self.ptz_service.SetConfiguration(request)
            self.tracking_enabled = enabled
            logger.info(f"Tracking {'enabled' if enabled else 'disabled'}")
            return {"success": True, "enabled": enabled}
            
        except Exception as e:
            # If ONVIF tracking not supported, just track the state locally
            # The camera may have built-in tracking that's always on
            logger.warning(f"Could not set tracking via ONVIF (camera may have built-in tracking): {e}")
            self.tracking_enabled = enabled
            return {"success": True, "enabled": enabled, "note": "Tracking state stored (camera may have built-in tracking)"}
    
    def get_tracking_status(self) -> Dict:
        """Get tracking status"""
        return {
            "success": True,
            "enabled": self.tracking_enabled
        }
    
    # ==================== Camera Info ====================
    
    def get_device_info(self) -> Dict:
        """Get camera device information"""
        conn_error = self._check_connection()
        if conn_error:
            return conn_error
        
        try:
            device_service = self.camera.create_devicemgmt_service()
            info = device_service.GetDeviceInformation()
            return {
                "success": True,
                "manufacturer": info.Manufacturer,
                "model": info.Model,
                "firmware": info.FirmwareVersion,
                "serial": info.SerialNumber,
                "hardware": info.HardwareId
            }
        except Exception as e:
            logger.error(f"Get device info failed: {e}")
            return {"success": False, "error": str(e)}
    
    def get_stream_uri(self, stream_type: str = "RTSP", protocol: str = "UDP") -> Dict:
        """Get the RTSP stream URI from the camera"""
        conn_error = self._check_connection()
        if conn_error:
            return conn_error
        
        if self.media_service is None:
            return {"success": False, "error": "Media service not available"}
        
        try:
            # Create stream setup request
            stream_setup = {
                'Stream': 'RTP-Unicast',
                'Transport': {
                    'Protocol': protocol  # UDP, HTTP, or RTSP
                }
            }
            
            # Get stream URI
            request = self.media_service.create_type('GetStreamUri')
            request.StreamSetup = stream_setup
            request.ProfileToken = self.profile_token
            
            response = self.media_service.GetStreamUri(request)
            
            stream_uri = response.Uri
            
            # If URI doesn't include credentials, add them
            if self.username and self.password:
                if '://' in stream_uri and '@' not in stream_uri:
                    # Insert credentials into the URI
                    # Encode # as %23 (fragment separator breaks URL parsing)
                    encoded_user = self.username.replace('#', '%23')
                    encoded_pass = self.password.replace('#', '%23')
                    protocol_end = stream_uri.find('://') + 3
                    stream_uri = (
                        stream_uri[:protocol_end] + 
                        f"{encoded_user}:{encoded_pass}@" + 
                        stream_uri[protocol_end:]
                    )
            
            logger.info(f"Stream URI retrieved: {stream_uri}")
            return {
                "success": True,
                "uri": stream_uri,
                "protocol": protocol
            }
            
        except Exception as e:
            logger.error(f"Get stream URI failed: {e}")
            return {"success": False, "error": str(e)}
    
    def get_snapshot_uri(self) -> Dict:
        """Get the snapshot URI from the camera"""
        conn_error = self._check_connection()
        if conn_error:
            return conn_error
        
        if self.media_service is None:
            return {"success": False, "error": "Media service not available"}
        
        try:
            request = self.media_service.create_type('GetSnapshotUri')
            request.ProfileToken = self.profile_token
            
            response = self.media_service.GetSnapshotUri(request)
            
            snapshot_uri = response.Uri
            
            # If URI doesn't include credentials, add them
            if self.username and self.password:
                if '://' in snapshot_uri and '@' not in snapshot_uri:
                    protocol_end = snapshot_uri.find('://') + 3
                    snapshot_uri = (
                        snapshot_uri[:protocol_end] + 
                        f"{self.username}:{self.password}@" + 
                        snapshot_uri[protocol_end:]
                    )
            
            logger.info(f"Snapshot URI retrieved: {snapshot_uri}")
            return {
                "success": True,
                "uri": snapshot_uri
            }
            
        except Exception as e:
            logger.error(f"Get snapshot URI failed: {e}")
            return {"success": False, "error": str(e)}
    
    def get_all_stream_uris(self) -> Dict:
        """Get all available stream profiles and their URIs"""
        conn_error = self._check_connection()
        if conn_error:
            return conn_error
        
        if self.media_service is None:
            return {"success": False, "error": "Media service not available"}
        
        try:
            profiles = self.media_service.GetProfiles()
            streams = []
            
            for profile in profiles:
                try:
                    # Get stream URI for this profile
                    stream_setup = {
                        'Stream': 'RTP-Unicast',
                        'Transport': {'Protocol': 'RTSP'}
                    }
                    
                    request = self.media_service.create_type('GetStreamUri')
                    request.StreamSetup = stream_setup
                    request.ProfileToken = profile.token
                    
                    response = self.media_service.GetStreamUri(request)
                    stream_uri = response.Uri
                    
                    # Add credentials
                    if self.username and self.password:
                        if '://' in stream_uri and '@' not in stream_uri:
                            protocol_end = stream_uri.find('://') + 3
                            stream_uri = (
                                stream_uri[:protocol_end] + 
                                f"{self.username}:{self.password}@" + 
                                stream_uri[protocol_end:]
                            )
                    
                    # Get video encoder config for resolution info
                    resolution = "Unknown"
                    encoding = "Unknown"
                    if hasattr(profile, 'VideoEncoderConfiguration') and profile.VideoEncoderConfiguration:
                        vec = profile.VideoEncoderConfiguration
                        if hasattr(vec, 'Resolution') and vec.Resolution:
                            resolution = f"{vec.Resolution.Width}x{vec.Resolution.Height}"
                        if hasattr(vec, 'Encoding'):
                            encoding = vec.Encoding
                    
                    streams.append({
                        "profile_token": profile.token,
                        "profile_name": profile.Name if hasattr(profile, 'Name') else profile.token,
                        "uri": stream_uri,
                        "resolution": resolution,
                        "encoding": encoding
                    })
                    
                except Exception as e:
                    logger.warning(f"Could not get stream URI for profile {profile.token}: {e}")
            
            logger.info(f"Found {len(streams)} stream profiles")
            return {
                "success": True,
                "streams": streams
            }
            
        except Exception as e:
            logger.error(f"Get all stream URIs failed: {e}")
            return {"success": False, "error": str(e)}


class CameraManager:
    """
    Manages multiple camera connections.
    Provides a registry of camera services that can be accessed by camera_id.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cameras: Dict[str, CameraService] = {}
            cls._instance._default_camera_id: Optional[str] = None
        return cls._instance
    
    def get_camera(self, camera_id: str = None, camera_ip: str = None, 
                   camera_port: int = None, username: str = None, 
                   password: str = None, onvif_port: int = None,
                   illuminator_port: str = None, illuminator_ip: str = None,
                   illuminator_tcp_port: int = None, illuminator_username: str = None,
                   illuminator_password: str = None,
                   auto_create: bool = True) -> Optional[CameraService]:
        """
        Get or create a camera service by ID or connection details.
        
        Args:
            camera_id: Unique identifier for the camera
            camera_ip: Camera IP address (used if creating new)
            camera_port: Camera port (used if creating new)
            username: Camera username (used if creating new)
            password: Camera password (used if creating new)
            onvif_port: ONVIF port for PTZ control (used if creating new)
            illuminator_port: Serial port for illuminator control (used if creating new)
            illuminator_ip: Illuminator IP address for network control (used if creating new)
            illuminator_tcp_port: Illuminator TCP port (used if creating new)
            illuminator_username: Illuminator username (used if creating new)
            illuminator_password: Illuminator password (used if creating new)
            auto_create: If True, create camera service if it doesn't exist
            
        Returns:
            CameraService instance or None
        """
        # Determine camera_id
        if camera_id is None:
            if camera_ip:
                port = camera_port or DEFAULT_CAMERA_PORT
                camera_id = f"{camera_ip}:{port}"
            elif self._default_camera_id:
                camera_id = self._default_camera_id
            else:
                # No default camera configured
                logger.warning("No camera_id specified and no default camera configured")
                return None
        
        # Return existing camera if available
        if camera_id in self._cameras:
            return self._cameras[camera_id]
        
        # Create new camera service if auto_create is True and we have enough info
        if auto_create and camera_ip:
            camera_service = CameraService(
                camera_ip=camera_ip,
                camera_port=camera_port or DEFAULT_CAMERA_PORT,
                username=username,
                password=password,
                onvif_port=onvif_port or DEFAULT_ONVIF_PORT,
                camera_id=camera_id,
                illuminator_port=illuminator_port,
                illuminator_ip=illuminator_ip,
                illuminator_tcp_port=illuminator_tcp_port,
                illuminator_username=illuminator_username,
                illuminator_password=illuminator_password
            )
            self._cameras[camera_id] = camera_service
            
            # Set as default if it's the first camera
            if self._default_camera_id is None:
                self._default_camera_id = camera_id
            
            return camera_service
        
        # Camera not found and can't auto-create
        if camera_id not in self._cameras:
            logger.warning(f"Camera {camera_id} not found and cannot auto-create without camera_ip")
        
        return None
    
    def register_camera(self, camera_ip: str, camera_port: int = None, 
                        username: str = None, password: str = None,
                        onvif_port: int = None,
                        camera_id: str = None,
                        illuminator_port: str = None,
                        illuminator_ip: str = None,
                        illuminator_tcp_port: int = None,
                        illuminator_username: str = None,
                        illuminator_password: str = None) -> CameraService:
        """
        Register a new camera with the manager.
        
        Args:
            camera_ip: Camera IP address (required)
            camera_port: Camera HTTP port (default: 80)
            username: Camera username for ONVIF authentication
            password: Camera password for ONVIF authentication
            onvif_port: ONVIF port for PTZ control (default: 80)
            camera_id: Unique identifier (default: generated from IP:port)
            illuminator_port: Serial port for illuminator control (e.g., 'COM3' or '/dev/ttyUSB0')
            illuminator_ip: Illuminator IP address for network control (e.g., '192.168.0.7')
            illuminator_tcp_port: Illuminator TCP port (default: 8000)
            illuminator_username: Illuminator username (optional)
            illuminator_password: Illuminator password (optional)
        
        Returns:
            The registered CameraService
        """
        port = camera_port or DEFAULT_CAMERA_PORT
        cam_id = camera_id or f"{camera_ip}:{port}"
        
        camera_service = CameraService(
            camera_ip=camera_ip,
            camera_port=port,
            username=username,
            password=password,
            onvif_port=onvif_port or DEFAULT_ONVIF_PORT,
            camera_id=cam_id,
            illuminator_port=illuminator_port,
            illuminator_ip=illuminator_ip,
            illuminator_tcp_port=illuminator_tcp_port,
            illuminator_username=illuminator_username,
            illuminator_password=illuminator_password
        )
        
        self._cameras[cam_id] = camera_service
        
        # Set as default if it's the first camera
        if self._default_camera_id is None:
            self._default_camera_id = cam_id
        
        logger.info(f"Registered camera: {cam_id}")
        return camera_service
    
    def unregister_camera(self, camera_id: str) -> bool:
        """Remove a camera from the manager"""
        if camera_id in self._cameras:
            self._cameras[camera_id].disconnect()
            del self._cameras[camera_id]
            
            # Update default if we removed the default camera
            if self._default_camera_id == camera_id:
                self._default_camera_id = next(iter(self._cameras), None)
            
            logger.info(f"Unregistered camera: {camera_id}")
            return True
        return False
    
    def list_cameras(self) -> List[Dict]:
        """List all registered cameras with their status"""
        return [
            {
                "camera_id": cam_id,
                "connected": cam.is_connected(),
                "camera_ip": cam.camera_ip,
                "camera_port": cam.camera_port,
                "is_default": cam_id == self._default_camera_id
            }
            for cam_id, cam in self._cameras.items()
        ]
    
    def set_default_camera(self, camera_id: str) -> bool:
        """Set the default camera"""
        if camera_id in self._cameras:
            self._default_camera_id = camera_id
            return True
        return False
    
    def get_default_camera_id(self) -> Optional[str]:
        """Get the default camera ID"""
        return self._default_camera_id
    
    def connect_camera(self, camera_id: str = None) -> Dict:
        """Explicitly connect to a camera"""
        camera = self.get_camera(camera_id, auto_create=False)
        if camera is None:
            return {"success": False, "error": f"Camera {camera_id} not found"}
        
        success = camera._connect()
        return camera.get_connection_status()
    
    def disconnect_camera(self, camera_id: str = None) -> Dict:
        """Disconnect from a camera"""
        camera = self.get_camera(camera_id, auto_create=False)
        if camera is None:
            return {"success": False, "error": f"Camera {camera_id} not found"}
        
        camera.disconnect()
        return {"success": True, "camera_id": camera_id}


# Global camera manager instance
camera_manager = CameraManager()
