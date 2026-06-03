from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.models import Post
    from ..main_window import MainWindow

def _ensure_fallback_backend(window: MainWindow) -> bool:
    return window.video_player.configure_fallback()


def _start_embedded_playback(window: MainWindow, source_url: str) -> None:
    window.video_player.start_embedded_playback(source_url, int(window.video_surface.winId()))


def _media_source_url(post: Post) -> str:
    return post.file_url or post.sample_url or post.preview_url


def _reset_seek_state(window: MainWindow) -> None:
    window._seek_dragging = False
    window._seek_was_playing = False
    window._seek_ui_locked = False
    window._seek_ui_unlock_deadline = 0.0
    window._seek_ui_hold_ms = 0
    window._seek_ui_stable_ticks = 0
    window._pending_seek_ms = 0
    window._pending_seek_target_ms = None
    window._pending_seek_deadline = 0.0
    window._pending_seek_retries = 0


def _restart_playback_at(window: MainWindow, post: Post, target_ms: int) -> None:
    if not window.video_player.is_available:
        return
    source_url = _media_source_url(post)
    if not source_url:
        return
    window.video_player.start_embedded_playback(source_url, int(window.video_surface.winId()), target_ms)


def show_video_preview(window: MainWindow, post: Post) -> None:
    _reset_seek_state(window)
    window._base_preview_pixmap = None
    window._is_long_strip_image = False
    window._image_zoom_percent = 100
    window.meta_view.setPlainText(window._format_post_metadata(post))
    source_url = _media_source_url(post)
    if not source_url:
        hide_video_view(window)
        window.preview_label.setText("This video post does not expose a playable URL.")
        window._set_status("Video post selected.")
        return

    if not window.video_player.is_available:
        hide_video_view(window)
        window.preview_label.setText("In-app video is unavailable on this build. Click 'Play Video' to open externally.")
        window._set_status("In-app video backend unavailable; using external playback.")
        return

    window.preview_container.hide()
    window.video_surface.show()

    playback_error = ""
    try:
        _start_embedded_playback(window, source_url)
        on_volume_changed(window, window.volume_slider.value())
        if window.video_player.fallback_active:
            window._set_status("Playing video preview in-app (VLC compatibility backend).")
        else:
            window._set_status("Playing video preview in-app.")
    except (RuntimeError, OSError) as exc:
        # Catch platform-specific video playback errors (e.g., codec issues, permission errors)
        playback_error = str(exc)
        if _ensure_fallback_backend(window):
            try:
                _start_embedded_playback(window, source_url)
                on_volume_changed(window, window.volume_slider.value())
                window._set_status("Playing video preview in-app (VLC compatibility backend).")
                return
            except (RuntimeError, OSError) as fallback_exc:
                # Fallback backend also failed
                playback_error = str(fallback_exc)

        hide_video_view(window)
        window.preview_label.setText("Unable to play this video in-app. Click 'Play Video' again to open externally.")
        window._set_status(playback_error or "Video playback failed")


def hide_video_view(window: MainWindow) -> None:
    window.video_player.stop()
    _reset_seek_state(window)
    window.seek_slider.blockSignals(True)
    window.seek_slider.setRange(0, 0)
    window.seek_slider.setValue(0)
    window.seek_slider.blockSignals(False)
    window.seek_time_label.setText("00:00 / 00:00")
    window.video_surface.hide()
    window.preview_container.show()
    window._set_preview_cursor()


def toggle_video_playback(window: MainWindow) -> None:
    post = window._current_post()
    if post is None:
        return
    if not window._is_video_post(post):
        window._set_status("Selected post is not a video.")
        return

    if window.video_player.is_available and window.video_surface.isVisible():
        if window.video_player.is_playing():
            window.video_player.pause()
            window._set_status("Video paused.")
            return
        if window.video_player.is_paused():
            window.video_player.play()
            window._set_status("Video playing.")
            return

    show_video_preview(window, post)


def on_volume_changed(window: MainWindow, value: int) -> None:
    window.video_player.set_volume(int(value))


