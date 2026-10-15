# PyInstaller spec for EasyWalp (onedir, windowed).
# CI runs: pyinstaller --noconfirm --clean packaging/windows/easywalp.spec
# The engine binary is staged into build/payload/photocraft by stage_payload.py.
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parents[1]  # repo root
PAYLOAD = ROOT / "build" / "payload"

datas = [
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "i18n"), "i18n"),
]
if (PAYLOAD / "photocraft").exists():
    datas.append((str(PAYLOAD / "photocraft"), "assets/photocraft"))

a = Analysis(
    [str(ROOT / "src" / "easywalp" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=["easywalp.app.mainwindow"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EasyWalp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed app
    icon=str(ROOT / "assets" / "icons" / "easywalp.ico"),
    version=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="EasyWalp",
)
