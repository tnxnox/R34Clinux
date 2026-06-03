from __future__ import annotations

import unittest

from PySide6.QtCore import QCoreApplication

from r34_client.core.worker import FunctionWorker


class WorkerLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QCoreApplication.instance() or QCoreApplication([])

    def test_worker_run_ignores_finished_emit_after_signals_deleted(self) -> None:
        worker = FunctionWorker(lambda: 123)
        worker.signals.deleteLater()
        self._app.processEvents()

        worker.run()

    def test_worker_run_ignores_failed_emit_after_signals_deleted(self) -> None:
        def boom() -> object:
            raise RuntimeError("boom")

        worker = FunctionWorker(boom)
        worker.signals.deleteLater()
        self._app.processEvents()

        worker.run()
