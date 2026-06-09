from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from r34_client.core.models import Post
from r34_client.ui.main_window import MainWindow


class PaginationTests(unittest.TestCase):
    def test_load_more_favorites_chunks(self) -> None:
        """_load_more_favorites loads posts in chunks of 100 by default."""
        window = MagicMock()
        window._format_post_tile = lambda post: f"#{post.id}"
        window.favorites_list = MagicMock()
        
        # Mock 250 favorites
        window._all_favorites_posts = [Post.from_payload({"id": i}) for i in range(250)]
        window._favorites_loaded_count = 0
        
        # Call the unbound method passing our mock window
        MainWindow._load_more_favorites(window)
        
        # Should load the first 100 posts
        self.assertEqual(window._favorites_loaded_count, 100)
        self.assertEqual(window.favorites_list.addItem.call_count, 100)
        
        # Load the next chunk
        MainWindow._load_more_favorites(window)
        self.assertEqual(window._favorites_loaded_count, 200)
        self.assertEqual(window.favorites_list.addItem.call_count, 200)

    def test_load_more_favorites_with_target_index(self) -> None:
        """_load_more_favorites loads enough items to reach target_index."""
        window = MagicMock()
        window._format_post_tile = lambda post: f"#{post.id}"
        window.favorites_list = MagicMock()
        
        # Mock 250 favorites
        window._all_favorites_posts = [Post.from_payload({"id": i}) for i in range(250)]
        window._favorites_loaded_count = 0
        
        # Ask to load up to index 150 (requires loading 151 items)
        MainWindow._load_more_favorites(window, target_index=150)
        self.assertEqual(window._favorites_loaded_count, 151)
        self.assertEqual(window.favorites_list.addItem.call_count, 151)

    def test_favorites_scroll_changed_triggers_loading(self) -> None:
        """_favorites_scroll_changed triggers loading more when close to bottom."""
        window = MagicMock()
        window.favorites_list = MagicMock()
        
        mock_scrollbar = MagicMock()
        mock_scrollbar.maximum.return_value = 100
        window.favorites_list.verticalScrollBar.return_value = mock_scrollbar
        
        # Scroll is at 50% (50/100) — should not trigger loading
        MainWindow._favorites_scroll_changed(window, 50)
        window._load_more_favorites.assert_not_called()
        
        # Scroll is at 90% (90/100) — should trigger loading
        MainWindow._favorites_scroll_changed(window, 90)
        window._load_more_favorites.assert_called_once()
