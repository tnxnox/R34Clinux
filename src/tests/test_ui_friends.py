from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from r34_client.core.models import Post
from r34_client.ui.friends.controller import (
    _fetch_friend_favorites_impl,
    _hydrate_cached_slice_impl,
    _trigger_background_prehydration,
    _prehydrate_remaining_impl,
    _friend_prehydrate_finished,
)


class FriendsControllerTests(unittest.TestCase):
    @patch("r34_client.ui.friends.controller.fetch_friend_favorites")
    @patch("r34_client.ui.friends.controller.hydrate_posts")
    def test_fetch_friend_favorites_impl(
        self, mock_hydrate: MagicMock, mock_fetch: MagicMock
    ) -> None:
        client = MagicMock()
        mock_fetch.return_value = [Post.from_payload({"id": 101})]
        
        res = _fetch_friend_favorites_impl(client, "123", "http://solver", page=5)
        
        mock_fetch.assert_called_once_with(client, "123", "http://solver", 5)
        mock_hydrate.assert_called_once_with(client, mock_fetch.return_value, start=0, limit=10)
        self.assertEqual(res, mock_fetch.return_value)

    @patch("r34_client.ui.friends.controller.hydrate_posts_copy")
    def test_hydrate_cached_slice_impl(self, mock_hydrate_copy: MagicMock) -> None:
        client = MagicMock()
        posts = [Post.from_payload({"id": 100 + i}) for i in range(50)]
        mock_hydrate_copy.return_value = list(posts)
        
        res = _hydrate_cached_slice_impl(client, posts, page=2)
        
        # Since page=2, slice starts at (2%5)*10 = 20, limit=10
        mock_hydrate_copy.assert_called_once_with(client, posts, start=20, limit=10)
        self.assertEqual(res, posts)

    @patch("r34_client.ui.friends.controller.FunctionWorker")
    def test_trigger_background_prehydration(self, mock_worker: MagicMock) -> None:
        window = MagicMock()
        # Post 0 is hydrated, Post 1 is not
        window._friend_cached_posts = [
            Post.from_payload({"id": 101, "file_url": "https://ex.com/101.jpg"}),
            Post.from_payload({"id": 102, "file_url": ""}),
        ]
        
        _trigger_background_prehydration(window, token=42)
        
        mock_worker.assert_called_once()
        window._start_worker.assert_called_once()

    @patch("r34_client.ui.friends.controller.hydrate_posts_copy")
    def test_prehydrate_remaining_impl(self, mock_hydrate_copy: MagicMock) -> None:
        client = MagicMock()
        posts = [
            Post.from_payload({"id": 101, "file_url": "https://ex.com/101.jpg"}),
            Post.from_payload({"id": 102, "file_url": ""}),
        ]
        mock_hydrate_copy.return_value = list(posts)
        
        res = _prehydrate_remaining_impl(client, posts)
        
        mock_hydrate_copy.assert_called_once_with(client, posts)
        self.assertEqual(res, posts)

    def test_friend_prehydrate_finished(self) -> None:
        window = MagicMock()
        window._friend_fetch_token = 42
        window._friend_cached_posts = []
        
        # Token mismatch - should be ignored
        _friend_prehydrate_finished(window, token=99, result=[Post.from_payload({"id": 101})])
        self.assertEqual(len(window._friend_cached_posts), 0)
        
        # Token matches - should update
        _friend_prehydrate_finished(window, token=42, result=[Post.from_payload({"id": 102})])
        self.assertEqual(len(window._friend_cached_posts), 1)
        self.assertEqual(window._friend_cached_posts[0].id, 102)
