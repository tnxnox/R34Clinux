from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QAbstractItemView,
)


class FriendsPanel(QWidget):
    """Component wrapping the friends list, friend's posts list, and related buttons."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.add_friend_button = QPushButton("Add Friend")
        self.remove_friend_button = QPushButton("Remove Friend")

        self.friends_list = QListWidget()
        self.friends_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        self.friend_posts_list = QListWidget()
        self.friend_posts_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.friend_posts_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        self.friend_page_label = QLabel("")

        self._build_layout()

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        friend_buttons = QHBoxLayout()
        friend_buttons.addWidget(self.add_friend_button)
        friend_buttons.addWidget(self.remove_friend_button)
        layout.addLayout(friend_buttons)

        layout.addWidget(QLabel("Friends"))
        layout.addWidget(self.friends_list, 1)

        layout.addWidget(QLabel("Friend's Favorites"))
        layout.addWidget(self.friend_page_label)
        layout.addWidget(self.friend_posts_list, 2)
