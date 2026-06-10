from __future__ import annotations

import unittest
from xml.etree import ElementTree as ET

from r34_client.api.flaresolverr.parsing import (
    _normalize_html_text,
    decode_payload,
    extract_body_text,
    looks_rate_limited,
    looks_logged_in,
    extract_post_ids,
    extract_favorite_tile_ids,
    extract_items,
)


class FlareSolverrParsingNormalizeTests(unittest.TestCase):
    def test_normalize_html_text_unescapes_html(self) -> None:
        result = _normalize_html_text("pok&eacute;mon")
        self.assertEqual(result, "pokémon")

    def test_normalize_html_text_handles_escaped_chars(self) -> None:
        result = _normalize_html_text('test\\"quote\\/slash')
        self.assertEqual(result, 'test"quote/slash')

    def test_normalize_html_text_handles_empty(self) -> None:
        self.assertEqual(_normalize_html_text(""), "")


class DecodePayloadTests(unittest.TestCase):
    def test_decode_json_object(self) -> None:
        result = decode_payload('{"key": "value"}')
        self.assertEqual(result, {"key": "value"})

    def test_decode_json_array(self) -> None:
        result = decode_payload('[1, 2, 3]')
        self.assertEqual(result, [1, 2, 3])

    def test_decode_xml(self) -> None:
        result = decode_payload("<root><item>text</item></root>")
        self.assertIsInstance(result, ET.Element)
        self.assertEqual(result.tag, "root")

    def test_decode_empty_returns_empty_list(self) -> None:
        self.assertEqual(decode_payload(""), [])
        self.assertEqual(decode_payload("  "), [])

    def test_decode_invalid_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            decode_payload("not valid json or xml")


class ExtractBodyTextTests(unittest.TestCase):
    def test_extract_body_text_finds_body(self) -> None:
        html = "<html><body>content</body></html>"
        self.assertEqual(extract_body_text(html), "content")

    def test_extract_body_text_no_body_returns_full(self) -> None:
        self.assertEqual(extract_body_text("plain text"), "plain text")

    def test_extract_body_text_empty(self) -> None:
        self.assertEqual(extract_body_text(""), "")


class LooksRateLimitedTests(unittest.TestCase):
    def test_detects_429_rate(self) -> None:
        self.assertTrue(looks_rate_limited("HTTP 429 rate limited"))

    def test_detects_too_many_requests(self) -> None:
        self.assertTrue(looks_rate_limited("Too many requests"))

    def test_rejects_clean_text(self) -> None:
        self.assertFalse(looks_rate_limited("OK response"))
        self.assertFalse(looks_rate_limited(""))

    def test_is_case_insensitive(self) -> None:
        self.assertTrue(looks_rate_limited("TOO MANY REQUESTS"))


class LooksLoggedInTests(unittest.TestCase):
    def test_detects_logout_link(self) -> None:
        self.assertTrue(looks_logged_in('page=account&s=logout'))

    def test_detects_change_password(self) -> None:
        self.assertTrue(looks_logged_in("page=account&s=change_password"))

    def test_detects_logout_of_account(self) -> None:
        self.assertTrue(looks_logged_in("logout of your account"))

    def test_rejects_logged_out_text(self) -> None:
        self.assertFalse(looks_logged_in("page=account&s=login"))
        self.assertFalse(looks_logged_in(""))


