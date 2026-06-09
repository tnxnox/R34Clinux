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

    def test_socket_registration_and_cancellation(self) -> None:
        import socket
        from r34_client.core.worker import _worker_sockets, _thread_local

        worker = FunctionWorker(lambda: None)
        _thread_local.current_worker = worker

        try:
            # Create a socket inside the worker context
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Verify it is registered
            self.assertIn(worker, _worker_sockets)
            self.assertIn(sock, _worker_sockets[worker])

            # Now cancel the worker and check that the socket is closed
            worker.cancel()
            
            # Since the socket was shut down and closed, its file descriptor is -1 (closed)
            self.assertEqual(sock.fileno(), -1)
        finally:
            _thread_local.current_worker = None
            try:
                sock.close()
            except Exception:
                pass

    def test_worker_cancelled_signal_emitted(self) -> None:
        from r34_client.core.worker import check_cancelled

        def run_with_cancel() -> None:
            check_cancelled()

        worker = FunctionWorker(run_with_cancel)
        worker.cancel()

        cancelled_called = False
        def on_cancelled() -> None:
            nonlocal cancelled_called
            cancelled_called = True

        worker.signals.cancelled.connect(on_cancelled)
        worker.run()
        self.assertTrue(cancelled_called)
