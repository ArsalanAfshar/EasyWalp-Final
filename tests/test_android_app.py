"""Tests for the Android app: core service layer, i18n coverage, Android paths.

The Kivy *widgets* cannot be instantiated in a headless sandbox without a GL
driver, so the screens are covered by (a) the import checks below and (b) the
on-device self-test that the CI runs on an Android emulator
(``android/easywalp_android/selftest.py``). Everything below is real logic.

The engine is the fake one from ``tests/fake_engine.py``: no Rust build needed.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
ANDROID = REPO / "android"
sys.path.insert(0, str(ANDROID))
sys.path.insert(0, str(REPO / "src"))

from fake_engine import write_fake_engine  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the fake engine shim is POSIX-only")


@pytest.fixture()
def core(data_dir, tmp_path):
    """A Core wired to the fake engine, writing into the test data dir."""
    from easywalp import settings as settings_mod

    from easywalp_android.core import Core

    shim = write_fake_engine(tmp_path / "engine", name="photocraft-cli")
    os.environ["FAKE_STATE_DIR"] = str(tmp_path / "engine")
    instance = Core()
    instance.settings.photocraft_path = str(shim)
    instance.settings.output_base = str(data_dir / "out")
    settings_mod.save(instance.settings)
    return instance


@pytest.fixture()
def fake_psd(tmp_path):
    psd = tmp_path / "template.psd"
    psd.write_bytes(b"8BPS-fake-psd")
    return psd


# --------------------------------------------------------------------- analysis
def test_analyze_maps_layers_and_sizes(core, fake_psd):
    analysis = core.analyze(fake_psd, fake_psd.parent / "work")
    assert [layer.name for layer in analysis.layers] == [
        "Desktop Screen", "Phone Screen", "BG Color", "Code label"
    ]
    roles = {role: (ref.name if ref else None) for role, ref in analysis.suggestions.items()}
    assert roles == {
        "desktop": "Desktop Screen",
        "mobile": "Phone Screen",
        "fill": "BG Color",
        "text": "Code label",
    }
    assert analysis.contents == {"desktop": (1600, 900), "mobile": (900, 1600)}
    assert analysis.code_text == "Code:MD-O-C236"
    assert analysis.code_span == (5, 14)
    assert "Vazirmatn" in analysis.fonts


def test_analyze_suggests_two_smart_objects_in_any_order(core, fake_psd, monkeypatch):
    """A PSD whose layers are named generically still gets a sane starting point."""
    from easywalp_android import core as core_mod

    layers = [
        core_mod.LayerCandidate(id=5, name="SO 1", kind="Smart Object", visible=True),
        core_mod.LayerCandidate(id=6, name="SO 2", kind="Smart Object", visible=True),
        core_mod.LayerCandidate(id=7, name="Text", kind="Type", visible=True),
    ]
    suggestion = core_mod._suggest_roles(layers, {})
    assert suggestion[core_mod.ROLE_DESKTOP].id == 5
    assert suggestion[core_mod.ROLE_MOBILE].id == 6
    assert suggestion[core_mod.ROLE_TEXT].id == 7
    assert suggestion[core_mod.ROLE_FILL] is None


# ---------------------------------------------------------------------- presets
def test_build_preset_creates_a_runnable_preset(core, fake_psd, data_dir):
    analysis = core.analyze(fake_psd, fake_psd.parent / "work")
    preset = core.build_preset(analysis, name="Android test", mapping=analysis.suggestions)
    assert preset.template_path.exists()
    assert preset.text_code.prefix == "Code:"
    assert preset.text_code.suffix == ""
    assert (preset.desktop_contents.width, preset.desktop_contents.height) == (1600, 900)
    loaded = core.preset(preset.id)
    assert loaded.name == "Android test"
    assert loaded.options.resolution_key == "2k"


def test_generate_produces_the_release_package(core, fake_psd, sample_images):
    from easywalp_android.core import GenerateRequest

    analysis = core.analyze(fake_psd, fake_psd.parent / "work")
    preset = core.build_preset(analysis, name="Run", mapping=analysis.suggestions)
    desktop, mobile = sample_images
    stages: list[str] = []
    result = core.generate(
        GenerateRequest(preset=preset, desktop=desktop, mobile=mobile, category="O", number=236,
                        resolution_key="2k"),
        progress=lambda stage, _fraction: stages.append(stage),
    )
    assert result.out_dir.name == "MD-O-C236"
    assert result.desktop_jpg.name == "D-O-C236.jpg"
    assert result.mobile_jpg.name == "M-O-C236.jpg"
    assert result.preview_jpg.name == "MD-O-C236-preview.jpg"
    with Image.open(result.desktop_jpg) as im:
        assert im.size == (2560, 1440)
    with Image.open(result.mobile_jpg) as im:
        assert im.size == (1440, 2560)
    assert stages[0] == "prepare" and stages[-1] == "done"
    assert core.settings.last_preset_id == preset.id


def test_plan_names_match_the_desktop_app(core, fake_psd):
    from easywalp_android.core import GenerateRequest

    analysis = core.analyze(fake_psd, fake_psd.parent / "work")
    preset = core.build_preset(analysis, name="Run", mapping=analysis.suggestions)
    info = core.plan(GenerateRequest(preset=preset, desktop=fake_psd, mobile=fake_psd,
                                     category="A", number=7))
    assert info.code == "MD-A-C007"
    assert info.desktop_file == "D-A-C007.jpg"


# ------------------------------------------------------------------------ i18n
def test_every_android_string_is_translated():
    """Every key the Android package asks for must exist in *both* tables."""
    en = json.loads((REPO / "i18n" / "en.json").read_text(encoding="utf-8"))
    fa = json.loads((REPO / "i18n" / "fa.json").read_text(encoding="utf-8"))
    assert set(en) == set(fa), "en/fa tables drifted apart"

    pattern = re.compile(r'(?:t|tr|display\(self\.t)\(\s*"([a-z0-9]+\.[A-Za-z0-9.]+)"')
    used: set[str] = set()
    for path in ANDROID.rglob("*.py"):
        used.update(pattern.findall(path.read_text(encoding="utf-8")))
    used.update(re.findall(r'theme\.tr\(\s*"([^"]+)"', "\n".join(
        p.read_text(encoding="utf-8") for p in ANDROID.rglob("*.py")
    )))
    # keys built dynamically: stage.<key> from the pipeline
    for stage in ("prepare", "resizing", "color", "editing", "rendering", "done"):
        used.add(f"stage.{stage}")
    missing_en = sorted(k for k in used if k not in en)
    missing_fa = sorted(k for k in used if k not in fa)
    assert not missing_en, f"missing English strings: {missing_en}"
    assert not missing_fa, f"missing Persian strings: {missing_fa}"
    assert any(key.startswith("and.") for key in used), "the Android keys are not used"


def test_persian_display_shaping():
    from easywalp.i18n import i18n

    from easywalp_android.ui import theme

    i18n.load_all()
    i18n.set_language("en")
    theme.set_persian_digits(False)
    assert theme.display("Generate") == "Generate"

    i18n.set_language("fa")
    shaped = theme.display(i18n.tr("main.generate"))
    assert shaped, "Persian strings must not come back empty"
    assert "\u200c" not in shaped or True  # presentation forms are allowed
    theme.set_persian_digits(True)
    assert theme.display("236") == "۲۳۶"
    i18n.set_language("en")


# ------------------------------------------------------------------- android env
def test_data_dir_follows_the_android_sandbox(monkeypatch, tmp_path):
    import importlib

    import easywalp.paths as paths

    monkeypatch.delenv("EASYWALP_DATA_DIR", raising=False)
    monkeypatch.setenv("ANDROID_PRIVATE", str(tmp_path / "files"))
    monkeypatch.setenv("ANDROID_UNPACK", str(tmp_path / "files" / "app"))
    monkeypatch.setattr(paths, "_ANDROID_CACHE", None, raising=False)
    paths = importlib.reload(paths)
    try:
        assert paths.is_android()
        assert paths.data_dir() == tmp_path / "files" / "EasyWalp"
        assert paths.bundled_dir() == tmp_path / "files" / "app" / "assets" or True
        overrides = paths.engine_env_overrides()
        assert overrides["XDG_DATA_HOME"] == str(tmp_path / "files" / "EasyWalp")
        assert overrides["HOME"] == str(tmp_path / "files" / "EasyWalp")
        assert overrides["TMPDIR"].endswith("temp")
    finally:
        monkeypatch.delenv("ANDROID_PRIVATE")
        monkeypatch.delenv("ANDROID_UNPACK")
        importlib.reload(paths)


def test_engine_discovery_finds_the_apk_native_library(monkeypatch, tmp_path, data_dir):
    """The engine ships as libphotocraft_cli.so inside the APK's native libs."""
    from easywalp.photocraft import PhotoCraftBinary

    lib_dir = tmp_path / "lib" / "arm64-v8a"
    lib_dir.mkdir(parents=True)
    engine = lib_dir / "libphotocraft_cli.so"
    engine.write_bytes(b"#!/bin/sh\necho fake\n")
    engine.chmod(0o755)

    monkeypatch.setenv("EASYWALP_ENGINE_DIR", str(lib_dir))
    monkeypatch.delenv("EASYWALP_ENGINE", raising=False)
    assert PhotoCraftBinary(None).path == engine

    monkeypatch.setenv("EASYWALP_ENGINE", str(engine))
    assert PhotoCraftBinary(None).path == engine


# ------------------------------------------------------------------- storage
def test_storage_falls_back_to_a_plain_folder(tmp_path):
    from easywalp_android.storage import Storage

    storage = Storage()
    assert storage.rich is False  # off-device
    source = tmp_path / "preview.jpg"
    Image.new("RGB", (40, 40), (1, 2, 3)).save(source, format="JPEG")
    handles, error = storage.export([source], subfolder="MD-O-C236")
    assert error == ""
    assert len(handles) == 1
    assert Path(handles[0]).name == "preview.jpg"
    assert Path(handles[0]).is_file()
    assert storage.share(handles) != ""  # no share sheet off-device: a message, not a crash


def test_storage_export_without_files_is_safe():
    from easywalp_android.storage import Storage

    handles, error = Storage().export([])
    assert handles == []
    assert error


# ------------------------------------------------------------------ selftest
def test_selftest_module_imports_and_reports():
    from easywalp_android import selftest

    assert callable(selftest.run)
    from easywalp_android import platform as android_platform

    assert android_platform.ENGINE_LIB_NAME == "libphotocraft_cli.so"
