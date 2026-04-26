from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from r34_client.ui.features.status import update_action_state, set_left_status, set_status, set_fit_mode
from r34_client.ui.helpers.image_fit import FitMode


class StatusTests(unittest.TestCase):
    def test_set_left_status(self) -> None:
        window = MagicMock()
        set_left_status(window, "Hello")
        window.left_status_label.setText.assert_called_once_with("Hello")

    def test_set_status(self) -> None:
        window = MagicMock()
        set_status(window, "Hello")
        window.left_status_label.setText.assert_called_once_with("Hello")

    def test_set_fit_mode(self) -> None:
        window = MagicMock()
        set_fit_mode(window, FitMode.FIT_WIDTH)
        self.assertEqual(window._fit_mode, FitMode.FIT_WIDTH)
        window._update_preview_scaling.assert_called_once()
        window.left_status_label.setText.assert_called_once_with("Image fit mode: fit_width")

    def test_update_action_state_no_selection_no_query(self) -> None:
        window = MagicMock()
        window._current_post.return_value = None
        window.search_input.text.return_value = ""
        window.video_player.is_available = False
        window._pinned_filters = []
        
        update_action_state(window)
        
        window.download_button.setEnabled.assert_called_once_with(False)
        window.open_button.setEnabled.assert_called_once_with(False)
        window.copy_button.setEnabled.assert_called_once_with(False)
        window.volume_slider.setEnabled.assert_called_once_with(False)
        window.seek_slider.setEnabled.assert_called_once_with(False)
        window.save_search_button.setEnabled.assert_called_once_with(False)
        window.pin_filter_button.setEnabled.assert_called_once_with(False)
        window.pin_filter_button.setText.assert_called_once_with("Pin filter")

    def test_update_action_state_with_selection_and_query(self) -> None:
        window = MagicMock()
        window._current_post.return_value = MagicMock()
        window.search_input.text.return_value = "pokemon"
        window.video_player.is_available = True
        window._current_post_is_video.return_value = True
        window._pinned_filters = ["pokemon"]
        
        update_action_state(window)
        
        window.download_button.setEnabled.assert_called_once_with(True)
        window.open_button.setEnabled.assert_called_once_with(True)
        window.copy_button.setEnabled.assert_called_once_with(True)
        window.volume_slider.setEnabled.assert_called_once_with(True)
        window.seek_slider.setEnabled.assert_called_once_with(True)
        window.save_search_button.setEnabled.assert_called_once_with(True)
        window.pin_filter_button.setEnabled.assert_called_once_with(True)
        window.pin_filter_button.setText.assert_called_once_with("Unpin filter")
