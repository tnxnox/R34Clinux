from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch, call
from xml.etree import ElementTree as ET

from r34_client.api.flaresolverr.client import FlareSolverrFavoritesClient
from r34_client.api.flaresolverr.errors import FlareSolverrError
from r34_client.core.models import Post


@patch("r34_client.api.flaresolverr.client.time.sleep")
class FlareSolverrFavoritesClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.req_patch = patch.object(FlareSolverrFavoritesClient, "_request_via_solver")
        self.post_patch = patch.object(FlareSolverrFavoritesClient, "_post_via_solver")
        self.mock_req = self.req_patch.start()
        self.mock_post = self.post_patch.start()

        self.client = FlareSolverrFavoritesClient(
            user_id="12345",
            api_key="abcde",
            website_username="myuser",
            website_password="mypassword",
            solver_url="http://mock-solver:8191",
        )

    def tearDown(self) -> None:
        self.client.close()
        self.req_patch.stop()
        self.post_patch.stop()

    def test_init_sets_up_session(self, mock_sleep: MagicMock) -> None:
        self.assertEqual(self.client.user_id, "12345")
        self.assertEqual(self.client.api_key, "abcde")
        self.assertEqual(self.client.website_username, "myuser")
        self.assertEqual(self.client.website_password, "mypassword")
        self.assertIsNotNone(self.client._solver_session)

    def test_auth_params_missing_credentials(self, mock_sleep: MagicMock) -> None:
        client_no_auth = FlareSolverrFavoritesClient(user_id="", api_key="")
        with self.assertRaises(FlareSolverrError):
            client_no_auth._auth_params()

        client_whitespace = FlareSolverrFavoritesClient(user_id="  ", api_key="  ")
        with self.assertRaises(FlareSolverrError):
            client_whitespace._auth_params()

    def test_auth_params_valid(self, mock_sleep: MagicMock) -> None:
        params = self.client._auth_params()
        self.assertEqual(params, {"user_id": "12345", "api_key": "abcde"})

    def test_favorite_exists_in_view_with_retries_success(self, mock_sleep: MagicMock) -> None:
        # First request: rate limited, Second request: success
        self.mock_req.side_effect = [
            "This page is temporarily rate limited. (HTTP 429)",
            '<html><body><div id="post-list"><a href="index.php?page=post&s=view&id=456" id="p456">Post</a></div></body></html>'
        ]
        res = self.client._favorite_exists_in_view_with_retries(456, attempts=3, allow_unknown=False)
        self.assertTrue(res)
        self.assertEqual(self.mock_req.call_count, 2)
        mock_sleep.assert_called_once_with(1.0)

    def test_favorite_exists_in_view_with_retries_rate_limit_failure(self, mock_sleep: MagicMock) -> None:
        self.mock_req.return_value = "This page is temporarily rate limited. (HTTP 429)"
        
        # allow_unknown=False raises FlareSolverrError
        with self.assertRaises(FlareSolverrError):
            self.client._favorite_exists_in_view_with_retries(456, attempts=2, allow_unknown=False)

        # allow_unknown=True returns None
        res = self.client._favorite_exists_in_view_with_retries(456, attempts=2, allow_unknown=True)
        self.assertIsNone(res)

    def test_favorite_exists_in_view_with_retries_unauthenticated(self, mock_sleep: MagicMock) -> None:
        # Page doesn't have login markers or list markers, e.g. login form
        self.mock_req.return_value = '<html><body>name="user" name="pass"</body></html>'
        
        with self.assertRaises(FlareSolverrError):
            self.client._favorite_exists_in_view_with_retries(456, attempts=1, allow_unknown=False)

        res = self.client._favorite_exists_in_view_with_retries(456, attempts=1, allow_unknown=True)
        self.assertIsNone(res)

    def test_request_body_with_rate_limit_retries(self, mock_sleep: MagicMock) -> None:
        # First rate limited, second ok
        self.mock_req.side_effect = [
            "<body>This page is temporarily rate limited. (HTTP 429)</body>",
            "<body>success!</body>"
        ]
        res = self.client._request_body_with_rate_limit_retries(url="http://test", attempts=3)
        self.assertEqual(res, "success!")
        mock_sleep.assert_called_once_with(1.0)

    def test_probe_web_login_success(self, mock_sleep: MagicMock) -> None:
        # First URL (account_home_url) returns authenticated page
        self.mock_req.return_value = "<html><body>page=account&s=logout</body></html>"
        self.assertTrue(self.client._probe_web_login())

    def test_probe_web_login_fail_then_success(self, mock_sleep: MagicMock) -> None:
        # First URL fails with error, second URL succeeds
        self.mock_req.side_effect = [
            FlareSolverrError("solver error"),
            "<html><body>page=account&s=logout</body></html>"
        ]
        self.assertTrue(self.client._probe_web_login())

    def test_probe_web_login_all_fail(self, mock_sleep: MagicMock) -> None:
        self.mock_req.return_value = "<html><body>Login Form: name=\"user\" name=\"pass\"</body></html>"
        self.assertFalse(self.client._probe_web_login())

    def test_ensure_web_login_already_auth(self, mock_sleep: MagicMock) -> None:
        self.client._web_session_authenticated = True
        with patch.object(FlareSolverrFavoritesClient, "_probe_web_login") as mock_probe:
            self.client._ensure_web_login()
            mock_probe.assert_not_called()

    def test_ensure_web_login_missing_credentials(self, mock_sleep: MagicMock) -> None:
        client_no_creds = FlareSolverrFavoritesClient(user_id="123", api_key="abc")
        with self.assertRaises(FlareSolverrError):
            client_no_creds._ensure_web_login()

    def test_ensure_web_login_performs_login(self, mock_sleep: MagicMock) -> None:
        with patch.object(FlareSolverrFavoritesClient, "_probe_web_login") as mock_probe:
            # probe_web_login returns False initially, then True after POSTing
            mock_probe.side_effect = [False, True]
            self.client._ensure_web_login()

            self.mock_post.assert_called_once()
            self.assertTrue(self.client._web_session_authenticated)

    def test_ensure_web_login_fails_inconclusive(self, mock_sleep: MagicMock) -> None:
        with patch.object(FlareSolverrFavoritesClient, "_probe_web_login") as mock_probe:
            # Always returns False to simulate failing verification
            mock_probe.return_value = False
            self.client._ensure_web_login()

            self.mock_post.assert_called_once()
            self.assertFalse(self.client._web_session_authenticated)

    def test_list_favorites_dapi_success_json_list(self, mock_sleep: MagicMock) -> None:
        self.mock_req.return_value = '[{"id": "1001", "tags": "tag1 tag2"}]'
        posts = self.client.list_favorites(10)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].id, 1001)

    def test_list_favorites_dapi_success_json_dict_post(self, mock_sleep: MagicMock) -> None:
        self.mock_req.return_value = '{"post": {"id": "1002", "tags": "tag3"}}'
        posts = self.client.list_favorites(10)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].id, 1002)

    def test_list_favorites_dapi_success_xml(self, mock_sleep: MagicMock) -> None:
        self.mock_req.return_value = '<posts><post id="1003" tags="tag4"/></posts>'
        posts = self.client.list_favorites(10)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].id, 1003)

    def test_list_favorites_dapi_failure_raised(self, mock_sleep: MagicMock) -> None:
        self.mock_req.return_value = '{"success": false, "message": "API Key Invalid"}'
        with self.assertRaises(FlareSolverrError):
            self.client.list_favorites(10)

    @patch("r34_client.api.hydration.hydrate_posts")
    def test_list_favorites_fallback_to_html(self, mock_hydrate: MagicMock, mock_sleep: MagicMock) -> None:
        with patch.object(FlareSolverrFavoritesClient, "_ensure_web_login") as mock_login:
            # First request (DAPI) raises FlareSolverrError (e.g. rate limit / endpoint block)
            # Second request (HTML fallback) returns HTML list of favorites
            self.mock_req.side_effect = [
                FlareSolverrError("DAPI block"),
                '<html><body><span class="thumb"><a href="index.php?page=post&s=view&id=2001"><img src="thumb_2001.jpg"/></a></span><!-- rule34 --></body></html>'
            ]
            
            posts = self.client.list_favorites(1)
            
            mock_login.assert_called_once()
            self.assertEqual(len(posts), 1)
            self.assertEqual(posts[0].id, 2001)
            mock_hydrate.assert_called_once()

    def test_list_favorites_dapi_and_html_empty(self, mock_sleep: MagicMock) -> None:
        with patch.object(FlareSolverrFavoritesClient, "_ensure_web_login") as mock_login:
            self.mock_req.side_effect = [
                FlareSolverrError("DAPI block"),
                '<html><body>Empty favorites list (rule34)</body></html>',
                '<html><body>Empty favorites list (rule34)</body></html>'
            ]
            
            posts = self.client.list_favorites(10)
            self.assertEqual(posts, [])

    def test_add_favorite_success(self, mock_sleep: MagicMock) -> None:
        with patch.object(FlareSolverrFavoritesClient, "_ensure_web_login") as mock_login, \
             patch.object(FlareSolverrFavoritesClient, "_favorite_exists_in_view_with_retries") as mock_exists:
            
            # API add returns success, exists check confirms
            self.mock_req.return_value = "<body>success</body>"
            mock_exists.return_value = True
            
            self.client.add_favorite(3001)
            
            mock_login.assert_called_once()
            mock_exists.assert_called_once_with(3001, attempts=2, allow_unknown=False)

    def test_add_favorite_needs_login_retry(self, mock_sleep: MagicMock) -> None:
        with patch.object(FlareSolverrFavoritesClient, "_ensure_web_login") as mock_login, \
             patch.object(FlareSolverrFavoritesClient, "_destroy_session") as mock_destroy, \
             patch.object(FlareSolverrFavoritesClient, "_favorite_exists_in_view_with_retries") as mock_exists:
            
            # First request to add: body is "2" (not logged in)
            # Second request to add (after re-login): succeeds
            self.mock_req.side_effect = [
                "<body>2</body>",
                "<body>success</body>"
            ]
            mock_exists.return_value = True
            
            self.client.add_favorite(3002)
            
            self.assertEqual(mock_destroy.call_count, 1)
            self.assertEqual(mock_login.call_count, 2)
            self.assertEqual(self.mock_req.call_count, 2)

    def test_add_favorite_fallback_to_web_url(self, mock_sleep: MagicMock) -> None:
        with patch.object(FlareSolverrFavoritesClient, "_ensure_web_login") as mock_login, \
             patch.object(FlareSolverrFavoritesClient, "_favorite_exists_in_view_with_retries") as mock_exists:
            
            # First request: returns "2" (not logged in)
            # Second request (after re-login): still returns "2" (e.g. public API block)
            # Third request (fallback to web add URL): returns success
            self.mock_req.side_effect = [
                "<body>2</body>",
                "<body>2</body>",
                "<body>ok web add</body>"
            ]
            mock_exists.return_value = True
            
            self.client.add_favorite(3003)
            
            self.assertEqual(self.mock_req.call_count, 3)

    def test_add_favorite_fails_verification(self, mock_sleep: MagicMock) -> None:
        with patch.object(FlareSolverrFavoritesClient, "_ensure_web_login") as mock_login, \
             patch.object(FlareSolverrFavoritesClient, "_favorite_exists_in_view_with_retries") as mock_exists:
            
            self.mock_req.return_value = "<body>success</body>"
            # exists check says False (it didn't stick)
            mock_exists.return_value = False
            
            with self.assertRaises(FlareSolverrError):
                self.client.add_favorite(3004)

    def test_remove_favorite_already_absent(self, mock_sleep: MagicMock) -> None:
        with patch.object(FlareSolverrFavoritesClient, "_favorite_exists_in_view") as mock_exists, \
             patch.object(FlareSolverrFavoritesClient, "_ensure_web_login") as mock_login:
            
            mock_exists.return_value = False
            self.client.remove_favorite(4001)
            self.mock_req.assert_not_called()
            mock_login.assert_called_once()

    def test_remove_favorite_success(self, mock_sleep: MagicMock) -> None:
        with patch.object(FlareSolverrFavoritesClient, "_favorite_exists_in_view") as mock_exists_before, \
             patch.object(FlareSolverrFavoritesClient, "_ensure_web_login") as mock_login, \
             patch.object(FlareSolverrFavoritesClient, "_favorite_exists_in_view_with_retries") as mock_exists_after:
            
            mock_exists_before.return_value = True
            self.mock_req.return_value = "<body>deleted successfully</body>"
            mock_exists_after.return_value = False # deleted!
            
            self.client.remove_favorite(4002)
            
            mock_login.assert_called_once()
            mock_exists_after.assert_called_once_with(4002, attempts=2, allow_unknown=True)

    def test_remove_favorite_not_logged_in_retry(self, mock_sleep: MagicMock) -> None:
        with patch.object(FlareSolverrFavoritesClient, "_favorite_exists_in_view") as mock_exists_before, \
             patch.object(FlareSolverrFavoritesClient, "_ensure_web_login") as mock_login, \
             patch.object(FlareSolverrFavoritesClient, "_favorite_exists_in_view_with_retries") as mock_exists_after:
            
            mock_exists_before.return_value = True
            # First delete request returns "2"
            # Second delete request returns success
            self.mock_req.side_effect = [
                "<body>2</body>",
                "<body>deleted</body>"
            ]
            mock_exists_after.return_value = False
            
            self.client.remove_favorite(4003)
            
            self.assertEqual(mock_login.call_count, 2)
            self.assertEqual(self.mock_req.call_count, 2)

    def test_context_manager(self, mock_sleep: MagicMock) -> None:
        with patch.object(FlareSolverrFavoritesClient, "close") as mock_close:
            with self.client as c:
                self.assertIs(c, self.client)
            mock_close.assert_called_once()
