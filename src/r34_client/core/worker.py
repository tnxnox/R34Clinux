from __future__ import annotations

import logging
import traceback
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

logger = logging.getLogger(__name__)


class WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class FunctionWorker(QRunnable):
    def __init__(self, function: Callable[..., object], *args, **kwargs) -> None:
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.function(*self.args, **self.kwargs)
        except Exception:
            error_text = traceback.format_exc()
            logger.error("Worker function raised an exception:\n%s", error_text)
            self._safe_emit_failed(error_text)
            return
        self._safe_emit_finished(result)

    def _safe_emit_finished(self, result: object) -> None:
        try:
            self.signals.finished.emit(result)
        except RuntimeError:
            # Receiver QObject can be deleted if the window closes while work is still running.
            logger.debug("Could not emit 'finished' signal — receiver may have been deleted")
            return

    def _safe_emit_failed(self, error_text: str) -> None:
        try:
            self.signals.failed.emit(error_text)
        except RuntimeError:
            # Ignore late signal delivery during teardown.
            logger.debug("Could not emit 'failed' signal — receiver may have been deleted")
            return
