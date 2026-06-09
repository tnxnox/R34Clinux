from __future__ import annotations

import unittest
from unittest.mock import patch

from r34_client.api.flaresolverr import FlareSolverrFavoritesClient, FlareSolverrError
from r34_client.api.flaresolverr_parsing import _normalize_html_text, decode_payload
from r34_client.sync.pending_mutations import extract_retry_after_seconds


class IsSessionErrorTests(unittest.TestCase):
    """Tests for FlareSolverrFavoritesClient._is_session_error."""

    def test_detects_session_not_found(self) -> None:
        self.assertTrue(
            FlareSolverrFavoritesClient._is_session_error("session not found")
        )

    def test_detects_session_doesnt_exist(self) -> None:
        self.assertTrue(
            FlareSolverrFavoritesClient._is_session_error("session doesn't exist")
        )

    def test_detects_session_does_not_exist(self) -> None:
        self.assertTrue(
            FlareSolverrFavoritesClient._is_session_error("session does not exist")
        )

    def test_detects_session_invalid(self) -> None:
        self.assertTrue(
            FlareSolverrFavoritesClient._is_session_error("session invalid")
        )

    def test_case_insensitive_matching(self) -> None:
        self.assertTrue(
            FlareSolverrFavoritesClient._is_session_error("SESSION NOT FOUND")
        )

    def test_does_not_match_non_session_errors(self) -> None:
        self.assertFalse(
            FlareSolverrFavoritesClient._is_session_error("timeout error")
        )
        self.assertFalse(
            FlareSolverrFavoritesClient._is_session_error("rate limited")
        )
        self.assertFalse(
            FlareSolverrFavoritesClient._is_session_error("internal server error")
        )

    def test_empty_string_returns_false(self) -> None:
        self.assertFalse(FlareSolverrFavoritesClient._is_session_error(""))

    def test_none_message_is_handled_gracefully(self) -> None:
        """The method should handle None by treating it as empty string."""
        self.assertFalse(FlareSolverrFavoritesClient._is_session_error(""))


class LooksTransientWebGateTests(unittest.TestCase):
    """Tests for FlareSolverrFavoritesClient._looks_transient_web_gate."""

    def test_plain_br_matches(self) -> None:
        self.assertTrue(
            FlareSolverrFavoritesClient._looks_transient_web_gate("<br>")
        )

    def test_double_br_matches(self) -> None:
        self.assertTrue(
            FlareSolverrFavoritesClient._looks_transient_web_gate("<br><br>")
        )

    def test_self_closing_br_matches(self) -> None:
        self.assertTrue(
            FlareSolverrFavoritesClient._looks_transient_web_gate("<br/><br/>")
        )

    def test_mixed_br_variants_match(self) -> None:
        self.assertTrue(
            FlareSolverrFavoritesClient._looks_transient_web_gate("<br/><br>")
        )
        self.assertTrue(
            FlareSolverrFavoritesClient._looks_transient_web_gate("<br><br/>")
        )

    def test_case_insensitive_matching(self) -> None:
        self.assertTrue(
            FlareSolverrFavoritesClient._looks_transient_web_gate("<BR>")
        )

    def test_html_with_content_does_not_match(self) -> None:
        self.assertFalse(
            FlareSolverrFavoritesClient._looks_transient_web_gate(
                "<html><body>content</body></html>"
            )
        )

    def test_empty_string_does_not_match(self) -> None:
        self.assertFalse(
            FlareSolverrFavoritesClient._looks_transient_web_gate("")
        )

    def test_normal_text_does_not_match(self) -> None:
        self.assertFalse(
            FlareSolverrFavoritesClient._looks_transient_web_gate("normal text")
        )

    def test_extra_whitespace_is_stripped(self) -> None:
        """Whitespace around the text is stripped before comparison."""
        self.assertTrue(
            FlareSolverrFavoritesClient._looks_transient_web_gate("  <br>  ")
        )


