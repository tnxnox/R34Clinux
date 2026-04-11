from __future__ import annotations

import json
import random
import re
import time
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QInputDialog, QMessageBox

from ...concurrency import FunctionWorker
from ...flaresolverr_client import FlareSolverrError
from ...models import Post
from ...rate_limit import is_rate_limited_error_message

if TYPE_CHECKING:
    from ..windows.main_window import MainWindow


def _wait_for_degraded_mode_window(window: MainWindow, *, max_wait_seconds: float) -> bool:
    waited = 0.0
    while window._degraded_mode_active() and waited < max_wait_seconds:
        step = min(0.5, max_wait_seconds - waited)
        time.sleep(step)
        waited += step
    return not window._degraded_mode_active()


def _pending_state_path(window: MainWindow):
    return window._sync_debug_log_path.parent / "pending-mutations.json"


def _ensure_pending_state_loaded(window: MainWindow) -> None:
    if getattr(window, "_pending_state_loaded", False):
        return

    window._pending_state_loaded = True
    window._pending_remote_add_meta = {}
    window._pending_remote_remove_meta = {}
    window._pending_endpoint_streaks = {"add": 0, "remove": 0}

    path = _pending_state_path(window)
    if not path.exists():
        return

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return

    for entry in payload.get("add", []):
        try:
            post_id = int(entry.get("id"))
        except Exception:
            continue
        window._pending_remote_add_ids.add(post_id)
        window._pending_remote_add_meta[post_id] = {
            "attempts": int(entry.get("attempts", 0)),
            "first_queued_at": float(entry.get("first_queued_at", time.time())),
            "next_attempt_at": float(entry.get("next_attempt_at", 0.0)),
            "last_error": str(entry.get("last_error", "")),
        }

    for entry in payload.get("remove", []):
        try:
            post_id = int(entry.get("id"))
        except Exception:
            continue
        window._pending_remote_remove_ids.add(post_id)
        window._pending_remote_remove_meta[post_id] = {
            "attempts": int(entry.get("attempts", 0)),
            "first_queued_at": float(entry.get("first_queued_at", time.time())),
            "next_attempt_at": float(entry.get("next_attempt_at", 0.0)),
            "last_error": str(entry.get("last_error", "")),
        }


def restore_pending_remote_mutations(window: MainWindow) -> None:
    _ensure_pending_state_loaded(window)


def _save_pending_state(window: MainWindow) -> None:
    _ensure_pending_state_loaded(window)
    path = _pending_state_path(window)
    path.parent.mkdir(parents=True, exist_ok=True)

    add_entries = []
    for post_id in sorted(window._pending_remote_add_ids):
        meta = window._pending_remote_add_meta.get(post_id, {})
        add_entries.append(
            {
                "id": post_id,
                "attempts": int(meta.get("attempts", 0)),
                "first_queued_at": float(meta.get("first_queued_at", time.time())),
                "next_attempt_at": float(meta.get("next_attempt_at", 0.0)),
                "last_error": str(meta.get("last_error", "")),
            }
        )

    remove_entries = []
    for post_id in sorted(window._pending_remote_remove_ids):
        meta = window._pending_remote_remove_meta.get(post_id, {})
        remove_entries.append(
            {
                "id": post_id,
                "attempts": int(meta.get("attempts", 0)),
                "first_queued_at": float(meta.get("first_queued_at", time.time())),
                "next_attempt_at": float(meta.get("next_attempt_at", 0.0)),
                "last_error": str(meta.get("last_error", "")),
            }
        )

    path.write_text(json.dumps({"add": add_entries, "remove": remove_entries}, indent=2), encoding="utf-8")


def _queue_pending_add(window: MainWindow, post_id: int, reason: str) -> None:
    _ensure_pending_state_loaded(window)
    target = int(post_id)
    window._pending_remote_remove_ids.discard(target)
    window._pending_remote_remove_meta.pop(target, None)

    meta = window._pending_remote_add_meta.get(target)
    if meta is None:
        meta = {
            "attempts": 0,
            "first_queued_at": time.time(),
            "next_attempt_at": 0.0,
            "last_error": "",
        }
    meta["last_error"] = reason
    window._pending_remote_add_ids.add(target)
    window._pending_remote_add_meta[target] = meta
    _save_pending_state(window)


