from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem

from ...concurrency import FunctionWorker
from ...models import Post, TagSuggestion
from ..sync.favorites_sync import sync_remote_favorites

if TYPE_CHECKING:
    from ..windows.main_window import MainWindow


def search(window: MainWindow) -> None:
    query = window.search_input.text().strip()
    apply_search_query(window, query)


def next_page(window: MainWindow) -> None:
    if not window.current_query:
        return
    window.current_page += 1
    run_search(window)


def previous_page(window: MainWindow) -> None:
    if window.current_page <= 0 or not window.current_query:
        return
    window.current_page -= 1
    run_search(window)


def apply_search_query(window: MainWindow, query: str, *, record_history: bool = True) -> None:
    normalized_query = query.strip()
    if not normalized_query:
        return

    window.search_input.setText(normalized_query)
    window.current_query = normalized_query
    window.current_page = 0
    window._update_action_state()
    if record_history:
        record_search_history(window, normalized_query)
    run_search(window)


def run_search(window: MainWindow) -> None:
    if not window.settings.has_credentials:
        window.open_settings(initial=True)
        return

    window.page_label.setText(f"Page {window.current_page + 1}")
    window.results_list.clear()
    window.preview_label.setText("Loading results...")
    window.meta_view.clear()
    window.current_posts = []
    window._refresh_related_tags([])
    window._update_action_state()
    window._set_status("Searching...")

    window._search_token += 1
    token = window._search_token

    worker = FunctionWorker(
        lambda: window.client.search_posts(window.current_query, window.current_page, window.settings.page_size)
    )
    worker.signals.finished.connect(lambda result: search_finished(window, token, result))
    worker.signals.failed.connect(window._operation_failed)
    window._start_worker(worker)


def search_finished(window: MainWindow, token: int, result: object) -> None:
    if token != window._search_token:
        return
    posts = list(result) if isinstance(result, list) else []
    window.current_posts = posts
    window.results_list.clear()

    for post in posts:
        item = QListWidgetItem(window._format_post_tile(post))
        item.setData(Qt.ItemDataRole.UserRole, post)
        window.results_list.addItem(item)

    if posts:
        window.results_list.setCurrentRow(0)
        window._set_status(f"Loaded {len(posts)} posts.")
    else:
        window.preview_label.setText("No posts matched the search query.")
        window.meta_view.setPlainText("No results.")
        window._set_status("Search completed with no results.")

    update_related_tags(window, posts)
    window._update_action_state()


def refresh_favorites(window: MainWindow) -> None:
    refresh_favorites_impl(window, local_only=False)


def refresh_local_favorites(window: MainWindow) -> None:
    refresh_favorites_impl(window, local_only=True)


def refresh_favorites_impl(window: MainWindow, local_only: bool) -> None:
    window._favorites_token += 1
    token = window._favorites_token
    if window._sync_enabled() and not local_only:
        window._set_right_status("Syncing favorites via FlareSolverr...")
        worker = FunctionWorker(lambda: sync_remote(window))
    else:
        window._set_right_status("Refreshing local favorites...")
        worker = FunctionWorker(
            lambda: window.local_favorites.list_favorites(collection_name=window._selected_collection_name())
        )

    worker.signals.finished.connect(lambda result: favorites_loaded(window, token, result))
    worker.signals.failed.connect(lambda error_text: favorites_failed(window, token, error_text))
    window._start_worker(worker)


def sync_remote(window: MainWindow) -> tuple[list[Post], bool]:
    if window._degraded_mode_active():
        remaining = window._degraded_mode_remaining()
        window._log_sync_debug(
            "Favorites sync skipped (degraded mode)",
            f"Remaining cooldown seconds: {remaining}",
        )
        cached_posts = window.local_favorites.list_favorites()
        return (cached_posts, bool(cached_posts))

    return sync_remote_favorites(
        settings=window.settings,
        local_favorites=window.local_favorites,
        make_sync_client=window._make_sync_client,
        log_sync_debug=window._log_sync_debug,
        on_sync_error=lambda message: window._mark_rate_limited_if_needed("favorites_sync", message),
        pending_remote_add_ids=window._pending_remote_add_ids,
    )


