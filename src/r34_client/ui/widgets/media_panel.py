from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QLabel,
    QSizePolicy,
    QTextBrowser,
    QSplitter,
)
from r34_client.ui.widgets.custom import ClickSeekSlider, ClickVideoSurface, AnimatedButton
from r34_client.ui.widgets.video_player import VideoPlayer


class MediaPanel(QWidget):
    """Component wrapping the media preview player, playback controls, and metadata views."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.preview_label = QLabel("Search for a post to preview it here.")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(320)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_label.setWordWrap(True)
        self.preview_label.setScaledContents(False)

        self.video_surface = ClickVideoSurface(parent)
        self.video_surface.setMinimumHeight(320)
        self.video_surface.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.video_surface.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.video_surface.hide()

        self.video_player = VideoPlayer(parent)

        self.meta_view = QTextBrowser()
        self.meta_view.setReadOnly(True)
        self.meta_view.setOpenLinks(False)

        self.download_button = AnimatedButton("Download", icon_name="download")
        self.open_button = AnimatedButton("Open in Browser", icon_name="open")
        self.copy_button = AnimatedButton("Copy Link", icon_name="copy")

        self.volume_slider = ClickSeekSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setFixedWidth(140)

        # Added Play/Pause button to the bottom playback controls
        self.play_button = AnimatedButton("", icon_name="play")
        self.play_button.setFixedSize(36, 36)

        self.seek_slider = ClickSeekSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setEnabled(False)
        self.seek_slider.setFixedHeight(22)

        self.seek_time_label = QLabel("00:00 / 00:00")
        self.seek_time_label.setStyleSheet("font-weight: 500; color: #94a3b8;")

        self.preview_container = QScrollArea()
        self.preview_container.setWidgetResizable(False)
        self.preview_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_container.setWidget(self.preview_label)

        self._build_layout()

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        media_widget = QWidget()
        media_layout = QVBoxLayout(media_widget)
        media_layout.setContentsMargins(0, 0, 0, 0)
        media_layout.setSpacing(10)

        media_layout.addWidget(self.preview_container, 3)
        media_layout.addWidget(self.video_surface, 3)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(10)
        meta_row.addWidget(self.download_button)
        meta_row.addWidget(self.open_button)
        meta_row.addWidget(self.copy_button)
        meta_row.addStretch(1)
        
        lbl_volume = QLabel("Volume")
        lbl_volume.setStyleSheet("color: #94a3b8; font-weight: 500;")
        meta_row.addWidget(lbl_volume)
        meta_row.addWidget(self.volume_slider)
        media_layout.addLayout(meta_row)

        playback_row = QHBoxLayout()
        playback_row.setSpacing(10)
        playback_row.addWidget(self.play_button)
        
        lbl_pos = QLabel("Position")
        lbl_pos.setStyleSheet("color: #94a3b8; font-weight: 500;")
        playback_row.addWidget(lbl_pos)
        playback_row.addWidget(self.seek_slider, 1)
        playback_row.addWidget(self.seek_time_label)
        media_layout.addLayout(playback_row)

        right_splitter = QSplitter()
        right_splitter.setOrientation(Qt.Orientation.Vertical)
        right_splitter.addWidget(media_widget)
        right_splitter.addWidget(self.meta_view)
        right_splitter.setSizes([620, 220])

        layout.addWidget(right_splitter, 1)
