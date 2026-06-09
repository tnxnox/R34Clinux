from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QCoreApplication

from r34_client.ui.widgets.video_player import VideoPlayer


class VideoPlayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QCoreApplication.instance() or QCoreApplication([])

    def test_initialization_with_vlc_none(self) -> None:
        """When vlc is None, the player is not available."""
        with patch("r34_client.ui.widgets.video_player.vlc", None):
            player = VideoPlayer()
            self.assertFalse(player.is_available)
            player.release()

    def test_release_cleans_up_resources(self) -> None:
        """Calling release resets vlc player and instance to None."""
        player = VideoPlayer()
        # Mock the internal player and instance
        mock_vlc_player = MagicMock()
        mock_vlc_instance = MagicMock()
        player._vlc_player = mock_vlc_player
        player._vlc_instance = mock_vlc_instance

        player.release()

        mock_vlc_player.stop.assert_called_once()
        mock_vlc_player.release.assert_called_once()
        self.assertIsNone(player._vlc_player)
        self.assertIsNone(player._vlc_instance)

    def test_stop_calls_underlying_vlc_stop(self) -> None:
        """stop() delegates to the underlying VLC player stop method."""
        player = VideoPlayer()
        mock_vlc_player = MagicMock()
        player._vlc_player = mock_vlc_player

        player.stop()

        mock_vlc_player.stop.assert_called_once()
