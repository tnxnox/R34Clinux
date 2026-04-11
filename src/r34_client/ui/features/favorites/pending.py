from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING

from ....execution.concurrency import FunctionWorker
from ....clients.flaresolverr_favorites_client import FlareSolverrError
from ....core.rate_limit import is_rate_limited_error_message
from ...sync.pending_mutations import (
    compute_backoff_seconds,
    ensure_pending_state_loaded,
    note_endpoint_success,
    save_pending_state,
)

if TYPE_CHECKING:
    from ...windows.main_window import MainWindow


def restore_pending_remote_mutations(window: MainWindow) -> None:
    ensure_pending_state_loaded(window)


def process_pending_remote_mutations(window: MainWindow) -> None:
    ensure_pending_state_loaded(window)
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
    ensure_pending_state_loaded(window)
    sync_client = window._make_sync_client(window.settings)
    if sync_client is None:
        return {
            "remaining_add": len(window._pending_remote_add_ids),
            "remaining_remove": len(window._pending_remote_remove_ids),
        }

    budget = 12
    processed = 0
    token_exhausted = False

    now_ts = time.time()

    for post_id in sorted(list(window._pending_remote_remove_ids)):
        if processed >= budget or window._degraded_mode_active():
            break
        meta = window._pending_remote_remove_meta.get(post_id, {})
        if float(meta.get("next_attempt_at", 0.0)) > now_ts:
            continue
        if not window._remote_mutation_bucket.consume(1.0, time.monotonic()):
            token_exhausted = True
            break
        try:
            sync_client.remove_favorite(post_id)
            window._pending_remote_remove_ids.discard(post_id)
            window._pending_remote_remove_meta.pop(post_id, None)
            window._rate_limit.note_success()
            note_endpoint_success(window, "remove")
            processed += 1
        except FlareSolverrError as exc:
            message = str(exc)
            window._mark_rate_limited_if_needed("pending_remote_remove", message)
            attempts = int(meta.get("attempts", 0)) + 1
            delay = compute_backoff_seconds(window, "remove", attempts, message)
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
            break
        if processed >= budget or window._degraded_mode_active():
            break
        meta = window._pending_remote_add_meta.get(post_id, {})
        if float(meta.get("next_attempt_at", 0.0)) > now_ts:
            continue
        if not window._remote_mutation_bucket.consume(1.0, time.monotonic()):
            token_exhausted = True
            break
        try:
            sync_client.add_favorite(post_id)
            window._pending_remote_add_ids.discard(post_id)
            window._pending_remote_add_meta.pop(post_id, None)
            window._rate_limit.note_success()
            note_endpoint_success(window, "add")
            processed += 1
        except FlareSolverrError as exc:
            message = str(exc)
            window._mark_rate_limited_if_needed("pending_remote_add", message)
            attempts = int(meta.get("attempts", 0)) + 1
            delay = compute_backoff_seconds(window, "add", attempts, message)
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

    save_pending_state(window)

    return {
        "remaining_add": len(window._pending_remote_add_ids),
        "remaining_remove": len(window._pending_remote_remove_ids),
        "tokens_available": int(window._remote_mutation_bucket.available_tokens(time.monotonic())),
        "token_wait_seconds": math.ceil(window._remote_mutation_bucket.seconds_until_available(1.0, time.monotonic())),
        "token_exhausted": int(token_exhausted),
    }


def pending_remote_mutations_finished(window: MainWindow, result: object) -> None:
    window._pending_sync_worker_active = False
    if not isinstance(result, dict):
        return
    remaining_add = int(result.get("remaining_add", 0))
    remaining_remove = int(result.get("remaining_remove", 0))
    tokens_available = int(result.get("tokens_available", 0))
    token_wait_seconds = int(result.get("token_wait_seconds", 0))
    token_exhausted = bool(int(result.get("token_exhausted", 0)))
    oldest_age = 0
    now_ts = time.time()
    for meta in getattr(window, "_pending_remote_add_meta", {}).values():
        oldest_age = max(oldest_age, int(max(0.0, now_ts - float(meta.get("first_queued_at", now_ts)))))
    for meta in getattr(window, "_pending_remote_remove_meta", {}).values():
        oldest_age = max(oldest_age, int(max(0.0, now_ts - float(meta.get("first_queued_at", now_ts)))))
    if remaining_add or remaining_remove:
        if token_exhausted:
            window._set_right_status(
                f"Pending sync: {remaining_add} add, {remaining_remove} remove (oldest {oldest_age}s, throttled {token_wait_seconds}s)."
            )
        else:
            window._set_right_status(
                f"Pending sync: {remaining_add} add, {remaining_remove} remove remaining (oldest {oldest_age}s, tokens {tokens_available})."
            )
    else:
        window._set_right_status("Pending sync complete.")


def pending_remote_mutations_failed(window: MainWindow, error_text: str) -> None:
    window._pending_sync_worker_active = False
    window._log_sync_debug("Pending sync worker failure", error_text)
