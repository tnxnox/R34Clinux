from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from r34_client.core.models import Post
from r34_client.ui.friends.controller import _hydrate_posts_from_api, _fetch_friend_favorites_impl, _fetch_page


class FriendsControllerTests(unittest.TestCase):
    def test_hydrate_posts_from_api_success(self) -> None:
        # Create a mock client
        client = MagicMock()
        
        # Create a list of posts
        posts = [
            Post.from_payload({"id": 101, "file_url": ""}),
            Post.from_payload({"id": 102, "file_url": ""}),
        ]
        
        # When search_posts is called, return hydrated posts
        hydrated_post_101 = Post.from_payload({"id": 101, "file_url": "https://ex.com/101.jpg", "score": "10", "tags": "a"})
        hydrated_post_102 = Post.from_payload({"id": 102, "file_url": "https://ex.com/102.jpg", "score": "20", "tags": "b"})
        
        def mock_search(query: str, page: int, limit: int) -> list[Post]:
            if "101" in query:
                return [hydrated_post_101]
            if "102" in query:
                return [hydrated_post_102]
            return []
            
        client.search_posts.side_effect = mock_search
        
        _hydrate_posts_from_api(client, posts, limit=2)
        
        # The posts should be hydrated in place
        self.assertEqual(posts[0].file_url, "https://ex.com/101.jpg")
        self.assertEqual(posts[1].file_url, "https://ex.com/102.jpg")
        self.assertEqual(client.search_posts.call_count, 2)

    def test_hydrate_posts_from_api_partial_failure(self) -> None:
        client = MagicMock()
        
        posts = [
            Post.from_payload({"id": 101, "file_url": ""}),
            Post.from_payload({"id": 102, "file_url": ""}),
        ]
        
        hydrated_post_102 = Post.from_payload({"id": 102, "file_url": "https://ex.com/102.jpg", "score": "20", "tags": "b"})
        
        def mock_search(query: str, page: int, limit: int) -> list[Post]:
            if "101" in query:
                raise RuntimeError("API failure")
            if "102" in query:
                return [hydrated_post_102]
            return []
            
        client.search_posts.side_effect = mock_search
        
        _hydrate_posts_from_api(client, posts, limit=2)
        
        # Post 101 should remain unhydrated, Post 102 should be hydrated
        self.assertEqual(posts[0].file_url, "")
        self.assertEqual(posts[1].file_url, "https://ex.com/102.jpg")

    @patch("r34_client.ui.friends.controller.favorites_view_url")
    @patch("r34_client.ui.friends.controller._fetch_page")
    @patch("r34_client.ui.friends.controller._hydrate_posts_from_api")
    def test_fetch_friend_favorites_impl_offset(self, mock_hydrate: MagicMock, mock_fetch_page: MagicMock, mock_fav_url: MagicMock) -> None:
        client = MagicMock()
        mock_fetch_page.return_value = "<html></html>"
        mock_fav_url.return_value = "https://example.test"
        
        _fetch_friend_favorites_impl(client, "123", "http://solver", page=2)
        
        # Verify that favorites_view_url was called with page=100 (2 * 50)
        mock_fav_url.assert_called_once_with("123", page=100)

    @patch("requests.get")
    def test_fetch_page_direct(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.text = "direct response"
        mock_get.return_value = mock_resp
        
        res = _fetch_page("https://example.test", flare_solver_url="")
        
        self.assertEqual(res, "direct response")
        mock_get.assert_called_once_with("https://example.test", headers=unittest.mock.ANY, timeout=15)
