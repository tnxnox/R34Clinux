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

PENDING_WORKER_WATCHDOG_SECONDS = 180.0
PENDING_WORKER_RESTART_THROTTLE_SECONDS = 45.0
PENDING_MUTATION_BUDGET = 6
PENDING_WORKER_MAX_RUN_SECONDS = 35.0

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
    now_ts = time.monotonic()
    if window._pending_sync_worker_active:
        active_for = now_ts - float(getattr(window, "_pending_sync_started_at", 0.0))
        if active_for < PENDING_WORKER_WATCHDOG_SECONDS:
            return
        last_restart = float(getattr(window, "_pending_sync_last_restart_at", 0.0))
        if now_ts - last_restart < PENDING_WORKER_RESTART_THROTTLE_SECONDS:
            window._set_right_status(
                "Pending sync worker is taking longer than expected; waiting for recovery window."
            )
            return

        window._pending_sync_last_restart_at = now_ts
        window._pending_sync_worker_active = False
        window._pending_sync_started_at = 0.0
        window._log_sync_debug(
            "Pending sync watchdog restart",
            f"Pending worker active for {active_for:.1f}s exceeded watchdog="
            f"{int(PENDING_WORKER_WATCHDOG_SECONDS)}s; scheduling replacement "
            f"(throttle={int(PENDING_WORKER_RESTART_THROTTLE_SECONDS)}s).",
        )

    window._pending_sync_worker_active = True
    window._pending_sync_started_at = now_ts
    with window._pending_state_lock:
        queued_add = len(window._pending_remote_add_ids)
        queued_remove = len(window._pending_remote_remove_ids)
    window._log_sync_debug(
        "Pending sync worker start",
        f"queued_add={queued_add} queued_remove={queued_remove} degraded={int(window._degraded_mode_active())}",
    )

    worker = FunctionWorker(lambda: process_pending_remote_mutations_impl(window))
    worker.signals.finished.connect(lambda result: pending_remote_mutations_finished(window, result))
    worker.signals.failed.connect(lambda error_text: pending_remote_mutations_failed(window, error_text))
    # Keep remote sync work off the single-thread mutation pool so local favorite
    # add/remove operations can complete immediately even if FlareSolverr stalls.
    window._start_worker(worker, workload="sync")


def process_pending_remote_mutations_impl(window: MainWindow) -> dict[str, int | float]:
    ensure_pending_state_loaded(window)

    # Snapshot shared state under lock to avoid races with main-thread mutations.
    with window._pending_state_lock:
        remove_ids = sorted(window._pending_remote_remove_ids)
        remove_meta = dict(window._pending_remote_remove_meta)
        add_ids = sorted(window._pending_remote_add_ids)
        add_meta = dict(window._pending_remote_add_meta)

    sync_client = window._make_sync_client(window.settings)
    if sync_client is None:
        return {
            "remaining_add": len(add_ids),
            "remaining_remove": len(remove_ids),
            "processed": 0,
            "tokens_spent": 0,
            "token_exhausted": 0,
            "tokens_available": round(window._remote_mutation_bucket.available_tokens(time.monotonic()), 1),
            "token_wait_seconds": math.ceil(window._remote_mutation_bucket.seconds_until_available(1.0, time.monotonic())),
        }

    budget = 12
    processed = 0
    tokens_spent = 0
    token_exhausted = False
    now_ts = time.time()

    for post_id in remove_ids:
        if processed >= budget or window._degraded_mode_active():
            break
        meta = remove_meta.get(post_id, {})
        if float(meta.get("next_attempt_at", 0.0)) > now_ts:
            continue
        if not window._remote_mutation_bucket.consume(1.0, time.monotonic()):
            token_exhausted = True
            break
        tokens_spent += 1
        try:
            sync_client.remove_favorite(post_id)
            with window._pending_state_lock:
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
            updated_meta = dict(meta, **{
                "attempts": attempts,
                "next_attempt_at": time.time() + delay,
                "last_error": message,
                "first_queued_at": float(meta.get("first_queued_at", time.time())),
            })
            with window._pending_state_lock:
                window._pending_remote_remove_meta[post_id] = updated_meta
            if is_rate_limited_error_message(message):
                break
            processed += 1

    for post_id in add_ids:
        if processed >= budget or window._degraded_mode_active():
            break
        meta = add_meta.get(post_id, {})
        if float(meta.get("next_attempt_at", 0.0)) > now_ts:
            continue
        if not window._remote_mutation_bucket.consume(1.0, time.monotonic()):
            token_exhausted = True
            break
        tokens_spent += 1
        try:
            sync_client.add_favorite(post_id)
            with window._pending_state_lock:
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
            updated_meta = dict(meta, **{
                "attempts": attempts,
                "next_attempt_at": time.time() + delay,
                "last_error": message,
                "first_queued_at": float(meta.get("first_queued_at", time.time())),
            })
            with window._pending_state_lock:
                window._pending_remote_add_meta[post_id] = updated_meta
            if is_rate_limited_error_message(message):
                break
            processed += 1

    save_pending_state(window)

    with window._pending_state_lock:
        remaining_add = len(window._pending_remote_add_ids)
        remaining_remove = len(window._pending_remote_remove_ids)

    return {
        "remaining_add": remaining_add,
        "remaining_remove": remaining_remove,
        "tokens_available": round(window._remote_mutation_bucket.available_tokens(time.monotonic()), 1),
        "token_wait_seconds": math.ceil(window._remote_mutation_bucket.seconds_until_available(1.0, time.monotonic())),
        "token_exhausted": int(token_exhausted),
        "tokens_spent": tokens_spent,
        "processed": processed,
    }


def pending_remote_mutations_finished(window: MainWindow, result: object) -> None:
    window._pending_sync_worker_active = False
    window._pending_sync_started_at = 0.0
    if not isinstance(result, dict):
        return

    remaining_add = len(window._pending_remote_add_ids)
    remaining_remove = len(window._pending_remote_remove_ids)
    
    tokens_available = float(result.get("tokens_available", 0.0))
    token_wait_seconds = int(result.get("token_wait_seconds", 0))
    token_exhausted = bool(int(result.get("token_exhausted", 0)))
    tokens_spent = int(result.get("tokens_spent", 0))
    processed = int(result.get("processed", 0))

    window._log_sync_debug(
        "Pending sync worker finished",
        f"processed={processed} token_exhausted={int(token_exhausted)} token_wait={token_wait_seconds}s "
        f"remaining_add={remaining_add} remaining_remove={remaining_remove} "
        f"tokens={tokens_available:.1f} spent={tokens_spent}",
    )
    
    if remaining_add or remaining_remove:
        window._set_right_status(
            f"Pending sync: {remaining_add} add, {remaining_remove} remove (processed {processed}, spent {tokens_spent}, tokens {tokens_available:.1f})."
        )
    else:
        window._set_right_status("Pending sync complete.")


def pending_remote_mutations_failed(window: MainWindow, error_text: str) -> None:
    window._pending_sync_worker_active = False
    window._pending_sync_started_at = 0.0
    window._log_sync_debug("Pending sync worker failure", error_text)
    first_line = error_text.splitlines()[0] if error_text else "unknown error"
    window._set_right_status(f"Pending remote sync failed: {first_line}")
