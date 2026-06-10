from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from r34_client.api.scraping import fetch_page, parse_scraped_favorites, fetch_friend_favorites


class ScrapingTests(unittest.TestCase):
    @patch("requests.get")
    def test_fetch_page_direct(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.text = "direct response"
        mock_get.return_value = mock_resp
        
        res = fetch_page("https://example.test", flare_solver_url="")
        
        self.assertEqual(res, "direct response")
        mock_get.assert_called_once_with("https://example.test", headers=unittest.mock.ANY, timeout=15)

    @patch("requests.post")
    def test_fetch_page_flaresolverr(self, mock_post: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"solution": {"response": "flaresolverr response"}}
        mock_post.return_value = mock_resp
        
        res = fetch_page("https://example.test", flare_solver_url="http://solver")
        
        self.assertEqual(res, "flaresolverr response")
        mock_post.assert_called_once()

    def test_parse_scraped_favorites(self) -> None:
        # Mock HTML parsing
        html = """
        <html>
        <body>
            <span class="thumb" id="s101"><a href="index.php?page=post&s=view&id=101"><img src="https://ex.com/t101.jpg"></a></span>
            <span class="thumb" id="s102"><a href="index.php?page=post&s=view&id=102"><img src="https://ex.com/t102.jpg"></a></span>
        </body>
        </html>
        """
        posts = parse_scraped_favorites(html)
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0].id, 101)
        self.assertEqual(posts[0].preview_url, "https://ex.com/t101.jpg")
        self.assertEqual(posts[1].id, 102)
        self.assertEqual(posts[1].preview_url, "https://ex.com/t102.jpg")

    @patch("r34_client.api.scraping.fetch_page")
    def test_fetch_friend_favorites(self, mock_fetch_page: MagicMock) -> None:
        client = MagicMock()
        mock_fetch_page.return_value = "<html></html>"
        
        # page = 5 -> API offset is 50
        posts = fetch_friend_favorites(client, "123", "http://solver", page=5)
        
        mock_fetch_page.assert_called_once()
        self.assertEqual(posts, [])
