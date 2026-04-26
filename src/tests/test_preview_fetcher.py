from __future__ import annotations

import unittest
from unittest.mock import patch

from r34_client.core.models import Post
from r34_client.ui.helpers.preview_fetcher import fetch_preview_bytes, preview_candidate_urls


class _FakeHTTPResponse:
    def __init__(self, status_code: int, content: bytes = b"", text: str = "") -> None:
        self.status_code = status_code
        self.content = content
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class PreviewFetcherTests(unittest.TestCase):
    def _post(self) -> Post:
        return Post.from_payload(
            {
                "id": "123",
                "tags": "a b",
                "rating": "s",
                "preview_url": "https://wimg.rule34.xxx/thumbnails/a.jpg",
                "sample_url": "",
                "file_url": "",
            }
        )

    def test_preview_candidate_urls_include_host_fallback(self) -> None:
        post = self._post()
        urls = preview_candidate_urls(post)

        self.assertIn("https://wimg.rule34.xxx/thumbnails/a.jpg", urls)
        self.assertIn("https://img.rule34.xxx/thumbnails/a.jpg", urls)

    def test_preview_candidate_urls_prioritize_full_image_then_preview_then_sample(self) -> None:
        post = Post.from_payload(
            {
                "id": "456",
                "tags": "x",
                "rating": "s",
                "file_url": "https://full.test/file.jpg",
                "preview_url": "https://preview.test/preview.jpg",
                "sample_url": "https://sample.test/sample.jpg",
            }
        )
        urls = preview_candidate_urls(post)

        self.assertEqual(urls[0], "https://full.test/file.jpg")
        self.assertEqual(urls[1], "https://preview.test/preview.jpg")
        self.assertEqual(urls[2], "https://sample.test/sample.jpg")

    def test_fetch_preview_bytes_retries_after_403(self) -> None:
        post = self._post()
        calls: list[str] = []

        def fake_get(url: str, timeout: int, headers: dict[str, str]):
            calls.append(url)
            if len(calls) == 1:
                return _FakeHTTPResponse(403, text="forbidden")
            return _FakeHTTPResponse(200, content=b"image")

        with patch("r34_client.ui.helpers.preview_fetcher.requests.get", side_effect=fake_get):
            data = fetch_preview_bytes(post, user_id="42")

        self.assertEqual(data, b"image")
        self.assertGreaterEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
