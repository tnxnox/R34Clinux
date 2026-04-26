from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem

from r34_client.core.models import Post, TagSuggestion

if TYPE_CHECKING:
    from ..main_window import MainWindow


def update_related_tags(window: MainWindow, posts: list[Post]) -> None:
    window.related_tags_list.blockSignals(True)
    window.related_tags_list.clear()

    suggestions = build_related_tags(posts, window.current_query, limit=12)
    for suggestion in suggestions:
        item = QListWidgetItem(f"{suggestion.value} ({suggestion.count or 1})")
        item.setData(Qt.ItemDataRole.UserRole, suggestion.value)
        window.related_tags_list.addItem(item)

    window.related_tags_list.blockSignals(False)
    window.related_tags_list.setEnabled(bool(suggestions))


def build_related_tags(posts: list[Post], query: str, limit: int = 12) -> list[TagSuggestion]:
    if not posts:
        return []

    excluded_tokens = {token.strip() for token in query.split() if token.strip()}
    tag_counts: Counter[str] = Counter()
    for post in posts:
        tag_counts.update(tag for tag in post.tags if tag not in excluded_tokens)

    suggestions: list[TagSuggestion] = []
    for tag, count in sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))[: max(0, int(limit))]:
        suggestions.append(TagSuggestion(value=tag, label=f"{tag} ({count})", count=count))
    return suggestions
