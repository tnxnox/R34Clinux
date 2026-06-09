from __future__ import annotations

import logging
import shutil
import time
import json
import os
import requests
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from r34_client.core.models import Post
    from r34_client.core.settings import AppSettings
    from r34_client.core.db import LocalFavoritesStore

logger = logging.getLogger(__name__)

# Maximum allowed download size: 500 MB
MAX_DOWNLOAD_BYTES = 500 * 1024 * 1024


class DownloadManager:
    def __init__(self, db: LocalFavoritesStore) -> None:
        self.db = db

    def _sanitize_path_segment(self, segment: str) -> str:
        """Sanitize a single path segment, allowing only safe characters."""
        return "".join(c for c in segment if c.isalnum() or c in (" ", ".", "_", "-")).strip(". ")

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
            # For paths, split by / and sanitize each segment to avoid path traversal
            segments = formatted.replace("\\", "/").split("/")
            sanitized_segments = [
                self._sanitize_path_segment(s)
                for s in segments
                if s.strip() and self._sanitize_path_segment(s.strip()) not in (".", "..", "~")
            ]
            # Build result and verify it stays within base directory (resolved later)
            return str(Path(*sanitized_segments)) if sanitized_segments else ""
        else:
            return sanitize(formatted)

    def _validate_path_within_base(self, full_path: Path, base_dir: Path) -> None:
        """Ensure the resolved path stays within the base directory (path traversal guard)."""
        resolved_full = full_path.resolve()
        resolved_base = base_dir.resolve()
        try:
            resolved_full.relative_to(resolved_base)
        except ValueError:
            raise ValueError(
                f"Path traversal detected: {resolved_full} is outside {resolved_base}"
            )

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

    def _check_disk_space(self, dest: Path, required_bytes: int) -> None:
        """Check that there's enough free disk space at the destination."""
        try:
            stat = shutil.disk_usage(dest.parent)
            if stat.free < required_bytes:
                raise RuntimeError(
                    f"Insufficient disk space: need {required_bytes / (1024*1024):.1f} MB, "
                    f"have {stat.free / (1024*1024):.1f} MB at {dest.parent}"
                )
        except OSError as e:
            logger.warning("Could not check disk space: %s", e)

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

        # Validate path stays within base directory (path traversal protection)
        self._validate_path_within_base(dest, Path(base_dir))

        # Handle filename collisions
        if dest.exists():
            dest = dest.with_name(f"{dest.stem}_{post.id}{dest.suffix}")

        # Handle unwritable download path
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            raise PermissionError(
                f"Cannot write to download directory: {dest.parent}. "
                "Check directory permissions or configure a different download path in Settings."
            )

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
                    # Graceful error for deleted content (HTTP 404/410)
                    if response.status_code in (404, 410):
                        raise RuntimeError(
                            f"Post #{post.id} no longer available on server "
                            f"(HTTP {response.status_code}) - the content may have been deleted."
                        )
                    response.raise_for_status()

                    # Check Content-Length to prevent oversized downloads
                    content_length = response.headers.get("content-length")
                    if content_length:
                        try:
                            expected_size = int(content_length)
                        except ValueError:
                            logger.warning("Malformed Content-Length header: %r, ignoring size limit", content_length)
                        else:
                            if expected_size > MAX_DOWNLOAD_BYTES:
                                raise RuntimeError(
                                    f"Download too large: {expected_size / (1024*1024):.1f} MB "
                                    f"(max {MAX_DOWNLOAD_BYTES / (1024*1024):.0f} MB)"
                                )
                            # Check disk space beforehand
                            self._check_disk_space(dest, expected_size * 2)

                    # Check disk space with a reasonable default even without content-length
                    if not content_length:
                        self._check_disk_space(dest, MAX_DOWNLOAD_BYTES)

                    bytes_downloaded = 0
                    read_start = time.monotonic()
                    max_read_duration = 120  # max seconds for the streaming loop
                    try:
                        with dest.open("wb") as f:
                            for chunk in response.iter_content(chunk_size=1024 * 64):
                                if chunk:
                                    bytes_downloaded += len(chunk)
                                    if bytes_downloaded > MAX_DOWNLOAD_BYTES:
                                        raise RuntimeError(
                                            f"Download exceeded maximum size of "
                                            f"{MAX_DOWNLOAD_BYTES / (1024*1024):.0f} MB"
                                        )
                                    # Enforce a total read timeout to prevent indefinite hangs
                                    if time.monotonic() - read_start > max_read_duration:
                                        raise RuntimeError(
                                            f"Download timed out after {max_read_duration}s "
                                            f"({bytes_downloaded / (1024*1024):.1f} MB received)"
                                        )
                                    f.write(chunk)
                    except PermissionError:
                        raise PermissionError(
                            f"Cannot write to {dest}. "
                            "Check directory permissions or configure a different download path in Settings."
                        )
                break  # Success
            except requests.RequestException as e:
                if attempt < max_retries:
                    wait = 2**attempt
                    logger.warning(
                        "Download attempt %d/%d failed for post %d: %s. Retrying in %ds...",
                        attempt + 1, max_retries + 1, post.id, e, wait,
                    )
                    time.sleep(wait)
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
