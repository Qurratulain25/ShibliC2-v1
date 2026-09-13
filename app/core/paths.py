"""Resolve install and data directories — portable across Windows/Linux demo PCs."""
from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_data_dir_cache: Path | None = None


def reset_data_dir_cache() -> None:
    """Test helper — forget the resolved data directory."""
    global _data_dir_cache
    _data_dir_cache = None


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def bundle_dir() -> Path:
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent.parent


def install_dir() -> Path:
    """Immutable application directory (binaries). Not used for writable data."""
    if is_frozen():
        exe_dir = Path(sys.executable).resolve().parent
        if exe_dir.name.lower() == "bin":
            return exe_dir.parent
        if exe_dir.name.lower() == "dist":
            return exe_dir.parent
        return exe_dir
    return bundle_dir()


def install_layout() -> str:
    flag = os.getenv("SHIBLI_INSTALL_LAYOUT", "").strip().lower()
    if flag in ("system", "dev"):
        return flag
    if is_frozen():
        return "system"
    return "dev"


def project_root() -> Path:
    """ShibliC2 project root (parent of dist/ when running EXE)."""
    if is_frozen():
        return install_dir()
    return bundle_dir()


def _dir_writable(root: Path) -> bool:
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def persistent_root() -> Path:
    """Client-writable root. Binaries stay in install_dir() / Program Files / /opt."""
    override = os.getenv("SHIBLI_PERSISTENT_ROOT", "").strip().strip("\r\n")
    if override:
        root = Path(override)
        root.mkdir(parents=True, exist_ok=True)
        return root
    if install_layout() == "system":
        if sys.platform == "win32":
            candidates = [Path(os.environ.get("PROGRAMDATA") or r"C:\ProgramData") / "ShibliC2"]
        else:
            candidates = [Path("/var/lib/shiblic2")]
        for root in candidates:
            if _dir_writable(root):
                return root
        fallback = _user_persistent_root()
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback
    return project_root()


def _user_persistent_root() -> Path:
    """Per-user desktop runtime when the system persistent root is not writable."""
    xdg = os.getenv("XDG_DATA_HOME", "").strip().strip("\r\n")
    if xdg:
        return Path(xdg) / "ShibliC2"
    return Path.home() / ".local" / "share" / "ShibliC2"


def _system_persistent() -> bool:
    return install_layout() == "system" and not os.getenv("SHIBLI_DATA_DIR", "").strip()


def ensure_persistent_tree() -> None:
    if not _system_persistent():
        return
    root = persistent_root()
    for name in ("config", "data", "logs", "recordings", "snapshots", "exports", "backups"):
        (root / name).mkdir(parents=True, exist_ok=True)


def _fallback_data_dir() -> Path:
    override = os.getenv("SHIBLI_DATA_DIR", "").strip().strip("\r\n")
    if override:
        return Path(override)
    xdg = os.getenv("XDG_DATA_HOME", "").strip().strip("\r\n")
    if xdg:
        return Path(xdg) / "ShibliC2"
    return Path.home() / ".local" / "share" / "ShibliC2"


def data_dir() -> Path:
    """
    Writable data directory. Prefers project data/, falls back to user profile
    when the project folder is read-only or owned by another user (common on demos).
    """
    global _data_dir_cache
    if _data_dir_cache is not None:
        return _data_dir_cache

    override = os.getenv("SHIBLI_DATA_DIR", "").strip().strip("\r\n")
    if override:
        root = Path(override)
        root.mkdir(parents=True, exist_ok=True)
        _data_dir_cache = root
        return root

    if install_layout() == "system":
        ensure_persistent_tree()
        root = persistent_root() / "data"
        if _dir_writable(root):
            _data_dir_cache = root
            return root

    local = project_root() / "data"
    if _dir_writable(local):
        _data_dir_cache = local
        return local

    fallback = _fallback_data_dir()
    if _dir_writable(fallback):
        if fallback != local:
            logger.warning(
                "Project data/ is not writable — using %s (set SHIBLI_DATA_DIR to override)",
                fallback,
            )
        _data_dir_cache = fallback
        return fallback

    raise PermissionError(
        f"Cannot write SHIBLI data directory. Tried: {local} and {fallback}. "
        "Run: ./scripts/ensure-ready.sh  or  sudo chown -R $(whoami) data/"
    )


