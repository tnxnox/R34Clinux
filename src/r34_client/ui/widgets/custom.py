from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QSlider, QStyle, QWidget


class ClickSeekSlider(QSlider):
    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            if self.orientation() == Qt.Orientation.Horizontal:
                position = int(event.position().x())
                span = max(self.width(), 1)
            else:
                position = int(event.position().y())
                span = max(self.height(), 1)

            value = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), position, span)
            self.sliderMoved.emit(value)
        super().mousePressEvent(event)


class ClickVideoSurface(QWidget):
    clicked = Signal()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
