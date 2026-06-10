from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from r34_client.core.models import Post
from r34_client.ui.friends.controller import _hydrate_posts_from_api, _fetch_friend_favorites_impl, _fetch_page, _hydrate_cached_slice_impl, _trigger_background_prehydration, _prehydrate_remaining_impl, _friend_prehydrate_finished


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
        
        _fetch_friend_favorites_impl(client, "123", "http://solver", page=5)
        
        # Verify that favorites_view_url was called with page=50 (1 * 50)
        mock_fav_url.assert_called_once_with("123", page=50)

    @patch("r34_client.ui.friends.controller._hydrate_posts_from_api")
    def test_hydrate_cached_slice_impl(self, mock_hydrate: MagicMock) -> None:
        client = MagicMock()
        posts = [Post.from_payload({"id": 100 + i}) for i in range(50)]
        
        res = _hydrate_cached_slice_impl(client, posts, page=2)
        
        # Since page=2, slice starts at (2%5)*10 = 20, limit=10
        mock_hydrate.assert_called_once()
        args, kwargs = mock_hydrate.call_args
        self.assertEqual(kwargs.get("start"), 20)
        self.assertEqual(kwargs.get("limit"), 10)
        # Verify that the original posts list wasn't modified directly (it returns a copy)
        self.assertIsNot(res, posts)

    @patch("requests.get")
    def test_fetch_page_direct(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.text = "direct response"
        mock_get.return_value = mock_resp
        
        res = _fetch_page("https://example.test", flare_solver_url="")
        
        self.assertEqual(res, "direct response")
        mock_get.assert_called_once_with("https://example.test", headers=unittest.mock.ANY, timeout=15)

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

    def test_prehydrate_remaining_impl(self) -> None:
        client = MagicMock()
        posts = [
            Post.from_payload({"id": 101, "file_url": "https://ex.com/101.jpg"}),
            Post.from_payload({"id": 102, "file_url": ""}),
        ]
        
        hydrated_post_102 = Post.from_payload({"id": 102, "file_url": "https://ex.com/102.jpg"})
        client.search_posts.return_value = [hydrated_post_102]
        
        res = _prehydrate_remaining_impl(client, posts)
        
        client.search_posts.assert_called_once_with("id:102", 0, 1)
        self.assertEqual(res[1].file_url, "https://ex.com/102.jpg")
        # Post 101 wasn't hydrated again since it was already hydrated
        self.assertEqual(client.search_posts.call_count, 1)

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
