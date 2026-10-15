"""Rotating file logging in %APPDATA%/EasyWalp/logs (plus a console echo)."""
from __future__ import annotations

import logging
import logging.handlers
import sys

from . import paths


def setup(verbose: bool = False) -> logging.Handler:
    handler = logging.handlers.RotatingFileHandler(
        paths.logs_dir() / "easywalp.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.addHandler(handler)

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    console.setLevel(logging.WARNING)
    root.addHandler(console)
    return handler
