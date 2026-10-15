"""Shared pytest fixtures: isolated EasyWalp data dir and sample images."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    """Point %APPDATA%-equivalent at a tmp dir for every test."""
    monkeypatch.setenv("EASYWALP_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


@pytest.fixture()
def sample_images(tmp_path):
    d = tmp_path / "img"
    d.mkdir()
    desktop = d / "desktop.png"
    mobile = d / "mobile.png"
    Image.new("RGB", (1920, 1080), (30, 90, 150)).save(desktop)
    Image.new("RGB", (1080, 1920), (150, 90, 30)).save(mobile)
    return desktop, mobile


@pytest.fixture()
def tiny_images(tmp_path):
    d = tmp_path / "tiny"
    d.mkdir()
    desktop = d / "desktop.png"
    mobile = d / "mobile.png"
    Image.new("RGB", (160, 90), (10, 10, 10)).save(desktop)
    Image.new("RGB", (90, 160), (200, 200, 200)).save(mobile)
    return desktop, mobile


# --------------------------------------------------------------------- Qt shutdown
# The GUI tests never destroy the windows they create, so PySide6 deletes the
# QApplication's C++ objects while Python still holds the wrappers. CPython then
# aborts *after* the report has been printed ("QObject: shared QObject was deleted
# directly" / "malloc_consolidate(): unaligned fastbin chunk detected"), turning a
# green run into a red CI step. `pytest_unconfigure` is the last hook that runs
# after the summary, so the exit code there is exactly pytest's verdict.
_SESSION_EXIT: int | None = None


def pytest_sessionfinish(session, exitstatus) -> None:
    global _SESSION_EXIT
    _SESSION_EXIT = int(exitstatus)


def pytest_unconfigure(config) -> None:
    if _SESSION_EXIT is None or "PySide6" not in sys.modules:
        return
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_SESSION_EXIT)
