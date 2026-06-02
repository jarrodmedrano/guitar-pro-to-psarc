"""Build the distributable .zip of gp-to-psarc.

Steps:
  1. Compile TypeScript + Tailwind CSS  (npm run build)
  2. Bundle everything with PyInstaller (gp_to_psarc.spec)
  3. Zip dist/gp-to-psarc/ → gp-to-psarc-v<VERSION>.zip

Usage:
  py build_dist.py                   # local build, version 1.0
  py build_dist.py --version 1.2.3   # CI / tagged release
  py build_dist.py --skip-npm        # skip npm build (already done in CI)
"""

import argparse
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent


def run(cmd: list[str], **kw) -> None:
    print(f"\n>>> {' '.join(cmd)}")
    subprocess.run(cmd, check=True, **kw)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="1.0", help="Release version string (e.g. 1.2.3)")
    parser.add_argument("--skip-npm", action="store_true", help="Skip npm run build (already done upstream)")
    args = parser.parse_args()

    if not args.skip_npm:
        run(["npm", "run", "build"], cwd=ROOT)

    run([sys.executable, "-m", "PyInstaller", "gp_to_psarc.spec", "--noconfirm"], cwd=ROOT)

    out_dir = ROOT / "dist" / "gp-to-psarc"
    zip_path = ROOT / f"gp-to-psarc-v{args.version}.zip"
    print(f"\n>>> Zipping {out_dir} → {zip_path}")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in out_dir.rglob("*"):
            z.write(f, Path("gp-to-psarc") / f.relative_to(out_dir))

    print(f"\n✓ Built: {zip_path} ({zip_path.stat().st_size // 1024 // 1024} MB)")


if __name__ == "__main__":
    main()
