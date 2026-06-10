from __future__ import annotations

import threading
from typing import TYPE_CHECKING
from PySide6.QtCore import QObject, Signal
from r34_client.core.models import Post

if TYPE_CHECKING:
    from r34_client.ui.helpers.prefetch import ImageCache
    from r34_client.core.models import TagSuggestion


class SyncState:
    """State related to Rule34 favorites remote synchronization."""

    def __init__(self) -> None:
        self.pending_remote_add_ids: set[int] = set()
        self.pending_remote_remove_ids: set[int] = set()
        self.pending_remote_add_meta: dict[int, dict] = {}
        self.pending_remote_remove_meta: dict[int, dict] = {}
        self.pending_endpoint_streaks: dict[str, int] = {"add": 0, "remove": 0}
        self.pending_state_loaded: bool = False
        self.pending_sync_worker_active: bool = False
        self.sync_active_workers: int = 0
        self.pending_sync_started_at: float = 0.0
        self.pending_sync_last_restart_at: float = 0.0
        self.last_favorite_sync_failed: bool = False
        self.last_favorite_sync_error: str = ""
        self.last_favorite_sync_debug: str = ""
        self.favorites_sync_fallback_used: bool = False
        self.pending_state_lock = threading.Lock()


class SearchState:
    """State related to query searching and autocomplete caches."""

    def __init__(self) -> None:
        self.search_token: int = 0
        self.preview_token: int = 0
        self.favorites_token: int = 0
        self.autocomplete_token: int = 0
        self.last_autocomplete_prefix: str = ""
        self.autocomplete_cache: dict[str, list[TagSuggestion]] = {}
        self.autocomplete_token_start: int = 0
        self.autocomplete_token_end: int = 0
        self.autocomplete_query_snapshot: str = ""
        self.search_history: list[str] = []
        self.saved_searches: list[str] = []
        self.pinned_filters: list[str] = []
        self.all_favorites_posts: list[Post] = []
        self.favorites_loaded_count: int = 0
        self.image_cache: ImageCache | None = None


class AppState(QObject):
    """Encapsulates the core application state, separating it from the UI layer."""

    search_completed = Signal(list)  # Emits current_posts
    favorites_updated = Signal(list)  # Emits favorite_posts
    friend_favorites_updated = Signal(list)  # Emits friend_posts
    page_changed = Signal(int)  # Emits current_page
    query_changed = Signal(str)  # Emits current_query

    def __init__(self) -> None:
        super().__init__()
        self._current_posts: list[Post] = []
        self._favorite_posts: list[Post] = []
        self._friend_posts: list[Post] = []
        self._favorite_ids: set[int] = set()
        self._current_page = 0
        self._current_query = ""

        # Sub-states
        self.sync = SyncState()
        self.search = SearchState()

    @property
    def current_posts(self) -> list[Post]:
        return self._current_posts

    @current_posts.setter
    def current_posts(self, posts: list[Post]) -> None:
        self._current_posts = posts
        self.search_completed.emit(posts)

    @property
    def favorite_posts(self) -> list[Post]:
        return self._favorite_posts

    @favorite_posts.setter
    def favorite_posts(self, posts: list[Post]) -> None:
        self._favorite_posts = posts
        self._favorite_ids = {post.id for post in posts}
        self.favorites_updated.emit(posts)

    @property
    def favorite_ids(self) -> set[int]:
        return self._favorite_ids

    @favorite_ids.setter
    def favorite_ids(self, value: set[int]) -> None:
        self._favorite_ids = value

    @property
    def friend_posts(self) -> list[Post]:
        return self._friend_posts

    @friend_posts.setter
    def friend_posts(self, posts: list[Post]) -> None:
        self._friend_posts = posts
        self.friend_favorites_updated.emit(posts)

    @property
    def current_page(self) -> int:
        return self._current_page

    @current_page.setter
    def current_page(self, page: int) -> None:
        self._current_page = page
        self.page_changed.emit(page)

    @property
    def current_query(self) -> str:
        return self._current_query

    @current_query.setter
    def current_query(self, query: str) -> None:
        self._current_query = query
        self.query_changed.emit(query)
