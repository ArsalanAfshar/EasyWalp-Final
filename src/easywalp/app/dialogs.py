"""Settings and About/Licenses dialogs."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
)

from .. import __version__, paths
from ..i18n import i18n
from ..photocraft import PhotoCraftBinary, PhotoCraftError
from .widgets import make_button

LICENSE_TABS = [
    ("EasyWalp (MIT)", "assets/LICENSE"),
    ("PhotoCraft - MIT", "assets/photocraft/LICENSE-MIT.txt"),
    ("PhotoCraft - Apache-2.0", "assets/photocraft/LICENSE-APACHE.txt"),
    ("PhotoCraft NOTICE", "assets/photocraft/NOTICE.txt"),
    ("Third-party notices", "assets/photocraft/THIRD_PARTY_NOTICES.txt"),
    ("Vazirmatn font (OFL)", "assets/fonts/OFL-Vazirmatn.txt"),
]


class SettingsDialog(QDialog):
    """Language, theme, Persian digits, engine path, data folder."""

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle(i18n.tr("app.settings"))
        self.setMinimumWidth(460)

        lay = QVBoxLayout(self)
        lay.setSpacing(12)

        # Language ---------------------------------------------------------
        row = QHBoxLayout()
        row.addWidget(QLabel(i18n.tr("app.language")))
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("English", "en")
        self.lang_combo.addItem("فارسی", "fa")
        self.lang_combo.setCurrentIndex(0 if settings.language == "en" else 1)
        row.addWidget(self.lang_combo, 1)
        lay.addLayout(row)

        # Theme --------------------------------------------------------------
        row = QHBoxLayout()
        row.addWidget(QLabel(i18n.tr("app.theme")))
        self.theme_combo = QComboBox()
        for value, key in (("dark", "theme.dark"), ("light", "theme.light"), ("system", "theme.system")):
            self.theme_combo.addItem(i18n.tr(key), value)
        idx = {"dark": 0, "light": 1, "system": 2}.get(settings.theme, 2)
        self.theme_combo.setCurrentIndex(idx)
        row.addWidget(self.theme_combo, 1)
        lay.addLayout(row)

        # Persian digits ------------------------------------------------------
        self.fa_digits = QCheckBox(i18n.tr("settings.persianDigits"))
        self.fa_digits.setChecked(settings.persian_digits)
        lay.addWidget(self.fa_digits)

        # Engine --------------------------------------------------------------
        engine_box = QVBoxLayout()
        engine_row = QHBoxLayout()
        self.engine_edit = QLineEdit(settings.photocraft_path)
        self.engine_edit.setPlaceholderText("photocraft-cli")
        browse = make_button(i18n.tr("main.browse"), flat=True)
        detect = make_button(i18n.tr("settings.engineDetect"), flat=True)
        engine_row.addWidget(self.engine_edit, 1)
        engine_row.addWidget(browse)
        engine_row.addWidget(detect)
        engine_box.addLayout(engine_row)
        self.engine_status = QLabel("")
        self.engine_status.setProperty("dim", True)
        engine_box.addWidget(self.engine_status)
        lay.addLayout(engine_box)

        browse.clicked.connect(self._browse_engine)
        detect.clicked.connect(self._detect_engine)
        self._detect_engine(quiet=True)

        # Data folder ----------------------------------------------------------
        data_row = QHBoxLayout()
        data_btn = make_button(i18n.tr("settings.dataFolder"), flat=True)
        data_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.data_dir()))))
        data_row.addWidget(data_btn)
        data_row.addStretch(1)
        lay.addLayout(data_row)

        lay.addStretch(1)
        close = make_button(i18n.tr("common.close"), accent=True)
        close.clicked.connect(self.accept)
        lay.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)

    def _browse_engine(self) -> None:
        exe = "photocraft-cli.exe" if os.name == "nt" else "photocraft-cli"
        file, _ = QFileDialog.getOpenFileName(self, i18n.tr("settings.enginePath"), "", f"{exe};;All files (*)")
        if file:
            self.engine_edit.setText(file)
            self._detect_engine()

    def _detect_engine(self, quiet: bool = False) -> None:
        path = self.engine_edit.text().strip()
        try:
            binary = PhotoCraftBinary(path or None)
            self.engine_status.setText(i18n.tr("settings.engineFound", version=binary.version()))
            self.engine_status.setProperty("error", False)
        except PhotoCraftError as e:
            self.engine_status.setText(str(e))
            self.engine_status.setProperty("error", True)
            if not quiet:
                QMessageBox.warning(self, i18n.tr("error.title"), str(e))
        self.engine_status.style().unpolish(self.engine_status)
        self.engine_status.style().polish(self.engine_status)

    def apply(self) -> None:
        self.settings.language = self.lang_combo.currentData()
        self.settings.theme = self.theme_combo.currentData()
        self.settings.persian_digits = self.fa_digits.isChecked()
        self.settings.photocraft_path = self.engine_edit.text().strip()


class AboutDialog(QDialog):
    """About + license texts (PhotoCraft MIT/Apache/NOTICE, Vazirmatn OFL, ...)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("app.about"))
        self.resize(560, 480)
        lay = QVBoxLayout(self)

        head = QLabel(f"EasyWalp {__version__}")
        head.setProperty("h1", True)
        sub = QLabel("Wallpaper release automation for the Wallify channel\nPowered by PhotoCraft engine")
        sub.setProperty("dim", True)
        lay.addWidget(head)
        lay.addWidget(sub)

        tabs = QTabWidget()
        lay.addWidget(tabs, 1)
        root = paths.bundled_dir().parent
        for title, rel in LICENSE_TABS:
            view = QTextEdit()
            view.setReadOnly(True)
            path = root / rel
            view.setPlainText(path.read_text(encoding="utf-8", errors="replace") if path.exists()
                              else f"(missing: {path})")
            tabs.addTab(view, title)

        close = make_button(i18n.tr("common.close"), accent=True)
        close.clicked.connect(self.accept)
        lay.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
