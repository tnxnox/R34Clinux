from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QAbstractItemView,
)

from r34_client.ui.widgets.custom import AnimatedButton


class FriendsPanel(QWidget):
    """Component wrapping the friends list, friend's posts list, and related buttons."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.add_friend_button = AnimatedButton("Add Friend", icon_name="user-plus")
        self.remove_friend_button = AnimatedButton("Remove Friend", icon_name="user-minus")

        self.friends_list = QListWidget()
        self.friends_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        self.friend_posts_list = QListWidget()
        self.friend_posts_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.friend_posts_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        self.friend_page_label = QLabel("")
        self.friend_page_label.setStyleSheet("font-weight: 500; color: #94a3b8;")

        self._build_layout()

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        friend_buttons = QHBoxLayout()
        friend_buttons.setSpacing(10)
        friend_buttons.addWidget(self.add_friend_button)
        friend_buttons.addWidget(self.remove_friend_button)
        layout.addLayout(friend_buttons)

        lbl_friends = QLabel("Friends")
        lbl_friends.setStyleSheet("font-size: 14px; font-weight: 600; color: #818cf8;")
        layout.addWidget(lbl_friends)
        layout.addWidget(self.friends_list, 1)

        lbl_favs = QLabel("Friend's Favorites")
        lbl_favs.setStyleSheet("font-size: 14px; font-weight: 600; color: #818cf8;")
        layout.addWidget(lbl_favs)
        layout.addWidget(self.friend_page_label)
        layout.addWidget(self.friend_posts_list, 2)
