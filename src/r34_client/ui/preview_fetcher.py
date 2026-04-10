from __future__ import annotations

from urllib.parse import urlparse

import requests

from ..models import Post


def normalize_media_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    if value.startswith("//"):
        return f"https:{value}"
    if value.startswith("http://"):
        return f"https://{value[7:]}"
    return value


def preview_candidate_urls(post: Post) -> list[str]:
    candidates = [
        normalize_media_url(post.file_url),
        normalize_media_url(post.preview_url),
        normalize_media_url(post.sample_url),
    ]

    expanded: list[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        expanded.append(candidate)
        parsed = urlparse(candidate)
        host = parsed.netloc.lower()
        if host == "wimg.rule34.xxx":
            expanded.append(candidate.replace("https://wimg.rule34.xxx", "https://img.rule34.xxx", 1))
        elif host == "img.rule34.xxx":
            expanded.append(candidate.replace("https://img.rule34.xxx", "https://wimg.rule34.xxx", 1))

    seen: set[str] = set()
    ordered: list[str] = []
    for value in expanded:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def preview_referers(post: Post, user_id: str = "") -> list[str]:
    referers = [post.page_url, "https://rule34.xxx/"]
    if user_id.strip():
        referers.insert(1, f"https://rule34.xxx/index.php?page=favorites&s=view&id={user_id.strip()}")
    return referers


def fetch_preview_bytes(post: Post, user_id: str = "") -> bytes:
    urls = preview_candidate_urls(post)
    if not urls:
        raise RuntimeError("This post does not expose a preview URL.")

    last_error = ""
    for url in urls:
        for referer in preview_referers(post, user_id=user_id):
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": referer,
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            }
            try:
                response = requests.get(url, timeout=30, headers=headers)
                if response.status_code == 403:
                    last_error = f"403 for {url} (referer={referer})"
                    continue
                response.raise_for_status()
                return response.content
            except requests.RequestException as exc:
                last_error = str(exc)

    raise RuntimeError(last_error or "Preview unavailable after retries.")
