#!/usr/bin/env python3
"""Fetch the prebuilt photocraft-cli binaries from this repo's `photocraft-bin`
staging branch (created by the "PhotoCraft binaries" workflow) into the folder
EasyWalp and the spike scripts look in:

  Windows: %APPDATA%\\EasyWalp\\engines\\photocraft-cli.exe
  Linux:   ~/.local/share/EasyWalp/engines/photocraft-cli

Usage:
  python scripts/fetch_engine.py                 # current platform
  python scripts/fetch_engine.py --platform windows-x64
  python scripts/fetch_engine.py --platform linux-x86_64 --out engines/
"""
from __future__ import annotations

import argparse
import io
import os
import platform
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

REPO = "ArsalanAfshar/EasyWalp-Final"
BRANCH = "photocraft-bin"


def current_platform() -> str:
    if platform.system() == "Windows":
        return "windows-x64"
    return "linux-x86_64"


def binary_name(plat: str) -> str:
    return "photocraft-cli.exe" if plat.startswith("windows") else "photocraft-cli"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", default=current_platform(), choices=["windows-x64", "linux-x86_64"])
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--out", default=None, help="destination folder (default: the EasyWalp engines dir)")
    args = ap.parse_args()

    url = f"https://codeload.github.com/{args.repo}/tar.gz/refs/heads/{BRANCH}"
    print(f"downloading {url} ...")
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            data = r.read()
    except Exception as e:
        print(
            f"could not download the staging branch ({e}).\n"
            "Run the 'PhotoCraft binaries' workflow first (see docs/RELEASE-CHECKLIST.md),\n"
            "or build locally: cargo build --release -p photocraft-cli",
            file=sys.stderr,
        )
        return 1

    wanted = f"photocraft-bin-{args.platform}"
    name = binary_name(args.platform)
    extracted = None
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        for member in tf.getmembers():
            parts = member.name.split("/")
            if len(parts) >= 2 and parts[1] == args.platform and parts[-1] == name:
                out_dir = Path(args.out) if args.out else _engines_dir()
                out_dir.mkdir(parents=True, exist_ok=True)
                src = tf.extractfile(member)
                assert src is not None
                dest = out_dir / name
                dest.write_bytes(src.read())
                if os.name != "nt":
                    dest.chmod(0o755)
                extracted = dest
                break
    if not extracted:
        print(f"binary '{name}' for {args.platform} not found on branch {BRANCH}.", file=sys.stderr)
        return 2
    print(f"installed: {extracted}")
    print("EasyWalp and scripts/spike will now find it automatically.")
    return 0


def _engines_dir() -> Path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from easywalp import paths

    return paths.engines_dir()


if __name__ == "__main__":
    raise SystemExit(main())
