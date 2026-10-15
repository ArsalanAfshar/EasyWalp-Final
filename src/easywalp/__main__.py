"""Entry point: `python -m easywalp` (GUI), `python -m easywalp gui`,
`python -m easywalp <pipeline args>` (CLI), or `EasyWalp.exe Something.easywalp`
(double-clicked preset package: import it, then open the GUI).

The GUI imports PySide6 lazily so CLI-only machines don't need Qt.
"""
from __future__ import annotations

import sys


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0].lower().endswith(".easywalp"):
        # File association / drag&drop onto the exe: import the preset, then GUI.
        from .app.mainwindow import import_and_run  # noqa: PLC0415

        return import_and_run(argv[0])
    if argv and argv[0] == "gui":
        argv = argv[1:]
        from .app.mainwindow import run_app  # noqa: PLC0415 - lazy GUI import

        return run_app(argv)
    if not argv:
        # No arguments: launching the plain module starts the GUI (double-click friendly).
        from .app.mainwindow import run_app  # noqa: PLC0415

        return run_app([])
    from .cli import main as cli_main  # noqa: PLC0415

    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
