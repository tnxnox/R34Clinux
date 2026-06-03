from __future__ import annotations

import unittest

from r34_client.core.models import Post
from r34_client.ui.search.related import build_related_tags


class SearchRelatedTests(unittest.TestCase):
    def test_build_related_tags_ranks_common_tags(self) -> None:
        posts = [
            Post(
                id=1,
                tags=["artist_a", "blue_hair", "solo"],
                rating="s",
                score=0,
                width=800,
                height=600,
                file_size=1024,
                source="",
                md5="",
                preview_url="",
                sample_url="",
                file_url="",
                created_at="",
            ),
            Post(
                id=2,
                tags=["artist_a", "blue_hair", "smile"],
                rating="s",
                score=0,
                width=800,
                height=600,
                file_size=1024,
                source="",
                md5="",
                preview_url="",
                sample_url="",
                file_url="",
                created_at="",
            ),
            Post(
                id=3,
                tags=["artist_b", "blue_hair", "smile"],
                rating="s",
                score=0,
                width=800,
                height=600,
                file_size=1024,
                source="",
                md5="",
                preview_url="",
                sample_url="",
                file_url="",
                created_at="",
            ),
        ]

        suggestions = build_related_tags(posts, "artist_a", limit=5)

        self.assertEqual([item.value for item in suggestions], ["blue_hair", "smile", "artist_b", "solo"])
        self.assertEqual(suggestions[0].count, 3)

    def test_build_related_tags_excludes_query_terms(self) -> None:
        posts = [
            Post(
                id=1,
                tags=["rating:safe", "blue_hair", "solo"],
                rating="s",
                score=0,
                width=800,
                height=600,
                file_size=1024,
                source="",
                md5="",
                preview_url="",
                sample_url="",
                file_url="",
                created_at="",
            )
        ]

        suggestions = build_related_tags(posts, "rating:safe", limit=5)

        self.assertNotIn("rating:safe", [item.value for item in suggestions])
        self.assertEqual([item.value for item in suggestions], ["blue_hair", "solo"])
