from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import requests
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog

from ...execution.concurrency import FunctionWorker
from ..rendering.post_helpers import download_url_needs_hydration

if TYPE_CHECKING:
    from ...core.models import Post
    from ..windows.main_window import MainWindow


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

    window._download_token += 1
    token = window._download_token

    worker = FunctionWorker(download)
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

    def download_many() -> list[Path]:
        return [download_post_to_directory(window, post, target_directory) for post in unique_posts]

    window._download_token += 1
    token = window._download_token

    worker = FunctionWorker(download_many)
    worker.signals.finished.connect(lambda result: download_many_finished(window, token, result))
    worker.signals.failed.connect(window._operation_failed)
    window._start_worker(worker, workload="download")


def download_post_to_directory(window: MainWindow, post: Post, target_directory: str) -> Path:
    resolved = resolve_download_post(window, post)
    url = resolved.download_url
    if not url:
        raise RuntimeError("This post does not expose a downloadable file URL.")

    destination = Path(target_directory) / resolved.file_name
    if destination.exists():
        destination = destination.with_name(f"{destination.stem}-{resolved.id}{destination.suffix}")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": resolved.page_url,
        "Accept": "*/*",
    }
    response = requests.get(url, timeout=60, stream=True, headers=headers)
    response.raise_for_status()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as file_handle:
        for chunk in response.iter_content(chunk_size=1024 * 64):
            if chunk:
                file_handle.write(chunk)
    return destination


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
    if token != window._download_token:
        return
    if isinstance(result, Path):
        window._set_status(f"Saved to {result}")


def download_many_finished(window: MainWindow, token: int, result: object) -> None:
    if token != window._download_token:
        return
    paths = [item for item in result if isinstance(item, Path)] if isinstance(result, list) else []
    window._set_status(f"Saved {len(paths)} files.")
