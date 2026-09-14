# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs, collect_submodules

root = Path(SPECPATH)
if sys.platform.startswith("linux"):
    dist_packages = Path("/usr/lib/python3/dist-packages")
    if dist_packages.is_dir() and str(dist_packages) not in sys.path:
        sys.path.insert(0, str(dist_packages))
hidden = collect_submodules("app") + collect_submodules("sqlcipher3") + collect_submodules("webview")
hidden += [
    "sqlcipher3",
    "sqlcipher3.dbapi2",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "engineio.async_drivers",
    "multipart",
    "httpx",
    "jwt",
    "fastapi",
    "starlette",
    "pydantic",
    "webview",
    "webview.platforms.gtk",
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "gi",
    "gi.repository",
    "gi.repository.Gtk",
    "gi.repository.GLib",
    "gi.repository.Gio",
    "gi.repository.WebKit2",
]

extra_datas = []
extra_binaries = collect_dynamic_libs("sqlcipher3")
try:
    sc_datas, sc_bins, sc_hidden = collect_all("sqlcipher3")
    extra_datas += sc_datas
    extra_binaries += sc_bins
    hidden += sc_hidden
except Exception:
    pass
try:
    w_datas, w_bins, w_hidden = collect_all("webview")
    extra_datas += w_datas
    extra_binaries += w_bins
    hidden += w_hidden
except Exception:
    pass
if sys.platform.startswith("linux"):
    try:
        g_datas, g_bins, g_hidden = collect_all("gi")
        extra_datas += g_datas
        extra_binaries += g_bins
        hidden += g_hidden
    except Exception:
        pass

example_yaml = root / "go2rtc.example.yaml"
if not example_yaml.exists():
    example_yaml = root / "go2rtc.yaml.example"

datas = [
    (str(root / "static"), "static"),
    (str(root / "config.example.json"), "."),
    (str(root / ".env.example"), "."),
    (str(root / "deployment" / "assets" / "logo"), "deployment/assets/logo"),
]
if example_yaml.exists():
    datas.append((str(example_yaml), "."))

icon = root / "deployment" / "assets" / "logo" / "shibli.ico"

a = Analysis(
    [str(root / "launcher.py")],
    pathex=[str(root)],
    binaries=extra_binaries,
    datas=datas + extra_datas,
    hiddenimports=sorted(set(hidden)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[
        str(root / "deployment" / "scripts" / "pyi_rth_sqlcipher.py"),
        str(root / "deployment" / "scripts" / "pyi_rth_gi_fallback.py"),
    ],
    excludes=["tkinter", "matplotlib", "numpy", "pandas"],
    noarchive=False,
    optimize=0,
)

# CPython's sqlite3.dll may also be collected for plaintext-DB detection.
# SQLCipher must still be imported first at runtime (pyi_rth_sqlcipher + db_engine).
# If SQLCipher ships its own sqlite3.dll, keep that copy beside sqlcipher3/.
_sqlcipher_sqlite = []
_other_bins = []
for item in a.binaries:
    dest = str(item[0]).replace("\\", "/").lower()
    src = str(item[1]).replace("\\", "/").lower()
    if dest.endswith("sqlite3.dll") and "sqlcipher" in src:
        _sqlcipher_sqlite.append(item)
    else:
        _other_bins.append(item)
if _sqlcipher_sqlite:
    a.binaries = _other_bins + _sqlcipher_sqlite

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ShibliC2",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon) if icon.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="ShibliC2",
)
