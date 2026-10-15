"""Android integration: engine location, fonts, permissions, intent handshake.

Everything here is defensive: on a desktop interpreter (used by the test suite)
every function returns ``None``/``False`` instead of importing ``jnius``, so
``easywalp_android`` can be imported and unit-tested anywhere.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

log = logging.getLogger("easywalp.android.platform")

#: the engine is shipped as a native library so Android extracts it with +x
ENGINE_LIB_NAME = "libphotocraft_cli.so"
SELFTEST_DIR_NAME = "selftest"


def is_android() -> bool:
    from easywalp.paths import is_android as _is_android

    return _is_android()


def _activity():
    """The running ``PythonActivity`` (or None off-device)."""
    try:
        from jnius import autoclass

        return autoclass("org.kivy.android.PythonActivity").mActivity
    except Exception as e:  # noqa: BLE001 - jnius is absent off-device
        log.debug("no Android activity: %s", e)
        return None


def api_level() -> int:
    """Android API level (0 when not on Android)."""
    activity = _activity()
    if activity is None:
        return 0
    try:
        from jnius import autoclass

        return int(autoclass("android.os.Build$VERSION").SDK_INT)
    except Exception:  # noqa: BLE001
        return 0


def device_model() -> str:
    activity = _activity()
    if activity is None:
        return "desktop"
    try:
        from jnius import autoclass

        build = autoclass("android.os.Build")
        return f"{build.MANUFACTURER} {build.MODEL} (Android {autoclass('android.os.Build$VERSION').RELEASE})"
    except Exception:  # noqa: BLE001
        return "android"


def native_library_dir() -> Path | None:
    """``ApplicationInfo.nativeLibraryDir`` - where Android extracted our libs."""
    activity = _activity()
    if activity is None:
        return None
    try:
        path = activity.getApplicationInfo().nativeLibraryDir
        return Path(str(path)) if path else None
    except Exception as e:  # noqa: BLE001
        log.warning("nativeLibraryDir unavailable: %s", e)
        return None


def external_files_dir() -> Path | None:
    """``/sdcard/Android/data/<pkg>/files`` - adb can read/write it (self-test handshake)."""
    activity = _activity()
    if activity is None:
        return None
    try:
        f = activity.getExternalFilesDir(None)
        return Path(str(f.getAbsolutePath())) if f else None
    except Exception as e:  # noqa: BLE001
        log.warning("external files dir unavailable: %s", e)
        return None


def prepare_engine_env() -> Path | None:
    """Point EasyWalp's engine discovery at the APK's extracted engine binary.

    The engine is packaged as ``lib/arm64-v8a/libphotocraft_cli.so``; Android only
    extracts *native libraries* with execute permission (files inside the app's
    writable data dir cannot be executed since Android 10), so this is the one
    place the engine can live and still be launched with ``subprocess``.
    """
    lib_dir = native_library_dir()
    if lib_dir:
        os.environ["EASYWALP_ENGINE_DIR"] = str(lib_dir)
        candidate = lib_dir / ENGINE_LIB_NAME
        if candidate.is_file():
            os.environ["EASYWALP_ENGINE"] = str(candidate)
            log.info("engine: %s", candidate)
            return candidate
    # Off-device (or a development build): fall back to the normal lookup.
    from easywalp.paths import data_dir, engines_dir

    for folder in (engines_dir(), data_dir() / "engines"):
        for name in ("libphotocraft_cli.so", "photocraft-cli"):
            candidate = folder / name
            if candidate.is_file():
                os.environ["EASYWALP_ENGINE"] = str(candidate)
                return candidate
    log.warning("no engine binary found")
    return None


def install_bundled_fonts() -> int:
    """Copy the bundled Vazirmatn faces into the folder the engine scans.

    PhotoCraft looks for fonts in ``$XDG_DATA_HOME/fonts`` (among others) and the
    Android launcher points ``XDG_DATA_HOME`` at EasyWalp's data dir - so text in
    the mockup uses exactly the same face as on Windows, even though Android's own
    font set is different.
    """
    from easywalp import paths

    target = paths.fonts_dir()
    sources: list[Path] = []
    bundled = paths.bundled_dir() / "fonts"
    if bundled.is_dir():
        sources += sorted(p for p in bundled.iterdir() if p.suffix.lower() in {".ttf", ".otf"})
    sources += sorted(paths.fonts_dir().glob("*.ttf"))  # already-imported fonts stay
    copied = 0
    for src in sources:
        if src.parent == target:
            continue
        dest = target / src.name
        if dest.exists() and dest.stat().st_size == src.stat().st_size:
            continue
        try:
            shutil.copyfile(src, dest)
            copied += 1
        except OSError as e:
            log.warning("font copy failed (%s): %s", src.name, e)
    if copied:
        log.info("installed %d bundled font file(s) into %s", copied, target)
    return copied


def import_font(source: Path) -> Path:
    """Copy a user-picked font file into the scanned font folder."""
    from easywalp import paths

    if source.suffix.lower() not in {".ttf", ".otf", ".ttc"}:
        raise ValueError("only .ttf/.otf/.ttc font files are supported")
    dest = paths.fonts_dir() / source.name
    shutil.copyfile(source, dest)
    return dest


def request_permissions() -> None:
    """Ask for the legacy storage permission on Android <= 9 (a no-op elsewhere)."""
    if not is_android():
        return
    try:
        from android.permissions import Permission, check_permission, request_permissions as _req

        permission = getattr(Permission, "WRITE_EXTERNAL_STORAGE", "android.permission.WRITE_EXTERNAL_STORAGE")
        if not check_permission(permission):
            _req([permission])
    except Exception as e:  # noqa: BLE001
        log.debug("permission request skipped: %s", e)


def startup_banner() -> str:
    """A one-line description of the runtime, shown in Settings/About."""
    from easywalp import __version__

    if not is_android():
        return f"EasyWalp {__version__} (development build)"
    level = api_level()
    return f"EasyWalp {__version__} - Android API {level} - {device_model()}"


# ---------------------------------------------------------------- self-test
def selftest_dir() -> Path | None:
    """Folder used for the automated on-device test (external files dir first)."""
    for root in (external_files_dir(), _private_files_dir()):
        if root is None:
            continue
        candidate = root / SELFTEST_DIR_NAME
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        return candidate
    return None


def _private_files_dir() -> Path | None:
    value = os.getenv("ANDROID_PRIVATE")
    return Path(value) if value else None


def selftest_request() -> dict | None:
    """Read ``selftest/request.json`` when an automated run was requested."""
    import json

    folder = selftest_dir()
    if folder is None:
        return None
    request_file = folder / "request.json"
    if not request_file.is_file():
        return None
    try:
        data = json.loads(request_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log.warning("unreadable self-test request: %s", e)
        return None
    return data if isinstance(data, dict) else {}
