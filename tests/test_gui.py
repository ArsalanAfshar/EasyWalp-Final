"""GUI smoke tests (offscreen Qt; skipped if PySide6 is unavailable).

These run on CI (Linux runners have libGL + offscreen platform) and on any dev
machine with a display. The sandbox without system Qt libraries skips them.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def qapp():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication  # noqa: F401
    except (ImportError, OSError) as e:  # e.g. libGL missing on headless minimal machines
        pytest.skip(f"Qt cannot load here: {e}")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def i18n_en():
    from easywalp.i18n import i18n

    i18n.load_all()
    i18n.set_language("en")
    yield i18n
    i18n.set_language("en")


def test_i18n_tables_loaded(i18n_en):
    assert i18n_en.tr("main.generate") == "Generate"
    i18n_en.set_language("fa")
    assert i18n_en.tr("main.generate") == "تولید"
    assert i18n_en.is_rtl() is True
    i18n_en.set_language("en")
    assert i18n_en.is_rtl() is False


def test_persian_digits_display_only(i18n_en):
    i18n_en.set_language("fa")
    assert i18n_en.digits("236") == "۲۳۶"
    i18n_en.set_language("en")
    assert i18n_en.digits("236") == "236"


def test_themes_build_stylesheet():
    from easywalp.themes import DARK, LIGHT, resolve, stylesheet

    dark = stylesheet(DARK)
    light = stylesheet(LIGHT)
    assert "#0b1524" in dark and "#f2f6fb" in light
    assert resolve("dark") is DARK
    assert resolve("light") is LIGHT
    assert resolve("whatever") in (DARK, LIGHT)


def test_mainwindow_constructs(qapp, data_dir, sample_images, i18n_en):
    from easywalp.app.mainwindow import MainWindow

    win = MainWindow()
    win.apply_theme()
    win.apply_language()
    assert win.windowTitle() == "EasyWalp"
    assert win.preset_combo.count() == 0  # no presets yet
    assert not win.generate_btn.isEnabled()


def test_code_preview_updates(qapp, data_dir, sample_images, i18n_en):
    from easywalp.config import GenerateOptions
    from easywalp.pipeline import plan_names

    info = plan_names(GenerateOptions(), "O", 236, "2k")
    assert info.code == "MD-O-C236"


def test_rtl_direction(qapp, data_dir, sample_images, i18n_en):
    from PySide6.QtCore import Qt

    from easywalp.app.mainwindow import MainWindow

    win = MainWindow()
    win.apply_language()  # default en -> LTR
    assert win.layoutDirection() == Qt.LayoutDirection.LeftToRight
    i18n_en.set_language("fa")
    win.apply_language()
    assert win.layoutDirection() == Qt.LayoutDirection.RightToLeft
    assert win.desktop_zone._title.text() == i18n_en.tr("main.desktop")
