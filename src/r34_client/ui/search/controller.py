from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem

from r34_client.core.worker import FunctionWorker
from r34_client.core.models import Post, TagSuggestion
from r34_client.ui.search import history as history_feature
from r34_client.ui.search import related as related_feature
from r34_client.ui.favorites.pending import process_pending_remote_mutations
from r34_client.sync.favorites_sync import sync_remote_favorites

if TYPE_CHECKING:
    from r34_client.ui.main_window import MainWindow


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
        history_feature.record_search_history(window, normalized_query)
    run_search(window)


def run_search(window: MainWindow) -> None:
    if not window.settings.has_credentials:
        window.open_settings(initial=True)
        return

    window.page_label.setText(f"Page {window.current_page + 1}")
    window.results_list.clear()
    if window.left_tabs.currentWidget() is window.results_list:
        window.preview_label.setText("Loading results...")
        window.meta_view.clear()
    window.current_posts = []
    window._refresh_related_tags([])
    window._update_action_state()
    window._set_status("Searching...")

    window._search_token += 1
    token = window._search_token

    worker = FunctionWorker(
        window.client.search_posts, window.current_query, window.current_page, window.settings.page_size
    )
    worker.signals.finished.connect(lambda result: search_finished(window, token, result))
    worker.signals.failed.connect(window._operation_failed)
    window._start_worker(worker, workload="search")


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

    update_related_tags(window, posts)
    window._update_action_state()

    # Warm the cache BEFORE selecting the first row so the background
    # prefetch has a head start before show_post checks the cache.
    if posts:
        window._prefetch_images(posts)

    if posts:
        if window.left_tabs.currentWidget() is window.results_list:
            window.results_list.setCurrentRow(0)
        window._set_status(f"Loaded {len(posts)} posts.")
    else:
        window.preview_label.setText("No posts matched the search query.")
        window.meta_view.setPlainText("No results.")
        window._set_status("Search completed with no results.")


def refresh_favorites(window: MainWindow) -> None:
    refresh_favorites_impl(window, local_only=False)


def refresh_local_favorites(window: MainWindow) -> None:
    refresh_favorites_impl(window, local_only=True)


def refresh_favorites_impl(window: MainWindow, local_only: bool) -> None:
    window._favorites_token += 1
    token = window._favorites_token
    if window._sync_enabled() and not local_only:
        window._set_right_status("Syncing favorites via FlareSolverr...")
        worker = FunctionWorker(sync_remote, window)
    else:
        window._set_right_status("Refreshing local favorites...")
        worker = FunctionWorker(
            window.local_favorites.list_favorites, collection_name=window._selected_collection_name()
        )

    worker.signals.finished.connect(lambda result: favorites_loaded(window, token, result))
    worker.signals.failed.connect(lambda error_text: favorites_failed(window, token, error_text))
    window._start_worker(worker, workload="sync")


def sync_remote(window: MainWindow) -> tuple[list[Post], bool]:
    if window._degraded_mode_active():
        remaining = window._degraded_mode_remaining()
        window._log_sync_debug(
            "Favorites sync skipped (degraded mode)",
            f"Remaining cooldown seconds: {remaining}",
        )
        cached_posts = window.local_favorites.list_favorites()
        return (cached_posts, bool(cached_posts))

    # Snapshot pending sets under lock to avoid data races with main-thread mutations.
    with window._pending_state_lock:
        pending_add_snapshot = set(window._pending_remote_add_ids)
        pending_remove_snapshot = set(window._pending_remote_remove_ids)

    # Save originals before sync_remote_favorites mutates the snapshots.
    pending_add_before = set(pending_add_snapshot)

    result = sync_remote_favorites(
        settings=window.settings,
        local_favorites=window.local_favorites,
        make_sync_client=window._make_sync_client,
        log_sync_debug=window._log_sync_debug,
        on_sync_error=lambda message: window._mark_rate_limited_if_needed("favorites_sync", message),
        pending_remote_add_ids=pending_add_snapshot,
        pending_remote_remove_ids=pending_remove_snapshot,
    )

    # Only clear IDs from the live pending set that were confirmed on the remote.
    # sync_remote_favorites mutates the snapshot via pending_ids.difference_update(remote_ids),
    # removing IDs that exist on the remote. The remaining IDs in the snapshot
    # are local-only pending adds still waiting to be pushed remotely.
    confirmed_add_ids = pending_add_before - pending_add_snapshot
    with window._pending_state_lock:
        window._pending_remote_add_ids.difference_update(confirmed_add_ids)

    return result


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

    # Warm the cache BEFORE restoring the selection so the background
    # prefetch has a head start before show_post checks the cache.
    if window.favorite_posts:
        window._prefetch_images(window.favorite_posts)

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
        pending_add = len(window._pending_remote_add_ids)
        pending_remove = len(window._pending_remote_remove_ids)
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
            if pending_add or pending_remove:
                window._set_right_status(
                    f"Favorites loaded ({len(window.favorite_posts)} posts). Pending sync: {pending_add} add, {pending_remove} remove."
                )
                process_pending_remote_mutations(window)
            else:
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
    history_feature.record_search_history(window, query)


def refresh_search_history(window: MainWindow) -> None:
    history_feature.refresh_search_history(window)


def on_search_history_activated(window: MainWindow, index: int) -> None:
    history_feature.on_search_history_activated(window, index)


def save_current_search(window: MainWindow) -> None:
    history_feature.save_current_search(window)


def refresh_saved_searches(window: MainWindow) -> None:
    history_feature.refresh_saved_searches(window)


def on_saved_search_activated(window: MainWindow, index: int) -> None:
    history_feature.on_saved_search_activated(window, index)


def toggle_pinned_filter(window: MainWindow) -> None:
    history_feature.toggle_pinned_filter(window)


def refresh_pinned_filters(window: MainWindow) -> None:
    history_feature.refresh_pinned_filters(window)


def on_pinned_filter_activated(window: MainWindow, index: int) -> None:
    history_feature.on_pinned_filter_activated(window, index)


def update_related_tags(window: MainWindow, posts: list[Post]) -> None:
    related_feature.update_related_tags(window, posts)


def build_related_tags(posts: list[Post], query: str, limit: int = 12) -> list[TagSuggestion]:
    return related_feature.build_related_tags(posts, query, limit)