def on_seek_slider_pressed(window: MainWindow) -> None:
    window._seek_dragging = True
    window._pending_seek_ms = window.seek_slider.value()
    window._seek_was_playing = window.video_player.is_playing()


def on_seek_slider_moved(window: MainWindow, value: int) -> None:
    window._pending_seek_ms = value
    total_ms = max(window.seek_slider.maximum(), 0)
    window.seek_time_label.setText(f"{window._format_millis(value)} / {window._format_millis(total_ms)}")


def on_seek_slider_released(window: MainWindow) -> None:
    window._seek_dragging = False
    if not window.video_player.is_available:
        return
    post = window._current_post()
    target = int(window._pending_seek_ms)
    total_ms = max(window.seek_slider.maximum(), 0)
    window._seek_ui_locked = True
    window._seek_ui_hold_ms = target
    window._seek_ui_unlock_deadline = time.monotonic() + 3.0

    window.seek_slider.blockSignals(True)
    window.seek_slider.setValue(min(target, total_ms))
    window.seek_slider.blockSignals(False)
    window.seek_time_label.setText(f"{window._format_millis(target)} / {window._format_millis(total_ms)}")

    if post is not None:
        source_url = _media_source_url(post)
        if source_url.startswith("http://") or source_url.startswith("https://"):
            try:
                _restart_playback_at(window, post, target)
                on_volume_changed(window, window.volume_slider.value())
                window._pending_seek_target_ms = target
                window._pending_seek_deadline = time.monotonic() + 2.0
                return
            except (RuntimeError, OSError, ValueError):
                # Fall back to direct seek methods below if playback restart fails
                pass

    window.video_player.set_time(target)

    # Fallback path for streams where set_time is unreliable.
    if total_ms > 0:
        window.video_player.set_position(max(0.0, min(1.0, target / total_ms)))

    if window._seek_was_playing:
        window.video_player.play()

    window._pending_seek_target_ms = target
    window._pending_seek_deadline = time.monotonic() + 2.0


def refresh_playback_controls(window: MainWindow) -> None:
    if not window.video_player.is_available:
        window.seek_slider.setEnabled(False)
        return

    post = window._current_post()
    is_video = post is not None and window._is_video_post(post)
    if not is_video:
        window.seek_slider.setEnabled(False)
        return

    total_ms = window.video_player.get_length()
    current_ms = window.video_player.get_time()

    if window._seek_ui_locked and not window._seek_dragging:
        if time.monotonic() >= window._seek_ui_unlock_deadline:
            window._pending_seek_target_ms = None
            window._seek_ui_locked = False
            window._seek_ui_hold_ms = 0

    # Keep the slider interactive while a seek-lock is active, even if VLC length is temporarily unknown.
    window.seek_slider.setEnabled(total_ms > 0 or window._seek_ui_locked)
    window.seek_slider.blockSignals(True)
    if total_ms > 0:
        window.seek_slider.setRange(0, total_ms)
    if window._seek_dragging:
        shown_ms = window._pending_seek_ms
        if total_ms > 0:
            window.seek_slider.setValue(min(shown_ms, total_ms))
        else:
            window.seek_slider.setValue(max(0, shown_ms))
    elif window._seek_ui_locked:
        shown_ms = window._seek_ui_hold_ms
        if total_ms > 0:
            window.seek_slider.setValue(min(shown_ms, total_ms))
        else:
            window.seek_slider.setValue(max(0, shown_ms))
    else:
        shown_ms = min(current_ms, total_ms) if total_ms > 0 else current_ms
        if total_ms > 0:
            window.seek_slider.setValue(shown_ms)
    window.seek_slider.blockSignals(False)
    if not window._seek_ui_locked:
        window.seek_slider.update()
    shown_total_ms = total_ms if total_ms > 0 else max(window.seek_slider.maximum(), shown_ms)
    window.seek_time_label.setText(
        f"{window._format_millis(shown_ms)} / {window._format_millis(shown_total_ms)}"
    )
