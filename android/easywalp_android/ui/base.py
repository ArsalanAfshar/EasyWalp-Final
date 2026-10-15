"""Common screen scaffolding: scroll body, banner, screen lifecycle hooks."""
from __future__ import annotations

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import Screen

from . import theme
from .widgets import Banner


class ScreenBase(Screen):
    """A scrollable screen with an inline banner and RTL-aware retranslation."""

    nav_title_key = ""

    def __init__(self, app, **kwargs) -> None:
        super().__init__(**kwargs)
        self.app = app
        self.banner = Banner()
        outer = BoxLayout(orientation="vertical", padding=(dp(10), dp(8), dp(10), dp(8)), spacing=dp(6))
        outer.add_widget(self.banner)
        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        self.body = BoxLayout(orientation="vertical", spacing=dp(10), size_hint_y=None)
        self.body.bind(minimum_height=self.body.setter("height"))
        self.scroll.add_widget(self.body)
        outer.add_widget(self.scroll)
        self.add_widget(outer)
        self.build()

    # ----------------------------------------------------------------- hooks
    def build(self) -> None:  # pragma: no cover - implemented by subclasses
        """Create the widgets (runs once, on first construction)."""

    def retranslate(self) -> None:  # pragma: no cover - optional
        """Re-apply translations after a language change."""

    def on_enter_screen(self) -> None:
        """Called when the screen becomes visible."""

    # --------------------------------------------------------------- helpers
    def add(self, widget):
        self.body.add_widget(widget)
        return widget

    def t(self, key: str, **kwargs) -> str:
        return theme.tr(key, **kwargs)

    def notify(self, text: str, level: str = "info") -> None:
        self.banner.show(text, level)

    def set_progress(self, stage: str, fraction: float) -> None:
        bar = getattr(self, "stage_bar", None)
        if bar is not None:
            bar.set_stage(stage, fraction)

    def rtl_row(self, widgets: list, **kwargs) -> BoxLayout:
        """A horizontal row whose children follow the reading direction."""
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("spacing", dp(8))
        row = BoxLayout(orientation="horizontal", **kwargs)
        for widget in theme.row_items(widgets):
            row.add_widget(widget)
        return row
