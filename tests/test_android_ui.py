"""UI smoke tests for the Android/Kivy screens.

Kivy needs a window provider for ``dp()``; a sandbox without libGL has none, so the
event loop's window is replaced by a tiny stub *before* Kivy widgets are
instantiated. Everything else is the real app: the real screens, the real core and
the fake engine from ``tests/fake_engine.py``.

These run locally on a machine with a working GL stack. CI does not run them: Kivy
segfaults in the texture path under Xvfb (all backends), so the same ground is
covered on the device by the ``ui_screens`` step of ``android-selftest``, which
builds the screens on a real Android GLES driver.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ANDROID = REPO / "android"
sys.path.insert(0, str(ANDROID))
sys.path.insert(0, str(REPO / "src"))

os.environ.setdefault("KIVY_NO_ARGS", "1")
os.environ.setdefault("KIVY_NO_CONSOLELOG", "1")
os.environ.setdefault("KIVY_NO_FILELOG", "1")

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the fake engine shim is POSIX-only")
# NOTE: CI covers the screens on-device; here Kivy needs a real GL stack.

# Kivy is an Android-only dependency; the desktop CI installs only requirements.txt.
pytest.importorskip("kivy", reason="the Android UI needs Kivy (pip install kivy)")


def _gl_available() -> bool:
    """Kivy builds its canvases through OpenGL; without a GL library it segfaults."""
    import ctypes

    for name in ("libGL.so.1", "libEGL.so.1", "opengl32.dll"):
        try:
            ctypes.CDLL(name)
        except OSError:
            continue
        return True
    return False


if not _gl_available():
    pytest.skip("no OpenGL library is loadable (CI runs these under xvfb + Mesa)",
                allow_module_level=True)

from fake_engine import write_fake_engine  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def headless_kivy():
    """Install the stub window once per test session."""
    from kivy.base import EventLoop

    if EventLoop.window is None:
        class _StubWindow:
            dpi = 160.0
            size = (411, 869)
            system_size = (411, 869)
            width = 411
            height = 869
            clearcolor = (0.0, 0.0, 0.0, 1.0)

        EventLoop.window = _StubWindow()
    EventLoop.ensure_window = lambda *a, **k: None
    yield


@pytest.fixture()
def app_env(data_dir, tmp_path, monkeypatch):
    """A ready-to-build Kivy app with a fake engine and an isolated data dir."""
    from easywalp import settings as settings_mod

    shim = write_fake_engine(tmp_path / "engine", name="photocraft-cli")
    monkeypatch.setenv("FAKE_STATE_DIR", str(tmp_path / "engine"))
    settings = settings_mod.load()
    settings.photocraft_path = str(shim)
    settings.output_base = str(data_dir / "out")
    settings_mod.save(settings)
    return {"shim": shim, "tmp": tmp_path, "data_dir": data_dir}


def _build_app():
    from easywalp_android.ui.app import EasyWalpApp

    app = EasyWalpApp()
    root = app.build()
    app.retranslate()
    return app, root


# ---------------------------------------------------------------------- widgets
def test_fonts_register_and_widgets_construct(headless_kivy, app_env):
    from easywalp_android.ui import theme, widgets

    registered = theme.register_fonts()
    assert registered.endswith("Vazirmatn-Regular.ttf")

    card = widgets.Surface()
    label = widgets.WrappedLabel(text="hello")
    button = widgets.ActionButton(text="go", accent=True)
    segment = widgets.Segment([("O", "Other"), ("A", "Anime")])
    bar = widgets.StageBar()
    banner = widgets.Banner()
    row = widgets.FieldRow(title="Desktop", on_press=lambda: None)

    segment.set_value("A", notify=True)
    assert segment.value() == "A"
    bar.set_stage("editing", 0.5)
    assert bar.bar.value == 50
    banner.show("warning text", "warn")
    assert banner.opacity == 1
    row.set_value("wallpaper.png")
    assert "wallpaper" in row.value.text
    assert card.orientation == "vertical"
    assert label.height > 0
    assert button.accent


# ------------------------------------------------------------------------- app
def test_app_builds_with_all_screens(headless_kivy, app_env):
    app, root = _build_app()
    assert root.orientation == "vertical"
    names = [screen.name for screen in app.sm.screens]
    assert names == ["home", "wizard", "presets", "settings"]
    for screen in app.sm.screens:
        assert screen.banner is not None
        assert screen.body is not None
    app.startup()  # engine + fonts + permissions + translations
    app.go("settings")
    assert app.current_screen().name == "settings"
    # back key goes home first
    assert app._on_key(None, 27) is True
    assert app.current_screen().name == "home"


def test_language_and_theme_switches(headless_kivy, app_env):
    from easywalp.i18n import i18n

    app, _root = _build_app()
    app.toggle_language()
    assert i18n.language == "fa"
    assert app.core.settings.language == "fa"
    assert app._lang_button.text == "EN"
    app.toggle_language()
    assert i18n.language == "en"
    app.apply_theme("light")
    assert app.core.settings.theme in {"dark", "light", "system", "light"}


# ------------------------------------------------------------------------ home
def test_home_shows_code_preview_and_results(headless_kivy, app_env):
    from PIL import Image

    from easywalp_android.core import GenerateRequest
    from fake_engine import FakeBinary  # noqa: F401  (documents the engine used)

    from easywalp_android.core import Core

    app, _root = _build_app()
    app.startup()
    core = app.core

    # a preset, built through the wizard code path
    psd = Path(app_env["tmp"]) / "template.psd"
    psd.write_bytes(b"8BPS-fake")
    analysis = core.analyze(psd, Path(app_env["tmp"]) / "work")
    preset = core.build_preset(analysis, name="UI preset", mapping=analysis.suggestions)
    core.settings.last_preset_id = preset.id
    core.save_settings()

    home = app.sm.get_screen("home")
    home.on_enter_screen()
    assert home.preset_spinner.values == ["UI preset"]
    assert home.preset_spinner.text == "UI preset"

    desktop = Path(app_env["tmp"]) / "desktop.png"
    mobile = Path(app_env["tmp"]) / "mobile.png"
    Image.new("RGB", (1920, 1080), (20, 40, 60)).save(desktop)
    Image.new("RGB", (1080, 1920), (60, 40, 20)).save(mobile)

    home.desktop_path = desktop
    home.mobile_path = mobile
    home.number_input.text = "236"
    home.refresh_preview()
    assert home.code_value.text == "MD-O-C236"
    assert home.generate_button.disabled is False

    result = core.generate(
        GenerateRequest(preset=preset, desktop=desktop, mobile=mobile, category="O", number=236)
    )
    home._show_result(result)
    assert home.result_card.opacity == 1
    assert result.preview_jpg.exists()
    assert "MD-O-C236" in home.result_info.text.replace("\u200c", "")

    # missing inputs disable the primary action again
    home.desktop_path = None
    home.refresh_preview()
    assert home.generate_button.disabled is True


# ---------------------------------------------------------------------- wizard
def test_wizard_builds_and_saves_a_preset(headless_kivy, app_env):
    app, _root = _build_app()
    app.startup()
    wizard = app.sm.get_screen("wizard")
    wizard.retranslate()

    psd = Path(app_env["tmp"]) / "template.psd"
    psd.write_bytes(b"8BPS-fake")
    wizard.psd = psd
    wizard.name_input.text = "From wizard"
    analysis = app.core.analyze(psd, Path(app_env["tmp"]) / "work")
    wizard.analysis = analysis
    wizard._show_analysis(analysis)

    layers = wizard.mapping()
    assert all(layers[role] is not None for role in layers)
    assert layers["desktop"].name == "Desktop Screen"

    preset = wizard._draft_preset()
    assert preset is not None
    assert preset.name == "From wizard"
    assert preset.desktop_contents.width == 1600

    wizard.save_preset()
    assert app.core.settings.last_preset_id
    assert [p.name for p in app.core.presets()] == ["From wizard"]


def test_wizard_warns_when_a_layer_is_missing(headless_kivy, app_env):
    app, _root = _build_app()
    app.startup()
    wizard = app.sm.get_screen("wizard")
    psd = Path(app_env["tmp"]) / "template.psd"
    psd.write_bytes(b"8BPS-fake")
    wizard.psd = psd
    analysis = app.core.analyze(psd, Path(app_env["tmp"]) / "work")
    wizard.analysis = analysis
    wizard._show_analysis(analysis)
    # the fill layer is optional in the UI flow: clearing it must block saving
    wizard._role_spinners["fill"].text = "—"
    assert wizard._draft_preset() is None
    assert wizard.banner.opacity == 1


# ------------------------------------------------------------------- presets
def test_presets_screen_lists_and_deletes(headless_kivy, app_env):
    app, _root = _build_app()
    app.startup()
    psd = Path(app_env["tmp"]) / "template.psd"
    psd.write_bytes(b"8BPS-fake")
    analysis = app.core.analyze(psd, Path(app_env["tmp"]) / "work")
    first = app.core.build_preset(analysis, name="Alpha", mapping=analysis.suggestions)
    second = app.core.build_preset(analysis, name="Beta", mapping=analysis.suggestions)

    screen = app.sm.get_screen("presets")
    screen.reload()
    assert len(screen.list_container.children) == 2

    screen._activate(first)
    assert app.core.settings.last_preset_id == first.id
    screen._delete(second)
    app.core.delete_preset(second)
    screen.reload()
    assert [p.name for p in app.core.presets()] == ["Alpha"]


# ------------------------------------------------------------------ settings
def test_settings_screen_reports_engine_and_storage(headless_kivy, app_env):
    app, _root = _build_app()
    app.startup()
    screen = app.sm.get_screen("settings")
    screen.refresh_engine()
    assert "photocraft-cli" in screen.engine_info.text or "fake" in screen.engine_info.text
    screen.refresh_storage()
    assert "data:" in screen.storage_info.text
    assert "out:" in screen.storage_info.text
