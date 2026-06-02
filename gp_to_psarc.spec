# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

block_cipher = None

a = Analysis(
    ["run_web.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("web/static",          "web/static"),
        ("lib/gp2rs.py",        "lib"),
        ("lib/gp2rs_gpx.py",    "lib"),
        ("lib/gp2midi.py",      "lib"),
        ("lib/cdlc_builder.py", "lib"),
        ("lib/patcher.py",      "lib"),
        ("lib/safepath.py",     "lib"),
        ("lib/tools/rscli/RsCli.exe", "rscli"),
    ],
    hiddenimports=[
        "uvicorn.lifespan.on",
        "uvicorn.protocols.websockets.websockets_impl",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.http.httptools_impl",
        "fastapi",
        "starlette.staticfiles",
        "starlette.responses",
        "guitarpro",
        "Crypto.Cipher.AES",
        "midiutil",
        "PIL",
        "PIL.Image",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="gp-to-psarc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,      # no terminal window
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="gp-to-psarc",
)
