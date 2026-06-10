from __future__ import annotations

from typing import TYPE_CHECKING

from r34_client.api.hydration import hydrate_posts, hydrate_posts_copy
from r34_client.api.scraping import fetch_friend_favorites
from r34_client.core.models import Post
from r34_client.core.worker import FunctionWorker

if TYPE_CHECKING:
    from ..main_window import MainWindow


def _fetch_friend_favorites_impl(client, user_id: str, solver_url: str, page: int = 0) -> list[Post]:
    posts = fetch_friend_favorites(client, user_id, solver_url, page)
    # Hydrate only the slice needed for the requested UI page
    start_idx = (page % 5) * 10
    hydrate_posts(client, posts, start=start_idx, limit=10)
    return posts


def _hydrate_cached_slice_impl(client, posts: list[Post], page: int) -> list[Post]:
    start_idx = (page % 5) * 10
    return hydrate_posts_copy(client, posts, start=start_idx, limit=10)


def add_friend_dialog(window: MainWindow) -> None:
    from PySide6.QtWidgets import QDialog, QLineEdit, QVBoxLayout, QFormLayout, QDialogButtonBox

    dialog = QDialog(window)
    dialog.setWindowTitle("Add Friend")
    dialog.setModal(True)

    user_id_input = QLineEdit()
    user_id_input.setPlaceholderText("R34 user ID (number)")

    name_input = QLineEdit()
    name_input.setPlaceholderText("Display name")

    notes_input = QLineEdit()
    notes_input.setPlaceholderText("Optional notes")

    layout = QVBoxLayout(dialog)
    form = QFormLayout()
    form.addRow("User ID:", user_id_input)
    form.addRow("Name:", name_input)
    form.addRow("Notes:", notes_input)
    layout.addLayout(form)

    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    if dialog.exec() != QDialog.Accepted:
        return

    user_id = user_id_input.text().strip()
    display_name = name_input.text().strip() or user_id
    notes = notes_input.text().strip()

    if not user_id:
        return

    window.local_favorites.add_friend(user_id, display_name, notes)
    _refresh_friends_list(window)


def remove_friend_dialog(window: MainWindow) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox

    item = window.friends_list.currentItem()
    if item is None:
        return
    friend = item.data(Qt.ItemDataRole.UserRole)
    if friend is None:
        return

    confirm = QMessageBox.question(
        window,
        "Remove Friend",
        f"Remove '{friend['display_name']}' (ID: {friend['user_id']}) from your friends?",
        QMessageBox.Yes | QMessageBox.No,
    )
    if confirm != QMessageBox.Yes:
        return

    window.local_favorites.remove_friend(str(friend["user_id"]))
    window.friend_posts_list.clear()
    window.friend_posts = []
    _refresh_friends_list(window)


def _refresh_friends_list(window: MainWindow) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QListWidgetItem

    window.friends_list.clear()
    friends = window.local_favorites.list_friends()
    for friend in friends:
        text = f"{friend['display_name']}  (ID: {friend['user_id']})"
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, friend)
        window.friends_list.addItem(item)


def load_friend_favorites(window: MainWindow, item: object = None) -> None:
    from PySide6.QtCore import Qt

    if item is None:
        item = window.friends_list.currentItem()
    if item is None:
        return
    friend = item.data(Qt.ItemDataRole.UserRole)
    if friend is None:
        return

    user_id = str(friend["user_id"])
    solver_url = window.settings.flaresolverr_url if window.settings.flaresolverr_enabled else ""

    window._friend_current_page = 0
    window._friend_user_id = user_id
    window._friend_cached_api_page = -1
    window._friend_cached_posts = []
    _fetch_friend_page(window, user_id, solver_url, page=0)


