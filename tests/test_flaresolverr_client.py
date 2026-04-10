from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import requests

from r34_client.flaresolverr_client import FlareSolverrError, FlareSolverrFavoritesClient


class FakeResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def json(self) -> dict[str, object]:
        return self._payload


class FlareSolverrClientTests(unittest.TestCase):
    def test_login_marker_detection_is_strict(self) -> None:
        self.assertFalse(FlareSolverrFavoritesClient._looks_logged_in("<html>My Account</html>"))
        self.assertTrue(FlareSolverrFavoritesClient._looks_logged_in("/index.php?page=account&s=logout"))

    def test_list_favorites_parses_posts(self) -> None:
        session_payload = {
            "status": "ok",
            "session": "r34-1",
        }
        solver_payload = {
            "status": "ok",
            "solution": {
                "response": json.dumps(
                    [
                        {
                            "id": "100",
                            "tags": "tag_x",
                            "rating": "s",
                            "preview_url": "https://img/p.jpg",
                            "sample_url": "https://img/s.jpg",
                            "file_url": "https://img/f.jpg",
                        }
                    ]
                )
            },
        }

        with patch(
            "r34_client.flaresolverr_client.requests.post",
            side_effect=[FakeResponse(session_payload), FakeResponse(solver_payload)],
        ):
            client = FlareSolverrFavoritesClient(user_id="1", api_key="secret")
            posts = client.list_favorites(limit=10)

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].id, 100)

    def test_add_favorite_calls_solver(self) -> None:
        with (
            patch.object(FlareSolverrFavoritesClient, "_ensure_web_login", return_value=None),
            patch.object(FlareSolverrFavoritesClient, "_favorite_exists_in_view", return_value=False),
            patch.object(FlareSolverrFavoritesClient, "_favorite_exists_in_view_with_retries", return_value=True),
            patch.object(
                FlareSolverrFavoritesClient,
                "_request_via_solver",
                return_value="<html><head></head><body>0</body></html>",
            ) as request_mock,
        ):
            client = FlareSolverrFavoritesClient(user_id="1", api_key="secret")
            client.add_favorite(321)

        request_mock.assert_called_once_with("https://rule34.xxx/public/addfav.php?id=321", headers=None)

    def test_add_favorite_raises_when_not_logged_in(self) -> None:
        with (
            patch.object(FlareSolverrFavoritesClient, "_ensure_web_login", return_value=None),
            patch.object(FlareSolverrFavoritesClient, "_favorite_exists_in_view", return_value=False),
            patch.object(
                FlareSolverrFavoritesClient,
                "_request_via_solver",
                return_value="<html><head></head><body>2</body></html>",
            ),
        ):
            client = FlareSolverrFavoritesClient(user_id="1", api_key="secret")
            with self.assertRaises(FlareSolverrError):
                client.add_favorite(321)

    def test_remove_favorite_uses_web_delete_endpoint(self) -> None:
        with (
            patch.object(FlareSolverrFavoritesClient, "_ensure_web_login", return_value=None),
            patch.object(
                FlareSolverrFavoritesClient,
                "_request_via_solver",
                side_effect=[
                    '<a href="index.php?page=post&s=view&id=321">x</a>',
                    "<html>ok</html>",
                    "<html>done</html>",
                ],
            ) as request_mock,
        ):
            client = FlareSolverrFavoritesClient(user_id="1", api_key="secret")
            client.remove_favorite(321)

        first_call = request_mock.call_args_list[1]
        first_call_args = first_call.args
        first_call_kwargs = first_call.kwargs
        self.assertEqual(
            first_call_args[0],
            "https://rule34.xxx/index.php?page=favorites&s=delete&id=321&return_pid=0",
        )
        self.assertEqual(first_call_kwargs["headers"], {"Referer": "https://rule34.xxx/index.php?page=favorites&s=view&id=1"})

    def test_remove_favorite_retries_when_rate_limited(self) -> None:
        rate_limited_html = "<div>429 Rate limiting</div>"
        with (
            patch.object(FlareSolverrFavoritesClient, "_ensure_web_login", return_value=None),
            patch.object(FlareSolverrFavoritesClient, "_request_via_solver") as request_mock,
            patch("r34_client.flaresolverr_client.time.sleep", return_value=None),
        ):
            request_mock.side_effect = [
                '<a href="index.php?page=post&s=view&id=321">x</a>',
                rate_limited_html,
                "<html>ok</html>",
                "<html>done</html>",
            ]
            client = FlareSolverrFavoritesClient(user_id="1", api_key="secret")
            client.remove_favorite(321)

        delete_calls = [
            call for call in request_mock.call_args_list if "s=delete&id=321" in call.args[0]
        ]
        self.assertEqual(len(delete_calls), 2)
        self.assertEqual(
            delete_calls[0].kwargs.get("headers"),
            {"Referer": "https://rule34.xxx/index.php?page=favorites&s=view&id=1"},
        )

    def test_remove_favorite_allows_unknown_state_when_view_rate_limited(self) -> None:
        rate_limited_html = "<div>429 Rate limiting</div>"
        with (
            patch.object(FlareSolverrFavoritesClient, "_ensure_web_login", return_value=None),
            patch.object(FlareSolverrFavoritesClient, "_request_via_solver") as request_mock,
            patch("r34_client.flaresolverr_client.time.sleep", return_value=None),
        ):
            request_mock.side_effect = [
                '<a href="index.php?page=post&s=view&id=321">x</a>',
                "<html>ok</html>",
                rate_limited_html,
                rate_limited_html,
                rate_limited_html,
            ]
            client = FlareSolverrFavoritesClient(user_id="1", api_key="secret")
            client.remove_favorite(321)

    def test_remove_favorite_does_not_call_api_delete(self) -> None:
        with (
            patch.object(FlareSolverrFavoritesClient, "_ensure_web_login", return_value=None),
            patch.object(FlareSolverrFavoritesClient, "_request_via_solver") as request_mock,
        ):
            request_mock.side_effect = [
                '<a href="index.php?page=post&s=view&id=321">x</a>',
                "<html>ok</html>",
                "<html>done</html>",
            ]
            client = FlareSolverrFavoritesClient(user_id="1", api_key="secret")
            client.remove_favorite(321)

        called_urls = [call.args[0] for call in request_mock.call_args_list]
        self.assertFalse(any("page=dapi&s=favorite&q=delete" in url for url in called_urls))

    def test_ensure_session_retries_transient_failures(self) -> None:
        session_payload = {
            "status": "ok",
            "session": "r34-1",
        }

        with (
            patch(
                "r34_client.flaresolverr_client.requests.post",
                side_effect=[requests.ConnectionError("boom"), FakeResponse(session_payload)],
            ),
            patch("r34_client.flaresolverr_client.time.sleep", return_value=None),
        ):
            client = FlareSolverrFavoritesClient(user_id="1", api_key="secret")
            client._ensure_session()

    def test_add_favorite_requires_website_credentials(self) -> None:
        with patch.object(
            FlareSolverrFavoritesClient,
            "_request_via_solver",
            return_value="<html><body>not logged</body></html>",
        ):
            client = FlareSolverrFavoritesClient(user_id="1", api_key="secret")
            with self.assertRaises(FlareSolverrError):
                client.add_favorite(321)

    def test_list_favorites_falls_back_to_html_when_dapi_empty(self) -> None:
        session_payload = {
            "status": "ok",
            "session": "r34-1",
        }
        dapi_empty = {
            "status": "ok",
            "solution": {
                "response": "[]",
            },
        }
        html_payload = {
            "status": "ok",
            "solution": {
                "response": (
                    '<a href="index.php?page=post&s=view&id=77">A</a>'
                    '<img src="//img.test/p77.jpg">'
                    '<a href="index.php?page=post&s=view&id=88">B</a>'
                    '<img src="https://img.test/p88.jpg">'
                )
            },
        }

        with patch(
            "r34_client.flaresolverr_client.requests.post",
            side_effect=[
                FakeResponse(session_payload),
                FakeResponse(dapi_empty),
                FakeResponse(html_payload),
            ],
        ):
            client = FlareSolverrFavoritesClient(user_id="1", api_key="secret")
            posts = client.list_favorites(limit=2)

        self.assertEqual([post.id for post in posts], [77, 88])
        self.assertEqual(posts[0].preview_url, "https://img.test/p77.jpg")

    def test_list_favorites_falls_back_to_html_on_dapi_parse_error(self) -> None:
        with patch.object(
            FlareSolverrFavoritesClient,
            "_request_via_solver",
            side_effect=[
                "<html><div>unexpected</div></html>",
                '<a href="index.php?page=post&s=view&id=44">A</a><img src="//img.test/p44.jpg">',
            ],
        ):
            client = FlareSolverrFavoritesClient(user_id="1", api_key="secret")
            posts = client.list_favorites(limit=1)

        self.assertEqual([post.id for post in posts], [44])
        self.assertEqual(posts[0].preview_url, "https://img.test/p44.jpg")


if __name__ == "__main__":
    unittest.main()
