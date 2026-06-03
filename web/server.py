import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from web.build_runner import BuildParams, run_build
from web.sessions import create_session, delete_session, get_session, set_art, set_audio

_STATIC = Path(__file__).parent / "static"
_GP_EXTENSIONS    = {".gp", ".gp3", ".gp4", ".gp5", ".gpx"}
_AUDIO_EXTENSIONS = {".mp3", ".ogg", ".wav", ".flac"}
_ART_EXTENSIONS   = {".jpg", ".jpeg", ".png", ".webp", ".dds"}
_MAX_GP_BYTES    = 20 * 1024 * 1024
_MAX_AUDIO_BYTES = 75 * 1024 * 1024
_MAX_ART_BYTES   =  5 * 1024 * 1024

app = FastAPI(title="gp-to-psarc")
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(_STATIC / "index.html"))


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _GP_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Expected: {', '.join(sorted(_GP_EXTENSIONS))}")

    data = await file.read()
    if len(data) > _MAX_GP_BYTES:
        raise HTTPException(413, "File too large (max 20 MB)")

    session = create_session(file.filename or f"input{ext}")
    session.input_path.write_bytes(data)

    import gp2rs
    title, artist, album = _extract_metadata(str(session.input_path))
    track_indices, name_map = gp2rs.auto_select_tracks(str(session.input_path))
    all_tracks = gp2rs.list_tracks(str(session.input_path))

    tracks = [
        {
            "index": t["index"],
            "name": t["name"],
            "strings": t["strings"],
            "notes": t["notes"],
            "is_drums": t.get("is_drums", False),
            # Drums have no Rocksmith arrangement type — exclude by default
            "selected": t["index"] in track_indices and not t.get("is_drums", False),
            "arrangement": name_map.get(t["index"], "Lead"),
        }
        for t in all_tracks
        if t["notes"] > 0
    ]

    return {
        "session_id": session.id,
        "title": title or Path(file.filename or "").stem,
        "artist": artist or "Unknown Artist",
        "album": album or "",
        "tracks": tracks,
    }


@app.post("/upload-audio")
async def upload_audio(session_id: str = Form(...), file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _AUDIO_EXTENSIONS:
        raise HTTPException(400, f"Unsupported audio type '{ext}'")

    data = await file.read()
    if len(data) > _MAX_AUDIO_BYTES:
        raise HTTPException(413, "Audio file too large (max 75 MB)")

    try:
        session = get_session(session_id)
    except KeyError:
        raise HTTPException(404, "Session expired — please drop the Guitar Pro file again to start a new session")

    audio_path = session.dir / f"audio{ext}"
    audio_path.write_bytes(data)
    set_audio(session_id, audio_path)
    return {"ok": True, "meta": _audio_metadata(audio_path)}


@app.post("/upload-art")
async def upload_art(session_id: str = Form(...), file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ART_EXTENSIONS:
        raise HTTPException(400, f"Unsupported image type '{ext}'. Expected: jpg, png, webp, dds")

    data = await file.read()
    if len(data) > _MAX_ART_BYTES:
        raise HTTPException(413, "Image too large (max 5 MB)")

    try:
        session = get_session(session_id)
    except KeyError:
        raise HTTPException(404, "Session expired — please drop the Guitar Pro file again to start a new session")

    art_path = session.dir / f"art{ext}"
    art_path.write_bytes(data)
    set_art(session_id, art_path)
    return {"ok": True}


@app.post("/detect-offset")
async def detect_offset(session_id: str = Form(...)):
    try:
        session = get_session(session_id)
    except KeyError:
        raise HTTPException(404, "Session expired")

    if not session.audio_path or not session.audio_path.exists():
        return {"offset": 0.0}

    import audio_sync
    offset = audio_sync.detect_offset(str(session.audio_path), str(session.input_path))
    return {"offset": offset}


@app.websocket("/ws/build")
async def ws_build(
    ws: WebSocket,
    session_id: str,
    title: str = "",
    artist: str = "",
    album: str = "",
    year: str = "",
    tracks: str = "",
    arrangements: str = "",
    audio_offset: float = 0.0,
):
    await ws.accept()

    track_indices = [int(x) for x in tracks.split(",") if x.strip()]
    arrangement_names = [x.strip() for x in arrangements.split(",") if x.strip()]

    params = BuildParams(
        session_id=session_id,
        title=title,
        artist=artist,
        album=album,
        year=year,
        track_indices=track_indices,
        arrangement_names=arrangement_names,
        audio_offset=audio_offset,
    )

    q: asyncio.Queue = asyncio.Queue()

    def report(stage: str, pct: float) -> None:
        q.put_nowait({"stage": stage, "progress": round(pct)})

    loop = asyncio.get_event_loop()
    task = loop.run_in_executor(None, run_build, params, report, q)

    try:
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=1.0)
                await ws.send_json(msg)
                if msg.get("done") or msg.get("error"):
                    break
            except asyncio.TimeoutError:
                if task.done():
                    break
    except WebSocketDisconnect:
        pass

    await ws.close()


@app.get("/download/{session_id}")
async def download(session_id: str, background_tasks: BackgroundTasks):
    try:
        session = get_session(session_id)
    except KeyError:
        raise HTTPException(404, "File not found or expired")

    if not session.output_path or not session.output_path.exists():
        raise HTTPException(404, "Build output not ready")

    background_tasks.add_task(delete_session, session_id)
    return FileResponse(
        str(session.output_path),
        media_type="application/octet-stream",
        filename=session.output_path.name,
    )


def _audio_metadata(audio_path: Path) -> dict:
    """Extract title/artist/album/year from audio file tags via mutagen."""
    try:
        from mutagen import File as MutagenFile
        tags = MutagenFile(audio_path, easy=True)
        if tags is None:
            return {}
        def first(key: str) -> str:
            vals = tags.get(key) or []
            return str(vals[0]).strip() if vals else ""
        return {
            "title":  first("title"),
            "artist": first("artist"),
            "album":  first("album"),
            "year":   first("date")[:4],   # date tag is often "2011-05-10"
        }
    except Exception:
        return {}


def _extract_metadata(gp_path: str) -> tuple[str, str, str]:
    ext = Path(gp_path).suffix.lower()
    try:
        if ext in (".gpx", ".gp"):
            from gp2rs_gpx import _load_gpif
            root = _load_gpif(gp_path)
            score = root.find("Score")
            if score is None:
                return "", "", ""
            return (
                (score.findtext("Title") or "").strip(),
                (score.findtext("Artist") or "").strip(),
                (score.findtext("Album") or "").strip(),
            )
        else:
            import guitarpro
            song = guitarpro.parse(gp_path)
            return (
                (song.title or "").strip(),
                (song.artist or "").strip(),
                (song.album or "").strip(),
            )
    except Exception:
        return "", "", ""
