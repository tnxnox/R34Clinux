from __future__ import annotations

import unittest

from r34_client.core.settings import AppSettings, SettingsStore


class AppSettingsTests(unittest.TestCase):
    def test_has_credentials_true_when_both_set(self) -> None:
        settings = AppSettings(user_id="123", api_key="secret")
        self.assertTrue(settings.has_credentials)

    def test_has_credentials_false_when_empty(self) -> None:
        self.assertFalse(AppSettings().has_credentials)

    def test_has_credentials_false_when_only_user_id(self) -> None:
        self.assertFalse(AppSettings(user_id="123").has_credentials)

    def test_has_credentials_false_when_only_api_key(self) -> None:
        self.assertFalse(AppSettings(api_key="secret").has_credentials)

    def test_has_credentials_false_with_whitespace_only(self) -> None:
        self.assertFalse(AppSettings(user_id="  ", api_key="  ").has_credentials)


class SettingsStoreLoadStringListTests(unittest.TestCase):
    def test_empty_input_returns_empty_list(self) -> None:
        self.assertEqual(SettingsStore._load_string_list(None, 10), [])
        self.assertEqual(SettingsStore._load_string_list([], 10), [])

    def test_single_string_wrapped_in_list(self) -> None:
        result = SettingsStore._load_string_list("hello", 10)
        self.assertEqual(result, ["hello"])

    def test_list_of_strings(self) -> None:
        result = SettingsStore._load_string_list(["a", "b", "c"], 10)
        self.assertEqual(result, ["a", "b", "c"])

    def test_strips_whitespace_and_deduplicates(self) -> None:
        result = SettingsStore._load_string_list(["  a  ", "a", "b"], 10)
        self.assertEqual(result, ["a", "b"])

    def test_respects_limit(self) -> None:
        result = SettingsStore._load_string_list(["a", "b", "c", "d"], 2)
        self.assertEqual(result, ["a", "b"])

    def test_skips_empty_strings(self) -> None:
        result = SettingsStore._load_string_list(["a", "", "b"], 10)
        self.assertEqual(result, ["a", "b"])