def favorites_loaded(window: MainWindow, token: int, result: object) -> None:
    if token != window._favorites_token:
        return

    previous_current_id: int | None = None
    previous_current_item = window.favorites_list.currentItem()
    if previous_current_item is not None:
        previous_post = previous_current_item.data(Qt.ItemDataRole.UserRole)
        if isinstance(previous_post, Post):
            previous_current_id = previous_post.id

    loaded_posts: list[Post]
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], list):
        loaded_posts = result[0]
        window._favorites_sync_fallback_used = bool(result[1])
    elif isinstance(result, list):
        loaded_posts = result
        window._favorites_sync_fallback_used = False
    else:
        return

    selected_collection = window._selected_collection_name()
    if selected_collection is not None:
        loaded_posts = window.local_favorites.list_favorites(collection_name=selected_collection)

    window.favorite_posts = [item for item in loaded_posts if isinstance(item, Post)]
    window.favorite_ids = {post.id for post in window.favorite_posts}
    window._refresh_collection_filter()

    window.favorites_list.clear()
    for post in window.favorite_posts:
        item = QListWidgetItem(window._format_post_tile(post))
        item.setData(Qt.ItemDataRole.UserRole, post)
        window.favorites_list.addItem(item)

    should_restore_selection = (
        window.left_tabs.currentWidget() is window.favorites_list
        or previous_current_id is not None
    )

    if should_restore_selection and window.favorites_list.count() > 0:
        target_row = 0
        if previous_current_id is not None:
            for index, post in enumerate(window.favorite_posts):
                if post.id == previous_current_id:
                    target_row = index
                    break

        window.favorites_list.setCurrentRow(target_row)
        selected_item = window.favorites_list.item(target_row)
        if selected_item is not None:
            selected_item.setSelected(True)
            if window.left_tabs.currentWidget() is window.favorites_list:
                window._handle_selection_change(selected_item, None)

    if window._sync_enabled():
        if window._favorites_sync_fallback_used:
            if window._degraded_mode_active():
                window._set_status(
                    "Favorites sync temporarily degraded due to rate limiting; "
                    f"showing local cache ({len(window.favorite_posts)} posts)."
                )
            else:
                window._set_status(
                    f"Favorites sync returned empty data; showing local cache ({len(window.favorite_posts)} posts)."
                )
        else:
            window._rate_limit.note_success()
            window._set_right_status(f"Favorites synced ({len(window.favorite_posts)} posts).")
    else:
        window._set_right_status(f"Local favorites loaded ({len(window.favorite_posts)} posts).")
    window._update_action_state()


def favorites_failed(window: MainWindow, token: int, error_text: str) -> None:
    if token != window._favorites_token:
        return
    first_line = error_text.splitlines()[0] if error_text else "unknown error"
    window._log_sync_debug("Favorites refresh failure", error_text)
    if window._sync_enabled():
        window._set_right_status(f"Favorites sync failed: {first_line} (see {window._sync_debug_log_path})")
    else:
        window._set_right_status(f"Local favorites refresh failed: {first_line}")


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

    apply_search_query(window, normalized_query)
    window.pinned_filters_combo.blockSignals(True)
    window.pinned_filters_combo.setCurrentIndex(0)
    window.pinned_filters_combo.blockSignals(False)


def update_related_tags(window: MainWindow, posts: list[Post]) -> None:
    window.related_tags_list.blockSignals(True)
    window.related_tags_list.clear()

    suggestions = build_related_tags(posts, window.current_query, limit=12)
    for suggestion in suggestions:
        item = QListWidgetItem(f"{suggestion.value} ({suggestion.count or 1})")
        item.setData(Qt.ItemDataRole.UserRole, suggestion.value)
        window.related_tags_list.addItem(item)

    window.related_tags_list.blockSignals(False)
    window.related_tags_list.setEnabled(bool(suggestions))


def build_related_tags(posts: list[Post], query: str, limit: int = 12) -> list[TagSuggestion]:
    if not posts:
        return []

    excluded_tokens = {token.strip() for token in query.split() if token.strip()}
    tag_counts: Counter[str] = Counter()
    for post in posts:
        tag_counts.update(tag for tag in post.tags if tag not in excluded_tokens)

    suggestions: list[TagSuggestion] = []
    for tag, count in sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))[: max(0, int(limit))]:
        suggestions.append(TagSuggestion(value=tag, label=f"{tag} ({count})", count=count))
    return suggestions
