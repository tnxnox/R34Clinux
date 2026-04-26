from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING

from r34_client.core.worker import FunctionWorker
from r34_client.api.flaresolverr import FlareSolverrError
from r34_client.core.rate_limit import is_rate_limited_error_message
from r34_client.sync.pending_mutations import (
    compute_backoff_seconds,
    ensure_pending_state_loaded,
    note_endpoint_success,
    save_pending_state,
)

if TYPE_CHECKING:
    from ..main_window import MainWindow


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

    # Take a snapshot of current state to process in background
    pending_adds = set(window._pending_remote_add_ids)
    pending_removes = set(window._pending_remote_remove_ids)
    add_meta = dict(window._pending_remote_add_meta)
    remove_meta = dict(window._pending_remote_remove_meta)
    
    sync_client = window._make_sync_client(window.settings)
    is_degraded = window._degraded_mode_active()
    
    worker = FunctionWorker(
        process_pending_remote_mutations_impl,
        sync_client=sync_client,
        pending_adds=pending_adds,
        pending_removes=pending_removes,
        add_meta=add_meta,
        remove_meta=remove_meta,
        mutation_bucket=window._remote_mutation_bucket,
        is_degraded=is_degraded
    )
    worker.signals.finished.connect(lambda result: pending_remote_mutations_finished(window, result))
    worker.signals.failed.connect(lambda error_text: pending_remote_mutations_failed(window, error_text))
    window._start_worker(worker, workload="mutation")


def process_pending_remote_mutations_impl(
    sync_client,
    pending_adds: set[int],
    pending_removes: set[int],
    add_meta: dict[int, dict],
    remove_meta: dict[int, dict],
    mutation_bucket,
    is_degraded: bool
) -> dict[str, object]:
    if sync_client is None:
        return {
            "success_adds": [],
            "success_removes": [],
            "failed_adds": {},
            "failed_removes": {},
            "token_exhausted": False,
        }

    budget = 12
    processed = 0
    tokens_spent = 0
    token_exhausted = False
    
    success_adds = []
    success_removes = []
    failed_adds = {}
    failed_removes = {}

    now_ts = time.time()

    for post_id in sorted(list(pending_removes)):
        if processed >= budget or is_degraded:
            break
        meta = remove_meta.get(post_id, {})
        if float(meta.get("next_attempt_at", 0.0)) > now_ts:
            continue
        if not mutation_bucket.consume(1.0, time.monotonic()):
            token_exhausted = True
            break
        tokens_spent += 1
        try:
            sync_client.remove_favorite(post_id)
            success_removes.append(post_id)
            processed += 1
        except FlareSolverrError as exc:
            message = str(exc)
            failed_removes[post_id] = message
            if is_rate_limited_error_message(message):
                break
            processed += 1

    for post_id in sorted(list(pending_adds)):
        if pending_removes and post_id not in success_removes: # prioritize removes
             # actually we already have the set from window, so we just check if any removes are left
             pass
        
        if processed >= budget or is_degraded:
            break
        meta = add_meta.get(post_id, {})
        if float(meta.get("next_attempt_at", 0.0)) > now_ts:
            continue
        if not mutation_bucket.consume(1.0, time.monotonic()):
            token_exhausted = True
            break
        tokens_spent += 1
        try:
            sync_client.add_favorite(post_id)
            success_adds.append(post_id)
            processed += 1
        except FlareSolverrError as exc:
            message = str(exc)
            failed_adds[post_id] = message
            if is_rate_limited_error_message(message):
                break
            processed += 1

    return {
        "success_adds": success_adds,
        "success_removes": success_removes,
        "failed_adds": failed_adds,
        "failed_removes": failed_removes,
        "tokens_available": round(mutation_bucket.available_tokens(time.monotonic()), 1),
        "token_wait_seconds": math.ceil(mutation_bucket.seconds_until_available(1.0, time.monotonic())),
        "token_exhausted": token_exhausted,
        "tokens_spent": tokens_spent,
        "processed": processed,
    }


def pending_remote_mutations_finished(window: MainWindow, result: object) -> None:
    window._pending_sync_worker_active = False
    if not isinstance(result, dict):
        return

    success_adds = result.get("success_adds", [])
    success_removes = result.get("success_removes", [])
    failed_adds = result.get("failed_adds", {})
    failed_removes = result.get("failed_removes", {})
    
    # Process successes
    for post_id in success_adds:
        window._pending_remote_add_ids.discard(post_id)
        window._pending_remote_add_meta.pop(post_id, None)
        note_endpoint_success(window, "add")
    
    for post_id in success_removes:
        window._pending_remote_remove_ids.discard(post_id)
        window._pending_remote_remove_meta.pop(post_id, None)
        note_endpoint_success(window, "remove")

    if success_adds or success_removes:
        window._rate_limit.note_success()

    # Process failures
    for post_id, message in failed_adds.items():
        window._mark_rate_limited_if_needed("pending_remote_add", message)
        meta = window._pending_remote_add_meta.get(post_id, {})
        attempts = int(meta.get("attempts", 0)) + 1
        delay = compute_backoff_seconds(window, "add", attempts, message)
        meta.update({
            "attempts": attempts,
            "next_attempt_at": time.time() + delay,
            "last_error": message,
            "first_queued_at": float(meta.get("first_queued_at", time.time())),
        })
        window._pending_remote_add_meta[post_id] = meta

    for post_id, message in failed_removes.items():
        window._mark_rate_limited_if_needed("pending_remote_remove", message)
        meta = window._pending_remote_remove_meta.get(post_id, {})
        attempts = int(meta.get("attempts", 0)) + 1
        delay = compute_backoff_seconds(window, "remove", attempts, message)
        meta.update({
            "attempts": attempts,
            "next_attempt_at": time.time() + delay,
            "last_error": message,
            "first_queued_at": float(meta.get("first_queued_at", time.time())),
        })
        window._pending_remote_remove_meta[post_id] = meta

    save_pending_state(window)

    remaining_add = len(window._pending_remote_add_ids)
    remaining_remove = len(window._pending_remote_remove_ids)
    
    tokens_available = float(result.get("tokens_available", 0.0))
    token_wait_seconds = int(result.get("token_wait_seconds", 0))
    token_exhausted = bool(result.get("token_exhausted", False))
    tokens_spent = int(result.get("tokens_spent", 0))
    processed = int(result.get("processed", 0))
    
    if remaining_add or remaining_remove:
        window._set_right_status(
            f"Pending sync: {remaining_add} add, {remaining_remove} remove (processed {processed}, spent {tokens_spent}, tokens {tokens_available:.1f})."
        )
    else:
        window._set_right_status("Pending sync complete.")


def pending_remote_mutations_failed(window: MainWindow, error_text: str) -> None:
    window._pending_sync_worker_active = False
    window._log_sync_debug("Pending sync worker failure", error_text)
