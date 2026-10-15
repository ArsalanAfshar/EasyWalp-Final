"""Reusable Kivy widgets for the EasyWalp Android screens (styled by theme.py)."""
from __future__ import annotations

from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar

from . import theme


def rgba(hex_color: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    value = hex_color.lstrip("#")
    r, g, b = (int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return (r, g, b, alpha)


class Surface(BoxLayout):
    """A rounded card with the theme's surface colour."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("padding", dp(12))
        kwargs.setdefault("spacing", dp(8))
        super().__init__(**kwargs)
        palette = theme.colors()
        with self.canvas.before:
            self._bg_color = Color(*rgba(palette["surface"]))
            self._bg = RoundedRectangle(radius=[dp(14)])
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *_args) -> None:
        self._bg.pos = self.pos
        self._bg.size = self.size

    def restyle(self) -> None:
        self._bg_color.rgba = rgba(theme.colors()["surface"])


class Base(BoxLayout):
    """A transparent container that participates in RTL mirroring."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.padding = kwargs.get("padding", dp(4))
        self.spacing = kwargs.get("spacing", dp(8))


class WrappedLabel(Label):
    """A label that wraps to its parent's width and grows vertically."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("halign", theme.align())
        kwargs.setdefault("valign", "middle")
        kwargs.setdefault("markup", True)
        kwargs.setdefault("color", rgba(theme.colors()["text"]))
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.bind(width=self._on_width, texture_size=self._on_texture)

    def _on_width(self, *_args) -> None:
        self.text_size = (self.width, None)

    def _on_texture(self, *_args) -> None:
        self.height = max(dp(20), self.texture_size[1] + dp(4))


class Title(WrappedLabel):
    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("bold", True)
        kwargs.setdefault("font_size", "17sp")
        super().__init__(**kwargs)


class Body(WrappedLabel):
    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("font_size", "14sp")
        kwargs.setdefault("color", rgba(theme.colors()["textDim"]))
        super().__init__(**kwargs)


class ActionButton(Button):
    """Flat themed button; ``accent=True`` for the primary action."""

    def __init__(self, text: str = "", accent: bool = False, **kwargs) -> None:
        palette = theme.colors()
        super().__init__(text=text, **kwargs)
        self.accent = accent
        self.background_normal = ""
        self.background_down = ""
        self.border = (0, 0, 0, 0)
        self.font_name = "Vazirmatn"
        self.font_size = "15sp"
        self.height = dp(46)
        self.size_hint_y = kwargs.get("size_hint_y", None)
        self.restyle()

    def restyle(self) -> None:
        palette = theme.colors()
        if self.accent:
            self.background_color = rgba(palette["accent"])
            self.color = rgba(palette["accentText"])
        else:
            self.background_color = rgba(palette["surfaceAlt"])
            self.color = rgba(palette["text"])


class Segment(Base):
    """A row of mutually exclusive buttons (category, resolution, language…)."""

    def __init__(self, options: list[tuple[str, str]], on_change=None, **kwargs) -> None:
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(46))
        super().__init__(**kwargs)
        self._buttons: dict[str, ActionButton] = {}
        self.on_change = on_change
        self._value = options[0][0] if options else ""
        for key, text in theme.row_items(list(options)):
            btn = ActionButton(text=text, accent=(key == self._value))
            btn.size_hint_y = 1
            btn.bind(on_release=lambda _b, k=key: self.set_value(k, notify=True))
            self._buttons[key] = btn
            self.add_widget(btn)

    def value(self) -> str:
        return self._value

    def set_value(self, value: str, notify: bool = False) -> None:
        if value not in self._buttons:
            return
        self._value = value
        for key, btn in self._buttons.items():
            btn.accent = key == value
            btn.restyle()
        if notify and self.on_change:
            self.on_change(value)

    def set_option_text(self, key: str, text: str) -> None:
        if key in self._buttons:
            self._buttons[key].text = text


class StageBar(Base):
    """Progress bar + the current stage name (keys match easywalp.pipeline.STAGES)."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(40))
        super().__init__(**kwargs)
        self.bar = ProgressBar(max=100, value=0)
        self.label = WrappedLabel(text="", font_size="13sp", size_hint_x=0.45)
        self.label.halign = theme.align()
        self.add_widget(self.label)
        self.add_widget(self.bar)

    def set_stage(self, stage_key: str, fraction: float) -> None:
        self.label.text = theme.tr(f"stage.{stage_key}") if stage_key else ""
        self.bar.value = max(0, min(100, fraction * 100))

    def reset(self) -> None:
        self.bar.value = 0
        self.label.text = ""


class Banner(Base):
    """An inline message (info / warn / error) the user can dismiss."""

    LEVELS = {"info": "accent", "warn": "danger", "error": "danger", "ok": "success"}

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(0))
        super().__init__(**kwargs)
        self.label = WrappedLabel(text="", font_size="13sp")
        self.close = ActionButton(text="✕", size_hint=(None, None), width=dp(38), height=dp(38))
        self.close.bind(on_release=lambda *_: self.hide())
        self.add_widget(self.label)
        self.add_widget(self.close)
        self.opacity = 0

    def show(self, text: str, level: str = "info") -> None:
        self.label.text = theme.display(text)
        self.label.color = rgba(theme.colors().get(self.LEVELS.get(level, "accent"), "#3d9bdb"))
        self.opacity = 1
        self.height = self.label.height + dp(8)

    def hide(self) -> None:
        self.opacity = 0
        self.height = dp(0)


class Thumb(ButtonBehavior, Image):
    """Preview image that can also be tapped (opens the full file)."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(140))
        super().__init__(**kwargs)
        self.fit_mode = "contain"


class FieldRow(Base):
    """Label + value + a button, mirrored in Persian."""

    def __init__(self, title: str, button_text: str = "…", on_press=None, **kwargs) -> None:
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(72))
        super().__init__(**kwargs)
        self.title = WrappedLabel(text=title, font_size="13sp", color=rgba(theme.colors()["textDim"]))
        self.value = WrappedLabel(text="", font_size="14sp")
        column = BoxLayout(orientation="vertical", spacing=dp(2))
        column.add_widget(self.title)
        column.add_widget(self.value)
        self.button = ActionButton(text=button_text, size_hint=(None, 1), width=dp(96))
        if on_press:
            self.button.bind(on_release=lambda *_: on_press())
        self.add_widget(column)
        self.add_widget(self.button)

    def set_value(self, text: str) -> None:
        self.value.text = theme.display(text)
