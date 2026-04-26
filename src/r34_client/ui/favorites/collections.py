from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QInputDialog, QMessageBox

from r34_client.core.worker import FunctionWorker
from r34_client.core.models import Post

if TYPE_CHECKING:
    from ..main_window import MainWindow


def assign_selection_to_new_collection(window: MainWindow, posts: list[Post]) -> None:
    text, accepted = QInputDialog.getText(window, "New collection", "Collection name")
    if not accepted:
        return
    assign_selection_to_collection(window, posts, text)


def assign_selection_to_collection(window: MainWindow, posts: list[Post], collection_name: str) -> None:
    post_ids = [post.id for post in posts]
    
    worker = FunctionWorker(window.local_favorites.assign_posts_to_collection, post_ids, collection_name)
    
    def on_finished(assigned: int) -> None:
        window._refresh_collection_filter()
        window._set_status(f"Added {assigned} favorites to collection '{collection_name.strip()}'.")
        
    def on_failed(error_text: str) -> None:
        QMessageBox.warning(window, "Collections", error_text)
        
    worker.signals.finished.connect(on_finished)
    worker.signals.failed.connect(on_failed)
    window._start_worker(worker, workload="mutation")


def remove_selection_from_collection(window: MainWindow, posts: list[Post], collection_name: str) -> None:
    post_ids = [post.id for post in posts]
    
    worker = FunctionWorker(window.local_favorites.remove_posts_from_collection, post_ids, collection_name)
    
    def on_finished(removed: int) -> None:
        window._set_status(f"Removed {removed} favorites from '{collection_name}'.")
        window._refresh_local_favorites()
        
    def on_failed(error_text: str) -> None:
        QMessageBox.warning(window, "Collections", error_text)

    worker.signals.finished.connect(on_finished)
    worker.signals.failed.connect(on_failed)
    window._start_worker(worker, workload="mutation")
