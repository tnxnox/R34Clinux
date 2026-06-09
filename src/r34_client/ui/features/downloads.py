from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog

from r34_client.core.worker import FunctionWorker
from r34_client.ui.helpers.post import download_url_needs_hydration

if TYPE_CHECKING:
    from ...core.models import Post
    from ..main_window import MainWindow


def open_selected_post(window: MainWindow) -> None:
    post = window._current_post()
    if post is None:
        return
    QDesktopServices.openUrl(QUrl(post.page_url))


def open_multiple_posts(window: MainWindow, posts: list[Post]) -> None:
    unique_posts = {post.id: post for post in posts}
    if not unique_posts:
        return
    for post in unique_posts.values():
        QDesktopServices.openUrl(QUrl(post.page_url))
    window._set_status(f"Opened {len(unique_posts)} posts in browser.")


def copy_selected_link(window: MainWindow) -> None:
    post = window._current_post()
    if post is None:
        return
    QApplication.clipboard().setText(post.page_url)
    window._set_status("Post link copied to clipboard.")


def download_selected_post(window: MainWindow) -> None:
    post = window._current_post()
    if post is None:
        return

    target_directory = window.settings.download_directory or window.store.default_download_directory()
    if not target_directory:
        target_directory = QFileDialog.getExistingDirectory(window, "Choose download folder")
    if not target_directory:
        return

    window._set_status(f"Downloading {post.file_name}...")

    def download() -> Path:
        return download_post_to_directory(window, post, target_directory)

    window._single_download_token += 1
    token = window._single_download_token

    worker = FunctionWorker(download_post_to_directory, window, post, target_directory)
    worker.signals.finished.connect(lambda result: download_finished(window, token, result))
    worker.signals.failed.connect(window._operation_failed)
    window._start_worker(worker, workload="download")


def download_multiple_posts(window: MainWindow, posts: list[Post]) -> None:
    unique_posts = list({post.id: post for post in posts}.values())
    if not unique_posts:
        return

    target_directory = window.settings.download_directory or window.store.default_download_directory()
    if not target_directory:
        target_directory = QFileDialog.getExistingDirectory(window, "Choose download folder")
    if not target_directory:
        return

    window._set_status(f"Downloading {len(unique_posts)} selected favorites...")

    def download_many(win: MainWindow, posts_to_dl: list[Post], tgt_dir: str) -> list[Path]:
        successes: list[Path] = []
        for p in posts_to_dl:
            try:
                result = download_post_to_directory(win, p, tgt_dir)
                if result is not None:
                    successes.append(result)
            except RuntimeError:
                continue
        return successes

    window._bulk_download_token += 1
    token = window._bulk_download_token

    worker = FunctionWorker(download_many, window, unique_posts, target_directory)
    worker.signals.finished.connect(lambda result: download_many_finished(window, token, result))
    worker.signals.failed.connect(window._operation_failed)
    window._start_worker(worker, workload="download")


def download_post_to_directory(window: MainWindow, post: Post, target_directory: str) -> Path:
    resolved = resolve_download_post(window, post)
    result = window.download_manager.download_post(resolved, window.settings)
    if result is None:
        # Already downloaded or skipped
        return Path("") 
    return result


def resolve_download_post(window: MainWindow, post: Post) -> Post:
    if not download_url_needs_hydration(post.download_url):
        return post
    candidates = window.client.search_posts(f"id:{post.id}", 0, 1)
    if not candidates:
        return post
    hydrated = candidates[0]
    if download_url_needs_hydration(hydrated.download_url):
        return post
    return hydrated


def start_worker(window: MainWindow, worker: FunctionWorker, workload: str = "general") -> None:
    window._active_workers.add(worker)

    def release_worker(*_: object) -> None:
        window._active_workers.discard(worker)

    worker.signals.finished.connect(release_worker)
    worker.signals.failed.connect(release_worker)
    window._pool_for_workload(workload).start(worker)


def download_finished(window: MainWindow, token: int, result: object) -> None:
    if token != window._single_download_token:
        return
    if isinstance(result, Path):
        if str(result):
            window._set_status(f"Saved to {result}")
        else:
            window._set_status("Post already downloaded.")


def download_many_finished(window: MainWindow, token: int, result: object) -> None:
    if token != window._bulk_download_token:
        return
    paths = [item for item in result if isinstance(item, Path) and str(item)] if isinstance(result, list) else []
    window._set_status(f"Saved {len(paths)} files.")
