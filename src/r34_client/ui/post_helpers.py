from __future__ import annotations

import requests

from ..models import Post


def is_video_post(post: Post) -> bool:
    candidates = [post.file_url, post.sample_url, post.preview_url]
    video_extensions = (".webm", ".mp4", ".mov", ".mkv")
    lowered = " ".join(item.lower() for item in candidates if item)
    return any(ext in lowered for ext in video_extensions)


def format_millis(value: int) -> str:
    total_seconds = max(int(value) // 1000, 0)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def needs_hydration(post: Post, hydrated_ids: set[int]) -> bool:
    needs = (
        post.score is None
        or post.file_size is None
        or not post.source
        or not post.file_url
        or not post.tags
    )
    if post.id in hydrated_ids and not needs:
        return False
    return needs


def probe_file_size(url: str, referer: str) -> int | None:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": referer,
        "Accept": "*/*",
    }
    try:
        head = requests.head(url, timeout=15, headers=headers, allow_redirects=True)
        if head.ok:
            content_length = head.headers.get("Content-Length")
            if content_length and content_length.isdigit():
                return int(content_length)
    except Exception:
        pass

    try:
        ranged_headers = {**headers, "Range": "bytes=0-0"}
        resp = requests.get(url, timeout=20, headers=ranged_headers, stream=True)
        if resp.status_code in (200, 206):
            content_range = resp.headers.get("Content-Range", "")
            if "/" in content_range:
                total = content_range.rsplit("/", 1)[-1].strip()
                if total.isdigit():
                    return int(total)
            content_length = resp.headers.get("Content-Length")
            if content_length and content_length.isdigit():
                return int(content_length)
    except Exception:
        return None
    return None


def format_post_metadata(post: Post) -> str:
    lines = [
        f"ID: {post.id}",
        f"Rating: {post.rating or 'unknown'}",
        f"Score: {post.score if post.score is not None else 'n/a'}",
        f"Dimensions: {post.dimensions}",
        f"File name: {post.file_name}",
        f"File size: {post.file_size if post.file_size is not None else 'n/a'}",
        f"Created: {post.created_at or 'n/a'}",
        f"Page: {post.page_url}",
        f"Download: {post.download_url or 'n/a'}",
        f"Source: {post.source or 'n/a'}",
        "",
        "Tags:",
        post.tags_text or 'n/a',
    ]
    return "\n".join(lines)


def format_post_tile(post: Post) -> str:
    score = post.score if post.score is not None else "n/a"
    return f"#{post.id}  {post.rating or 'unknown'}  score:{score}"


def download_url_needs_hydration(url: str) -> bool:
    lowered = (url or "").lower()
    if not lowered:
        return True
    return "/thumbnails/" in lowered or "thumbnail_" in lowered
