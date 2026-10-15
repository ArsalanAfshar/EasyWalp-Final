"""Reusable EasyWalp widgets: drop zones, toggles, header, code preview card."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..i18n import i18n
from ..paths import bundled_dir

log = logging.getLogger("easywalp.ui")

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def load_pixmap(path: Path, max_size: QSize | None = None) -> QPixmap | None:
    try:
        pm = QPixmap(str(path))
    except Exception:  # pragma: no cover
        return None
    if pm.isNull():
        return None
    if max_size is not None and (pm.width() > max_size.width() or pm.height() > max_size.height()):
        return pm.scaled(max_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return pm


def logo_pixmap(size: int = 36) -> QPixmap | None:
    p = bundled_dir() / "logo" / "wallify-logo.png"
    if not p.exists():
        return None
    return load_pixmap(p, QSize(size, size))


class DropZone(QFrame):
    """A big drag-&-drop zone with a thumbnail, filename and original resolution."""

    changed = Signal(object)  # Path | None

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("dropZone", True)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(240, 170)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._path: Path | None = None
        self._drag_over = False

        self._layout = QVBoxLayout(self)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.setSpacing(6)

        self._thumb = QLabel()
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setMinimumHeight(90)
        self._title = QLabel(title)
        self._title.setProperty("h2", True)
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint = QLabel(i18n.tr("main.dropHere"))
        self._hint.setProperty("dim", True)
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fileinfo = QLabel("")
        self._fileinfo.setProperty("dim", True)
        self._fileinfo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._layout.addWidget(self._title)
        self._layout.addWidget(self._thumb)
        self._layout.addWidget(self._fileinfo)
        self._layout.addWidget(self._hint)

    # ------------------------------------------------------------- content
    def set_image(self, path: Path | None) -> None:
        self._path = path
        if path is None:
            self._thumb.clear()
            self._fileinfo.setText("")
            self.setProperty("filled", False)
            self._hint.setText(i18n.tr("main.dropHere"))
        else:
            pm = load_pixmap(path, QSize(300, 150))
            if pm is not None:
                self._thumb.setPixmap(pm)
            try:
                from PIL import Image

                with Image.open(path) as im:
                    size_text = f"{im.width}×{im.height}"
            except Exception:
                size_text = "?"
            self._fileinfo.setText(f"{path.name}  ·  {size_text}")
            self._hint.setText("")
            self.setProperty("filled", True)
        self._refresh_style()
        self.changed.emit(self._path)

    def image_path(self) -> Path | None:
        return self._path

    def set_title(self, title: str) -> None:
        self._title.setText(title)

    # ---------------------------------------------------------------- drag
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if self._accepts(event):
            self._drag_over = True
            self.setProperty("dragOver", True)
            self._refresh_style()
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._drag_over = False
        self.setProperty("dragOver", False)
        self._refresh_style()

    def dropEvent(self, event) -> None:  # noqa: N802
        self._drag_over = False
        self.setProperty("dragOver", False)
        for url in event.mimeData().urls():
            p = Path(url.toLocalFile())
            if p.suffix.lower() in IMAGE_EXTS:
                self.set_image(p)
                event.acceptProposedAction()
                return
        self._refresh_style()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        start = self._path.parent if self._path else Path.home()
        file, _ = QFileDialog.getOpenFileName(
            self, i18n.tr("main.dropHere").replace("\n", " "), str(start),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if file:
            self.set_image(Path(file))

    def _accepts(self, event) -> bool:
        if not event.mimeData().hasUrls():
            return False
        return any(Path(u.toLocalFile()).suffix.lower() in IMAGE_EXTS for u in event.mimeData().urls())

    def _refresh_style(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)


class SegmentToggle(QWidget):
    """A two-option segmented toggle (O/A, 2K/4K)."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        """options: list of (value, i18n-key-or-text)."""
        super().__init__(parent)
        self._values = [v for v, _ in options]
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self._buttons: list[QPushButton] = []
        for value, text in options:
            b = QPushButton(text)
            b.setCheckable(True)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setProperty("segment", True)
            self._group.addButton(b)
            b.clicked.connect(lambda _=False, v=value: self.changed.emit(v))
            row.addWidget(b)
            self._buttons.append(b)
        if self._buttons:
            self._buttons[0].setChecked(True)

    def value(self) -> str:
        for i, b in enumerate(self._buttons):
            if b.isChecked():
                return self._values[i]
        return self._values[0] if self._values else ""

    def set_value(self, value: str) -> None:
        for i, v in enumerate(self._values):
            self._buttons[i].setChecked(v == value)

    def set_option_text(self, value: str, text: str) -> None:
        if value in self._values:
            self._buttons[self._values.index(value)].setText(text)


class CodePreviewCard(QFrame):
    """Live summary: code, folder and the exact file names that will be written."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("card", True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(4)
        self._code = QLabel("")
        self._code.setProperty("h1", True)
        self._rows = QLabel("")
        self._rows.setProperty("dim", True)
        self._rows.setWordWrap(True)
        self._sizes = QLabel("")
        self._sizes.setProperty("dim", True)
        lay.addWidget(self._code)
        lay.addWidget(self._rows)
        lay.addWidget(self._sizes)

    def update_info(self, lines: list[str], code: str, sizes: str) -> None:
        self._code.setText(code)
        self._rows.setText("\n".join(lines))
        self._sizes.setText(sizes)


def make_button(text: str, accent: bool = False, flat: bool = False) -> QPushButton:
    b = QPushButton(text)
    if accent:
        b.setProperty("accent", True)
    if flat:
        b.setProperty("flat", True)
    return b
