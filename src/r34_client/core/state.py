from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from r34_client.core.models import Post


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
