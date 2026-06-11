from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QPropertyAnimation, Property, QRectF, QSize
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QIcon
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QPushButton, QToolTip

from r34_client.ui.resources.icons import get_icon


class SidebarButton(QPushButton):
    """Sleek vertical sidebar button that displays a color-changing icon and custom tooltip."""
    def __init__(self, icon_name: str, tooltip_text: str, parent: QWidget | None = None) -> None:
        super().__init__("", parent)
        self.icon_name = icon_name
        self.setToolTip(tooltip_text)
        self.setFixedSize(56, 56)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._active = False
        self._hovered = False
        self._icon_color = "#94a3b8"
        self._update_icon()

    def set_active(self, active: bool) -> None:
        self._active = active
        self._icon_color = "#6366f1" if active else ("#f8fafc" if self._hovered else "#94a3b8")
        self._update_icon()
        self.update()

    def _update_icon(self) -> None:
        self.setIcon(get_icon(self.icon_name, color_hex=self._icon_color, size=24))
        self.setIconSize(QSize(24, 24))

    def enterEvent(self, event) -> None:
        self._hovered = True
        if not self._active:
            self._icon_color = "#f8fafc"
            self._update_icon()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        if not self._active:
            self._icon_color = "#94a3b8"
            self._update_icon()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw a subtle hover/active background circle/rounded rect
        rect = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        if self._active:
            painter.setBrush(QBrush(QColor("rgba(99, 102, 241, 0.12)")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 12, 12)
        elif self._hovered:
            painter.setBrush(QBrush(QColor("rgba(255, 255, 255, 0.05)")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 12, 12)

        # Let standard QPushButton draw the icon
        super().paintEvent(event)
        painter.end()


class Sidebar(QWidget):
    """Vertical navigation sidebar with sliding indicator and settings trigger."""
    tab_clicked = Signal(int)
    settings_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(72)
        self.setStyleSheet("background-color: #070a13;")

        self._active_index = 0
        self._indicator_y = 16.0  # Animated position
        self._indicator_target = 16.0
        self._indicator_height = 24.0

        self._anim = QPropertyAnimation(self, b"indicatorY")
        self._anim.setDuration(220)

        self.buttons: list[SidebarButton] = []
        self._build_layout()

    def _build_layout(self) -> None:
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 16, 0, 16)
        self.layout.setSpacing(12)

        # Main tabs
        self.btn_search = SidebarButton("search", "Search Results", self)
        self.btn_favs = SidebarButton("star", "Favorites", self)
        self.btn_friends = SidebarButton("users", "Friends", self)

        self.buttons = [self.btn_search, self.btn_favs, self.btn_friends]

        for i, btn in enumerate(self.buttons):
            self.layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignCenter)
            btn.clicked.connect(lambda checked=False, idx=i: self.set_active_tab(idx))

        self.layout.addStretch(1)

        # Settings tab at the bottom
        self.btn_settings = SidebarButton("settings", "Settings", self)
        self.layout.addWidget(self.btn_settings, 0, Qt.AlignmentFlag.AlignCenter)
        self.btn_settings.clicked.connect(self.settings_clicked.emit)

        # Set initial active states
        self.buttons[0].set_active(True)

    def get_indicator_y(self) -> float:
        return self._indicator_y

    def set_indicator_y(self, val: float) -> None:
        self._indicator_y = val
        self.update()

    # Define property for animation
    indicatorY = Property(float, get_indicator_y, set_indicator_y)

    def set_active_tab(self, index: int, animate: bool = True) -> None:
        if index < 0 or index >= len(self.buttons):
            return
        
        # Deactivate previous
        self.buttons[self._active_index].set_active(False)
        self._active_index = index
        self.buttons[index].set_active(True)

        self.tab_clicked.emit(index)

        # Calculate target Y coordinate for sliding indicator
        button = self.buttons[index]
        target_y = button.y() + (button.height() - self._indicator_height) / 2.0
        self._indicator_target = target_y

        if animate:
            self._anim.stop()
            self._anim.setStartValue(self._indicator_y)
            self._anim.setEndValue(target_y)
            self._anim.start()
        else:
            self.set_indicator_y(target_y)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Snap indicator to correct position on resize (no animation)
        button = self.buttons[self._active_index]
        target_y = button.y() + (button.height() - self._indicator_height) / 2.0
        self.set_indicator_y(target_y)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw sidebar background
        painter.setBrush(QBrush(QColor("#070a13")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(self.rect())

        # Draw sliding indicator bar on the left edge
        painter.setBrush(QBrush(QColor("#6366f1")))
        painter.setPen(Qt.PenStyle.NoPen)
        indicator_rect = QRectF(0, self._indicator_y, 4, self._indicator_height)
        painter.drawRoundedRect(indicator_rect, 2, 2)

        painter.end()


class LeftTabs(QWidget):
    """
    Drop-in replacement for QTabWidget that pairs our modern vertical Sidebar
    with a QStackedWidget.
    """
    currentChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.sidebar = Sidebar(self)
        self.stacked = QStackedWidget(self)

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.addWidget(self.sidebar)
        self.layout.addWidget(self.stacked, 1)

        self.sidebar.tab_clicked.connect(self._on_sidebar_tab_clicked)
        # Propagate settings click up to window if needed
        self.sidebar.settings_clicked.connect(self._on_settings_clicked)

    def addTab(self, widget: QWidget, label: str) -> None:
        """Compatibility function for QTabWidget.addTab"""
        self.stacked.addWidget(widget)

    def currentWidget(self) -> QWidget:
        """Compatibility function for QTabWidget.currentWidget"""
        return self.stacked.currentWidget()

    def setCurrentWidget(self, widget: QWidget) -> None:
        """Compatibility function for QTabWidget.setCurrentWidget"""
        idx = self.stacked.indexOf(widget)
        if idx >= 0:
            self.setCurrentIndex(idx)

    def currentIndex(self) -> int:
        """Compatibility function for QTabWidget.currentIndex"""
        return self.stacked.currentIndex()

    def setCurrentIndex(self, index: int) -> None:
        """Compatibility function for QTabWidget.setCurrentIndex"""
        self.stacked.setCurrentIndex(index)
        self.sidebar.set_active_tab(index)

    def _on_sidebar_tab_clicked(self, index: int) -> None:
        self.stacked.setCurrentIndex(index)
        self.currentChanged.emit(index)

    def _on_settings_clicked(self) -> None:
        # Resolve window
        win = self.window()
        if win and hasattr(win, "open_settings"):
            win.open_settings()
