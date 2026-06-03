from __future__ import annotations

import unittest
from unittest.mock import patch

from r34_client.core.models import Post
from r34_client.ui.helpers.post import (
    is_video_post,
    format_millis,
    needs_hydration,
    format_post_metadata,
    format_post_tile,
    download_url_needs_hydration,
    probe_file_size,
)


class IsVideoPostTests(unittest.TestCase):
    def _make_post(self, file_url: str = "", sample_url: str = "", preview_url: str = "") -> Post:
        return Post.from_payload({
            "id": 1,
            "file_url": file_url,
            "sample_url": sample_url,
            "preview_url": preview_url,
        })

    def test_detects_webm(self) -> None:
        self.assertTrue(is_video_post(self._make_post(file_url="https://ex.com/video.webm")))

    def test_detects_mp4(self) -> None:
        self.assertTrue(is_video_post(self._make_post(file_url="https://ex.com/video.mp4")))

    def test_detects_mov(self) -> None:
        self.assertTrue(is_video_post(self._make_post(sample_url="https://ex.com/clip.mov")))

    def test_detects_mkv(self) -> None:
        self.assertTrue(is_video_post(self._make_post(preview_url="https://ex.com/thumb.mkv")))

    def test_image_is_not_video(self) -> None:
        self.assertFalse(is_video_post(self._make_post(file_url="https://ex.com/image.jpg")))

    def test_no_urls_returns_false(self) -> None:
        self.assertFalse(is_video_post(self._make_post()))


class FormatMillisTests(unittest.TestCase):
    def test_seconds_only(self) -> None:
        self.assertEqual(format_millis(45000), "00:45")

    def test_minutes_and_seconds(self) -> None:
        self.assertEqual(format_millis(125000), "02:05")

    def test_hours_minutes_seconds(self) -> None:
        self.assertEqual(format_millis(3661000), "01:01:01")

    def test_zero(self) -> None:
        self.assertEqual(format_millis(0), "00:00")

    def test_negative_clamped_to_zero(self) -> None:
        self.assertEqual(format_millis(-1000), "00:00")


class NeedsHydrationTests(unittest.TestCase):
    def test_hydrated_post_does_not_need_hydration(self) -> None:
        post = Post.from_payload({
            "id": 1, "score": "100", "file_size": "1024", "source": "src",
            "file_url": "https://ex.com/f.jpg", "tags": "a b",
        })
        self.assertFalse(needs_hydration(post, {1}))

    def test_incomplete_post_needs_hydration(self) -> None:
        post = Post.from_payload({"id": 1, "file_url": ""})
        self.assertTrue(needs_hydration(post, set()))

    def test_hydrated_ids_overrides_check(self) -> None:
        post = Post.from_payload({
            "id": 1, "score": "100", "file_size": "1024", "source": "src",
            "file_url": "https://ex.com/f.jpg", "tags": "a b",
        })
        self.assertFalse(needs_hydration(post, {1}))

    def test_not_in_hydrated_ids_but_fully_loaded(self) -> None:
        post = Post.from_payload({
            "id": 2, "score": "100", "file_size": "1024", "source": "src",
            "file_url": "https://ex.com/f.jpg", "tags": "a b",
        })
        self.assertFalse(needs_hydration(post, {1}))


class FormatPostMetadataTests(unittest.TestCase):
    def test_metadata_contains_core_info(self) -> None:
        post = Post.from_payload({"id": 42, "rating": "s", "tags": "a", "file_url": "https://ex.com/f.jpg"})
        metadata = format_post_metadata(post)
        self.assertIn("ID: 42", metadata)
        self.assertIn("Rating: s", metadata)
        self.assertIn("Tags:", metadata)

    def test_metadata_with_none_values(self) -> None:
        post = Post.from_payload({"id": 1})
        metadata = format_post_metadata(post)
        self.assertIn("n/a", metadata)


class FormatPostTileTests(unittest.TestCase):
    def test_tile_format(self) -> None:
        post = Post.from_payload({"id": 1, "rating": "s", "score": "50"})
        tile = format_post_tile(post)
        self.assertEqual(tile, "#1  s  score:50")

    def test_tile_with_none_score(self) -> None:
        post = Post.from_payload({"id": 1, "rating": "q"})
        tile = format_post_tile(post)
        self.assertIn("n/a", tile)


class DownloadUrlNeedsHydrationTests(unittest.TestCase):
    def test_needs_hydration_for_thumbnail_path(self) -> None:
        self.assertTrue(download_url_needs_hydration("https://ex.com/thumbnails/1.jpg"))

    def test_needs_hydration_for_thumbnail_prefix(self) -> None:
        self.assertTrue(download_url_needs_hydration("https://ex.com/thumbnail_1.jpg"))

    def test_no_hydration_for_direct_image(self) -> None:
        self.assertFalse(download_url_needs_hydration("https://ex.com/images/1.jpg"))

    def test_empty_url_needs_hydration(self) -> None:
        self.assertTrue(download_url_needs_hydration(""))

    def test_none_url_needs_hydration(self) -> None:
        self.assertTrue(download_url_needs_hydration(""))


class ProbeFileSizeTests(unittest.TestCase):
    def test_head_request_returns_content_length(self) -> None:
        mock_head = unittest.mock.MagicMock()
        mock_head.ok = True
        mock_head.headers = {"Content-Length": "5000"}

        with patch("r34_client.ui.helpers.post._HTTP.head", return_value=mock_head):
            size = probe_file_size("https://ex.com/file.jpg", "https://ex.com/")
            self.assertEqual(size, 5000)

    def test_head_failure_falls_back_to_range_request(self) -> None:
        mock_head = unittest.mock.MagicMock()
        mock_head.ok = False

        mock_range = unittest.mock.MagicMock()
        mock_range.status_code = 206
        mock_range.headers = {"Content-Range": "bytes 0-0/8000"}

        with patch("r34_client.ui.helpers.post._HTTP.head", return_value=mock_head):
            with patch("r34_client.ui.helpers.post._HTTP.get", return_value=mock_range):
                size = probe_file_size("https://ex.com/file.jpg", "https://ex.com/")
                self.assertEqual(size, 8000)

    def test_both_fail_returns_none(self) -> None:
        with patch("r34_client.ui.helpers.post._HTTP.head", side_effect=RuntimeError("fail")):
            with patch("r34_client.ui.helpers.post._HTTP.get", side_effect=RuntimeError("fail")):
                size = probe_file_size("https://ex.com/file.jpg", "https://ex.com/")
                self.assertIsNone(size)
