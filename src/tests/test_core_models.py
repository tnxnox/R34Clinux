from __future__ import annotations

import unittest

from r34_client.core.models import Post, TagSuggestion


class ModelTests(unittest.TestCase):
    def test_post_uses_best_available_download_name(self) -> None:
        post = Post.from_payload(
            {
                "id": 7,
                "tags": "pokemon",
                "file_url": "https://example.test/files/image.png",
                "sample_url": "https://example.test/sample.jpg",
            }
        )

        self.assertEqual(post.file_name, "image.png")
        self.assertEqual(post.best_preview_url, "https://example.test/sample.jpg")

    def test_tag_suggestion_parses_count(self) -> None:
        suggestion = TagSuggestion.from_payload({"label": "pokemon (880615)", "value": "pokemon"})

        self.assertEqual(suggestion.value, "pokemon")
        self.assertEqual(suggestion.count, 880615)
        self.assertEqual(suggestion.display_text, "pokemon (880615)")

    def test_post_dimensions(self) -> None:
        post = Post.from_payload({"id": 1, "width": "1920", "height": "1080"})
        self.assertEqual(post.dimensions, "1920 x 1080")

    def test_post_dimensions_unknown(self) -> None:
        post = Post.from_payload({"id": 1})
        self.assertEqual(post.dimensions, "Unknown size")

    def test_post_page_url(self) -> None:
        post = Post.from_payload({"id": 42})
        self.assertIn("id=42", post.page_url)

    def test_post_download_url_fallback(self) -> None:
        post = Post.from_payload({"id": 1, "file_url": "https://ex.com/f.jpg"})
        self.assertEqual(post.download_url, "https://ex.com/f.jpg")

    def test_post_download_url_falls_back(self) -> None:
        post = Post.from_payload({"id": 1, "sample_url": "https://ex.com/s.jpg"})
        self.assertEqual(post.download_url, "https://ex.com/s.jpg")

    def test_merge_with_fills_missing_fields(self) -> None:
        local = Post.from_payload({"id": 1, "tags": "a", "rating": "s"})
        remote = Post.from_payload({"id": 1, "tags": "", "rating": "", "score": "100"})
        merged = local.merge_with(remote)
        self.assertEqual(merged.tags, ["a"])
        self.assertEqual(merged.rating, "s")
        self.assertEqual(merged.score, 100)

    def test_merge_with_prefers_remote(self) -> None:
        local = Post.from_payload({"id": 1, "tags": "old", "rating": "s"})
        remote = Post.from_payload({"id": 1, "tags": "new", "rating": "e"})
        merged = local.merge_with(remote)
        self.assertEqual(merged.tags, ["new"])
        self.assertEqual(merged.rating, "e")
