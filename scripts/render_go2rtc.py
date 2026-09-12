#!/usr/bin/env python3
"""Render go2rtc.yaml from enabled camera records. Does not log RTSP URLs."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.bootstrap_env import bootstrap_environment  # noqa: E402
from app.core.database import list_local_cameras  # noqa: E402
from app.core.paths import project_root  # noqa: E402
from app.services.go2rtc import cameras_to_stream_map, render_config_text  # noqa: E402


def main() -> int:
    bootstrap_environment(project_root())
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "go2rtc.yaml"
    try:
        cameras = list_local_cameras()
    except Exception:
        print("go2rtc render skipped: camera database not readable")
        return 0
    streams = cameras_to_stream_map(cameras)
    if not streams:
        if dest.exists():
            print("go2rtc render skipped: no enabled Day/Thermal RTSP URLs; keeping existing yaml")
            return 0
        dest.write_text(render_config_text([]), encoding="utf-8")
        print("go2rtc yaml skeleton written (no camera streams yet)")
        return 0
    dest.write_text(render_config_text(cameras), encoding="utf-8")
    print(f"go2rtc yaml rendered with streams: {', '.join(sorted(streams))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
