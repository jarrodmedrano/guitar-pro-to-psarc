# gp-to-psarc

Converts Guitar Pro files (`.gp`, `.gp3`, `.gp4`, `.gp5`, `.gpx`) to Rocksmith 2014 Custom DLC `.psarc` files.

Includes a drag-and-drop web UI and a command-line interface.

---

## Requirements

| Tool | Purpose | Notes |
|---|---|---|
| [Python 3.10+](https://www.python.org/downloads/) | Backend runtime | Use the `py` launcher on Windows |
| [Node.js + npm](https://nodejs.org/) | Frontend build (TypeScript/Tailwind) | LTS version recommended |
| [.NET 10 SDK](https://dotnet.microsoft.com/en-us/download/dotnet/10.0) | Build RsCli (one-time) | Only needed for the initial RsCli build |
| [ffmpeg](https://ffmpeg.org/download.html) | Audio conversion | Must be on PATH |
| [FluidSynth](https://www.fluidsynth.org/) + a soundfont | MIDI audio rendering | Optional — only needed if not supplying your own audio file |

---

## First-time Setup

### 1. Install Python dependencies

```
py -m pip install pyguitarpro pycryptodome midiutil Pillow mutagen fastapi "uvicorn[standard]" python-multipart pyinstaller --trusted-host pypi.org --trusted-host files.pythonhosted.org
```

### 2. Install Node dependencies

```
npm install
```

### 3. Build the frontend (TypeScript + Tailwind CSS)

```
npm run build
```

### 4. Build RsCli (one-time, requires .NET 10 SDK)

RsCli converts Rocksmith XML to encrypted SNG format. Build it once and it lives in `lib/tools/rscli/`.

```
git clone --depth 1 https://github.com/iminashi/Rocksmith2014.NET.git C:\temp\rs2014
mkdir C:\temp\rs2014\tools\RsCli
copy rscli\RsCli.fsproj C:\temp\rs2014\tools\RsCli\
copy rscli\Program.fs  C:\temp\rs2014\tools\RsCli\
cd C:\temp\rs2014\tools\RsCli
dotnet publish -c Release -r win-x64 --self-contained -o C:\path\to\gp-to-psarc\lib\tools\rscli
```

Replace `C:\path\to\gp-to-psarc` with the actual project path.

> The `rscli/` source files (`RsCli.fsproj`, `Program.fs`) are included in the repo.

---

## Running the Web UI

```
py run_web.py
```

Or double-click **`start-web.bat`**.

The browser opens automatically to `http://127.0.0.1:8765`.

**Workflow:**
1. Drop a Guitar Pro file onto the drop zone
2. Edit song metadata (title, artist, album, year) — auto-filled from the file and audio tags
3. Drop an album art image (jpg/png/webp) — optional
4. Drop an audio file (mp3/ogg/wav) — optional, MIDI audio is generated automatically if omitted
5. Select which tracks to include and their arrangement type (Lead / Rhythm / Bass / Drums)
6. Click **Build PSARC**
7. Click **Download** when done

Drop the `.psarc` into your Rocksmith 2014 DLC folder:
```
Steam\steamapps\common\Rocksmith2014\dlc\
```

---

## Command-Line Interface

```
py gp_to_psarc.py song.gp5
py gp_to_psarc.py song.gp5 --audio backing.mp3
py gp_to_psarc.py song.gp  --output out.psarc --title "My Song" --artist "Me"
```

**Options:**

| Flag | Description |
|---|---|
| `-o / --output` | Output `.psarc` path (default: same directory as input) |
| `--audio` | Audio file to embed. If omitted, MIDI audio is rendered via FluidSynth |
| `--title` | Override song title (default: read from GP file metadata) |
| `--artist` | Override artist name |
| `--album` | Override album name |
| `--year` | Override release year |

---

## Development

Recompile TypeScript on save while editing:

```
npm run watch
```

Restart the server after any Python file change:

```
py run_web.py
```

---

## Building the Distributable `.exe`

Produces a single folder that friends can unzip and run — no Python or Node needed.

```
py build_dist.py
```

Output: `gp-to-psarc-v1.0.zip`

**Friend's install:**
1. Unzip
2. Double-click `gp-to-psarc.exe`
3. Browser opens automatically

> ffmpeg must be on PATH on the target machine. Friends can install it via `winget install ffmpeg`.

---

## Project Structure

```
gp-to-psarc/
├── gp_to_psarc.py       CLI entry point
├── run_web.py           Web server entry point
├── start-web.bat        Double-click launcher
├── build_dist.py        Builds the distributable .exe
├── gp_to_psarc.spec     PyInstaller config
├── package.json         npm scripts (TypeScript + Tailwind build)
├── tsconfig.json        TypeScript config
├── pyproject.toml       Python dependencies
├── rscli/               RsCli F# source (build once with dotnet)
├── lib/                 Core conversion modules (vendored from Slopsmith)
│   ├── gp2rs.py         GP3/4/5 → Rocksmith XML
│   ├── gp2rs_gpx.py     GP6/7/8 → Rocksmith XML
│   ├── gp2midi.py       GP → MIDI → audio
│   ├── cdlc_builder.py  PSARC assembly
│   ├── patcher.py       Low-level PSARC packing
│   └── tools/rscli/     RsCli binary (built from rscli/ source)
└── web/
    ├── server.py        FastAPI backend
    ├── build_runner.py  Build pipeline
    ├── sessions.py      Temp file lifecycle
    ├── ts/app.ts        TypeScript frontend source
    ├── css/input.css    Tailwind entry
    └── static/          Compiled frontend (gitignored)
```
