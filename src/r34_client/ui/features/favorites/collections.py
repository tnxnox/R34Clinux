from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QInputDialog, QMessageBox

from ....core.models import Post

if TYPE_CHECKING:
    from ...windows.main_window import MainWindow


def assign_selection_to_new_collection(window: MainWindow, posts: list[Post]) -> None:
    text, accepted = QInputDialog.getText(window, "New collection", "Collection name")
    if not accepted:
        return
    assign_selection_to_collection(window, posts, text)


def assign_selection_to_collection(window: MainWindow, posts: list[Post], collection_name: str) -> None:
    post_ids = [post.id for post in posts]
    try:
        assigned = window.local_favorites.assign_posts_to_collection(post_ids, collection_name)
    except ValueError as exc:
        QMessageBox.warning(window, "Collections", str(exc))
        return
    window._refresh_collection_filter()
    window._set_status(f"Added {assigned} favorites to collection '{collection_name.strip()}'.")


def remove_selection_from_collection(window: MainWindow, posts: list[Post], collection_name: str) -> None:
    removed = window.local_favorites.remove_posts_from_collection([post.id for post in posts], collection_name)
    window._set_status(f"Removed {removed} favorites from '{collection_name}'.")
    window._refresh_local_favorites()
