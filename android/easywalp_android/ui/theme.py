"""Colours, fonts and Persian text handling for the Kivy UI.

* the palette is the *same* Wallify palette the desktop app uses
  (``easywalp.themes.DARK`` / ``LIGHT``), so both builds look identical;
* Vazirmatn is registered as the default Kivy font (Android's own fonts have no
  Persian coverage worth using);
* Kivy cannot shape Arabic script, so Persian strings are run through
  ``arabic-reshaper`` + ``python-bidi`` before display. If those tiny pure-Python
  packages are missing the app still runs, just with raw (unjoined) Persian text.
"""
from __future__ import annotations

import logging

from easywalp.i18n import i18n
from easywalp.paths import bundled_dir
from easywalp.themes import DARK, LIGHT

log = logging.getLogger("easywalp.android.theme")

PALETTES = {"dark": DARK, "light": LIGHT}
_state = {"mode": "dark", "persian_digits": True, "font": ""}

try:  # optional, pure Python (p4a requirements list both)
    import arabic_reshaper
    from bidi.algorithm import get_display

    _HAS_SHAPER = True
except Exception:  # noqa: BLE001
    _HAS_SHAPER = False


def register_fonts() -> str:
    """Register Vazirmatn and make it the default face for every Kivy widget."""
    from kivy.core.text import LabelBase

    fonts = bundled_dir() / "fonts"
    regular = fonts / "Vazirmatn-Regular.ttf"
    if not regular.exists():
        log.warning("bundled font missing: %s", regular)
        return ""
    # LabelBase only knows these four slots; Vazirmatn has no italic face, so the
    # SemiBold weight stands in for bold text.
    files = {
        "fn_regular": regular,
        "fn_bold": fonts / "Vazirmatn-Bold.ttf",
        "fn_italic": fonts / "Vazirmatn-SemiBold.ttf",
        "fn_bolditalic": fonts / "Vazirmatn-Bold.ttf",
    }
    for key, path in list(files.items()):
        if not path.exists():
            del files[key]
        else:
            files[key] = str(path)  # Kivy wants strings, not Path objects
    LabelBase.register(name="Vazirmatn", **files)
    # Replacing "Roboto" switches Kivy's default font everywhere at once.
    LabelBase.register(name="Roboto", **files)
    _state["font"] = str(regular)
    return str(regular)


def set_mode(mode: str) -> dict:
    """'dark' | 'light' | 'system' - returns the active palette."""
    resolved = mode
    if mode == "system":
        resolved = "dark" if _system_prefers_dark() else "light"
    _state["mode"] = resolved if resolved in PALETTES else "dark"
    return colors()


def mode() -> str:
    return _state["mode"]


def colors() -> dict:
    return PALETTES.get(_state["mode"], DARK)


def set_persian_digits(enabled: bool) -> None:
    _state["persian_digits"] = bool(enabled)


def _system_prefers_dark() -> bool:
    """Android exposes the system theme through the activity's configuration."""
    try:
        from jnius import autoclass

        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        configuration = activity.getResources().getConfiguration()
        mask = configuration.UI_MODE_NIGHT_MASK
        night_yes = configuration.UI_MODE_NIGHT_YES
        return int(mask & night_yes) == int(night_yes)
    except Exception:  # noqa: BLE001 - not on Android: stay dark
        return True


# ------------------------------------------------------------------- text
def tr(key: str, **kwargs) -> str:
    """Translated *and* display-ready string (Persian shaped, digits converted)."""
    return display(i18n.tr(key, **kwargs))


def display(text: str) -> str:
    """Shape Persian text for Kivy's non-shaping text stack."""
    if not text:
        return text
    if i18n.language == "fa" and _state["persian_digits"]:
        text = i18n.digits(text)
    if i18n.language == "fa" and _HAS_SHAPER and _has_arabic(text):
        try:
            return get_display(arabic_reshaper.reshape(text))
        except Exception as e:  # noqa: BLE001 - never let text break the UI
            log.debug("reshaping failed: %s", e)
    return text


def is_rtl() -> bool:
    return i18n.is_rtl()


def row_items(items: list) -> list:
    """Order a horizontal row's children for the current language."""
    return list(reversed(items)) if is_rtl() else list(items)


def align() -> str:
    return "right" if is_rtl() else "left"


def _has_arabic(text: str) -> bool:
    return any("\u0600" <= c <= "\u06ff" or "\ufb50" <= c <= "\ufdff" for c in text)
