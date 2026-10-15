"""End-to-end GUI flow tests: the real widgets, the real core, the fake engine.

The sandbox that writes this code cannot load Qt at all, so the desktop GUI is
exercised on CI (offscreen Qt) - which is exactly where the "never executed" bugs
live: buttons created without their text, a wizard whose pages were built but never
added to the stack. Everything here drives the *real* dialogs and the *real* pipeline.

QMessageBox is stubbed out: a modal box would hang a headless test run.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

pytestmark = [
    pytest.mark.gui,
    pytest.mark.skipif(sys.platform == "win32", reason="the fake engine shim is POSIX-only"),
]

from fake_engine import write_fake_engine  # noqa: E402


class QuietBox:
    """Records what the UI wanted to tell the user instead of blocking on it."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def warning(self, _parent=None, title="", text="", *a, **k):
        self.calls.append(("warning", f"{title} {text}"))
        return None

    def information(self, _parent=None, title="", text="", *a, **k):
        self.calls.append(("info", f"{title} {text}"))
        return None

    def critical(self, _parent=None, title="", text="", *a, **k):
        self.calls.append(("critical", f"{title} {text}"))
        return None

    def question(self, *a, **k):
        from PySide6.QtWidgets import QMessageBox

        return QMessageBox.StandardButton.Yes


@pytest.fixture(scope="module")
def qapp():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
    except (ImportError, OSError) as e:  # pragma: no cover - no Qt here
        pytest.skip(f"Qt cannot load here: {e}")
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def i18n_en():
    from easywalp.i18n import i18n

    i18n.load_all()
    i18n.set_language("en")
    yield i18n
    i18n.set_language("en")


@pytest.fixture()
def quiet_box(monkeypatch):
    box = QuietBox()
    for module in (
        "easywalp.app.mainwindow",
        "easywalp.app.wizard",
        "easywalp.app.presets_dialog",
        "easywalp.app.dialogs",
    ):
        monkeypatch.setattr(f"{module}.QMessageBox", box)
    return box


@pytest.fixture()
def engine_env(data_dir, tmp_path, monkeypatch):
    """A fake engine wired into the settings the dialogs read."""
    from easywalp import settings as settings_mod

    shim = write_fake_engine(tmp_path / "engine")
    monkeypatch.setenv("FAKE_STATE_DIR", str(tmp_path / "engine"))
    settings = settings_mod.load()
    settings.photocraft_path = str(shim)
    settings.output_base = str(data_dir / "out")
    settings_mod.save(settings)
    return {"shim": shim, "dir": tmp_path, "settings": settings, "data": data_dir}


@pytest.fixture()
def psd(tmp_path):
    """The fake engine never opens the file, but a preset stores it as its template."""
    path = tmp_path / "wallify-template.psd"
    path.write_bytes(b"8BPS" + b"\x00" * 64)
    return path


def _binary(engine_env):
    from easywalp.photocraft import PhotoCraftBinary

    return PhotoCraftBinary(str(engine_env["shim"]))


def _inspect(engine_env, preset):
    from easywalp.wizard import inspect_psd

    return inspect_psd(_binary(engine_env), preset.template_path)


def _preset_from_fake_engine(engine_env, psd, name="GUI preset"):
    """Create a preset the way the wizard does, without the widget layer."""
    from easywalp import __version__
    from easywalp.presets import LayerRef, detect_code_span, import_psd_as_preset, split_code_text
    from easywalp.wizard import smart_object_contents, text_layer_info, top_level_layers

    psd.parent.mkdir(parents=True, exist_ok=True)
    if not psd.exists():
        psd.write_bytes(b"8BPS" + b"\x00" * 64)
    binary = _binary(engine_env)
    preset = import_psd_as_preset(psd, name, __version__)
    candidates = top_level_layers(_inspect(engine_env, preset))
    smart = [c for c in candidates if c.kind == "Smart Object"]
    fills = [c for c in candidates if c.kind == "Fill"]
    texts = [c for c in candidates if c.kind == "Type"]
    assert len(smart) >= 2 and fills and texts, "the fake document must offer every layer kind"

    def ref(candidate):
        return LayerRef(candidate.id, candidate.name, candidate.kind)

    preset.desktop_smart_object = ref(smart[0])
    preset.mobile_smart_object = ref(smart[1])
    preset.solid_color_fill = ref(fills[0])
    preset.text_layer = ref(texts[0])
    for role, layer in (("desktop", preset.desktop_smart_object), ("mobile", preset.mobile_smart_object)):
        w, h, _name = smart_object_contents(binary, preset.template_path, layer, preset.dir / "probe")
        target = preset.desktop_contents if role == "desktop" else preset.mobile_contents
        target.width, target.height = w, h
    text = str(text_layer_info(binary, preset.template_path, preset.text_layer).get("text", ""))
    span = detect_code_span(text)
    assert span, f"the fake document's text layer has no code: {text!r}"
    preset.text_code = split_code_text(text, span)
    preset.save()
    return preset