def _queue_pending_remove(window: MainWindow, post_id: int, reason: str) -> None:
    _ensure_pending_state_loaded(window)
    target = int(post_id)
    window._pending_remote_add_ids.discard(target)
    window._pending_remote_add_meta.pop(target, None)

    meta = window._pending_remote_remove_meta.get(target)
    if meta is None:
        meta = {
            "attempts": 0,
            "first_queued_at": time.time(),
            "next_attempt_at": 0.0,
            "last_error": "",
        }
    meta["last_error"] = reason
    window._pending_remote_remove_ids.add(target)
    window._pending_remote_remove_meta[target] = meta
    _save_pending_state(window)


def _clear_pending_add(window: MainWindow, post_id: int) -> None:
    _ensure_pending_state_loaded(window)
    target = int(post_id)
    window._pending_remote_add_ids.discard(target)
    window._pending_remote_add_meta.pop(target, None)
    _save_pending_state(window)


def _clear_pending_remove(window: MainWindow, post_id: int) -> None:
    _ensure_pending_state_loaded(window)
    target = int(post_id)
    window._pending_remote_remove_ids.discard(target)
    window._pending_remote_remove_meta.pop(target, None)
    _save_pending_state(window)


def _extract_retry_after_seconds(message: str) -> int | None:
    match = re.search(r"retry[-_ ]?after[^0-9]*(\d+)", message or "", flags=re.IGNORECASE)
    if not match:
        return None
    return max(0, int(match.group(1)))


def _compute_backoff_seconds(window: MainWindow, endpoint: str, attempts: int, message: str) -> float:
    _ensure_pending_state_loaded(window)
    retry_after = _extract_retry_after_seconds(message)
    streaks = window._pending_endpoint_streaks
    current_streak = int(streaks.get(endpoint, 0)) + 1
    streaks[endpoint] = current_streak

    base_delay = min(120.0, 1.25 * (2 ** min(current_streak, 6)))
    if retry_after is not None:
        base_delay = max(base_delay, float(retry_after))

    jitter = random.uniform(0.2, max(0.4, base_delay * 0.35))
    return base_delay + jitter


def _note_endpoint_success(window: MainWindow, endpoint: str) -> None:
    _ensure_pending_state_loaded(window)
    window._pending_endpoint_streaks[endpoint] = 0


def process_pending_remote_mutations(window: MainWindow) -> None:
    _ensure_pending_state_loaded(window)
    if not window._sync_enabled():
        return
    if not window._pending_remote_add_ids and not window._pending_remote_remove_ids:
        return
    if window._pending_sync_worker_active:
        return

    window._pending_sync_worker_active = True
    worker = FunctionWorker(lambda: process_pending_remote_mutations_impl(window))
    worker.signals.finished.connect(lambda result: pending_remote_mutations_finished(window, result))
    worker.signals.failed.connect(lambda error_text: pending_remote_mutations_failed(window, error_text))
    window._start_worker(worker, workload="mutation")


