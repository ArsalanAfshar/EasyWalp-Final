"""Filesystem locations for EasyWalp data (settings, presets, logs, binaries).

Windows: %APPDATA%\\EasyWalp\\...   (via ``os.getenv("APPDATA")``)
Linux/macOS dev runs: ~/.local/share/EasyWalp, overridden by EASYWALP_DATA_DIR.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    """The per-user data root: %APPDATA%\\EasyWalp on Windows."""
    override = os.getenv("EASYWALP_DATA_DIR")
    if override:
        root = Path(override)
    elif os.name == "nt":
        root = Path(os.getenv("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "EasyWalp"
    else:
        root = Path(os.getenv("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "EasyWalp"
    root.mkdir(parents=True, exist_ok=True)
    return root


def settings_file() -> Path:
    return data_dir() / "settings.json"


def presets_dir() -> Path:
    d = data_dir() / "presets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def logs_dir() -> Path:
    d = data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def engines_dir() -> Path:
    """Where photocraft-cli binaries live (bundled next to the exe, or downloaded)."""
    d = data_dir() / "engines"
    d.mkdir(parents=True, exist_ok=True)
    return d


def temp_dir() -> Path:
    d = data_dir() / "temp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def bundled_dir() -> Path:
    """Directory of bundled resources (fonts/icons), frozen-aware for PyInstaller."""
    bundled = getattr(sys, "_MEIPASS", None)  # PyInstaller onefile
    if bundled and Path(bundled).joinpath("assets").exists():
        return Path(bundled) / "assets"
    # PyInstaller onedir: assets sit next to the executable.
    exe_dir = Path(getattr(sys, "executable", "")).resolve().parent
    if (exe_dir / "assets").exists():
        return exe_dir / "assets"
    # Source checkout: <repo>/assets
    return Path(__file__).resolve().parents[2] / "assets"
