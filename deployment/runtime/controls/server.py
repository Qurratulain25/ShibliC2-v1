# server.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from routes.camera_routes import router as camera_router
from utils.logger import setup_logging
from config import FRONTEND_URL, PORT, USR_SERVER_IP, USR_SERVER_PORT, USR_LRF_DEVICE_IP, USR_ILLUMINATOR_DEVICE_IP
from services.camera_service import camera_manager
from services.usr_connection import get_usr_connection, start_usr_server, stop_usr_server

# Setup logging to files
setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the FastAPI app"""
    # Startup
    print("\n" + "="*70)
    print("[SHIBLI-controls] ONVIF Camera Control Service")
    print("="*70)
    print(f"\n[Config] Server Configuration:")
    print(f"   Frontend URL: {FRONTEND_URL}")
    
    print(f"\n[Camera] Connection Mode: DYNAMIC")
    print(f"   Cameras are registered dynamically from SHIBLI-Core database.")
    print(f"   No hardcoded camera configuration required.")
    
    # Start USR TCP Server for LRF/Illuminator
    print(f"\n[USR] Connection (LRF/Illuminator):")
    print(f"   Starting TCP Server on {USR_SERVER_IP}:{USR_SERVER_PORT}...")
    
    # Configure device IP mapping
    from services.usr_connection import get_usr_connection
    usr_conn = get_usr_connection(USR_SERVER_IP, USR_SERVER_PORT)
    usr_conn.set_device_ip("lrf", USR_LRF_DEVICE_IP)
    usr_conn.set_device_ip("illuminator", USR_ILLUMINATOR_DEVICE_IP)
    
    if start_usr_server(USR_SERVER_IP, USR_SERVER_PORT):
        print(f"   [OK] TCP Server started - waiting for USR devices")
        print(f"   Expected devices:")
        print(f"     - LRF device:         {USR_LRF_DEVICE_IP} (prefix: 2F 03 07)")
        print(f"     - Illuminator device: {USR_ILLUMINATOR_DEVICE_IP} (prefix: 2F 04 07)")
    else:
        print(f"   [FAIL] Failed to start TCP Server (port may be in use)")
    
    print(f"\n[API] Available Camera Management Endpoints:")
    print(f"   GET  /api/camera/cameras              - List all registered cameras")
    print(f"   POST /api/camera/cameras/register     - Register a new camera")
    print(f"   POST /api/camera/cameras/{{id}}/connect  - Connect to a camera")
    print(f"   GET  /api/camera/cameras/{{id}}/status   - Get camera connection status")
    
    print(f"\n[API] LRF/Illuminator Endpoints:")
    print(f"   POST /api/camera/lrf/single-range     - Single range measurement")
    print(f"   POST /api/camera/illuminator          - Turn illuminator on/off")
    print(f"   GET  /api/camera/usr/status           - USR connection status")
    
    print(f"\n[Info] Multi-Camera Support:")
    print(f"   All control endpoints accept optional 'camera_id' query parameter.")
    print(f"   Example: POST /api/camera/pan-left?camera_id=192.168.1.68:80")
    
    print(f"\n[Info] Camera Registration:")
    print(f"   Cameras should be added via SHIBLI-Dashboard Camera Configuration.")
    print(f"   PTZ control uses the RGB camera's ONVIF settings automatically.")
    
    print("\n" + "="*70)
    print(f"[START] Server running on http://0.0.0.0:{PORT}")
    print("="*70 + "\n")
    
    yield
    
    # Shutdown - disconnect all cameras
    print("\n[SHUTDOWN] SHIBLI-controls shutting down...")
    
    # Stop USR connection
    stop_usr_server()
    print("   USR TCP Server stopped")
    
    for cam_info in camera_manager.list_cameras():
        try:
            camera_manager.disconnect_camera(cam_info['camera_id'])
        except:
            pass

app = FastAPI(
    title="SHIBLI-controls",
    description="ONVIF Camera Control Service with multi-camera support",
    version="2.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint - always returns OK even if no cameras connected"""
    cameras = camera_manager.list_cameras()
    return {
        "status": "healthy",
        "service": "SHIBLI-controls",
        "cameras_registered": len(cameras),
        "cameras_connected": sum(1 for c in cameras if c.get('connected', False))
    }

# Include camera routes
app.include_router(camera_router, prefix="/api/camera", tags=["camera"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
