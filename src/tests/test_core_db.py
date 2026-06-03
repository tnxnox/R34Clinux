from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from r34_client.core.db import LocalFavoritesStore
from r34_client.core.models import Post


class LocalFavoritesStoreTests(unittest.TestCase):
    def test_add_list_remove_favorite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "favorites.db"
            store = LocalFavoritesStore(database_path=db_path)

            post = Post.from_payload(
                {
                    "id": 123,
                    "tags": "tag_a tag_b",
                    "rating": "s",
                    "score": 10,
                    "preview_url": "https://img.example/preview.jpg",
                    "sample_url": "https://img.example/sample.jpg",
                    "file_url": "https://img.example/file.jpg",
                }
            )

            store.add_favorite(post)
            listed = store.list_favorites()

            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0].id, post.id)
            self.assertEqual(listed[0].tags_text, "tag_a tag_b")

            store.remove_favorite(post.id)
            self.assertEqual(store.list_favorites(), [])

    def test_replace_all_mirrors_remote_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "favorites.db"
            store = LocalFavoritesStore(database_path=db_path)

            first = Post.from_payload({"id": 1, "tags": "a", "rating": "s"})
            second = Post.from_payload({"id": 2, "tags": "b", "rating": "q"})
            third = Post.from_payload({"id": 3, "tags": "c", "rating": "e"})

            store.add_favorite(first)
            store.add_favorite(second)

            store.replace_all([third])
            listed = store.list_favorites()

            self.assertEqual([item.id for item in listed], [3])

    def test_collections_assign_and_filter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "favorites.db"
            store = LocalFavoritesStore(database_path=db_path)

            first = Post.from_payload({"id": 1, "tags": "a", "rating": "s"})
            second = Post.from_payload({"id": 2, "tags": "b", "rating": "q"})
            store.add_favorite(first)
            store.add_favorite(second)

            assigned = store.assign_posts_to_collection([1, 2], "Artists")
            self.assertEqual(assigned, 2)
            self.assertEqual(store.list_collections(), ["Artists"])

            filtered = store.list_favorites(collection_name="Artists")
            self.assertEqual({post.id for post in filtered}, {1, 2})

            removed = store.remove_posts_from_collection([2], "Artists")
            self.assertEqual(removed, 1)
            filtered_after = store.list_favorites(collection_name="Artists")
            self.assertEqual([post.id for post in filtered_after], [1])

    def test_add_list_remove_friend(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "friends.db"
            store = LocalFavoritesStore(database_path=db_path)

            store.add_friend("123", "Alice", "my friend")
            friends = store.list_friends()
            self.assertEqual(len(friends), 1)
            self.assertEqual(friends[0]["user_id"], "123")
            self.assertEqual(friends[0]["display_name"], "Alice")
            self.assertEqual(friends[0]["notes"], "my friend")

            got = store.get_friend("123")
            self.assertIsNotNone(got)
            self.assertEqual(got["display_name"], "Alice")

            store.remove_friend("123")
            self.assertEqual(store.list_friends(), [])
            self.assertIsNone(store.get_friend("123"))

    def test_add_friend_deduplicates_by_user_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "friends.db"
            store = LocalFavoritesStore(database_path=db_path)

            store.add_friend("123", "Alice")
            store.add_friend("123", "Bob")
            friends = store.list_friends()
            self.assertEqual(len(friends), 1)
            self.assertEqual(friends[0]["display_name"], "Bob")

    def test_list_friends_sorted_by_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "friends.db"
            store = LocalFavoritesStore(database_path=db_path)

            store.add_friend("2", "Zoe")
            store.add_friend("1", "Alice")
            store.add_friend("3", "bob")
            names = [f["display_name"] for f in store.list_friends()]
            self.assertEqual(names, ["Alice", "bob", "Zoe"])

    def test_get_friend_returns_none_for_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "friends.db"
            store = LocalFavoritesStore(database_path=db_path)
            self.assertIsNone(store.get_friend("999"))

    def test_replace_all_preserves_collection_for_kept_posts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "favorites.db"
            store = LocalFavoritesStore(database_path=db_path)

            first = Post.from_payload({"id": 10, "tags": "a", "rating": "s"})
            second = Post.from_payload({"id": 20, "tags": "b", "rating": "q"})
            store.add_favorite(first)
            store.add_favorite(second)
            store.assign_posts_to_collection([10, 20], "Keep")

            refreshed = [
                Post.from_payload({"id": 10, "tags": "a2", "rating": "s"}),
                Post.from_payload({"id": 30, "tags": "c", "rating": "e"}),
            ]
            store.replace_all(refreshed)

            keep_collection = store.list_favorites(collection_name="Keep")
            self.assertEqual([post.id for post in keep_collection], [10])
