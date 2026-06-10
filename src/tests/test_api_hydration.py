from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from r34_client.core.models import Post
from r34_client.api.hydration import hydrate_posts, hydrate_posts_copy


class HydrationTests(unittest.TestCase):
    def test_hydrate_posts_success(self) -> None:
        client = MagicMock()
        posts = [
            Post.from_payload({"id": 101, "file_url": ""}),
            Post.from_payload({"id": 102, "file_url": ""}),
        ]
        
        hydrated_post_101 = Post.from_payload({"id": 101, "file_url": "https://ex.com/101.jpg", "score": "10", "tags": "a"})
        hydrated_post_102 = Post.from_payload({"id": 102, "file_url": "https://ex.com/102.jpg", "score": "20", "tags": "b"})
        
        def mock_search(query: str, page: int, limit: int) -> list[Post]:
            if "101" in query:
                return [hydrated_post_101]
            if "102" in query:
                return [hydrated_post_102]
            return []
            
        client.search_posts.side_effect = mock_search
        
        hydrate_posts(client, posts, limit=2)
        
        self.assertEqual(posts[0].file_url, "https://ex.com/101.jpg")
        self.assertEqual(posts[1].file_url, "https://ex.com/102.jpg")
        self.assertEqual(client.search_posts.call_count, 2)

    def test_hydrate_posts_partial_failure(self) -> None:
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
        
        hydrate_posts(client, posts, limit=2)
        
        self.assertEqual(posts[0].file_url, "")
        self.assertEqual(posts[1].file_url, "https://ex.com/102.jpg")

    def test_hydrate_posts_copy(self) -> None:
        client = MagicMock()
        posts = [
            Post.from_payload({"id": 101, "file_url": ""}),
        ]
        hydrated_post = Post.from_payload({"id": 101, "file_url": "https://ex.com/101.jpg"})
        client.search_posts.return_value = [hydrated_post]
        
        res = hydrate_posts_copy(client, posts)
        
        self.assertIsNot(res, posts)
        self.assertEqual(res[0].file_url, "https://ex.com/101.jpg")
        self.assertEqual(posts[0].file_url, "")
