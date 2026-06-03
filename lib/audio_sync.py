from pathlib import Path
import xml.etree.ElementTree as ET


def _read_gp_bpm(gp_path: str) -> float:
    ext = Path(gp_path).suffix.lower()
    try:
        if ext in (".gpx", ".gp"):
            import zipfile
            with zipfile.ZipFile(gp_path) as z:
                gpif_name = next(
                    (n for n in z.namelist() if n.lower().endswith("score.gpif")),
                    None,
                )
                if gpif_name is None:
                    return 120.0
                with z.open(gpif_name) as f:
                    root = ET.parse(f).getroot()
            mt = root.find("MasterTrack")
            if mt is not None:
                for auto in mt.findall(".//Automations/*"):
                    if auto.findtext("Type") == "Tempo":
                        raw = (auto.findtext("Value") or "").strip()
                        try:
                            return float(raw.split()[0])
                        except (ValueError, IndexError):
                            pass
        else:
            import guitarpro
            song = guitarpro.parse(gp_path)
            return float(song.tempo)
    except Exception:
        pass
    return 120.0


def detect_offset(audio_path: str, gp_path: str) -> float:
    """Return estimated audio_offset in seconds (time into audio where chart beat-1 falls).

    Uses librosa beat tracking seeded with the GP file's initial BPM. Falls back
    to 0.0 on any error (missing librosa, unreadable file, no beats detected).
    """
    try:
        import librosa  # type: ignore[import]

        bpm = _read_gp_bpm(gp_path)
        y, sr = librosa.load(audio_path, sr=22050, mono=True, duration=120.0)
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        _, beat_frames = librosa.beat.beat_track(
            onset_envelope=onset_env,
            sr=sr,
            start_bpm=bpm,
            trim=True,
        )
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        if len(beat_times) == 0:
            return 0.0
        return round(float(beat_times[0]), 3)
    except Exception:
        return 0.0
