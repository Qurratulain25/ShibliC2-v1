"""Production logging — rotating files, timestamps, no credential leakage."""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from typing import Any

_RTSP_AUTH = re.compile(r"(rtsp://)([^/@]+)@", re.IGNORECASE)
_PASSWORD_ASSIGN = re.compile(
    r"(?i)(password|passwd|pwd|secret|token|api[_-]?key|db_key)\s*[:=]\s*\S+"
)

_CONFIGURED = False


def redact_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = _RTSP_AUTH.sub(r"\1***:***@", text)
    return _PASSWORD_ASSIGN.sub(r"\1=***", text)


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact_text(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: redact_text(v) if isinstance(v, str) else v for k, v in record.args.items()}
                else:
                    record.args = tuple(
                        redact_text(a) if isinstance(a, str) else a for a in record.args
                    )
        except Exception:
            pass
        return True


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    from .paths import logs_dir

    log_dir = logs_dir()
    handler = RotatingFileHandler(
        log_dir / "shibli-c2.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    handler.addFilter(RedactFilter())

    stream = logging.StreamHandler()
    stream.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    stream.addFilter(RedactFilter())

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        root.addHandler(handler)
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler) for h in root.handlers):
        root.addHandler(stream)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
