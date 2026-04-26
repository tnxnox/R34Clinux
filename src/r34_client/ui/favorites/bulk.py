from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

from r34_client.core.worker import FunctionWorker
from r34_client.core.models import Post
from r34_client.core.rate_limit import is_rate_limited_error_message
from r34_client.sync.pending_mutations import (
    clear_pending_add,
    clear_pending_remove,
    queue_pending_add,
    queue_pending_remove,
    save_pending_state,
)
from r34_client.ui.favorites.pending import process_pending_remote_mutations

if TYPE_CHECKING:
    from ..main_window import MainWindow


def add_multiple_favorites(window: MainWindow, posts: list[Post]) -> None:
    unique_posts = {post.id: post for post in posts}
    if not unique_posts:
        return

    window._set_status(f"Adding {len(unique_posts)} favorites...")
    window._mutation_token += 1
    token = window._mutation_token

    sync_enabled = window._sync_enabled()
    
    worker = FunctionWorker(
        add_multiple_favorites_impl,
        local_favorites=window.local_favorites,
        posts=list(unique_posts.values()),
        sync_enabled=sync_enabled,
        window_ref=window # Still need for some pending helpers but we'll be careful
    )
    worker.signals.finished.connect(lambda result: favorite_bulk_add_finished(window, token, result))
    worker.signals.failed.connect(window._operation_failed)
    window._start_worker(worker, workload="mutation")


def add_multiple_favorites_impl(local_favorites, posts: list[Post], sync_enabled: bool, window_ref: MainWindow) -> dict[str, object]:
    added_ids: list[int] = []
    failed_ids: list[int] = []
    deferred_sync_ids: list[int] = []
    failed_errors: list[str] = []

    for post in posts:
        local_favorites.add_favorite(post)
        if sync_enabled:
            queue_pending_add(window_ref, post.id, "queued optimistic bulk add", persist=False)
            deferred_sync_ids.append(post.id)
        else:
            clear_pending_add(window_ref, post.id, persist=False)
            clear_pending_remove(window_ref, post.id, persist=False)
        added_ids.append(post.id)

    save_pending_state(window_ref)

    if failed_ids:
        window._last_favorite_sync_failed = True
        window._last_favorite_sync_error = f"Bulk add failed for {len(failed_ids)} post(s)."
        window._last_favorite_sync_debug = "\n".join(failed_errors)
    else:
        window._last_favorite_sync_failed = False
        window._last_favorite_sync_error = ""
        window._last_favorite_sync_debug = ""

    return {
        "added_ids": added_ids,
        "failed_ids": failed_ids,
        "deferred_sync_ids": deferred_sync_ids,
        "failed_errors": failed_errors,
    }


def favorite_bulk_add_finished(window: MainWindow, token: int, result: object) -> None:
    if token != window._mutation_token:
        return

    if isinstance(result, dict):
        added_ids = [int(item) for item in result.get("added_ids", [])]
        failed_ids = [int(item) for item in result.get("failed_ids", [])]
        deferred_sync_ids = [int(item) for item in result.get("deferred_sync_ids", [])]
        failed_errors = [str(item) for item in result.get("failed_errors", [])]
    else:
        added_ids = []
        failed_ids = []
        deferred_sync_ids = []
        failed_errors = []

    for post_id in added_ids:
        window.favorite_ids.add(post_id)

    if failed_ids:
        window._set_status(
            f"Added {len(added_ids)} favorites; {len(failed_ids)} failed due to sync limits."
        )
        only_rate_limited_failures = all(
            is_rate_limited_error_message(message) or "degraded mode active" in message.lower()
            for message in failed_errors
        )
        if not only_rate_limited_failures:
            QMessageBox.warning(
                window,
                "Bulk Add Partial Failure",
                "Some favorites could not be added remotely.\n\n" + "\n".join(failed_errors[:12]),
            )
    else:
        if deferred_sync_ids:
            window._set_status(
                f"Added {len(added_ids)} favorites locally; queued {len(deferred_sync_ids)} for background remote sync."
            )
        else:
            window._set_status(f"Added {len(added_ids)} favorites.")

    if window._sync_enabled() and failed_ids:
        window._refresh_favorites()
    else:
        window._refresh_local_favorites()

    if window._sync_enabled() and deferred_sync_ids:
        process_pending_remote_mutations(window)


