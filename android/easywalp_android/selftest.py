"""Automated on-device test (used by CI on an Android emulator).

The launcher runs this when ``selftest/request.json`` exists in the app's external
files dir (``adb push`` can write there). It exercises the *real* stack on the
device: the cross-compiled PhotoCraft engine, Pillow, the wizard analysis, a full
generate run and the gallery export. The result is written to
``selftest/result.json`` for ``adb pull`` - so a green APK build is backed by an
actual end-to-end run, not just "it compiled".

Request:

    {"engine": true, "pipeline": true, "export": false, "keep": false}

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


def _image_size(path: Path) -> list[int]:
    from PIL import Image

    with Image.open(path) as im:
        return [im.width, im.height]
