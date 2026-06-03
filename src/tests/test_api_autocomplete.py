from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from r34_client.api.autocomplete import (
    AutocompleteClient,
    AutocompleteError,
    _normalize_whitespace,
    _sanitize_value,
)


class AutocompleteNormalizeTests(unittest.TestCase):
    def test_normalize_whitespace_collapses_spaces(self) -> None:
        self.assertEqual(_normalize_whitespace("  hello   world  "), "hello world")

    def test_normalize_whitespace_strips_ends(self) -> None:
        self.assertEqual(_normalize_whitespace("  \t  test  \n  "), "test")


class AutocompleteSanitizeTests(unittest.TestCase):
    def test_sanitize_value_unescapes_html(self) -> None:
        result = _sanitize_value("pok&eacute;mon")
        self.assertEqual(result, "pokémon")

    def test_sanitize_value_rejects_spaces(self) -> None:
        result = _sanitize_value("tag one")
        self.assertEqual(result, "")

    def test_sanitize_value_rejects_invalid_chars(self) -> None:
        self.assertEqual(_sanitize_value("bad;tag"), "")
        self.assertEqual(_sanitize_value("bad&tag"), "")
        self.assertEqual(_sanitize_value("bad?tag"), "")

    def test_sanitize_value_returns_empty_for_none(self) -> None:
        self.assertEqual(_sanitize_value(None), "")

    def test_sanitize_value_returns_empty_for_empty_string(self) -> None:
        self.assertEqual(_sanitize_value(""), "")

    def test_sanitize_value_passes_valid_tag(self) -> None:
        self.assertEqual(_sanitize_value("valid_tag"), "valid_tag")


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code


class AutocompleteClientTests(unittest.TestCase):
    def test_fetch_returns_empty_for_empty_prefix(self) -> None:
        client = AutocompleteClient()
        self.assertEqual(client.fetch(""), [])
        self.assertEqual(client.fetch("  "), [])

    def test_fetch_raises_on_http_error(self) -> None:
        with patch("requests.Session.get", return_value=FakeResponse("error", 500)):
            client = AutocompleteClient()
            with self.assertRaises(AutocompleteError):
                client.fetch("test")

    def test_fetch_returns_empty_for_empty_response(self) -> None:
        with patch("requests.Session.get", return_value=FakeResponse("")):
            client = AutocompleteClient()
            self.assertEqual(client.fetch("test"), [])

    def test_fetch_raises_on_invalid_json(self) -> None:
        with patch("requests.Session.get", return_value=FakeResponse("not json")):
            client = AutocompleteClient()
            with self.assertRaises(AutocompleteError):
                client.fetch("test")

    def test_fetch_raises_on_non_list_json(self) -> None:
        with patch("requests.Session.get", return_value=FakeResponse('{"key": "value"}')):
            client = AutocompleteClient()
            with self.assertRaises(AutocompleteError):
                client.fetch("test")

    def test_fetch_parses_suggestions(self) -> None:
        payload = json.dumps([
            {"label": "tag_one (100)", "value": "tag_one"},
            {"label": "tag_two (50)", "value": "tag_two"},
        ])
        with patch("requests.Session.get", return_value=FakeResponse(payload)) as get_mock:
            client = AutocompleteClient()
            suggestions = client.fetch("tag")

        self.assertEqual(len(suggestions), 2)
        self.assertEqual(suggestions[0].value, "tag_one")
        self.assertEqual(suggestions[0].count, 100)
        self.assertEqual(suggestions[1].value, "tag_two")
        get_mock.assert_called_once()
        self.assertEqual(get_mock.call_args.kwargs["params"]["q"], "tag")

    def test_fetch_skips_invalid_items(self) -> None:
        payload = json.dumps([
            {"label": "valid (10)", "value": "valid_tag"},
            {"label": "invalid (5)", "value": "has space"},
            {"label": "not a dict"},
        ])
        with patch("requests.Session.get", return_value=FakeResponse(payload)):
            client = AutocompleteClient()
            suggestions = client.fetch("tag")

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].value, "valid_tag")

    def test_fetch_deduplicates_by_value(self) -> None:
        payload = json.dumps([
            {"label": "same (10)", "value": "same_tag"},
            {"label": "same duplicate (5)", "value": "same_tag"},
        ])
        with patch("requests.Session.get", return_value=FakeResponse(payload)):
            client = AutocompleteClient()
            suggestions = client.fetch("tag")

        self.assertEqual(len(suggestions), 1)
