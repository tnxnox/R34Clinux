from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLineEdit,
    QPushButton,
    QComboBox,
    QLabel,
)


class SearchPanel(QWidget):
    """Component for the search bar, pagination, and preset search filters."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Core search components
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search tags, e.g. character rating:safe")

        self.search_button = QPushButton("Search")

        self.search_history_combo = QComboBox()
        self.search_history_combo.setMinimumWidth(220)

        self.saved_searches_combo = QComboBox()
        self.saved_searches_combo.setMinimumWidth(220)

        self.pinned_filters_combo = QComboBox()
        self.pinned_filters_combo.setMinimumWidth(220)

        self.save_search_button = QPushButton("Save search")
        self.pin_filter_button = QPushButton("Pin filter")

        self.prev_button = QPushButton("Previous")
        self.next_button = QPushButton("Next")
        self.page_label = QLabel("Page 1")

        self._build_layout()

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        search_row = QHBoxLayout()
        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(self.search_button)
        search_row.addWidget(QLabel("Recent"))
        search_row.addWidget(self.search_history_combo)
        search_row.addWidget(self.prev_button)
        search_row.addWidget(self.next_button)
        search_row.addWidget(self.page_label)
        layout.addLayout(search_row)

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Pinned"))
        preset_row.addWidget(self.pinned_filters_combo)
        preset_row.addWidget(QLabel("Saved"))
        preset_row.addWidget(self.saved_searches_combo)
        preset_row.addWidget(self.save_search_button)
        preset_row.addWidget(self.pin_filter_button)
        layout.addLayout(preset_row)
