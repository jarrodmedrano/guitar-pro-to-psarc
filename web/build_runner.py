import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from web.sessions import get_session, set_output

ProgressFn = Callable[[str, float], None]


@dataclass
class BuildParams:
    session_id: str
    title: str
    artist: str
    album: str
    year: str
    track_indices: list[int]
    arrangement_names: list[str]
    audio_offset: float = 0.0


def _safe(s: str) -> str:
    return re.sub(r'[<>:"/\\|?*\s]+', "_", s).strip("_") or "unknown"


def run_build(params: BuildParams, report: ProgressFn, result_queue) -> None:
    try:
        from gp2rs import convert_file
        from cdlc_builder import build_cdlc

        session = get_session(params.session_id)
        gp_path = str(session.input_path)

        report("Converting tracks to Rocksmith XML...", 10)
        name_map: dict[int, str] = dict(zip(params.track_indices, params.arrangement_names))
        xml_files = convert_file(
            gp_path,
            str(session.xml_dir),
            track_indices=params.track_indices,
            arrangement_names=name_map,
            audio_offset=params.audio_offset,
        )

        # Filenames are "{track_name}_{ArrangementType}.xml"
        arr_names = [Path(f).stem.rsplit("_", 1)[-1] for f in xml_files]

        report("Preparing audio...", 40)
        if session.audio_path:
            audio_path = str(session.audio_path)
        else:
            try:
                from gp2midi import gp_to_audio
                report("Rendering MIDI audio via FluidSynth...", 42)
                audio_path = gp_to_audio(gp_path, str(session.dir / "audio.ogg"))
            except Exception as e:
                raise RuntimeError(
                    "No audio file provided and MIDI rendering failed. "
                    "Drag an mp3/ogg/wav onto the audio drop zone before building. "
                    f"(FluidSynth error: {e})"
                ) from e

        output = str(session.dir / f"{_safe(params.artist)}_{_safe(params.title)}.psarc")

        def on_progress(stage: str, pct: float) -> None:
            # build_cdlc emits 0-100; compress into 50-100 to avoid bar regression
            report(stage, 50 + pct * 0.5)

        report("Building PSARC...", 50)
        build_cdlc(
            xml_paths=xml_files,
            arrangement_names=arr_names,
            audio_path=audio_path,
            title=params.title,
            artist=params.artist,
            album=params.album,
            year=params.year,
            output_path=output,
            album_art_path=str(session.art_path) if session.art_path else "",
            on_progress=on_progress,
        )

        set_output(params.session_id, Path(output))
        result_queue.put_nowait({
            "done": True,
            "progress": 100,
            "stage": "Complete!",
            "filename": Path(output).name,
            "download_url": f"/download/{params.session_id}",
        })

    except Exception as exc:
        import traceback
        traceback.print_exc()
        result_queue.put_nowait({"error": str(exc)})
