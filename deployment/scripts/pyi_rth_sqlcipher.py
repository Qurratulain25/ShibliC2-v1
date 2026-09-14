"""Windows frozen: expose SQLCipher's directory to the DLL search path before imports."""
import os
import sys
from pathlib import Path

if os.name == "nt" and getattr(sys, "frozen", False):
    meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    exe_dir = Path(sys.executable).resolve().parent
    folders = [
        meipass / "sqlcipher3",
        meipass,
        exe_dir / "_internal" / "sqlcipher3",
        exe_dir / "_internal",
        exe_dir,
    ]
    existing = [str(folder) for folder in folders if folder.is_dir()]
    if existing:
        os.environ["PATH"] = os.pathsep.join(existing) + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        for folder in existing:
            try:
                os.add_dll_directory(folder)
            except OSError:
                pass