def process_pending_remote_mutations_impl(window: MainWindow) -> dict[str, int]:
    _ensure_pending_state_loaded(window)
    sync_client = window._make_sync_client(window.settings)
    if sync_client is None:
        return {
            "remaining_add": len(window._pending_remote_add_ids),
            "remaining_remove": len(window._pending_remote_remove_ids),
        }

    budget = 12
    processed = 0

    now_ts = time.time()

    # Prioritize remote deletes first so removal intent converges quickly.
    for post_id in sorted(list(window._pending_remote_remove_ids)):
        if processed >= budget or window._degraded_mode_active():
            break
        meta = window._pending_remote_remove_meta.get(post_id, {})
        if float(meta.get("next_attempt_at", 0.0)) > now_ts:
            continue
        try:
            sync_client.remove_favorite(post_id)
            window._pending_remote_remove_ids.discard(post_id)
            window._pending_remote_remove_meta.pop(post_id, None)
            window._rate_limit.note_success()
            _note_endpoint_success(window, "remove")
            processed += 1
        except FlareSolverrError as exc:
            message = str(exc)
            window._mark_rate_limited_if_needed("pending_remote_remove", message)
            attempts = int(meta.get("attempts", 0)) + 1
            delay = _compute_backoff_seconds(window, "remove", attempts, message)
            meta.update(
                {
                    "attempts": attempts,
                    "next_attempt_at": time.time() + delay,
                    "last_error": message,
                    "first_queued_at": float(meta.get("first_queued_at", time.time())),
                }
            )
            window._pending_remote_remove_meta[post_id] = meta
            if is_rate_limited_error_message(message):
                break
            processed += 1

    for post_id in sorted(list(window._pending_remote_add_ids)):
        if window._pending_remote_remove_ids:
            # Keep this cycle focused on draining deletes first.
            break
        if processed >= budget or window._degraded_mode_active():
            break
        meta = window._pending_remote_add_meta.get(post_id, {})
        if float(meta.get("next_attempt_at", 0.0)) > now_ts:
            continue
        try:
            sync_client.add_favorite(post_id)
            window._pending_remote_add_ids.discard(post_id)
            window._pending_remote_add_meta.pop(post_id, None)
            window._rate_limit.note_success()
            _note_endpoint_success(window, "add")
            processed += 1
        except FlareSolverrError as exc:
            message = str(exc)
            window._mark_rate_limited_if_needed("pending_remote_add", message)
            attempts = int(meta.get("attempts", 0)) + 1
            delay = _compute_backoff_seconds(window, "add", attempts, message)
            meta.update(
                {
                    "attempts": attempts,
                    "next_attempt_at": time.time() + delay,
                    "last_error": message,
                    "first_queued_at": float(meta.get("first_queued_at", time.time())),
                }
            )
            window._pending_remote_add_meta[post_id] = meta
            if is_rate_limited_error_message(message):
                break
            processed += 1

    _save_pending_state(window)

    return {
        "remaining_add": len(window._pending_remote_add_ids),
        "remaining_remove": len(window._pending_remote_remove_ids),
    }


def pending_remote_mutations_finished(window: MainWindow, result: object) -> None:
    window._pending_sync_worker_active = False
    if not isinstance(result, dict):
        return
    remaining_add = int(result.get("remaining_add", 0))
    remaining_remove = int(result.get("remaining_remove", 0))
    oldest_age = 0
    now_ts = time.time()
    for meta in getattr(window, "_pending_remote_add_meta", {}).values():
        oldest_age = max(oldest_age, int(max(0.0, now_ts - float(meta.get("first_queued_at", now_ts)))))
    for meta in getattr(window, "_pending_remote_remove_meta", {}).values():
        oldest_age = max(oldest_age, int(max(0.0, now_ts - float(meta.get("first_queued_at", now_ts)))))
    if remaining_add or remaining_remove:
        window._set_right_status(
            f"Pending sync: {remaining_add} add, {remaining_remove} remove remaining (oldest {oldest_age}s)."
        )
    else:
        window._set_right_status("Pending sync complete.")


def pending_remote_mutations_failed(window: MainWindow, error_text: str) -> None:
    window._pending_sync_worker_active = False
    window._log_sync_debug("Pending sync worker failure", error_text)


def add_multiple_favorites(window: MainWindow, posts: list[Post]) -> None:
    unique_posts = {post.id: post for post in posts}
    if not unique_posts:
        return

    window._set_status(f"Adding {len(unique_posts)} favorites...")
    window._mutation_token += 1
    token = window._mutation_token

    worker = FunctionWorker(lambda: add_multiple_favorites_impl(window, list(unique_posts.values())))
    worker.signals.finished.connect(lambda result: favorite_bulk_add_finished(window, token, result))
    worker.signals.failed.connect(window._operation_failed)
    window._start_worker(worker, workload="mutation")