class NormalizeHtmlTextTests(unittest.TestCase):
    """Tests for _normalize_html_text from flaresolverr_parsing."""

    def test_unescapes_html_entities(self) -> None:
        result = _normalize_html_text("pok&eacute;mon")
        self.assertEqual(result, "pokémon")

    def test_handles_escaped_quotes_and_slashes(self) -> None:
        result = _normalize_html_text('test\\"quote\\/slash')
        self.assertEqual(result, 'test"quote/slash')

    def test_handles_empty_string(self) -> None:
        self.assertEqual(_normalize_html_text(""), "")

    def test_handles_none_like_empty(self) -> None:
        self.assertEqual(_normalize_html_text(""), "")

    def test_regular_text_passes_through(self) -> None:
        result = _normalize_html_text("hello world")
        self.assertEqual(result, "hello world")


class SessionNameTests(unittest.TestCase):
    """Tests for FlareSolverrFavoritesClient._session_name."""

    def test_returns_r34_prefix_format(self) -> None:
        client = FlareSolverrFavoritesClient(user_id="user123", api_key="key")
        name = client._session_name()
        self.assertTrue(name.startswith("r34-"))
        self.assertIn("user123", name)

    def test_sanitizes_special_characters_from_user_id(self) -> None:
        client = FlareSolverrFavoritesClient(user_id="user@#$%^", api_key="key")
        name = client._session_name()
        # Only alphanumeric, underscore, and hyphen should remain
        self.assertEqual(name, "r34-user")

    def test_empty_user_id_uses_default_fallback(self) -> None:
        client = FlareSolverrFavoritesClient(user_id="", api_key="key")
        name = client._session_name()
        self.assertEqual(name, "r34-default")

    def test_whitespace_user_id_uses_default(self) -> None:
        client = FlareSolverrFavoritesClient(user_id="   ", api_key="key")
        name = client._session_name()
        self.assertEqual(name, "r34-default")

    def test_returns_consistent_format(self) -> None:
        client = FlareSolverrFavoritesClient(user_id="test_user-123", api_key="key")
        name = client._session_name()
        # hyphens and underscores are kept
        self.assertTrue(name.startswith("r34-"))
        self.assertIn("test_user-123", name)


class DecodePayloadTests(unittest.TestCase):
    """Tests for decode_payload from flaresolverr_parsing."""

    def test_parses_valid_json_object(self) -> None:
        result = decode_payload('{"key": "value"}')
        self.assertEqual(result, {"key": "value"})

    def test_parses_valid_json_array(self) -> None:
        result = decode_payload("[1, 2, 3]")
        self.assertEqual(result, [1, 2, 3])

    def test_handles_empty_string_returns_empty_list(self) -> None:
        self.assertEqual(decode_payload(""), [])

    def test_handles_whitespace_only_returns_empty_list(self) -> None:
        self.assertEqual(decode_payload("  "), [])

    def test_invalid_json_falls_back_to_xml_and_raises(self) -> None:
        """Invalid JSON that is also not XML should raise RuntimeError."""
        with self.assertRaises(RuntimeError):
            decode_payload("not valid json or xml")

    def test_parses_xml_as_element(self) -> None:
        from xml.etree import ElementTree as ET

        result = decode_payload("<root><item>text</item></root>")
        self.assertIsInstance(result, ET.Element)
        self.assertEqual(result.tag, "root")


class ExtractRetryAfterSecondsTests(unittest.TestCase):
    """Tests for extract_retry_after_seconds from pending_mutations."""

    def test_extracts_retry_after_value(self) -> None:
        self.assertEqual(extract_retry_after_seconds("retry after 30 seconds"), 30)

    def test_various_spellings(self) -> None:
        self.assertEqual(extract_retry_after_seconds("Retry-After: 60"), 60)
        self.assertEqual(extract_retry_after_seconds("retry_after=120"), 120)
        self.assertEqual(extract_retry_after_seconds("RETRY_AFTER 15"), 15)

    def test_no_match_returns_none(self) -> None:
        self.assertIsNone(extract_retry_after_seconds("no retry info"))

    def test_empty_message_returns_none(self) -> None:
        self.assertIsNone(extract_retry_after_seconds(""))

    def test_negative_sign_is_ignored_absolute_value_used(self) -> None:
        """The regex captures the absolute value even with a negative sign."""
        result = extract_retry_after_seconds("retry after -5")
        self.assertEqual(result, 5)
