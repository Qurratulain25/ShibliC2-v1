"""Load and normalize environment — safe on Windows/Linux/macOS demo machines."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

_BOOTSTRAPPED = False
_PLACEHOLDER_DB_KEYS = {"", "change-this-in-production", "changeme", "password"}


def _normalize_env_file(path: Path) -> None:
    if not path.is_file():
        return
    try:
        raw = path.read_bytes()
    except OSError:
        return
    if b"\r" not in raw:
        return
    try:
        text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        path.write_text(text, encoding="utf-8", newline="\n")
    except OSError:
        pass


def _sanitize_environ() -> None:
    for key, value in list(os.environ.items()):
        if not isinstance(value, str):
            continue
        cleaned = value.strip().strip("\r\n")
        if cleaned != value:
            os.environ[key] = cleaned


def bootstrap_environment(project_root: Path | None = None) -> None:
    """Load .env files once and strip Windows CRLF artifacts from values."""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    _BOOTSTRAPPED = True

    from .paths import data_dir, env_path, project_root as _root

    if project_root is None:
        project_root = _root()

    runtime_env = env_path()
    candidates = [
        runtime_env,
        data_dir() / ".env",
        project_root / "data" / ".env",
        project_root / ".env",
    ]
    for path in candidates:
        _normalize_env_file(path)
        if path.is_file():
            load_dotenv(path, override=False)

    _sanitize_environ()
    _ensure_production_secrets(runtime_env)
    _sanitize_environ()


def _upsert_env_line(path: Path, name: str, value: str) -> None:
    lines: list[str] = []
    found = False
    if path.is_file():
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    out: list[str] = []
    for line in lines:
        if line.startswith(f"{name}="):
            out.append(f"{name}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{name}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _ensure_production_secrets(env_file: Path) -> None:
    from .paths import data_dir, install_layout, is_frozen

    if not (is_frozen() or install_layout() == "system"):
        return
    os.environ.setdefault("SHIBLI_ENV", "production")
    if (os.getenv("SHIBLI_ENV") or "").strip().lower() in ("production", "prod"):
        if not (os.getenv("SHIBLI_JWT_SECRET") or os.getenv("JWT_SECRET") or "").strip():
            secret = secrets.token_hex(32)
            _upsert_env_line(env_file, "SHIBLI_JWT_SECRET", secret)
            os.environ["SHIBLI_JWT_SECRET"] = secret
        db = data_dir() / "shibli_c2.db"
        key = (os.getenv("SHIBLI_DB_KEY") or "").strip()
        has_db = db.exists() and db.stat().st_size > 0
        if key.lower() in _PLACEHOLDER_DB_KEYS and not has_db:
            key = secrets.token_hex(32)
            _upsert_env_line(env_file, "SHIBLI_DB_KEY", key)
            os.environ["SHIBLI_DB_KEY"] = key
        _upsert_env_line(env_file, "SHIBLI_ENV", os.environ.get("SHIBLI_ENV", "production"))


def env_str(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    if value is None:
        return default
    return str(value).strip().strip("\r\n")
