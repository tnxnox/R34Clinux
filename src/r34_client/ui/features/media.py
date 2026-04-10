from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...models import Post
    from ..main_window import MainWindow

try:
    import vlc  # type: ignore
except ImportError:  # pragma: no cover
    vlc = None


def show_video_preview(window: MainWindow, post: Post) -> None:
    window._base_preview_pixmap = None
    window._is_long_strip_image = False
    window._image_zoom_percent = 100
    window.meta_view.setPlainText(window._format_post_metadata(post))
    source_url = post.file_url or post.sample_url or post.preview_url
    if not source_url:
        hide_video_view(window)
        window.preview_label.setText("This video post does not expose a playable URL.")
        window._set_status("Video post selected.")
        return

    if window._vlc_player is None or window._vlc_instance is None:
        hide_video_view(window)
        window.preview_label.setText("In-app video is unavailable on this build. Click 'Play Video' to open externally.")
        window._set_status("In-app video backend unavailable; using external playback.")
        return

    window.preview_container.hide()
    window.video_surface.show()

    try:
        media = window._vlc_instance.media_new(source_url)
        window._vlc_player.set_media(media)
        window_id = int(window.video_surface.winId())
        if hasattr(window._vlc_player, "set_xwindow"):
            window._vlc_player.set_xwindow(window_id)
        elif hasattr(window._vlc_player, "set_hwnd"):
            window._vlc_player.set_hwnd(window_id)
        elif hasattr(window._vlc_player, "set_nsobject"):
            window._vlc_player.set_nsobject(window_id)

        result = window._vlc_player.play()
        if result == -1:
            raise RuntimeError("VLC could not start playback")
        on_volume_changed(window, window.volume_slider.value())
        window._set_status("Playing video preview in-app.")
    except Exception as exc:
        hide_video_view(window)
        window.preview_label.setText("Unable to play this video in-app. Click 'Play Video' again to open externally.")
        window._set_status(str(exc))


def hide_video_view(window: MainWindow) -> None:
    if window._vlc_player is not None:
        try:
            window._vlc_player.stop()
        except Exception:
            pass
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

    if window._vlc_player is not None and vlc is not None and window.video_surface.isVisible():
        try:
            state = window._vlc_player.get_state()
            if state == vlc.State.Playing:
                window._vlc_player.pause()
                window._set_status("Video paused.")
                return
            if state in (vlc.State.Paused, vlc.State.Stopped, vlc.State.Ended):
                window._vlc_player.play()
                window._set_status("Video playing.")
                return
        except Exception:
            pass

    show_video_preview(window, post)


def on_volume_changed(window: MainWindow, value: int) -> None:
    if window._vlc_player is None:
        return
    try:
        window._vlc_player.audio_set_volume(int(value))
    except Exception:
        return


def on_seek_slider_pressed(window: MainWindow) -> None:
    window._seek_dragging = True
    window._pending_seek_ms = window.seek_slider.value()


def on_seek_slider_moved(window: MainWindow, value: int) -> None:
    window._pending_seek_ms = value
    total_ms = max(window.seek_slider.maximum(), 0)
    window.seek_time_label.setText(f"{window._format_millis(value)} / {window._format_millis(total_ms)}")


def on_seek_slider_released(window: MainWindow) -> None:
    window._seek_dragging = False
    if window._vlc_player is None:
        return
    target = int(window._pending_seek_ms)
    try:
        window._vlc_player.set_time(target)
    except Exception:
        return


def refresh_playback_controls(window: MainWindow) -> None:
    if window._vlc_player is None:
        window.seek_slider.setEnabled(False)
        return

    post = window._current_post()
    is_video = post is not None and window._is_video_post(post)
    if not is_video:
        window.seek_slider.setEnabled(False)
        return

    try:
        total_ms = max(int(window._vlc_player.get_length()), 0)
        current_ms = max(int(window._vlc_player.get_time()), 0)
    except Exception:
        window.seek_slider.setEnabled(False)
        return

    window.seek_slider.setEnabled(total_ms > 0)
    window.seek_slider.blockSignals(True)
    window.seek_slider.setRange(0, total_ms)
    if not window._seek_dragging:
        window.seek_slider.setValue(min(current_ms, total_ms))
    window.seek_slider.blockSignals(False)
    shown_ms = window.seek_slider.value() if window._seek_dragging else current_ms
    window.seek_time_label.setText(f"{window._format_millis(shown_ms)} / {window._format_millis(total_ms)}")
