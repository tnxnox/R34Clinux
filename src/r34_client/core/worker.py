from __future__ import annotations

import logging
import threading
import time
import traceback
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

import socket
import weakref

logger = logging.getLogger(__name__)

_thread_local = threading.local()
_worker_sockets_lock = threading.Lock()
# Mapping of FunctionWorker -> WeakSet of active sockets
_worker_sockets: dict[FunctionWorker, weakref.WeakSet[socket.socket]] = {}


def register_socket_for_worker(worker: FunctionWorker, sock: socket.socket) -> None:
    with _worker_sockets_lock:
        if worker not in _worker_sockets:
            _worker_sockets[worker] = weakref.WeakSet()
        _worker_sockets[worker].add(sock)


def unregister_socket_for_worker(worker: FunctionWorker, sock: socket.socket) -> None:
    with _worker_sockets_lock:
        if worker in _worker_sockets:
            _worker_sockets[worker].discard(sock)
            if not _worker_sockets[worker]:
                del _worker_sockets[worker]


def cancel_worker_sockets(worker: FunctionWorker) -> None:
    with _worker_sockets_lock:
        socks = list(_worker_sockets.get(worker, []))
    for sock in socks:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass


_original_socket_class = socket.socket


class TrackedSocket(_original_socket_class):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        worker = getattr(_thread_local, "current_worker", None)
        if worker is not None:
            self._associated_worker = worker
            register_socket_for_worker(worker, self)
        else:
            self._associated_worker = None

    def close(self) -> None:
        worker = getattr(self, "_associated_worker", None)
        if worker is not None:
            unregister_socket_for_worker(worker, self)
        super().close()


# Apply the monkeypatch
socket.socket = TrackedSocket


class WorkerCancelledError(BaseException):
    """Exception raised when a background worker is cancelled."""
    pass


def is_current_worker_cancelled() -> bool:
    """Check if the currently executing worker has been cancelled."""
    worker = getattr(_thread_local, "current_worker", None)
    if worker is not None:
        return worker.is_cancelled()
    return False


def check_cancelled() -> None:
    """Raise WorkerCancelledError if the current worker is cancelled."""
    if is_current_worker_cancelled():
        raise WorkerCancelledError("Worker operation cancelled")


def cancellable_sleep(seconds: float) -> None:
    """Sleep for the specified time, checking for cancellation periodically."""
    start = time.time()
    while time.time() - start < seconds:
        check_cancelled()
        remaining = seconds - (time.time() - start)
        if remaining <= 0:
            break
        time.sleep(min(0.05, remaining))


class WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()


class FunctionWorker(QRunnable):
    def __init__(self, function: Callable[..., object], *args, **kwargs) -> None:
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self._cancel_event = threading.Event()

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def cancel(self) -> None:
        self._cancel_event.set()
        cancel_worker_sockets(self)

    @Slot()
    def run(self) -> None:
        if self.is_cancelled():
            self._safe_emit_cancelled()
            return

        _thread_local.current_worker = self
        try:
            result = self.function(*self.args, **self.kwargs)
        except WorkerCancelledError:
            self._safe_emit_cancelled()
            return
        except BaseException as exc:
            if isinstance(exc, SystemExit):
                raise
            error_text = traceback.format_exc()
            logger.error("Worker function raised an exception:\n%s", error_text)
            self._safe_emit_failed(error_text)
            return
        finally:
            _thread_local.current_worker = None

        self._safe_emit_finished(result)

    def _safe_emit_finished(self, result: object) -> None:
        try:
            self.signals.finished.emit(result)
        except RuntimeError:
            logger.debug("Could not emit 'finished' signal — receiver may have been deleted")
            return

    def _safe_emit_failed(self, error_text: str) -> None:
        try:
            self.signals.failed.emit(error_text)
        except RuntimeError:
            logger.debug("Could not emit 'failed' signal — receiver may have been deleted")
            return

    def _safe_emit_cancelled(self) -> None:
        try:
            self.signals.cancelled.emit()
        except RuntimeError:
            logger.debug("Could not emit 'cancelled' signal — receiver may have been deleted")
            return
