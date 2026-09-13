"""Windows frozen: expose SQLCipher's directory to the DLL search path before imports."""
import os
import sys
from pathlib import Path

if os.name == "nt" and getattr(sys, "frozen", False) and hasattr(os, "add_dll_directory"):
    meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    exe_dir = Path(sys.executable).resolve().parent
    for folder in (
        meipass / "sqlcipher3",
        meipass,
        exe_dir / "_internal" / "sqlcipher3",
        exe_dir / "_internal",
        exe_dir,
    ):
        if folder.is_dir():
            try:
                os.add_dll_directory(str(folder))
            except OSError:
                pass
