from __future__ import annotations

import unittest
from r34_client.core.state import AppState
from r34_client.core.models import Post


class TestAppState(unittest.TestCase):
    def setUp(self) -> None:
        self.state = AppState()

    def test_search_completed_signal(self) -> None:
        received_posts: list[Post] = []

        def handle_search_completed(posts: list[Post]) -> None:
            received_posts.extend(posts)

        self.state.search_completed.connect(handle_search_completed)

        posts = [
            Post(
                id=1,
                tags=[],
                rating="safe",
                score=10,
                width=100,
                height=100,
                file_size=1024,
                source="",
                md5="",
                preview_url="",
                sample_url="",
                file_url="",
                created_at="",
            )
        ]
        self.state.current_posts = posts

        self.assertEqual(len(received_posts), 1)
        self.assertEqual(received_posts[0].id, 1)

    def test_favorites_updated_signal(self) -> None:
        received_posts: list[Post] = []

        def handle_favorites(posts: list[Post]) -> None:
            received_posts.extend(posts)

        self.state.favorites_updated.connect(handle_favorites)

        posts = [
            Post(
                id=2,
                tags=[],
                rating="explicit",
                score=5,
                width=200,
                height=200,
                file_size=2048,
                source="",
                md5="",
                preview_url="",
                sample_url="",
                file_url="",
                created_at="",
            )
        ]
        self.state.favorite_posts = posts

        self.assertEqual(len(received_posts), 1)
        self.assertEqual(received_posts[0].id, 2)
        self.assertEqual(self.state.favorite_ids, {2})

    def test_friend_favorites_updated_signal(self) -> None:
        received_posts: list[Post] = []

        def handle_friend_posts(posts: list[Post]) -> None:
            received_posts.extend(posts)

        self.state.friend_favorites_updated.connect(handle_friend_posts)

        posts = [
            Post(
                id=3,
                tags=[],
                rating="questionable",
                score=1,
                width=300,
                height=300,
                file_size=512,
                source="",
                md5="",
                preview_url="",
                sample_url="",
                file_url="",
                created_at="",
            )
        ]
        self.state.friend_posts = posts

        self.assertEqual(len(received_posts), 1)
        self.assertEqual(received_posts[0].id, 3)

    def test_page_changed_signal(self) -> None:
        pages: list[int] = []

        def handle_page(page: int) -> None:
            pages.append(page)

        self.state.page_changed.connect(handle_page)

        self.state.current_page = 5

        self.assertEqual(pages, [5])

    def test_query_changed_signal(self) -> None:
        queries: list[str] = []

        def handle_query(query: str) -> None:
            queries.append(query)

        self.state.query_changed.connect(handle_query)

        self.state.current_query = "rating:safe"

        self.assertEqual(queries, ["rating:safe"])
