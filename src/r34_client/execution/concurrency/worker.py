from __future__ import annotations

import traceback
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class FunctionWorker(QRunnable):
    def __init__(self, function: Callable[[], object]) -> None:
        super().__init__()
        self.function = function
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.function()
        except Exception:
            self._safe_emit_failed(traceback.format_exc())
            return
        self._safe_emit_finished(result)

    def _safe_emit_finished(self, result: object) -> None:
        try:
            self.signals.finished.emit(result)
        except RuntimeError:
            # Receiver QObject can be deleted if the window closes while work is still running.
            return

    def _safe_emit_failed(self, error_text: str) -> None:
        try:
            self.signals.failed.emit(error_text)
        except RuntimeError:
            # Ignore late signal delivery during teardown.
            return
