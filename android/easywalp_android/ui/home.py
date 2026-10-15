"""The Generate screen: everything needed for one wallpaper release."""
from __future__ import annotations

import logging
from pathlib import Path

from kivy.metrics import dp
from kivy.uix.image import Image
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from easywalp.config import RESOLUTIONS

from ..core import ROLES, CoreError, GenerateRequest, resolution_choices
from ..storage import PICK_IMAGE
from . import theme
from .base import ScreenBase
from .widgets import ActionButton, Banner, Body, FieldRow, Segment, StageBar, Surface, Thumb, Title, rgba

log = logging.getLogger("easywalp.android.ui.home")

STAGE_KEYS = ("prepare", "resizing", "color", "editing", "rendering", "done")


class HomeScreen(ScreenBase):
    nav_title_key = "and.navHome"

    # ------------------------------------------------------------------ build
    def build(self) -> None:
        self.desktop_path: Path | None = None
        self.mobile_path: Path | None = None
        self.result = None
        self.handles: list[str] = []
        self._preset_names: dict[str, str] = {}

        self.add(self._preset_card())
        self.add(self._source_card())
        self.add(self._options_card())

        self.code_card = Surface()
        self.code_title = Title(text="")
        self.code_value = Title(text="—", font_size="22sp")
        self.code_files = Body(text="")
        self.code_card.add_widget(self.code_title)
        self.code_card.add_widget(self.code_value)
        self.code_card.add_widget(self.code_files)
        self.add(self.code_card)

        self.stage_bar = StageBar()
        self.add(self.stage_bar)

        self.generate_button = ActionButton(text="", accent=True, height=dp(54))
        self.generate_button.bind(on_release=lambda *_: self.generate())
        self.add(self.generate_button)

        self.add(self._result_card())
        self.add(Banner())  # errors from background work land in the screen banner

    def _preset_card(self) -> Surface:
        card = Surface()
        self.preset_title = Title(text="")
        self.preset_spinner = Spinner(text="—", values=[], size_hint_y=None, height=dp(46),
                                      font_name="Vazirmatn")
        self.preset_spinner.bind(text=self._preset_chosen)
        self.preset_manage = ActionButton(text="", size_hint_y=None, height=dp(42))
        self.preset_manage.bind(on_release=lambda *_: self.app.go("wizard"))
        self.preset_more = ActionButton(text="", size_hint_y=None, height=dp(42))
        self.preset_more.bind(on_release=lambda *_: self.app.go("presets"))
        card.add_widget(self.preset_title)
        card.add_widget(self.preset_spinner)
        card.add_widget(self.rtl_row([self.preset_manage, self.preset_more]))
        return card

    def _source_card(self) -> Surface:
        card = Surface()
        self.desktop_row = FieldRow(title="", on_press=lambda: self.pick("desktop"))
        self.mobile_row = FieldRow(title="", on_press=lambda: self.pick("mobile"))
        self.desktop_thumb = Thumb(opacity=0)
        self.mobile_thumb = Thumb(opacity=0)
        card.add_widget(self.desktop_row)
        card.add_widget(self.desktop_thumb)
        card.add_widget(self.mobile_row)
        card.add_widget(self.mobile_thumb)
        return card

    def _options_card(self) -> Surface:
        card = Surface()
        self.category_segment = Segment([("O", ""), ("A", "")],
                                        on_change=lambda _v: self.refresh_preview())
        self.resolution_segment = Segment(resolution_choices(), on_change=self._resolution_changed)
        self.number_input = TextInput(text="1", input_filter="int", multiline=False,
                                      size_hint_y=None, height=dp(46), halign="center")
        self.number_minus = ActionButton(text="−", size_hint=(None, 1), width=dp(54))
        self.number_plus = ActionButton(text="+", size_hint=(None, 1), width=dp(54))
        self.number_minus.bind(on_release=lambda *_: self._bump_number(-1))
        self.number_plus.bind(on_release=lambda *_: self._bump_number(+1))
        self.category_label = Body(text="")
        self.resolution_label = Body(text="")
        self.number_label = Body(text="")
        card.add_widget(self.category_label)
        card.add_widget(self.category_segment)
        card.add_widget(self.resolution_label)
        card.add_widget(self.resolution_segment)
        card.add_widget(self.number_label)
        card.add_widget(self.rtl_row([self.number_minus, self.number_input, self.number_plus], height=dp(46)))
        return card

    def _result_card(self) -> Surface:
        card = Surface()
        card.opacity = 0
        card.height = dp(0)
        card.size_hint_y = None
        self.result_card = card
        self.result_title = Title(text="")
        self.preview_thumb = Thumb(height=dp(190))
        self.result_info = Body(text="")
        self.save_button = ActionButton(text="", accent=True)
        self.share_button = ActionButton(text="")
        self.open_button = ActionButton(text="")
        self.save_button.bind(on_release=lambda *_: self.export_result())
        self.share_button.bind(on_release=lambda *_: self.share_result())
        self.open_button.bind(on_release=lambda *_: self.open_preview())
        card.add_widget(self.result_title)
        card.add_widget(self.preview_thumb)
        card.add_widget(self.result_info)
        card.add_widget(self.rtl_row([self.save_button, self.share_button, self.open_button]))
        return card

    # ----------------------------------------------------------- translations
    def retranslate(self) -> None:
        self.preset_title.text = self.t("main.preset")
        self.preset_manage.text = self.t("preset.new")
        self.preset_more.text = self.t("main.managePresets")
        self.desktop_row.title.text = self.t("main.desktop")
        self.desktop_row.button.text = self.t("and.choose")
        self.mobile_row.title.text = self.t("main.mobile")
        self.mobile_row.button.text = self.t("and.choose")
        self.category_label.text = self.t("main.category")
        self.category_segment.set_option_text("O", self.t("main.catO"))
        self.category_segment.set_option_text("A", self.t("main.catA"))
        self.resolution_label.text = self.t("main.resolution")
        self.number_label.text = self.t("main.number")
        self.code_title.text = self.t("main.codePreview")
        self.generate_button.text = self.t("main.generating") if getattr(self, "_busy", False) else self.t("main.generate")
        self.result_title.text = self.t("main.success")
        self.save_button.text = self.t("and.saveGallery")
        self.share_button.text = self.t("and.share")
        self.open_button.text = self.t("main.openPreview")
        self._refresh_presets()
        self.refresh_preview()

    def on_enter_screen(self) -> None:
        self._refresh_presets()

    # -------------------------------------------------------------- presets
    def _refresh_presets(self) -> None:
        presets = self.app.core.presets()
        self._preset_names = {}
        values = []
        for preset in presets:
            label = preset.name
            while label in self._preset_names:
                label += " •"
            self._preset_names[label] = preset.id
            values.append(label)
        self.preset_spinner.values = values
        if values:
            current = self.app.core.settings.last_preset_id
            target = next((v for v in values if self._preset_names[v] == current), values[0])
            self.preset_spinner.text = target
        else:
            self.preset_spinner.text = theme.display(self.t("main.noPreset"))
            self.preset_spinner.values = [self.preset_spinner.text]
        self.refresh_preview()

    def _preset_chosen(self, _spinner, text: str) -> None:
        preset_id = self._preset_names.get(text)
        if not preset_id:
            return
        self.app.core.settings.last_preset_id = preset_id
        self.app.core.save_settings()
        try:
            preset = self.app.core.preset(preset_id)
        except Exception as e:  # noqa: BLE001
            self.notify(str(e), "error")
            return
        self.resolution_segment.set_value(preset.options.resolution_key)
        self.refresh_preview()

    def current_preset(self):
        preset_id = self._preset_names.get(self.preset_spinner.text)
        if not preset_id:
            return None
        try:
            return self.app.core.preset(preset_id)
        except Exception as e:  # noqa: BLE001
            log.warning("preset load failed: %s", e)
            return None

    # --------------------------------------------------------------- picking
    def pick(self, which: str) -> None:
        title = self.t("main.desktop") if which == "desktop" else self.t("main.mobile")
        filetypes = [("images", ["jpg", "jpeg", "png", "webp", "bmp", "tif", "tiff"])]

        def picked(path: Path | None, error: str) -> None:
            if error and error != "cancelled":
                self.notify(f"{error}", "error")
                return
            if path is None:
                return
            if which == "desktop":
                self.desktop_path = path
                self.desktop_row.set_value(path.name)
                self.desktop_thumb.source = str(path)
                self.desktop_thumb.opacity = 1
            else:
                self.mobile_path = path
                self.mobile_row.set_value(path.name)
                self.mobile_thumb.source = str(path)
                self.mobile_thumb.opacity = 1
            self.refresh_preview()

        self.app.storage.pick_file(PICK_IMAGE, picked, title=title, filetypes=filetypes)

    # -------------------------------------------------------------- options
    def _bump_number(self, delta: int) -> None:
        try:
            value = max(0, int(self.number_input.text or "0") + delta)
        except ValueError:
            value = 0
        self.number_input.text = str(value)
        self.refresh_preview()

    def _resolution_changed(self, _value: str) -> None:
        self.refresh_preview()

    def _request(self) -> GenerateRequest | None:
        preset = self.current_preset()
        if preset is None:
            return None
        if self.desktop_path is None or self.mobile_path is None:
            return None
        try:
            number = int(self.number_input.text or "0")
        except ValueError:
            number = 0
        return GenerateRequest(
            preset=preset,
            desktop=self.desktop_path,
            mobile=self.mobile_path,
            category=self.category_segment.value() or "O",
            number=number,
            resolution_key=self.resolution_segment.value(),
        )

    def refresh_preview(self) -> None:
        request = self._request()
        if request is None:
            preset = self.current_preset()
            hint = self.t("main.noPreset") if preset is None else self.t("and.needImages")
            self.code_value.text = "—"
            self.code_files.text = theme.display(hint)
            self.generate_button.disabled = True
            return
        try:
            info = self.app.core.plan(request)
        except CoreError as e:
            self.code_value.text = "—"
            self.code_files.text = theme.display(str(e))
            self.generate_button.disabled = True
            return
        self.generate_button.disabled = False
        self.code_value.text = theme.display(info.code)
        sizes = theme.tr(
            "main.targetSizes",
            desktop=f"{info.desktop_target[0]}×{info.desktop_target[1]}",
            mobile=f"{info.mobile_target[0]}×{info.mobile_target[1]}",
        )
        folder = self.app.core.output_base() / info.folder_name
        self.code_files.text = "\n".join(
            [
                theme.display(sizes),
                theme.display(f"📁 {folder}"),
                theme.display(f"🖼 {info.desktop_file}"),
                theme.display(f"📱 {info.mobile_file}"),
                theme.display(f"🪧 {info.preview_file}"),
            ]
        )

    # ------------------------------------------------------------ generating
    def generate(self) -> None:
        request = self._request()
        if request is None:
            self.notify(self.t("and.needImages"), "warn")
            return
        if self._busy:
            return
        self._busy = True
        self.generate_button.text = self.t("main.generating")
        self.generate_button.disabled = True
        self.result_card.opacity = 0
        self.result_card.height = dp(0)
        self.banner.hide()
        self.stage_bar.reset()
        conflict = None
        try:
            conflict = self.app.core.existing_folder(request)
        except CoreError:
            pass
        if conflict:
            self.notify(self.t("overwrite.text", folder=conflict.name), "warn")

        def work():
            return self.app.core.generate(request, self.app.progress_callback(self), overwrite=True)

        def done(result) -> None:
            self._busy = False
            self.result = result
            self.handles = []
            self.generate_button.text = self.t("main.generate")
            self.generate_button.disabled = False
            self.stage_bar.set_stage("done", 1.0)
            self._show_result(result)
            if result.warnings:
                self.notify(" · ".join(str(w) for w in result.warnings[:3]), "warn")

        def failed(error) -> None:
            self._busy = False
            self.generate_button.text = self.t("main.generate")
            self.generate_button.disabled = False
            self.stage_bar.reset()
            self.notify(str(error), "error")

        self.app.run_bg(work, on_done=done, on_error=failed)

    def _show_result(self, result) -> None:
        card = self.result_card
        card.opacity = 1
        card.height = dp(360)
        self.preview_thumb.source = str(result.preview_jpg)
        info = result.code
        self.result_info.text = "\n".join(
            [
                theme.display(f"{self.t('main.codePreview')}: {info.code}"),
                theme.display(f"📁 {result.out_dir.name}"),
                theme.display(f"🖼 {result.desktop_jpg.name} · {result.mobile_jpg.name}"),
                theme.display(f"🪧 {result.preview_jpg.name}"),
                theme.display(f"⚙ {self.t('and.averageColor')}: {result.average_color}"),
            ]
        )

    # -------------------------------------------------------------- exporting
    def export_result(self) -> None:
        if not self.result:
            return
        files = [self.result.desktop_jpg, self.result.mobile_jpg, self.result.preview_jpg]
        code = self.result.code.folder_name

        def work():
            return self.app.storage.export(files, subfolder=code)

        def done(payload) -> None:
            handles, error = payload
            self.handles = handles
            if error:
                self.notify(error, "error")
            else:
                self.notify(self.t("and.savedGallery", count=len(handles)), "ok")

        self.app.run_bg(work, on_done=done, on_error=lambda e: self.notify(str(e), "error"))

    def share_result(self) -> None:
        if not self.result:
            return
        code = self.result.code.code
        if not self.handles:
            # Export first (MediaStore URIs are what the share sheet needs).
            files = [self.result.desktop_jpg, self.result.mobile_jpg, self.result.preview_jpg]
            subfolder = self.result.code.folder_name

            def work():
                return self.app.storage.export(files, subfolder=subfolder)

            def done(payload) -> None:
                handles, error = payload
                self.handles = handles
                if error and not handles:
                    self.notify(error, "error")
                    return
                message = self.app.storage.share(handles, text=code)
                if message:
                    self.notify(message, "warn")

            self.app.run_bg(work, on_done=done, on_error=lambda e: self.notify(str(e), "error"))
            return
        message = self.app.storage.share(self.handles, text=code)
        if message:
            self.notify(message, "warn")

    def open_preview(self) -> None:
        if not self.result:
            return
        if self.handles:
            message = self.app.storage.view(self.handles[-1])
            if not message:
                return
            self.notify(message, "warn")
            return
        self.export_result()
        self.notify(self.t("and.savedGallery", count=3), "ok")
