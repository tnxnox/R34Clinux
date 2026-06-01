from __future__ import annotations

import os
import time
import json
import requests
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from r34_client.core.models import Post
    from r34_client.core.settings import AppSettings
    from r34_client.core.db import LocalFavoritesStore


class DownloadManager:
    def __init__(self, db: LocalFavoritesStore) -> None:
        self.db = db

    def _format_template(self, template: str, post: Post, is_path: bool = False) -> str:
        def sanitize(segment: str) -> str:
            # Allow alphabetic, numeric, space, dot, underscore, dash
            return "".join(c for c in segment if c.isalnum() or c in (" ", ".", "_", "-")).strip()

        try:
            formatted = template.format(
                id=post.id,
                md5=post.md5 or "unknown",
                score=post.score if post.score is not None else 0,
                rating=post.rating or "unknown",
            )
        except (KeyError, ValueError):
            formatted = str(post.id)

        if is_path:
            # For paths, we split by / and sanitize each segment to avoid path traversal
            segments = formatted.replace("\\", "/").split("/")
            sanitized_segments = [sanitize(s) for s in segments if s.strip() and s.strip() != ".."]
            return os.path.join(*sanitized_segments) if sanitized_segments else ""
        else:
            return sanitize(formatted)

    def format_filename(self, post: Post, template: str, use_sample: bool = False) -> str:
        url = post.sample_url if use_sample and post.sample_url else post.file_url
        if not url:
            url = post.preview_url

        ext = ".jpg"
        if url:
            from urllib.parse import urlparse
            path = urlparse(url).path
            ext = os.path.splitext(path)[1] or ".jpg"

        name = self._format_template(template, post, is_path=False)
        if not name:
            name = str(post.id)
        return f"{name}{ext}"

    def download_post(self, post: Post, settings: AppSettings) -> Path | None:
        if not post.file_url and not post.sample_url:
            raise RuntimeError("Post has no downloadable content.")

        if self.db.is_downloaded(post.id, post.md5):
            return None

        base_dir = settings.download_directory
        if not base_dir:
            from r34_client.core.settings import SettingsStore
            base_dir = SettingsStore.default_download_directory()

        # Handle subfolder template
        subfolder = ""
        if settings.download_path_template:
            subfolder = self._format_template(settings.download_path_template, post, is_path=True)

        filename = self.format_filename(
            post, settings.download_naming_template or "{id}", settings.download_use_sample
        )

        dest = Path(base_dir) / subfolder / filename

        # Handle filename collisions
        if dest.exists():
            dest = dest.with_name(f"{dest.stem}_{post.id}{dest.suffix}")

        dest.parent.mkdir(parents=True, exist_ok=True)

        url = post.sample_url if settings.download_use_sample and post.sample_url else post.file_url
        if not url:
            url = post.preview_url

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": post.page_url,
        }

        # Retry logic
        max_retries = max(0, settings.download_max_retries)

        for attempt in range(max_retries + 1):
            try:
                with requests.get(url, timeout=60, stream=True, headers=headers) as response:
                    response.raise_for_status()

                    with dest.open("wb") as f:
                        for chunk in response.iter_content(chunk_size=1024 * 64):
                            if chunk:
                                f.write(chunk)
                break  # Success
            except requests.RequestException as e:
                if attempt < max_retries:
                    time.sleep(2**attempt)  # Exponential backoff
                    continue
                else:
                    if dest.exists():
                        dest.unlink()  # Cleanup partial download
                    raise RuntimeError(f"Failed to download post {post.id} after {max_retries} retries: {e}") from e

        if settings.download_sidecar_enabled:
            self._write_sidecar(dest, post, settings.download_sidecar_format)

        self.db.record_download(post.id, post.md5, str(dest))
        return dest

    def _write_sidecar(self, media_path: Path, post: Post, fmt: str = "json") -> None:
        fmt = fmt.lower()
        if fmt in ("json", "both"):
            sidecar = media_path.with_suffix(".json")
            data = {
                "id": post.id,
                "tags": post.tags,
                "score": post.score,
                "rating": post.rating,
                "md5": post.md5,
                "source": post.source,
                "created_at": post.created_at,
            }
            sidecar.write_text(json.dumps(data, indent=2), encoding="utf-8")

        if fmt in ("txt", "both"):
            sidecar = media_path.with_suffix(".txt")
            sidecar.write_text(post.tags_text, encoding="utf-8")
