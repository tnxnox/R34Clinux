from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from r34_client.core.models import Post
from r34_client.core.settings import AppSettings
from r34_client.sync.favorites_sync import sync_remote_favorites


class SyncFavoritesTests(unittest.TestCase):
    def _make_settings(self, strategy: str = "merge") -> AppSettings:
        return AppSettings(
            user_id="1",
            api_key="secret",
            page_size=200,
            sync_conflict_strategy=strategy,
        )

    def _make_post(self, post_id: int) -> Post:
        return Post.from_payload({"id": post_id, "tags": f"tag_{post_id}", "rating": "s"})

    def test_no_sync_client_returns_local(self) -> None:
        local_favs = MagicMock()
        local_favs.list_favorites.return_value = []
        posts, changed = sync_remote_favorites(
            settings=self._make_settings(),
            local_favorites=local_favs,
            make_sync_client=lambda s: None,
            log_sync_debug=lambda a, b: None,
        )
        self.assertEqual(posts, [])
        self.assertFalse(changed)

    def test_remote_fetch_success_merge_strategy(self) -> None:
        local_posts = [self._make_post(1), self._make_post(2)]
        local_favs = MagicMock()
        local_favs.list_favorites.return_value = local_posts
        sync_client = MagicMock()
        sync_client.list_favorites.return_value = local_posts
        sync_client.debug_summary.return_value = ""

        posts, changed = sync_remote_favorites(
            settings=self._make_settings("merge"),
            local_favorites=local_favs,
            make_sync_client=lambda s: sync_client,
            log_sync_debug=lambda a, b: None,
        )
        self.assertEqual(len(posts), 2)
        self.assertFalse(changed)
        local_favs.replace_all.assert_called_once()

    def test_remote_fetch_failure_returns_local_cache(self) -> None:
        from r34_client.api.flaresolverr import FlareSolverrError

        cached = [self._make_post(1)]
        local_favs = MagicMock()
        local_favs.list_favorites.return_value = cached
        sync_client = MagicMock()
        sync_client.list_favorites.side_effect = FlareSolverrError("network error")
        sync_client.debug_summary.return_value = ""

        posts, changed = sync_remote_favorites(
            settings=self._make_settings(),
            local_favorites=local_favs,
            make_sync_client=lambda s: sync_client,
            log_sync_debug=lambda a, b: None,
        )
        self.assertEqual(posts, cached)
        self.assertTrue(changed)

    def test_remote_wins_strategy(self) -> None:
        local_favs = MagicMock()
        local_favs.list_favorites.return_value = [self._make_post(1)]
        sync_client = MagicMock()
        sync_client.list_favorites.return_value = [self._make_post(1)]
        sync_client.debug_summary.return_value = ""

        sync_remote_favorites(
            settings=self._make_settings("remote_wins"),
            local_favorites=local_favs,
            make_sync_client=lambda s: sync_client,
            log_sync_debug=lambda a, b: None,
        )
        local_favs.replace_all.assert_called_once()

    def test_local_wins_strategy_keeps_cache(self) -> None:
        cached = [self._make_post(1)]
        local_favs = MagicMock()
        local_favs.list_favorites.return_value = cached
        sync_client = MagicMock()
        sync_client.list_favorites.return_value = [self._make_post(2)]
        sync_client.debug_summary.return_value = ""

        posts, changed = sync_remote_favorites(
            settings=self._make_settings("local_wins"),
            local_favorites=local_favs,
            make_sync_client=lambda s: sync_client,
            log_sync_debug=lambda a, b: None,
        )
        self.assertEqual(posts, cached)
        self.assertTrue(changed)

    def test_empty_remote_merge_with_pending_ids(self) -> None:
        local_favs = MagicMock()
        local_favs.list_favorites.return_value = [self._make_post(1)]
        sync_client = MagicMock()
        sync_client.list_favorites.return_value = []
        sync_client.debug_summary.return_value = ""

        sync_remote_favorites(
            settings=self._make_settings("merge"),
            local_favorites=local_favs,
            make_sync_client=lambda s: sync_client,
            log_sync_debug=lambda a, b: None,
            pending_remote_add_ids={1, 2},
        )
        local_favs.replace_all.assert_called_once()