def static_dir() -> Path:
    return bundle_dir() / "static"


def config_path() -> Path:
    if _system_persistent():
        cfg_dir = persistent_root() / "config"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        target = cfg_dir / "config.json"
    else:
        target = data_dir() / "config.json"
    if not target.exists():
        for name in ("config.json", "config.example.json"):
            template = project_root() / name
            if template.exists():
                shutil.copy2(template, target)
                break
    return target


def env_path() -> Path:
    target = data_dir() / ".env"
    if target.exists():
        return target
    db = data_dir() / "shibli_c2.db"
    backups = [
        data_dir() / "shibli_c2.db.verify_backup",
        data_dir() / "shibli_c2.db.verify_backup.safe",
    ]
    db_exists = db.exists() and db.stat().st_size > 0
    backup_exists = any(p.exists() and p.stat().st_size > 0 for p in backups)
    if db_exists or backup_exists:
        raise RuntimeError(
            "data/.env is missing but an encrypted database or backup exists. "
            "Restore the original data/.env. Refusing to create a new environment file."
        )
    templates = [project_root() / ".env.example"]
    if install_layout() != "system":
        templates.append(project_root() / ".env")
    for template in templates:
        if template.exists():
            shutil.copy2(template, target)
            break
    return target


def go2rtc_config_path() -> Path:
    """Runtime go2rtc config in writable data — never overwrite an existing file."""
    if install_layout() != "system":
        legacy = project_root() / "go2rtc.yaml"
        if legacy.exists():
            return legacy
    if _system_persistent():
        cfg_dir = persistent_root() / "config"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        target = cfg_dir / "go2rtc.yaml"
    else:
        target = data_dir() / "go2rtc.yaml"
    if target.exists():
        return target
    examples = [
        data_dir() / "go2rtc.example.yaml",
        install_dir() / "go2rtc.example.yaml",
        install_dir() / "go2rtc.yaml.example",
        project_root() / "go2rtc.example.yaml",
        project_root() / "go2rtc.yaml.example",
        bundle_dir() / "go2rtc.example.yaml",
        bundle_dir() / "go2rtc.yaml.example",
    ]
    for example in examples:
        if example.is_file():
            try:
                shutil.copy2(example, target)
            except OSError:
                pass
            break
    if not target.exists():
        target.write_text(
            "api:\n  listen: \":1984\"\n  origin: \"*\"\n\nstreams: {}\n",
            encoding="utf-8",
        )
    return target


def _persistent_subdir(name: str) -> Path:
    if _system_persistent():
        path = persistent_root() / name
    else:
        path = data_dir() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def recordings_dir() -> Path:
    return _persistent_subdir("recordings")


def logs_dir() -> Path:
    return _persistent_subdir("logs")


def backups_dir() -> Path:
    """Central automatic/manual DB backups. Never the active database directory root."""
    return _persistent_subdir("backups")


def snapshots_dir() -> Path:
    return _persistent_subdir("snapshots")


def exports_dir() -> Path:
    return _persistent_subdir("exports")


def resolve_recording_path(configured: str | Path | None = None, *, repair_db: bool = False) -> Path:
    """
    Return a writable recordings folder. Falls back to data/recordings when the
    stored path came from another PC (e.g. /home/otheruser/Desktop/...).
    """
    default = recordings_dir()
    raw = str(configured or "").strip().strip("\r\n")
    if not raw:
        return default

    target = Path(raw).expanduser()
    if not target.is_absolute():
        target = (project_root() / target).resolve()

    if _dir_writable(target):
        return target

    logger.warning("Recording path not usable on this machine (%s) — using %s", target, default)
    if repair_db and raw:
        try:
            from .database import set_setting

            set_setting("recording_path", str(default))
        except Exception as exc:
            logger.debug("Could not repair recording_path in DB: %s", exc)
    return default
