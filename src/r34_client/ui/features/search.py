from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem

from ...concurrency import FunctionWorker
from ...models import Post
from ..favorites_sync import sync_remote_favorites

if TYPE_CHECKING:
    from ..main_window import MainWindow


def search(window: MainWindow) -> None:
    query = window.search_input.text().strip()
    window.current_query = query
    window.current_page = 0
    run_search(window)


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


def run_search(window: MainWindow) -> None:
    if not window.settings.has_credentials:
        window.open_settings(initial=True)
        return

    window.page_label.setText(f"Page {window.current_page + 1}")
    window.results_list.clear()
    window.preview_label.setText("Loading results...")
    window.meta_view.clear()
    window.current_posts = []
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
    )


def favorites_loaded(window: MainWindow, token: int, result: object) -> None:
    if token != window._favorites_token:
        return

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
