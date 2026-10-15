"""The EasyWalp main screen and application bootstrap (run_app)."""
from __future__ import annotations

import logging
import platform
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import __app_name__, __version__, logging_setup, settings as settings_mod
from ..config import RESOLUTIONS
from ..i18n import i18n
from ..paths import bundled_dir, data_dir
from ..photocraft import PhotoCraftBinary, PhotoCraftError
from ..pipeline import PipelineError, check_overwrite, output_folder, plan_names
from ..presets import Preset, PresetError
from ..themes import resolve as resolve_theme, stylesheet
from .dialogs import AboutDialog, SettingsDialog
from .presets_dialog import PresetsDialog
from .widgets import CodePreviewCard, DropZone, SegmentToggle, logo_pixmap, make_button
from .wizard import WizardDialog
from .worker import GenerateRequest, GenerateWorker

log = logging.getLogger("easywalp.ui")

STAGE_KEYS = ("prepare", "resizing", "color", "editing", "rendering", "done")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = settings_mod.load()
        self.worker: GenerateWorker | None = None
        self.last_result = None

        self.setWindowTitle(__app_name__)
        icon_path = bundled_dir() / "icons" / "easywalp.ico"
        if not icon_path.exists():
            icon_path = bundled_dir() / "icons" / "easywalp-256.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(960, 700)

        central = QWidget()
        self.setCentralWidget(central)
        self.root = QVBoxLayout(central)
        self.root.setContentsMargins(18, 12, 18, 14)
        self.root.setSpacing(12)

        self._build_header()
        self._build_body()
        self._retranslate()

        if self.settings.window_geometry:
            try:
                x, y, w, h = self.settings.window_geometry
                self.setGeometry(x, y, w, h)
            except (TypeError, ValueError):
                pass

    # ------------------------------------------------------------- header
    def _build_header(self) -> None:
        bar = QHBoxLayout()
        logo = QLabel()
        pm = logo_pixmap(40)
        if pm:
            logo.setPixmap(pm)
        self.title_label = QLabel(__app_name__)
        self.title_label.setProperty("h1", True)
        bar.addWidget(logo)
        bar.addWidget(self.title_label)
        bar.addStretch(1)

        self.settings_btn = make_button("⚙", flat=True)
        self.settings_btn.setToolTip(i18n.tr("app.settings"))
        self.settings_btn.clicked.connect(self._open_settings)
        self.about_btn = make_button("ℹ", flat=True)
        self.about_btn.setToolTip(i18n.tr("app.about"))
        self.about_btn.clicked.connect(lambda: AboutDialog(self).exec())
        bar.addWidget(self.settings_btn)
        bar.addWidget(self.about_btn)
        self.root.addLayout(bar)

    # --------------------------------------------------------------- body
    def _build_body(self) -> None:
        # preset row
        row = QHBoxLayout()
        self.preset_label = QLabel()
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(240)
        self.manage_btn = make_button("", flat=True)
        row.addWidget(self.preset_label)
        row.addWidget(self.preset_combo, 1)
        row.addWidget(self.manage_btn)
        self.root.addLayout(row)

        # drop zones
        zones = QHBoxLayout()
        self.desktop_zone = DropZone("")
        self.mobile_zone = DropZone("")
        zones.addWidget(self.desktop_zone, 1)
        zones.addWidget(self.mobile_zone, 1)
        self.root.addLayout(zones, 1)

        # controls row: category / resolution / number
        ctrl = QHBoxLayout()
        self.category_label = QLabel()
        self.category_toggle = SegmentToggle([("O", ""), ("A", "")])
        self.resolution_label = QLabel()
        self.resolution_toggle = SegmentToggle([(k, RESOLUTIONS[k].label) for k in RESOLUTIONS])
        self.number_label = QLabel()
        self.number_spin = QSpinBox()
        self.number_spin.setRange(0, 999999)
        self.number_spin.setMinimumWidth(110)
        for w in (self.category_label, self.category_toggle, self.resolution_label,
                  self.resolution_toggle, self.number_label, self.number_spin):
            ctrl.addWidget(w)
        ctrl.addStretch(1)
        self.root.addLayout(ctrl)

        # code preview card
        self.code_card = CodePreviewCard()
        self.root.addWidget(self.code_card)

        # output row
        out_row = QHBoxLayout()
        self.out_label = QLabel()
        self.out_edit = QLineEdit(self.settings.output_base)
        self.out_btn = make_button(i18n.tr("main.browse"))
        out_row.addWidget(self.out_label)
        out_row.addWidget(self.out_edit, 1)
        out_row.addWidget(self.out_btn)
        self.root.addLayout(out_row)

        # progress + generate
        prog_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.stage_label = QLabel("")
        self.stage_label.setProperty("dim", True)
        self.generate_btn = make_button(i18n.tr("main.generate"), accent=True)
        self.generate_btn.setMinimumHeight(44)
        self.generate_btn.setMinimumWidth(170)
        prog_row.addWidget(self.stage_label, 1)
        prog_row.addWidget(self.progress, 2)
        prog_row.addWidget(self.generate_btn)
        self.root.addLayout(prog_row)

        # result row
        self.result_row = QHBoxLayout()
        self.result_thumb = QLabel()
        self.result_info = QLabel("")
        self.open_folder_btn = make_button()
        self.copy_code_btn = make_button()
        self.open_preview_btn = make_button()
        self.result_row.addWidget(self.result_thumb)
        res_btns = QVBoxLayout()
        res_btns.addWidget(self.result_info)
        btns = QHBoxLayout()
        btns.addWidget(self.open_folder_btn)
        btns.addWidget(self.copy_code_btn)
        btns.addWidget(self.open_preview_btn)
        btns.addStretch(1)
        res_btns.addLayout(btns)
        self.result_row.addLayout(res_btns, 1)
        self.result_widget = QFrame()
        self.result_widget.setProperty("card", True)
        self.result_widget.setLayout(self.result_row)
        self.result_widget.hide()
        self.root.addWidget(self.result_widget)

        # wiring
        self.preset_combo.currentIndexChanged.connect(self._preset_changed)
        self.manage_btn.clicked.connect(self._open_presets)
        self.out_btn.clicked.connect(self._pick_out)
        self.out_edit.textChanged.connect(lambda _t: self._update_preview())
        self.category_toggle.changed.connect(lambda _v: self._update_preview())
        self.resolution_toggle.changed.connect(lambda _v: self._update_preview())
        self.number_spin.valueChanged.connect(lambda _v: self._update_preview())
        self.generate_btn.clicked.connect(self._generate)
        self.open_folder_btn.clicked.connect(self._open_result_folder)
        self.copy_code_btn.clicked.connect(self._copy_code)
        self.open_preview_btn.clicked.connect(self._open_preview)
        for zone in (self.desktop_zone, self.mobile_zone):
            zone.changed.connect(lambda _p: self._update_preview())

        self.reload_presets(select_id=self.settings.last_preset_id or None)
        self.category_toggle.set_value(self.settings.last_category)
        self.resolution_toggle.set_value(self.settings.last_resolution)
        self.number_spin.setValue(self.settings.last_number)

    # ---------------------------------------------------------- i18n / dir
    def _retranslate(self) -> None:
        self.preset_label.setText(i18n.tr("main.preset"))
        self.manage_btn.setText(i18n.tr("main.managePresets"))
        self.desktop_zone.set_title(i18n.tr("main.desktop"))
        self.mobile_zone.set_title(i18n.tr("main.mobile"))
        self.category_label.setText(i18n.tr("main.category"))
        self.category_toggle.set_option_text("O", i18n.tr("main.catO"))
        self.category_toggle.set_option_text("A", i18n.tr("main.catA"))
        self.resolution_label.setText(i18n.tr("main.resolution"))
        self.number_label.setText(i18n.tr("main.number"))
        self.out_label.setText(i18n.tr("main.outputFolder"))
        self.out_btn.setText(i18n.tr("main.browse"))
        self.generate_btn.setText(i18n.tr("main.generating") if self.worker else i18n.tr("main.generate"))
        self.settings_btn.setToolTip(i18n.tr("app.settings"))
        self.about_btn.setToolTip(i18n.tr("app.about"))
        self.open_folder_btn.setText(i18n.tr("main.openFolder"))
        self.copy_code_btn.setText(i18n.tr("main.copyCode"))
        self.open_preview_btn.setText(i18n.tr("main.openPreview"))
        self._update_preview()

    def apply_language(self) -> None:
        i18n.set_language(self.settings.language)
        self.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if i18n.is_rtl() else Qt.LayoutDirection.LeftToRight
        )
        self._retranslate()

    def apply_theme(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(stylesheet(resolve_theme(self.settings.theme)))

    # ------------------------------------------------------------- presets
    def reload_presets(self, select_id: str | None = None) -> None:
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        presets = Preset.load_all()
        for preset in presets:
            self.preset_combo.addItem(preset.name, preset.id)
        self.preset_combo.blockSignals(False)
        if not presets:
            self._update_preview()
            return
        target = select_id or self.settings.last_preset_id
        idx = next((i for i in range(self.preset_combo.count()) if self.preset_combo.itemData(i) == target), 0)
        self.preset_combo.setCurrentIndex(idx)

    def current_preset(self) -> Preset | None:
        pid = self.preset_combo.currentData()
        if not pid:
            return None
        try:
            return Preset.load(str(pid))
        except PresetError as e:
            log.warning("preset load failed: %s", e)
            return None

    def _preset_changed(self) -> None:
        preset = self.current_preset()
        if preset:
            self.settings.last_preset_id = preset.id
            self.resolution_toggle.set_value(preset.options.resolution_key)
        self._update_preview()

    # ------------------------------------------------------- live preview
    def _current_category(self) -> str:
        return self.category_toggle.value() or "O"

    def _update_preview(self) -> None:
        preset = self.current_preset()
        category = self._current_category()
        number = self.number_spin.value()
        res_key = self.resolution_toggle.value()
        self.settings.last_category = category
        self.settings.last_resolution = res_key
        self.settings.last_number = number
        if preset is None:
            self.code_card.update_info([i18n.tr("main.noPreset")], "—", "")
            self.generate_btn.setEnabled(False)
            return
        self.generate_btn.setEnabled(True)
        from ..config import GenerateOptions

        opts = preset.options
        try:
            info = plan_names(opts, category, number, res_key)
        except PipelineError as e:
            self.code_card.update_info([str(e)], "—", "")
            return
        out_base = self.out_edit.text().strip()
        folder = output_folder(Path(out_base) if out_base else Path("<out>"), info)
        lines = [
            f"📁 {folder}",
            f"🖼 {info.desktop_file}  ({info.desktop_target[0]}×{info.desktop_target[1]})",
            f"📱 {info.mobile_file}  ({info.mobile_target[0]}×{info.mobile_target[1]})",
            f"🪧 {info.preview_file}",
        ]
        sizes = i18n.tr(
            "main.targetSizes",
            desktop=f"{info.desktop_target[0]}×{info.desktop_target[1]}",
            mobile=f"{info.mobile_target[0]}×{info.mobile_target[1]}",
        )
        shown_code = i18n.digits(info.code)
        self.code_card.update_info(lines, shown_code, sizes)

    # ------------------------------------------------------------ generate
    def _pick_out(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, i18n.tr("main.outputFolder"), self.out_edit.text() or "")
        if folder:
            self.out_edit.setText(folder)

    def _generate(self) -> None:
        if self.worker is not None:
            return
        preset = self.current_preset()
        if preset is None:
            return
        desktop = self.desktop_zone.image_path()
        mobile = self.mobile_zone.image_path()
        out_base = self.out_edit.text().strip()
        if desktop is None or mobile is None:
            QMessageBox.warning(self, i18n.tr("error.title"),
                                i18n.tr("main.desktop") + " / " + i18n.tr("main.mobile"))
            return
        if not out_base:
            QMessageBox.warning(self, i18n.tr("error.title"), i18n.tr("main.outputFolder"))
            return
        try:
            binary = PhotoCraftBinary(self.settings.photocraft_path or None)
        except PhotoCraftError as e:
            QMessageBox.critical(self, i18n.tr("error.title"), i18n.tr("error.engineMissing") + f"\n{e}")
            return

        info = plan_names(preset.options, self._current_category(), self.number_spin.value(),
                          self.resolution_toggle.value())
        conflict = check_overwrite(Path(out_base), info)
        if conflict is not None:
            answer = QMessageBox.question(
                self, i18n.tr("overwrite.title"),
                i18n.tr("overwrite.text", folder=str(conflict)),
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        options_override = {"resolution_key": self.resolution_toggle.value()}
        request = GenerateRequest(
            preset=preset,
            desktop=desktop,
            mobile=mobile,
            category=self._current_category(),
            number=self.number_spin.value(),
            out_base=Path(out_base),
            options_override=options_override,
        )
        self.worker = GenerateWorker(request, binary, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.failed.connect(self._on_failed)
        self.worker.warnings.connect(self._on_warnings)
        self.worker.finished_ok.connect(self._on_success)
        self.worker.finished.connect(self._worker_done)
        self.generate_btn.setEnabled(False)
        self.generate_btn.setText(i18n.tr("main.generating"))
        self.progress.setValue(2)
        self.result_widget.hide()
        settings_mod.remember_output_folder(self.settings, out_base)
        self.worker.start()

    def _on_progress(self, stage: str, frac: float) -> None:
        self.progress.setValue(int(frac * 100))
        self.stage_label.setText(i18n.tr(f"stage.{stage}"))

    def _on_failed(self, message: str, details: str) -> None:
        error_box(self, message, details)

    def _on_warnings(self, warnings: list) -> None:
        if warnings:
            QMessageBox.warning(self, i18n.tr("warn.title"), "\n".join("• " + w for w in warnings))

    def _on_success(self, result) -> None:
        self.last_result = result
        self.progress.setValue(100)
        self.stage_label.setText(i18n.tr("stage.done"))
        self.result_info.setText(
            f"{result.code.code}\n{result.desktop_jpg.name} · {result.mobile_jpg.name}\n{result.preview_jpg.name}"
        )
        from PySide6.QtGui import QPixmap

        pm = QPixmap(str(result.preview_jpg))
        if not pm.isNull():
            self.result_thumb.setPixmap(
                pm.scaled(190, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )
        self.result_widget.show()
        settings_mod.save(self.settings)

    def _worker_done(self) -> None:
        self.worker = None
        self.generate_btn.setEnabled(True)
        self.generate_btn.setText(i18n.tr("main.generate"))

    # -------------------------------------------------------------- result
    def _open_result_folder(self) -> None:
        if self.last_result:
            _open_in_explorer(self.last_result.out_dir)

    def _copy_code(self) -> None:
        if self.last_result:
            QApplication.clipboard().setText(self.last_result.code.code)

    def _open_preview(self) -> None:
        if self.last_result:
            _open_in_explorer(self.last_result.preview_jpg)

    # ------------------------------------------------------------- dialogs
    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec():
            dlg.apply()
            settings_mod.save(self.settings)
            self.apply_language()
            self.apply_theme()

    def _open_presets(self) -> None:
        try:
            binary = PhotoCraftBinary(self.settings.photocraft_path or None)
        except PhotoCraftError as e:
            QMessageBox.critical(self, i18n.tr("error.title"), i18n.tr("error.engineMissing") + f"\n{e}")
            return

        def open_wizard():
            WizardDialog(self.settings, binary, self).exec()

        dlg = PresetsDialog(self.settings, binary, open_wizard, self)
        dlg.presets_changed.connect(lambda: self.reload_presets())
        dlg.exec()

    def maybe_open_wizard(self) -> None:
        if not Preset.list_ids():
            try:
                binary = PhotoCraftBinary(self.settings.photocraft_path or None)
            except PhotoCraftError as e:
                QMessageBox.critical(self, i18n.tr("error.title"), i18n.tr("error.engineMissing") + f"\n{e}")
                return
            WizardDialog(self.settings, binary, self).exec()

    # ------------------------------------------------------------- closing
    def closeEvent(self, event) -> None:  # noqa: N802
        g = self.geometry()
        self.settings.window_geometry = [g.x(), g.y(), g.width(), g.height()]
        settings_mod.save(self.settings)
        super().closeEvent(event)


def error_box(parent, message: str, details: str = "") -> None:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle(i18n.tr("error.title"))
    box.setText(message)
    if details:
        box.setDetailedText(details)
    copy_btn = box.addButton(i18n.tr("error.copyDetails"), QMessageBox.ButtonRole.ActionRole)
    box.addButton(QMessageBox.StandardButton.Ok)
    box.exec()
    if box.clickedButton() is copy_btn:
        QApplication.clipboard().setText((message + "\n\n" + details).strip())


def _open_in_explorer(path: Path) -> None:
    path = Path(path)
    if sys.platform == "win32":
        if path.is_dir():
            subprocess.Popen(["explorer", str(path)])
        else:
            subprocess.Popen(["explorer", "/select,", str(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def run_app(argv: list[str]) -> int:
    logging_setup.setup()
    log.info("EasyWalp %s on %s / Python %s", __version__, platform.platform(), platform.python_version())
    app = QApplication(argv)
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)

    i18n.load_all()
    settings = settings_mod.load()
    i18n.set_language(settings.language)

    win = MainWindow()
    win.apply_theme()
    win.apply_language()
    win.show()
    QTimer.singleShot(200, win.maybe_open_wizard)
    return app.exec()
