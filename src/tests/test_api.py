from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from r34_client.api.client import Rule34Client


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200, content_type: str = "application/json") -> None:
        self.text = text
        self.status_code = status_code
        self.headers = {"content-type": content_type}


class Rule34ClientTests(unittest.TestCase):
    def test_search_posts_uses_auth_and_parses_json(self) -> None:
        payload = [
            {
                "id": "123",
                "tags": "pokemon ponytail",
                "rating": "s",
                "score": "42",
                "width": "800",
                "height": "600",
                "file_size": "111",
                "source": "",
                "md5": "abc",
                "preview_url": "https://example.test/preview.jpg",
                "sample_url": "https://example.test/sample.jpg",
                "file_url": "https://example.test/file.jpg",
                "date": "2024-01-01",
            }
        ]

        with patch("requests.Session.get", return_value=FakeResponse(json.dumps(payload))) as get_mock:
            client = Rule34Client(user_id="1", api_key="secret")
            posts = client.search_posts("po", 0, 50)

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].id, 123)
        self.assertEqual(posts[0].file_name, "file.jpg")
        called_kwargs = get_mock.call_args.kwargs
        self.assertEqual(called_kwargs["params"]["user_id"], "1")
        self.assertEqual(called_kwargs["params"]["api_key"], "secret")
        self.assertEqual(called_kwargs["params"]["tags"], "po")

    def test_autocomplete_tags_parses_label_and_value(self) -> None:
        payload = json.dumps([
            {"label": "pokemon (880615)", "value": "pokemon"},
            {"label": "pov (579200)", "value": "pov"},
        ])

        with patch("requests.Session.get", return_value=FakeResponse(payload)):
            client = Rule34Client(user_id="1", api_key="secret")
            suggestions = client.autocomplete_tags("po")

        self.assertEqual([item.value for item in suggestions], ["pokemon", "pov"])
        self.assertEqual([item.count for item in suggestions], [880615, 579200])
        self.assertEqual(suggestions[0].display_text, "pokemon (880615)")

    def test_autocomplete_tags_sanitizes_invalid_entries(self) -> None:
        payload = json.dumps([
            {"label": "pok&eacute;mon_(species) (197584)", "value": "pok&eacute;mon_(species)"},
            {"label": "invalid combo (10)", "value": "tag_one tag_two"},
            {"label": "bad query (5)", "value": "bad?tag"},
            {"label": "clean_tag (2)", "value": "clean_tag"},
            {"label": "clean_tag (2)", "value": "clean_tag"},
        ])

        with patch("requests.Session.get", return_value=FakeResponse(payload)):
            client = Rule34Client(user_id="1", api_key="secret")
            suggestions = client.autocomplete_tags("po")

        self.assertEqual([item.value for item in suggestions], ["pokémon_(species)", "clean_tag"])
        self.assertEqual([item.count for item in suggestions], [197584, 2])
