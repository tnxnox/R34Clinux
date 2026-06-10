from __future__ import annotations

from datetime import datetime
import time
from typing import TYPE_CHECKING

from r34_client.core.rate_limit import is_rate_limited_error_message

if TYPE_CHECKING:
    from ..helpers.image_fit import FitMode
    from ..main_window import MainWindow


def update_action_state(window: MainWindow) -> None:
    has_selection = window._current_post() is not None
    has_query = bool(window.search_input.text().strip())
    window.download_button.setEnabled(has_selection)
    window.open_button.setEnabled(has_selection)
    window.copy_button.setEnabled(has_selection)
    window.volume_slider.setEnabled(window.video_player.is_available)
    window.seek_slider.setEnabled(window.video_player.is_available and has_selection and window._current_post_is_video())
    window.save_search_button.setEnabled(has_query)
    window.pin_filter_button.setEnabled(has_query)
    window.pin_filter_button.setText(
        "Unpin filter" if has_query and window.search_input.text().strip() in window._pinned_filters else "Pin filter"
    )


def set_left_status(window: MainWindow, message: str) -> None:
    window.left_status_label.setText(message)


def set_right_status(window: MainWindow, message: str) -> None:
    window.right_status_label.setText(message)


def set_status(window: MainWindow, message: str) -> None:
    set_left_status(window, message)


def set_fit_mode(window: MainWindow, mode: FitMode) -> None:
    from PySide6.QtCore import QTimer
    window._fit_mode = mode
    window._image_zoom_percent = 100
    window._update_preview_scaling()
    
    # Defer resetting the scrollbar values to 0 to ensure the QScrollArea layout has updated
    QTimer.singleShot(0, lambda: _reset_scrollbars_after_layout(window))
    
    set_status(window, f"Image fit mode: {mode.value}")


def _reset_scrollbars_after_layout(window: MainWindow) -> None:
    window.preview_container.horizontalScrollBar().setValue(0)
    window.preview_container.verticalScrollBar().setValue(0)


def cancel_current_operations(window: MainWindow) -> None:
    window._search_token += 1
    window._preview_token += 1
    window._favorites_token += 1
    window._autocomplete_token += 1
    window._mutation_token += 1
    window._download_token += 1
    window._hydrate_token += 1
    set_status(window, "Cancelled current operations.")


def mark_rate_limited_if_needed(window: MainWindow, context: str, error_message: str) -> None:
    if not is_rate_limited_error_message(error_message):
        return
    backoff = window._rate_limit.mark_rate_limited(time.monotonic())
    log_sync_debug(
        window,
        f"Rate limit degraded mode ({context})",
        f"Backoff seconds: {backoff}\nError: {error_message}",
    )


def degraded_mode_remaining(window: MainWindow) -> int:
    return window._rate_limit.remaining_seconds(time.monotonic())


def degraded_mode_active(window: MainWindow) -> bool:
    return degraded_mode_remaining(window) > 0


def log_sync_debug(window: MainWindow, title: str, details: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    window._sync_debug_log_path.parent.mkdir(parents=True, exist_ok=True)
    with window._sync_debug_log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {title}\n")
        handle.write((details or "(no details)").strip() + "\n\n")
