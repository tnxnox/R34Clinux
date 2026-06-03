from __future__ import annotations

import unittest

from r34_client.api.urls import (
    RULE34_WEB_BASE_URL,
    favorites_view_url,
    favorites_list_url,
    account_home_url,
    account_login_url,
    add_favorite_public_url,
    add_favorite_web_url,
    delete_favorite_web_url,
)


class UrlsTests(unittest.TestCase):
    def test_favorites_view_url(self) -> None:
        url = favorites_view_url("42")
        self.assertEqual(url, f"{RULE34_WEB_BASE_URL}/index.php?page=favorites&s=view&id=42")

    def test_favorites_view_url_strips_whitespace(self) -> None:
        url = favorites_view_url("  42  ")
        self.assertEqual(url, f"{RULE34_WEB_BASE_URL}/index.php?page=favorites&s=view&id=42")

    def test_favorites_list_url(self) -> None:
        url = favorites_list_url()
        self.assertEqual(url, f"{RULE34_WEB_BASE_URL}/index.php?page=favorites&s=list")

    def test_account_home_url(self) -> None:
        url = account_home_url()
        self.assertEqual(url, f"{RULE34_WEB_BASE_URL}/index.php?page=account&s=home")

    def test_account_login_url(self) -> None:
        url = account_login_url()
        self.assertEqual(url, f"{RULE34_WEB_BASE_URL}/index.php?page=account&s=login&code=00")

    def test_add_favorite_public_url(self) -> None:
        url = add_favorite_public_url(999)
        self.assertEqual(url, f"{RULE34_WEB_BASE_URL}/public/addfav.php?id=999")

    def test_add_favorite_web_url(self) -> None:
        url = add_favorite_web_url(888)
        self.assertEqual(url, f"{RULE34_WEB_BASE_URL}/index.php?page=favorites&s=add&id=888")

    def test_delete_favorite_web_url(self) -> None:
        url = delete_favorite_web_url(777)
        self.assertEqual(url, f"{RULE34_WEB_BASE_URL}/index.php?page=favorites&s=delete&id=777&return_pid=0")

    def test_add_favorite_public_url_coerces_to_int(self) -> None:
        url = add_favorite_public_url(1.5)
        self.assertIn("id=1", url)
