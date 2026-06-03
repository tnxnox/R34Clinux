from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    import vlc  # type: ignore
except ImportError:  # pragma: no cover
    logger.warning("VLC Python bindings not available; in-app video playback disabled.")
    vlc = None


class VideoPlayer:
    def __init__(self) -> None:
        self._vlc_instance = None
        self._vlc_player = None
        self._fallback_active = True
        self._setup_backend(fallback=True)

    def _argument_profiles(self, fallback: bool) -> list[list[str]]:
        """Return progressively more conservative argument sets to try.

        Returns a list of argument lists, ordered from most aggressive to
        most conservative.  Each profile is tried in order until one
        succeeds.
        """
        base = ["--no-video-title-show", "--network-caching=600", "--file-caching=300"]

        if not fallback:
            return [base[:]]

        return [
            # Profile 1 — hardware decode disabled, forced xcb output (default)
            base + ["--avcodec-hw=none", "--vout=xcb_x11", "--codec=avcodec"],
            # Profile 2 — alternative flags for VLC 4.0+ / different builds
            base + ["--avcodec-hw=none", "--vout=xcb", "--codec=avcodec"],
            # Profile 3 — no hardware opts at all
            base[:],
        ]

    def _setup_backend(self, fallback: bool) -> bool:
        if vlc is None:
            self._vlc_instance = None
            self._vlc_player = None
            self._fallback_active = False
            return False

        profiles = self._argument_profiles(fallback)

        for idx, args in enumerate(profiles):
            try:
                instance = vlc.Instance(*args)
                if instance is None:
                    logger.debug(
                        "VLC instance returned None with profile %d/%d (args=%s)",
                        idx + 1, len(profiles), args,
                    )
                    continue
                player = instance.media_player_new()
                if player is None:
                    logger.debug(
                        "VLC media_player_new returned None with profile %d/%d",
                        idx + 1, len(profiles),
                    )
                    continue
                self._vlc_instance = instance
                self._vlc_player = player
                self._fallback_active = fallback
                if idx > 0:
                    logger.info("VLC backend initialised with fallback profile %d/%d", idx + 1, len(profiles))
                return True
            except Exception as exc:
                logger.debug(
                    "VLC profile %d/%d failed: %s",
                    idx + 1, len(profiles), exc,
                )
                continue

        # All profiles exhausted
        logger.warning(
            "Failed to set up VLC backend (fallback=%s) after %d profiles",
            fallback, len(profiles),
        )
        self._vlc_instance = None
        self._vlc_player = None
        self._fallback_active = False
        return False

    @property
    def is_available(self) -> bool:
        return self._vlc_player is not None

    @property
    def fallback_active(self) -> bool:
        return self._fallback_active

    def configure_fallback(self) -> bool:
        return self._setup_backend(fallback=True)

    def start_embedded_playback(self, source_url: str, window_id: int, start_time_ms: int = 0) -> None:
        if self._vlc_player is None or self._vlc_instance is None:
            raise RuntimeError("In-app video backend unavailable")

        media = self._vlc_instance.media_new(source_url)
        if self._fallback_active:
            media.add_option(":avcodec-hw=none")
            media.add_option(":codec=avcodec")
        media.add_option(":network-caching=600")
        media.add_option(":file-caching=300")
        
        if start_time_ms > 0:
            start_seconds = max(0.0, start_time_ms / 1000.0)
            media.add_option(f":start-time={start_seconds:.3f}")

        self._vlc_player.set_media(media)
        
        if hasattr(self._vlc_player, "set_xwindow"):
            self._vlc_player.set_xwindow(window_id)
        elif hasattr(self._vlc_player, "set_hwnd"):
            self._vlc_player.set_hwnd(window_id)
        elif hasattr(self._vlc_player, "set_nsobject"):
            self._vlc_player.set_nsobject(window_id)

        result = self._vlc_player.play()
        if result == -1:
            raise RuntimeError("VLC could not start playback")

    def release(self) -> None:
        if self._vlc_player is not None:
            try:
                self._vlc_player.stop()
            except Exception:
                pass
            try:
                self._vlc_player.release()
            except Exception:
                pass
            self._vlc_player = None
            self._vlc_instance = None

    def stop(self) -> None:
        if self._vlc_player is not None:
            try:
                self._vlc_player.stop()
            except Exception:
                pass

    def play(self) -> None:
        if self._vlc_player is not None:
            try:
                self._vlc_player.play()
            except Exception:
                pass

    def pause(self) -> None:
        if self._vlc_player is not None:
            try:
                self._vlc_player.pause()
            except Exception:
                pass

    def is_playing(self) -> bool:
        if self._vlc_player is None or vlc is None:
            return False
        try:
            return self._vlc_player.get_state() == vlc.State.Playing
        except Exception:
            return False

    def is_paused(self) -> bool:
        if self._vlc_player is None or vlc is None:
            return False
        try:
            return self._vlc_player.get_state() == vlc.State.Paused
        except Exception:
            return False

    def set_volume(self, volume: int) -> None:
        if self._vlc_player is not None:
            try:
                self._vlc_player.audio_set_volume(int(volume))
            except Exception:
                pass

    def get_length(self) -> int:
        if self._vlc_player is not None:
            try:
                return max(int(self._vlc_player.get_length()), 0)
            except Exception:
                pass
        return 0

    def get_time(self) -> int:
        if self._vlc_player is not None:
            try:
                return max(int(self._vlc_player.get_time()), 0)
            except Exception:
                pass
        return 0

    def set_time(self, time_ms: int) -> None:
        if self._vlc_player is not None:
            try:
                self._vlc_player.set_time(time_ms)
            except Exception:
                pass

    def set_position(self, pos: float) -> None:
        if self._vlc_player is not None:
            try:
                self._vlc_player.set_position(max(0.0, min(1.0, pos)))
            except Exception:
                pass