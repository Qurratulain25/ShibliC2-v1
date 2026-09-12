"""Allow the frozen desktop window to use the OS PyGObject if needed."""
import sys
from pathlib import Path

try:
    import gi  # noqa: F401
except Exception:
    extra = Path("/usr/lib/python3/dist-packages")
    if extra.is_dir() and str(extra) not in sys.path:
        sys.path.insert(0, str(extra))
