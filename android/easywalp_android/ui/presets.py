"""Preset manager for Android: activate, import, export/share, rename, delete."""
from __future__ import annotations

import logging
from pathlib import Path

from kivy.metrics import dp
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput

from easywalp.presets import PresetError

from . import theme
from .base import ScreenBase
from .widgets import ActionButton, Body, Surface, Title, rgba

log = logging.getLogger("easywalp.android.ui.presets")


class PresetsScreen(ScreenBase):
    nav_title_key = "and.navPresets"

    def build(self) -> None:
        self.empty_hint = Body(text="")
        self.add(self.empty_hint)
        self.import_button = ActionButton(text="", height=dp(48))
        self.import_button.bind(on_release=lambda *_: self.import_preset())
        self.add(self.import_button)
        self.list_container = Surface()
        self.add(self.list_container)
        self.retranslate()

    def retranslate(self) -> None:
        self.import_button.text = self.t("preset.import")
        self.empty_hint.text = theme.display(self.t("and.noPresets"))
        self.reload()

    def on_enter_screen(self) -> None:
        self.reload()

    # ------------------------------------------------------------------ list
    def reload(self) -> None:
        self.list_container.clear_widgets()
        presets = self.app.core.presets()
        self.empty_hint.opacity = 0 if presets else 1
        for preset in presets:
            self.list_container.add_widget(self._row(preset))

    def _row(self, preset) -> Surface:
        row = Surface(size_hint_y=None, padding=dp(10))
        active = preset.id == self.app.core.settings.last_preset_id
        title = Title(text=theme.display(preset.name) + ("  ✓" if active else ""))
        meta = Body(
            text=theme.display(
                f"{preset.options.resolution_key.upper()} · "
                f"{preset.desktop_contents.width}×{preset.desktop_contents.height} / "
                f"{preset.mobile_contents.width}×{preset.mobile_contents.height}"
            )
        )
        use_button = ActionButton(text=self.t("and.activate"), accent=not active)
        export_button = ActionButton(text=self.t("and.exportFile"))
        rename_button = ActionButton(text=self.t("preset.rename"))
        delete_button = ActionButton(text=self.t("preset.delete"))
        use_button.bind(on_release=lambda *_: self._activate(preset))
        export_button.bind(on_release=lambda *_: self._export(preset))
        rename_button.bind(on_release=lambda *_: self._rename(preset))
        delete_button.bind(on_release=lambda *_: self._delete(preset))
        row.add_widget(title)
        row.add_widget(meta)
        row.add_widget(self.rtl_row([use_button, export_button]))
        row.add_widget(self.rtl_row([rename_button, delete_button]))
        return row

    # --------------------------------------------------------------- actions
    def _activate(self, preset) -> None:
        self.app.core.settings.last_preset_id = preset.id
        self.app.core.save_settings()
        self.notify(self.t("and.activated", name=preset.name), "ok")
        self.reload()

    def _export(self, preset) -> None:
        dest_dir = self.app.core.output_base() / "_export"

        def work():
            package = self.app.core.export_file(preset, dest_dir)
            return package, self.app.storage.export([package], subfolder="EasyWalp")

        def done(payload) -> None:
            package, (handles, error) = payload
            if error and not handles:
                self.notify(error, "error")
                return
            message = self.app.storage.share(handles, text=package.name)
            if message:
                self.notify(self.t("and.exported", name=package.name), "ok")

        self.app.run_bg(work, on_done=done, on_error=lambda e: self.notify(str(e), "error"))

    def _rename(self, preset) -> None:
        field = TextInput(text=preset.name, multiline=False)
        popup = Popup(title=theme.display(self.t("preset.rename")), content=field,
                      size_hint=(0.85, 0.35))

        def confirm(*_args) -> None:
            preset.rename(field.text)
            popup.dismiss()
            self.reload()

        confirm_button = ActionButton(text=self.t("common.ok"), accent=True)
        confirm_button.bind(on_release=confirm)
        layout_popup(popup, field, confirm_button, self.t("common.cancel"))
        popup.open()

    def _delete(self, preset) -> None:
        def confirm(*_args) -> None:
            self.app.core.delete_preset(preset)
            if self.app.core.settings.last_preset_id == preset.id:
                self.app.core.settings.last_preset_id = ""
                self.app.core.save_settings()
            popup.dismiss()
            self.reload()

        label = Body(text=theme.display(self.t("preset.deleteConfirm", name=preset.name)))
        popup = Popup(title=theme.display(self.t("preset.delete")), content=label,
                      size_hint=(0.85, 0.3))
        button = ActionButton(text=self.t("common.yes"), accent=True)
        button.bind(on_release=confirm)
        layout_popup(popup, label, button, self.t("common.no"), cancel_action=popup.dismiss)
        popup.open()

    def import_preset(self) -> None:
        def picked(path: Path | None, error: str) -> None:
            if error and error != "cancelled":
                self.notify(error, "error")
                return
            if path is None:
                return
            try:
                preset = self.app.core.import_file(path)
            except PresetError as e:
                self.notify(self.t("preset.importFailed", error=str(e)), "error")
                return
            self.app.core.settings.last_preset_id = preset.id
            self.app.core.save_settings()
            self.notify(self.t("preset.imported", name=preset.name), "ok")
            self.reload()

        self.app.storage.pick_file(
            "*/*", picked, title=self.t("preset.import"),
            filetypes=[("easywalp", ["easywalp", "zip"])],
        )


def layout_popup(popup: Popup, content, confirm_button, cancel_text: str, cancel_action=None) -> None:
    """Give a Popup a title area, its content and a confirm/cancel row."""
    from kivy.uix.boxlayout import BoxLayout

    buttons = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(8))
    cancel = ActionButton(text=cancel_text)
    cancel.bind(on_release=lambda *_: cancel_action() if cancel_action else popup.dismiss())
    for widget in theme.row_items([confirm_button, cancel]):
        buttons.add_widget(widget)
    wrapper = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
    wrapper.add_widget(content)
    wrapper.add_widget(buttons)
    popup.content = wrapper
