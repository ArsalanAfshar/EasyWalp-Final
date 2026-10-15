"""First-run setup wizard: pick a PSD, map the 4 layers that matter, mark the
code position, validate and dry-run through the real PhotoCraft pipeline."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..i18n import i18n
from ..photocraft import PhotoCraftBinary, PhotoCraftError
from ..pipeline import PipelineError
from ..presets import (
    LayerRef,
    Preset,
    PresetError,
    detect_code_span,
    import_psd_as_preset,
    split_code_text,
)
from .. import wizard as wiz
from .widgets import make_button
from .worker import AsyncCall

log = logging.getLogger("easywalp.ui.wizard")

EXPECTED_ASPECTS = {"desktop": 16 / 9, "mobile": 9 / 16}


class WizardDialog(QDialog):
    """4-step wizard; creates a working preset in storage and saves on finish."""

    presets_changed = Signal()

    def __init__(self, settings, binary: PhotoCraftBinary, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.binary = binary
        self.preset: Preset | None = None
        self.doc_info: dict = {}
        self.candidates: list[wiz.LayerCandidate] = []
        self.thumbs: dict[int, Path] = {}
        self._analyzed = False

        self.setWindowTitle(i18n.tr("wizard.title"))
        self.resize(720, 560)
        lay = QVBoxLayout(self)

        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self._build_page_pick()
        self._build_page_map()
        self._build_page_code()
        self._build_page_finish()

        nav = QHBoxLayout()
        self.back_btn = make_button("←")
        self.next_btn = make_button(i18n.tr("common.ok"), accent=True)
        self.cancel_btn = make_button(i18n.tr("common.cancel"))
        nav.addWidget(self.back_btn)
        nav.addWidget(self.cancel_btn)
        nav.addStretch(1)
        nav.addWidget(self.next_btn)
        lay.addLayout(nav)

        self.back_btn.clicked.connect(self._go_back)
        self.cancel_btn.clicked.connect(self._cancel)
        self.next_btn.clicked.connect(self._go_next)
        self._sync_buttons()

    # ------------------------------------------------------------ page 1
    def _build_page_pick(self) -> None:
        page = QWidget()
        lay = QVBoxLayout(page)
        title = QLabel(i18n.tr("wizard.step1"))
        title.setProperty("h1", True)
        lay.addWidget(title)
        row = QHBoxLayout()
        self.psd_edit = QLineEdit()
        pick = make_button(i18n.tr("main.browse"))
        analyze = make_button(i18n.tr("wizard.dryRun"), accent=True)
        analyze.setText("Analyze")
        row.addWidget(self.psd_edit, 1)
        row.addWidget(pick)
        lay.addLayout(row)
        pick.clicked.connect(self._pick_psd)
        analyze.clicked.connect(self._analyze)
        self.pick_status = QLabel("")
        self.pick_status.setProperty("dim", True)
        self.pick_status.setWordWrap(True)
        lay.addWidget(self.pick_status)
        lay.addStretch(1)
        self._analyze_btn = analyze
        self.stack.addWidget(page)

    def _pick_psd(self) -> None:
        file, _ = QFileDialog.getOpenFileName(self, i18n.tr("wizard.pickPsd"), "", "Photoshop (*.psd *.psb)")
        if file:
            self.psd_edit.setText(file)

    def _analyze(self) -> None:
        psd = Path(self.psd_edit.text().strip())
        if not psd.exists():
            QMessageBox.warning(self, i18n.tr("error.title"), f"{psd}")
            return
        self.pick_status.setText("…")
        self._analyze_btn.setEnabled(False)

        def work():
            preset = import_psd_as_preset(psd, psd.stem, __version__)
            info = wiz.inspect_psd(self.binary, preset.template_path)
            return preset, info

        self._call(work, self._analyzed_ok)

    def _analyzed_ok(self, result) -> None:
        preset, info = result
        self.preset = preset
        self.doc_info = info
        self.candidates = wiz.top_level_layers(info)
        self._analyzed = True
        self.pick_status.setText(
            f"{info.get('width', '?')}×{info.get('height', '?')}  ·  {len(self.candidates)} layers"
        )
        self._populate_combos()
        self._start_thumbnails()
        self._analyze_btn.setEnabled(True)
        self.next_btn.setEnabled(True)
        self.stack.setCurrentIndex(1)
        self._sync_buttons()

    def _start_thumbnails(self) -> None:
        psd = self.preset.template_path

        def work():
            return wiz.export_layer_thumbnails(self.binary, psd, psd.parent / "thumbs")

        self._call(work, self._thumbs_ok, fail_ok=True)

    def _thumbs_ok(self, result) -> None:
        self.thumbs = result or {}
        for combo in (self.so_desktop_combo, self.so_mobile_combo, self.fill_combo, self.text_combo):
            self._decorate_combo(combo)

    # ------------------------------------------------------------ page 2
    def _build_page_map(self) -> None:
        page = QWidget()
        lay = QVBoxLayout(page)
        title = QLabel(i18n.tr("wizard.step2"))
        title.setProperty("h1", True)
        lay.addWidget(title)
        self.so_desktop_combo = self._add_combo(lay, i18n.tr("wizard.layers.desktopSO"), "Smart Object")
        self.so_mobile_combo = self._add_combo(lay, i18n.tr("wizard.layers.mobileSO"), "Smart Object")
        self.fill_combo = self._add_combo(lay, i18n.tr("wizard.layers.fill"), "Fill")
        self.text_combo = self._add_combo(lay, i18n.tr("wizard.layers.text"), "Type")
        self.map_status = QLabel("")
        self.map_status.setProperty("dim", True)
        self.map_status.setWordWrap(True)
        lay.addWidget(self.map_status)
        lay.addStretch(1)
        for c in (self.so_desktop_combo, self.so_mobile_combo, self.fill_combo, self.text_combo):
            c.currentIndexChanged.connect(self._mapping_changed)

    def _add_combo(self, lay: QVBoxLayout, label: str, kind: str) -> QComboBox:
        row = QHBoxLayout()
        lab = QLabel(label)
        lab.setMinimumWidth(220)
        combo = QComboBox()
        combo.setMinimumHeight(34)
        combo.setIconSize(QSize(28, 28))
        row.addWidget(lab)
        row.addWidget(combo, 1)
        lay.addLayout(row)
        combo.setProperty("kind", kind)
        return combo

    def _populate_combos(self) -> None:
        for combo in (self.so_desktop_combo, self.so_mobile_combo):
            self._fill_combo(combo, kinds={"Smart Object"})
        self._fill_combo(self.fill_combo, kinds={"Fill"})
        self._fill_combo(self.text_combo, kinds={"Type"})
        self._auto_select()
        self._mapping_changed()

    def _fill_combo(self, combo: QComboBox, kinds: set[str]) -> None:
        combo.clear()
        for cand in self.candidates:
            if cand.kind in kinds:
                thumb = self.thumbs.get(cand.id)
                icon = QIcon(str(thumb)) if thumb else QIcon()
                combo.addItem(icon, cand.label, cand.id)

    def _decorate_combo(self, combo: QComboBox) -> None:
        for i in range(combo.count()):
            lid = combo.itemData(i)
            thumb = self.thumbs.get(int(lid))
            if thumb:
                combo.setItemIcon(i, QIcon(str(thumb)))

    def _auto_select(self) -> None:
        """Prefer sensibly named layers to help non-technical users."""
        hints = {
            "so_desktop_combo": ("desktop", "imac", "pc", "monitor"),
            "so_mobile_combo": ("mobile", "phone", "iphone"),
            "fill_combo": ("color", "bg", "background", "solid"),
            "text_combo": ("code", "text", "label"),
        }
        for attr, words in hints.items():
            combo: QComboBox = getattr(self, attr)
            if combo.count() == 0:
                continue
            chosen = 0
            for i in range(combo.count()):
                name = combo.itemText(i).lower()
                if any(w in name for w in words):
                    chosen = i
                    break
            combo.setCurrentIndex(chosen)

    def _mapping_changed(self) -> None:
        if not self.preset:
            return
        ok, problems = self._apply_mapping()
        self.map_status.setText("\n".join(problems) if problems else "")
        self.next_btn.setEnabled(ok)

    def _apply_mapping(self) -> tuple[bool, list[str]]:
        problems: list[str] = []
        p = self.preset

        def ref(combo: QComboBox) -> LayerRef | None:
            lid = combo.currentData()
            if lid is None:
                return None
            cand = next((c for c in self.candidates if c.id == int(lid)), None)
            return LayerRef(id=int(lid), name=cand.name, kind=cand.kind) if cand else None

        p.desktop_smart_object = ref(self.so_desktop_combo)
        p.mobile_smart_object = ref(self.so_mobile_combo)
        p.solid_color_fill = ref(self.fill_combo)
        p.text_layer = ref(self.text_combo)
        if p.desktop_smart_object is None or p.mobile_smart_object is None:
            problems.append("- " + i18n.tr("wizard.layers.desktopSO") + " / " + i18n.tr("wizard.layers.mobileSO"))
        if p.solid_color_fill is None:
            problems.append("- " + i18n.tr("wizard.layers.fill"))
        if p.text_layer is None:
            problems.append("- " + i18n.tr("wizard.layers.text"))
        return (not problems), problems

    # ------------------------------------------------------------ page 3
    def _build_page_code(self) -> None:
        page = QWidget()
        lay = QVBoxLayout(page)
        title = QLabel(i18n.tr("wizard.step3"))
        title.setProperty("h1", True)
        lay.addWidget(title)
        self.text_view = QLineEdit()
        self.text_view.setMinimumHeight(38)
        lay.addWidget(self.text_view)
        hint = QLabel(i18n.tr("wizard.codeHint"))
        hint.setProperty("dim", True)
        lay.addWidget(hint)
        self.detect_label = QLabel("")
        lay.addWidget(self.detect_label)
        self.code_status = QLabel("")
        self.code_status.setProperty("dim", True)
        self.code_status.setWordWrap(True)
        lay.addWidget(self.code_status)
        lay.addStretch(1)

    # ------------------------------------------------------------ page 4
    def _build_page_finish(self) -> None:
        page = QWidget()
        lay = QVBoxLayout(page)
        title = QLabel(i18n.tr("wizard.step4"))
        title.setProperty("h1", True)
        lay.addWidget(title)
        self.finish_status = QLabel("")
        self.finish_status.setProperty("dim", True)
        self.finish_status.setWordWrap(True)
        lay.addWidget(self.finish_status)
        bar_row = QHBoxLayout()
        self.dry_bar = QProgressBar()
        self.dry_bar.setRange(0, 100)
        self.dry_btn = make_button(i18n.tr("wizard.dryRun"), accent=True)
        bar_row.addWidget(self.dry_btn, 1)
        bar_row.addWidget(self.dry_bar, 2)
        lay.addLayout(bar_row)
        self.dry_thumb = QLabel("")
        self.dry_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.dry_thumb, 1)

        self.dry_btn.clicked.connect(self._dry_run)

    # ------------------------------------------------------------ nav
    def _go_back(self) -> None:
        i = self.stack.currentIndex()
        if i > 0:
            self.stack.setCurrentIndex(i - 1)
        self._sync_buttons()

    def _go_next(self) -> None:
        i = self.stack.currentIndex()
        if i == 0:
            self._analyze()
            return
        if i == 1:
            ok, _ = self._apply_mapping()
            if not ok:
                return
            self._enter_code_page()
            return
        if i == 2:
            if not self._apply_code_span():
                return
            self._enter_finish_page()
            return
        if i == 3:
            self._save_and_close()

    def _cancel(self) -> None:
        if self.preset is not None:
            # Keep nothing half-built: remove the cloned template unless saved.
            if not self._saved:
                self.preset.delete()
        self.reject()

    _saved = False

    def _sync_buttons(self) -> None:
        i = self.stack.currentIndex()
        self.back_btn.setVisible(i > 0)
        if i == 0:
            self.next_btn.setText("Analyze")
            self.next_btn.setEnabled(bool(self.psd_edit.text().strip()))
        elif i == 1:
            self.next_btn.setText(i18n.tr("common.ok"))
        elif i == 2:
            self.next_btn.setText(i18n.tr("common.ok"))
        else:
            self.next_btn.setText(i18n.tr("wizard.save"))
        if i == 1:
            ok, _ = self._apply_mapping()
            self.next_btn.setEnabled(ok)

    # ------------------------------------------------------------ code page
    def _enter_code_page(self) -> None:
        self.stack.setCurrentIndex(2)
        self._sync_buttons()
        psd = self.preset.template_path

        def work():
            return wiz.text_layer_info(self.binary, psd, self.preset.text_layer)

        self._call(work, self._text_ok)

    def _text_ok(self, info: dict) -> None:
        text = str(info.get("text", ""))
        self._text_full = text
        self._text_font = str(info.get("font", ""))
        self.text_view.setText(text)
        span = detect_code_span(text)
        if span:
            self.text_view.setSelection(span[0], span[1] - span[0])
            self.detect_label.setText(f"{i18n.tr('wizard.detectCode')}: {text[span[0]:span[1]]}")
        else:
            self.detect_label.setText(i18n.tr("wizard.detectCode") + ": —")
        # fonts + aspect warnings
        notes = []
        fonts = sorted({self._text_font} - {""}) if self._text_font else []
        installed = wiz.installed_font_families()
        if fonts and "*" not in installed:
            missing = [f for f in fonts if not any(f.lower() in s.lower() for s in installed)]
            if missing:
                notes.append("⚠ " + i18n.tr("wizard.fontMissing", fonts=", ".join(missing)))
            self._font_missing = missing
        else:
            self._font_missing = []
        for label, ref in (("desktop", self.preset.desktop_smart_object), ("mobile", self.preset.mobile_smart_object)):
            if ref:
                notes.append(f"• {label}: {ref.name}")
        self.code_status.setText("\n".join(notes))
        self.next_btn.setEnabled(bool(span))

    def _apply_code_span(self) -> bool:
        text = self._text_full
        start = self.text_view.selectionStart()
        length = self.text_view.selectedText()
        if start < 0 or not length:
            span = detect_code_span(text)
            if not span:
                QMessageBox.warning(self, i18n.tr("error.title"), i18n.tr("wizard.codeHint"))
                return False
            start, end = span
        else:
            end = start + len(length)
        self.preset.text_code = split_code_text(text, (start, end))
        return True

    # ------------------------------------------------------------ finish page
    def _enter_finish_page(self) -> None:
        self.stack.setCurrentIndex(3)
        self._sync_buttons()
        self._probe_contents()

    def _probe_contents(self) -> None:
        psd = self.preset.template_path
        pairs = [("desktop", self.preset.desktop_smart_object), ("mobile", self.preset.mobile_smart_object)]

        def work():
            sizes = {}
            for label, ref in pairs:
                w, h, _f = wiz.smart_object_contents(self.binary, psd, ref, psd.parent / "probe")
                sizes[label] = (w, h)
            return sizes

        self._call(work, self._contents_ok)

    def _contents_ok(self, sizes: dict) -> None:
        d = sizes.get("desktop", (0, 0))
        m = sizes.get("mobile", (0, 0))
        self.preset.desktop_contents.width, self.preset.desktop_contents.height = d
        self.preset.mobile_contents.width, self.preset.mobile_contents.height = m
        notes = []
        for label, (w, h) in (("desktop", d), ("mobile", m)):
            expected = EXPECTED_ASPECTS[label]
            aspect = w / h if h else 0
            if aspect and abs(aspect - expected) / expected > 0.01:
                notes.append(
                    "⚠ " + i18n.tr(
                        "wizard.aspectWarning",
                        so=label, w=w, h=h, aspect=f"{aspect:.2f}",
                        expected="16:9" if label == "desktop" else "9:16",
                    )
                )
        notes.append(f"• desktop SO contents: {d[0]}×{d[1]}   • mobile SO contents: {m[0]}×{m[1]}")
        if self._font_missing:
            notes.append("⚠ " + i18n.tr("wizard.fontMissing", fonts=", ".join(self._font_missing)))
        self.finish_status.setText("\n".join(notes))

    def _dry_run(self) -> None:
        self.dry_btn.setEnabled(False)
        self.dry_bar.setValue(5)

        def work():
            preview, warnings = wiz.dry_run(self.binary, self.preset, self.preset.dir)
            return preview, warnings

        self._call(work, self._dry_ok, on_fail=self._dry_fail)
        # crude progress: indeterminate busy feel
        self.dry_bar.setRange(0, 0)

    def _dry_ok(self, result) -> None:
        preview, warnings = result
        self.dry_bar.setRange(0, 100)
        self.dry_bar.setValue(100)
        pm = QPixmap(str(preview))
        if not pm.isNull():
            self.dry_thumb.setPixmap(
                pm.scaled(560, 340, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )
        if warnings:
            self.finish_status.setText(self.finish_status.text() + "\n" + "\n".join("⚠ " + w for w in warnings))
        self.dry_btn.setEnabled(True)
        self.dry_btn.setText(i18n.tr("wizard.dryRunDone"))

    def _dry_fail(self, title: str, details: str) -> None:
        self.dry_bar.setRange(0, 100)
        self.dry_bar.setValue(0)
        self.dry_btn.setEnabled(True)
        from .mainwindow import error_box

        error_box(self, title, details)

    def _save_and_close(self) -> None:
        assert self.preset is not None
        self.preset.fonts = [f for f in {self._text_font} if f]
        self.preset.app_version = __version__
        self.preset.save()
        self._saved = True
        self.presets_changed.emit()
        self.accept()

    # ------------------------------------------------------------ async glue
    def _call(self, fn, on_done, on_fail=None, fail_ok: bool = False) -> None:
        self.setEnabled(False)

        def done(result):
            self.setEnabled(True)
            on_done(result)

        def fail(title: str, details: str):
            self.setEnabled(True)
            if fail_ok:
                log.warning("wizard async step failed: %s", title)
                return
            (on_fail or self._default_fail)(title, details)

        call = AsyncCall(fn, done, fail, self)
        call.start()

    def _default_fail(self, title: str, details: str) -> None:
        from .mainwindow import error_box

        error_box(self, title, details)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
izeEvent(event)
