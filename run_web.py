import os
import sys
import threading
import webbrowser
from pathlib import Path

# When running as a PyInstaller bundle, fix paths before any lib imports
if hasattr(sys, "_MEIPASS"):
    base = Path(sys._MEIPASS)
    os.environ.setdefault("RSCLI_PATH", str(base / "rscli" / "RsCli.exe"))
    sys.path.insert(0, str(base / "lib"))
else:
    sys.path.insert(0, str(Path(__file__).parent / "lib"))

import uvicorn

if __name__ == "__main__":
    threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8765")).start()
    uvicorn.run("web.server:app", host="127.0.0.1", port=8765, log_level="warning")
