#!/usr/bin/env python3
"""Install the GitHub Actions workflows into .github/workflows/.

GitHub blocks some app integrations from pushing `.github/workflows/*` files, so
the canonical copies of EasyWalp's three workflows live in `ops/workflows/` and
this script puts them where GitHub runs them. Run ONCE in your own clone (where
you log in with your own GitHub account):

    python scripts/install_workflows.py
    git add .github/workflows
    git commit -m "Install EasyWalp CI workflows"
    git push

After that, everything is automatic:
  - tests.yml          every push: pytest (Linux + Windows)
  - photocraft-binaries.yml  builds the pinned photocraft-cli (Actions tab, or
                       automatically when config/photocraft-pin.json changes)
  - release.yml        on tags v*: full release (engine + app + installer)
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "ops" / "workflows"
DEST = ROOT / ".github" / "workflows"


def main() -> int:
    if not SRC.exists():
        print(f"missing {SRC}", file=sys.stderr)
        return 1
    DEST.mkdir(parents=True, exist_ok=True)
    copied = []
    for f in sorted(SRC.glob("*.yml")):
        shutil.copyfile(f, DEST / f.name)
        copied.append(f.name)
    print("installed:")
    for name in copied:
        print(f"  .github/workflows/{name}")
    print(
        "\nNow commit and push them (from your own GitHub account):\n"
        '  git add .github/workflows && git commit -m "Install CI workflows" && git push'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
