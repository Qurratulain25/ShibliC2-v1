import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# JWT configuration
JWT_SECRET = os.getenv('JWT_SECRET', '')

# CORS configuration
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')

# Server configuration
PORT = int(os.getenv('PORT', 8001))

# SHIBLI-Core API URL (for fetching camera configuration)
CORE_API_URL = os.getenv('CORE_API_URL', 'http://localhost:3000')

# =============================================================================
# DEPRECATED: Legacy camera configuration
# These defaults are no longer used. Camera configuration should come from
# the SHIBLI-Core database via the /api/camera/stream/:id endpoint.
# The CameraManager now supports dynamic camera registration.
# =============================================================================
# CAMERA_IP = os.getenv('CAMERA_IP', '192.168.1.68')
# CAMERA_PORT = int(os.getenv('CAMERA_PORT', 80))
# CAMERA_USERNAME = os.getenv('CAMERA_USERNAME', 'admin')
# CAMERA_PASSWORD = os.getenv('CAMERA_PASSWORD', '')

# Fallback defaults (only used if no camera is registered dynamically)
DEFAULT_CAMERA_PORT = int(os.getenv('DEFAULT_CAMERA_PORT', 80))
DEFAULT_ONVIF_PORT = int(os.getenv('DEFAULT_ONVIF_PORT', 80))

# =============================================================================
# USR Device Connection Configuration
# The USR-TCP232 devices connect TO this server as TCP Clients
# Multiple devices can connect, each handling different hardware
# =============================================================================
USR_SERVER_IP = os.getenv('USR_SERVER_IP', '192.168.0.50')  # Your PC's IP address
USR_SERVER_PORT = int(os.getenv('USR_SERVER_PORT', 8234))   # Port USR devices connect to

# Device IP Mapping - which USR device handles which hardware
# LRF device: 192.168.0.128 connects from port 8235
# Illuminator device: 192.168.0.7 connects from port 6000
USR_LRF_DEVICE_IP = os.getenv('USR_LRF_DEVICE_IP', '192.168.0.128')
USR_ILLUMINATOR_DEVICE_IP = os.getenv('USR_ILLUMINATOR_DEVICE_IP', '192.168.0.7')

# =============================================================================
# Legacy Illuminator configuration (deprecated - use USR connection above)
# =============================================================================
ILLUMINATOR_IP = os.getenv('ILLUMINATOR_IP', '192.168.0.50')  # Same as USR_SERVER_IP
ILLUMINATOR_TCP_PORT = int(os.getenv('ILLUMINATOR_TCP_PORT', 8234))  # Same as USR_SERVER_PORT
ILLUMINATOR_USERNAME = os.getenv('ILLUMINATOR_USERNAME', '')
ILLUMINATOR_PASSWORD = os.getenv('ILLUMINATOR_PASSWORD', '')

# Serial connection (deprecated - USR device handles serial)
ILLUMINATOR_SERIAL_PORT = os.getenv('ILLUMINATOR_SERIAL_PORT', None)
