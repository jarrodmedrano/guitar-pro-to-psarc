"""Build the distributable .zip of gp-to-psarc.

Steps:
  1. Compile TypeScript + Tailwind CSS  (npm run build)
  2. Bundle everything with PyInstaller (gp_to_psarc.spec)
  3. Zip dist/gp-to-psarc/ → gp-to-psarc-v1.0.zip

Usage:
  py build_dist.py
"""

import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
VERSION = "1.0"


def run(cmd: list[str], **kw) -> None:
    print(f"\n>>> {' '.join(cmd)}")
    subprocess.run(cmd, check=True, **kw)


def main() -> None:
    # 1. TypeScript + Tailwind
    run(["npm", "run", "build"], cwd=ROOT)

    # 2. PyInstaller
    run([sys.executable, "-m", "PyInstaller", "gp_to_psarc.spec", "--noconfirm"], cwd=ROOT)

    # 3. Zip
    out_dir = ROOT / "dist" / "gp-to-psarc"
    zip_path = ROOT / f"gp-to-psarc-v{VERSION}.zip"
    print(f"\n>>> Zipping {out_dir} → {zip_path}")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in out_dir.rglob("*"):
            z.write(f, Path("gp-to-psarc") / f.relative_to(out_dir))

    print(f"\n✓ Built: {zip_path} ({zip_path.stat().st_size // 1024 // 1024} MB)")


if __name__ == "__main__":
    main()
