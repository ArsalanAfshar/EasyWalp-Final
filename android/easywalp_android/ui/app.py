"""The EasyWalp Android application shell: header, screens, bottom navigation."""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window  # may be None when no window provider exists
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import FadeTransition, ScreenManager

from easywalp import __version__, logging_setup, paths
from easywalp.i18n import i18n

from ..core import Core
from ..platform import install_bundled_fonts, prepare_engine_env, request_permissions, startup_banner
from ..storage import Storage
from . import theme
from .widgets import ActionButton, Base, Body, Title, rgba

log = logging.getLogger("easywalp.android.ui")

SCREENS = ("home", "wizard", "presets", "settings")


class EasyWalpApp(App):
    """Kivy ``App`` wiring the core services to the screens."""

    title = "EasyWalp"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.core: Core | None = None
        self.storage: Storage | None = None
        self.sm: ScreenManager | None = None
        self._nav_buttons: dict[str, ActionButton] = {}
        self._banner_hook = None

    # ------------------------------------------------------------------ build
    def build(self):
        logging_setup.setup()
        theme.register_fonts()
        self.core = Core()
        self.storage = Storage()
        i18n.load_all()
        i18n.set_language(self.core.settings.language)
        theme.set_persian_digits(self.core.settings.persian_digits)
        palette = theme.set_mode(self.core.settings.theme)
        self._set_background(palette)

        root = BoxLayout(orientation="vertical", spacing=0)
        root.add_widget(self._header())
        self.sm = ScreenManager(transition=FadeTransition(duration=0.12))
        from .home import HomeScreen
        from .presets import PresetsScreen
        from .settings import SettingsScreen
        from .wizard import WizardScreen

        for cls in (HomeScreen, WizardScreen, PresetsScreen, SettingsScreen):
            self.sm.add_widget(cls(app=self))
        root.add_widget(self.sm)
        root.add_widget(self._nav())

        self._bind_back_key()
        Clock.schedule_once(lambda _dt: self.startup(), 0.25)
        return root

    # ----------------------------------------------------------- window bits
    def _set_background(self, palette: dict) -> None:
        """Tint the window background (a no-op when the platform has no window)."""
        try:
            Window.clearcolor = rgba(palette["bg"])
        except Exception as e:  # noqa: BLE001 - headless test runs
            log.debug("no window to tint: %s", e)

    def _bind_back_key(self) -> None:
        try:
            Window.bind(on_keyboard=self._on_key)
        except Exception as e:  # noqa: BLE001
            log.debug("cannot bind the back key: %s", e)

    def _header(self) -> BoxLayout:
        bar = Base(size_hint_y=None, height=dp(58), padding=(dp(14), dp(8), dp(14), dp(4)))
        bar.orientation = "horizontal"
        titles = BoxLayout(orientation="vertical", spacing=0)
        name = Title(text="EasyWalp", font_size="19sp")
        self._tagline = Body(text="", font_size="12sp")
        titles.add_widget(name)
        titles.add_widget(self._tagline)
        self._lang_button = ActionButton(text="", size_hint=(None, 1), width=dp(64))
        self._lang_button.bind(on_release=lambda *_: self.toggle_language())
        self._theme_button = ActionButton(text="◐", size_hint=(None, 1), width=dp(54))
        self._theme_button.bind(on_release=lambda *_: self.toggle_theme())
        bar.add_widget(titles)
        bar.add_widget(self._lang_button)
        bar.add_widget(self._theme_button)
        return bar

    def _nav(self) -> BoxLayout:
        bar = Base(size_hint_y=None, height=dp(58), padding=(dp(6), dp(4), dp(6), dp(6)))
        bar.orientation = "horizontal"
        for name in SCREENS:
            btn = ActionButton(text="", size_hint_y=1)
            btn.bind(on_release=lambda _b, n=name: self.go(n))
            self._nav_buttons[name] = btn
            bar.add_widget(btn)
        return bar

    # ------------------------------------------------------------- lifecycle
    def dpi_scale(self) -> float:
        return 1.0

    def startup(self) -> None:
        """Runs after the first frame: fonts, engine, permissions, status."""
        try:
            prepare_engine_env()
            copied = install_bundled_fonts()
            if copied:
                log.info("installed %d font file(s) for the engine", copied)
        except Exception as e:  # noqa: BLE001 - never block the UI
            log.warning("startup preparation failed: %s", e)
        request_permissions()
        self.retranslate()
        ok, text = self.core.engine_status()
        if not ok:
            self.notify(theme.tr("error.engineMissing") + " " + text, "error")
        else:
            log.info("engine ready: %s", text)
        self.current_screen().on_enter_screen()

    def on_stop(self) -> None:
        if self.core:
            self.core.save_settings()

    def _on_key(self, _window, key, *_args) -> bool:
        if key == 27:  # Android back button / Esc
            if self.sm and self.sm.current != "home":
                self.go("home")
                return True
        return False

    # --------------------------------------------------------------- i18n
    def retranslate(self) -> None:
        self._tagline.text = theme.tr("app.tagline")
        self._lang_button.text = "EN" if i18n.language == "fa" else "فارسی"
        self._theme_button.text = "☀" if theme.mode() == "dark" else "☾"
        labels = {
            "home": "and.navHome",
            "wizard": "and.navWizard",
            "presets": "and.navPresets",
            "settings": "and.navSettings",
        }
        for key, i18n_key in labels.items():
            self._nav_buttons[key].text = theme.tr(i18n_key)
        for screen in self.sm.screens if self.sm else []:
            if hasattr(screen, "retranslate"):
                screen.retranslate()
        self._apply_layout_direction()

    def _apply_layout_direction(self) -> None:
        """Kivy has no RTL layout engine: flip the horizontal containers ourselves."""
        for bar in (self._nav_buttons["home"].parent, self._lang_button.parent):
            if bar is None:
                continue
            children = list(bar.children)
            for child in children:
                bar.remove_widget(child)
            for child in theme.row_items(list(reversed(children))):
                bar.add_widget(child)

    def toggle_language(self) -> None:
        new_lang = "en" if i18n.language == "fa" else "fa"
        i18n.set_language(new_lang)
        self.core.set_language(new_lang)
        self.retranslate()

    def toggle_theme(self) -> None:
        new_mode = "light" if theme.mode() == "dark" else "dark"
        self.core.set_theme(new_mode)
        self.apply_theme(new_mode)

    def apply_theme(self, mode: str | None = None) -> None:
        palette = theme.set_mode(mode or self.core.settings.theme)
        self._set_background(palette)
        self._restyle(self.root)
        self.retranslate()

    def _restyle(self, widget) -> None:
        if hasattr(widget, "restyle"):
            widget.restyle()
        for child in getattr(widget, "children", []):
            self._restyle(child)

    # -------------------------------------------------------------- screens
    def current_screen(self):
        return self.sm.current_screen if self.sm else None

    def go(self, name: str) -> None:
        if not self.sm or name not in SCREENS:
            return
        self.sm.current = name
        screen = self.sm.get_screen(name)
        if hasattr(screen, "on_enter_screen"):
            screen.on_enter_screen()

    # ------------------------------------------------------------ messaging
    def notify(self, text: str, level: str = "info") -> None:
        screen = self.current_screen()
        banner = getattr(screen, "banner", None)
        if banner is not None:
            banner.show(text, level)
        log.info("notify(%s): %s", level, text)

    # -------------------------------------------------------------- workers
    def run_bg(self, work, on_done=None, on_error=None) -> None:
        """Run *work* on a thread and deliver the result on the UI thread."""

        def runner() -> None:
            try:
                result = work()
            except Exception as e:  # noqa: BLE001 - report, never crash the app
                log.exception("background task failed")
                if on_error:
                    Clock.schedule_once(lambda _dt, err=e: on_error(err), 0)
                else:
                    Clock.schedule_once(lambda _dt, err=e: self.notify(str(err), "error"), 0)
                return
            if on_done:
                Clock.schedule_once(lambda _dt, res=result: on_done(res), 0)

        threading.Thread(target=runner, daemon=True).start()

    def progress_callback(self, screen) -> Callable[[str, float], None]:
        """A pipeline progress callback that hops onto the UI thread."""

        def report(stage: str, fraction: float) -> None:
            Clock.schedule_once(lambda _dt: screen.set_progress(stage, fraction), 0)

        return report

    def about_text(self) -> str:
        return "\n".join(
            [
                startup_banner(),
                theme.tr("and.aboutEngine"),
                theme.tr("and.aboutLicenses"),
                f"data: {paths.data_dir()}",
            ]
        )
