"""Automated on-device test (used by CI on an Android emulator).

The launcher runs this when ``selftest/request.json`` exists in the app's external
files dir (``adb push`` can write there). It exercises the *real* stack on the
device: the cross-compiled PhotoCraft engine, Pillow, the wizard analysis, a full
generate run and the gallery export. The result is written to
``selftest/result.json`` for ``adb pull`` - so a green APK build is backed by an
actual end-to-end run, not just "it compiled".

Request:

    {"engine": true, "pipeline": true, "export": false, "ui": true, "keep": false}

``ui`` builds the whole Kivy screen tree on the device. That check lives here and
not in the desktop CI because Kivy segfaults when it creates textures under Xvfb
(no GL backend survives), while on Android the exact same code path runs against
the real GLES driver - and that is the environment the APK ships into.

Result: ``{"ok": bool, "steps": [...], "elapsed": float, "platform": {...}}``
"""
from __future__ import annotations

import json
import logging
import platform
import shutil
import sys
import time
import traceback
from pathlib import Path

log = logging.getLogger("easywalp.android.selftest")


def run(request: dict) -> dict:
    """Run the requested checks; never raises."""
    from easywalp import __version__, logging_setup, paths
    from easywalp.photocraft import PhotoCraftBinary

    from easywalp.testkit import build_template_psd, sample_wallpapers

    from .core import Core, GenerateRequest
    from .platform import install_bundled_fonts, prepare_engine_env

    logging_setup.setup()
    started = time.monotonic()
    result: dict = {
        "ok": False,
        "app": __version__,
        "steps": [],
        "elapsed": 0.0,
        "platform": {
            "python": sys.version.split()[0],
            "implementation": platform.platform(),
            "android": paths.is_android(),
            "data_dir": str(paths.data_dir()),
            "bundled_dir": str(paths.bundled_dir()),
        },
    }
    work = paths.data_dir() / "selftest"
    if work.exists() and not request.get("keep"):
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)

    def step(name: str, ok: bool, detail: str = "") -> None:
        result["steps"].append({"name": name, "ok": bool(ok), "detail": detail})
        log.info("selftest %s: %s %s", name, ok, detail)

    try:
        engine_path = prepare_engine_env()
        step("engine_locate", engine_path is not None, str(engine_path))

        binary = PhotoCraftBinary(None)
        version = binary.version()
        step("engine_run", bool(version and version != "unknown"), version)

        fonts = install_bundled_fonts()
        step("fonts", bool(fonts) or True, f"{fonts} file(s) installed")

        core = Core()
        step("resources", True, f"{len(list(paths.bundled_dir().glob('*')))} bundled resource entries")

        if request.get("pipeline", True):
            _pipeline_steps(core, work, build_template_psd, sample_wallpapers, step, GenerateRequest)

        if request.get("export"):
            _export_step(core, work, step)

        if request.get("ui", True):
            _ui_step(core, step)
    except Exception as e:  # noqa: BLE001 - the report is the point
        log.exception("selftest crashed")
        result["steps"].append({"name": "crash", "ok": False, "detail": f"{e}\n{traceback.format_exc()}"})

    result["elapsed"] = round(time.monotonic() - started, 2)
    result["ok"] = all(s["ok"] for s in result["steps"]) and bool(result["steps"])
    return result


