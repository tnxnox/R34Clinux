from __future__ import annotations

import unittest

from r34_client.config import AppSettings
from r34_client.flaresolverr_client import FlareSolverrError
from r34_client.models import Post
from r34_client.ui.sync.favorites_sync import sync_remote_favorites


class _LocalFavoritesStub:
    def __init__(self, posts: list[Post]) -> None:
        self._posts = list(posts)

    def list_favorites(self) -> list[Post]:
        return list(self._posts)

    def replace_all(self, posts: list[Post]) -> None:
        self._posts = list(posts)


class _SyncClientStub:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)

    def list_favorites(self, limit: int) -> list[Post]:
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
        sync_client = _SyncClientStub([FlareSolverrError("boom"), []])
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
        self.assertEqual(errors, ["boom"])

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
