from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...windows.main_window import MainWindow


def record_search_history(window: MainWindow, query: str) -> None:
    normalized_query = query.strip()
    if not normalized_query:
        return

    history = [item for item in window._search_history if item != normalized_query]
    history.insert(0, normalized_query)
    window._search_history = history[: window._search_history_limit]
    window.store.save_search_history(window._search_history, window._search_history_limit)
    refresh_search_history(window)


def refresh_search_history(window: MainWindow) -> None:
    current_query = window.search_history_combo.currentData()
    window.search_history_combo.blockSignals(True)
    window.search_history_combo.clear()
    window.search_history_combo.addItem("Recent searches", None)
    for query in window._search_history:
        window.search_history_combo.addItem(query, query)
    if current_query is not None:
        index = window.search_history_combo.findData(current_query)
        if index >= 0:
            window.search_history_combo.setCurrentIndex(index)
    else:
        window.search_history_combo.setCurrentIndex(0)
    window.search_history_combo.blockSignals(False)


def on_search_history_activated(window: MainWindow, index: int) -> None:
    query = window.search_history_combo.itemData(index)
    normalized_query = str(query).strip() if query is not None else ""
    if not normalized_query:
        return

    from . import apply_search_query

    apply_search_query(window, normalized_query)
    window.search_history_combo.blockSignals(True)
    window.search_history_combo.setCurrentIndex(0)
    window.search_history_combo.blockSignals(False)


def save_current_search(window: MainWindow) -> None:
    normalized_query = window.search_input.text().strip()
    if not normalized_query:
        return

    queries = [item for item in window._saved_searches if item != normalized_query]
    queries.insert(0, normalized_query)
    window._saved_searches = queries[: window._saved_searches_limit]
    window.store.save_saved_searches(window._saved_searches, window._saved_searches_limit)
    refresh_saved_searches(window)
    window._update_action_state()


def refresh_saved_searches(window: MainWindow) -> None:
    current_query = window.saved_searches_combo.currentData()
    window.saved_searches_combo.blockSignals(True)
    window.saved_searches_combo.clear()
    window.saved_searches_combo.addItem("Saved searches", None)
    for query in window._saved_searches:
        window.saved_searches_combo.addItem(query, query)
    if current_query is not None:
        index = window.saved_searches_combo.findData(current_query)
        if index >= 0:
            window.saved_searches_combo.setCurrentIndex(index)
    else:
        window.saved_searches_combo.setCurrentIndex(0)
    window.saved_searches_combo.blockSignals(False)


def on_saved_search_activated(window: MainWindow, index: int) -> None:
    query = window.saved_searches_combo.itemData(index)
    normalized_query = str(query).strip() if query is not None else ""
    if not normalized_query:
        return

    from . import apply_search_query

    apply_search_query(window, normalized_query)
    window.saved_searches_combo.blockSignals(True)
    window.saved_searches_combo.setCurrentIndex(0)
    window.saved_searches_combo.blockSignals(False)


def toggle_pinned_filter(window: MainWindow) -> None:
    normalized_query = window.search_input.text().strip()
    if not normalized_query:
        return

    pinned = [item for item in window._pinned_filters if item != normalized_query]
    if len(pinned) == len(window._pinned_filters):
        pinned.insert(0, normalized_query)
    window._pinned_filters = pinned[: window._pinned_filters_limit]
    window.store.save_pinned_filters(window._pinned_filters, window._pinned_filters_limit)
    refresh_pinned_filters(window)
    window._update_action_state()


def refresh_pinned_filters(window: MainWindow) -> None:
    current_query = window.pinned_filters_combo.currentData()
    window.pinned_filters_combo.blockSignals(True)
    window.pinned_filters_combo.clear()
    window.pinned_filters_combo.addItem("Pinned filters", None)
    for query in window._pinned_filters:
        window.pinned_filters_combo.addItem(query, query)
    if current_query is not None:
        index = window.pinned_filters_combo.findData(current_query)
        if index >= 0:
            window.pinned_filters_combo.setCurrentIndex(index)
    else:
        window.pinned_filters_combo.setCurrentIndex(0)
    window.pinned_filters_combo.blockSignals(False)


def on_pinned_filter_activated(window: MainWindow, index: int) -> None:
    query = window.pinned_filters_combo.itemData(index)
    normalized_query = str(query).strip() if query is not None else ""
    if not normalized_query:
        return

    from . import apply_search_query

    apply_search_query(window, normalized_query)
    window.pinned_filters_combo.blockSignals(True)
    window.pinned_filters_combo.setCurrentIndex(0)
    window.pinned_filters_combo.blockSignals(False)
