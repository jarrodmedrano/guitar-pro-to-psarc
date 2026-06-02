#!/usr/bin/env python3
"""Convert Guitar Pro files to Rocksmith 2014 .psarc

Usage:
    python gp_to_psarc.py song.gp5
    python gp_to_psarc.py song.gp5 --output song.psarc
    python gp_to_psarc.py song.gp5 --audio backing.mp3
    python gp_to_psarc.py song.gp5 --title "My Song" --artist "Me" --audio backing.mp3

Requires:
    pip install pyguitarpro pycryptodome midiutil Pillow
    RsCli binary at lib/tools/rscli/RsCli.exe (or set RSCLI_PATH env var)
    ffmpeg on PATH
    fluidsynth on PATH + a soundfont (only needed without --audio)
"""

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))


def _extract_metadata(gp_path: str) -> tuple[str, str, str]:
    ext = Path(gp_path).suffix.lower()
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


def convert(
    gp_path: str,
    output: str | None,
    audio: str | None,
    title: str | None,
    artist: str | None,
    album: str | None,
    year: str | None,
) -> str:
    from gp2rs import convert_file, auto_select_tracks

    file_title, file_artist, file_album = _extract_metadata(gp_path)
    title = title or file_title or Path(gp_path).stem
    artist = artist or file_artist or "Unknown Artist"
    album = album or file_album or ""
    year = year or ""

    if output is None:
        output = str(Path(gp_path).with_suffix(".psarc"))

    track_indices, arrangement_names = auto_select_tracks(gp_path)
    if not track_indices:
        print("No convertible tracks found in this file.", file=sys.stderr)
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        xml_dir = tmp_path / "xml"
        xml_dir.mkdir()

        print(f"Converting {len(track_indices)} track(s) to Rocksmith XML...")
        xml_files = convert_file(
            gp_path, str(xml_dir),
            track_indices=track_indices,
            arrangement_names=arrangement_names,
        )

        # Filenames are "{track_name}_{ArrangementType}.xml"; extract the type.
        arr_names = [Path(f).stem.rsplit("_", 1)[-1] for f in xml_files]

        if audio:
            audio_path = audio
            print(f"Using provided audio: {audio_path}")
        else:
            from gp2midi import gp_to_audio
            print("Rendering MIDI audio via FluidSynth...")
            audio_path = gp_to_audio(gp_path, str(tmp_path / "audio.ogg"))

        from cdlc_builder import build_cdlc

        def on_progress(stage: str, pct: float) -> None:
            print(f"  [{pct:3.0f}%] {stage}")

        print(f'Building "{title}" by {artist}...')
        result = build_cdlc(
            xml_paths=xml_files,
            arrangement_names=arr_names,
            audio_path=audio_path,
            title=title,
            artist=artist,
            album=album,
            year=year,
            output_path=output,
            on_progress=on_progress,
        )

    print(f"\nCreated: {result}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a Guitar Pro file to a Rocksmith 2014 .psarc",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input", help="Guitar Pro file (.gp, .gp5, .gpx, etc.)")
    parser.add_argument("-o", "--output", help="Output .psarc path (default: input filename with .psarc extension)")
    parser.add_argument("--audio", help="Audio file to embed (mp3/ogg/wav). If omitted, MIDI audio is rendered via FluidSynth.")
    parser.add_argument("--title", help="Override song title (default: read from file)")
    parser.add_argument("--artist", help="Override artist name (default: read from file)")
    parser.add_argument("--album", help="Override album name (default: read from file)")
    parser.add_argument("--year", help="Override release year")
    args = parser.parse_args()

    try:
        convert(args.input, args.output, args.audio, args.title, args.artist, args.album, args.year)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
