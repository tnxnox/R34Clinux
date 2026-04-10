from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QDialog, QPlainTextEdit, QPushButton, QVBoxLayout

from ..debug.diagnostics import DiagnosticsSnapshot, format_diagnostics_report

if TYPE_CHECKING:
    from ..windows.main_window import MainWindow


def diagnostics_snapshot(window: MainWindow) -> DiagnosticsSnapshot:
    remaining = window._rate_limit.remaining_seconds(time.monotonic())
    selected = window._current_post()
    return DiagnosticsSnapshot(
        sync_enabled=window._sync_enabled(),
        degraded_mode_active=remaining > 0,
        degraded_mode_remaining_seconds=remaining,
        fit_mode=window._fit_mode.value,
        active_workers=len(window._active_workers),
        current_query=window.current_query,
        current_page=window.current_page,
        current_results_count=len(window.current_posts),
        current_favorites_count=len(window.favorite_posts),
        selected_post_id=(selected.id if selected is not None else None),
        last_sync_failed=window._last_favorite_sync_failed,
        last_sync_error=window._last_favorite_sync_error,
        sync_debug_log_path=str(window._sync_debug_log_path),
    )


def open_diagnostics(window: MainWindow) -> None:
    dialog = QDialog(window)
    dialog.setWindowTitle("Diagnostics")
    dialog.resize(860, 540)

    layout = QVBoxLayout(dialog)
    report = QPlainTextEdit(dialog)
    report.setReadOnly(True)
    report.setPlainText(format_diagnostics_report(diagnostics_snapshot(window)))
    layout.addWidget(report, 1)

    close_button = QPushButton("Close", dialog)
    close_button.clicked.connect(dialog.accept)
    layout.addWidget(close_button)

    dialog.exec()


def open_controls(window: MainWindow) -> None:
    dialog = QDialog(window)
    dialog.setWindowTitle("Controls")
    dialog.resize(760, 480)

    layout = QVBoxLayout(dialog)
    report = QPlainTextEdit(dialog)
    report.setReadOnly(True)
    report.setPlainText(
        "R34 Linux Client Controls\n\n"
        "Search and discovery\n"
        "- Type tags in the search bar and press Enter or Search\n"
        "- Use Recent to rerun earlier queries\n"
        "- Save or pin the current query from the controls next to search\n"
        "- Pick related tags from the suggestions panel under the left sidebar\n\n"
        "Keyboard shortcuts\n"
        "- Esc: cancel ongoing operations\n"
        "- J: move to the next post\n"
        "- K: move to the previous post\n"
        "- Ctrl+J: extend selection forward\n"
        "- Ctrl+K: extend selection backward\n"
        "- F: toggle favorite on the selected post\n"
        "- O: open the selected post in the browser\n"
        "- D: download the selected post\n\n"
        "Favorites and collections\n"
        "- Use the Favorites tab for local favorites and collections\n"
        "- Right-click selections to bulk add, bulk remove, bulk open, or bulk download\n"
        "- Use the Collections button to create and manage favorite groups\n\n"
        "Viewer and toolbar\n"
        "- Fit buttons switch image fitting mode: smart, width, height, or 1:1\n"
        "- Use the mouse wheel or zoom controls to change preview scale\n"
        "- Click and drag on zoomed previews to pan around long images\n"
        "- Diagnostics shows sync state, last errors, and current activity\n"
    )
    layout.addWidget(report, 1)

    close_button = QPushButton("Close", dialog)
    close_button.clicked.connect(dialog.accept)
    layout.addWidget(close_button)

    dialog.exec()
