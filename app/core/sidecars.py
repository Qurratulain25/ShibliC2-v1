"""Start and stop SHIBLI helper processes owned by this application instance."""
from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from .paths import go2rtc_config_path, install_dir, is_frozen, logs_dir

logger = logging.getLogger(__name__)

_CHILDREN: list[subprocess.Popen] = []
_MAX_SIDECAR_LOG = 5 * 1024 * 1024


def _open_sidecar_log(path: Path):
    """Append to a sidecar log, rotating once when the file already exceeds 5 MiB."""
    try:
        if path.is_file() and path.stat().st_size >= _MAX_SIDECAR_LOG:
            rotated = path.with_name(path.name + ".1")
            if rotated.exists():
                rotated.unlink()
            path.replace(rotated)
    except OSError:
        logger.warning("Could not rotate sidecar log %s", path)
    return path.open("ab")


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def resolve_go2rtc_bin() -> Path | None:
    env = os.getenv("GO2RTC_BIN", "").strip()
    candidates = [
        Path(env) if env else None,
        install_dir() / "bin" / ("go2rtc.exe" if sys.platform == "win32" else "go2rtc"),
        install_dir() / ("go2rtc.exe" if sys.platform == "win32" else "go2rtc"),
        Path(sys.executable).resolve().parent / ("go2rtc.exe" if sys.platform == "win32" else "go2rtc"),
        Path("/usr/local/bin/go2rtc") if not is_frozen() else None,
        Path("/usr/bin/go2rtc") if not is_frozen() else None,
    ]
    for path in candidates:
        if path and path.is_file() and os.access(path, os.X_OK):
            return path
    return None


def resolve_ffmpeg_bin() -> Path | None:
    env = os.getenv("FFMPEG_BIN", "").strip() or os.getenv("FFMPEG_PATH", "").strip()
    name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    candidates = [
        Path(env) if env else None,
        install_dir() / "bin" / name,
        install_dir() / name,
        Path(sys.executable).resolve().parent / name,
    ]
    for path in candidates:
        if path and path.is_file() and os.access(path, os.X_OK):
            return path
    from shutil import which

    found = which("ffmpeg")
    return Path(found) if found else None


def resolve_controls_cmd() -> list[str] | None:
    env_bin = os.getenv("SHIBLI_CONTROLS_BIN", "").strip()
    exe_name = "ShibliControls.exe" if sys.platform == "win32" else "ShibliControls"
    if env_bin and Path(env_bin).is_file():
        return [env_bin]
    for frozen_bin in (
        install_dir() / "controls" / exe_name,
        install_dir() / "bin" / exe_name,
        Path(sys.executable).resolve().parent / exe_name,
    ):
        if frozen_bin.is_file():
            return [str(frozen_bin)]

    controls_dir = os.getenv("SHIBLI_CONTROLS_DIR", "").strip()
    if not controls_dir:
        for candidate in (
            install_dir() / "controls",
            install_dir().parent / "SHIBLI-controls",
        ):
            if (candidate / "server.py").is_file():
                controls_dir = str(candidate)
                break
    if not controls_dir:
        return None
    server = Path(controls_dir) / "server.py"
    if not server.is_file():
        return None
    for py in (
        Path(controls_dir) / "venv" / "bin" / "python3",
        Path(controls_dir) / "venv" / "Scripts" / "python.exe",
        Path(sys.executable),
    ):
        if py.is_file():
            return [str(py), str(server)]
    return None


def _controls_child_env(logs: Path) -> dict[str, str]:
    """Environment for SHIBLI-controls. Logs must not resolve under Program Files / /opt."""
    env = os.environ.copy()
    env.setdefault("PORT", os.getenv("SHIBLI_CONTROLS_PORT", "8001"))
    secret = (os.getenv("SHIBLI_JWT_SECRET") or os.getenv("JWT_SECRET") or "").strip()
    if secret:
        env["JWT_SECRET"] = secret
        env["SHIBLI_JWT_SECRET"] = secret
    env["SHIBLI_LOG_DIR"] = str(logs)
    return env


def _packaged_production() -> bool:
    if is_frozen():
        return True
    layout = (os.getenv("SHIBLI_INSTALL_LAYOUT") or "").strip().lower()
    env_name = (os.getenv("SHIBLI_ENV") or "").strip().lower()
    return layout == "system" or env_name in ("production", "prod")


def start_sidecars() -> list[subprocess.Popen]:
    """Start go2rtc / controls only if they are not already listening."""
    logs = logs_dir()
    logs.mkdir(parents=True, exist_ok=True)
    started_go2rtc = False

    if not _port_open("127.0.0.1", 1984):
        go2rtc = resolve_go2rtc_bin()
        config = go2rtc_config_path()
        if go2rtc and config.exists():
            log = _open_sidecar_log(logs / "go2rtc.log")
            child = subprocess.Popen(
                [str(go2rtc), "-config", str(config)],
                stdout=log,
                stderr=log,
                cwd=str(install_dir()),
            )
            _CHILDREN.append(child)
            started_go2rtc = True
            logger.info("Started go2rtc pid=%s", child.pid)
        else:
            logger.info("go2rtc not started (binary or config missing)")
    else:
        logger.info("go2rtc already listening — leaving existing process")

    if not _port_open("127.0.0.1", 8001):
        cmd = resolve_controls_cmd()
        if cmd:
            env = _controls_child_env(logs)
            log = _open_sidecar_log(logs / "controls.log")
            child = subprocess.Popen(
                cmd,
                stdout=log,
                stderr=log,
                cwd=str(Path(cmd[-1]).parent if cmd[-1].endswith("server.py") else install_dir()),
                env=env,
            )
            _CHILDREN.append(child)
            logger.info("Started SHIBLI-controls pid=%s", child.pid)
            deadline = time.time() + 1.0
            while time.time() < deadline and child.poll() is None:
                if _port_open("127.0.0.1", 8001):
                    break
                time.sleep(0.1)
            code = child.poll()
            if code is not None:
                logger.error(
                    "SHIBLI-controls exited immediately (code=%s). See %s",
                    code,
                    logs / "controls.log",
                )
                if _packaged_production():
                    raise RuntimeError(
                        "SHIBLI-controls failed to start. See logs/controls.log in the writable runtime."
                    )
        else:
            logger.info("SHIBLI-controls not started (not bundled and not configured)")
    else:
        logger.info("SHIBLI-controls already listening — leaving existing process")

    if started_go2rtc:
        deadline = time.time() + 8
        while time.time() < deadline and not _port_open("127.0.0.1", 1984):
            time.sleep(0.2)
        if not _port_open("127.0.0.1", 1984):
            logger.error("go2rtc did not start listening on 127.0.0.1:1984")
    return list(_CHILDREN)


def stop_sidecars() -> None:
    """Stop only processes this launcher started."""
    while _CHILDREN:
        child = _CHILDREN.pop()
        code = child.poll()
        if code is not None:
            logger.info("sidecar pid=%s already exited code=%s", getattr(child, "pid", "?"), code)
            continue
        try:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=3)
            logger.info(
                "stopped sidecar pid=%s code=%s",
                getattr(child, "pid", "?"),
                child.poll(),
            )
        except Exception:
            logger.debug("Could not stop sidecar pid=%s", getattr(child, "pid", "?"))