class ExtractPostIdsTests(unittest.TestCase):
    def test_extracts_ids_from_href_links(self) -> None:
        html = '<a href="index.php?page=post&s=view&id=123">link</a>'
        self.assertEqual(extract_post_ids(html), [123])

    def test_extracts_multiple_ids(self) -> None:
        html = """
            <a href="index.php?page=post&s=view&id=100">a</a>
            <a href="index.php?page=post&s=view&id=200">b</a>
        """
        self.assertEqual(extract_post_ids(html), [100, 200])

    def test_deduplicates_ids(self) -> None:
        html = """
            <a href="index.php?page=post&s=view&id=100">a</a>
            <a href="index.php?page=post&s=view&id=100">b</a>
        """
        self.assertEqual(extract_post_ids(html), [100])

    def test_skips_non_post_links(self) -> None:
        html = '<a href="index.php?page=favorites&s=view&id=100">fav</a>'
        self.assertEqual(extract_post_ids(html), [])

    def test_fallback_finds_unquoted_hrefs(self) -> None:
        html = "page=post&s=view&id=456"
        self.assertEqual(extract_post_ids(html), [456])

    def test_empty_html(self) -> None:
        self.assertEqual(extract_post_ids(""), [])


class ExtractFavoriteTileIdsTests(unittest.TestCase):
    def test_extracts_ids_from_tile_anchors(self) -> None:
        html = '<a id="p789">link</a>'
        self.assertEqual(extract_favorite_tile_ids(html), [789])

    def test_deduplicates_tile_ids(self) -> None:
        html = '<a id="p1">a</a><a id="p1">b</a>'
        self.assertEqual(extract_favorite_tile_ids(html), [1])

    def test_empty_html(self) -> None:
        self.assertEqual(extract_favorite_tile_ids(""), [])


class ExtractItemsTests(unittest.TestCase):
    def test_extracts_items_from_tiles(self) -> None:
        html = '<a id="p1"><img src="https://img.test/preview.jpg"></a>'
        items = extract_items(html)
        self.assertEqual(items, [(1, "https://img.test/preview.jpg")])

    def test_prepends_https_to_protocol_relative(self) -> None:
        html = '<a id="p2"><img src="//img.test/preview.jpg"></a>'
        items = extract_items(html)
        self.assertEqual(items, [(2, "https://img.test/preview.jpg")])

    def test_fallback_to_post_ids_and_imgs(self) -> None:
        html = '<img src="fallback.jpg">'
        self.assertEqual(extract_items(html), [])


class FlareSolverrValidationTests(unittest.TestCase):
    def test_validate_logged_out_raises(self) -> None:
        # Lacks page=account&s=logout or other login signatures
        html = "<html><body>Some random page</body></html>"
        with self.assertRaises(RuntimeError) as ctx:
            extract_items(html, validate=True)
        self.assertIn("session is not logged in", str(ctx.exception))

    def test_validate_not_rule34_raises(self) -> None:
        # Has logout signature but no rule34 signature
        html = "<html><body>s=logout but nothing else</body></html>"
        with self.assertRaises(RuntimeError) as ctx:
            extract_items(html, validate=True)
        self.assertIn("Not a Rule34 page", str(ctx.exception))

    def test_validate_rate_limited_raises(self) -> None:
        html = "HTTP 429 rate limited"
        with self.assertRaises(RuntimeError) as ctx:
            extract_items(html, validate=True)
        self.assertIn("rate limited", str(ctx.exception))

    def test_validate_cloudflare_raises(self) -> None:
        html = "rule34 page=account&s=logout cloudflare checking your browser"
        with self.assertRaises(RuntimeError) as ctx:
            extract_items(html, validate=True)
        self.assertIn("blocked by Cloudflare", str(ctx.exception))

    def test_validate_layout_changed_raises(self) -> None:
        # Rule34, logged in, but contains thumbnail indicator and 0 items parsed
        html = "rule34 page=account&s=logout /thumbnails/pic.jpg"
        with self.assertRaises(RuntimeError) as ctx:
            extract_items(html, validate=True)
        self.assertIn("Rule34 layout might have changed", str(ctx.exception))

    def test_validate_empty_valid_page_passes(self) -> None:
        # Rule34, logged in, truly empty (no thumbnails, no posts)
        html = "rule34 page=account&s=logout No favorites found"
        # Should not raise, just return empty list
        self.assertEqual(extract_items(html, validate=True), [])
