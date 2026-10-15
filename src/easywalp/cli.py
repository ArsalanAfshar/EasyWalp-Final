"""CLI mode: `python -m easywalp --preset NAME --desktop a.png --mobile b.png
--category O --number 236 --res 2k --out D:\\Out`

Runs the same core pipeline as the GUI (PhotoCraft renders the preview).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, logging_setup
from .config import RESOLUTIONS
from .photocraft import PhotoCraftBinary
from .pipeline import Pipeline, PipelineError, check_overwrite, plan_names
from .presets import Preset, PresetError
from .wizard import PhotoCraftError


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m easywalp",
        description="EasyWalp - generate a Wallify wallpaper package (2 wallpapers + PhotoCraft preview mockup)",
    )
    p.add_argument("--preset", required=True, help="preset name (or id)")
    p.add_argument("--desktop", required=True, type=Path, help="desktop wallpaper image")
    p.add_argument("--mobile", required=True, type=Path, help="mobile wallpaper image")
    p.add_argument("--category", default="O", choices=["O", "A"], help="O=Other, A=Anime (default O)")
    p.add_argument("--number", required=True, type=int, help="wallpaper number")
    p.add_argument("--res", default="2k", choices=sorted(RESOLUTIONS), help="target resolution (default 2k)")
    p.add_argument("--out", required=True, type=Path, help="output base folder")
    p.add_argument("--color", default=None, help="override average color, #rrggbb")
    p.add_argument("--no-suffix", dest="suffix", action="store_false", default=None,
                   help="force the preset's resolution-suffix setting off")
    p.add_argument("--suffix", dest="suffix", action="store_true", default=None,
                   help="force the resolution suffix on for this run")
    p.add_argument("--yes", action="store_true", help="overwrite an existing folder without asking")
    p.add_argument("--engine", default=None, type=Path, help="path to photocraft-cli")
    p.add_argument("--version", action="version", version=f"EasyWalp {__version__}")
    return p


def find_preset(name_or_id: str) -> Preset:
    for preset in Preset.load_all():
        if preset.name == name_or_id or preset.id == name_or_id:
            return preset
    known = ", ".join(p.name for p in Preset.load_all()) or "(none installed)"
    raise PresetError(f"preset '{name_or_id}' not found. Installed presets: {known}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging_setup.setup()
    try:
        preset = find_preset(args.preset)
        override: dict = {}
        if args.res:
            override["resolution_key"] = args.res
        if args.suffix is not None:
            override["add_resolution_suffix"] = args.suffix
        if args.color:
            override["color_source"] = "manual"
            override["manual_color"] = args.color

        info = plan_names(preset.options, args.category, args.number, override.get("resolution_key", preset.options.resolution_key))
        conflict = check_overwrite(args.out, info)
        if conflict and not args.yes:
            answer = input(f"Folder {conflict} exists. Overwrite? [y/N] ").strip().lower()
            if answer not in {"y", "yes"}:
                print("aborted")
                return 1

        binary = PhotoCraftBinary(args.engine)
        pipeline = Pipeline(binary)
        result = pipeline.generate(
            preset,
            args.desktop,
            args.mobile,
            args.category,
            args.number,
            args.out,
            progress=lambda stage, frac: print(f"[{stage} {int(frac * 100):3d}%]", flush=True),
            options_override=override,
        )
        for w in result.warnings:
            print(f"warning: {w}", file=sys.stderr)
        print(f"Done: {result.out_dir}")
        print(f"  {result.desktop_jpg.name}")
        print(f"  {result.mobile_jpg.name}")
        print(f"  {result.preview_jpg.name}")
        return 0
    except (PipelineError, PresetError, PhotoCraftError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