def add_multiple_favorites_impl(window: MainWindow, posts: list[Post]) -> dict[str, object]:
    added_ids: list[int] = []
    failed_ids: list[int] = []
    deferred_sync_ids: list[int] = []
    failed_errors: list[str] = []

    sync_client = window._make_sync_client(window.settings)
    for post in posts:
        if sync_client is not None:
            if window._degraded_mode_active():
                if not _wait_for_degraded_mode_window(window, max_wait_seconds=0.5):
                    deferred_sync_ids.append(post.id)
                    failed_errors.append(
                        f"#{post.id}: deferred remote add (degraded mode active: {window._degraded_mode_remaining()}s remaining)"
                    )
                    window.local_favorites.add_favorite(post)
                    added_ids.append(post.id)
                    _queue_pending_add(
                        window,
                        post.id,
                        f"degraded mode active: {window._degraded_mode_remaining()}s remaining",
                    )
                    continue

            attempts = 2
            remote_success = False
            last_error = ""
            for attempt in range(1, attempts + 1):
                try:
                    sync_client.add_favorite(post.id)
                    window._rate_limit.note_success()
                    _clear_pending_add(window, post.id)
                    _clear_pending_remove(window, post.id)
                    remote_success = True
                    break
                except FlareSolverrError as exc:
                    last_error = str(exc)
                    window._mark_rate_limited_if_needed("favorite_bulk_add", last_error)
                    # In bulk mode, immediate defer is better UX than repeatedly retrying a
                    # known rate-limited path for the same post.
                    if is_rate_limited_error_message(last_error):
                        break
                    break

            if not remote_success:
                if is_rate_limited_error_message(last_error):
                    deferred_sync_ids.append(post.id)
                    failed_errors.append(f"#{post.id}: deferred remote add ({last_error or 'rate limited'})")
                    window._log_sync_debug(
                        f"Bulk favorite add deferred for #{post.id}",
                        f"Reason: {last_error or 'rate limited'}\n\n{sync_client.debug_summary()}",
                    )
                    window.local_favorites.add_favorite(post)
                    _queue_pending_add(window, post.id, last_error or "rate limited")
                    added_ids.append(post.id)
                    continue

                failed_ids.append(post.id)
                failed_errors.append(f"#{post.id}: {last_error or 'unknown sync error'}")
                window._log_sync_debug(
                    f"Bulk favorite add sync failure for #{post.id}",
                    f"Error: {last_error or 'unknown sync error'}\n\n{sync_client.debug_summary()}",
                )
                continue

        window.local_favorites.add_favorite(post)
        _clear_pending_add(window, post.id)
        _clear_pending_remove(window, post.id)
        added_ids.append(post.id)

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
                f"Added {len(added_ids)} favorites locally; remote sync deferred for {len(deferred_sync_ids)} due to rate limits."
            )
        else:
            window._set_status(f"Added {len(added_ids)} favorites.")

    if window._sync_enabled() and failed_ids:
        window._refresh_favorites()
    else:
        window._refresh_local_favorites()


def remove_multiple_favorites(window: MainWindow, posts: list[Post]) -> None:
    unique_posts = {post.id: post for post in posts}
    if not unique_posts:
        return

    window._set_status(f"Removing {len(unique_posts)} favorites...")
    window._mutation_token += 1
    token = window._mutation_token

    worker = FunctionWorker(lambda: remove_multiple_favorites_impl(window, list(unique_posts.values())))
    worker.signals.finished.connect(lambda result: favorite_bulk_mutation_finished(window, token, result))
    worker.signals.failed.connect(window._operation_failed)
    window._start_worker(worker, workload="mutation")


