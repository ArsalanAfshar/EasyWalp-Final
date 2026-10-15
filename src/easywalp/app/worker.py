"""Background worker for Generate: keeps the UI responsive; reports progress,
warnings, errors and the finished result via Qt signals."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..photocraft import PhotoCraftBinary
from ..pipeline import CodeInfo, GenerateResult, Pipeline, PipelineError
from ..presets import Preset, PresetError
from ..wizard import PhotoCraftError

log = logging.getLogger("easywalp.ui.worker")


@dataclass
class GenerateRequest:
    preset: Preset
    desktop: Path
    mobile: Path
    category: str
    number: int
    out_base: Path
    options_override: dict = field(default_factory=dict)


class GenerateWorker(QThread):
    progress = Signal(str, float)          # stage key, 0..1
    failed = Signal(str, str)              # title, details
    warnings = Signal(list)                # list[str] (non-blocking notes)
    finished_ok = Signal(object)           # GenerateResult

    def __init__(self, request: GenerateRequest, binary: PhotoCraftBinary, parent=None) -> None:
        super().__init__(parent)
        self.request = request
        self.binary = binary

    def run(self) -> None:  # noqa: D102 - QThread override
        pipeline = Pipeline(self.binary)
        try:
            result = pipeline.generate(
                self.request.preset,
                self.request.desktop,
                self.request.mobile,
                self.request.category,
                self.request.number,
                self.request.out_base,
                progress=lambda stage, frac: self.progress.emit(stage, frac),
                options_override=self.request.options_override,
            )
        except (PipelineError, PhotoCraftError) as e:
            self.failed.emit(str(e), "")
        except Exception as e:  # unexpected - show with copyable details
            log.exception("generate failed")
            self.failed.emit(str(e), _traceback_text(e))
        else:
            if result.warnings:
                self.warnings.emit(list(result.warnings))
            self.finished_ok.emit(result)


def _traceback_text(e: Exception) -> str:
    import traceback

    return "".join(traceback.format_exception(type(e), e, e.__traceback__))


class AsyncCall(QThread):
    """Run `fn()` on a worker thread; deliver success/failure on the GUI thread."""

    succeeded = Signal(object)
    failed_sig = Signal(str, str)

    def __init__(self, fn, on_done, on_fail, parent=None) -> None:
        super().__init__(parent)
        self._fn = fn
        self.succeeded.connect(on_done)
        self.failed_sig.connect(on_fail)

    def run(self) -> None:
        try:
            result = self._fn()
        except (PipelineError, PhotoCraftError, PresetError) as e:
            self.failed_sig.emit(str(e), "")
        except Exception as e:  # pragma: no cover - unexpected
            log.exception("async call failed")
            self.failed_sig.emit(str(e), _traceback_text(e))
        else:
            self.succeeded.emit(result)


__all__ = ["GenerateWorker", "GenerateRequest", "GenerateResult", "CodeInfo", "AsyncCall"]
