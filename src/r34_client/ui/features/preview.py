from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from ...concurrency import FunctionWorker
from ...models import Post
from ..rendering.image_fit import compute_base_render_size
from ..rendering.post_helpers import is_video_post, needs_hydration, probe_file_size
from ..rendering.preview_fetcher import fetch_preview_bytes

if TYPE_CHECKING:
    from ..windows.main_window import MainWindow


def _find_item_by_post_id(list_widget, post_id: int):
    for row in range(list_widget.count()):
        item = list_widget.item(row)
        if item is None:
            continue
        candidate = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(candidate, Post) and candidate.id == post_id:
            return item
    return None


def handle_selection_change(window: MainWindow, current, _previous) -> None:
    window._update_action_state()
    if current is None:
        return
    post = current.data(Qt.ItemDataRole.UserRole)
    if isinstance(post, Post):
        show_post(window, post)


def show_post(window: MainWindow, post: Post, allow_hydrate: bool = True) -> None:
    if allow_hydrate and needs_hydration(post, window._metadata_hydrated_ids):
        window.meta_view.setPlainText("Loading post details...")
        window.preview_label.setText("Loading preview...")

        window._hydrate_token += 1
        token = window._hydrate_token

        worker = FunctionWorker(lambda: hydrate_post(window, post))
        worker.signals.finished.connect(lambda hydrated: show_hydrated_post(window, token, post, hydrated))
        worker.signals.failed.connect(lambda error_text: show_hydration_failed(window, token, post, error_text))
        window._start_worker(worker)
        return

    if is_video_post(post):
        window._show_video_preview(post)
        return

    window.meta_view.setPlainText(window._format_post_metadata(post))
    window.preview_label.setText("Loading preview...")

    window._preview_token += 1
    token = window._preview_token
    if not post.best_preview_url:
        window.preview_label.setText("This post does not expose a preview URL.")
        return

    def fetch_preview() -> bytes:
        return fetch_preview_bytes(post, user_id=window.settings.user_id)

    worker = FunctionWorker(fetch_preview)
    worker.signals.finished.connect(lambda data: preview_loaded(window, token, data, post))
    worker.signals.failed.connect(lambda error_text: preview_failed_with_context(window, post, error_text))
    window._start_worker(worker)


def current_post_is_video(window: MainWindow) -> bool:
    post = window._current_post()
    return is_video_post(post) if post is not None else False


def hydrate_post(window: MainWindow, post: Post) -> Post:
    candidates = window.client.search_posts(f"id:{post.id}", 0, 1)
    if candidates:
        hydrated = candidates[0]
        if not hydrated.source:
            hydrated.source = hydrated.page_url
        if hydrated.file_size is None and hydrated.file_url:
            probed = probe_file_size(hydrated.file_url, hydrated.page_url)
            if probed is not None:
                hydrated.file_size = probed
        return hydrated
    return post


def show_hydrated_post(window: MainWindow, token: int, fallback: Post, hydrated: object) -> None:
    if token != window._hydrate_token:
        return
    chosen = hydrated if isinstance(hydrated, Post) else fallback
    if isinstance(chosen, Post):
        window._metadata_hydrated_ids.add(chosen.id)
        if window.left_tabs.currentWidget() is window.favorites_list:
            target_item = _find_item_by_post_id(window.favorites_list, fallback.id)
            if target_item is not None:
                target_item.setData(Qt.ItemDataRole.UserRole, chosen)
                target_item.setText(window._format_post_tile(chosen))
            window.favorite_posts = [chosen if item.id == chosen.id else item for item in window.favorite_posts]
            window.local_favorites.add_favorite(chosen)
        else:
            target_item = _find_item_by_post_id(window.results_list, fallback.id)
            if target_item is not None:
                target_item.setData(Qt.ItemDataRole.UserRole, chosen)
                target_item.setText(window._format_post_tile(chosen))
            window.current_posts = [chosen if item.id == chosen.id else item for item in window.current_posts]
        window._update_action_state()
    active_post = window._current_post()
    if active_post is not None and active_post.id == chosen.id:
        show_post(window, chosen, allow_hydrate=False)


