"""EasyWalp - automated wallpaper release pipeline for the Wallify channel.

Core pipeline (this package) is GUI-free; ``easywalp.app`` holds the PySide6 UI
and ``easywalp.__main__`` dispatches between them. The preview mockup is always
rendered by the PhotoCraft engine (see easywalp.photocraft).
"""

__app_name__ = "EasyWalp"

try:  # stamped by the release CI (scripts/release/stage_payload.py)
    from ._build_version import BUILD_VERSION as __version__
except ImportError:  # source checkout
    __version__ = "0.1.0"

APP_ID = "EasyWalp"
