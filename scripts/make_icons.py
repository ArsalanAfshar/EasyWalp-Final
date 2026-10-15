#!/usr/bin/env python3
"""Generate EasyWalp application icons from the Wallify channel logo.

Produces assets/icons/easywalp.ico (multi-size, for the exe/installer) and
PNG sizes used for the window icon at runtime. Derived art keeps the logo's
navy/cyan identity: a rounded-corner square crop of the logo itself.

Usage: python scripts/make_icons.py [path/to/logo.png]
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOGO = ROOT / "assets" / "logo" / "wallify-logo.png"
OUT_DIR = ROOT / "assets" / "icons"

PNG_SIZES = [16, 24, 32, 48, 64, 128, 256, 512]
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
RADIUS_RATIO = 0.22  # rounded-corner radius relative to the icon size


def rounded(image: Image.Image, size: int) -> Image.Image:
    """Center-crop to a square, scale to `size`, and round the corners."""
    square = ImageOps.fit(image, (size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    radius = max(1, int(size * RADIUS_RATIO))
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(square, (0, 0), mask)
    return out


def main() -> int:
    logo_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOGO
    if not logo_path.exists():
        print(f"logo not found: {logo_path}", file=sys.stderr)
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    logo = Image.open(logo_path).convert("RGB")

    for s in PNG_SIZES:
        rounded(logo, s).save(OUT_DIR / f"easywalp-{s}.png")

    # The largest PNG becomes the ico source (Pillow downsamples the rest).
    big = rounded(logo, max(ICO_SIZES))
    big.save(
        OUT_DIR / "easywalp.ico",
        format="ICO",
        sizes=[(s, s) for s in ICO_SIZES],
    )
    print(f"wrote {OUT_DIR / 'easywalp.ico'} and {len(PNG_SIZES)} PNGs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
