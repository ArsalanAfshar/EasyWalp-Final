"""EasyWalp for Android - a Kivy front end for the same core pipeline as the desktop app.

The package is named ``easywalp_android`` (the desktop GUI lives in
``easywalp.app`` and uses PySide6, which is not available on Android). Everything
below the UI - resizing, average color, the PhotoCraft PSD edit and the naming
rules - is the *same* code as on Windows, imported from ``easywalp``.
"""

__all__ = ["__version__"]

try:  # the version stamped by the release build, when present
    from easywalp import __version__  # noqa: F401
except ImportError:  # pragma: no cover - source checkout without the core package
    __version__ = "0.0.0"
