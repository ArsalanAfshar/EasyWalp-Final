"""The rendered buildozer.spec has to be readable by buildozer.

Buildozer looks every `android.*` / `p4a.*` value up with
``config.get*('app', key)``, so the keys ``prepare_apk.py`` fills in are only
honoured inside the ``[app]`` section. Appended to the end of the file they end
up in ``[buildozer]``, are silently ignored, and the build quietly falls back to
buildozer's own SDK/NDK directories - which cost a couple of CI runs before the
"Requested API target 35 is not available" error was traced back here.
"""
from __future__ import annotations

import configparser
import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PREPARE_APK = REPO / "scripts" / "android" / "prepare_apk.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("prepare_apk", PREPARE_APK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    module = _load_module()
    out = tmp_path_factory.mktemp("spec")
    path = module.render_spec(
        out, "1.2.3", "/opt/android/sdk", "/opt/android/ndk", "/opt/p4a",
        ("arm64-v8a", "x86"),
    )
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8")
    return path, parser


def test_generated_keys_live_in_the_app_section(rendered):
    path, parser = rendered
    assert parser.has_section("app")
    for key, expected in {
        "version": "1.2.3",
        "android.numeric_version": "10203",
        "android.archs": "arm64-v8a,x86",
        "android.add_libs_arm64_v8a": "libs/arm64-v8a/*.so",
        "android.add_libs_x86": "libs/x86/*.so",
        "android.sdk_path": "/opt/android/sdk",
        "android.ndk_path": "/opt/android/ndk",
        "p4a.source_dir": "/opt/p4a",
    }.items():
        assert parser.get("app", key) == expected, f"{key} is not in [app] of {path}"
    assert not parser.has_option("buildozer", "android.sdk_path")


def test_numeric_version_is_monotonic():
    module = _load_module()
    versions = ["0.1.0", "0.1.1", "0.2.0", "1.0.0", "1.2.3"]
    codes = [module.numeric_version(v) for v in versions]
    assert codes == sorted(codes) and len(set(codes)) == len(codes)
    assert module.numeric_version("0.1.0") == 100
    assert module.numeric_version("nonsense") == 0


def test_appless_spec_still_renders(tmp_path, monkeypatch):
    """A spec without a [buildozer] section must not lose the keys either."""
    module = _load_module()
    monkeypatch.setattr(module, "ANDROID_DIR", tmp_path)
    (tmp_path / "buildozer.spec").write_text(
        "[app]\ntitle = EasyWalp\nversion = 0.0.0\n", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    path = module.render_spec(out, "2.0.0", "/sdk", None, None, ())
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8")
    assert parser.get("app", "version") == "2.0.0"
    assert parser.get("app", "android.numeric_version") == "20000"
    assert parser.get("app", "android.sdk_path") == "/sdk"