# ------------------------------------------------------------------- main window
def test_main_window_constructs_with_its_result_row(qapp, data_dir, engine_env, sample_images, i18n_en, quiet_box):
    from easywalp.app.mainwindow import MainWindow

    win = MainWindow()
    win.apply_theme()
    win.apply_language()
    assert win.windowTitle() == "EasyWalp"
    assert win.preset_combo.count() == 0  # no presets yet
    assert not win.generate_btn.isEnabled()
    # every result button carries its label (they are translated in apply_language)
    assert win.open_folder_btn.text() == i18n_en.tr("main.openFolder")
    assert win.copy_code_btn.text() == i18n_en.tr("main.copyCode")
    assert win.open_preview_btn.text() == i18n_en.tr("main.openPreview")
    assert win.result_widget.isHidden()


def test_main_window_runs_the_whole_generation_flow(
    qapp, data_dir, engine_env, sample_images, i18n_en, quiet_box
):
    from PySide6.QtWidgets import QApplication

    from easywalp.app.mainwindow import MainWindow
    from easywalp.pipeline import Pipeline

    desktop, mobile = sample_images
    preset = _preset_from_fake_engine(engine_env, data_dir / "psd" / "template.psd", name="Wallify")

    win = MainWindow()
    win.reload_presets(preset.id)
    assert win.preset_combo.currentData() == preset.id
    assert win.current_preset().name == "Wallify"

    win.desktop_zone.set_image(desktop)
    win.mobile_zone.set_image(mobile)
    win.category_toggle.set_value("O")
    win.resolution_toggle.set_value("2k")
    win.number_spin.setValue(236)
    win.out_edit.setText(str(data_dir / "out"))
    win._update_preview()
    assert win.generate_btn.isEnabled()
    assert win.code_card._code.text() == "MD-O-C236"
    assert "MD-O-C236" in win.code_card._rows.text()

    result = Pipeline(_binary(engine_env)).generate(preset, desktop, mobile, "O", 236, data_dir / "out")
    win._on_success(result)
    assert not win.result_widget.isHidden()
    assert win.last_result is result
    assert "MD-O-C236" in win.result_info.text()
    assert win.progress.value() == 100

    win._copy_code()
    assert QApplication.clipboard().text() == "MD-O-C236"

    # a click without both images must warn (not start a worker)
    win.desktop_zone.set_image(None)
    win._generate()
    assert win.worker is None
    assert any("warning" == kind for kind, _text in quiet_box.calls)


# ---------------------------------------------------------------------- wizard
def test_wizard_navigates_every_page_and_saves(
    qapp, data_dir, engine_env, i18n_en, psd, quiet_box, monkeypatch
):
    from easywalp.app.wizard import WizardDialog
    from easywalp.presets import Preset, import_psd_as_preset, split_code_text

    dialog = WizardDialog(engine_env["settings"], _binary(engine_env))
    # regression: all four pages must be in the stack, not only the first one
    assert dialog.stack.count() == 4

    preset = import_psd_as_preset(psd, psd.stem, "0.0.0")
    # the dialog normally analyzes in a worker thread; feed it the result directly
    monkeypatch.setattr(dialog, "_start_thumbnails", lambda: None)
    monkeypatch.setattr(dialog, "_probe_contents", lambda: None)
    dialog.psd_edit.setText(str(psd))
    dialog._analyzed_ok((preset, _inspect(engine_env, preset)))
    assert dialog.stack.currentIndex() == 1
    assert dialog.so_desktop_combo.count() >= 2
    assert dialog.so_mobile_combo.count() >= 2
    assert dialog.fill_combo.count() >= 1
    assert dialog.text_combo.count() >= 1

    ok, problems = dialog._apply_mapping()
    assert ok, problems
    assert dialog.preset.desktop_smart_object is not None
    assert dialog.preset.solid_color_fill.kind == "Fill"

    dialog.stack.setCurrentIndex(2)
    dialog._text_ok({"text": "Code:MD-O-C236", "font": "Vazirmatn", "sizePt": 72})
    assert dialog.text_view.text() == "Code:MD-O-C236"
    assert dialog._apply_code_span() is True
    assert dialog.preset.text_code == split_code_text("Code:MD-O-C236", (5, 14))

    dialog.stack.setCurrentIndex(3)
    dialog._contents_ok({"desktop": (1600, 900), "mobile": (900, 1600)})
    status = dialog.finish_status.text()
    assert "1600×900" in status and "900×1600" in status

    dialog._save_and_close()
    assert dialog._saved is True
    assert [p.name for p in Preset.load_all()] == [psd.stem]


