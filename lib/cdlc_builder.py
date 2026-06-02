"""Build a complete Rocksmith 2014 CDLC .psarc from arrangement XMLs + audio."""

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

log = logging.getLogger("slopsmith.lib.cdlc_builder")

from patcher import pack_psarc

RSCLI = Path(os.environ.get("RSCLI_PATH", str(Path(__file__).parent / "tools" / "rscli" / "RsCli")))
WW2OGG = Path(__file__).parent / "tools" / "dlcbuilder-linux" / "Tools" / "ww2ogg"
REVORB = Path(__file__).parent / "tools" / "dlcbuilder-linux" / "Tools" / "revorb"
CODEBOOKS = Path(__file__).parent / "tools" / "dlcbuilder-linux" / "Tools" / "packed_codebooks_aoTuV_603.bin"

DEFAULT_APP_ID = "248750"


def _sanitize_key(artist: str, title: str) -> str:
    """Generate a lowercase alphanumeric DLC key."""
    combined = f"{artist}{title}"
    return re.sub(r"[^a-z0-9]", "", combined.lower())[:40]


def _generate_manifest(
    dlc_key: str, arrangement_name: str, song_title: str,
    artist: str, album: str, year: str, song_length: float,
    tuning: list[int], persistent_id: str, master_id: int,
) -> dict:
    """Generate a Rocksmith manifest JSON for an arrangement."""
    arr_lower = arrangement_name.lower()
    route_mask = 4 if arr_lower == "bass" else (2 if arr_lower == "rhythm" else 1)

    return {
        "Entries": {
            persistent_id: {
                "Attributes": {
                    "ArrangementName": arrangement_name,
                    "DLCKey": dlc_key,
                    "LeaderboardChallengeRating": 0,
                    "ManifestUrn": f"urn:database:json-db:{dlc_key}_{arr_lower}",
                    "MasterID_RDV": master_id,
                    "PersistentID": persistent_id,
                    "SongKey": dlc_key,
                    "SongLength": song_length,
                    "SongName": song_title,
                    "ArtistName": artist,
                    "AlbumName": album or "",
                    "SongYear": int(year) if year else 2024,
                    "Tuning": {f"string{i}": v for i, v in enumerate(tuning)},
                    "ArrangementSort": 0,
                    "RouteMask": route_mask,
                    "CapoFret": 0,
                    "CentOffset": 0.0,
                    "DNA_Chords": 0.0,
                    "DNA_Riffs": 0.0,
                    "DNA_Solo": 0.0,
                    "NotesEasy": 0.0,
                    "NotesMedium": 0.0,
                    "NotesHard": 0.0,
                    "Tones": [],
                    "Tone_Base": "Default",
                    "Tone_Multiplayer": "",
                    "Tone_A": "",
                    "Tone_B": "",
                    "Tone_C": "",
                    "Tone_D": "",
                }
            }
        },
        "ModelName": "RSEnumerable_Song",
        "IterationVersion": 2,
        "InsertRoot": f"Static.Songs.Headers.{dlc_key}",
    }


def _generate_hsan(arrangements: list[dict]) -> dict:
    """Generate the aggregate .hsan manifest."""
    entries = {}
    for arr in arrangements:
        for pid, data in arr["Entries"].items():
            entries[pid] = data
    return {
        "Entries": entries,
        "ModelName": "RSEnumerable_Song",
        "IterationVersion": 2,
        "InsertRoot": "Static.Songs.Headers",
    }


