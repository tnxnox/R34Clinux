from __future__ import annotations

import logging
import unittest
from unittest.mock import patch

from r34_client.core.settings import AppSettings, SettingsStore


class ValidateSettingsTests(unittest.TestCase):
    """Tests for SettingsStore._validate_settings."""

    @patch("r34_client.core.settings.QSettings")
    def test_page_size_above_1000_clamps_to_1000(self, mock_qsettings: object) -> None:
        """page_size > 1000 should log a warning and clamp to 1000."""
        store = SettingsStore()
        settings = AppSettings(page_size=2000)
        with self.assertLogs("r34_client.core.settings", level="WARNING") as logs:
            store._validate_settings(settings)
        any_warn = any("page_size is 2000" in msg for msg in logs.output)
        self.assertTrue(any_warn, "Expected a warning about large page_size")
        self.assertEqual(settings.page_size, 1000)

    @patch("r34_client.core.settings.QSettings")
    def test_page_size_below_1_resets_to_50(self, mock_qsettings: object) -> None:
        """page_size < 1 should be reset to the default of 50."""
        store = SettingsStore()
        settings = AppSettings(page_size=0)
        with self.assertLogs("r34_client.core.settings", level="WARNING") as logs:
            store._validate_settings(settings)
        self.assertEqual(settings.page_size, 50)

    @patch("r34_client.core.settings.QSettings")
    def test_page_size_negative_resets_to_50(self, mock_qsettings: object) -> None:
        """A negative page_size should also be reset to 50."""
        store = SettingsStore()
        settings = AppSettings(page_size=-10)
        with self.assertLogs("r34_client.core.settings", level="WARNING") as logs:
            store._validate_settings(settings)
        self.assertEqual(settings.page_size, 50)

    @patch("r34_client.core.settings.QSettings")
    def test_page_size_normal_passes_through(self, mock_qsettings: object) -> None:
        """A page_size in the valid range [1, 1000] should pass through unchanged."""
        store = SettingsStore()
        settings = AppSettings(page_size=42)
        with self.assertNoLogs("r34_client.core.settings", level="WARNING"):
            store._validate_settings(settings)
        self.assertEqual(settings.page_size, 42)

    @patch("r34_client.core.settings.QSettings")
    def test_download_max_retries_negative_clamped_to_0(self, mock_qsettings: object) -> None:
        """download_max_retries < 0 should be clamped to 0."""
        store = SettingsStore()
        settings = AppSettings(download_max_retries=-5)
        with self.assertLogs("r34_client.core.settings", level="WARNING") as logs:
            store._validate_settings(settings)
        self.assertEqual(settings.download_max_retries, 0)

    @patch("r34_client.core.settings.QSettings")
    def test_download_max_retries_non_negative_passes_through(self, mock_qsettings: object) -> None:
        """A non-negative download_max_retries should stay unchanged."""
        store = SettingsStore()
        settings = AppSettings(download_max_retries=3)
        with self.assertNoLogs("r34_client.core.settings", level="WARNING"):
            store._validate_settings(settings)
        self.assertEqual(settings.download_max_retries, 3)

    @patch("r34_client.core.settings.QSettings")
    def test_download_max_retries_zero_passes_through(self, mock_qsettings: object) -> None:
        """Zero is a valid value for download_max_retries (no retries)."""
        store = SettingsStore()
        settings = AppSettings(download_max_retries=0)
        with self.assertNoLogs("r34_client.core.settings", level="WARNING"):
            store._validate_settings(settings)
        self.assertEqual(settings.download_max_retries, 0)

    @patch("r34_client.core.settings.QSettings")
    def test_sidecar_format_invalid_resets_to_json(self, mock_qsettings: object) -> None:
        """Invalid sidecar format should be reset to 'json'."""
        store = SettingsStore()
        settings = AppSettings(download_sidecar_format="invalid")
        with self.assertLogs("r34_client.core.settings", level="WARNING") as logs:
            store._validate_settings(settings)
        self.assertEqual(settings.download_sidecar_format, "json")

    @patch("r34_client.core.settings.QSettings")
    def test_sidecar_format_valid_passes_through(self, mock_qsettings: object) -> None:
        """Valid sidecar formats should be accepted (case-insensitive)."""
        for fmt in ("json", "txt", "both", "JSON", "Txt", "BOTH"):
            with self.subTest(fmt=fmt):
                store = SettingsStore()
                settings = AppSettings(download_sidecar_format=fmt)
                with self.assertNoLogs("r34_client.core.settings", level="WARNING"):
                    store._validate_settings(settings)
                self.assertEqual(settings.download_sidecar_format.lower(), fmt.lower())

    @patch("r34_client.core.settings.QSettings")
    def test_sync_conflict_strategy_invalid_resets_to_merge(self, mock_qsettings: object) -> None:
        """Unknown sync conflict strategy should be reset to 'merge'."""
        store = SettingsStore()
        settings = AppSettings(sync_conflict_strategy="bogus")
        with self.assertLogs("r34_client.core.settings", level="WARNING") as logs:
            store._validate_settings(settings)
        self.assertEqual(settings.sync_conflict_strategy, "merge")

    @patch("r34_client.core.settings.QSettings")
    def test_sync_conflict_strategy_valid_passes_through(self, mock_qsettings: object) -> None:
        """Known sync conflict strategies should pass through unchanged."""
        for strategy in ("merge", "local_wins", "remote_wins"):
            with self.subTest(strategy=strategy):
                store = SettingsStore()
                settings = AppSettings(sync_conflict_strategy=strategy)
                with self.assertNoLogs("r34_client.core.settings", level="WARNING"):
                    store._validate_settings(settings)
                self.assertEqual(settings.sync_conflict_strategy, strategy)


