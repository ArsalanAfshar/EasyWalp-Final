"""Settings: language, theme, engine status, storage paths, fonts, about."""
from __future__ import annotations

import logging
from pathlib import Path

from kivy.metrics import dp
from kivy.uix.switch import Switch

from easywalp.i18n import i18n

from ..platform import startup_banner
from . import theme
from .base import ScreenBase
from .widgets import ActionButton, Body, Segment, Surface, Title, rgba

log = logging.getLogger("easywalp.android.ui.settings")


class SettingsScreen(ScreenBase):
    nav_title_key = "and.navSettings"

    def build(self) -> None:
        self.add(self._language_card())
        self.add(self._theme_card())
        self.add(self._engine_card())
        self.add(self._storage_card())
        self.add(self._about_card())
        self.retranslate()

    # ---------------------------------------------------------------- cards
    def _language_card(self) -> Surface:
        card = Surface()
        self.language_title = Title(text="")
        self.language_segment = Segment([("en", "English"), ("fa", "فارسی")], on_change=self._language)
        card.add_widget(self.language_title)
        card.add_widget(self.language_segment)
        return card

    def _theme_card(self) -> Surface:
        card = Surface()
        self.theme_title = Title(text="")
        self.theme_segment = Segment(
            [("dark", ""), ("light", ""), ("system", "")], on_change=self._theme
        )
        self.digits_hint = Body(text="")
        self.digits_switch = Switch(active=bool(self.app.core.settings.persian_digits),
                                    size_hint=(None, 1), width=dp(70))
        self.digits_switch.bind(active=self._digits)
        card.add_widget(self.theme_title)
        card.add_widget(self.theme_segment)
        card.add_widget(self.digits_hint)
        card.add_widget(self.rtl_row([self.digits_switch], height=dp(48)))
        return card

    def _engine_card(self) -> Surface:
        card = Surface()
        self.engine_title = Title(text="")
        self.engine_info = Body(text="")
        self.detect_button = ActionButton(text="")
        self.detect_button.bind(on_release=lambda *_: self.detect_engine())
        self.log_button = ActionButton(text="")
        self.log_button.bind(on_release=lambda *_: self.show_log())
        card.add_widget(self.engine_title)
        card.add_widget(self.engine_info)
        card.add_widget(self.rtl_row([self.detect_button, self.log_button]))
        return card

    def _storage_card(self) -> Surface:
        card = Surface()
        self.storage_title = Title(text="")
        self.storage_info = Body(text="")
        card.add_widget(self.storage_title)
        card.add_widget(self.storage_info)
        return card

    def _about_card(self) -> Surface:
        card = Surface()
        self.about_title = Title(text="")
        self.about_info = Body(text="")
        card.add_widget(self.about_title)
        card.add_widget(self.about_info)
        return card

    # ---------------------------------------------------------- translation
    def retranslate(self) -> None:
        self.language_title.text = self.t("app.language")
        self.language_segment.set_value(self.app.core.settings.language)
        self.theme_title.text = self.t("app.theme")
        self.theme_segment.set_option_text("dark", self.t("theme.dark"))
        self.theme_segment.set_option_text("light", self.t("theme.light"))
        self.theme_segment.set_option_text("system", self.t("theme.system"))
        self.theme_segment.set_value(self.app.core.settings.theme)
        self.digits_hint.text = self.t("settings.persianDigits")
        self.engine_title.text = self.t("settings.engine")
        self.detect_button.text = self.t("settings.engineDetect")
        self.log_button.text = self.t("and.viewLog")
        self.storage_title.text = self.t("and.storage")
        self.about_title.text = self.t("app.about")
        self.about_info.text = theme.display(
            "\n".join([self.t("and.aboutEngine"), self.t("and.aboutLicenses"), startup_banner()])
        )
        self.refresh_engine()
        self.refresh_storage()

    def on_enter_screen(self) -> None:
        self.refresh_engine()
        self.refresh_storage()

    # ------------------------------------------------------------- actions
    def _language(self, value: str) -> None:
        i18n.set_language(value)
        self.app.core.set_language(value)
        self.app.retranslate()

    def _theme(self, value: str) -> None:
        self.app.apply_theme(value)

    def _digits(self, _switch, value: bool) -> None:
        theme.set_persian_digits(value)
        self.app.core.settings.persian_digits = bool(value)
        self.app.core.save_settings()
        self.app.retranslate()

    def detect_engine(self) -> None:
        self.refresh_engine()
        ok, text = self.app.core.engine_status()
        self.notify(self.t("settings.engineFound", version=text) if ok else text, "ok" if ok else "error")

    def refresh_engine(self) -> None:
        ok, text = self.app.core.engine_status()
        self.engine_info.text = theme.display(
            (self.t("settings.engineFound", version=text) if ok else self.t("error.engineMissing"))
        )
        self.engine_info.color = rgba(theme.colors()["success"] if ok else theme.colors()["danger"])

    def refresh_storage(self) -> None:
        self.storage_info.text = theme.display(self.app.core.storage_summary())

    def show_log(self) -> None:
        from kivy.uix.popup import Popup

        from easywalp import paths

        log_file = paths.logs_dir() / "easywalp.log"
        try:
            text = log_file.read_text(encoding="utf-8", errors="replace")[-4000:]
        except OSError:
            text = self.t("and.noLog")
        label = Body(text=theme.display(text))
        popup = Popup(title=theme.display(self.t("and.viewLog")), content=label,
                      size_hint=(0.95, 0.8))
        popup.open()
