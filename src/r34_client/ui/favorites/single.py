from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

from r34_client.core.worker import FunctionWorker
from r34_client.core.models import Post
from r34_client.sync.pending_mutations import clear_pending_add, clear_pending_remove, queue_pending_add, queue_pending_remove
from r34_client.ui.favorites.pending import process_pending_remote_mutations

if TYPE_CHECKING:
    from ..main_window import MainWindow


def add_favorite(window: MainWindow, post: Post) -> None:
    if window._sync_enabled():
        window._set_right_status(f"Adding #{post.id} locally and queueing remote sync...")
    else:
        window._set_right_status(f"Adding #{post.id} to local favorites...")

    window._mutation_token += 1
    token = window._mutation_token

    worker = FunctionWorker(add_favorite_impl, window, post)
    worker.signals.finished.connect(lambda _: favorite_mutation_finished(window, token, post.id, True))
    worker.signals.failed.connect(window._operation_failed)
    window._start_worker(worker, workload="mutation")


def remove_favorite(window: MainWindow, post: Post) -> None:
    if window._sync_enabled():
        window._set_right_status(f"Removing #{post.id} locally and queueing remote sync...")
    else:
        window._set_right_status(f"Removing #{post.id} from local favorites...")

    window._mutation_token += 1
    token = window._mutation_token

    worker = FunctionWorker(remove_favorite_impl, window, post)
    worker.signals.finished.connect(lambda _: favorite_mutation_finished(window, token, post.id, False))
    worker.signals.failed.connect(window._operation_failed)
    window._start_worker(worker, workload="mutation")


def add_favorite_impl(window: MainWindow, post: Post) -> int:
    window.local_favorites.add_favorite(post)
    if window._sync_enabled():
        queue_pending_add(window, post.id, "queued optimistic add")
    else:
        clear_pending_add(window, post.id)
        clear_pending_remove(window, post.id)
    return post.id


def remove_favorite_impl(window: MainWindow, post: Post) -> int:
    window.local_favorites.remove_favorites([post.id])
    if window._sync_enabled():
        queue_pending_remove(window, post.id, "queued optimistic remove")
    else:
        clear_pending_remove(window, post.id)
        clear_pending_add(window, post.id)
    return post.id


def favorite_mutation_finished(window: MainWindow, token: int, post_id: int, favorited: bool) -> None:
    if token != window._mutation_token:
        return

    window._last_favorite_sync_failed = False
    window._last_favorite_sync_error = ""
    window._last_favorite_sync_debug = ""

    if favorited:
        window.favorite_ids.add(post_id)
    else:
        window.favorite_ids.discard(post_id)
    if window._sync_enabled():
        action = "added" if favorited else "removed"
        window._set_status(f"Favorite {action} locally for #{post_id}; remote sync queued.")
        process_pending_remote_mutations(window)
    else:
        window._set_status(f"Local favorite updated for post #{post_id}.")
    window._refresh_local_favorites()


def operation_failed(window: MainWindow, error_text: str) -> None:
    window.preview_label.setText("Unable to load content.")
    window.meta_view.setPlainText(error_text)
    window._mark_rate_limited_if_needed("operation_failed", error_text)
    window._set_status("Operation failed.")
    QMessageBox.critical(window, "R34 Linux Client", error_text)


def toggle_current_favorite(window: MainWindow) -> None:
    post = window._current_post()
    if post is None:
        return
    if post.id in window.favorite_ids:
        window._remove_favorite(post)
    else:
        window._add_favorite(post)
