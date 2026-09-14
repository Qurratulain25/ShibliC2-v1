"""
USR Device Connection Manager
Manages TCP Server connection for USR-TCP232 RS232/RS485 to Ethernet converters.

The USR devices are configured as TCP Clients that connect TO this server.
Multiple devices can connect, each handling different hardware:
- LRF device (192.168.0.128) uses prefix: 2F 03 07
- Illuminator device (192.168.0.7) uses prefix: 2F 04 07

Docker Deployment:
This service uses 'network_mode: host' in Docker, which means the container
shares the host's network stack. This allows USR devices to be identified
by their real IP addresses (simple and reliable).

Speed Optimizations:
- Non-blocking socket operations with select()
- Fast timeouts (200ms initial, 500ms typical)
- TCP_NODELAY for low-latency communication
- Optimized socket buffer sizes

Configuration (from USR device web interface):
- Work Mode: TCP Client
- Remote Server Addr: PC IP (e.g., 192.168.0.50)
- Remote Port Number: 8234
- Local Port Number: 8235 (LRF) or 6000 (Illuminator)
"""
import socket
import select
import threading
import time
import logging
from typing import Optional, Dict, Any
from threading import Lock, Event

logger = logging.getLogger(__name__)

# Device type mapping by IP address
DEVICE_TYPE_MAP = {
    "lrf": "192.168.0.128",
    "illuminator": "192.168.0.7"
}

# Command prefixes for device identification (used in backwards-compat send_command)
DEVICE_PREFIXES = {
    "lrf": bytes([0x2F, 0x03, 0x07]),
    "illuminator": bytes([0x2F, 0x04, 0x07])
}

# Speed-optimized timeout settings (in seconds)
FAST_TIMEOUT = 0.2      # 200ms - initial fast check
NORMAL_TIMEOUT = 0.5    # 500ms - normal operation
MAX_TIMEOUT = 1.0       # 1s - maximum wait for slow responses


