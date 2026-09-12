"""
LRF (Laser Range Finder) Service
Handles communication with LRF devices for distance measurement
Uses shared USR Connection Manager (TCP Server mode)

Protocol Notes:
- All commands must be prefixed with 2F 03 07
- Commands: Stop=ee1602030508, Single=ee1602030205, StartContinuous=ee1602030407
- Response format: ee 16 06 03 XX 00 AB CD EF YY
- Distance = (AB × 256) + CD + (EF ÷ 255) meters

Connection Architecture:
- USR LRF device (192.168.0.128) is configured as TCP Client
- This service uses USRConnectionManager which runs as TCP Server on PC (192.168.0.50:8234)
- Commands are routed to the LRF device specifically (not illuminator)
"""
import time
import logging
from typing import Optional, Dict

from services.usr_connection import get_usr_connection, start_usr_server

logger = logging.getLogger(__name__)


class LRFService:
    """Service for controlling LRF (Laser Range Finder) devices via USR TCP Server"""
    
    # LRF command prefix - REQUIRED before every command
    LRF_PREFIX = bytes([0x2F, 0x03, 0x07])
    
    # LRF Commands (without prefix)
    CMD_STOP = bytes.fromhex('ee1602030508')
    CMD_SINGLE = bytes.fromhex('ee1602030205')
    CMD_CONTINUOUS = bytes.fromhex('ee1602030407')
    
    # Response header for distance measurement
    DISTANCE_RESPONSE_HEADER = bytes.fromhex('ee160603')
    
    def __init__(self, server_ip: str = "192.168.0.50", server_port: int = 8234):
        """
        Initialize LRF Service.
        
        Args:
            server_ip: IP address for TCP server (your PC's IP)
            server_port: Port for TCP server (must match USR device config)
        """
        self.server_ip = server_ip
        self.server_port = server_port
        self.registered_lrfs: Dict[str, Dict] = {}
        self.continuous_mode_active: Dict[str, bool] = {}
        self._connection = None
        
    def _get_connection(self):
        """Get or create the shared USR connection."""
        if self._connection is None:
            self._connection = get_usr_connection(self.server_ip, self.server_port)
        return self._connection
    
    def start_server(self) -> bool:
        """
        Start the TCP server for USR device connection.
        
        Returns:
            True if server started successfully
        """
        return start_usr_server(self.server_ip, self.server_port)
    
    def is_connected(self) -> bool:
        """Check if LRF device is connected."""
        conn = self._get_connection()
        return conn.is_device_connected("lrf")
    
    def wait_for_connection(self, timeout: float = 30.0) -> bool:
        """
        Wait for LRF device to connect.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if connected within timeout
        """
        conn = self._get_connection()
        return conn.wait_for_device("lrf", timeout)
        
    def register_lrf(self, camera_id: str, lrf_ip: str = None, lrf_port: int = None, 
                     username: str = "", password: str = ""):
        """
        Register an LRF device for control.
        
        Note: IP/port parameters are kept for API compatibility but the actual
        connection uses the shared USR TCP Server.
        
        Args:
            camera_id: Unique identifier for the camera system
            lrf_ip: (Deprecated) IP address - not used, connection via USR server
            lrf_port: (Deprecated) Port - not used, connection via USR server
            username: Authentication username (for future use)
            password: Authentication password (for future use)
        """
        self.registered_lrfs[camera_id] = {
            'ip': lrf_ip or self.server_ip,
            'port': lrf_port or self.server_port,
            'username': username,
            'password': password
        }
        self.continuous_mode_active[camera_id] = False
        logger.info(f"LRF registered for camera {camera_id} (using USR server at {self.server_ip}:{self.server_port})")
        
    def unregister_lrf(self, camera_id: str):
        """Unregister an LRF device"""
        if camera_id in self.registered_lrfs:
            # Stop continuous mode if active
            if self.continuous_mode_active.get(camera_id):
                self._send_stop_command(camera_id)
            del self.registered_lrfs[camera_id]
            del self.continuous_mode_active[camera_id]
            logger.info(f"LRF unregistered for camera {camera_id}")
            
    def get_lrf_info(self, camera_id: str) -> Optional[Dict]:
        """Get LRF device information"""
        return self.registered_lrfs.get(camera_id)
    
    def _send_command(self, command: bytes, wait_response: bool = True) -> Optional[bytes]:
        """
        Send a command to the LRF via USR connection.
        
        Args:
            command: Command bytes (without prefix)
            wait_response: Whether to wait for response
            
        Returns:
            Response bytes if wait_response=True, else None
        """
        conn = self._get_connection()
        
        if not conn.is_device_connected("lrf"):
            logger.warning("LRF device not connected, attempting to start server...")
            if not conn.is_running:
                conn.start()
            if not conn.wait_for_device("lrf", timeout=5.0):
                logger.error("LRF device not connected")
                return None
        
        # Build full command with prefix
        # full_command = self.LRF_PREFIX + command
        # logger.info(f"Sending LRF command: {full_command.hex().upper()}")

       # Build full command with prefix
        full_command = self.LRF_PREFIX + command
        logger.info("[LRF] [USR] TX lrf connected=%s cmd=%s", conn.is_device_connected("lrf"), full_command.hex().upper())

        # Route command specifically to LRF device
        response = conn.send_to_device(
            "lrf",
            full_command, 
            wait_response=wait_response,
            timeout=3.0,
            response_header=self.DISTANCE_RESPONSE_HEADER if wait_response else None
        )

        if response:
            logger.info(f"Received LRF response: {response.hex().upper()}")
        
        return response
            
    def _parse_distance_response(self, response: bytes) -> Optional[float]:
        """
        Parse distance from LRF response.
        
        Response format: ee 16 06 03 XX 00 AB CD EF YY
        - Bytes 6,7,8 (AB, CD, EF) contain distance data
        - Distance (meters) = (AB × 256) + CD + (EF ÷ 255)
        
        Args:
            response: Response bytes from LRF
            
        Returns:
            Distance in meters, or None if parsing fails
        """
        if not response or len(response) < 10:
            logger.error(f"Invalid response length: {len(response) if response else 0}")
            return None
            
        try:
            logger.debug(f"Raw LRF response ({len(response)} bytes): {response.hex().upper()}")
            
            # Find the distance response header (ee 16 06 03)
            header_pos = response.find(self.DISTANCE_RESPONSE_HEADER)
            
            if header_pos == -1:
                logger.error("Distance response header (EE 16 06 03) not found")
                return None
            
            # Extract the 10-byte distance response
            distance_response = response[header_pos:header_pos + 10]
            
            if len(distance_response) < 10:
                logger.error(f"Incomplete distance response: {len(distance_response)} bytes")
                return None
            
            logger.debug(f"Distance response at pos {header_pos}: {distance_response.hex().upper()}")
            
            # Byte 4 is command type (02=single, 04=continuous), NOT status
            # Byte 5 is the actual status: 00 or 02 = success, 04 = no target
            command_type = distance_response[4]
            status_byte = distance_response[5]
            
            logger.debug(f"Command type: {command_type:02X}, Status: {status_byte:02X}")
            
            if status_byte == 0x04:
                logger.warning("LRF status: No target found")
                return None
            
            # Extract distance bytes (indices 6, 7, 8)
            byte_ab = distance_response[6]  # High byte
            byte_cd = distance_response[7]  # Low byte
            byte_ef = distance_response[8]  # Decimal byte
            
            # Calculate distance: (AB × 256) + CD + (EF ÷ 255)
            distance = (byte_ab * 256) + byte_cd + (byte_ef / 255.0)
            
            logger.info(f"Distance: {distance:.2f}m (AB={byte_ab:02X}, CD={byte_cd:02X}, EF={byte_ef:02X})")
            return distance
            
        except Exception as e:
            logger.error(f"Error parsing distance: {e}")
            return None
            
    def _send_stop_command(self, camera_id: str = None) -> bool:
        """Send STOP command to LRF."""
        response = self._send_command(self.CMD_STOP, wait_response=True)
        if response:
            logger.info(f"Stop command sent successfully")
            return True
        return False
        
    def single_range_measurement(self, camera_id: str = None) -> Optional[float]:
        """
        Perform a single range measurement.
        
        Workflow:
        1. Send STOP command
        2. Wait 150ms
        3. Send SINGLE RANGE command
        4. Parse distance from response
        
        Args:
            camera_id: Camera identifier (optional, for multi-camera support)
            
        Returns:
            Distance in meters, or None if measurement fails
        """
        try:
            # Step 1: Send STOP command
            stop_response = self._send_command(self.CMD_STOP, wait_response=True)
            logger.debug(f"STOP response: {stop_response.hex().upper() if stop_response else 'None'}")
            
            # Step 2: Wait 150ms
            time.sleep(0.15)
            
            # Step 3: Send SINGLE RANGE command
            response = self._send_command(self.CMD_SINGLE, wait_response=True)
            
            if not response:
                logger.warning("No response from LRF")
                return None
            
            # Step 4: Parse distance
            distance = self._parse_distance_response(response)
            
            if distance is not None:
                logger.info(f"Single range measurement: {distance:.2f}m")
            
            return distance
            
        except Exception as e:
            logger.error(f"Single range measurement error: {e}")
            return None
            
    def start_continuous_ranging(self, camera_id: str = None) -> bool:
        """
        Start continuous ranging mode.
        
        Workflow:
        1. Send STOP command
        2. Wait 100ms
        3. Send START CONTINUOUS command
        
        Args:
            camera_id: Camera identifier
            
        Returns:
            True if started successfully
        """
        try:
            # Send STOP first
            self._send_stop_command(camera_id)
            time.sleep(0.1)
            
            # Send START CONTINUOUS command
            response = self._send_command(self.CMD_CONTINUOUS, wait_response=True)
            
            if response:
                if camera_id:
                    self.continuous_mode_active[camera_id] = True
                logger.info("Continuous ranging started")
                return True
            
            logger.error("Failed to start continuous ranging")
            return False
            
        except Exception as e:
            logger.error(f"Error starting continuous ranging: {e}")
            return False
            
    def stop_continuous_ranging(self, camera_id: str = None) -> bool:
        """
        Stop continuous ranging mode.
        
        Args:
            camera_id: Camera identifier
            
        Returns:
            True if stopped successfully
        """
        success = self._send_stop_command(camera_id)
        if success and camera_id:
            self.continuous_mode_active[camera_id] = False
            logger.info("Continuous ranging stopped")
        return success
            
    def is_continuous_mode_active(self, camera_id: str) -> bool:
        """Check if continuous mode is active for a camera."""
        return self.continuous_mode_active.get(camera_id, False)
    
    def get_continuous_distance(self, camera_id: str = None) -> Optional[float]:
        """
        Get distance reading during continuous mode.
        
        During continuous mode, the LRF sends distance measurements automatically.
        This method reads the incoming data and parses the distance.
        
        Args:
            camera_id: Camera identifier
            
        Returns:
            Distance in meters, or None if no data available
        """
        try:
            conn = self._get_connection()
            
            if not conn.is_device_connected("lrf"):
                logger.warning("LRF device not connected")
                return None
            
            # Get the LRF client socket
            client_socket = conn._get_client_by_device_type("lrf")
            if not client_socket:
                logger.error("LRF socket not available")
                return None
            
            # Read any available data from the socket (non-blocking peek first)
            import socket
            try:
                # Set a short timeout for reading continuous data
                client_socket.settimeout(0.5)
                
                # Read incoming data
                data = client_socket.recv(1024)
                
                if data:
                    logger.debug(f"Continuous mode data received: {data.hex().upper()}")
                    
                    # Parse the distance from the response
                    distance = self._parse_distance_response(data)
                    
                    if distance is not None:
                        logger.info(f"Continuous distance: {distance:.2f}m")
                        return distance
                    
            except socket.timeout:
                logger.debug("No data available from LRF")
                return None
            except Exception as e:
                logger.error(f"Error reading continuous data: {e}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting continuous distance: {e}")
            return None
    
    def get_connection_status(self) -> Dict:
        """Get the USR connection status."""
        conn = self._get_connection()
        return conn.get_status()


# Global instance
lrf_service = LRFService()
