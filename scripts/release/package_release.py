#!/usr/bin/env python3
"""Assemble the release folder: installer, portable zip and SHA256 checksums.

Produces in ``release/``:

    EasyWalp-Setup-<version>.exe               the Inno Setup installer
    EasyWalp-Portable-<version>.exe            single file, unzip-free, double-click to run
    EasyWalp-Setup-<version>-windows.zip       installer + single file + the onedir tree
    SHA256SUMS.txt                             checksums of all of them

The zip holds three ways to run the same build: the installer (no admin rights
needed), the single-file portable exe, and ``portable/EasyWalp/`` exactly as
PyInstaller built it (the tree the installer puts into
``%LOCALAPPDATA%\\Programs\\EasyWalp``). The single file is the one to send someone
who "downloaded it and it does not start": nothing to unpack, nothing to keep
together.

Usage (CI):

    python scripts/release/package_release.py --version 1.0.0 \
        --installer installer-out/EasyWalp-Setup-1.0.0.exe \
        --portable dist/EasyWalp-Portable/EasyWalp-Portable.exe --dist dist/EasyWalp
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class PackagingError(RuntimeError):
    """A readable packaging failure."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_tree(zf: zipfile.ZipFile, folder: Path, prefix: str) -> int:
    """Zip ``folder`` under ``prefix``; returns the number of files added."""
    count = 0
    for path in sorted(folder.rglob("*")):
        if path.is_dir():
            continue
        arcname = f"{prefix}/{path.relative_to(folder).as_posix()}"
        zf.write(path, arcname, compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
        count += 1
    return count


def build_portable_zip(version: str, dist: Path, installer: Path, out_zip: Path,
                       portable: Path | None = None) -> int:
    """Installer + portable app in one zip (the file the README points at)."""
    with zipfile.ZipFile(out_zip, "w") as zf:
        zf.write(installer, installer.name, compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
        if portable is not None and portable.is_file():
            zf.write(portable, portable.name, compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
        files = add_tree(zf, dist, f"portable/{dist.name}")
    if files == 0:
        raise PackagingError(f"the PyInstaller output folder is empty: {dist}")
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Package the EasyWalp Windows release")
    parser.add_argument("--version", required=True, help="release version, e.g. 1.0.0")
    parser.add_argument("--installer", type=Path, required=True, help="the built installer .exe")
    parser.add_argument("--dist", type=Path, default=ROOT / "dist" / "EasyWalp",
                        help="the PyInstaller onedir output (default: dist/EasyWalp)")
    parser.add_argument("--portable", type=Path, default=ROOT / "dist" / "EasyWalp-Portable" / "EasyWalp-Portable.exe",
                        help="the PyInstaller onefile output (optional but recommended)")
    parser.add_argument("--out", type=Path, default=ROOT / "release",
                        help="release folder (default: release/)")
    args = parser.parse_args(argv)

    version = args.version.strip().lstrip("vV")
    if not args.installer.is_file():
        print(f"error: installer not found: {args.installer}", file=sys.stderr)
        return 1
    if not args.dist.is_dir():
        print(f"error: PyInstaller output not found: {args.dist}", file=sys.stderr)
        return 1

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    installer = out / f"EasyWalp-Setup-{version}.exe"
    if args.installer.resolve() != installer.resolve():
        installer.write_bytes(args.installer.read_bytes())

    portable = out / f"EasyWalp-Portable-{version}.exe"
    if args.portable.is_file():
        if args.portable.resolve() != portable.resolve():
            portable.write_bytes(args.portable.read_bytes())
    else:
        # Not fatal: the installer and the onedir zip are still a complete release.
        print(f"warning: no single-file build at {args.portable} - shipping without it", file=sys.stderr)
        portable = None

    zip_path = out / f"EasyWalp-Setup-{version}-windows.zip"
    try:
        count = build_portable_zip(version, args.dist, installer, zip_path, portable)
    except PackagingError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    files = [installer, zip_path] + ([portable] if portable is not None else [])
    sums = out / "SHA256SUMS.txt"
    sums.write_text("\n".join(f"{sha256(p)}  {p.name}" for p in files) + "\n", encoding="utf-8")

    print(f"installer: {installer} ({installer.stat().st_size / 1e6:.1f} MB)")
    if portable is not None:
        print(f"portable:  {portable} ({portable.stat().st_size / 1e6:.1f} MB)")
    print(f"zip:       {zip_path} ({zip_path.stat().st_size / 1e6:.1f} MB, {count} files)")
    print(f"checksums: {sums}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