def show_hydration_failed(window: MainWindow, token: int, fallback: Post, error_text: str) -> None:
    if token != window._hydrate_token:
        return
    first_line = error_text.splitlines()[-1] if error_text else "Unable to load post details"
    window._set_status(first_line)
    show_post(window, fallback, allow_hydrate=False)


def preview_failed(window: MainWindow, error_text: str) -> None:
    first_line = error_text.splitlines()[-1] if error_text else "Preview unavailable"
    window._base_preview_pixmap = None
    window._is_long_strip_image = False
    window._image_zoom_percent = 100
    window._image_pan_active = False
    window._hide_video_view()
    window.preview_label.setText("Preview unavailable for this item.")
    window._set_status(first_line)


def preview_failed_with_context(window: MainWindow, post: Post, error_text: str) -> None:
    if window.left_tabs.currentWidget() is window.favorites_list or post.id in window.favorite_ids:
        window._log_sync_debug(
            f"Favorites preview fetch failure for #{post.id}",
            "\n".join(
                [
                    f"Error: {error_text.splitlines()[-1] if error_text else 'unknown error'}",
                    f"Post page: {post.page_url}",
                    f"Sample URL: {post.sample_url or 'n/a'}",
                    f"Preview URL: {post.preview_url or 'n/a'}",
                    f"File URL: {post.file_url or 'n/a'}",
                ]
            ),
        )
    preview_failed(window, error_text)


def preview_loaded(window: MainWindow, token: int, data: object, post: Post) -> None:
    if token != window._preview_token or not isinstance(data, (bytes, bytearray)):
        return

    image = QImage.fromData(bytes(data))
    if image.isNull():
        window.preview_label.setText("Preview image could not be decoded.")
        return

    pixmap = QPixmap.fromImage(image)
    if pixmap.isNull():
        window.preview_label.setText("Preview image could not be loaded.")
        return

    window._base_preview_pixmap = pixmap
    window._is_long_strip_image = pixmap.height() >= (pixmap.width() * 2.2)
    window._image_zoom_percent = 100
    window._hide_video_view()
    window.preview_label.setText("")
    update_preview_scaling(window)
    if window._is_long_strip_image:
        window.preview_container.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        window.preview_container.verticalScrollBar().setValue(0)
    else:
        window.preview_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
    window.preview_label.setToolTip(post.file_name)


def update_preview_scaling(window: MainWindow) -> None:
    if window._base_preview_pixmap is None:
        window._set_preview_cursor()
        return
    viewport = window.preview_container.viewport()
    target_size = viewport.size()
    if target_size.width() <= 1 or target_size.height() <= 1:
        window._set_preview_cursor()
        return

    source = window._base_preview_pixmap
    if source.width() <= 0 or source.height() <= 0:
        return

    base_width, base_height = compute_base_render_size(
        source_width=source.width(),
        source_height=source.height(),
        viewport_width=target_size.width(),
        viewport_height=target_size.height(),
        is_long_strip=window._is_long_strip_image,
        fit_mode=window._fit_mode,
    )

    zoom_factor = max(window._image_zoom_percent, 25) / 100.0
    render_width = max(1, round(base_width * zoom_factor))
    render_height = max(1, round(base_height * zoom_factor))

    scaled = source.scaled(
        render_width,
        render_height,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    window.preview_label.resize(scaled.size())
    window.preview_label.setMinimumSize(scaled.size())
    window.preview_label.setPixmap(scaled)
    window._set_preview_cursor()


def set_image_zoom(window: MainWindow, value: int) -> None:
    window._image_zoom_percent = max(25, min(300, int(value)))
    update_preview_scaling(window)


def can_pan_image(window: MainWindow) -> bool:
    if window._base_preview_pixmap is None or window.video_surface.isVisible():
        return False
    horizontal = window.preview_container.horizontalScrollBar()
    vertical = window.preview_container.verticalScrollBar()
    return horizontal.maximum() > 0 or vertical.maximum() > 0


def set_preview_cursor(window: MainWindow) -> None:
    viewport = window.preview_container.viewport()
    if window._image_pan_active:
        viewport.setCursor(Qt.CursorShape.ClosedHandCursor)
        return
    if can_pan_image(window):
        viewport.setCursor(Qt.CursorShape.OpenHandCursor)
        return
    viewport.unsetCursor()