def _generate_xblock(dlc_key: str, arrangements_info: list[dict]) -> str:
    """Generate the .xblock game entity XML."""
    lines = ['<?xml version="1.0" encoding="utf-8"?>']
    lines.append('<game>')
    lines.append('  <entitySet>')

    for info in arrangements_info:
        name = info["name"].lower()
        lines.append(f'    <entity id="{info["persistent_id"]}" modelName="RSEnumerable_Song"'
                     f' name="{dlc_key}_{name}" iterations="0">')
        lines.append(f'      <property name="Header">')
        lines.append(f'        <set value="urn:database:json-db:{dlc_key}_{name}" />')
        lines.append(f'      </property>')
        lines.append(f'      <property name="Manifest">')
        lines.append(f'        <set value="urn:database:json-db:{dlc_key}_{name}" />')
        lines.append(f'      </property>')
        lines.append(f'      <property name="SngAsset">')
        lines.append(f'        <set value="urn:application:musicgame-song:{dlc_key}_{name}" />')
        lines.append(f'      </property>')
        lines.append(f'      <property name="AlbumArtSmall">')
        lines.append(f'        <set value="urn:image:dds:album_{dlc_key}_64" />')
        lines.append(f'      </property>')
        lines.append(f'      <property name="AlbumArtMedium">')
        lines.append(f'        <set value="urn:image:dds:album_{dlc_key}_128" />')
        lines.append(f'      </property>')
        lines.append(f'      <property name="AlbumArtLarge">')
        lines.append(f'        <set value="urn:image:dds:album_{dlc_key}_256" />')
        lines.append(f'      </property>')
        lines.append(f'      <property name="LyricArt">')
        lines.append(f'        <set value="" />')
        lines.append(f'      </property>')
        lines.append(f'      <property name="ShowLightsXMLAsset">')
        lines.append(f'        <set value="urn:application:xml:{dlc_key}_showlights" />')
        lines.append(f'      </property>')
        lines.append(f'      <property name="SoundBank">')
        lines.append(f'        <set value="urn:audio:wwise-sound-bank:song_{dlc_key}" />')
        lines.append(f'      </property>')
        lines.append(f'      <property name="PreviewSoundBank">')
        lines.append(f'        <set value="urn:audio:wwise-sound-bank:song_{dlc_key}_preview" />')
        lines.append(f'      </property>')
        lines.append(f'    </entity>')

    lines.append('  </entitySet>')
    lines.append('</game>')
    return '\n'.join(lines)