def test_wizard_warns_instead_of_saving_without_a_layer(
    qapp, data_dir, engine_env, i18n_en, psd, quiet_box, monkeypatch
):
    from easywalp.app.wizard import WizardDialog
    from easywalp.presets import Preset, import_psd_as_preset

    dialog = WizardDialog(engine_env["settings"], _binary(engine_env))
    monkeypatch.setattr(dialog, "_start_thumbnails", lambda: None)
    preset = import_psd_as_preset(psd, "warn me", "0.0.0")
    dialog._analyzed_ok((preset, _inspect(engine_env, preset)))

    dialog.fill_combo.setCurrentIndex(-1)  # the user cleared the fill layer
    ok, problems = dialog._apply_mapping()
    assert ok is False and problems
    assert dialog.next_btn.isEnabled() is False

    dialog._cancel()
    assert Preset.load_all() == []


# --------------------------------------------------------------------- dialogs
def test_settings_dialog_finds_the_engine(qapp, data_dir, engine_env, i18n_en, quiet_box):
    from easywalp.app.dialogs import SettingsDialog
    from easywalp import settings as settings_mod

    dialog = SettingsDialog(engine_env["settings"])
    dialog._detect_engine(quiet=True)
    assert str(engine_env["shim"]) in dialog.engine_edit.text()
    assert "fake" in dialog.engine_status.text() or "photocraft-cli" in dialog.engine_status.text()

    dialog.fa_digits.setChecked(True)
    dialog.theme_combo.setCurrentIndex(1)
    dialog.apply()
    settings_mod.save(dialog.settings)
    saved = settings_mod.load()
    assert saved.language == dialog.lang_combo.currentData()
    assert saved.theme == dialog.theme_combo.currentData()
    assert saved.persian_digits is True


def test_presets_dialog_lists_and_exports(qapp, data_dir, engine_env, i18n_en, psd, quiet_box, monkeypatch):
    from easywalp.app.presets_dialog import PresetsDialog
    from easywalp.presets import Preset

    first = _preset_from_fake_engine(engine_env, psd, name="Alpha")
    second = _preset_from_fake_engine(engine_env, psd.parent / "second.psd", name="Beta")
    assert first.id != second.id

    dialogue = PresetsDialog(engine_env["settings"], _binary(engine_env), lambda: None)
    assert dialogue.list.count() == 2
    assert dialogue.export_btn.isEnabled() is True

    target = data_dir / "exports" / "Beta.easywalp"

    class FakeFileDialog:
        @staticmethod
        def getSaveFileName(*_a, **_k):
            return str(target), ""

        @staticmethod
        def getOpenFileName(*_a, **_k):
            return "", ""

    monkeypatch.setattr("easywalp.app.presets_dialog.QFileDialog", FakeFileDialog)
    dialogue.list.setCurrentRow(1)
    assert dialogue._current().name == "Beta"
    dialogue._export()
    assert target.is_file()
    # exporting must not disturb the installed presets
    assert sorted(p.name for p in Preset.load_all()) == ["Alpha", "Beta"]


