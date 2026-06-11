from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QComboBox,
    QLabel,
)

from r34_client.ui.widgets.custom import AnimatedButton, AnimatedLineEdit


class SearchPanel(QWidget):
    """Component for the search bar, pagination, and preset search filters."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Core search components using custom animated widgets
        self.search_input = AnimatedLineEdit()
        self.search_input.setPlaceholderText("Search tags, e.g. character rating:safe")

        # Search button with search icon, no text for sleek look
        self.search_button = AnimatedButton("", icon_name="search")
        self.search_button.setFixedWidth(50)

        self.search_history_combo = QComboBox()
        self.search_history_combo.setMinimumWidth(220)

        self.saved_searches_combo = QComboBox()
        self.saved_searches_combo.setMinimumWidth(220)

        self.pinned_filters_combo = QComboBox()
        self.pinned_filters_combo.setMinimumWidth(220)

        self.save_search_button = AnimatedButton("Save search", icon_name="save")
        self.pin_filter_button = AnimatedButton("Pin filter", icon_name="pin")

        self.prev_button = AnimatedButton("", icon_name="chevron-left")
        self.prev_button.setFixedWidth(40)
        self.next_button = AnimatedButton("", icon_name="chevron-right")
        self.next_button.setFixedWidth(40)
        
        self.page_label = QLabel("Page 1")
        self.page_label.setStyleSheet("font-weight: 600; padding: 0 4px;")

        self._build_layout()

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)

        search_row = QHBoxLayout()
        search_row.setSpacing(10)
        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(self.search_button)
        
        lbl_recent = QLabel("Recent")
        lbl_recent.setStyleSheet("color: #94a3b8; font-weight: 500;")
        search_row.addWidget(lbl_recent)
        
        search_row.addWidget(self.search_history_combo)
        search_row.addWidget(self.prev_button)
        search_row.addWidget(self.next_button)
        search_row.addWidget(self.page_label)
        layout.addLayout(search_row)

        preset_row = QHBoxLayout()
        preset_row.setSpacing(10)
        
        lbl_pinned = QLabel("Pinned")
        lbl_pinned.setStyleSheet("color: #94a3b8; font-weight: 500;")
        preset_row.addWidget(lbl_pinned)
        preset_row.addWidget(self.pinned_filters_combo)
        
        lbl_saved = QLabel("Saved")
        lbl_saved.setStyleSheet("color: #94a3b8; font-weight: 500;")
        preset_row.addWidget(lbl_saved)
        preset_row.addWidget(self.saved_searches_combo)
        
        preset_row.addWidget(self.save_search_button)
        preset_row.addWidget(self.pin_filter_button)
        layout.addLayout(preset_row)