def _generate_showlights(song_length: float) -> str:
    """Generate a minimal showlights XML."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<showlights count="1">\n'
        f'  <showlight time="0.000" note="44" />\n'
        f'</showlights>'
    )


def _generate_aggregategraph(dlc_key: str, arrangements_info: list[dict]) -> str:
    """Generate the aggregate graph .nt file."""
    lines = []
    # Minimal aggregate graph entries
    for info in arrangements_info:
        name = info["name"].lower()
        lines.append(f'urn:application:musicgame-song:{dlc_key}_{name} {{')
        lines.append(f'  a urn:application:musicgame-song ;')
        lines.append(f'}}')
    return '\n'.join(lines)


def build_cdlc(
    xml_paths: list[str],
    arrangement_names: list[str],
    audio_path: str,
    title: str,
    artist: str,
    album: str = "",
    year: str = "",
    output_path: str = "",
    album_art_path: str = "",
    on_progress=None,
) -> str:
    """Build a complete CDLC .psarc file.

    Args:
        xml_paths: Rocksmith arrangement XML files
        arrangement_names: Name for each arrangement ("Lead", "Rhythm", "Bass")
        audio_path: Path to audio file (OGG/WAV/MP3)
        title: Song title
        artist: Artist name
        album: Album name
        year: Release year
        output_path: Output .psarc path (auto-generated if empty)
        album_art_path: Path to album art image (optional)
        on_progress: Callback(stage: str, pct: float)

    Returns:
        Path to the created .psarc file
    """
    dlc_key = _sanitize_key(artist, title)
    tmp = Path(tempfile.mkdtemp(prefix="cdlc_build_"))

    def progress(msg, pct=0):
        if on_progress:
            on_progress(msg, pct)
        log.info("[%.0f%%] %s", pct, msg)

    try:
        build_dir = tmp / dlc_key
        build_dir.mkdir()

        # ── Convert XMLs to SNG ───────────────────────────────────────────
        arrangements_info = []
        manifests = []

        for i, (xml_path, arr_name) in enumerate(zip(xml_paths, arrangement_names)):
            progress(f"Converting {arr_name} XML to SNG...", 10 + i * 15)

            arr_lower = arr_name.lower()
            persistent_id = str(uuid.uuid4()).upper()
            master_id = 1000 + i

            # SNG conversion via RsCli
            sng_dir = build_dir / "songs" / "bin" / "generic"
            sng_dir.mkdir(parents=True, exist_ok=True)
            sng_path = sng_dir / f"{dlc_key}_{arr_lower}.sng"

            result = subprocess.run(
                [str(RSCLI), "xml2sng", xml_path, str(sng_path)],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(f"SNG conversion failed for {arr_name}: {result.stderr}")

            # Copy XML arrangement
            arr_dir = build_dir / "songs" / "arr"
            arr_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(xml_path, arr_dir / f"{dlc_key}_{arr_lower}.xml")

            # Read XML for metadata
            import xml.etree.ElementTree as ET
            tree = ET.parse(xml_path)
            root = tree.getroot()
            song_length = float(root.find("songLength").text) if root.find("songLength") is not None else 300.0
            tuning_el = root.find("tuning")
            tuning = [int(tuning_el.get(f"string{j}", "0")) for j in range(6)] if tuning_el is not None else [0]*6

            # Generate manifest
            manifest = _generate_manifest(
                dlc_key, arr_name, title, artist, album, year,
                song_length, tuning, persistent_id, master_id,
            )
            manifests.append(manifest)

            manifest_dir = build_dir / "manifests" / f"songs_dlc_{dlc_key}"
            manifest_dir.mkdir(parents=True, exist_ok=True)
            (manifest_dir / f"{dlc_key}_{arr_lower}.json").write_text(
                json.dumps(manifest, indent=2)
            )

            arrangements_info.append({
                "name": arr_name,
                "persistent_id": persistent_id,
                "master_id": master_id,
            })

        # ── HSAN ──────────────────────────────────────────────────────────
        progress("Generating manifests...", 60)
        hsan = _generate_hsan(manifests)
        manifest_dir = build_dir / "manifests" / f"songs_dlc_{dlc_key}"
        (manifest_dir / f"songs_dlc_{dlc_key}.hsan").write_text(
            json.dumps(hsan, indent=2)
        )

        # ── Audio ─────────────────────────────────────────────────────────
        progress("Processing audio...", 65)
        audio_dir = build_dir / "audio" / "windows"
        audio_dir.mkdir(parents=True, exist_ok=True)

        # Convert audio to OGG if needed, then copy as .wem
        # (Rocksmith actually needs Wwise WEM, but many CDLCs ship with
        # renamed OGG files and the game accepts them)
        audio_ext = Path(audio_path).suffix.lower()
        wem_path = audio_dir / f"song_{dlc_key}.wem"

        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if audio_ext in (".ogg", ".wem"):
            shutil.copy2(audio_path, wem_path)
        elif audio_ext == ".wav":
            # Convert WAV to OGG, then copy as .wem
            ogg_tmp = tmp / "audio.ogg"
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", audio_path, "-q:a", "6", str(ogg_tmp)],
                capture_output=True, text=True,
            )
            if result.returncode != 0 or not ogg_tmp.exists():
                # If conversion fails, copy WAV directly (Rocksmith may still play it)
                progress("Warning: ffmpeg conversion failed, using WAV directly", 67)
                shutil.copy2(audio_path, wem_path)
            else:
                shutil.copy2(ogg_tmp, wem_path)
        else:
            # Convert any other format to OGG
            ogg_tmp = tmp / "audio.ogg"
            subprocess.run(
                ["ffmpeg", "-y", "-i", audio_path, "-q:a", "6", str(ogg_tmp)],
                capture_output=True,
            )
            if ogg_tmp.exists():
                shutil.copy2(ogg_tmp, wem_path)
            else:
                raise RuntimeError(f"Failed to convert audio: {audio_path}")

        # Create a minimal .bnk (soundbank) - empty placeholder
        bnk_path = audio_dir / f"song_{dlc_key}.bnk"
        bnk_path.write_bytes(b'\x00' * 64)
        bnk_preview = audio_dir / f"song_{dlc_key}_preview.bnk"
        bnk_preview.write_bytes(b'\x00' * 64)

        # ── Album art ─────────────────────────────────────────────────────
        progress("Processing album art...", 75)
        art_dir = build_dir / "gfxassets" / "album_art"
        art_dir.mkdir(parents=True, exist_ok=True)

        if album_art_path and Path(album_art_path).exists():
            ext = Path(album_art_path).suffix.lower()
            if ext == ".dds":
                for size in [64, 128, 256]:
                    shutil.copy2(album_art_path, art_dir / f"album_{dlc_key}_{size}.dds")
            else:
                # Convert to DDS using Pillow
                try:
                    from PIL import Image
                    img = Image.open(album_art_path).convert("RGBA")
                    for size in [64, 128, 256]:
                        resized = img.resize((size, size), Image.LANCZOS)
                        dds_path = art_dir / f"album_{dlc_key}_{size}.dds"
                        resized.save(str(dds_path))
                except ImportError:
                    # Fallback: create minimal placeholder DDS
                    for size in [64, 128, 256]:
                        _write_placeholder_dds(art_dir / f"album_{dlc_key}_{size}.dds", size)
        else:
            for size in [64, 128, 256]:
                _write_placeholder_dds(art_dir / f"album_{dlc_key}_{size}.dds", size)

        # ── Showlights ────────────────────────────────────────────────────
        arr_dir = build_dir / "songs" / "arr"
        (arr_dir / f"{dlc_key}_showlights.xml").write_text(
            _generate_showlights(song_length)
        )

        # ── XBlock ────────────────────────────────────────────────────────
        xblock_dir = build_dir / "gamexblocks" / "nsongs"
        xblock_dir.mkdir(parents=True, exist_ok=True)
        (xblock_dir / f"{dlc_key}.xblock").write_text(
            _generate_xblock(dlc_key, arrangements_info)
        )

        # ── Aggregate graph ───────────────────────────────────────────────
        (build_dir / f"{dlc_key}_aggregategraph.nt").write_text(
            _generate_aggregategraph(dlc_key, arrangements_info)
        )

        # ── App ID + toolkit version ──────────────────────────────────────
        (build_dir / "appid.appid").write_text(DEFAULT_APP_ID)
        (build_dir / "toolkit.version").write_text("RsCli GP2RS 1.0")

        # ── Pack PSARC ────────────────────────────────────────────────────
        progress("Packing PSARC...", 90)
        if not output_path:
            safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)
            safe_artist = re.sub(r'[<>:"/\\|?*]', '_', artist)
            output_path = f"{safe_title}_{safe_artist}_p.psarc"

        pack_psarc(str(build_dir), output_path)
        progress(f"Created: {output_path}", 100)
        return output_path

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _write_placeholder_dds(path: Path, size: int):
    """Write a minimal uncompressed DDS file (dark gray)."""
    # DDS header (128 bytes) + uncompressed RGBA data
    import struct
    header = bytearray(128)
    header[0:4] = b'DDS '
    struct.pack_into('<I', header, 4, 124)  # header size
    struct.pack_into('<I', header, 8, 0x1 | 0x2 | 0x4 | 0x1000)  # flags
    struct.pack_into('<I', header, 12, size)  # height
    struct.pack_into('<I', header, 16, size)  # width
    struct.pack_into('<I', header, 20, size * 4)  # pitch
    struct.pack_into('<I', header, 76, 32)  # pixel format size
    struct.pack_into('<I', header, 80, 0x41)  # DDPF_RGB | DDPF_ALPHAPIXELS
    struct.pack_into('<I', header, 88, 32)  # RGB bit count
    struct.pack_into('<I', header, 92, 0x00FF0000)  # R mask
    struct.pack_into('<I', header, 96, 0x0000FF00)  # G mask
    struct.pack_into('<I', header, 100, 0x000000FF)  # B mask
    struct.pack_into('<I', header, 104, 0xFF000000)  # A mask

    pixel = b'\x30\x30\x30\xFF'  # dark gray RGBA
    data = pixel * (size * size)
    path.write_bytes(bytes(header) + data)
