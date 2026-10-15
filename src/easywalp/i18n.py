"""Runtime-switchable i18n: JSON string tables for en/fa, no hardcoded UI strings.

Codes, file names and the mockup text always use Latin digits; Persian digits are
display-only (``display_digits``) when the user enables them.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger("easywalp.i18n")

SUPPORTED = ("en", "fa")
RTL_LANGUAGES = {"fa"}

_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


class I18n:
    def __init__(self) -> None:
        self.language = "en"
        self._tables: dict[str, dict[str, str]] = {}

    # ------------------------------------------------------------- loading
    def load_all(self, i18n_dir: Path | None = None) -> None:
        import sys

        candidates = []
        if i18n_dir is not None:
            candidates.append(i18n_dir)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "i18n")            # PyInstaller (onefile/onedir)
        from .paths import bundled_dir

        candidates.append(bundled_dir() / "i18n")                # installed layout variant
        candidates.append(Path(__file__).resolve().parents[2] / "i18n")  # source checkout
        for d in candidates:
            if (d / "en.json").exists():
                break
        else:
            log.warning("no i18n tables found in %s", [str(c) for c in candidates])
            return
        for lang in SUPPORTED:
            f = d / f"{lang}.json"
            if not f.exists():
                log.warning("i18n table missing: %s", f)
                self._tables.setdefault(lang, {})
                continue
            try:
                self._tables[lang] = json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                log.error("bad i18n table %s: %s", f, e)
                self._tables.setdefault(lang, {})

    # -------------------------------------------------------------- access
    def set_language(self, lang: str) -> None:
        self.language = lang if lang in SUPPORTED else "en"

    def is_rtl(self) -> bool:
        return self.language in RTL_LANGUAGES

    def tr(self, key: str, **kwargs) -> str:
        table = self._tables.get(self.language, {})
        text = table.get(key)
        if text is None:
            text = self._tables.get("en", {}).get(key, key)
            if text == key:
                log.debug("missing i18n key: %s", key)
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, IndexError, ValueError):
                log.warning("bad format for key %s", key)
        return text

    def digits(self, text: str) -> str:
        """Display-only digit conversion (never applied to codes/file names)."""
        if self.language == "fa":
            return text.translate(_PERSIAN_DIGITS)
        return text


i18n = I18n()
