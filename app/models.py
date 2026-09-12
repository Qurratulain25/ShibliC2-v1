from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class RecordingMode(str, Enum):
    off = "off"
    ch1 = "ch1"
    ch2 = "ch2"
    both = "both"


class PTZDirection(str, Enum):
    up = "up"
    down = "down"
    left = "left"
    right = "right"
    up_left = "up_left"
    up_right = "up_right"
    down_left = "down_left"
    down_right = "down_right"
    stop = "stop"
    home = "home"
    zoom_in = "zoom_in"
    zoom_out = "zoom_out"


class PTZMode(str, Enum):
    abs = "abs"
    rel = "rel"


class PTZTarget(str, Enum):
    both = "both"
    day = "day"
    thermal = "thermal"


class LRFMode(str, Enum):
    single = "single"
    continuous = "continuous"
    scan = "scan"


class IlluminationSource(str, Enum):
    ir = "ir"
    white = "white"
    laser = "laser"


class BeamMode(str, Enum):
    narrow = "narrow"
    medium = "medium"
    wide = "wide"


class PTZMoveRequest(BaseModel):
    direction: PTZDirection
    speed: str = Field(default="medium", pattern="^(low|medium|high)$")
    mode: PTZMode = PTZMode.rel
    ptz_id: Optional[str] = None
    camera_id: Optional[str] = None
    ptz_target: Optional[PTZTarget] = None


class PTZLensRequest(BaseModel):
    action: str = Field(pattern="^(zoom_in|zoom_out|focus_plus|focus_minus|iris_plus|iris_minus)$")
    ptz_id: Optional[str] = None
    camera_id: Optional[str] = None
    ptz_target: Optional[PTZTarget] = None


class PresetRequest(BaseModel):
    preset: str
    ptz_id: Optional[str] = None
    camera_id: Optional[str] = None
    ptz_target: Optional[PTZTarget] = None


class RecordingRequest(BaseModel):
    mode: RecordingMode


class OSDRequest(BaseModel):
    enabled: bool


class OSDConfigRequest(BaseModel):
    show_telemetry: Optional[bool] = None
    show_logo: Optional[bool] = None
    logo_text: Optional[str] = Field(default=None, max_length=48)
    custom_text: Optional[str] = Field(default=None, max_length=120)
    position: Optional[str] = Field(
        default=None,
        pattern="^(top-left|top-right|bottom-left|bottom-right)$",
    )


class LRFRequest(BaseModel):
    mode: LRFMode = LRFMode.single
    camera_id: Optional[str] = None


class AutoPanRequest(BaseModel):
    enabled: bool
    camera_id: Optional[str] = None
    speed: str = Field(default="medium", pattern="^(low|medium|high)$")
    ptz_target: Optional[PTZTarget] = None


class FocusAutoRequest(BaseModel):
    channel: str = Field(default="day", pattern="^(day|thermal)$")
    camera_id: Optional[str] = None
    ptz_id: Optional[str] = None
    ptz_target: Optional[PTZTarget] = None
    auto: Optional[bool] = None


class FocusHoldRequest(BaseModel):
    direction: str = Field(pattern="^(near|far|focus_minus|focus_plus)$")
    channel: str = Field(default="day", pattern="^(day|thermal)$")
    camera_id: Optional[str] = None
    ptz_id: Optional[str] = None
    ptz_target: Optional[PTZTarget] = None


class FocusModeRequest(BaseModel):
    auto: bool
    channel: str = Field(default="day", pattern="^(day|thermal)$")
    camera_id: Optional[str] = None
    ptz_id: Optional[str] = None
    ptz_target: Optional[PTZTarget] = None


class MotorSpeedRequest(BaseModel):
    speed: str = Field(default="medium", pattern="^(low|medium|high)$")
    camera_id: Optional[str] = None
    ptz_id: Optional[str] = None


class ThermalImageRequest(BaseModel):
    polarity: Optional[str] = Field(default=None, pattern="^(white_hot|black_hot)$")
    brightness: Optional[int] = Field(default=None, ge=0, le=100)
    contrast: Optional[int] = Field(default=None, ge=0, le=100)
    camera_id: Optional[str] = None
    ptz_id: Optional[str] = None


class IlluminationRequest(BaseModel):
    enabled: Optional[bool] = None
    source: Optional[IlluminationSource] = None
    intensity: Optional[str] = Field(default=None, pattern="^(low|med|high)$")
    beam: Optional[BeamMode] = None
    brightness: Optional[int] = Field(default=None, ge=0, le=100)
    fov: Optional[int] = Field(default=None, ge=5, le=90)
    fov_action: Optional[str] = Field(default=None, pattern="^(reset)$")
    bump: Optional[str] = Field(default=None, pattern="^(brightness_up|brightness_down|fov_up|fov_down)$")
    camera_id: Optional[str] = None


class QuickActionRequest(BaseModel):
    group: str
    action: str


class LayoutRequest(BaseModel):
    layout: str = Field(
        pattern="^(day_thermal|day_full|thermal_full|custom|single|dual|triple|quad|quad6|grid9|grid16)$"
    )


class LoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=4, max_length=128)
    connection_mode: str = Field(default="lan", max_length=32)


class ConnectionModeRequest(BaseModel):
    connection_mode: str = Field(default="lan", max_length=32)


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=4, max_length=128)
    role: str = Field(pattern="^(ADMINISTRATOR|OPERATOR|VIEWER)$")
    full_name: str = Field(default="", max_length=128)
    permissions: Optional[List[str]] = None
    active: bool = True


class ResetPasswordRequest(BaseModel):
    password: str = Field(min_length=4, max_length=128)


class ForgotPasswordRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    recovery_code: str = Field(min_length=4, max_length=64)
    new_password: str = Field(min_length=4, max_length=128)


class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=128)
    role: Optional[str] = Field(default=None, pattern="^(ADMINISTRATOR|OPERATOR|VIEWER)$")
    permissions: Optional[List[str]] = None
    active: Optional[bool] = None


class UserCamerasRequest(BaseModel):
    camera_ids: List[int] = Field(default_factory=list)


class SettingsUpdateRequest(BaseModel):
    theme: Optional[str] = None
    recording_path: Optional[str] = None
