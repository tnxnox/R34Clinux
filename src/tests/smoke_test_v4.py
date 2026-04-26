"""
Smoke tests for V4 features.
Download Workflow.
"""

import sys
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile
import shutil
import json

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from r34_client.core.settings import AppSettings, SettingsStore
from r34_client.ui.main_window import MainWindow
from r34_client.core.models import Post
from PySide6.QtWidgets import QApplication

class V4SmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if QApplication.instance() is None:
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp()
        self.store = MagicMock(spec=SettingsStore)
        self.settings = AppSettings(
            user_id="test", 
            api_key="test",
            download_directory=self.test_dir
        )
        self.store.load.return_value = self.settings
        
        with patch("r34_client.core.db.sqlite3"):
            self.window = MainWindow(self.store)

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir)

    def test_v4_settings_model(self) -> None:
        """V4.1: Verify V4 settings are present in AppSettings."""
        self.assertTrue(hasattr(self.settings, "download_path_template"))
        self.assertTrue(hasattr(self.settings, "download_max_retries"))
        self.assertTrue(hasattr(self.settings, "download_sidecar_format"))

    @patch("r34_client.core.download_manager.requests.get")
    def test_v4_download_workflow(self, mock_get) -> None:
        """V4.1, V4.2, V4.3: Full download workflow with profiles and sidecars."""
        post = Post.from_payload({
            "id": 1234,
            "md5": "abc123md5",
            "rating": "safe",
            "tags": "tag1 tag2",
            "file_url": "http://x.com/img.jpg"
        })
        
        self.settings.download_path_template = "{rating}/nested"
        self.settings.download_sidecar_enabled = True
        self.settings.download_sidecar_format = "both"
        
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"data"]
        mock_get.return_value = mock_response
        
        # We need to mock LocalFavoritesStore because it's used in DownloadManager
        self.window.local_favorites.is_downloaded = MagicMock(return_value=False)
        self.window.local_favorites.record_download = MagicMock()
        
        result = self.window.download_manager.download_post(post, self.settings)
        
        expected_path = Path(self.test_dir) / "safe" / "nested" / "1234.jpg"
        self.assertEqual(result, expected_path)
        self.assertTrue(expected_path.exists())
        
        # Verify sidecars
        self.assertTrue(expected_path.with_suffix(".json").exists())
        self.assertTrue(expected_path.with_suffix(".txt").exists())

if __name__ == "__main__":
    unittest.main()