def _fetch_friend_page(window: MainWindow, user_id: str, solver_url: str, page: int) -> None:
    window._friend_fetch_token += 1
    token = window._friend_fetch_token

    window.friend_posts_list.clear()
    window.friend_posts = []

    api_page = page // 5
    start_idx = (page % 5) * 10
    end_idx = start_idx + 10

    if window._friend_cached_api_page == api_page and window._friend_cached_posts:
        slice_posts = window._friend_cached_posts[start_idx:end_idx]
        needs_hydration = any(not p.file_url for p in slice_posts) if slice_posts else False

        if not needs_hydration:
            _friend_favorites_fetched(window, token, window._friend_cached_posts)
            return

        window._set_status(f"Hydrating favorites for user {user_id} (page {page + 1})...")
        worker = FunctionWorker(_hydrate_cached_slice_impl, window.client, window._friend_cached_posts, page)
        worker.signals.finished.connect(lambda result: _friend_favorites_fetched(window, token, result))
        worker.signals.failed.connect(window._operation_failed)
        window._start_worker(worker, workload="general")
        return

    window._set_status(f"Loading favorites for user {user_id} (page {page + 1})...")
    worker = FunctionWorker(_fetch_friend_favorites_impl, window.client, user_id, solver_url, page)
    worker.signals.finished.connect(lambda result: _friend_favorites_fetched(window, token, result))
    worker.signals.failed.connect(window._operation_failed)
    window._start_worker(worker, workload="general")


def next_friend_page(window: MainWindow) -> None:
    if not window._friend_user_id:
        return
    window._friend_current_page += 1
    solver_url = window.settings.flaresolverr_url if window.settings.flaresolverr_enabled else ""
    _fetch_friend_page(
        window,
        window._friend_user_id,
        solver_url,
        window._friend_current_page,
    )


def prev_friend_page(window: MainWindow) -> None:
    if not window._friend_user_id or window._friend_current_page <= 0:
        return
    window._friend_current_page -= 1
    solver_url = window.settings.flaresolverr_url if window.settings.flaresolverr_enabled else ""
    _fetch_friend_page(
        window,
        window._friend_user_id,
        solver_url,
        window._friend_current_page,
    )


def _friend_favorites_fetched(window: MainWindow, token: int, result: object) -> None:
    if token != window._friend_fetch_token:
        return

    if not isinstance(result, list):
        window._set_status("Failed to parse friend favorites")
        return

    posts: list[Post] = []
    for obj in result:
        if isinstance(obj, Post):
            posts.append(obj)

    window._friend_cached_posts = posts
    window._friend_cached_api_page = window._friend_current_page // 5

    page = window._friend_current_page
    start_idx = (page % 5) * 10
    end_idx = start_idx + 10
    displayed = posts[start_idx:end_idx]

    has_more = False
    if len(posts) > end_idx:
        has_more = True
    elif len(posts) >= 50:
        has_more = True

    window._friend_has_more = has_more
    window.friend_posts = displayed
    window._set_status(f"Loaded page {page + 1} of friend's favorites ({len(posts)} posts in cache).")

    # Trigger background pre-hydration for the rest of the 50-post API page
    _trigger_background_prehydration(window, token)


def _trigger_background_prehydration(window: MainWindow, token: int) -> None:
    posts = window._friend_cached_posts
    unhydrated_indices = [i for i, p in enumerate(posts) if not p.file_url]
    if not unhydrated_indices:
        return

    worker = FunctionWorker(_prehydrate_remaining_impl, window.client, posts)
    worker.signals.finished.connect(lambda result: _friend_prehydrate_finished(window, token, result))
    window._start_worker(worker, workload="general")


def _prehydrate_remaining_impl(client, posts: list[Post]) -> list[Post]:
    return hydrate_posts_copy(client, posts)


def _friend_prehydrate_finished(window: MainWindow, token: int, result: object) -> None:
    if token != window._friend_fetch_token:
        return
    if not isinstance(result, list):
        return
    posts: list[Post] = []
    for obj in result:
        if isinstance(obj, Post):
            posts.append(obj)
    window._friend_cached_posts = posts