def remove_multiple_favorites_impl(window: MainWindow, posts: list[Post]) -> dict[str, object]:
    removed_ids: list[int] = []
    failed_ids: list[int] = []
    deferred_sync_ids: list[int] = []
    failed_errors: list[str] = []

    sync_client = window._make_sync_client(window.settings)
    for post in posts:
        if sync_client is None:
            window.local_favorites.remove_favorite(post.id)
            removed_ids.append(post.id)
            continue

        if window._degraded_mode_active():
            if not _wait_for_degraded_mode_window(window, max_wait_seconds=0.5):
                deferred_sync_ids.append(post.id)
                failed_errors.append(
                    f"#{post.id}: deferred remote remove (degraded mode active: {window._degraded_mode_remaining()}s remaining)"
                )
                window.local_favorites.remove_favorite(post.id)
                _queue_pending_remove(
                    window,
                    post.id,
                    f"degraded mode active: {window._degraded_mode_remaining()}s remaining",
                )
                removed_ids.append(post.id)
                continue

        attempts = 2
        success = False
        last_error = ""
        for attempt in range(1, attempts + 1):
            try:
                sync_client.remove_favorite(post.id)
                window._rate_limit.note_success()
                _clear_pending_remove(window, post.id)
                _clear_pending_add(window, post.id)
                success = True
                break
            except FlareSolverrError as exc:
                last_error = str(exc)
                window._mark_rate_limited_if_needed("favorite_bulk_remove", last_error)
                # In bulk mode, immediately defer on rate limits to keep the batch responsive.
                if is_rate_limited_error_message(last_error):
                    break
                break

        if success:
            window.local_favorites.remove_favorite(post.id)
            _clear_pending_remove(window, post.id)
            _clear_pending_add(window, post.id)
            removed_ids.append(post.id)
            continue

        if is_rate_limited_error_message(last_error):
            deferred_sync_ids.append(post.id)
            failed_errors.append(f"#{post.id}: deferred remote remove ({last_error or 'rate limited'})")
            window._log_sync_debug(
                f"Bulk favorite remove deferred for #{post.id}",
                f"Reason: {last_error or 'rate limited'}\n\n{sync_client.debug_summary()}",
            )
            window.local_favorites.remove_favorite(post.id)
            _queue_pending_remove(window, post.id, last_error or "rate limited")
            removed_ids.append(post.id)
            continue

        failed_ids.append(post.id)
        failed_errors.append(f"#{post.id}: {last_error or 'unknown sync error'}")
        window._log_sync_debug(
            f"Bulk favorite remove sync failure for #{post.id}",
            f"Error: {last_error or 'unknown sync error'}\n\n{sync_client.debug_summary()}",
        )

    if failed_ids:
        window._last_favorite_sync_failed = True
        window._last_favorite_sync_error = f"Bulk remove failed for {len(failed_ids)} post(s)."
        window._last_favorite_sync_debug = "\n".join(failed_errors)
    else:
        window._last_favorite_sync_failed = False
        window._last_favorite_sync_error = ""
        window._last_favorite_sync_debug = ""

    return {
        "removed_ids": removed_ids,
        "failed_ids": failed_ids,
        "deferred_sync_ids": deferred_sync_ids,
        "failed_errors": failed_errors,
    }


def favorite_bulk_mutation_finished(window: MainWindow, token: int, result: object) -> None:
    if token != window._mutation_token:
        return
    if isinstance(result, dict):
        removed_ids = [int(item) for item in result.get("removed_ids", [])]
        failed_ids = [int(item) for item in result.get("failed_ids", [])]
        deferred_sync_ids = [int(item) for item in result.get("deferred_sync_ids", [])]
        failed_errors = [str(item) for item in result.get("failed_errors", [])]
    else:
        removed_ids = []
        failed_ids = []
        deferred_sync_ids = []
        failed_errors = []

    for post_id in removed_ids:
        window.favorite_ids.discard(post_id)

    if failed_ids:
        window._set_status(
            f"Removed {len(removed_ids)} favorites; {len(failed_ids)} failed and were kept."
        )
        QMessageBox.warning(
            window,
            "Bulk Remove Partial Failure",
            "Some favorites could not be removed remotely and were kept locally to avoid desync.\n\n"
            + "\n".join(failed_errors[:12]),
        )
    else:
        if deferred_sync_ids:
            window._set_status(
                f"Removed {len(removed_ids)} favorites locally; remote sync deferred for {len(deferred_sync_ids)} due to rate limits."
            )
        else:
            window._set_status(f"Removed {len(removed_ids)} favorites.")

    if window._sync_enabled() and failed_ids:
        window._refresh_favorites()
    else:
        window._refresh_local_favorites()


