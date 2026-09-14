import logging
import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 5


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

    combined_handler = RotatingFileHandler(
        log_dir / "combined.log",
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    error_handler = RotatingFileHandler(
        log_dir / "error.log",
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    console_handler = logging.StreamHandler()
    error_handler.setLevel(logging.ERROR)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    combined_handler.setFormatter(formatter)
    error_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logging.basicConfig(
        level=logging.INFO,
        handlers=[combined_handler, error_handler, console_handler]
    )