class USRConnectionManager:
    """
    Singleton TCP Server that manages connections from multiple USR devices.
    
    Multiple USR devices connect TO this server as TCP Clients.
    Devices are identified by their IP address (requires host network mode in Docker).
    
    Optimized for low-latency command/response cycles.
    """
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self, server_ip: str = "192.168.0.50", server_port: int = 8234):
        """
        Initialize the USR Connection Manager.
        
        Args:
            server_ip: IP address to bind the TCP server (0.0.0.0 for all interfaces)
            server_port: Port to listen on (must match USR device Remote Port)
        """
        if self._initialized:
            return
            
        self.server_ip = server_ip
        self.server_port = server_port
        
        self.server_socket: Optional[socket.socket] = None
        
        # Client connections - keyed by IP address for fast lookup
        self.clients: Dict[str, Dict[str, Any]] = {}
        self.clients_lock = Lock()
        
        self.is_running = False
        self.send_lock = Lock()
        self.server_thread: Optional[threading.Thread] = None
        self.stop_event = Event()
        
        # Device IP mapping (can be updated from config)
        self.device_ip_map = dict(DEVICE_TYPE_MAP)
        
        self._initialized = True
        logger.info(f"USR Connection Manager initialized (server: {server_ip}:{server_port})")
    
    def set_device_ip(self, device_type: str, ip: str):
        """
        Set the IP address for a specific device type.
        
        Args:
            device_type: 'lrf' or 'illuminator'
            ip: IP address of the device
        """
        self.device_ip_map[device_type] = ip
        logger.info(f"Device mapping updated: {device_type} -> {ip}")
    
    def start(self) -> bool:
        """
        Start the TCP server and wait for USR device connections.
        
        Returns:
            True if server started successfully
        """
        if self.is_running:
            logger.warning("Server already running")
            return True
        
        try:
            bind_ip = self.server_ip
            self.server_socket = self._create_listen_socket(bind_ip, self.server_port)
            self.server_socket.listen(5)
            self.server_socket.settimeout(1.0)
            
            self.is_running = True
            self.stop_event.clear()
            
            # Start accept thread
            self.server_thread = threading.Thread(target=self._accept_loop, daemon=True)
            self.server_thread.start()
            
            logger.info(f"TCP Server started on {self.server_ip}:{self.server_port}")
            logger.info("Waiting for USR devices to connect...")
            return True
            
        except OSError as e:
            if "10048" in str(e) or "Address already in use" in str(e):
                logger.error(f"Port {self.server_port} already in use. Close other applications using this port.")
            elif self._address_not_available(e):
                logger.error(
                    "USR/LRF/illuminator listener IP %s is not present on this machine (%s). "
                    "Hardware remains UNAVAILABLE; camera/PTZ API continues.",
                    self.server_ip,
                    e,
                )
            else:
                logger.error(f"Failed to start server: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            return False

    @staticmethod
    def _address_not_available(exc: OSError) -> bool:
        winerr = getattr(exc, "winerror", None)
        errno = getattr(exc, "errno", None)
        text = str(exc)
        return (
            winerr == 10049
            or errno in (99, 125)
            or "10049" in text
            or "Cannot assign requested address" in text
            or "The requested address is not valid" in text
        )

    def _create_listen_socket(self, bind_ip: str, port: int) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
        try:
            sock.bind((bind_ip, port))
            return sock
        except OSError as exc:
            if bind_ip not in ("0.0.0.0", "", "::") and self._address_not_available(exc):
                logger.warning(
                    "USR listener IP %s is not available (%s). Binding 0.0.0.0:%s so "
                    "LRF/illuminator stay optional and do not take down SHIBLI-controls.",
                    bind_ip,
                    exc,
                    port,
                )
                try:
                    sock.close()
                except OSError:
                    pass
                fallback = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                fallback.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                fallback.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                fallback.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
                fallback.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
                try:
                    fallback.bind(("0.0.0.0", port))
                    self.server_ip = "0.0.0.0"
                    return fallback
                except OSError:
                    try:
                        fallback.close()
                    except OSError:
                        pass
                    raise exc
            try:
                sock.close()
            except OSError:
                pass
            raise
    
    def _accept_loop(self):
        """Background thread that accepts and maintains client connections."""
        while not self.stop_event.is_set():
            try:
                if self.server_socket:
                    try:
                        client, addr = self.server_socket.accept()
                        
                        # Optimize client socket for low latency
                        client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
                        client.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
                        client.settimeout(NORMAL_TIMEOUT)
                        
                        client_ip = addr[0]
                        client_port = addr[1]
                        
                        # Identify device type by IP address
                        device_type = "unknown"
                        for dev_type, dev_ip in self.device_ip_map.items():
                            if client_ip == dev_ip:
                                device_type = dev_type
                                break
                        
                        with self.clients_lock:
                            # Close existing connection from same IP if any
                            if client_ip in self.clients:
                                try:
                                    self.clients[client_ip]['socket'].close()
                                except:
                                    pass
                                logger.info(f"Replacing existing connection from {client_ip}")
                            
                            self.clients[client_ip] = {
                                'socket': client,
                                'address': addr,
                                'device_type': device_type,
                                'connected_at': time.time()
                            }
                        
                        logger.info(f"USR device connected: {client_ip}:{client_port} -> {device_type}")
                        
                    except socket.timeout:
                        self._check_connections()
                        continue
                    except Exception as e:
                        if not self.stop_event.is_set():
                            logger.debug(f"Accept error: {e}")
                        continue
                else:
                    time.sleep(0.5)
                    
            except Exception as e:
                if not self.stop_event.is_set():
                    logger.error(f"Accept loop error: {e}")
                time.sleep(1)
    
    def _check_connections(self):
        """Check if existing connections are still alive."""
        with self.clients_lock:
            dead_clients = []
            for client_ip, client_info in self.clients.items():
                sock = client_info['socket']
                try:
                    # Use select for non-blocking check
                    ready, _, _ = select.select([sock], [], [], 0)
                    if ready:
                        sock.setblocking(False)
                        try:
                            data = sock.recv(1024, socket.MSG_PEEK)
                            if not data:
                                raise ConnectionError("Connection closed")
                        except BlockingIOError:
                            pass  # No data available, connection still good
                        finally:
                            sock.setblocking(True)
                            sock.settimeout(NORMAL_TIMEOUT)
                except Exception:
                    dead_clients.append(client_ip)
            
            for client_ip in dead_clients:
                device_type = self.clients[client_ip].get('device_type', 'unknown')
                logger.warning(f"USR device disconnected: {client_ip} ({device_type})")
                try:
                    self.clients[client_ip]['socket'].close()
                except:
                    pass
                del self.clients[client_ip]
    
    def _get_client_by_device_type(self, device_type: str) -> Optional[socket.socket]:
        """
        Get client socket by device type.
        
        Args:
            device_type: 'lrf' or 'illuminator'
            
        Returns:
            Socket for the device, or None if not connected
        """
        target_ip = self.device_ip_map.get(device_type)
        if not target_ip:
            logger.error(f"Unknown device type: {device_type}")
            return None
        
        with self.clients_lock:
            client_info = self.clients.get(target_ip)
            if client_info:
                return client_info['socket']
        
        return None
    
    def stop(self):
        """Stop the TCP server."""
        self.stop_event.set()
        self.is_running = False
        
        with self.clients_lock:
            for client_ip, client_info in self.clients.items():
                try:
                    client_info['socket'].close()
                except:
                    pass
            self.clients.clear()
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            self.server_socket = None
        
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=2.0)
        
        logger.info("TCP Server stopped")
    
    def is_device_connected(self, device_type: str) -> bool:
        """
        Check if a specific device is connected.
        
        Args:
            device_type: 'lrf' or 'illuminator'
            
        Returns:
            True if device is connected
        """
        target_ip = self.device_ip_map.get(device_type)
        if not target_ip:
            return False
        
        with self.clients_lock:
            return target_ip in self.clients
    
    def wait_for_device(self, device_type: str, timeout: float = 30.0) -> bool:
        """
        Wait for a specific device to connect.
        
        Args:
            device_type: 'lrf' or 'illuminator'
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if connected within timeout
        """
        start_time = time.time()
        while not self.is_device_connected(device_type) and (time.time() - start_time) < timeout:
            time.sleep(0.1)
        return self.is_device_connected(device_type)
    
    def wait_for_connection(self, timeout: float = 30.0) -> bool:
        """
        Wait for any USR device to connect.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if any device connected within timeout
        """
        start_time = time.time()
        while len(self.clients) == 0 and (time.time() - start_time) < timeout:
            time.sleep(0.1)
        return len(self.clients) > 0
    
    @property
    def is_connected(self) -> bool:
        """Check if any device is connected."""
        with self.clients_lock:
            return len(self.clients) > 0
    
    def send_to_device(self, device_type: str, command: bytes, wait_response: bool = True,
                       timeout: float = NORMAL_TIMEOUT, response_header: bytes = None) -> Optional[bytes]:
        """
        Send a command to a specific device type.
        
        SPEED OPTIMIZED: Uses select() for non-blocking waits and fast timeouts.
        
        Args:
            device_type: 'lrf' or 'illuminator'
            command: Full command bytes including prefix
            wait_response: Whether to wait for response
            timeout: Response timeout in seconds (default 0.5s)
            response_header: Expected header bytes to look for in response (optional)
            
        Returns:
            Response bytes if wait_response=True, else empty bytes on success, None on error
        """
        client_socket = self._get_client_by_device_type(device_type)
        
        if not client_socket:
            logger.error(f"[USR] Device '{device_type}' not connected")
            return None
        
        with self.send_lock:
            try:
                # Send command
                client_socket.setblocking(True)
                client_socket.settimeout(FAST_TIMEOUT)
                
                logger.debug(f"[USR] TX {device_type}: {command.hex().upper()} ({len(command)}B)")
                client_socket.send(command)
                
                if not wait_response:
                    return b''  # Success, no response expected
                
                # Use select() for fast response waiting
                all_data = b''
                start_time = time.time()
                max_wait = min(timeout, MAX_TIMEOUT)
                
                while (time.time() - start_time) < max_wait:
                    ready, _, _ = select.select([client_socket], [], [], FAST_TIMEOUT)
                    
                    if ready:
                        try:
                            chunk = client_socket.recv(1024)
                            if chunk:
                                all_data += chunk
                                logger.debug(f"[USR] RX {device_type}: {chunk.hex().upper()} ({len(chunk)}B)")
                                
                                # Early break if we have the expected response header
                                if response_header and response_header in all_data:
                                    break
                                # If no specific header expected, one read is usually enough
                                if not response_header:
                                    break
                            else:
                                break  # Connection closed
                        except (socket.timeout, BlockingIOError):
                            if all_data:
                                break
                    else:
                        # Timeout on select
                        if all_data:
                            break
                
                if all_data:
                    elapsed = (time.time() - start_time) * 1000
                    logger.debug(f"[USR] Response from {device_type}: {len(all_data)}B in {elapsed:.0f}ms")
                
                return all_data if all_data else None
                
            except Exception as e:
                logger.error(f"[USR] Error sending to {device_type}: {e}")
                # Mark client as disconnected
                target_ip = self.device_ip_map.get(device_type)
                if target_ip:
                    with self.clients_lock:
                        if target_ip in self.clients:
                            try:
                                self.clients[target_ip]['socket'].close()
                            except:
                                pass
                            del self.clients[target_ip]
                return None
    
    def send_command(self, command: bytes, wait_response: bool = True, 
                     timeout: float = NORMAL_TIMEOUT, response_header: bytes = None) -> Optional[bytes]:
        """
        Send a command to the appropriate device based on command prefix.
        
        Args:
            command: Full command bytes including prefix
            wait_response: Whether to wait for response
            timeout: Response timeout in seconds
            response_header: Expected header bytes to look for in response
            
        Returns:
            Response bytes if wait_response=True, else None
        """
        # Determine device from command prefix
        if command.startswith(bytes([0x2F, 0x03, 0x07])):
            return self.send_to_device("lrf", command, wait_response, timeout, response_header)
        elif command.startswith(bytes([0x2F, 0x04, 0x07])):
            return self.send_to_device("illuminator", command, wait_response, timeout, response_header)
        
        # Unknown prefix - try first available client
        with self.clients_lock:
            if not self.clients:
                logger.error("No USR devices connected")
                return None
            
            first_ip = list(self.clients.keys())[0]
            device_type = self.clients[first_ip].get('device_type', 'unknown')
        
        return self.send_to_device(device_type, command, wait_response, timeout, response_header)
    
    def get_status(self) -> Dict[str, Any]:
        """Get connection status for all devices."""
        with self.clients_lock:
            devices_status = {}
            for device_type, expected_ip in self.device_ip_map.items():
                client_info = self.clients.get(expected_ip)
                devices_status[device_type] = {
                    "expected_ip": expected_ip,
                    "connected": client_info is not None,
                    "client_address": f"{client_info['address'][0]}:{client_info['address'][1]}" if client_info else None,
                    "connected_at": client_info.get('connected_at') if client_info else None
                }
            
            return {
                "server_running": self.is_running,
                "server_address": f"{self.server_ip}:{self.server_port}",
                "total_clients_connected": len(self.clients),
                "devices": devices_status
            }


# Global singleton instance
_connection_manager: Optional[USRConnectionManager] = None


def get_usr_connection(server_ip: str = "192.168.0.50", server_port: int = 8234) -> USRConnectionManager:
    """
    Get the global USR Connection Manager instance.
    
    Args:
        server_ip: IP address to bind (0.0.0.0 for all interfaces)
        server_port: Port to listen on
        
    Returns:
        USRConnectionManager singleton instance
    """
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = USRConnectionManager(server_ip, server_port)
    return _connection_manager


def start_usr_server(server_ip: str = "192.168.0.50", server_port: int = 8234) -> bool:
    """
    Start the USR connection server.
    
    Args:
        server_ip: IP address to bind (0.0.0.0 for all interfaces)
        server_port: Port to listen on
        
    Returns:
        True if started successfully
    """
    manager = get_usr_connection(server_ip, server_port)
    return manager.start()


def stop_usr_server():
    """Stop the USR connection server."""
    global _connection_manager
    if _connection_manager:
        _connection_manager.stop()