def assign_selection_to_new_collection(window: MainWindow, posts: list[Post]) -> None:
    text, accepted = QInputDialog.getText(window, "New collection", "Collection name")
    if not accepted:
        return
    assign_selection_to_collection(window, posts, text)


def assign_selection_to_collection(window: MainWindow, posts: list[Post], collection_name: str) -> None:
    post_ids = [post.id for post in posts]
    try:
        assigned = window.local_favorites.assign_posts_to_collection(post_ids, collection_name)
    except ValueError as exc:
        QMessageBox.warning(window, "Collections", str(exc))
        return
    window._refresh_collection_filter()
    window._set_status(f"Added {assigned} favorites to collection '{collection_name.strip()}'.")


def remove_selection_from_collection(window: MainWindow, posts: list[Post], collection_name: str) -> None:
    removed = window.local_favorites.remove_posts_from_collection([post.id for post in posts], collection_name)
    window._set_status(f"Removed {removed} favorites from '{collection_name}'.")
    window._refresh_local_favorites()


def add_favorite(window: MainWindow, post: Post) -> None:
    if window._sync_enabled():
        window._set_right_status(f"Adding #{post.id} to account favorites via FlareSolverr...")
    else:
        window._set_right_status(f"Adding #{post.id} to local favorites...")

    window._mutation_token += 1
    token = window._mutation_token

    worker = FunctionWorker(lambda: add_favorite_impl(window, post))
    worker.signals.finished.connect(lambda _: favorite_mutation_finished(window, token, post.id, True))
    worker.signals.failed.connect(window._operation_failed)
    window._start_worker(worker, workload="mutation")


def remove_favorite(window: MainWindow, post: Post) -> None:
    if window._sync_enabled():
        window._set_right_status(f"Removing #{post.id} from account favorites via FlareSolverr...")
    else:
        window._set_right_status(f"Removing #{post.id} from local favorites...")

    window._mutation_token += 1
    token = window._mutation_token

    worker = FunctionWorker(lambda: remove_favorite_impl(window, post))
    worker.signals.finished.connect(lambda _: favorite_mutation_finished(window, token, post.id, False))
    worker.signals.failed.connect(window._operation_failed)
    window._start_worker(worker, workload="mutation")


def add_favorite_impl(window: MainWindow, post: Post) -> int:
    window._last_favorite_sync_failed = False
    window._last_favorite_sync_error = ""
    window._last_favorite_sync_debug = ""
    sync_client = window._make_sync_client(window.settings)
    if sync_client is not None:
        if window._degraded_mode_active():
            window._last_favorite_sync_failed = True
            window._last_favorite_sync_error = (
                "Rate-limited degraded mode active; remote add skipped temporarily. "
                f"Retry in {window._degraded_mode_remaining()}s."
            )
            window._last_favorite_sync_debug = ""
        else:
            attempts = 3
            for attempt in range(1, attempts + 1):
                try:
                    sync_client.add_favorite(post.id)
                    window._last_favorite_sync_failed = False
                    window._last_favorite_sync_error = ""
                    window._last_favorite_sync_debug = ""
                    window._rate_limit.note_success()
                    break
                except FlareSolverrError as exc:
                    window._last_favorite_sync_failed = True
                    window._last_favorite_sync_error = str(exc)
                    window._last_favorite_sync_debug = sync_client.debug_summary()
                    window._mark_rate_limited_if_needed("favorite_add", window._last_favorite_sync_error)
                    if is_rate_limited_error_message(window._last_favorite_sync_error) and attempt < attempts:
                        time.sleep(0.35 * attempt)
                        continue
                    window._log_sync_debug(
                        f"Favorite add sync failure for #{post.id}",
                        f"Error: {window._last_favorite_sync_error}\n\n{window._last_favorite_sync_debug}",
                    )
                    break
    window.local_favorites.add_favorite(post)
    if window._last_favorite_sync_failed and is_rate_limited_error_message(window._last_favorite_sync_error):
        _queue_pending_add(window, post.id, window._last_favorite_sync_error)
    else:
        _clear_pending_add(window, post.id)
    _clear_pending_remove(window, post.id)
    return post.id


