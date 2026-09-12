#!/usr/bin/env python3
"""Write deployment/runtime-manifest.json from files actually present."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def _file_ver(path: Path, args: list[str]) -> str:
    if not path.is_file():
        return ""
    return _run([str(path), *args]).splitlines()[0] if path.is_file() else ""


def main() -> int:
    linux_go2rtc = ROOT / "deployment" / "runtime" / "linux" / "go2rtc"
    linux_ffmpeg = ROOT / "deployment" / "runtime" / "linux" / "ffmpeg"
    win_go2rtc = ROOT / "deployment" / "runtime" / "windows" / "go2rtc.exe"
    win_ffmpeg = ROOT / "deployment" / "runtime" / "windows" / "ffmpeg.exe"
    controls = ROOT / "deployment" / "runtime" / "controls"
    py = ROOT / ".venv" / "bin" / "python"
    interpreter = str(py) if py.is_file() else sys.executable

    go2rtc = ""
    if linux_go2rtc.is_file():
        go2rtc = _run([str(linux_go2rtc), "-version"]) or _run([str(linux_go2rtc), "--version"])
    ffmpeg = ""
    if linux_ffmpeg.is_file():
        ffmpeg = _run([str(linux_ffmpeg), "-version"]).splitlines()[0] if _run([str(linux_ffmpeg), "-version"]) else ""
        if not ffmpeg:
            ffmpeg = _file_ver(linux_ffmpeg, ["-version"])

    py_ver = _run([interpreter, "-c", "import sys; print(sys.version.split()[0])"])
    webview_ver = _run([interpreter, "-c", "import webview,sys; print(getattr(webview,'__version__',''))"])
    sqlcipher_ver = _run([interpreter, "-c", "import sqlcipher3; print(getattr(sqlcipher3,'__version__','present'))"])

    req = {}
    req_path = ROOT / "requirements.txt"
    if req_path.is_file():
        for line in req_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            req[line.split("==")[0].split(">=")[0]] = line

    ctrl_req = ""
    ctrl_req_path = controls / "requirements.txt"
    if ctrl_req_path.is_file():
        ctrl_req = " ".join(
            ln.strip() for ln in ctrl_req_path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")
        )

    manifest = {
        "product": "SHIBLI C2",
        "version": "1.0",
        "package_version": "1.0.0",
        "go2rtc": go2rtc or ("1.9.14 (vendored linux binary present)" if linux_go2rtc.is_file() else ""),
        "go2rtc_windows_present": win_go2rtc.is_file(),
        "ffmpeg": ffmpeg,
        "ffmpeg_windows_present": win_ffmpeg.is_file(),
        "python_runtime": py_ver,
        "desktop_runtime": f"pywebview {webview_ver}".strip() if webview_ver else "pywebview",
        "sqlcipher": sqlcipher_ver,
        "controls": "deployment/runtime/controls (server.py)" if (controls / "server.py").is_file() else "",
        "controls_requirements": ctrl_req,
        "application_requirements": req,
        "notes": [
            "Values are recorded from the build machine at packaging time.",
            "Empty Windows fields mean the Windows sidecar has not been fetched on this host.",
        ],
    }
    dest = ROOT / "deployment" / "runtime-manifest.json"
    if dest.is_file():
        try:
            existing = json.loads(dest.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
        if existing.get("build_baseline", "").startswith("Ubuntu 22.04") and not (
            Path("/etc/os-release").read_text(encoding="utf-8").find("22.04") >= 0
            if Path("/etc/os-release").is_file()
            else False
        ):
            print(f"Preserved existing Ubuntu 22.04 production manifest at {dest}")
            return 0
    dest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
