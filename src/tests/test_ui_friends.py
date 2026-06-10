from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from r34_client.core.models import Post
from r34_client.ui.friends.controller import _hydrate_posts_from_api


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
