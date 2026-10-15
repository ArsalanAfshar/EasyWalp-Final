"""Preset manager: list presets, create (wizard), import, export, rename,
duplicate, delete."""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .. import __app_name__, __version__
from ..i18n import i18n
from ..photocraft import PhotoCraftBinary
from ..presets import Preset, PresetError, export_preset, import_preset
from .widgets import make_button


class PresetsDialog(QDialog):
    presets_changed = Signal()

    def __init__(self, settings, binary: PhotoCraftBinary, open_wizard, parent=None) -> None:
        """`open_wizard` is a callable that launches the setup wizard."""
        super().__init__(parent)
        self.settings = settings
        self.binary = binary
        self._open_wizard = open_wizard

        self.setWindowTitle(i18n.tr("main.managePresets"))
        self.resize(520, 460)
        lay = QVBoxLayout(self)

        self.list = QListWidget()
        lay.addWidget(self.list, 1)

        row_new = QHBoxLayout()
        new_btn = make_button(i18n.tr("preset.new"))
        import_btn = make_button(i18n.tr("preset.import"))
        row_new.addWidget(new_btn)
        row_new.addWidget(import_btn)
        row_new.addStretch(1)
        lay.addLayout(row_new)

        row_edit = QHBoxLayout()
        self.export_btn = make_button(i18n.tr("preset.export"))
        rename_btn = make_button(i18n.tr("preset.rename"))
        dup_btn = make_button(i18n.tr("preset.duplicate"))
        del_btn = make_button(i18n.tr("preset.delete"))
        del_btn.setProperty("danger", True)
        for b in (self.export_btn, rename_btn, dup_btn, del_btn):
            row_edit.addWidget(b)
        lay.addLayout(row_edit)

        self.fonts_check = QCheckBox(i18n.tr("preset.exportFonts"))
        lay.addWidget(self.fonts_check)

        close = make_button(i18n.tr("common.close"), accent=True)
        close.clicked.connect(self.accept)
        lay.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)

        new_btn.clicked.connect(self._new)
        import_btn.clicked.connect(self._import)
        self.export_btn.clicked.connect(self._export)
        rename_btn.clicked.connect(self._rename)
        dup_btn.clicked.connect(self._duplicate)
        del_btn.clicked.connect(self._delete)

        self._edit_buttons = [self.export_btn, rename_btn, dup_btn, del_btn]
        for b in self._edit_buttons:
            b.setEnabled(False)
        self.reload()
        self.list.currentRowChanged.connect(self._selection_changed)

    # ------------------------------------------------------------------ data
    def reload(self) -> None:
        self.list.clear()
        for preset in Preset.load_all():
            item = QListWidgetItem(f"{preset.name}\n{preset.dir.name}")
            item.setData(Qt.ItemDataRole.UserRole, preset.id)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _current(self) -> Preset | None:
        item = self.list.currentItem()
        if not item:
            return None
        return Preset.load(str(item.data(Qt.ItemDataRole.UserRole)))

    def _selection_changed(self, row: int) -> None:
        has = row >= 0
        for b in self._edit_buttons:
            b.setEnabled(has)

    # --------------------------------------------------------------- actions
    def _new(self) -> None:
        self.hide()
        try:
            self._open_wizard()
        finally:
            self.reload()
            self.presets_changed.emit()
            self.show()

    def _import(self) -> None:
        file, _ = QFileDialog.getOpenFileName(self, i18n.tr("preset.import"), "", "EasyWalp preset (*.easywalp)")
        if not file:
            return
        try:
            preset = import_preset(Path(file), __version__)
        except PresetError as e:
            QMessageBox.critical(self, i18n.tr("preset.importFailed", error=""), str(e))
            return
        self.reload()
        self.presets_changed.emit()
        QMessageBox.information(self, __app_name__, i18n.tr("preset.imported", name=preset.name))

    def _export(self) -> None:
        preset = self._current()
        if not preset:
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, i18n.tr("preset.export"), f"{preset.name}.easywalp", "EasyWalp preset (*.easywalp)"
        )
        if not dest:
            return
        try:
            export_preset(preset, Path(dest), include_fonts=self.fonts_check.isChecked())
        except PresetError as e:
            QMessageBox.critical(self, i18n.tr("error.title"), str(e))

    def _rename(self) -> None:
        preset = self._current()
        if not preset:
            return
        name, ok = QInputDialog.getText(self, i18n.tr("preset.rename"), "", text=preset.name)
        if ok and name.strip():
            preset.rename(name)
            self.reload()
            self.presets_changed.emit()

    def _duplicate(self) -> None:
        preset = self._current()
        if not preset:
            return
        from ..presets import new_preset_id

        clone = Preset.from_dict(_preset_dict(preset))
        clone.id = new_preset_id()
        clone.name = f"{preset.name} (copy)"
        clone.dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(preset.template_path, clone.template_path)
        clone.save()
        self.reload()
        self.presets_changed.emit()

    def _delete(self) -> None:
        preset = self._current()
        if not preset:
            return
        answer = QMessageBox.question(
            self, i18n.tr("preset.delete"), i18n.tr("preset.deleteConfirm", name=preset.name)
        )
        if answer == QMessageBox.StandardButton.Yes:
            preset.delete()
            self.reload()
            self.presets_changed.emit()


def _preset_dict(preset: Preset) -> dict:
    import json

    return json.loads(preset.json_path.read_text(encoding="utf-8"))
