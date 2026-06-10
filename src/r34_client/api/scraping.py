from __future__ import annotations

import json
from typing import TYPE_CHECKING
import requests

from r34_client.api.flaresolverr.parsing import extract_body_text, extract_items
from r34_client.api.urls import favorites_view_url
from r34_client.core.models import Post

if TYPE_CHECKING:
    from r34_client.api.client import Rule34Client


def fetch_page(url: str, flare_solver_url: str = "") -> str | None:
    """Fetch HTML page either directly or through FlareSolverr to bypass Cloudflare."""
    if not flare_solver_url:
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            }
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException:
            return None

    try:
        payload = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": 30000,
        }
        resp = requests.post(
            f"{flare_solver_url.rstrip('/')}/v1",
            json=payload,
            timeout=35,
        )
        resp.raise_for_status()
        body = resp.json()
        solution = body.get("solution", {})
        return solution.get("response")
    except (requests.RequestException, json.JSONDecodeError):
        return None


def parse_scraped_favorites(html: str) -> list[Post]:
    """Parse favorites page HTML and extract basic post information (IDs and preview URLs)."""
    body = extract_body_text(html)
    items = extract_items(body)

    posts: list[Post] = []
    seen: set[int] = set()
    for post_id, preview_url in items:
        if post_id in seen:
            continue
        seen.add(post_id)
        post = Post(
            id=post_id,
            tags=[],
            rating="",
            score=None,
            width=None,
            height=None,
            file_size=None,
            source="",
            md5="",
            preview_url=preview_url,
            sample_url="",
            file_url="",
            created_at="",
        )
        posts.append(post)
    return posts


def fetch_friend_favorites(
    client: Rule34Client,
    user_id: str,
    flare_solver_url: str,
    page: int = 0,
) -> list[Post]:
    """Fetch and parse friend's favorites page from Rule34.

    The returned posts will only have ID and preview_url populated.
    """
    api_page = page // 5
    pid = api_page * 50
    url = favorites_view_url(user_id, page=pid)
    html = fetch_page(url, flare_solver_url=flare_solver_url)
    if html is None:
        msg = f"Failed to fetch favorites for user {user_id} (page {page})"
        raise RuntimeError(msg)
    return parse_scraped_favorites(html)
