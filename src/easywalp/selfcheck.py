"""``EasyWalp --self-check``: prove a *built* app can start, without a user watching.

``--version`` only proves that Python started and a module was importable: it says
nothing about the things that actually break a frozen build - a missing Qt platform
plugin, a resource folder that PyInstaller dropped, an engine binary that is not
next to the exe, a data directory the app cannot write to. Those failures look like
"the app does not start" on the user's machine and like a green build in CI.

This module walks the same startup path the GUI takes and reports each step. It runs
with whatever platform plugin is available (CI sets ``QT_QPA_PLATFORM=offscreen``,
so it works without a desktop session), never blocks on a dialog, and always exits
with a status the caller can check.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

OK = "ok"
FAILED = "failed"


class Report:
    """Collects ``name: ok/failed`` lines and prints them at the end."""

    def __init__(self) -> None:
        self.lines: list[tuple[str, str, str]] = []
        self.failures: list[str] = []

    def ok(self, name: str, detail: str = "") -> None:
        self.lines.append((OK, name, detail))

    def fail(self, name: str, detail: str) -> None:
        self.lines.append((FAILED, name, detail))
        self.failures.append(f"{name}: {detail}")

    def check(self, name: str, fn, detail=lambda value: "") -> object | None:
        try:
            value = fn()
        except Exception as e:  # noqa: BLE001 - a self-check reports, it does not raise
            self.fail(name, f"{type(e).__name__}: {e}")
            return None
        self.ok(name, detail(value))
        return value

    def print(self) -> None:
        for status, name, detail in self.lines:
            print(f"[{status:6}] {name}{'  - ' + detail if detail else ''}", flush=True)


def _resources(report: Report) -> None:
    from .paths import bundled_dir

    root = bundled_dir()
    report.ok("resource root", str(root))

    def check_icons():
        missing = [p for p in ("icons/easywalp.ico", "logo/wallify-logo.png") if not (root / p).exists()]
        if missing:
            raise FileNotFoundError(", ".join(missing))
        return root / "icons"

    report.check("bundled icons", check_icons)

    def check_i18n():
        from .i18n import SUPPORTED, i18n

        i18n.load_all()
        i18n.set_language("fa")
        table = i18n._tables.get("fa", {})  # noqa: SLF001 - the check is about the table
        if not table:
            raise LookupError("the Persian table did not load")
        for key in ("app.tagline", "main.preset", "error.title"):
            if i18n.tr(key) == key:
                raise KeyError(f"{key} missing from every table")
        return f"{len(table)} keys"

    report.check("i18n tables", check_i18n)

    def check_fonts():
        fonts = sorted((root / "fonts").glob("*")) if (root / "fonts").exists() else []
        if not fonts:
            raise FileNotFoundError("no fonts in the bundle")
        return fonts[0].name

    report.check("bundled fonts", check_fonts)


def _data_dir(report: Report) -> None:
    from .paths import data_dir

    def check_writable():
        root = data_dir()
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=root, prefix="selfcheck-", suffix=".tmp", delete=True):
            pass
        return str(root)

    report.check("writable data directory", check_writable)


def _engine(report: Report) -> None:
    from .photocraft import PhotoCraftBinary, PhotoCraftError

    try:
        binary = PhotoCraftBinary()
    except PhotoCraftError as e:
        report.fail("engine binary", str(e))
        return
    report.ok("engine binary", str(binary.path))

    def check_runs():
        proc = subprocess.run(  # noqa: S603 - the path is ours
            [str(binary.path), "--version"],
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        if proc.returncode != 0:
            raise RuntimeError(f"exit {proc.returncode}: {(proc.stderr or proc.stdout).strip()[:200]}")
        return (proc.stdout or proc.stderr).strip().splitlines()[0]

    report.check("engine runs", check_runs)


def _gui(report: Report) -> None:
    """Start the real window - the step that catches a missing Qt platform plugin."""
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
    except Exception as e:  # noqa: BLE001
        report.fail("PySide6 import", f"{type(e).__name__}: {e}")
        return

    from .app.mainwindow import MainWindow

    def check_window():
        app = QApplication.instance() or QApplication([])
        app.setApplicationName("EasyWalp self-check")
        win = MainWindow()
        win.apply_theme()
        win.apply_language()
        win.show()
        app.processEvents()
        title = win.windowTitle()
        if not title:
            raise RuntimeError("the main window has no title - i18n did not load")
        from .app.widgets import logo_pixmap

        pixmap = logo_pixmap(36)
        win.close()
        # The title keeps the window alive until here; the pixmap result is reported too.
        return (title, "logo" if pixmap is not None else "no logo")

    result = report.check("main window", check_window)
    if result:
        title, logo = result  # type: ignore[misc]
        report.ok("window title", title)
        report.ok("bundled logo", logo)
        # Leave nothing behind: the event loop never starts in a self-check.
        QTimer.singleShot(0, QApplication.quit)


def run(argv: list[str] | None = None) -> int:
    """Run every check; returns 0 when the app is usable, 2 when it is not."""
    report = Report()
    print(f"EasyWalp self-check on {sys.platform}, frozen={getattr(sys, 'frozen', False)}", flush=True)
    print(f"QT_QPA_PLATFORM={os.getenv('QT_QPA_PLATFORM', '(default)')}", flush=True)
    for step in (_resources, _data_dir, _engine, _gui):
        try:
            step(report)
        except Exception as e:  # noqa: BLE001 - a broken step must not hide the others
            report.fail(step.__name__.lstrip("_"), f"{type(e).__name__}: {e}")
    report.print()
    if report.failures:
        print(f"SELF-CHECK FAILED ({len(report.failures)} problem(s))", flush=True)
        for line in report.failures:
            print(f"  - {line}", flush=True)
        return 2
    print("SELF-CHECK OK", flush=True)
    return 0


def _bundled_assets_hint() -> Path | None:  # pragma: no cover - diagnostics only
    """Where the app thinks its resources are (printed when a check fails)."""
    try:
        from .paths import bundled_dir

        return bundled_dir()
    except Exception:  # noqa: BLE001
        return None
