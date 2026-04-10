from __future__ import annotations

from collections.abc import Callable

from ..config import AppSettings
from ..flaresolverr_client import FlareSolverrError, FlareSolverrFavoritesClient
from ..local_favorites import LocalFavoritesStore
from ..models import Post


def sync_remote_favorites(
    settings: AppSettings,
    local_favorites: LocalFavoritesStore,
    make_sync_client: Callable[[AppSettings], FlareSolverrFavoritesClient | None],
    log_sync_debug: Callable[[str, str], None],
    on_sync_error: Callable[[str], None] | None = None,
) -> tuple[list[Post], bool]:
    sync_client = make_sync_client(settings)
    if sync_client is None:
        return (local_favorites.list_favorites(), False)

    local_posts = local_favorites.list_favorites()
    local_by_id = {post.id: post for post in local_posts}

    sync_attempt_notes: list[str] = []
    remote_posts: list[Post] = []
    for attempt in range(1, 3):
        try:
            remote_posts = sync_client.list_favorites(limit=max(settings.page_size, 200))
            sync_attempt_notes.append(f"attempt={attempt} remote_count={len(remote_posts)}")
            if remote_posts:
                break
        except FlareSolverrError as exc:
            sync_attempt_notes.append(f"attempt={attempt} error={exc}")
            if on_sync_error is not None:
                on_sync_error(str(exc))

    if not remote_posts:
        # Some favorite endpoints can respond with an empty payload despite valid mutations.
        # Keep cached local favorites instead of wiping the tab.
        log_sync_debug(
            "Favorites sync fallback to local cache",
            "\n".join(
                [
                    "Outcome: remote favorites empty or unavailable.",
                    f"Local cache count: {len(local_posts)}",
                    *sync_attempt_notes,
                    "",
                    "FlareSolverr trace:",
                    sync_client.debug_summary(),
                ]
            ),
        )
        return (local_posts, bool(local_posts))

    strategy = (settings.sync_conflict_strategy or "merge").strip().lower()
    if strategy == "local_wins":
        log_sync_debug(
            "Favorites sync strategy local_wins",
            "Keeping local favorites cache as source of truth for this sync cycle.",
        )
        return (local_posts, bool(local_posts))

    if strategy == "remote_wins":
        local_favorites.replace_all(remote_posts)
        return (local_favorites.list_favorites(), False)

    merged_posts: list[Post] = []
    for remote in remote_posts:
        local = local_by_id.get(remote.id)
        if local is None:
            merged_posts.append(remote)
            continue

        merged_posts.append(
            Post(
                id=remote.id,
                tags=remote.tags or local.tags,
                rating=remote.rating or local.rating,
                score=remote.score if remote.score is not None else local.score,
                width=remote.width if remote.width is not None else local.width,
                height=remote.height if remote.height is not None else local.height,
                file_size=remote.file_size if remote.file_size is not None else local.file_size,
                source=remote.source or local.source,
                md5=remote.md5 or local.md5,
                preview_url=remote.preview_url or local.preview_url,
                sample_url=remote.sample_url or local.sample_url,
                file_url=remote.file_url or local.file_url,
                created_at=remote.created_at or local.created_at,
            )
        )

    local_favorites.replace_all(merged_posts)
    return (local_favorites.list_favorites(), False)
