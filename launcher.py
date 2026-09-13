"""
SHIBLI C2 — cross-platform launcher.
"""
from __future__ import annotations

import atexit
import os
import signal
import socket
import sys
import threading
import time
import webbrowser


def _prepare_environment() -> tuple[str, int]:
    if getattr(sys, "frozen", False):
        os.chdir(os.path.dirname(sys.executable))
        os.environ.setdefault("SHIBLI_DESKTOP", "1")
        os.environ.setdefault("SHIBLI_INSTALL_LAYOUT", "system")
        os.environ.setdefault("SHIBLI_ENV", "production")
    else:
        root = os.path.dirname(os.path.abspath(__file__))
        if root not in sys.path:
            sys.path.insert(0, root)
    from app.core.bootstrap_env import bootstrap_environment, env_str
    from app.core.paths import project_root

    layout = os.getenv("SHIBLI_INSTALL_LAYOUT", "").strip().lower()
    env_name = os.getenv("SHIBLI_ENV", "").strip().lower()
    fail_closed = (
        getattr(sys, "frozen", False)
        or layout == "system"
        or env_name in ("production", "prod")
    )
    try:
        bootstrap_environment(project_root())
    except Exception:
        if fail_closed:
            raise
        env_str = lambda name, default="": os.getenv(name, default).strip().strip("\r\n")  # noqa: E731
    host = env_str("VMS_HOST", "127.0.0.1")
    try:
        port = int(env_str("VMS_PORT", "8080"))
    except ValueError:
        port = 8080
    return host, port


def _listening_pid(port: int) -> int | None:
    if sys.platform == "win32":
        try:
            import subprocess
            out = subprocess.check_output(
                f'netstat -ano | findstr ":{port}"',
                shell=True,
                text=True,
                stderr=subprocess.DEVNULL,
            )
            for line in out.splitlines():
                if "LISTENING" in line.upper():
                    parts = line.split()
                    if parts:
                        return int(parts[-1])
        except Exception:
            pass
        return None

    try:
        import re
        import subprocess
        out = subprocess.check_output(
            ["ss", "-H", "-ltnp", f"sport = :{port}"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        for line in out.splitlines():
            match = re.search(r"pid=(\d+)", line)
            if match:
                return int(match.group(1))
    except Exception:
        pass

    try:
        import subprocess
        out = subprocess.check_output(
            ["lsof", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        pids = out.strip().split()
        if pids:
            return int(pids[0])
    except Exception:
        pass
    return None


def _port_in_use(host: str, port: int) -> tuple[bool, int | None]:
    pid = _listening_pid(port)
    if pid is not None:
        return True, pid

    bind_host = host if host not in ("0.0.0.0", "::") else "127.0.0.1"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((bind_host, port))
            return False, None
    except OSError:
        return True, None


def _icon_path():
    from pathlib import Path
    from app.core.paths import bundle_dir, install_dir

    for path in (
        install_dir() / "share" / "icons" / "shibli.png",
        install_dir() / "shibli.ico",
        bundle_dir() / "deployment" / "assets" / "logo" / "shibli.ico",
        bundle_dir() / "static" / "branding" / "logo.png",
    ):
        if path.is_file():
            return str(path)
    return None


def _fatal(message: str, code: int = 1) -> None:
    print(message, flush=True)
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, "SHIBLI C2", 0x10)
        except Exception:
            pass
    raise SystemExit(code)


def _wait_for_listen(host: str, port: int, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.4):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _ensure_backend_listening(host: str, port: int, url: str, server_thread: threading.Thread | None = None) -> None:
    if _wait_for_listen(host, port):
        return
    from app.core.sidecars import stop_sidecars

    stop_sidecars()
    extra = ""
    if server_thread is not None and not server_thread.is_alive():
        extra = " The backend process exited during startup."
    _fatal(f"ERROR: SHIBLI C2 backend did not start listening on {url}.{extra}")


def main() -> None:
    host, port = _prepare_environment()
    from app.core.paths import go2rtc_config_path
    from app.core.sidecars import start_sidecars, stop_sidecars

    go2rtc_config_path()
    in_use, pid = _port_in_use(host, port)
    if in_use:
        pid_msg = f" (PID {pid})" if pid else ""
        _fatal(
            f"ERROR: Port {port} is already in use{pid_msg}. "
            "Stop the existing instance, then start SHIBLI C2 again."
        )

    display_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    url = f"http://{display_host}:{port}"

    frozen = getattr(sys, "frozen", False)
    no_browser = os.getenv("SHIBLI_NO_BROWSER", "").lower() in ("1", "true", "yes")
    want_desktop = os.getenv("SHIBLI_DESKTOP", "1" if frozen else "").lower() in ("1", "true", "yes")

    import uvicorn
    from app.core.logging_setup import configure_logging
    from app.core.version import APP_VERSION_DISPLAY, PRODUCT_NAME
    from app.main import app

    configure_logging()
    start_sidecars()
    atexit.register(stop_sidecars)

    def _on_signal(signum, _frame) -> None:
        stop_sidecars()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    print(f"{PRODUCT_NAME} {APP_VERSION_DISPLAY} binding to {host}:{port} …")

    if want_desktop and not no_browser:
        def run_server() -> None:
            uvicorn.run(app, host=host, port=port, log_level="warning")

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        _ensure_backend_listening(display_host, port, url, server_thread)
        try:
            import inspect
            import webview

            kwargs = {
                "title": PRODUCT_NAME,
                "url": url,
                "width": 1440,
                "height": 900,
                "min_size": (1100, 700),
            }
            icon = _icon_path()
            params = inspect.signature(webview.create_window).parameters
            if icon and "icon" in params:
                kwargs["icon"] = icon
            webview.create_window(**kwargs)
            start_kwargs = {}
            if sys.platform.startswith("linux") and "gui" in inspect.signature(webview.start).parameters:
                start_kwargs["gui"] = "gtk"
            webview.start(**start_kwargs)
            stop_sidecars()
            return
        except ImportError:
            if frozen:
                stop_sidecars()
                _fatal("ERROR: Desktop window runtime (pywebview) is missing from this build.")
            print("pywebview not installed — development browser fallback.", flush=True)

    if not no_browser and not frozen:
        def open_browser() -> None:
            time.sleep(1.5)
            webbrowser.open(url)

        threading.Thread(target=open_browser, daemon=True).start()

    try:
        uvicorn.run(app, host=host, port=port, log_level="warning")
    finally:
        stop_sidecars()


if __name__ == "__main__":
    main()
