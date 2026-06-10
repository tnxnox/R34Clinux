from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from r34_client.core.models import Post


def hydrate_posts(
    client,
    posts: list[Post],
    *,
    start: int = 0,
    limit: int | None = None,
    max_workers: int = 10,
    force: bool = False,
) -> None:
    """Fetch full metadata for each post via the Rule34 API client in-place.

    Only hydrates posts that lack a file_url unless force=True.
    """
    end = start + limit if limit is not None else len(posts)
    indices_to_hydrate = []
    for i in range(start, min(end, len(posts))):
        if force or not posts[i].file_url:
            indices_to_hydrate.append(i)

    if not indices_to_hydrate:
        return

    def hydrate_single(index: int, post: Post) -> tuple[int, Post | None]:
        try:
            candidates = client.search_posts(f"id:{post.id}", 0, 1)
            if candidates:
                return index, candidates[0]
        except Exception:
            pass
        return index, None

    workers = min(len(indices_to_hydrate), max_workers)
    if workers <= 0:
        return

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(hydrate_single, idx, posts[idx])
            for idx in indices_to_hydrate
        ]
        for fut in futures:
            try:
                idx, hydrated_post = fut.result()
                if hydrated_post is not None:
                    posts[idx] = hydrated_post
            except Exception:
                continue


def hydrate_posts_copy(
    client,
    posts: list[Post],
    *,
    start: int = 0,
    limit: int | None = None,
    max_workers: int = 10,
    force: bool = False,
) -> list[Post]:
    """Return a copy of the posts list with specified posts hydrated."""
    posts_copy = list(posts)
    hydrate_posts(
        client,
        posts_copy,
        start=start,
        limit=limit,
        max_workers=max_workers,
        force=force,
    )
    return posts_copy
