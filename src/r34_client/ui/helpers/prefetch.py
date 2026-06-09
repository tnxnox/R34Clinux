from __future__ import annotations

import threading
from collections import OrderedDict
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from r34_client.core.models import Post


import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ImageCache:
    """Bounded LRU cache for downloaded preview image bytes.

    Thread-safe — designed to be read from the UI (main) thread and
    written from background worker or daemon threads.
    """

    def __init__(self, max_size: int = 20, max_disk_size_bytes: int = 200 * 1024 * 1024) -> None:
        self._max_size = max_size
        self.max_disk_size_bytes = max_disk_size_bytes
        self._cache: OrderedDict[int, bytes] = OrderedDict()
        self._lock = threading.Lock()
        self._disk_lock = threading.Lock()

        # Resolve XDG cache directory
        xdg_cache = os.environ.get("XDG_CACHE_HOME")
        if xdg_cache:
            base = Path(xdg_cache)
        else:
            base = Path.home() / ".cache"
        self.cache_dir = base / "r34_client" / "previews"
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def get(self, post_id: int) -> bytes | None:
        with self._lock:
            if post_id in self._cache:
                self._cache.move_to_end(post_id)
                return self._cache[post_id]

        # Fallback to disk cache
        filepath = self.cache_dir / str(post_id)
        if filepath.exists():
            with self._disk_lock:
                try:
                    data = filepath.read_bytes()
                    try:
                        os.utime(filepath, None)
                    except OSError:
                        pass
                    
                    # Store in memory cache
                    with self._lock:
                        self._cache[post_id] = data
                        self._cache.move_to_end(post_id)
                        while len(self._cache) > self._max_size:
                            self._cache.popitem(last=False)
                    return data
                except Exception:
                    pass
        return None

    def put(self, post_id: int, data: bytes) -> None:
        if not data:
            return
        with self._lock:
            self._cache[post_id] = data
            self._cache.move_to_end(post_id)
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

        # Write to disk cache in a daemon background thread to keep UI fast
        threading.Thread(
            target=self._disk_write_and_evict_worker,
            args=(post_id, data),
            daemon=True
        ).start()

    def _disk_write_and_evict_worker(self, post_id: int, data: bytes) -> None:
        with self._disk_lock:
            try:
                filepath = self.cache_dir / str(post_id)
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                filepath.write_bytes(data)
                try:
                    os.utime(filepath, None)
                except OSError:
                    pass
                self._evict_disk_cache_if_needed()
            except Exception as e:
                logger.warning("Failed to write to disk cache: %s", e)

    def _evict_disk_cache_if_needed(self) -> None:
        try:
            files = []
            total_size = 0
            for entry in self.cache_dir.iterdir():
                if entry.is_file():
                    try:
                        stat = entry.stat()
                        files.append((entry, stat.st_size, stat.st_mtime))
                        total_size += stat.st_size
                    except OSError:
                        pass

            if total_size <= self.max_disk_size_bytes:
                return

            # Sort files by modification time (oldest first)
            files.sort(key=lambda x: x[2])

            for entry, size, _ in files:
                try:
                    entry.unlink()
                    total_size -= size
                except OSError:
                    pass
                if total_size <= self.max_disk_size_bytes:
                    break
        except Exception as e:
            logger.warning("Failed to evict disk cache: %s", e)

    def contains(self, post_id: int) -> bool:
        with self._lock:
            if post_id in self._cache:
                return True
        filepath = self.cache_dir / str(post_id)
        return filepath.exists()

    def remove(self, post_id: int) -> None:
        with self._lock:
            self._cache.pop(post_id, None)
        filepath = self.cache_dir / str(post_id)
        if filepath.exists():
            with self._disk_lock:
                try:
                    filepath.unlink()
                except OSError:
                    pass

    def invalidate(self) -> None:
        with self._lock:
            self._cache.clear()
        if self.cache_dir.exists():
            with self._disk_lock:
                for entry in self.cache_dir.iterdir():
                    if entry.is_file():
                        try:
                            entry.unlink()
                        except OSError:
                            pass

    @property
    def size(self) -> int:
        # Return count of files in disk cache + any unsaved memory ones
        try:
            with self._disk_lock:
                disk_count = sum(1 for entry in self.cache_dir.iterdir() if entry.is_file())
            return disk_count
        except Exception:
            with self._lock:
                return len(self._cache)

    @property
    def max_size(self) -> int:
        return self._max_size


def _best_prefetch_url(post: Post) -> str | None:
    """Return a single URL to prefetch, preferring sample over preview over file."""
    from r34_client.ui.helpers.preview_fetcher import preview_candidate_urls

    urls = preview_candidate_urls(post)
    return urls[0] if urls else None


def prefetch_images_batch(
    posts: list[Post],
    user_id: str,
    cache: ImageCache,
    *,
    limit: int = 5,
) -> int:
    """Download preview images for *posts* not already in *cache*.

    Returns the number of new images cached.  Runs synchronously — call from a
    background worker, never from the UI thread.
    """
    from r34_client.ui.helpers.preview_fetcher import preview_candidate_urls, preview_referers
    from r34_client.core.worker import check_cancelled

    fetched = 0
    with requests.Session() as session:
        for post in posts[:limit]:
            check_cancelled()
            if cache.contains(post.id):
                continue

            urls = preview_candidate_urls(post)
            if not urls:
                continue

            for referer in preview_referers(post, user_id=user_id):
                for url in urls:
                    check_cancelled()
                    try:
                        resp = session.get(
                            url,
                            timeout=15,
                            headers={
                                "User-Agent": (
                                    "Mozilla/5.0 (X11; Linux x86_64) "
                                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                                    "Chrome/124.0.0.0 Safari/537.36"
                                ),
                                "Referer": referer,
                                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                            },
                        )
                        if resp.status_code == 200:
                            cache.put(post.id, resp.content)
                            fetched += 1
                            break
                        if resp.status_code == 403:
                            continue  # try next referer/URL
                    except requests.RequestException:
                        continue
                else:
                    continue  # all URLs failed for this referer; try next referer
                break  # one URL + referer succeeded; move to next post

    return fetched


def prefetch_adjacent(
    current_post: Post,
    all_posts: list[Post],
    user_id: str,
    cache: ImageCache,
    *,
    count: int = 5,
) -> int:
    """Prefetch *count* posts on each side of *current_post* in *all_posts*.

    Skips posts already in the cache.  Runs synchronously — call from a
    background worker.
    """
    try:
        idx = all_posts.index(current_post)
    except ValueError:
        return 0

    candidates: list[Post] = []
    # Posts after the current one (most likely next navigation target)
    candidates.extend(all_posts[idx + 1 : idx + 1 + count])
    # Posts before the current one
    start = max(0, idx - count)
    candidates.extend(all_posts[start:idx])

    return prefetch_images_batch(candidates, user_id, cache)


def prefetch_metadata_batch(
    posts: list[Post],
    client,
    *,
    limit: int = 5,
) -> dict[int, Post]:
    """Hydrate metadata for *posts* not yet fully populated.

    Calls the API for each post that still has fields missing (score,
    file_url, tags, etc.) and returns a dict mapping post_id to the
    hydrated Post.  Runs synchronously — call from a background worker.
    """
    from r34_client.ui.helpers.post import needs_hydration

    results: dict[int, Post] = {}
    for post in posts[:limit]:
        if post.id in results:
            continue
        if not needs_hydration(post, set()):
            continue
        try:
            candidates = client.search_posts(f"id:{post.id}", 0, 1)
            if candidates:
                results[post.id] = candidates[0]
        except Exception:
            continue
    return results
