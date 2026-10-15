#!/usr/bin/env python3
"""Build a synthetic EasyWalp-style mockup PSD *with PhotoCraft itself*.

Creates: 2000x1500 canvas, a desktop smart object (16:9 sample), a mobile smart
object (9:16 sample), a Solid Color fill layer under them, and a Type layer with
the code text `Code:MD-O-C236`. Saved as `template.psd`.

Used by the spike and CI tests so nobody needs private PSDs to validate the
pipeline. Run:  python scripts/spike/make_test_psd.py --cli <photocraft-cli> --out dir
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from PIL import Image, ImageDraw  # noqa: E402

from easywalp.photocraft import Session, run_one_shot  # noqa: E402
from easywalp.pipeline import save_wallpaper_jpg, cover_resize  # noqa: E402


def gradient(w: int, h: int, top, bottom, label: str) -> Image.Image:
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        t = y / max(1, h - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(w):
            px[x, y] = color
    d = ImageDraw.Draw(im)
    d.rectangle([0, h - 60, w, h], fill=(255, 255, 255))
    d.text((20, h - 45), label, fill=(0, 0, 0))
    return im


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cli", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    desktop = args.out / "sample-desktop.png"
    mobile = args.out / "sample-mobile.png"
    gradient(1600, 900, (36, 98, 158), (10, 22, 40), "DESKTOP").save(desktop)
    gradient(900, 1600, (158, 98, 36), (40, 18, 8), "MOBILE").save(mobile)

    new = {"width": 2000, "height": 1500, "background": "#0b1524"}
    place_d = {"path": "sample-desktop.png", "asSmartObject": True}
    place_m = {"path": "sample-mobile.png", "asSmartObject": True}

    with Session(PhotoCraftBinary(args.cli), work_root=args.out) as s:
        s.start()
        s.call("doc.new", new)
        s.call("doc.place", place_d)
        s.call("doc.place", place_m)
        s.execute("layer.newFillLayer.solidColor", {"color": "#203040", "name": "BG Color"})
        s.execute("type.create", {"text": "Code:MD-O-C236", "size": 72, "color": "#ffffff", "name": "Code label"})
        saved = s.call("doc.save", {"path": "template.psd"})
        print("saved:", saved)
    print(f"template at {args.out / 'template.psd'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
