from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication
from r34_client.ui.dialogs.settings import SettingsDialog
from r34_client.core.settings import AppSettings, SettingsStore


class SettingsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Safely instantiate QApplication for headless/CI testing
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.settings = AppSettings(
            user_id="user123",
            api_key="apikeyabc",
            website_username="webuser",
            website_password="webpassword",
            download_directory="/my/downloads",
            download_naming_template="{id}_{md5}",
            download_path_template="{rating}",
            download_use_sample=True,
            download_sidecar_enabled=True,
            download_sidecar_format="txt",
            download_max_retries=5,
            page_size=42,
            flaresolverr_enabled=True,
            flaresolverr_url="http://solver:8191",
            sync_conflict_strategy="local_wins",
            background_sync_interval_minutes=15,
        )
        self.store = MagicMock(spec=SettingsStore)
        self.store.default_download_directory.return_value = "/default/downloads"
        self.dialog = SettingsDialog(self.settings, self.store)

    def tearDown(self) -> None:
        self.dialog.deleteLater()

    def test_initialization_binds_values(self) -> None:
        self.assertEqual(self.dialog.user_id_edit.text(), "user123")
        self.assertEqual(self.dialog.api_key_edit.text(), "apikeyabc")
        self.assertEqual(self.dialog.website_username_edit.text(), "webuser")
        self.assertEqual(self.dialog.website_password_edit.text(), "webpassword")
        self.assertEqual(self.dialog.download_edit.text(), "/my/downloads")
        self.assertEqual(self.dialog.download_naming_template_edit.text(), "{id}_{md5}")
        self.assertEqual(self.dialog.download_path_template_edit.text(), "{rating}")
        self.assertTrue(self.dialog.download_use_sample_check.isChecked())
        self.assertTrue(self.dialog.download_sidecar_enabled_check.isChecked())
        self.assertEqual(self.dialog.download_sidecar_format_combo.currentData(), "txt")
        self.assertEqual(self.dialog.download_max_retries_spin.value(), 5)
        self.assertEqual(self.dialog.page_size_spin.value(), 42)
        self.assertTrue(self.dialog.flaresolverr_enabled_check.isChecked())
        self.assertEqual(self.dialog.flaresolverr_url_edit.text(), "http://solver:8191")
        self.assertEqual(self.dialog.conflict_strategy_combo.currentData(), "local_wins")
        self.assertEqual(self.dialog.background_sync_interval_spin.value(), 15)

    def test_current_settings_maps_correctly(self) -> None:
        # Modify widget values
        self.dialog.user_id_edit.setText("newuser")
        self.dialog.api_key_edit.setText("newkey")
        self.dialog.download_edit.setText("/new/path")
        self.dialog.download_use_sample_check.setChecked(False)
        self.dialog.download_sidecar_enabled_check.setChecked(False)
        self.dialog.page_size_spin.setValue(100)
        self.dialog.flaresolverr_enabled_check.setChecked(False)
        self.dialog.background_sync_interval_spin.setValue(0)

        updated = self.dialog.current_settings()

        self.assertEqual(updated.user_id, "newuser")
        self.assertEqual(updated.api_key, "newkey")
        self.assertEqual(updated.download_directory, "/new/path")
        self.assertFalse(updated.download_use_sample)
        self.assertFalse(updated.download_sidecar_enabled)
        self.assertEqual(updated.page_size, 100)
        self.assertFalse(updated.flaresolverr_enabled)
        self.assertEqual(updated.background_sync_interval_minutes, 0)

    @patch("PySide6.QtWidgets.QFileDialog.getExistingDirectory")
    def test_choose_directory_success(self, mock_get_dir: MagicMock) -> None:
        mock_get_dir.return_value = "/chosen/directory"
        self.dialog._choose_directory()
        self.assertEqual(self.dialog.download_edit.text(), "/chosen/directory")
        mock_get_dir.assert_called_once_with(self.dialog, "Choose download folder", "/my/downloads")

    @patch("PySide6.QtWidgets.QFileDialog.getExistingDirectory")
    def test_choose_directory_cancelled(self, mock_get_dir: MagicMock) -> None:
        mock_get_dir.return_value = "" # cancelled
        self.dialog._choose_directory()
        # Should remain unchanged
        self.assertEqual(self.dialog.download_edit.text(), "/my/downloads")
