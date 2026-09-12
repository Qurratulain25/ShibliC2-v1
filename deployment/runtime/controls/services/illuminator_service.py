"""
Illuminator Service - Handles communication with IR Illuminator
Uses shared USR Connection Manager (TCP Server mode)
Based on Communication Protocol V3.2 for laser light system

Protocol Details:
- Command Prefix: 2F 04 07 (illuminator specific, vs LRF 2F 03 07)
- Baud Rate: 9600 B/S (handled by USR device)
- Data Format: 1 Start Bit, 8 Data Bits, 1 Stop Bit, No Parity
- Address Code: 0x01 (laser light system)

Command Format (7 bytes after prefix):
- Byte 1: Sync Byte (0xFF)
- Byte 2: Address Code (0x01)
- Byte 3-4: Instruction Code
- Byte 5-6: Data Code
- Byte 7: Checksum Byte (MOD(sum of bytes 2-6) / 0x100)

Connection Architecture:
- USR Illuminator device (192.168.0.7) is configured as TCP Client
- This service uses USRConnectionManager which runs as TCP Server on PC (192.168.0.50:8234)
- Commands are routed to the Illuminator device specifically (not LRF)
"""

import logging
import time
from typing import Dict, Optional, Tuple
from threading import Lock

from services.usr_connection import get_usr_connection, start_usr_server

logger = logging.getLogger(__name__)


