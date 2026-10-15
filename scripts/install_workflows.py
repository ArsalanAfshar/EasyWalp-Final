#!/usr/bin/env python3
"""Install the GitHub Actions workflow into .github/workflows/.

GitHub blocks some app integrations from pushing `.github/workflows/*` files, so
the canonical copy of EasyWalp's CI lives in `ops/workflows/easywalp-ci.yml` and
this script puts it where GitHub runs it. Run ONCE in your own clone (where you
log in with your own GitHub account):

    python scripts/install_workflows.py
    git add .github/workflows
    git commit -m "Install EasyWalp CI"
    git push

After that, everything is automatic:
  - every push  -> pytest (Linux + Windows) + ready photocraft-cli binaries
                   staged on the `photocraft-bin` branch
  - Actions tab > "EasyWalp CI" > "Run workflow" with a version (e.g. 0.1.0)
                -> full Windows installer published to GitHub Releases
  - pushing a v* tag does the same as the manual run
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "ops" / "workflows" / "easywalp-ci.yml"
DEST = ROOT / ".github" / "workflows" / "easywalp-ci.yml"


def main() -> int:
    if not SRC.exists():
        print(f"missing {SRC}", file=sys.stderr)
        return 1
    DEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SRC, DEST)
    print(f"installed: {DEST}")
    print(
        "\nNow commit and push (from your own GitHub account):\n"
        '  git add .github/workflows && git commit -m "Install EasyWalp CI" && git push'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
