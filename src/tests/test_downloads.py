from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from r34_client.ui.features.downloads import resolve_download_post
from r34_client.core.models import Post


class DownloadsTests(unittest.TestCase):
    def test_resolve_download_post_returns_post_if_not_needs_hydration(self) -> None:
        post = Post.from_payload({
            "id": 123,
            "file_url": "https://img.rule34.xxx/images/123.jpg",
        })
        window = MagicMock()
        resolved = resolve_download_post(window, post)
        self.assertEqual(resolved, post)
        window.client.search_posts.assert_not_called()

    def test_resolve_download_post_hydrates_if_needed(self) -> None:
        post = Post.from_payload({
            "id": 123,
            "file_url": "https://img.rule34.xxx/thumbnails/123.jpg",
        })
        hydrated_post = Post.from_payload({
            "id": 123,
            "file_url": "https://img.rule34.xxx/images/123.jpg",
        })
        window = MagicMock()
        window.client.search_posts.return_value = [hydrated_post]
        
        resolved = resolve_download_post(window, post)
        self.assertEqual(resolved, hydrated_post)
        window.client.search_posts.assert_called_once_with("id:123", 0, 1)

    @patch("r34_client.core.download_manager.requests.get")
    def test_download_post_with_manager(self, mock_get) -> None:
        from r34_client.core.download_manager import DownloadManager
        from r34_client.core.settings import AppSettings
        
        post = Post.from_payload({
            "id": 456,
            "file_url": "https://img.rule34.xxx/images/456.png",
        })
        
        db = MagicMock()
        db.is_downloaded.return_value = False
        
        settings = AppSettings(
            download_directory="/tmp/downloads",
            download_naming_template="{id}_test",
            download_use_sample=False,
            download_sidecar_enabled=False
        )
        
        manager = DownloadManager(db)
        
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"fake", b"data"]
        mock_get.return_value.__enter__.return_value = mock_response
        
        with patch("pathlib.Path.open") as mock_open:
            file_handle = MagicMock()
            mock_open.return_value.__enter__.return_value = file_handle
            
            result = manager.download_post(post, settings)
            
            self.assertEqual(result, Path("/tmp/downloads/456_test.png"))
            mock_get.assert_called_once()
            file_handle.write.assert_any_call(b"fake")
            file_handle.write.assert_any_call(b"data")
            db.record_download.assert_called_once()

    def test_download_post_with_manager_skips_duplicates(self) -> None:
        from r34_client.core.download_manager import DownloadManager
        from r34_client.core.settings import AppSettings
        
        post = Post.from_payload({
            "id": 456,
            "md5": "abcd",
            "file_url": "https://img.rule34.xxx/images/456.png",
        })
        
        db = MagicMock()
        db.is_downloaded.return_value = True
        
        settings = AppSettings(
            download_directory="/tmp/downloads"
        )
        
        manager = DownloadManager(db)
        result = manager.download_post(post, settings)
        self.assertIsNone(result)

    def test_format_filename(self) -> None:
        from r34_client.core.download_manager import DownloadManager
        manager = DownloadManager(MagicMock())
        post = Post.from_payload({
            "id": 789,
            "md5": "deadbeef",
            "score": 100,
            "rating": "explicit",
            "file_url": "https://img/789.webm",
            "sample_url": "https://img/789_sample.jpg"
        })
        
        name_1 = manager.format_filename(post, "{id}_{md5}", use_sample=False)
        self.assertEqual(name_1, "789_deadbeef.webm")
        
        name_2 = manager.format_filename(post, "{rating}_{score}_{id}", use_sample=True)
        self.assertEqual(name_2, "explicit_100_789.jpg")

    def test_format_path_template(self) -> None:
        from r34_client.core.download_manager import DownloadManager
        manager = DownloadManager(MagicMock())
        post = Post.from_payload({
            "id": 123,
            "rating": "questionable",
            "md5": "abc"
        })
        
        path = manager._format_template("{rating}/{md5}", post, is_path=True)
        # On Linux it should be questionable/abc
        self.assertEqual(path, "questionable/abc")

    @patch("r34_client.core.download_manager.requests.get")
    @patch("time.sleep") # Mock sleep to speed up test
    def test_download_post_retries(self, mock_sleep, mock_get) -> None:
        from r34_client.core.download_manager import DownloadManager
        from r34_client.core.settings import AppSettings
        import requests
        
        post = Post.from_payload({"id": 111, "file_url": "http://x.com/1.jpg"})
        db = MagicMock()
        db.is_downloaded.return_value = False
        settings = AppSettings(download_directory="/tmp", download_max_retries=2)
        manager = DownloadManager(db)
        
        # First 2 calls fail, 3rd succeeds
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"ok"]
        
        # We need a context manager mock for the successful call
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_response
        
        mock_get.side_effect = [
            requests.RequestException("fail1"),
            requests.RequestException("fail2"),
            mock_cm
        ]
        
        with patch("pathlib.Path.open") as mock_open:
            mock_open.return_value.__enter__.return_value = MagicMock()
            with patch("pathlib.Path.mkdir"): # Avoid creating actual dirs
                result = manager.download_post(post, settings)
                self.assertIsNotNone(result)
                self.assertEqual(mock_get.call_count, 3)

    def test_write_sidecar(self) -> None:
        from r34_client.core.download_manager import DownloadManager
        import json
        manager = DownloadManager(MagicMock())
        post = Post.from_payload({
            "id": 999,
            "tags": "a b c",
            "md5": "abc1234",
            "score": 42
        })
        
        with patch("pathlib.Path.write_text") as mock_write:
            media_path = Path("/tmp/test/999.jpg")
            manager._write_sidecar(media_path, post, fmt="json")
            
            mock_write.assert_called_once()
            written_json = mock_write.call_args[0][0]
            data = json.loads(written_json)
            self.assertEqual(data["id"], 999)
            self.assertEqual(data["tags"], ["a", "b", "c"])

    def test_write_sidecar_txt(self) -> None:
        from r34_client.core.download_manager import DownloadManager
        manager = DownloadManager(MagicMock())
        post = Post.from_payload({
            "id": 999,
            "tags": "tag1 tag2"
        })
        
        with patch("pathlib.Path.write_text") as mock_write:
            media_path = Path("/tmp/test/999.jpg")
            manager._write_sidecar(media_path, post, fmt="txt")
            mock_write.assert_called_once_with("tag1 tag2", encoding="utf-8")

    def test_write_sidecar_both(self) -> None:
        from r34_client.core.download_manager import DownloadManager
        manager = DownloadManager(MagicMock())
        post = Post.from_payload({"id": 999, "tags": "t1 t2"})
        
        with patch("pathlib.Path.write_text") as mock_write:
            media_path = Path("/tmp/test/999.jpg")
            manager._write_sidecar(media_path, post, fmt="both")
            self.assertEqual(mock_write.call_count, 2)

    @patch("r34_client.core.download_manager.requests.get")
    @patch("time.sleep")
    def test_download_post_cleanup_on_failure(self, mock_sleep, mock_get) -> None:
        from r34_client.core.download_manager import DownloadManager
        from r34_client.core.settings import AppSettings
        import requests
        
        post = Post.from_payload({"id": 123, "file_url": "http://x.com/1.jpg"})
        db = MagicMock()
        db.is_downloaded.return_value = False
        settings = AppSettings(download_directory="/tmp", download_max_retries=1)
        manager = DownloadManager(db)
        
        mock_get.side_effect = requests.RequestException("Fatal")
        
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.unlink") as mock_unlink:
                with patch("pathlib.Path.open"):
                    with patch("pathlib.Path.mkdir"):
                        with self.assertRaises(RuntimeError):
                            manager.download_post(post, settings)
                        mock_unlink.assert_called_once()
