from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QVariantAnimation, QRectF
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QIcon
from PySide6.QtWidgets import QSlider, QStyle, QWidget, QPushButton, QLineEdit

class ClickSeekSlider(QSlider):
    def __init__(self, orientation: Qt.Orientation = Qt.Orientation.Horizontal, parent: QWidget | None = None) -> None:
        super().__init__(orientation, parent)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            if self.orientation() == Qt.Orientation.Horizontal:
                position = int(event.position().x())
                span = max(self.width(), 1)
            else:
                position = int(event.position().y())
                span = max(self.height(), 1)

            value = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), position, span)
            self.setValue(value)
            self.sliderMoved.emit(value)
        super().mousePressEvent(event)


class ClickVideoSurface(QWidget):
    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class AnimatedButton(QPushButton):
    """Sleek button that smoothly interpolates background and border colors on hover/press."""
    def __init__(self, text: str = "", parent: QWidget | None = None, icon_name: str | None = None) -> None:
        super().__init__(text, parent)
        self.icon_name = icon_name

        self._normal_bg = QColor("#1e293b")
        self._hover_bg = QColor("#334155")
        self._pressed_bg = QColor("#0f172a")
        self._disabled_bg = QColor("#0b0f19")
        
        self._normal_border = QColor("#334155")
        self._hover_border = QColor("#475569")
        self._pressed_border = QColor("#6366f1")
        self._disabled_border = QColor("#1e293b")
        
        self._normal_text = QColor("#f8fafc")
        self._disabled_text = QColor("#475569")
        self._accent_color = QColor("#6366f1")

        self._bg_color = self._normal_bg
        self._border_color = self._normal_border
        self._text_color = self._normal_text

        self._bg_anim = QVariantAnimation(self)
        self._bg_anim.setDuration(120)
        self._bg_anim.valueChanged.connect(self._set_bg)

        self._border_anim = QVariantAnimation(self)
        self._border_anim.setDuration(120)
        self._border_anim.valueChanged.connect(self._set_border)

        # Dynamic icon color states
        self._icon_color = "#94a3b8"
        self._update_icon()

    def _set_bg(self, val: QColor) -> None:
        self._bg_color = val
        self.update()

    def _set_border(self, val: QColor) -> None:
        self._border_color = val
        self.update()

    def _update_icon(self) -> None:
        if not self.icon_name:
            return
        from r34_client.ui.resources.icons import get_icon
        ic = get_icon(self.icon_name, color_hex=self._icon_color)
        self.setIcon(ic)

    def enterEvent(self, event) -> None:
        if self.isEnabled():
            self._bg_anim.stop()
            self._bg_anim.setStartValue(self._bg_color)
            self._bg_anim.setEndValue(self._hover_bg)
            self._bg_anim.start()

            self._border_anim.stop()
            self._border_anim.setStartValue(self._border_color)
            self._border_anim.setEndValue(self._hover_border)
            self._border_anim.start()

            self._icon_color = "#f8fafc"
            self._update_icon()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if self.isEnabled():
            self._bg_anim.stop()
            self._bg_anim.setStartValue(self._bg_color)
            self._bg_anim.setEndValue(self._normal_bg)
            self._bg_anim.start()

            self._border_anim.stop()
            self._border_anim.setStartValue(self._border_color)
            self._border_anim.setEndValue(self._normal_border)
            self._border_anim.start()

            self._icon_color = "#94a3b8"
            self._update_icon()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if self.isEnabled() and event.button() == Qt.MouseButton.LeftButton:
            self._bg_anim.stop()
            self._bg_color = self._pressed_bg
            self._border_anim.stop()
            self._border_color = self._pressed_border
            self._icon_color = "#6366f1"
            self._update_icon()
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self.isEnabled() and event.button() == Qt.MouseButton.LeftButton:
            dest_bg = self._hover_bg if self.underMouse() else self._normal_bg
            dest_border = self._hover_border if self.underMouse() else self._normal_border
            self._icon_color = "#f8fafc" if self.underMouse() else "#94a3b8"
            self._update_icon()
            
            self._bg_anim.stop()
            self._bg_anim.setStartValue(self._bg_color)
            self._bg_anim.setEndValue(dest_bg)
            self._bg_anim.start()

            self._border_anim.stop()
            self._border_anim.setStartValue(self._border_color)
            self._border_anim.setEndValue(dest_border)
            self._border_anim.start()
        super().mouseReleaseEvent(event)

    def changeEvent(self, event) -> None:
        if event.type() == event.Type.EnabledChange:
            if not self.isEnabled():
                self._bg_color = self._disabled_bg
                self._border_color = self._disabled_border
                self._text_color = self._disabled_text
                self._icon_color = "#475569"
            else:
                self._bg_color = self._normal_bg
                self._border_color = self._normal_border
                self._text_color = self._normal_text
                self._icon_color = "#94a3b8"
            self._update_icon()
            self.update()
        super().changeEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setBrush(QBrush(self._bg_color))
        painter.setPen(QPen(self._border_color, 1.2))
        painter.drawRoundedRect(rect, 8, 8)

        # Draw icon & text
        icon = self.icon()
        text = self.text()
        
        icon_size = self.iconSize()
        icon_width = icon_size.width() if not icon.isNull() else 0
        
        fm = painter.fontMetrics()
        text_width = fm.horizontalAdvance(text) if text else 0
        
        spacing = 8 if icon_width and text_width else 0
        content_width = icon_width + spacing + text_width
        
        start_x = (self.width() - content_width) / 2.0
        
        if not icon.isNull():
            icon_y = (self.height() - icon_size.height()) / 2.0
            mode = QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled
            icon.paint(painter, int(start_x), int(icon_y), icon_size.width(), icon_size.height(), Qt.AlignmentFlag.AlignCenter, mode)
            start_x += icon_width + spacing
            
        if text:
            painter.setPen(self._text_color if self.isEnabled() else self._disabled_text)
            text_rect = QRectF(start_x, 0, self.width() - start_x, self.height())
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        
        painter.end()


class AnimatedLineEdit(QLineEdit):
    """Sleek text input with a glowing border animation on focus."""
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._focus_val = 0.0

        self._normal_border = QColor("#334155")
        self._focus_border = QColor("#6366f1")

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(150)
        self._anim.valueChanged.connect(self._set_focus_val)

        # Style standard components via QSS, but we'll paint the border manually or style it
        self.setStyleSheet("""
            QLineEdit {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 7px 12px;
                color: #f8fafc;
                selection-background-color: #4f46e5;
            }
        """)

    def _set_focus_val(self, val: float) -> None:
        self._focus_val = val
        # Interpolate border color
        r = int(self._normal_border.red() + (self._focus_border.red() - self._normal_border.red()) * val)
        g = int(self._normal_border.green() + (self._focus_border.green() - self._normal_border.green()) * val)
        b = int(self._normal_border.blue() + (self._focus_border.blue() - self._normal_border.blue()) * val)
        color_hex = f"#{r:02x}{g:02x}{b:02x}"
        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: #1e293b;
                border: 1px solid {color_hex};
                border-radius: 8px;
                padding: 7px 12px;
                color: #f8fafc;
                selection-background-color: #4f46e5;
            }}
        """)

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self._anim.stop()
        self._anim.setStartValue(self._focus_val)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._anim.stop()
        self._anim.setStartValue(self._focus_val)
        self._anim.setEndValue(0.0)
        self._anim.start()