def remove_favorite_impl(window: MainWindow, post: Post) -> int:
    window._last_favorite_sync_failed = False
    window._last_favorite_sync_error = ""
    window._last_favorite_sync_debug = ""
    sync_client = window._make_sync_client(window.settings)
    if sync_client is not None:
        if window._degraded_mode_active():
            window._last_favorite_sync_failed = True
            window._last_favorite_sync_error = (
                "Rate-limited degraded mode active; remote remove skipped temporarily. "
                f"Retry in {window._degraded_mode_remaining()}s."
            )
            window._last_favorite_sync_debug = ""
        else:
            attempts = 3
            removed_remote = False
            for attempt in range(1, attempts + 1):
                try:
                    sync_client.remove_favorite(post.id)
                    window._last_favorite_sync_failed = False
                    window._last_favorite_sync_error = ""
                    window._last_favorite_sync_debug = ""
                    window._rate_limit.note_success()
                    removed_remote = True
                    break
                except FlareSolverrError as exc:
                    window._last_favorite_sync_failed = True
                    window._last_favorite_sync_error = str(exc)
                    window._last_favorite_sync_debug = sync_client.debug_summary()
                    window._mark_rate_limited_if_needed("favorite_remove", window._last_favorite_sync_error)
                    if is_rate_limited_error_message(window._last_favorite_sync_error) and attempt < attempts:
                        time.sleep(0.35 * attempt)
                        continue
                    window._log_sync_debug(
                        f"Favorite remove sync failure for #{post.id}",
                        f"Error: {window._last_favorite_sync_error}\n\n{window._last_favorite_sync_debug}",
                    )
                    break

            if not removed_remote:
                if is_rate_limited_error_message(window._last_favorite_sync_error):
                    window.local_favorites.remove_favorite(post.id)
                    _queue_pending_remove(window, post.id, window._last_favorite_sync_error)
                return post.id

    window.local_favorites.remove_favorite(post.id)
    _clear_pending_remove(window, post.id)
    _clear_pending_add(window, post.id)
    return post.id


def favorite_mutation_finished(window: MainWindow, token: int, post_id: int, favorited: bool) -> None:
    if token != window._mutation_token:
        return
    if favorited:
        window.favorite_ids.add(post_id)
    else:
        window.favorite_ids.discard(post_id)
    if window._last_favorite_sync_failed:
        if is_rate_limited_error_message(window._last_favorite_sync_error):
            window._set_status(
                f"Rate-limited while syncing #{post_id}; local state saved and automatic sync will retry later."
            )
            window._refresh_local_favorites()
            return
        window._set_status(
            f"Saved locally for #{post_id}; account sync unavailable. Debug log: {window._sync_debug_log_path}"
        )
        lines = [
            f"Account sync failed for post #{post_id}.",
            "",
            f"Error: {window._last_favorite_sync_error}",
            "",
            f"Debug log file: {window._sync_debug_log_path}",
        ]
        if window._last_favorite_sync_debug:
            lines.extend(["", "Last sync trace:", window._last_favorite_sync_debug])
        QMessageBox.warning(window, "Favorites Sync Warning", "\n".join(lines))
        window._refresh_local_favorites()
    elif window._sync_enabled():
        window._set_status(f"Favorite updated for post #{post_id}.")
        window._refresh_local_favorites()
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
