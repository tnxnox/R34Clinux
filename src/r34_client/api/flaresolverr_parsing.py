from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import parse_qs, urlparse
from xml.etree import ElementTree as ET


def _normalize_html_text(value: str) -> str:
    normalized = html.unescape(value or "")
    # Some responses include serialized HTML fragments (escaped quotes/slashes).
    return normalized.replace('\\"', '"').replace("\\'", "'").replace("\\/", "/")


def decode_payload(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        return []

    if stripped.startswith("{") or stripped.startswith("["):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

    try:
        return ET.fromstring(stripped)
    except ET.ParseError as exc:
        raise RuntimeError("Unable to parse response returned via FlareSolverr.") from exc


def extract_body_text(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""

    match = re.search(r"<body[^>]*>(.*?)</body>", text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def looks_rate_limited(text: str) -> bool:
    lowered = (text or "").lower()
    return (
        "429" in lowered and "rate" in lowered
    ) or "too many requests" in lowered


def looks_logged_in(html_text: str) -> bool:
    lowered = (html_text or "").lower()
    return (
        "page=account&s=logout" in lowered
        or "s=logout" in lowered
        or "page=account&s=login&code=01" in lowered
        or "logout of your account" in lowered
        or "page=account&s=change_password" in lowered
    )


def extract_post_ids(html_text: str) -> list[int]:
    normalized = _normalize_html_text(html_text)
    seen: set[int] = set()
    ids: list[int] = []

    href_matches = re.findall(r"href\s*=\s*['\"]([^'\"]+)['\"]", normalized, flags=re.IGNORECASE)
    for href in href_matches:
        parsed = urlparse(href)
        query = parse_qs(parsed.query)
        if query.get("page", [""])[0] != "post":
            continue
        if query.get("s", [""])[0] != "view":
            continue
        post_id_raw = query.get("id", [""])[0]
        if not str(post_id_raw).isdigit():
            continue
        post_id = int(str(post_id_raw))
        if post_id in seen:
            continue
        seen.add(post_id)
        ids.append(post_id)

    if ids:
        return ids

    # Fallback for malformed links without a quoted href value.
    matches = re.findall(r"page=post(?:&|\?)s=view(?:&|\?)id=(\d+)", normalized)
    for value in matches:
        post_id = int(value)
        if post_id in seen:
            continue
        seen.add(post_id)
        ids.append(post_id)
    return ids


def extract_favorite_tile_ids(html_text: str) -> list[int]:
    normalized = _normalize_html_text(html_text)
    seen: set[int] = set()
    ids: list[int] = []

    for raw_id in re.findall(r"<a[^>]+id=['\"]p(\d+)['\"][^>]*>", normalized, flags=re.IGNORECASE):
        post_id = int(raw_id)
        if post_id in seen:
            continue
        seen.add(post_id)
        ids.append(post_id)
    return ids


def validate_favorites_html(html_text: str) -> None:
    if looks_rate_limited(html_text):
        raise RuntimeError("Rule34 request was rate limited.")

    if not looks_logged_in(html_text):
        raise RuntimeError("Rule34 session is not logged in / session expired.")

    lowered = html_text.lower()
    has_signature = (
        "rule34" in lowered
        or "rule 34" in lowered
        or "layout.css" in lowered
        or "page=account" in lowered
    )
    if not has_signature:
        raise RuntimeError("Invalid response: Not a Rule34 page.")

    if "cloudflare" in lowered and ("checking your browser" in lowered or "enable javascript" in lowered):
        raise RuntimeError("Rule34 request blocked by Cloudflare challenge.")


def validate_favorites_parsed_results(html_text: str, parsed_count: int) -> None:
    validate_favorites_html(html_text)

    if parsed_count == 0:
        lowered = html_text.lower()
        has_post_links = "page=post" in lowered or "/post/view" in lowered
        has_thumbnails = "/thumbnails/" in lowered or "preview.rule34.xxx" in lowered

        if has_post_links or has_thumbnails:
            raise RuntimeError(
                "Failed to parse favorites: Rule34 layout might have changed. "
                "Found thumbnail or post indicators in HTML, but extracted 0 items."
            )


def extract_items(html_text: str, validate: bool = False) -> list[tuple[int, str]]:
    if validate:
        validate_favorites_html(html_text)

    normalized = _normalize_html_text(html_text)

    tile_matches = re.findall(
        r"<a[^>]+id=['\"]p(\d+)['\"][^>]*>\s*<img[^>]+src=['\"]([^'\"]+)['\"]",
        normalized,
        flags=re.IGNORECASE,
    )
    if tile_matches:
        seen_tile_ids: set[int] = set()
        items: list[tuple[int, str]] = []
        for raw_id, preview in tile_matches:
            post_id = int(raw_id)
            if post_id in seen_tile_ids:
                continue
            seen_tile_ids.add(post_id)
            if preview.startswith("//"):
                preview = f"https:{preview}"
            items.append((post_id, preview))
        if validate:
            validate_favorites_parsed_results(html_text, len(items))
        return items

    ids = extract_post_ids(normalized)
    previews = re.findall(r'<img[^>]+src="([^"]+)"', normalized, flags=re.IGNORECASE)

    items: list[tuple[int, str]] = []
    for index, post_id in enumerate(ids):
        preview = previews[index] if index < len(previews) else ""
        if preview.startswith("//"):
            preview = f"https:{preview}"
        items.append((post_id, preview))

    if validate:
        validate_favorites_parsed_results(html_text, len(items))
    return items
