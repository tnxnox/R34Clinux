from __future__ import annotations

import unittest

from r34_client.core.settings import AppSettings
from r34_client.api.flaresolverr import FlareSolverrError
from r34_client.core.models import Post
from r34_client.sync.favorites_sync import sync_remote_favorites


class _LocalFavoritesStub:
    def __init__(self, posts: list[Post]) -> None:
        self._posts = list(posts)

    def list_favorites(self) -> list[Post]:
        return list(self._posts)

    def replace_all(self, posts: list[Post]) -> None:
        self._posts = list(posts)

    def upsert_many(self, posts: list[Post]) -> None:
        new_posts = {p.id: p for p in posts}
        updated = []
        seen = set()
        for p in self._posts:
            if p.id in new_posts:
                updated.append(new_posts[p.id])
                seen.add(p.id)
            else:
                updated.append(p)
        for p in posts:
            if p.id not in seen:
                updated.append(p)
        self._posts = updated


class _SyncClientStub:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def list_favorites(self, limit: int) -> list[Post]:
        self.calls += 1
        current = self._responses.pop(0)
        if isinstance(current, Exception):
            raise current
        return list(current)

    def debug_summary(self) -> str:
        return "stub-trace"


class FavoritesSyncTests(unittest.TestCase):
    def _settings(self) -> AppSettings:
        return AppSettings(
            user_id="1",
            api_key="secret",
            page_size=50,
            flaresolverr_enabled=True,
            flaresolverr_url="http://127.0.0.1:8191",
        )

    def _post(self, post_id: int, preview: str = "") -> Post:
        return Post.from_payload(
            {
                "id": str(post_id),
                "tags": "x",
                "rating": "s",
                "score": "1",
                "preview_url": preview,
                "sample_url": preview,
                "file_url": preview,
            }
        )

    def test_sync_falls_back_to_local_and_logs(self) -> None:
        local = _LocalFavoritesStub([self._post(10)])
        sync_client = _SyncClientStub([FlareSolverrError("boom"), FlareSolverrError("boom-again")])
        logs: list[tuple[str, str]] = []
        errors: list[str] = []

        def make_sync_client(_: AppSettings):
            return sync_client

        result, used_fallback = sync_remote_favorites(
            settings=self._settings(),
            local_favorites=local,
            make_sync_client=make_sync_client,
            log_sync_debug=lambda title, details: logs.append((title, details)),
            on_sync_error=lambda message: errors.append(message),
        )

        self.assertTrue(used_fallback)
        self.assertEqual([p.id for p in result], [10])
        self.assertEqual(logs[0][0], "Favorites sync fallback to local cache")
        self.assertIn("attempt=1 error=boom", logs[0][1])
        self.assertIn("attempt=2 error=boom-again", logs[0][1])
        self.assertEqual(errors, ["boom", "boom-again"])

    def test_sync_empty_remote_is_not_fallback(self) -> None:
        local = _LocalFavoritesStub([self._post(10)])
        sync_client = _SyncClientStub([[]])
        logs: list[tuple[str, str]] = []

        result, used_fallback = sync_remote_favorites(
            settings=self._settings(),
            local_favorites=local,
            make_sync_client=lambda _: sync_client,
            log_sync_debug=lambda title, details: logs.append((title, details)),
        )

        self.assertFalse(used_fallback)
        self.assertEqual([p.id for p in result], [])
        self.assertEqual(sync_client.calls, 1)
        self.assertEqual(logs[0][0], "Favorites sync remote empty")

    def test_sync_empty_remote_local_wins_keeps_cache(self) -> None:
        local = _LocalFavoritesStub([self._post(10)])
        sync_client = _SyncClientStub([[]])
        logs: list[tuple[str, str]] = []
        settings = self._settings()
        settings.sync_conflict_strategy = "local_wins"

        result, used_fallback = sync_remote_favorites(
            settings=settings,
            local_favorites=local,
            make_sync_client=lambda _: sync_client,
            log_sync_debug=lambda title, details: logs.append((title, details)),
        )

        self.assertFalse(used_fallback)
        self.assertEqual([p.id for p in result], [10])
        self.assertEqual(sync_client.calls, 1)
        self.assertEqual(logs[0][0], "Favorites sync remote empty (local_wins)")

    def test_sync_empty_remote_merge_preserves_pending_deferred_adds(self) -> None:
        local = _LocalFavoritesStub([self._post(10), self._post(20)])
        sync_client = _SyncClientStub([[]])
        logs: list[tuple[str, str]] = []
        pending = {20}

        result, used_fallback = sync_remote_favorites(
            settings=self._settings(),
            local_favorites=local,
            make_sync_client=lambda _: sync_client,
            log_sync_debug=lambda title, details: logs.append((title, details)),
            pending_remote_add_ids=pending,
        )

        self.assertFalse(used_fallback)
        self.assertEqual([p.id for p in result], [20])
        self.assertEqual(logs[0][0], "Favorites sync remote empty")

    def test_sync_merge_preserves_pending_deferred_add_missing_from_remote(self) -> None:
        local = _LocalFavoritesStub([self._post(10), self._post(20)])
        sync_client = _SyncClientStub([[self._post(10)]])
        pending = {20}

        result, used_fallback = sync_remote_favorites(
            settings=self._settings(),
            local_favorites=local,
            make_sync_client=lambda _: sync_client,
            log_sync_debug=lambda *_: None,
            pending_remote_add_ids=pending,
        )

        self.assertFalse(used_fallback)
        self.assertEqual([p.id for p in result], [10, 20])

    def test_sync_merge_clears_pending_id_once_remote_contains_it(self) -> None:
        local = _LocalFavoritesStub([self._post(10), self._post(20)])
        sync_client = _SyncClientStub([[self._post(10), self._post(20)]])
        pending = {20}

        result, used_fallback = sync_remote_favorites(
            settings=self._settings(),
            local_favorites=local,
            make_sync_client=lambda _: sync_client,
            log_sync_debug=lambda *_: None,
            pending_remote_add_ids=pending,
        )

        self.assertFalse(used_fallback)
        self.assertEqual([p.id for p in result], [10, 20])
        self.assertEqual(pending, set())

    def test_sync_merges_remote_with_local_metadata(self) -> None:
        local_post = self._post(10, preview="https://local/p.jpg")
        remote_post = Post.from_payload({"id": "10", "tags": "", "rating": "", "preview_url": ""})
        local = _LocalFavoritesStub([local_post])
        sync_client = _SyncClientStub([[remote_post]])

        def make_sync_client(_: AppSettings):
            return sync_client

        result, used_fallback = sync_remote_favorites(
            settings=self._settings(),
            local_favorites=local,
            make_sync_client=make_sync_client,
            log_sync_debug=lambda *_: None,
        )

        self.assertFalse(used_fallback)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, 10)
        self.assertEqual(result[0].preview_url, "https://local/p.jpg")

    def test_sync_local_wins_keeps_cache(self) -> None:
        local_post = self._post(10, preview="https://local/p.jpg")
        remote_post = self._post(20, preview="https://remote/p.jpg")
        local = _LocalFavoritesStub([local_post])
        sync_client = _SyncClientStub([[remote_post]])

        settings = self._settings()
        settings.sync_conflict_strategy = "local_wins"

        result, used_fallback = sync_remote_favorites(
            settings=settings,
            local_favorites=local,
            make_sync_client=lambda _: sync_client,
            log_sync_debug=lambda *_: None,
        )

        self.assertTrue(used_fallback)
        self.assertEqual([item.id for item in result], [10])

    def test_sync_remote_wins_overwrites_cache(self) -> None:
        local_post = self._post(10, preview="https://local/p.jpg")
        remote_post = self._post(20, preview="https://remote/p.jpg")
        local = _LocalFavoritesStub([local_post])
        sync_client = _SyncClientStub([[remote_post]])

        settings = self._settings()
        settings.sync_conflict_strategy = "remote_wins"

        result, used_fallback = sync_remote_favorites(
            settings=settings,
            local_favorites=local,
            make_sync_client=lambda _: sync_client,
            log_sync_debug=lambda *_: None,
        )

        self.assertFalse(used_fallback)
        self.assertEqual([item.id for item in result], [20])


if __name__ == "__main__":
    unittest.main()
