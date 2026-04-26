from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import QLineEdit, QListWidget

if TYPE_CHECKING:
    from ..main_window import MainWindow


def register_global_shortcuts(window: MainWindow) -> None:
    shortcut_specs = [
        ("Esc", window._cancel_current_operations),
        ("J", lambda: invoke_global_navigation(window, lambda: move_selection(window, +1))),
        ("K", lambda: invoke_global_navigation(window, lambda: move_selection(window, -1))),
        ("Ctrl+J", lambda: invoke_global_navigation(window, lambda: extend_selection(window, +1))),
        ("Ctrl+K", lambda: invoke_global_navigation(window, lambda: extend_selection(window, -1))),
        ("F", lambda: invoke_global_navigation(window, window._toggle_current_favorite)),
        ("O", lambda: invoke_global_navigation(window, window.open_selected_post)),
        ("D", lambda: invoke_global_navigation(window, window.download_selected_post)),
    ]

    for key_sequence, callback in shortcut_specs:
        shortcut = QShortcut(key_sequence, window)
        shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        shortcut.activated.connect(callback)
        window._global_shortcuts.append(shortcut)


def invoke_global_navigation(window: MainWindow, callback: Callable[[], None]) -> None:
    if isinstance(window.focusWidget(), QLineEdit):
        return
    callback()


def active_posts_list(window: MainWindow) -> QListWidget:
    return window.favorites_list if window.left_tabs.currentWidget() is window.favorites_list else window.results_list


def move_selection(window: MainWindow, delta: int) -> None:
    target_list = active_posts_list(window)
    if target_list.count() <= 0:
        return
    current_row = target_list.currentRow()
    if current_row < 0:
        current_row = 0
    new_row = max(0, min(target_list.count() - 1, current_row + delta))
    target_list.setCurrentRow(new_row)


def extend_selection(window: MainWindow, delta: int) -> None:
    target_list = active_posts_list(window)
    if target_list.count() <= 0:
        return

    current_row = target_list.currentRow()
    if current_row < 0:
        current_row = 0

    new_row = max(0, min(target_list.count() - 1, current_row + delta))
    target_list.setCurrentRow(new_row)

    min_row = min(current_row, new_row)
    max_row = max(current_row, new_row)
    for row in range(min_row, max_row + 1):
        item = target_list.item(row)
        if item is not None:
            item.setSelected(True)
