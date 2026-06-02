import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

_EXPIRY_SECONDS = 1800  # 30 minutes

@dataclass(frozen=True)
class Session:
    id: str
    dir: Path
    input_path: Path
    xml_dir: Path
    created_at: float
    audio_path: Optional[Path] = None
    art_path: Optional[Path] = None
    output_path: Optional[Path] = None


_sessions: dict[str, Session] = {}
_lock = threading.Lock()


def create_session(filename: str) -> Session:
    sid = str(uuid.uuid4())
    base = Path(tempfile.gettempdir()) / "gp2psarc" / sid
    base.mkdir(parents=True, exist_ok=True)
    xml_dir = base / "xml"
    xml_dir.mkdir()
    ext = Path(filename).suffix.lower()
    session = Session(
        id=sid,
        dir=base,
        input_path=base / f"input{ext}",
        xml_dir=xml_dir,
        created_at=time.time(),
    )
    with _lock:
        _sessions[sid] = session
    return session


def get_session(sid: str) -> Session:
    with _lock:
        s = _sessions.get(sid)
    if s is None:
        raise KeyError(f"Session {sid!r} not found or expired")
    return s


def set_audio(sid: str, audio_path: Path) -> Session:
    with _lock:
        s = replace(_sessions[sid], audio_path=audio_path)
        _sessions[sid] = s
    return s


def set_art(sid: str, art_path: Path) -> Session:
    with _lock:
        s = replace(_sessions[sid], art_path=art_path)
        _sessions[sid] = s
    return s


def set_output(sid: str, output_path: Path) -> Session:
    with _lock:
        s = replace(_sessions[sid], output_path=output_path)
        _sessions[sid] = s
    return s


def delete_session(sid: str) -> None:
    with _lock:
        s = _sessions.pop(sid, None)
    if s and s.dir.exists():
        import shutil
        shutil.rmtree(s.dir, ignore_errors=True)


def _sweeper() -> None:
    while True:
        time.sleep(300)
        now = time.time()
        with _lock:
            expired = [sid for sid, s in _sessions.items()
                       if now - s.created_at > _EXPIRY_SECONDS]
        for sid in expired:
            delete_session(sid)


threading.Thread(target=_sweeper, daemon=True).start()