class HasCredentialsTests(unittest.TestCase):
    """Tests for AppSettings.has_credentials."""

    def test_returns_true_when_both_user_id_and_api_key_set(self) -> None:
        settings = AppSettings(user_id="123", api_key="secret")
        self.assertTrue(settings.has_credentials)

    def test_returns_false_when_empty(self) -> None:
        self.assertFalse(AppSettings().has_credentials)

    def test_returns_false_when_only_user_id(self) -> None:
        self.assertFalse(AppSettings(user_id="123").has_credentials)

    def test_returns_false_when_only_api_key(self) -> None:
        self.assertFalse(AppSettings(api_key="secret").has_credentials)

    def test_returns_false_with_whitespace_only(self) -> None:
        self.assertFalse(AppSettings(user_id="  ", api_key="  ").has_credentials)

    def test_strips_whitespace_from_values(self) -> None:
        settings = AppSettings(user_id="  user123  ", api_key="  key456  ")
        self.assertTrue(settings.has_credentials)


class LoadStringListTests(unittest.TestCase):
    """Tests for SettingsStore._load_string_list."""

    def test_none_input_returns_empty_list(self) -> None:
        self.assertEqual(SettingsStore._load_string_list(None, 10), [])

    def test_empty_list_returns_empty_list(self) -> None:
        self.assertEqual(SettingsStore._load_string_list([], 10), [])

    def test_single_string_wrapped_in_list_and_stripped(self) -> None:
        result = SettingsStore._load_string_list("  hello  ", 10)
        self.assertEqual(result, ["hello"])

    def test_actual_list_returns_deduplicated_stripped_items(self) -> None:
        result = SettingsStore._load_string_list(["a", "  a  ", "b"], 10)
        self.assertEqual(result, ["a", "b"])

    def test_respects_limit(self) -> None:
        result = SettingsStore._load_string_list(["a", "b", "c", "d"], 2)
        self.assertEqual(result, ["a", "b"])

    def test_skips_empty_and_whitespace_only_items(self) -> None:
        result = SettingsStore._load_string_list(["a", "", "  ", "b"], 10)
        self.assertEqual(result, ["a", "b"])

    def test_limit_zero_returns_empty_list(self) -> None:
        result = SettingsStore._load_string_list(["a", "b", "c"], 0)
        self.assertEqual(result, [])

    def test_negative_limit_treated_as_zero(self) -> None:
        result = SettingsStore._load_string_list(["a", "b", "c"], -5)
        self.assertEqual(result, [])


class DefaultDownloadDirectoryTests(unittest.TestCase):
    """Tests for SettingsStore.default_download_directory."""

    @patch("r34_client.core.settings.QStandardPaths")
    def test_returns_something_when_standard_path_available(
        self, mock_qsp: object
    ) -> None:
        from r34_client.core.settings import QStandardPaths

        QStandardPaths.writableLocation.return_value = "/some/downloads"  # type: ignore[attr-defined]
        result = SettingsStore.default_download_directory()
        self.assertTrue(len(result) > 0)

    @patch("r34_client.core.settings.QStandardPaths")
    def test_returns_path_when_standard_path_exists(
        self, mock_qsp: object
    ) -> None:
        from r34_client.core.settings import QStandardPaths

        QStandardPaths.writableLocation.return_value = "/custom/downloads"  # type: ignore[attr-defined]
        result = SettingsStore.default_download_directory()
        self.assertEqual(result, "/custom/downloads")

    @patch("r34_client.core.settings.QStandardPaths.writableLocation", return_value="")
    @patch("r34_client.core.settings.Path.home")
    def test_returns_home_downloads_fallback_when_standard_empty(
        self, mock_home: object, mock_wl: object
    ) -> None:
        from pathlib import Path

        mock_home.return_value = Path("/home/testuser")  # type: ignore[attr-defined]
        result = SettingsStore.default_download_directory()
        self.assertEqual(result, "/home/testuser/Downloads")