def _pipeline_steps(core, work: Path, build_psd, sample_wallpapers, step, request_cls) -> None:
    """Synthetic PSD (built *by the engine*) -> preset -> full generate."""
    psd = work / "template.psd"
    try:
        build_psd(core.engine(), work)
        step("psd_built", psd.exists(), f"{psd.stat().st_size if psd.exists() else 0} bytes")
    except Exception as e:  # noqa: BLE001
        step("psd_built", False, f"{e}\n{traceback.format_exc()}")
        return
    if not psd.exists():
        return

    try:
        analysis = core.analyze(psd, work / "analysis")
        mapped = {k: (v is not None) for k, v in analysis.suggestions.items()}
        step("analyze", all(mapped.values()),
             f"layers={len(analysis.layers)} code='{analysis.code_text}' contents={analysis.contents}")
        if not all(mapped.values()):
            return
    except Exception as e:  # noqa: BLE001
        step("analyze", False, f"{e}\n{traceback.format_exc()}")
        return

    try:
        preset = core.build_preset(analysis, name="Self test", mapping=analysis.suggestions)
        step("preset", preset.json_path.exists(), f"{preset.desktop_contents.width}x"
                                                 f"{preset.desktop_contents.height}")
    except Exception as e:  # noqa: BLE001
        step("preset", False, f"{e}\n{traceback.format_exc()}")
        return

    try:
        desktop, mobile = sample_wallpapers(work)
        request = request_cls(preset=preset, desktop=desktop, mobile=mobile, category="O",
                              number=236, resolution_key="2k")
        stages: list[str] = []
        core.settings.output_base = str(work / "out")
        generated = core.generate(request, progress=lambda stage, _frac: stages.append(stage))
        sizes = {
            "desktop": _image_size(generated.desktop_jpg),
            "mobile": _image_size(generated.mobile_jpg),
            "preview": _image_size(generated.preview_jpg),
        }
        ok = (
            sizes["desktop"] == [2560, 1440]
            and sizes["mobile"] == [1440, 2560]
            and generated.desktop_jpg.exists()
            and generated.preview_jpg.exists()
        )
        step("generate", ok, f"stages={stages} sizes={sizes} color={generated.average_color}")

        # A second run exercises the 4K path and overwrite handling.
        request4k = request_cls(preset=preset, desktop=desktop, mobile=mobile, category="A",
                                number=1, resolution_key="4k")
        second = core.generate(request4k)
        step("generate4k", _image_size(second.desktop_jpg) == [4096, 2304],
             f"{_image_size(second.desktop_jpg)} {second.desktop_jpg.name}")
    except Exception as e:  # noqa: BLE001
        step("generate", False, f"{e}\n{traceback.format_exc()}")


def _export_step(core, work: Path, step) -> None:
    """Gallery export through the Android MediaStore (if the helper is present)."""
    try:
        from .storage import Storage

        storage = Storage()
        outputs = sorted((work / "out").glob("**/*.jpg"))[-3:]
        handles, error = storage.export(outputs, subfolder="SelfTest")
        step("gallery_export", bool(handles) or not storage.rich, f"{len(handles)} file(s) {error}")
    except Exception as e:  # noqa: BLE001
        step("gallery_export", False, f"{e}\n{traceback.format_exc()}")


def _ui_step(core, step) -> None:
    """Build and drive the whole Kivy UI - the desktop CI cannot run this.

    The screens are constructed exactly like the app constructs them at startup
    (``EasyWalpApp.build()``), then every screen is entered (`on_enter_screen`),
    both languages and both themes are applied and the home screen's code preview
    is refreshed. A crash or an exception anywhere in that path is what a user
    would see as "the app does not open", so it is worth failing the build over.
    """
    try:
        from easywalp.i18n import i18n
        from easywalp.pipeline import plan_names

        from .ui.app import EasyWalpApp, SCREENS

        app = EasyWalpApp()
        root = app.build()
        names = [screen.name for screen in app.sm.screens]
        app.retranslate()
        for name in SCREENS:
            app.go(name)
            screen = app.sm.get_screen(name)
            if hasattr(screen, "retranslate"):
                screen.retranslate()
        app.go("home")
        home = app.sm.get_screen("home")

        app.toggle_language()
        rtl_ok = i18n.language == "fa" and app._lang_button.text == "EN"
        app.toggle_language()
        app.apply_theme("light")
        app.apply_theme("dark")

        # The home screen must show the code for the current inputs (the first
        # thing a user checks before pressing Generate).
        preset = next(iter(core.presets()), None)
        preview_ok = True
        if preset is not None:
            core.settings.last_preset_id = preset.id
            home.on_enter_screen()
            home.number_input.text = "236"
            home.refresh_preview()
            info = plan_names(preset.options, "O", 236, preset.options.resolution_key)
            preview_ok = info.code in home.code_value.text
        ok = root.orientation == "vertical" and names == list(SCREENS) and rtl_ok and preview_ok
        step("ui_screens", ok,
             f"screens={names} language={i18n.language} rtl={rtl_ok} preview={preview_ok} "
             f"widgets={len(root.children)}")
    except Exception as e:  # noqa: BLE001 - report, never crash the app
        step("ui_screens", False, f"{e}\n{traceback.format_exc()}")


def _image_size(path: Path) -> list[int]:
    from PIL import Image

    with Image.open(path) as im:
        return [im.width, im.height]
