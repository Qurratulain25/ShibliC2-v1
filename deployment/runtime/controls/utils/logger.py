import logging
import os
import time
from pathlib import Path


def resolve_log_dir() -> Path:
    """Writable log directory. Production passes SHIBLI_LOG_DIR from the SHIBLI parent."""
    configured = os.getenv("SHIBLI_LOG_DIR", "").strip().strip("\r\n")
    if configured:
        log_dir = Path(configured).expanduser()
    else:
        log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logging():
    """Setup logging to write to combined.log and error.log files with UTC timestamps"""

    # Force logging timestamps to use UTC
    logging.Formatter.converter = time.gmtime

    log_dir = resolve_log_dir()

    # Create handlers
    combined_handler = logging.FileHandler(log_dir / "combined.log")
    error_handler = logging.FileHandler(log_dir / "error.log")
    console_handler = logging.StreamHandler()
    error_handler.setLevel(logging.ERROR)

    # Set format (timestamp will now be in UTC)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    combined_handler.setFormatter(formatter)
    error_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        handlers=[combined_handler, error_handler, console_handler]
    )
