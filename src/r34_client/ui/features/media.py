from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...models import Post
    from ..windows.main_window import MainWindow

try:
    import vlc  # type: ignore
except ImportError:  # pragma: no cover
    vlc = None


def _configure_vlc_backend(window: MainWindow, *, fallback: bool) -> bool:
    if vlc is None:
        window._vlc_instance = None
        window._vlc_player = None
        window._vlc_fallback_active = False
        return False

    args = ["--no-video-title-show", "--network-caching=1500"]
    if fallback:
        # Compatibility profile avoids problematic GPU decode/output paths on some Linux systems.
        args.extend(["--avcodec-hw=none", "--vout=xcb_x11", "--codec=avcodec"])

    try:
        window._vlc_instance = vlc.Instance(*args)
        window._vlc_player = window._vlc_instance.media_player_new()
        window._vlc_fallback_active = fallback
        return True
    except Exception:
        window._vlc_instance = None
        window._vlc_player = None
        window._vlc_fallback_active = False
        return False


def _start_embedded_playback(window: MainWindow, source_url: str) -> None:
    if window._vlc_player is None or window._vlc_instance is None:
        raise RuntimeError("In-app VLC backend unavailable")

    media = window._vlc_instance.media_new(source_url)
    media.add_option(":avcodec-hw=none")
    media.add_option(":codec=avcodec")
    media.add_option(":network-caching=1500")
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


def _media_source_url(post: Post) -> str:
    return post.file_url or post.sample_url or post.preview_url


def _restart_playback_at(window: MainWindow, post: Post, target_ms: int) -> None:
    if window._vlc_player is None or window._vlc_instance is None:
        return
    source_url = _media_source_url(post)
    if not source_url:
        return

    start_seconds = max(0.0, target_ms / 1000.0)
    media = window._vlc_instance.media_new(source_url)
    media.add_option(f":start-time={start_seconds:.3f}")
    media.add_option(":avcodec-hw=none")
    media.add_option(":codec=avcodec")
    media.add_option(":network-caching=1500")
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
        raise RuntimeError("VLC restart seek failed")


def show_video_preview(window: MainWindow, post: Post) -> None:
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

    if window._vlc_player is None or window._vlc_instance is None:
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
        if window._vlc_fallback_active:
            window._set_status("Playing video preview in-app (VLC compatibility backend).")
        else:
            window._set_status("Playing video preview in-app.")
    except Exception as exc:
        playback_error = str(exc)
        if _configure_vlc_backend(window, fallback=True):
            try:
                _start_embedded_playback(window, source_url)
                on_volume_changed(window, window.volume_slider.value())
                window._set_status("Playing video preview in-app (VLC compatibility backend).")
                return
            except Exception as fallback_exc:
                playback_error = str(fallback_exc)

        hide_video_view(window)
        window.preview_label.setText("Unable to play this video in-app. Click 'Play Video' again to open externally.")
        window._set_status(playback_error or "Video playback failed")


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
    window._seek_was_playing = False
    if window._vlc_player is not None and vlc is not None:
        try:
            window._seek_was_playing = window._vlc_player.get_state() == vlc.State.Playing
        except Exception:
            window._seek_was_playing = False


def on_seek_slider_moved(window: MainWindow, value: int) -> None:
    window._pending_seek_ms = value
    total_ms = max(window.seek_slider.maximum(), 0)
    window.seek_time_label.setText(f"{window._format_millis(value)} / {window._format_millis(total_ms)}")


def on_seek_slider_released(window: MainWindow) -> None:
    window._seek_dragging = False
    if window._vlc_player is None:
        return
    post = window._current_post()
    target = int(window._pending_seek_ms)
    total_ms = max(window.seek_slider.maximum(), 0)

    if post is not None:
        source_url = _media_source_url(post)
        if source_url.startswith("http://") or source_url.startswith("https://"):
            try:
                _restart_playback_at(window, post, target)
                on_volume_changed(window, window.volume_slider.value())
                window._pending_seek_target_ms = target
                window._pending_seek_deadline = time.monotonic() + 2.0
                window._pending_seek_retries = 0
                return
            except Exception:
                # Fall back to direct seek methods below.
                pass

    try:
        window._vlc_player.set_time(target)
    except Exception:
        pass

    # Fallback path for streams where set_time is unreliable.
    if total_ms > 0:
        try:
            window._vlc_player.set_position(max(0.0, min(1.0, target / total_ms)))
        except Exception:
            pass

    if window._seek_was_playing:
        try:
            window._vlc_player.play()
        except Exception:
            pass

    window._pending_seek_target_ms = target
    window._pending_seek_deadline = time.monotonic() + 2.0
    window._pending_seek_retries = 0


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

    if (
        window._pending_seek_target_ms is not None
        and not window._seek_dragging
        and total_ms > 0
    ):
        delta = abs(current_ms - window._pending_seek_target_ms)
        if delta <= 1500:
            window._pending_seek_target_ms = None
            window._pending_seek_retries = 0
        elif time.monotonic() <= window._pending_seek_deadline and window._pending_seek_retries < 3:
            try:
                window._vlc_player.set_position(
                    max(0.0, min(1.0, window._pending_seek_target_ms / total_ms))
                )
                if window._seek_was_playing:
                    window._vlc_player.play()
            except Exception:
                pass
            window._pending_seek_retries += 1
        else:
            window._pending_seek_target_ms = None
            window._pending_seek_retries = 0

    window.seek_slider.setEnabled(total_ms > 0)
    window.seek_slider.blockSignals(True)
    window.seek_slider.setRange(0, total_ms)
    if not window._seek_dragging:
        window.seek_slider.setValue(min(current_ms, total_ms))
    window.seek_slider.blockSignals(False)
    shown_ms = window.seek_slider.value() if window._seek_dragging else current_ms
    window.seek_time_label.setText(f"{window._format_millis(shown_ms)} / {window._format_millis(total_ms)}")
