"""``--self-check`` must pass on a healthy checkout and fail on a broken build.

The Windows release runs this same code path on the *packaged* app
(``EasyWalp.exe --self-check``), so a bug in here would either hide a broken build
or block a good one. Running it here against the fake engine keeps both directions
honest: everything present -> exit 0, engine missing -> exit 2 with a report.

The report/exit-code logic is checked without Qt (a sandbox may have no working
GL stack at all); the step that really starts the window is checked in CI, where
offscreen Qt is available. The resource lookup is checked separately, because a
frozen app that cannot find ``assets/`` behaves exactly like a broken download.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the fake engine shim is POSIX-only")


class NoGui:
    """Stands in for the Qt step: records that it was asked to run."""

    def __init__(self) -> None:
        self.called = 0

    def __call__(self, report) -> None:
        self.called += 1
        report.ok("main window", "stubbed")


@pytest.fixture()
def no_gui(monkeypatch):
    from easywalp import selfcheck

    stub = NoGui()
    monkeypatch.setattr(selfcheck, "_gui", stub)
    return stub


def _run(capsys) -> tuple[int, str]:
    from easywalp import selfcheck

    code = selfcheck.run([])
    return code, capsys.readouterr().out


def test_self_check_passes_with_a_working_engine(tmp_path, data_dir, capsys, monkeypatch, no_gui):
    from fake_engine import write_fake_engine

    engine = write_fake_engine(tmp_path / "engine")
    monkeypatch.setenv("EASYWALP_ENGINE", str(engine))
    monkeypatch.setenv("FAKE_STATE_DIR", str(tmp_path))
    code, out = _run(capsys)
    assert code == 0, out
    assert "SELF-CHECK OK" in out
    assert no_gui.called == 1
    for name in ("resource root", "bundled icons", "i18n tables", "bundled fonts",
                 "writable data directory", "engine binary", "engine runs", "main window"):
        assert f"[ok    ] {name}" in out, f"{name} is not in the report:\n{out}"


def test_self_check_fails_when_the_engine_is_missing(data_dir, capsys, monkeypatch, no_gui):
    monkeypatch.delenv("EASYWALP_ENGINE", raising=False)
    monkeypatch.delenv("EASYWALP_ENGINE_DIR", raising=False)
    code, out = _run(capsys)
    assert code == 2, out
    assert "SELF-CHECK FAILED" in out
    assert "[failed] engine binary" in out


@pytest.mark.gui
def test_self_check_starts_the_window_for_real(tmp_path, data_dir, capsys, monkeypatch):
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError, reason="Qt cannot load here")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from fake_engine import write_fake_engine

    monkeypatch.setenv("EASYWALP_ENGINE", str(write_fake_engine(tmp_path / "engine")))
    monkeypatch.setenv("FAKE_STATE_DIR", str(tmp_path))
    code, out = _run(capsys)
    assert code == 0, out
    assert "[ok    ] main window" in out
    assert "[ok    ] bundled logo" in out


def test_bundled_dir_follows_the_frozen_layouts(tmp_path, monkeypatch):
    """Source checkout, PyInstaller onedir (next to the exe) and onefile (_MEIPASS)."""
    from easywalp import paths

    monkeypatch.delenv("ANDROID_ARGUMENT", raising=False)
    monkeypatch.delenv("ANDROID_PRIVATE", raising=False)
    monkeypatch.delenv("ANDROID_UNPACK", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    # source checkout: <repo>/assets
    assert paths.bundled_dir().resolve() == (Path(__file__).resolve().parents[1] / "assets").resolve()

    # onedir: assets/ next to the executable
    exe_dir = tmp_path / "dist" / "EasyWalp"
    (exe_dir / "assets").mkdir(parents=True)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "EasyWalp.exe"))
    assert paths.bundled_dir().resolve() == (exe_dir / "assets").resolve()

    # onefile: assets/ inside the folder PyInstaller unpacks to
    meipass = tmp_path / "_MEI123456"
    (meipass / "assets").mkdir(parents=True)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    assert paths.bundled_dir().resolve() == (meipass / "assets").resolve()
