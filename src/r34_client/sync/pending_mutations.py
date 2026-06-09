from __future__ import annotations

import json
import logging
import random
import re
import time
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..ui.main_window import MainWindow


def pending_state_path(window: MainWindow):
    return window._sync_debug_log_path.parent / "pending-mutations.json"


def ensure_pending_state_loaded(window: MainWindow) -> None:
    with window._pending_state_lock:
        if window._pending_state_loaded:
            return

        window._pending_state_loaded = True
        path = pending_state_path(window)
        if not path.exists():
            return

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to parse pending mutations file '%s': %s", path, exc)
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


def save_pending_state(window: MainWindow) -> None:
    ensure_pending_state_loaded(window)
    path = pending_state_path(window)
    path.parent.mkdir(parents=True, exist_ok=True)

    with window._pending_state_lock:
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


def queue_pending_add(window: MainWindow, post_id: int, reason: str, *, persist: bool = True) -> None:
    ensure_pending_state_loaded(window)
    target = int(post_id)
    with window._pending_state_lock:
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
    
    if persist:
        save_pending_state(window)


def queue_pending_remove(window: MainWindow, post_id: int, reason: str, *, persist: bool = True) -> None:
    ensure_pending_state_loaded(window)
    target = int(post_id)
    with window._pending_state_lock:
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
    
    if persist:
        save_pending_state(window)


def clear_pending_add(window: MainWindow, post_id: int, *, persist: bool = True) -> None:
    ensure_pending_state_loaded(window)
    target = int(post_id)
    with window._pending_state_lock:
        window._pending_remote_add_ids.discard(target)
        window._pending_remote_add_meta.pop(target, None)
    
    if persist:
        save_pending_state(window)


def clear_pending_remove(window: MainWindow, post_id: int, *, persist: bool = True) -> None:
    ensure_pending_state_loaded(window)
    target = int(post_id)
    with window._pending_state_lock:
        window._pending_remote_remove_ids.discard(target)
        window._pending_remote_remove_meta.pop(target, None)
    
    if persist:
        save_pending_state(window)


def extract_retry_after_seconds(message: str) -> int | None:
    match = re.search(r"retry[-_ ]?after[^0-9]*(\d+)", message or "", flags=re.IGNORECASE)
    if not match:
        return None
    return max(0, int(match.group(1)))


def compute_backoff_seconds(window: MainWindow, endpoint: str, attempts: int, message: str) -> float:
    ensure_pending_state_loaded(window)
    retry_after = extract_retry_after_seconds(message)
    with window._pending_state_lock:
        streaks = window._pending_endpoint_streaks
        current_streak = int(streaks.get(endpoint, 0)) + 1
        streaks[endpoint] = current_streak

    base_delay = min(120.0, 1.25 * (2 ** min(current_streak, 6)))
    if retry_after is not None:
        base_delay = max(base_delay, float(retry_after))

    jitter = random.uniform(0.2, max(0.4, base_delay * 0.35))
    return base_delay + jitter


def note_endpoint_success(window: MainWindow, endpoint: str) -> None:
    ensure_pending_state_loaded(window)
    with window._pending_state_lock:
        window._pending_endpoint_streaks[endpoint] = 0
