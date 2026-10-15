#!/usr/bin/env python3
"""Build a synthetic EasyWalp-style mockup PSD *with PhotoCraft itself*.

Creates: 2000x1500 canvas, a desktop smart object (16:9 sample), a mobile smart
object (9:16 sample), a Solid Color fill layer under them, and a Type layer with
the code text `Code:MD-O-C236`. Saved as `template.psd`.

The fixture itself lives in `easywalp.testkit` (shared with the Android self-test);
this script is the desktop/CI entry point:

    python scripts/spike/make_test_psd.py --cli <photocraft-cli> --out dir
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from easywalp.photocraft import PhotoCraftBinary  # noqa: E402
from easywalp.testkit import CODE_TEXT, build_template_psd  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cli", type=Path, default=None, help="photocraft-cli (default: auto-detect)")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--code", default=CODE_TEXT, help="text of the code layer")
    args = ap.parse_args()

    binary = PhotoCraftBinary(args.cli)
    template = build_template_psd(binary, args.out, code_text=args.code)
    print(f"template at {template}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