# --------------------------------------------------- page 1: the Analyze buttons
def _pump(qapp, condition, timeout=20.0):
    """Spin the event loop until `condition()` - worker threads deliver via signals."""
    import time

    deadline = time.monotonic() + timeout
    ok = False
    while time.monotonic() < deadline:
        qapp.processEvents()
        if condition():
            ok = True
            break
        time.sleep(0.02)
    # let the worker thread finish and clean itself up before the dialog goes away
    for _ in range(5):
        qapp.processEvents()
        time.sleep(0.02)
    return ok


def test_page_one_has_a_live_analyze_button(qapp, data_dir, engine_env, i18n_en, psd, quiet_box, monkeypatch):
    """The button the user could not press.

    Two separate faults made it dead: the inline button next to Browse was created and
    connected but never added to the layout (so it was not on screen at all), and the
    "Analyze PSD" button in the nav row was decided once, when the dialog was built -
    a path typed or pasted into the field afterwards never re-enabled it.
    """
    from easywalp.app.wizard import WizardDialog

    dialog = WizardDialog(engine_env["settings"], _binary(engine_env))
    page = dialog.stack.widget(0)

    # the inline button is really part of the page
    assert dialog._analyze_btn.parent() is page
    # nothing chosen yet -> nothing to analyze
    assert dialog.next_btn.isEnabled() is False
    assert dialog._analyze_btn.isEnabled() is False

    # a path typed by the user (not picked in the file dialog) must enable both
    dialog.psd_edit.setText(str(psd))
    assert dialog._analyze_btn.isEnabled() is True
    assert dialog.next_btn.isEnabled() is True

    dialog.psd_edit.clear()
    assert dialog.next_btn.isEnabled() is False

    # and pressing that button actually analyzes and moves on to page 2
    dialog.psd_edit.setText(str(psd))
    monkeypatch.setattr(dialog, "_start_thumbnails", lambda: None)
    dialog.next_btn.click()
    assert _pump(qapp, lambda: dialog.stack.currentIndex() == 1), "the analyze never finished"
    assert dialog.preset is not None
    assert dialog.candidates, "no layers were read from the PSD"


def test_page_one_analyze_keys(qapp, data_dir, engine_env, i18n_en, psd, quiet_box, monkeypatch):
    """Enter in the path field is the same as pressing Analyze PSD."""
    from easywalp.app.wizard import WizardDialog

    dialog = WizardDialog(engine_env["settings"], _binary(engine_env))
    monkeypatch.setattr(dialog, "_start_thumbnails", lambda: None)
    dialog.psd_edit.setText(str(psd))
    dialog.psd_edit.returnPressed.emit()
    assert _pump(qapp, lambda: dialog.stack.currentIndex() == 1), "Enter did not analyze"


def test_page_one_recovers_from_a_missing_or_broken_psd(
    qapp, data_dir, engine_env, i18n_en, tmp_path, psd, quiet_box, monkeypatch
):
    """A wrong path, or a PSD the engine rejects, must leave the button pressable."""
    from easywalp.app.wizard import WizardDialog

    dialog = WizardDialog(engine_env["settings"], _binary(engine_env))

    missing = tmp_path / "renamed-or-deleted.psd"
    dialog.psd_edit.setText(str(missing))
    dialog.next_btn.click()
    assert quiet_box.calls and "renamed-or-deleted.psd" in quiet_box.calls[-1][1]
    assert dialog.stack.currentIndex() == 0
    assert dialog.next_btn.isEnabled() is True
    assert dialog._analyze_btn.isEnabled() is True

    # the engine blows up on this one: buttons come back and the wizard stays put
    import easywalp.app.wizard as wizard_mod

    def boom(*_a, **_k):
        raise RuntimeError("not a photoshop file")

    reported = []
    monkeypatch.setattr(WizardDialog, "_default_fail",
                        lambda _self, title, details: reported.append((title, details)))
    monkeypatch.setattr(wizard_mod.wiz, "inspect_psd", boom)
    monkeypatch.setattr(dialog, "_start_thumbnails", lambda: None)
    dialog.psd_edit.setText(str(psd))
    dialog.next_btn.click()
    assert _pump(qapp, lambda: bool(reported)), "the failure was never reported"
    assert "photoshop" in str(reported[-1])
    assert dialog.stack.currentIndex() == 0
    assert dialog.next_btn.isEnabled() is True
    assert dialog._analyze_btn.isEnabled() is True
    # and the clone that failed halfway is not left behind as an empty preset
    from easywalp.presets import Preset

    assert Preset.load_all() == []
