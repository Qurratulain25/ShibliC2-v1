# -*- mode: python ; coding: utf-8 -*-
# Built from a sanitized copy of SHIBLI-controls (no venv, .env, or live data).
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

root = Path(os.environ.get("SHIBLI_CONTROLS_SRC") or SPECPATH)

hidden = collect_submodules("routes") + collect_submodules("services") + collect_submodules("controllers")
hidden += collect_submodules("middleware") + collect_submodules("utils")
hidden += [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "jwt",
    "dotenv",
    "serial",
    "onvif",
    "zeep",
    "lxml",
    "cgi",
    "legacy_cgi",
]

datas = []
binaries = []
for pkg in ("onvif", "zeep", "lxml", "uvicorn"):
    try:
        pkg_datas, pkg_bins, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_bins
        hidden += pkg_hidden
    except Exception:
        pass

a = Analysis(
    [str(root / "server.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hidden)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ShibliControls",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ShibliControls")
