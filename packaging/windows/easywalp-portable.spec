# PyInstaller spec for the *portable* EasyWalp: one file, nothing to install.
#
# CI runs: pyinstaller --noconfirm --clean packaging/windows/easywalp-portable.spec
# The installer is built from easywalp.spec (onedir); this one exists because the
# most common "the app will not start" report is a user who downloaded a single
# file out of an onedir build - a folder you cannot unzip or an .exe started on its
# own. Everything - Python, Qt, the assets and the engine - is inside this one .exe.
#
# Keep the lists below in sync with easywalp.spec; tests/test_installer_files.py
# compares the two files so a module added to one cannot be missing from the other.
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parents[1]  # repo root (SPECPATH = packaging/windows)
PAYLOAD = ROOT / "build" / "payload"

datas = [
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "i18n"), "i18n"),
]
if (PAYLOAD / "photocraft").exists():
    datas.append((str(PAYLOAD / "photocraft"), "assets/photocraft"))

hidden = [
    "easywalp",
    "easywalp.__main__",
    "easywalp.cli",
    "easywalp.config",
    "easywalp.i18n",
    "easywalp.logging_setup",
    "easywalp.paths",
    "easywalp.photocraft",
    "easywalp.photocraft_protocol",
    "easywalp.pipeline",
    "easywalp.presets",
    "easywalp.selfcheck",
    "easywalp.settings",
    "easywalp.themes",
    "easywalp.wizard",
    "easywalp.app",
    "easywalp.app.mainwindow",
    "easywalp.app.widgets",
    "easywalp.app.wizard",
    "easywalp.app.dialogs",
    "easywalp.app.presets_dialog",
    "easywalp.app.worker",
]

a = Analysis(
    [str(ROOT / "packaging" / "windows" / "easywalp_entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

# One file: binaries and data go *into* the exe (exclude_binaries=False) and are
# unpacked into sys._MEIPASS at startup, which is what paths.bundled_dir() reads.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="EasyWalp-Portable",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,  # windowed app
    disable_windowed_traceback=False,
    icon=str(ROOT / "assets" / "icons" / "easywalp.ico"),
    version=None,
)
