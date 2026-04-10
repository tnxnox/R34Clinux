from __future__ import annotations

import unittest

from r34_client.models import Post, TagSuggestion


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
