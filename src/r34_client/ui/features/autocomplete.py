from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QStandardItem

from ...execution.concurrency import FunctionWorker
from ...core.models import TagSuggestion

if TYPE_CHECKING:
    from ..windows.main_window import MainWindow


def schedule_autocomplete(window: MainWindow, *_: object) -> None:
    window.autocomplete_timer.start()


def current_token_context(window: MainWindow) -> tuple[int, int, str]:
    text = window.search_input.text()
    cursor = window.search_input.cursorPosition()
    start = cursor
    while start > 0 and not text[start - 1].isspace():
        start -= 1

    end = cursor
    while end < len(text) and not text[end].isspace():
        end += 1

    return (start, end, text[start:cursor])


def refresh_autocomplete(window: MainWindow) -> None:
    start, end, prefix = current_token_context(window)
    window._autocomplete_token_start = start
    window._autocomplete_token_end = end
    window._autocomplete_query_snapshot = window.search_input.text()

    if len(prefix) < 2:
        window.completer_model.clear()
        window.completer.popup().hide()
        return

    cached = cached_suggestions(window, prefix)
    if cached:
        apply_autocomplete(window, prefix, cached)

    if prefix == window._last_autocomplete_prefix:
        return

    window._last_autocomplete_prefix = prefix

    window._autocomplete_token += 1
    token = window._autocomplete_token

    worker = FunctionWorker(lambda: window.client.autocomplete_tags(prefix))
    worker.signals.finished.connect(lambda result: autocomplete_finished(window, token, prefix, result))
    worker.signals.failed.connect(lambda error_text: autocomplete_failed(window, token, error_text))
    window._start_worker(worker, workload="autocomplete")


def autocomplete_finished(window: MainWindow, token: int, prefix: str, result: object) -> None:
    if token != window._autocomplete_token or not isinstance(result, list):
        return

    suggestions = [item for item in result if isinstance(item, TagSuggestion)]
    window._autocomplete_cache[prefix] = suggestions
    apply_autocomplete(window, prefix, suggestions)


def autocomplete_failed(window: MainWindow, token: int, error_text: str) -> None:
    if token != window._autocomplete_token:
        return
    window._set_status(f"Autocomplete unavailable: {error_text.splitlines()[0]}")


def cached_suggestions(window: MainWindow, prefix: str) -> list[TagSuggestion]:
    if prefix in window._autocomplete_cache:
        return window._autocomplete_cache[prefix]

    matching_prefixes = [key for key in window._autocomplete_cache if prefix.startswith(key)]
    if not matching_prefixes:
        return []

    nearest_prefix = max(matching_prefixes, key=len)
    return [item for item in window._autocomplete_cache[nearest_prefix] if item.value.startswith(prefix)]


def apply_autocomplete(window: MainWindow, prefix: str, suggestions: list[TagSuggestion]) -> None:
    start, end, active_prefix = current_token_context(window)
    if active_prefix != prefix:
        return

    window._autocomplete_token_start = start
    window._autocomplete_token_end = end
    window._autocomplete_query_snapshot = window.search_input.text()

    window.completer_model.clear()
    for suggestion in suggestions:
        item = QStandardItem(suggestion.display_text)
        item.setData(suggestion.value, Qt.ItemDataRole.UserRole)
        window.completer_model.appendRow(item)

    if window.completer_model.rowCount() <= 0:
        window.completer.popup().hide()
        return

    window.completer.setCompletionPrefix(prefix)
    window.completer.complete()


def insert_completion(window: MainWindow, completion: str) -> None:
    value = completion.strip()
    if not value:
        return

    snapshot = window._autocomplete_query_snapshot or window.search_input.text()
    start = window._autocomplete_token_start
    end = window._autocomplete_token_end
    QTimer.singleShot(0, lambda: apply_completion_to_token(window, value, snapshot, start, end))


def apply_completion_to_token(window: MainWindow, value: str, snapshot: str, start: int, end: int) -> None:
    text = snapshot
    if start < 0 or end < start or end > len(text):
        live_text = window.search_input.text()
        start, end, _ = current_token_context(window)
        text = live_text
        if start < 0 or end < start or end > len(text):
            return

    new_text = f"{text[:start]}{value}{text[end:]}"
    cursor_pos = start + len(value)

    if cursor_pos >= len(new_text):
        new_text = f"{new_text} "
        cursor_pos = len(new_text)

    window.search_input.setText(new_text)
    window.search_input.setCursorPosition(cursor_pos)
    window.completer.popup().hide()
    schedule_autocomplete(window)
