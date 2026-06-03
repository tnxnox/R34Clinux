from __future__ import annotations

import json
from typing import TYPE_CHECKING

import requests

from r34_client.api.flaresolverr_parsing import extract_body_text, extract_items
from r34_client.api.urls import favorites_view_url
from r34_client.core.models import Post
from r34_client.core.worker import FunctionWorker

if TYPE_CHECKING:
    from ..main_window import MainWindow


def _fetch_page(url: str, flare_solver_url: str = "") -> str | None:
    try:
        payload = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": 30000,
        }
        resp = requests.post(
            f"{flare_solver_url.rstrip('/')}/v1",
            json=payload,
            timeout=35,
        )
        resp.raise_for_status()
        body = resp.json()
        solution = body.get("solution", {})
        return solution.get("response")
    except (requests.RequestException, json.JSONDecodeError, KeyError, TypeError):
        return None


def _parse_friend_favorites(html: str) -> list[Post]:
    body = extract_body_text(html)
    items = extract_items(body)

    posts: list[Post] = []
    seen: set[int] = set()
    for post_id, preview_url in items:
        if post_id in seen:
            continue
        seen.add(post_id)
        post = Post(
            id=post_id,
            tags=[],
            rating="",
            score=None,
            width=None,
            height=None,
            file_size=None,
            source="",
            md5="",
            preview_url=preview_url,
            sample_url="",
            file_url="",
            created_at="",
        )
        posts.append(post)
    return posts


def _fetch_friend_favorites_impl(user_id: str, solver_url: str) -> list[Post]:
    url = favorites_view_url(user_id)
    html = _fetch_page(url, flare_solver_url=solver_url)
    if html is None:
        msg = f"Failed to fetch favorites for user {user_id}"
        raise RuntimeError(msg)
    return _parse_friend_favorites(html)


def add_friend_dialog(window: MainWindow) -> None:
    from PySide6.QtWidgets import QDialog, QLineEdit, QVBoxLayout, QFormLayout, QDialogButtonBox

    dialog = QDialog(window)
    dialog.setWindowTitle("Add Friend")
    dialog.setModal(True)

    user_id_input = QLineEdit()
    user_id_input.setPlaceholderText("R34 user ID (number)")

    name_input = QLineEdit()
    name_input.setPlaceholderText("Display name")

    notes_input = QLineEdit()
    notes_input.setPlaceholderText("Optional notes")

    layout = QVBoxLayout(dialog)
    form = QFormLayout()
    form.addRow("User ID:", user_id_input)
    form.addRow("Name:", name_input)
    form.addRow("Notes:", notes_input)
    layout.addLayout(form)

    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    if dialog.exec() != QDialog.Accepted:
        return

    user_id = user_id_input.text().strip()
    display_name = name_input.text().strip() or user_id
    notes = notes_input.text().strip()

    if not user_id:
        return

    window.local_favorites.add_friend(user_id, display_name, notes)
    _refresh_friends_list(window)


def remove_friend_dialog(window: MainWindow) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox

    item = window.friends_list.currentItem()
    if item is None:
        return
    friend = item.data(Qt.ItemDataRole.UserRole)
    if friend is None:
        return

    confirm = QMessageBox.question(
        window,
        "Remove Friend",
        f"Remove '{friend['display_name']}' (ID: {friend['user_id']}) from your friends?",
        QMessageBox.Yes | QMessageBox.No,
    )
    if confirm != QMessageBox.Yes:
        return

    window.local_favorites.remove_friend(str(friend["user_id"]))
    window.friend_posts_list.clear()
    window.friend_posts = []
    _refresh_friends_list(window)


def _refresh_friends_list(window: MainWindow) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QListWidgetItem

    window.friends_list.clear()
    friends = window.local_favorites.list_friends()
    for friend in friends:
        text = f"{friend['display_name']}  (ID: {friend['user_id']})"
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, friend)
        window.friends_list.addItem(item)


def load_friend_favorites(window: MainWindow, item: object = None) -> None:
    from PySide6.QtCore import Qt

    if item is None:
        item = window.friends_list.currentItem()
    if item is None:
        return
    friend = item.data(Qt.ItemDataRole.UserRole)
    if friend is None:
        return

    user_id = str(friend["user_id"])
    solver_url = window.settings.flaresolverr_url

    window._friend_fetch_token += 1
    token = window._friend_fetch_token

    window.friend_posts_list.clear()
    window.friend_posts = []
    window._set_status(f"Loading favorites for user {user_id}...")

    worker = FunctionWorker(_fetch_friend_favorites_impl, user_id, solver_url)
    worker.signals.finished.connect(lambda result: _friend_favorites_fetched(window, token, result))
    worker.signals.failed.connect(window._operation_failed)
    window._start_worker(worker, workload="general")


def _friend_favorites_fetched(window: MainWindow, token: int, result: object) -> None:
    if token != window._friend_fetch_token:
        return

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QListWidgetItem

    if not isinstance(result, list):
        window._set_status("Failed to parse friend favorites")
        return

    posts: list[Post] = []
    for obj in result:
        if isinstance(obj, Post):
            posts.append(obj)

    window.friend_posts_list.clear()
    for post in posts:
        item = QListWidgetItem(window._format_post_tile(post))
        item.setData(Qt.ItemDataRole.UserRole, post)
        window.friend_posts_list.addItem(item)

    window.friend_posts = posts
    window._set_status(f"Loaded {len(posts)} favorites")
