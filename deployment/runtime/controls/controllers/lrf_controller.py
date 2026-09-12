"""
LRF (Laser Range Finder) Controller
Handles HTTP endpoints for LRF control operations
"""
from fastapi import Response
from fastapi.responses import JSONResponse
import logging
from typing import Optional
from pydantic import BaseModel
from services.lrf_service import lrf_service
from services.usr_connection import get_usr_connection
logger = logging.getLogger(__name__)

DEFAULT_LRF_IP = "192.168.0.128"
DEFAULT_LRF_PORT = 8234


# Request models
class LRFRegistrationRequest(BaseModel):
    lrf_ip: str
    lrf_port: int = 8234  # SHIBLI LRF uses port 8234
    username: str = ""
    password: str = ""
    camera_id: Optional[str] = None


class LRFController:
    """Controller for LRF operations"""
    
    def __init__(self):
        self.lrf_service = lrf_service
        logger.info("LRFController initialized")
    
    def register_lrf(self, request: LRFRegistrationRequest):
        """
        Register an LRF device for control
        
        POST /api/camera/lrf/register
        Body: {
            "lrf_ip": "192.168.0.7",
            "lrf_port": 80,
            "username": "admin",
            "password": "admin",
            "camera_id": "optional-camera-id"
        }
        """
        try:
            camera_id = request.camera_id or "default"
            
            self.lrf_service.register_lrf(
                camera_id=camera_id,
                lrf_ip=request.lrf_ip,
                lrf_port=request.lrf_port,
                username=request.username,
                password=request.password
            )
            
            logger.info(f"LRF registered successfully for camera {camera_id}")
            return JSONResponse(content={
                "success": True,
                "message": f"LRF registered for camera {camera_id}",
                "camera_id": camera_id
            })
            
        except Exception as e:
            logger.error(f"Error registering LRF: {e}")
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to register LRF: {str(e)}"}
            )

    
    # def single_range(self, camera_id: Optional[str] = None):
    #     """
    #     Perform single range measurement
        
    #     POST /api/camera/lrf/single-range?camera_id=xxx
        
    #     Returns distance in meters
    #     """
    #     try:
    #         camera_id = camera_id or "default"
            
    #         # Check if LRF is registered
    #         lrf_info = self.lrf_service.get_lrf_info(camera_id)
    #         if not lrf_info:
    #             return JSONResponse(
    #                 status_code=404,
    #                 content={"error": f"LRF not registered for camera {camera_id}"}
    #             )
            
    #         # Perform measurement
    #         distance = self.lrf_service.single_range_measurement(camera_id)
            
    #         if distance is not None:
    #             logger.info(f"Single range measurement: {distance:.2f}m")
    #             return JSONResponse(content={
    #                 "success": True,
    #                 "distance": round(distance, 2),
    #                 "unit": "meters",
    #                 "mode": "single"
    #             })
    #         else:
    #             return JSONResponse(
    #                 status_code=500,
    #                 content={"error": "Failed to measure distance"}
    #             )
                
    #     except Exception as e:
    #         logger.error(f"Error in single range measurement: {e}")
    #         return JSONResponse(
    #             status_code=500,
    #             content={"error": f"Single range measurement failed: {str(e)}"}
    #         )
    
    def _ensure_lrf_binding(self, camera_id: str) -> dict:
        lrf_info = self.lrf_service.get_lrf_info(camera_id)
        if lrf_info:
            return lrf_info

        self.lrf_service.register_lrf(
            camera_id=camera_id,
            lrf_ip=DEFAULT_LRF_IP,
            lrf_port=DEFAULT_LRF_PORT,
            username="",
            password="",
    )
        lrf_info = self.lrf_service.get_lrf_info(camera_id) or {}
        logger.info(
            "[LRF] Auto-registered default LRF for camera_id=%s -> %s:%s",
            camera_id,
            lrf_info.get("ip"),
            lrf_info.get("port"),
        )
        return lrf_info

    def single_range(self, camera_id: Optional[str] = None):
        """
        Perform single range measurement
            
        POST /api/camera/lrf/single-range?camera_id=xxx
            
        Returns distance in meters
        """
        try:
            camera_id = camera_id or "default"
            lrf_info = self._ensure_lrf_binding(camera_id)

            conn = get_usr_connection()
            lrf_connected = conn.is_device_connected("lrf")
            logger.info(
                "[LRF] single-range camera_id=%s registered=%s usr_lrf_connected=%s",
                camera_id,
                lrf_info,
                lrf_connected,
            )

            if not lrf_connected:
                return JSONResponse(
                    status_code=503,
                    content={
                        "success": False,
                        "error": "USR LRF device is not connected",
                        "camera_id": camera_id,
                        "lrf": lrf_info,
                    },
                )

            distance = self.lrf_service.single_range_measurement(camera_id)

            if distance is not None:
                logger.info("[LRF] single-range result camera_id=%s distance=%.2fm", camera_id, distance)
                return JSONResponse(content={
                    "success": True,
                    "distance": round(distance, 2),
                    "unit": "meters",
                    "mode": "single",
                    "camera_id": camera_id,
                })

            logger.error("[LRF] single-range timeout/no response camera_id=%s", camera_id)
            return JSONResponse(
                status_code=504,
                content={
                    "success": False,
                    "error": "LRF timeout or invalid response",
                    "camera_id": camera_id,
                },
            )

        except Exception as e:
            logger.error(f"Error in single range measurement: {e}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Single range measurement failed: {str(e)}"}
            )

    
    def start_continuous(self, camera_id: Optional[str] = None):
        """
        Start continuous ranging mode
        
        POST /api/camera/lrf/start-continuous?camera_id=xxx
        
        LRF will send measurements automatically every ~100ms
        """
        # try:
        #     camera_id = camera_id or "default"
            
        #     # Check if LRF is registered
        #     lrf_info = self.lrf_service.get_lrf_info(camera_id)
        #     if not lrf_info:
        #         return JSONResponse(
        #             status_code=404,
        #             content={"error": f"LRF not registered for camera {camera_id}"}
        #         )
            
        #     # Start continuous mode
        #     success = self.lrf_service.start_continuous_ranging(camera_id)
            
        #     if success:
        #         logger.info(f"Continuous ranging started for camera {camera_id}")
        #         return JSONResponse(content={
        #             "success": True,
        #             "message": "Continuous ranging started",
        #             "mode": "continuous"
        #         })
        #     else:
        #         return JSONResponse(
        #             status_code=500,
        #             content={"error": "Failed to start continuous ranging"}
        #         )
                
        # except Exception as e:
        #     logger.error(f"Error starting continuous ranging: {e}")
        #     return JSONResponse(
        #         status_code=500,
        #         content={"error": f"Failed to start continuous ranging: {str(e)}"}
        #     )

        try:
            camera_id = camera_id or "default"
            lrf_info = self._ensure_lrf_binding(camera_id)
            logger.info("[LRF] continuous-start camera_id=%s registered=%s", camera_id, lrf_info)

            success = self.lrf_service.start_continuous_ranging(camera_id)

            if success:
                logger.info("[LRF] continuous-start success camera_id=%s", camera_id)
                return JSONResponse(content={
                    "success": True,
                    "message": "Continuous ranging started",
                    "mode": "continuous",
                    "camera_id": camera_id,
                })

            logger.error("[LRF] continuous-start failed camera_id=%s", camera_id)
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "Failed to start continuous ranging", "camera_id": camera_id}
            )

        except Exception as e:
            logger.error(f"Error starting continuous ranging: {e}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Failed to start continuous ranging: {str(e)}"}
            )


    
    def stop_continuous(self, camera_id: Optional[str] = None):
        """
        Stop continuous ranging mode
        
        POST /api/camera/lrf/stop-continuous?camera_id=xxx
        """
        # try:
        #     camera_id = camera_id or "default"
            
        #     # Check if LRF is registered
        #     lrf_info = self.lrf_service.get_lrf_info(camera_id)
        #     if not lrf_info:
        #         return JSONResponse(
        #             status_code=404,
        #             content={"error": f"LRF not registered for camera {camera_id}"}
        #         )
            
        #     # Stop continuous mode
        #     success = self.lrf_service.stop_continuous_ranging(camera_id)
            
        #     if success:
        #         logger.info(f"Continuous ranging stopped for camera {camera_id}")
        #         return JSONResponse(content={
        #             "success": True,
        #             "message": "Continuous ranging stopped",
        #             "mode": "stopped"
        #         })
        #     else:
        #         return JSONResponse(
        #             status_code=500,
        #             content={"error": "Failed to stop continuous ranging"}
        #         )
                
        # except Exception as e:
        #     logger.error(f"Error stopping continuous ranging: {e}")
        #     return JSONResponse(
        #         status_code=500,
        #         content={"error": f"Failed to stop continuous ranging: {str(e)}"}
        #     )

        try:
            camera_id = camera_id or "default"
            lrf_info = self._ensure_lrf_binding(camera_id)
            logger.info("[LRF] continuous-stop camera_id=%s registered=%s", camera_id, lrf_info)

            success = self.lrf_service.stop_continuous_ranging(camera_id)

            if success:
                logger.info("[LRF] continuous-stop success camera_id=%s", camera_id)
                return JSONResponse(content={
                    "success": True,
                    "message": "Continuous ranging stopped",
                    "mode": "stopped",
                    "camera_id": camera_id,
                })

            logger.error("[LRF] continuous-stop failed camera_id=%s", camera_id)
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "Failed to stop continuous ranging", "camera_id": camera_id}
            )

        except Exception as e:
            logger.error(f"Error stopping continuous ranging: {e}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Failed to stop continuous ranging: {str(e)}"}
            )

    
    def get_distance(self, camera_id: Optional[str] = None):
        """
        Get current distance reading (during continuous mode)
        
        GET /api/camera/lrf/get-distance?camera_id=xxx
        
        Returns the latest distance measurement from continuous mode
        """
        try:
            camera_id = camera_id or "default"
            
            # Check if LRF is registered
            lrf_info = self.lrf_service.get_lrf_info(camera_id)
            if not lrf_info:
                return JSONResponse(
                    status_code=404,
                    content={"error": f"LRF not registered for camera {camera_id}"}
                )
            
            # Check if continuous mode is active
            if not self.lrf_service.is_continuous_mode_active(camera_id):
                return JSONResponse(
                    status_code=400,
                    content={"error": "Continuous mode is not active"}
                )
            
            # Get distance
            distance = self.lrf_service.get_continuous_distance(camera_id)
            
            if distance is not None:
                return JSONResponse(content={
                    "success": True,
                    "distance": round(distance, 2),
                    "unit": "meters",
                    "mode": "continuous"
                })
            else:
                # No data or no target - this is a valid state, not an error
                return JSONResponse(content={
                    "success": True,
                    "distance": None,
                    "unit": "meters",
                    "mode": "continuous",
                    "status": "no_target"
                })
                
        except Exception as e:
            logger.error(f"Error getting distance: {e}")
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to get distance: {str(e)}"}
            )
    
    def get_status(self, camera_id: Optional[str] = None):
        """
        Get LRF status
        
        GET /api/camera/lrf/status?camera_id=xxx
        
        Returns whether LRF is registered and if continuous mode is active
        """
        try:
            camera_id = camera_id or "default"
            
            lrf_info = self.lrf_service.get_lrf_info(camera_id)
            
            if not lrf_info:
                return JSONResponse(content={
                    "registered": False,
                    "continuous_mode": False,
                    "camera_id": camera_id
                })
            
            is_continuous = self.lrf_service.is_continuous_mode_active(camera_id)
            
            return JSONResponse(content={
                "registered": True,
                "continuous_mode": is_continuous,
                "lrf_ip": lrf_info['ip'],
                "lrf_port": lrf_info['port'],
                "camera_id": camera_id
            })
            
        except Exception as e:
            logger.error(f"Error getting LRF status: {e}")
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to get LRF status: {str(e)}"}
            )


# Global instance
lrf_controller = LRFController()

