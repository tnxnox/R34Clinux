from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from r34_client.core.worker import FunctionWorker
from r34_client.core.models import Post
from r34_client.ui.helpers.image_fit import compute_base_render_size
from r34_client.ui.helpers.post import is_video_post, needs_hydration, probe_file_size
from r34_client.ui.helpers.preview_fetcher import fetch_preview_bytes

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..main_window import MainWindow


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
        logger.debug("Selection changed: no item selected")
        return
    post = current.data(Qt.ItemDataRole.UserRole)
    if isinstance(post, Post):
        logger.info("Selection changed: Post ID %d", post.id)
        show_post(window, post)


def show_post(window: MainWindow, post: Post, allow_hydrate: bool = True) -> None:
    needs_hydrate = allow_hydrate and needs_hydration(post, window._metadata_hydrated_ids)
    logger.debug("show_post called for ID %d (needs_hydrate=%s, allow_hydrate=%s)", post.id, needs_hydrate, allow_hydrate)

    if needs_hydrate:
        window._set_status(f"Post #{post.id} selected (loading details...).")
        window.meta_view.setPlainText("Loading post details...")
        window.preview_label.setText("Loading preview...")

        window._hydrate_token += 1
        h_token = window._hydrate_token
        logger.debug("Starting metadata hydration for ID %d (token=%d)", post.id, h_token)

        worker = FunctionWorker(hydrate_post, window, post)
        worker.signals.finished.connect(lambda hydrated, t=h_token: show_hydrated_post(window, t, post, hydrated))
        worker.signals.failed.connect(lambda error_text, t=h_token: show_hydration_failed(window, t, post, error_text))
        window._start_worker(worker, workload="preview")

    if is_video_post(post):
        window._show_video_preview(post)
        return

    if not needs_hydrate:
        window.meta_view.setPlainText(window._format_post_metadata(post))

    window._preview_token += 1
    token = window._preview_token
    logger.debug("Requested preview load for ID %d (token=%d)", post.id, token)

    if not post.best_preview_url:
        logger.warning("Post ID %d has no preview URL", post.id)
        window.preview_label.setText("This post does not expose a preview URL.")
        window._set_status(f"Post #{post.id} selected (no preview URL).")
        return

    # Check cache first — instant display without a network request.
    cached = window._image_cache.get(post.id)
    if cached is not None:
        logger.debug("Preview for ID %d found in cache (token=%d)", post.id, token)
        window._set_status(f"Post #{post.id} selected.")
        preview_loaded(window, token, cached, post)
        return

    logger.debug("Fetching preview bytes for ID %d from network (token=%d)", post.id, token)
    window.preview_label.setText("Loading preview...")
    window._set_status(f"Post #{post.id} selected (loading preview...).")
    worker = FunctionWorker(fetch_preview_bytes, post, user_id=window.settings.user_id)
    worker.signals.finished.connect(lambda data: preview_loaded(window, token, data, post))
    worker.signals.failed.connect(lambda error_text: preview_failed_with_context(window, token, post, error_text))
    window._start_worker(worker, workload="preview")


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
        logger.debug("Hydration finished for ID %d but token mismatched (got %d, current %d), discarding", fallback.id, token, window._hydrate_token)
        return
    logger.info("Successfully hydrated metadata for ID %d", fallback.id)
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
        elif window.left_tabs.currentWidget() is window.friends_tab:
            target_item = _find_item_by_post_id(window.friend_posts_list, fallback.id)
            if target_item is not None:
                target_item.setData(Qt.ItemDataRole.UserRole, chosen)
                target_item.setText(window._format_post_tile(chosen))
            window.friend_posts = [chosen if item.id == chosen.id else item for item in window.friend_posts]
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
        logger.debug("Hydration failed for ID %d but token mismatched (got %d, current %d), discarding error", fallback.id, token, window._hydrate_token)
        return
    logger.error("Hydration failed for ID %d: %s", fallback.id, error_text)
    reason = error_text.splitlines()[-1] if error_text else ""
    msg = f"Failed to load details: {reason}" if reason else "Unable to load post details."
    window._set_status(msg)
    active_post = window._current_post()
    if active_post is not None and active_post.id == fallback.id:
        logger.debug("Hydration failed post ID %d is still active selection, displaying fallback", fallback.id)
        show_post(window, fallback, allow_hydrate=False)
    else:
        logger.debug("Hydration failed post ID %d is no longer active selection, skipping display fallback", fallback.id)


def preview_failed(window: MainWindow, error_text: str) -> None:
    window._base_preview_pixmap = None
    window._is_long_strip_image = False
    window._image_zoom_percent = 100
    window._image_pan_active = False
    window._hide_video_view()
    window.preview_label.setText("Preview unavailable for this item.")
    
    reason = error_text.splitlines()[-1] if error_text else ""
    msg = f"Preview unavailable: {reason}" if reason else "Preview unavailable."
    window._set_status(msg)


def preview_failed_with_context(window: MainWindow, token: int, post: Post, error_text: str) -> None:
    if token != window._preview_token:
        logger.debug("Preview fetch failed for ID %d but token mismatched (got %d, current %d), discarding error", post.id, token, window._preview_token)
        return
    logger.error("Preview fetch failed for ID %d: %s", post.id, error_text)
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
        logger.debug("Preview loaded for ID %d but token mismatched or invalid data (got token %d, current %d)", post.id, token, window._preview_token)
        return
    logger.info("Preview loaded for ID %d (%d bytes)", post.id, len(data))

    image = QImage.fromData(bytes(data))
    if image.isNull():
        window.preview_label.setText("Preview image could not be decoded.")
        return

    pixmap = QPixmap.fromImage(image)
    if pixmap.isNull():
        window.preview_label.setText("Preview image could not be loaded.")
        return

    # Cache for future requests (adjacent post navigation, tab switches, etc.)
    window._image_cache.put(post.id, bytes(data))

    window._base_preview_pixmap = pixmap

    # Classify as "long strip" (comic strip / stitched multi-panel) only when
    # the image is both very tall *and* narrower than the viewport.  A genuine
    # strip is typically ~500–800 px wide with height/width > 4× — fitting it to
    # viewport height would make it unreadably tiny.  A tall single image
    # (full-body portrait, phone wallpaper, etc.) that's 2.2–4× taller than it is
    # wide still looks fine centered in the viewport and shouldn't be top-aligned
    # or forced to full width.
    vp = window.preview_container.viewport()
    vp_w = max(1, vp.width())
    ratio = pixmap.height() / pixmap.width()
    width_is_narrow = pixmap.width() < vp_w
    window._is_long_strip_image = ratio >= 4.0 or (ratio >= 2.8 and width_is_narrow)
    window._image_zoom_percent = 100
    window._hide_video_view()
    window.preview_label.setText("")
    update_preview_scaling(window)

    # Fire-and-forget: prefetch adjacent posts for instant J/K navigation.
    window._prefetch_adjacent(post)
    if window._is_long_strip_image:
        window.preview_container.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        window.preview_container.verticalScrollBar().setValue(0)
    else:
        window.preview_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
    window.preview_label.setToolTip(post.file_name)
    window._set_status(f"Post #{post.id} selected.")


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
    window.preview_label.adjustSize()  # Force parent scroll area layout update synchronously
    window.preview_container.updateGeometry()  # Notify parent layout system of geometry change
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
