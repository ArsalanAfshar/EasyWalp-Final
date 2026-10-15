"""Preset setup wizard for Android: pick a PSD, map the layers, test, save."""
from __future__ import annotations

import logging
from pathlib import Path

from kivy.metrics import dp
from kivy.uix.image import Image
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.switch import Switch
from kivy.uix.textinput import TextInput

from easywalp.config import GenerateOptions
from easywalp.presets import LayerRef, PresetError, detect_code_span, split_code_text

from ..core import ROLES, ROLE_DESKTOP, ROLE_FILL, ROLE_MOBILE, ROLE_TEXT, CoreError
from ..platform import import_font
from . import theme
from .base import ScreenBase
from .widgets import ActionButton, Body, Segment, Surface, Thumb, Title, rgba

log = logging.getLogger("easywalp.android.ui.wizard")

ROLE_KEYS = {
    ROLE_DESKTOP: "wizard.layers.desktopSO",
    ROLE_MOBILE: "wizard.layers.mobileSO",
    ROLE_FILL: "wizard.layers.fill",
    ROLE_TEXT: "wizard.layers.text",
}


class WizardScreen(ScreenBase):
    nav_title_key = "and.navWizard"

    # ------------------------------------------------------------------ build
    def build(self) -> None:
        self.psd: Path | None = None
        self.analysis = None
        self.dry_run_preview: Path | None = None
        self._role_spinners: dict[str, Spinner] = {}
        self._labels: dict[str, str] = {}

        self.add(self._intro_card())
        self.add(self._mapping_card())
        self.add(self._options_card())
        self.add(self._test_card())

        self.save_button = ActionButton(text="", accent=True, height=dp(54))
        self.save_button.bind(on_release=lambda *_: self.save_preset())
        self.save_button.disabled = True
        self.add(self.save_button)

    def _intro_card(self) -> Surface:
        card = Surface()
        self.intro_title = Title(text="")
        self.intro_hint = Body(text="")
        self.choose_button = ActionButton(text="", height=dp(50))
        self.choose_button.bind(on_release=lambda *_: self.choose_psd())
        self.status = Body(text="")
        card.add_widget(self.intro_title)
        card.add_widget(self.intro_hint)
        card.add_widget(self.choose_button)
        card.add_widget(self.status)
        return card

    def _mapping_card(self) -> Surface:
        card = Surface()
        self.mapping_title = Title(text="")
        for role in ROLES:
            spinner = Spinner(text="—", values=[], size_hint_y=None, height=dp(46), font_name="Vazirmatn")
            spinner.bind(text=lambda _s, value, r=role: self._role_changed(r, value))
            self._role_spinners[role] = spinner
            label = Body(text="")
            self._labels[role] = label
            card.add_widget(label)
            card.add_widget(spinner)
        self.thumb_scroll = ScrollView(size_hint_y=None, height=dp(0), do_scroll_y=False)
        self.thumb_strip = None
        card.add_widget(self.thumb_scroll)
        self.code_info = Body(text="")
        card.add_widget(self.code_info)
        self.font_info = Body(text="")
        card.add_widget(self.font_info)
        return card

    def _options_card(self) -> Surface:
        card = Surface()
        self.name_label = Body(text="")
        self.name_input = TextInput(text="", multiline=False, size_hint_y=None, height=dp(46))
        self.template_label = Body(text="")
        self.template_input = TextInput(text="MD-{CAT}-C{num}", multiline=False,
                                        size_hint_y=None, height=dp(46))
        self.resolution_label = Body(text="")
        from ..core import resolution_choices

        self.resolution_segment = Segment(resolution_choices())
        self.suffix_label = Body(text="")
        self.suffix_switch = Switch(active=False, size_hint=(None, 1), width=dp(70))
        self.font_button = ActionButton(text="", height=dp(44))
        self.font_button.bind(on_release=lambda *_: self.choose_font())
        card.add_widget(self.name_label)
        card.add_widget(self.name_input)
        card.add_widget(self.template_label)
        card.add_widget(self.template_input)
        card.add_widget(self.resolution_label)
        card.add_widget(self.resolution_segment)
        card.add_widget(self.suffix_label)
        card.add_widget(self.rtl_row([self.suffix_switch], height=dp(48)))
        card.add_widget(self.font_button)
        return card

    def _test_card(self) -> Surface:
        card = Surface()
        self.test_button = ActionButton(text="", height=dp(46))
        self.test_button.bind(on_release=lambda *_: self.test_render())
        self.test_thumb = Thumb(height=dp(190), opacity=0)
        self.test_info = Body(text="")
        card.add_widget(self.test_button)
        card.add_widget(self.test_thumb)
        card.add_widget(self.test_info)
        return card

    # ----------------------------------------------------------- translation
    def retranslate(self) -> None:
        self.intro_title.text = self.t("wizard.title")
        self.intro_hint.text = self.t("wizard.pickPsd")
        self.choose_button.text = self.t("and.choosePsd")
        self.mapping_title.text = self.t("wizard.step2")
        for role, label in self._labels.items():
            label.text = self.t(ROLE_KEYS[role])
        self.name_label.text = self.t("and.presetName")
        self.template_label.text = self.t("and.codeTemplate")
        self.resolution_label.text = self.t("main.resolution")
        self.suffix_label.text = self.t("and.resolutionSuffix")
        self.font_button.text = self.t("and.importFont")
        self.test_button.text = self.t("wizard.dryRun")
        self.save_button.text = self.t("wizard.save")
        if self.analysis is not None:
            self._show_analysis(self.analysis)

    def on_enter_screen(self) -> None:
        self.retranslate()

    # ---------------------------------------------------------------- picking
    def choose_psd(self) -> None:
        def picked(path: Path | None, error: str) -> None:
            if error and error != "cancelled":
                self.notify(error, "error")
                return
            if path is None:
                return
            self.psd = path
            if not self.name_input.text:
                self.name_input.text = path.stem
            self.status.text = theme.display(path.name)
            self.analyze()

        self.app.storage.pick_file(
            "*/*", picked, title=self.t("wizard.pickPsd"),
            filetypes=[("photoshop", ["psd", "psb"])],
        )

    def analyze(self) -> None:
        if not self.psd:
            return
        self.status.text = self.t("and.analyzing")
        self.analysis = None
        work_dir = self.app.core.output_base() / "_wizard" / self.psd.stem

        def work():
            return self.app.core.analyze(self.psd, work_dir)

        def done(analysis) -> None:
            self.analysis = analysis
            self.status.text = self.t("and.analysisDone")
            self._show_analysis(analysis)
            self.save_button.disabled = False
            self._load_thumbnails(analysis)

        def failed(error) -> None:
            self.status.text = ""
            self.notify(str(error), "error")

        self.app.run_bg(work, on_done=done, on_error=failed)

    def _show_analysis(self, analysis) -> None:
        self._labels_values = [
            f"[{layer.kind}] {layer.name}" + ("" if layer.visible else " (hidden)")
            for layer in analysis.layers
        ]
        values = list(self._labels_values)
        for role, spinner in self._role_spinners.items():
            spinner.values = values
            suggested = analysis.suggestions.get(role)
            text = next(
                (v for v, layer in zip(values, analysis.layers)
                 if suggested and layer.id == suggested.id),
                None,
            )
            spinner.text = text or "—"
        if analysis.code_text:
            code = analysis.code_text
            span = analysis.code_span or detect_code_span(code)
            detected = code[span[0]:span[1]] if span else code
            self.code_info.text = theme.display(self.t("wizard.detectCode") + f": {detected}")
        else:
            self.code_info.text = theme.display(self.t("and.noTextLayer"))
        if analysis.font_warnings:
            self.font_info.text = theme.display(self.t("wizard.fontMissing", fonts=", ".join(analysis.fonts)))
            self.font_info.color = rgba(theme.colors()["danger"])
        elif analysis.fonts:
            self.font_info.text = theme.display(self.t("wizard.fontWarning", fonts=", ".join(analysis.fonts)))
            self.font_info.color = rgba(theme.colors()["textDim"])
        else:
            self.font_info.text = ""
        if not self.app.core.engine_status()[0]:
            self.notify(self.t("error.engineMissing"), "error")

    def _load_thumbnails(self, analysis) -> None:
        work_dir = analysis.psd.parent / "_thumbs"

        def work():
            return self.app.core.layer_thumbnails(analysis.psd, work_dir)

        def done(thumbs: dict) -> None:
            if not thumbs:
                return
            from kivy.uix.boxlayout import BoxLayout

            strip = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint=(None, 1))
            strip.bind(minimum_width=strip.setter("width"))
            for layer_id, path in sorted(thumbs.items()):
                strip.add_widget(Image(source=str(path), size_hint=(None, 1), width=dp(120)))
            if self.thumb_strip is not None:
                self.thumb_scroll.remove_widget(self.thumb_strip)
            self.thumb_strip = strip
            self.thumb_scroll.add_widget(strip)
            self.thumb_scroll.height = dp(120)

        self.app.run_bg(work, on_done=done)

    def _role_changed(self, role: str, value: str) -> None:
        self.dry_run_preview = None
        self.test_thumb.opacity = 0

    def mapping(self) -> dict[str, LayerRef | None]:
        out: dict[str, LayerRef | None] = {}
        if self.analysis is None:
            return out
        for role, spinner in self._role_spinners.items():
            try:
                index = list(self._labels_values).index(spinner.text)
            except (ValueError, AttributeError):
                out[role] = None
                continue
            layer = self.analysis.layers[index]
            out[role] = LayerRef(layer.id, layer.name, layer.kind)
        return out

    # ------------------------------------------------------------- fonts
    def choose_font(self) -> None:
        def picked(path: Path | None, error: str) -> None:
            if error and error != "cancelled":
                self.notify(error, "error")
                return
            if path is None:
                return
            try:
                dest = import_font(path)
            except (OSError, ValueError) as e:
                self.notify(str(e), "error")
                return
            self.notify(self.t("and.fontImported", name=dest.name), "ok")

        self.app.storage.pick_file(
            "*/*", picked, title=self.t("and.importFont"),
            filetypes=[("fonts", ["ttf", "otf", "ttc"])],
        )

    # ------------------------------------------------------------- test render
    def test_render(self) -> None:
        preset = self._draft_preset()
        if preset is None:
            return
        out_dir = self.app.core.output_base() / "_wizard" / "dryrun"
        self.test_info.text = self.t("main.generating")

        def work():
            return self.app.core.dry_run(preset, out_dir)

        def done(payload) -> None:
            preview, warnings = payload
            self.dry_run_preview = preview
            self.test_thumb.source = str(preview)
            self.test_thumb.opacity = 1
            self.test_info.text = theme.display(self.t("wizard.dryRunDone"))
            if warnings:
                self.notify(" · ".join(str(w) for w in warnings[:3]), "warn")

        self.app.run_bg(work, on_done=done, on_error=lambda e: self.notify(str(e), "error"))

    # ------------------------------------------------------------------ saving
    def _draft_preset(self):
        """A not-yet-saved preset built from the current wizard state."""
        if self.analysis is None:
            self.notify(self.t("wizard.pickPsd"), "warn")
            return None
        mapping = self.mapping()
        missing = [role for role in ROLES if mapping.get(role) is None]
        if missing:
            self.notify(self.t("and.mappingNeeded"), "warn")
            return None
        options = GenerateOptions(
            resolution_key=self.resolution_segment.value() or "2k",
            add_resolution_suffix=self.suffix_switch.active,
        )
        options.templates.code = self.template_input.text.strip() or "MD-{CAT}-C{num}"
        options.templates.folder = options.templates.code
        text_code = None
        if self.analysis.code_text:
            span = self.analysis.code_span or detect_code_span(self.analysis.code_text)
            if span:
                text_code = split_code_text(self.analysis.code_text, span)
        preset = self.app.core.build_preset(
            self.analysis,
            name=self.name_input.text,
            mapping=mapping,
            text_code=text_code,
            options=options,
        )
        return preset

    def save_preset(self) -> None:
        try:
            preset = self._draft_preset()
        except CoreError as e:
            self.notify(str(e), "error")
            return
        except PresetError as e:
            self.notify(str(e), "error")
            return
        if preset is None:
            return
        self.app.core.settings.last_preset_id = preset.id
        self.app.core.save_settings()
        self.notify(self.t("preset.imported", name=preset.name), "ok")
        self.analysis = None
        self.psd = None
        self.status.text = ""
        self.save_button.disabled = True
        self.app.go("home")
