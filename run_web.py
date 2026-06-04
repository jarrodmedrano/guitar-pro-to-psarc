import os
import sys
import threading
import webbrowser
from pathlib import Path

# PyInstaller with console=False sets stdout/stderr to None.
# Uvicorn's default log formatter calls .isatty() on them and crashes.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# When running as a PyInstaller bundle, fix paths before any lib imports
if hasattr(sys, "_MEIPASS"):
    base = Path(sys._MEIPASS)
    os.environ.setdefault("RSCLI_PATH", str(base / "rscli" / "RsCli.exe"))
    sys.path.insert(0, str(base / "lib"))
else:
    sys.path.insert(0, str(Path(__file__).parent / "lib"))

import uvicorn
from web.server import app

if __name__ == "__main__":
    threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8765")).start()
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