class IlluminatorService:
    """
    Service for controlling IR Illuminator via USR TCP Server connection.
    
    Shares the same USR connection as LRF service but uses different command prefix.
    """
    
    # Command prefix for illuminator (different from LRF which uses 2F 03 07)
    ILLUMINATOR_PREFIX = bytes([0x2F, 0x04, 0x07])
    
    # Protocol constants
    SYNC_BYTE = 0xFF
    ADDRESS_CODE = 0x01
    
    # Instruction codes for CONTROL commands (Inst1 = 0x01)
    INST_CONTROL = (0x01, 0x01)        # On/Off control
    INST_BRIGHTNESS_STEP = (0x01, 0x02)  # Brightness increase/decrease by step
    INST_SET_BRIGHTNESS = (0x01, 0x03)   # Set specific brightness
    INST_SET_MOTOR = (0x01, 0x05)        # Motor control for FOV adjustment
    INST_RESET = (0x01, 0x06)            # Reset to default
    
    # Instruction codes for QUERY commands (Inst1 = 0x02)
    INST_QUERY_STATUS = (0x02, 0x01)     # Query laser on/off status
    INST_QUERY_BRIGHTNESS = (0x02, 0x03) # Query brightness level
    INST_QUERY_MOTOR = (0x02, 0x05)      # Query motor position
    
    # Data codes for control commands
    DATA_LASER_ON = (0x01, 0x00)
    DATA_LASER_OFF = (0x00, 0x00)
    DATA_INCREASE_BRIGHTNESS = (0x00, 0x00)
    DATA_DECREASE_BRIGHTNESS = (0x01, 0x00)
    
    def __init__(self, server_ip: str = "192.168.0.50", server_port: int = 8234,
                 port: str = None, baud_rate: int = 9600,
                 ip: str = None, tcp_port: int = 8234,
                 username: str = None, password: str = None):
        """
        Initialize illuminator service.
        
        Args:
            server_ip: IP address for TCP server (your PC's IP)
            server_port: Port for TCP server (must match USR device config)
            port: (Deprecated) Serial port - not used with USR connection
            baud_rate: (Deprecated) Baud rate - configured on USR device
            ip: (Deprecated) Network IP - not used, connection via USR server
            tcp_port: (Deprecated) TCP port - not used, connection via USR server
            username: (Deprecated) Username - not used
            password: (Deprecated) Password - not used
        """
        self.server_ip = server_ip
        self.server_port = server_port
        self._connection = None
        self.lock = Lock()
        
        # Connection type for compatibility
        self.connection_type = 'network'
        self.is_connected = False
        
        # State cache
        self.cached_brightness = 75  # Default brightness %
        self.cached_status = False   # Laser on/off
        self.cached_fov = 30         # Default FOV in degrees
        
        logger.info(f"Illuminator Service initialized (using USR server at {server_ip}:{server_port})")
    
    def _get_connection(self):
        """Get or create the shared USR connection."""
        if self._connection is None:
            self._connection = get_usr_connection(self.server_ip, self.server_port)
        return self._connection
    
    def _connect(self) -> bool:
        """Establish connection via USR server."""
        conn = self._get_connection()
        if not conn.is_running:
            conn.start()
        self.is_connected = conn.is_device_connected("illuminator")
        return self.is_connected
    
    def _disconnect(self):
        """Disconnect (no-op, connection managed by USRConnectionManager)."""
        pass
    
    def _calculate_checksum(self, data: bytes) -> int:
        """
        Calculate checksum byte.
        Checksum = MOD(Byte2 + Byte3 + Byte4 + Byte5 + Byte6) / 0x100
        """
        return sum(data) % 0x100
    
    def _build_command(self, inst_code: Tuple[int, int], data_code: Tuple[int, int]) -> bytes:
        """
        Build a 7-byte command according to protocol.
        
        Args:
            inst_code: Tuple of (Instruction Code Byte 1, Instruction Code Byte 2)
            data_code: Tuple of (Data Code Byte 1, Data Code Byte 2)
        
        Returns:
            7-byte command ready to send
        """
        # Build bytes 2-6
        payload = bytes([
            self.ADDRESS_CODE,
            inst_code[0],
            inst_code[1],
            data_code[0],
            data_code[1]
        ])
        
        # Calculate checksum
        checksum = self._calculate_checksum(payload)
        
        # Build full command
        command = bytes([self.SYNC_BYTE]) + payload + bytes([checksum])
        
        return command
    
    def _send_command(self, command: bytes, expect_response: bool = False) -> Optional[bytes]:
        """
        Send command to illuminator via USR connection.
        
        Args:
            command: 7-byte command to send
            expect_response: Whether to wait for and return response
        
        Returns:
            Response bytes if expect_response=True, None otherwise
        """
        conn = self._get_connection()
        
        # Check illuminator device connection
        is_connected = conn.is_device_connected("illuminator")
        logger.info(f"[SEND_CMD] Illuminator connected: {is_connected}, Server running: {conn.is_running}")
        
        if not is_connected:
            logger.warning("Illuminator device not connected, attempting to start server...")
            if not conn.is_running:
                conn.start()
            if not conn.wait_for_device("illuminator", timeout=5.0):
                logger.error("Illuminator device not connected after waiting")
                return None
        
        with self.lock:
            try:
                # Add illuminator prefix before command
                full_command = self.ILLUMINATOR_PREFIX + command
                logger.info(f"[SEND_CMD] Full command with prefix: {full_command.hex().upper()}")
                logger.info(f"[SEND_CMD] Command breakdown: PREFIX={self.ILLUMINATOR_PREFIX.hex().upper()} + CMD={command.hex().upper()}")
                
                # # Route command specifically to Illuminator device
                # response = conn.send_to_device(
                #     "illuminator",
                #     full_command,
                #     wait_response=expect_response,
                #     timeout=1.0
                # )

                logger.info("[USR] TX illuminator: %s", full_command.hex().upper())
                # Route command specifically to Illuminator device
                response = conn.send_to_device(
                    "illuminator",
                    full_command,
                    wait_response=expect_response,
                    timeout=1.0
                )


                logger.info(f"[SEND_CMD] Command sent to illuminator device successfully")
                
                # Delay between commands (protocol recommendation: 1-2ms)
                time.sleep(0.002)
                
                if response:
                    logger.info(f"[SEND_CMD] Received response: {response.hex().upper()}")
                    return response
                elif expect_response:
                    logger.warning("[SEND_CMD] Expected response but got none")
                
                return response
                
            except Exception as e:
                logger.error(f"[SEND_CMD] Failed to send illuminator command: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return None
    
    def _parse_response(self, response: bytes) -> Optional[Dict]:
        """
        Parse response from illuminator.
        
        Response format is same as command: FF 01 [INST] [DATA] CHECKSUM
        """
        if not response or len(response) < 7:
            return None
        
        # Remove prefix if present
        if response.startswith(self.ILLUMINATOR_PREFIX):
            response = response[len(self.ILLUMINATOR_PREFIX):]
        
        if len(response) < 7:
            return None
        
        # Find sync byte
        sync_pos = response.find(bytes([self.SYNC_BYTE]))
        if sync_pos == -1:
            return None
        
        response = response[sync_pos:]
        if len(response) < 7:
            return None
        
        # Validate sync byte and address
        if response[0] != self.SYNC_BYTE or response[1] != self.ADDRESS_CODE:
            return None
        
        # Verify checksum
        expected_checksum = self._calculate_checksum(response[1:6])
        if response[6] != expected_checksum:
            logger.warning(f"Checksum mismatch: expected {expected_checksum:02X}, got {response[6]:02X}")
            # Continue anyway as some devices may not send correct checksum
        
        return {
            'inst_code': (response[2], response[3]),
            'data_code': (response[4], response[5]),
            'checksum': response[6]
        }
    
    # ==================== Public API Methods ====================
    
    # def turn_on(self) -> Dict:
    #     """
    #     Turn laser illuminator ON.
    #     Command: FF 01 01 01 01 00 04
    #     """
    #     try:
    #         command = self._build_command(self.INST_CONTROL, self.DATA_LASER_ON)
    #         logger.info(f"[TURN_ON] Built command (7 bytes): {command.hex().upper()}")
    #         logger.info(f"[TURN_ON] Expected: FF01010101000 4")
    #         result = self._send_command(command)
            
    #         self.cached_status = True
    #         logger.info("Illuminator turned ON - command sent successfully")
    #         return {"success": True, "enabled": True}
            
    #     except Exception as e:
    #         logger.error(f"Failed to turn on illuminator: {e}")
    #         return {"success": False, "error": str(e)}

    def turn_on(self) -> Dict:
        """
        Turn laser illuminator ON.
        Command: FF 01 01 01 01 00 04
        """
        try:
            command = self._build_command(self.INST_CONTROL, self.DATA_LASER_ON)
            logger.info(f"[TURN_ON] Built command (7 bytes): {command.hex().upper()}")
            logger.info(f"[TURN_ON] Expected: FF01010101000 4")
            result = self._send_command(command)

            if result is None:
                logger.error("Illuminator ON failed: no USR send/response")
                return {"success": False, "error": "USR illuminator command failed (ON)"}

            self.cached_status = True
            logger.info("Illuminator turned ON - command sent successfully")
            return {"success": True, "enabled": True}

        except Exception as e:
            logger.error(f"Failed to turn on illuminator: {e}")
            return {"success": False, "error": str(e)}


    def turn_on(self) -> Dict:
        """
        Turn laser illuminator ON.
        Command: FF 01 01 01 01 00 04
        """
        try:
            command = self._build_command(self.INST_CONTROL, self.DATA_LASER_ON)
            logger.info(f"[TURN_ON] Built command (7 bytes): {command.hex().upper()}")
            logger.info(f"[TURN_ON] Expected: FF01010101000 4")
            result = self._send_command(command)

            if result is None:
                logger.error("Illuminator ON failed: no USR send/response")
                return {"success": False, "error": "USR illuminator command failed (ON)"}

            self.cached_status = True
            logger.info("Illuminator turned ON - command sent successfully")
            return {"success": True, "enabled": True}

        except Exception as e:
            logger.error(f"Failed to turn on illuminator: {e}")
            return {"success": False, "error": str(e)}
        
    # def turn_off(self) -> Dict:
    #     """
    #     Turn laser illuminator OFF.
    #     Command: FF 01 01 01 00 00 03
    #     """
    #     try:
    #         command = self._build_command(self.INST_CONTROL, self.DATA_LASER_OFF)
    #         logger.info(f"[TURN_OFF] Built command (7 bytes): {command.hex().upper()}")
    #         logger.info(f"[TURN_OFF] Expected: FF0101010000003")
    #         result = self._send_command(command)
            
    #         self.cached_status = False
    #         logger.info("Illuminator turned OFF - command sent successfully")
    #         return {"success": True, "enabled": False}
            
    #     except Exception as e:
    #         logger.error(f"Failed to turn off illuminator: {e}")
    #         return {"success": False, "error": str(e)}

    def turn_off(self) -> Dict:
        """
        Turn laser illuminator OFF.
        Command: FF 01 01 01 00 00 03
        """
        try:
            command = self._build_command(self.INST_CONTROL, self.DATA_LASER_OFF)
            logger.info(f"[TURN_OFF] Built command (7 bytes): {command.hex().upper()}")
            logger.info(f"[TURN_OFF] Expected: FF0101010000003")
            result = self._send_command(command)

            if result is None:
                logger.error("Illuminator OFF failed: no USR send/response")
                return {"success": False, "error": "USR illuminator command failed (OFF)"}

            self.cached_status = False
            logger.info("Illuminator turned OFF - command sent successfully")
            return {"success": True, "enabled": False}

        except Exception as e:
            logger.error(f"Failed to turn off illuminator: {e}")
            return {"success": False, "error": str(e)}
    
    def set_enabled(self, enabled: bool) -> Dict:
        """Set illuminator on/off state."""
        if enabled:
            return self.turn_on()
        else:
            return self.turn_off()
    
    def increase_brightness(self) -> Dict:
        """
        Increase brightness by one step.
        Command: FF 01 01 02 00 00 04
        """
        try:
            command = self._build_command(self.INST_BRIGHTNESS_STEP, self.DATA_INCREASE_BRIGHTNESS)
            logger.info(f"[BRIGHTNESS_UP] Built command (7 bytes): {command.hex().upper()}")
            logger.info(f"[BRIGHTNESS_UP] Expected: FF0101020000004")
            self._send_command(command)
            
            self.cached_brightness = min(100, self.cached_brightness + 5)
            logger.info(f"Illuminator brightness increased to {self.cached_brightness}%")
            return {"success": True, "brightness": self.cached_brightness}
            
        except Exception as e:
            logger.error(f"Failed to increase brightness: {e}")
            return {"success": False, "error": str(e)}
    
    def decrease_brightness(self) -> Dict:
        """
        Decrease brightness by one step.
        Command: FF 01 01 02 01 00 05
        """
        try:
            command = self._build_command(self.INST_BRIGHTNESS_STEP, self.DATA_DECREASE_BRIGHTNESS)
            logger.info(f"[BRIGHTNESS_DOWN] Built command (7 bytes): {command.hex().upper()}")
            logger.info(f"[BRIGHTNESS_DOWN] Expected: FF0101020100005")
            self._send_command(command)
            
            self.cached_brightness = max(0, self.cached_brightness - 5)
            logger.info(f"Illuminator brightness decreased to {self.cached_brightness}%")
            return {"success": True, "brightness": self.cached_brightness}
            
        except Exception as e:
            logger.error(f"Failed to decrease brightness: {e}")
            return {"success": False, "error": str(e)}
    
    def set_brightness(self, brightness: int) -> Dict:
        """
        Set specific brightness level.
        Command: FF 01 01 03 P1 00 SUM
        
        Args:
            brightness: Brightness level 0-100
        """
        try:
            brightness = max(0, min(100, brightness))
            brightness_hex = int((brightness / 100.0) * 255)
            
            command = self._build_command(self.INST_SET_BRIGHTNESS, (brightness_hex, 0x00))
            self._send_command(command)
            
            self.cached_brightness = brightness
            logger.info(f"Illuminator brightness set to {brightness}%")
            return {"success": True, "brightness": brightness}
            
        except Exception as e:
            logger.error(f"Failed to set brightness: {e}")
            return {"success": False, "error": str(e)}
    
    def query_status(self) -> Dict:
        """
        Query laser on/off status.
        Command: FF 01 02 01 00 00 04
        """
        try:
            # Use INST_QUERY_STATUS (0x02, 0x01) with data (0x00, 0x00)
            command = self._build_command(self.INST_QUERY_STATUS, (0x00, 0x00))
            logger.info(f"[QUERY_STATUS] Built command (7 bytes): {command.hex().upper()}")
            logger.info(f"[QUERY_STATUS] Expected: FF0102010000004")
            response = self._send_command(command, expect_response=True)
            
            if response:
                parsed = self._parse_response(response)
                if parsed and parsed['inst_code'] == (0x02, 0x01):
                    # Response: P1=0 means OFF, P1=1 means ON
                    status = parsed['data_code'][0] == 0x01
                    self.cached_status = status
                    return {"success": True, "enabled": status}
            
            return {"success": True, "enabled": self.cached_status}
            
        except Exception as e:
            logger.error(f"Failed to query status: {e}")
            return {"success": False, "error": str(e), "enabled": self.cached_status}
    
    def query_brightness(self) -> Dict:
        """
        Query current brightness level.
        Command: FF 01 02 03 00 00 06
        """
        try:
            # Use INST_QUERY_BRIGHTNESS (0x02, 0x03) with data (0x00, 0x00)
            command = self._build_command(self.INST_QUERY_BRIGHTNESS, (0x00, 0x00))
            logger.info(f"[QUERY_BRIGHTNESS] Built command (7 bytes): {command.hex().upper()}")
            logger.info(f"[QUERY_BRIGHTNESS] Expected: FF0102030000006")
            response = self._send_command(command, expect_response=True)
            
            if response:
                parsed = self._parse_response(response)
                if parsed and parsed['inst_code'] == (0x02, 0x03):
                    brightness_hex = parsed['data_code'][0]
                    brightness = int((brightness_hex / 255.0) * 100)
                    self.cached_brightness = brightness
                    return {"success": True, "brightness": brightness}
            
            return {"success": True, "brightness": self.cached_brightness}
            
        except Exception as e:
            logger.error(f"Failed to query brightness: {e}")
            return {"success": False, "error": str(e), "brightness": self.cached_brightness}
    
    def set_motor_position(self, angle: int) -> Dict:
        """
        Set motor position to control illuminator FOV/angle.
        Command: FF 01 01 05 P1 P2 SUM
        
        Args:
            angle: Angle in degrees (5-90)
        """
        try:
            angle = max(5, min(90, angle))
            
            # Map angle to motor positions (0x0001 to 0xFFFF)
            position = int(((angle - 5) / 85.0) * 0xFFFE) + 1
            
            p1 = (position >> 8) & 0xFF
            p2 = position & 0xFF
            
            command = self._build_command(self.INST_SET_MOTOR, (p1, p2))
            self._send_command(command)
            
            self.cached_fov = angle
            logger.info(f"Illuminator FOV set to {angle}°")
            return {"success": True, "fov": angle}
            
        except Exception as e:
            logger.error(f"Failed to set motor position: {e}")
            return {"success": False, "error": str(e)}
    
    def query_motor_position(self) -> Dict:
        """
        Query current motor position.
        Command: FF 01 02 05 00 00 08
        """
        try:
            # Use INST_QUERY_MOTOR (0x02, 0x05) with data (0x00, 0x00)
            command = self._build_command(self.INST_QUERY_MOTOR, (0x00, 0x00))
            logger.info(f"[QUERY_MOTOR] Built command (7 bytes): {command.hex().upper()}")
            logger.info(f"[QUERY_MOTOR] Expected: FF0102050000008")
            response = self._send_command(command, expect_response=True)
            
            if response:
                parsed = self._parse_response(response)
                if parsed and parsed['inst_code'] == (0x02, 0x05):
                    p1, p2 = parsed['data_code']
                    position = (p1 << 8) | p2
                    angle = int(((position - 1) / 0xFFFE) * 85.0) + 5
                    self.cached_fov = angle
                    return {"success": True, "fov": angle, "motor_position": position}
            
            return {"success": True, "fov": self.cached_fov}
            
        except Exception as e:
            logger.error(f"Failed to query motor position: {e}")
            return {"success": False, "error": str(e), "fov": self.cached_fov}
    
    def reset_to_default(self) -> Dict:
        """
        Initialize motor and set to maximum output light angle position.
        Command: FF 01 01 06 00 00 08
        """
        try:
            command = self._build_command(self.INST_RESET, (0x00, 0x00))
            self._send_command(command)
            
            self.cached_fov = 90
            logger.info("Illuminator reset to default position")
            return {"success": True, "fov": 90}
            
        except Exception as e:
            logger.error(f"Failed to reset illuminator: {e}")
            return {"success": False, "error": str(e)}
    
    def get_cached_state(self) -> Dict:
        """Return cached state without querying hardware."""
        conn = self._get_connection()
        return {
            "success": True,
            "enabled": self.cached_status,
            "brightness": self.cached_brightness,
            "fov": self.cached_fov,
            "connected": conn.is_device_connected("illuminator") if conn else False
        }
    
    def get_connection_status(self) -> Dict:
        """Get the USR connection status."""
        conn = self._get_connection()
        return conn.get_status()
    
    def __del__(self):
        """Cleanup on destruction."""
        pass  # Connection managed by USRConnectionManager
