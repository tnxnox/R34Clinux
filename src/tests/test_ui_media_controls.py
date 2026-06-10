from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt, QPointF, QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from r34_client.ui.widgets.custom import ClickSeekSlider
from r34_client.ui.features.media import refresh_playback_controls


class MockVideoPlayer:
    def __init__(self) -> None:
        self.is_available = True
        self.length = 10000
        self.time = 2000
        self.playing = True

    def get_length(self) -> int:
        return self.length

    def get_time(self) -> int:
        return self.time

    def is_playing(self) -> bool:
        return self.playing


class MockMainWindow:
    def __init__(self) -> None:
        self.video_player = MockVideoPlayer()
        self.seek_slider = ClickSeekSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 10000)
        self.seek_slider.setValue(2000)
        self.seek_time_label = MagicMock()
        self._current_post_val = MagicMock()
        self._is_video_post_val = True
        self._seek_ui_locked = False
        self._seek_dragging = False
        self._pending_seek_ms = 0
        self._seek_ui_hold_ms = 0
        self._seek_ui_unlock_deadline = 0.0
        self._pending_seek_target_ms: int | None = None

    def _current_post(self) -> MagicMock | None:
        return self._current_post_val

    def _is_video_post(self, post: object) -> bool:
        return self._is_video_post_val

    def _format_millis(self, ms: int) -> str:
        return f"{ms}"


class MediaControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_click_seek_slider_mouse_press(self) -> None:
        """Left click on ClickSeekSlider updates value and emits sliderMoved."""
        slider = ClickSeekSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(10)
        slider.resize(100, 20)

        moved_values: list[int] = []
        slider.sliderMoved.connect(moved_values.append)

        # Simulate left-button click at horizontal position 50 (middle of 100 width)
        event = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(50.0, 10.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        slider.mousePressEvent(event)

        # The style mapping of position 50 on width 100 (range 0 to 100) should be around 50
        self.assertAlmostEqual(slider.value(), 50, delta=5)
        self.assertEqual(len(moved_values), 1)
        self.assertAlmostEqual(moved_values[0], 50, delta=5)

    def test_refresh_playback_controls_normal(self) -> None:
        """Normally refresh_playback_controls updates range, value, and label."""
        window = MockMainWindow()
        refresh_playback_controls(window)

        self.assertEqual(window.seek_slider.minimum(), 0)
        self.assertEqual(window.seek_slider.maximum(), 10000)
        self.assertEqual(window.seek_slider.value(), 2000)
        window.seek_time_label.setText.assert_called_with("2000 / 10000")

    def test_refresh_playback_controls_seek_locked_buffering(self) -> None:
        """When total_ms is 0 and seek lock is active, previous range and value are preserved."""
        window = MockMainWindow()
        window.seek_slider.setRange(0, 15000)
        window.seek_slider.setValue(5000)
        
        # Simulate seek-lock: we seeked to 5000, but VLC reports length 0/time 0 because it reloads
        window._seek_ui_locked = True
        window._seek_ui_hold_ms = 5000
        window._seek_ui_unlock_deadline = time.monotonic() + 3.0
        window.video_player.length = 0
        window.video_player.time = 0

        refresh_playback_controls(window)

        # The range and value should NOT snap to 0!
        self.assertEqual(window.seek_slider.maximum(), 15000)
        self.assertEqual(window.seek_slider.value(), 5000)
        window.seek_time_label.setText.assert_called_with("5000 / 15000")

    def test_refresh_playback_controls_early_unlock(self) -> None:
        """When player time is close to seek hold target, the seek lock is released."""
        window = MockMainWindow()
        window.seek_slider.setRange(0, 15000)
        
        # Seek lock active
        window._seek_ui_locked = True
        window._seek_ui_hold_ms = 5000
        window._seek_ui_unlock_deadline = time.monotonic() + 3.0
        
        # VLC has finished buffering and current time is 5100 (close to 5000 target)
        window.video_player.length = 15000
        window.video_player.time = 5100

        refresh_playback_controls(window)

        # The lock should be released
        self.assertFalse(window._seek_ui_locked)
        self.assertEqual(window.seek_slider.value(), 5100)
        window.seek_time_label.setText.assert_called_with("5100 / 15000")
