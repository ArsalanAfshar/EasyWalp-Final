"""Filesystem locations for EasyWalp data (settings, presets, logs, binaries).

Windows: %APPDATA%\\EasyWalp\\...   (via ``os.getenv("APPDATA")``)
Linux/macOS dev runs: ~/.local/share/EasyWalp, overridden by EASYWALP_DATA_DIR.
Android (python-for-android build): the app's private files directory, which
python-for-android exports as ``ANDROID_PRIVATE`` (internal storage - presets and
their PSD clones are private to EasyWalp, exactly like %APPDATA% on Windows).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def is_android() -> bool:
    """True inside a python-for-android APK (the bootstrap exports these vars)."""
    if sys.platform == "android":
        return True
    return any(os.getenv(name) for name in ("ANDROID_ARGUMENT", "ANDROID_PRIVATE", "ANDROID_UNPACK"))


def android_root_dir() -> Path | None:
    """The unpacked app root inside an APK (holds ``main.py``, ``assets``, ``easywalp``)."""
    for name in ("ANDROID_UNPACK", "ANDROID_APP_PATH", "ANDROID_ARGUMENT"):
        value = os.getenv(name)
        if value:
            return Path(value)
    return None


def data_dir() -> Path:
    """The per-user data root: %APPDATA%\\EasyWalp on Windows, the app files dir on Android."""
    override = os.getenv("EASYWALP_DATA_DIR")
    if override:
        root = Path(override)
    elif is_android():
        sandbox = os.getenv("ANDROID_PRIVATE") or os.getenv("ANDROID_UNPACK")
        root = Path(sandbox or ".") / "EasyWalp"
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
    """Directory of bundled resources (fonts/icons), frozen-aware for PyInstaller.

    On Android the resources ship inside the app root (``ANDROID_UNPACK``) that
    python-for-android unpacks from the APK - that copy is read-only, so anything
    writable lives under :func:`data_dir` instead.
    """
    root = android_root_dir()
    if root is not None and (root / "assets").exists():
        return root / "assets"
    bundled = getattr(sys, "_MEIPASS", None)  # PyInstaller onefile
    if bundled and Path(bundled).joinpath("assets").exists():
        return Path(bundled) / "assets"
    # PyInstaller onedir: assets sit next to the executable.
    exe_dir = Path(getattr(sys, "executable", "")).resolve().parent
    if (exe_dir / "assets").exists():
        return exe_dir / "assets"
    # Source checkout: <repo>/assets
    return Path(__file__).resolve().parents[2] / "assets"


def fonts_dir() -> Path:
    """User/bundled font files the engine may use (copied here by the Android app)."""
    d = data_dir() / "fonts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def engine_override() -> Path | None:
    """Explicit engine binary from the environment (used by the Android launcher)."""
    value = os.getenv("EASYWALP_ENGINE")
    if value and Path(value).is_file():
        return Path(value)
    return None


def engine_env_overrides() -> dict[str, str]:
    """Extra environment for the engine child process.

    The engine finds fonts by scanning well-known directories; on Android there is
    no ``/usr/share/fonts``, but it does look at ``$XDG_DATA_HOME/fonts`` and
    ``$HOME/.fonts`` - so point both at the app's data dir, where the app copies
    the bundled Vazirmatn faces and any font the user imports. ``TMPDIR`` keeps the
    engine's scratch files inside the app sandbox as well.
    """
    if not is_android():
        return {}
    root = data_dir()
    tmp = temp_dir()
    return {
        "HOME": str(root),
        "XDG_DATA_HOME": str(root),
        "TMPDIR": str(tmp),
    }