def remove_multiple_favorites(window: MainWindow, posts: list[Post]) -> None:
    unique_posts = {post.id: post for post in posts}
    if not unique_posts:
        return

    window._set_status(f"Removing {len(unique_posts)} favorites locally and queueing remote sync...")
    window._mutation_token += 1
    token = window._mutation_token

    sync_enabled = window._sync_enabled()

    worker = FunctionWorker(
        remove_multiple_favorites_impl,
        local_favorites=window.local_favorites,
        posts=list(unique_posts.values()),
        sync_enabled=sync_enabled,
        window_ref=window
    )
    worker.signals.finished.connect(lambda result: favorite_bulk_mutation_finished(window, token, result))
    worker.signals.failed.connect(window._operation_failed)
    window._start_worker(worker, workload="mutation")


def remove_multiple_favorites_impl(local_favorites, posts: list[Post], sync_enabled: bool, window_ref: MainWindow) -> dict[str, object]:
    requested_ids = sorted({post.id for post in posts})
    failed_ids: list[int] = []
    deferred_sync_ids: list[int] = []
    failed_errors: list[str] = []

    removed_count = local_favorites.remove_favorites(requested_ids)

    for post_id in requested_ids:
        if sync_enabled:
            queue_pending_remove(window_ref, post_id, "queued optimistic bulk remove", persist=False)
            deferred_sync_ids.append(post_id)
        else:
            clear_pending_remove(window_ref, post_id, persist=False)
            clear_pending_add(window_ref, post_id, persist=False)

    save_pending_state(window_ref)

    if failed_ids:
        window._last_favorite_sync_failed = True
        window._last_favorite_sync_error = f"Bulk remove failed for {len(failed_ids)} post(s)."
        window._last_favorite_sync_debug = "\n".join(failed_errors)
    else:
        window._last_favorite_sync_failed = False
        window._last_favorite_sync_error = ""
        window._last_favorite_sync_debug = ""

    return {
        "requested_ids": requested_ids,
        "removed_count": removed_count,
        "failed_ids": failed_ids,
        "deferred_sync_ids": deferred_sync_ids,
        "failed_errors": failed_errors,
    }


def favorite_bulk_mutation_finished(window: MainWindow, token: int, result: object) -> None:
    if token != window._mutation_token:
        return
    if isinstance(result, dict):
        requested_ids = [int(item) for item in result.get("requested_ids", [])]
        removed_count = int(result.get("removed_count", 0))
        failed_ids = [int(item) for item in result.get("failed_ids", [])]
        deferred_sync_ids = [int(item) for item in result.get("deferred_sync_ids", [])]
        failed_errors = [str(item) for item in result.get("failed_errors", [])]
    else:
        requested_ids = []
        removed_count = 0
        failed_ids = []
        deferred_sync_ids = []
        failed_errors = []

    for post_id in requested_ids:
        window.favorite_ids.discard(post_id)

    if failed_ids:
        window._set_status(
            f"Removed {removed_count} of {len(requested_ids)} favorites locally; {len(failed_ids)} failed and were kept."
        )
        QMessageBox.warning(
            window,
            "Bulk Remove Partial Failure",
            "Some favorites could not be removed remotely and were kept locally to avoid desync.\n\n"
            + "\n".join(failed_errors[:12]),
        )
    else:
        if deferred_sync_ids:
            if removed_count != len(requested_ids):
                window._set_status(
                    f"Removed {removed_count} of {len(requested_ids)} favorites locally; queued {len(deferred_sync_ids)} for background remote sync."
                )
            else:
                window._set_status(
                    f"Removed {removed_count} favorites locally; queued {len(deferred_sync_ids)} for background remote sync."
                )
        else:
            if removed_count != len(requested_ids):
                window._set_status(f"Removed {removed_count} of {len(requested_ids)} favorites.")
            else:
                window._set_status(f"Removed {removed_count} favorites.")

    if window._sync_enabled() and failed_ids:
        window._refresh_favorites()
    else:
        window._refresh_local_favorites()

    if window._sync_enabled() and deferred_sync_ids:
        process_pending_remote_mutations(window)
