from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu

from ...models import Post

if TYPE_CHECKING:
    from ..windows.main_window import MainWindow


def selected_results_posts(window: MainWindow) -> list[Post]:
    posts: list[Post] = []
    for item in window.results_list.selectedItems():
        post = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(post, Post):
            posts.append(post)
    if posts:
        return posts
    current = window._current_post()
    return [current] if current is not None else []


def selected_favorite_posts(window: MainWindow) -> list[Post]:
    posts: list[Post] = []
    for item in window.favorites_list.selectedItems():
        post = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(post, Post):
            posts.append(post)
    if posts:
        return posts
    current = window._current_post()
    return [current] if current is not None else []


def open_results_context_menu(window: MainWindow, position) -> None:
    item = window.results_list.itemAt(position)
    if item is None:
        return

    if item not in window.results_list.selectedItems():
        window.results_list.setCurrentItem(item)
        item.setSelected(True)

    selected_posts = selected_results_posts(window)
    if not selected_posts:
        return

    menu = QMenu(window)

    selected_not_favorited = [post for post in selected_posts if post.id not in window.favorite_ids]
    selected_favorited = [post for post in selected_posts if post.id in window.favorite_ids]

    if len(selected_posts) > 1:
        if selected_not_favorited:
            add_action = menu.addAction(f"Add {len(selected_not_favorited)} selected to favorites")
            add_action.triggered.connect(lambda: window._add_multiple_favorites(selected_not_favorited))
        if selected_favorited:
            remove_action = menu.addAction(f"Remove {len(selected_favorited)} selected from favorites")
            remove_action.triggered.connect(lambda: window._remove_multiple_favorites(selected_favorited))
    else:
        post = selected_posts[0]
        if post.id in window.favorite_ids:
            action = menu.addAction("Remove from favorites")
            action.triggered.connect(lambda: window._remove_favorite(post))
        else:
            action = menu.addAction("Add to favorites")
            action.triggered.connect(lambda: window._add_favorite(post))

    menu.exec(window.results_list.viewport().mapToGlobal(position))


def open_favorites_context_menu(window: MainWindow, position) -> None:
    item = window.favorites_list.itemAt(position)
    if item is None:
        return

    if item not in window.favorites_list.selectedItems():
        window.favorites_list.setCurrentItem(item)
        item.setSelected(True)

    selected_posts = selected_favorite_posts(window)
    if not selected_posts:
        return

    menu = QMenu(window)

    if len(selected_posts) > 1:
        remove_action = menu.addAction(f"Remove {len(selected_posts)} selected from favorites")
        remove_action.triggered.connect(lambda: window._remove_multiple_favorites(selected_posts))

        download_action = menu.addAction(f"Download {len(selected_posts)} selected")
        download_action.triggered.connect(lambda: window._download_multiple_posts(selected_posts))

        open_action = menu.addAction(f"Open {len(selected_posts)} selected in browser")
        open_action.triggered.connect(lambda: window._open_multiple_posts(selected_posts))
    else:
        remove_action = menu.addAction("Remove from favorites")
        remove_action.triggered.connect(lambda: window._remove_favorite(selected_posts[0]))

    menu.addSeparator()
    assign_submenu = menu.addMenu("Add selected to collection")
    new_collection_action = assign_submenu.addAction("New collection...")
    new_collection_action.triggered.connect(lambda: window._assign_selection_to_new_collection(selected_posts))

    for collection in window.local_favorites.list_collections():
        action = assign_submenu.addAction(collection)
        action.triggered.connect(lambda _checked=False, c=collection: window._assign_selection_to_collection(selected_posts, c))

    current_collection = window._selected_collection_name()
    if current_collection:
        remove_collection_action = menu.addAction(f"Remove selected from '{current_collection}'")
        remove_collection_action.triggered.connect(
            lambda: window._remove_selection_from_collection(selected_posts, current_collection)
        )

    menu.exec(window.favorites_list.viewport().mapToGlobal(position))
