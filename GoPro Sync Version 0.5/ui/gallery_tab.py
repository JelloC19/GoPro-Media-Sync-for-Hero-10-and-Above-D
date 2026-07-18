"""Zweiter Tab: Galerie mit getrennter Video-/Foto-Ansicht und eingebautem Player."""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QIcon, QPainter, QColor, QBrush, QPolygon
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QStackedWidget, QSizePolicy,
)

from core.config import ConfigManager
from core.media_scanner import scan_gallery, human_size, MediaItem
from ui.video_thumbnail import VideoThumbnailQueue
from ui.video_player_dialog import VideoPlayerDialog
from ui.image_viewer_dialog import ImageViewerDialog
from ui.theme import ACCENT, TEXT_SECONDARY, CARD_HOVER

THUMB_SIZE = QSize(220, 150)


def _placeholder_video_thumb() -> QPixmap:
    pixmap = QPixmap(THUMB_SIZE)
    pixmap.fill(QColor("#161922"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QBrush(QColor(ACCENT)))
    painter.setPen(Qt.PenStyle.NoPen)
    cx, cy = pixmap.width() // 2, pixmap.height() // 2
    r = 26
    painter.drawEllipse(QPoint(cx, cy), r, r)
    painter.setBrush(QBrush(QColor("#06121a")))
    triangle = QPolygon([
        QPoint(cx - 8, cy - 13),
        QPoint(cx - 8, cy + 13),
        QPoint(cx + 14, cy),
    ])
    painter.drawPolygon(triangle)
    painter.end()
    return pixmap


PLACEHOLDER_VIDEO_THUMB = None  # lazy, erst nach QApplication erzeugt


class GalleryTab(QWidget):
    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.thumb_queue = VideoThumbnailQueue(self)
        self.videos: list[MediaItem] = []
        self.photos: list[MediaItem] = []

        self._build_ui()

    # ---------------------------------------------------------- UI Aufbau
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Galerie")
        title.setObjectName("heading")
        header.addWidget(title)
        header.addStretch()

        self.videos_btn = QPushButton(f"🎬  Videos")
        self.videos_btn.setCheckable(True)
        self.videos_btn.setChecked(True)
        self.videos_btn.clicked.connect(lambda: self._switch_view(0))

        self.photos_btn = QPushButton(f"🖼  Fotos")
        self.photos_btn.setCheckable(True)
        self.photos_btn.clicked.connect(lambda: self._switch_view(1))

        for btn in (self.videos_btn, self.photos_btn):
            btn.setObjectName("secondary")
            btn.setFixedHeight(38)
            header.addWidget(btn)

        refresh_btn = QPushButton("Aktualisieren")
        refresh_btn.setObjectName("secondary")
        refresh_btn.clicked.connect(self.refresh)
        header.addWidget(refresh_btn)

        layout.addLayout(header)

        self.empty_label = QLabel(
            "Noch keine Medien gefunden.\nSynchronisiere zuerst deine GoPro im Tab „Sync“."
        )
        self.empty_label.setObjectName("subheading")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setVisible(False)
        layout.addWidget(self.empty_label)

        self.stack = QStackedWidget()

        self.video_list = self._make_grid()
        self.video_list.itemDoubleClicked.connect(self._open_video)

        self.photo_list = self._make_grid()
        self.photo_list.itemDoubleClicked.connect(self._open_photo)

        self.stack.addWidget(self.video_list)
        self.stack.addWidget(self.photo_list)
        layout.addWidget(self.stack, 1)

    def _make_grid(self) -> QListWidget:
        grid = QListWidget()
        grid.setViewMode(QListWidget.ViewMode.IconMode)
        grid.setIconSize(THUMB_SIZE)
        grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        grid.setMovement(QListWidget.Movement.Static)
        grid.setSpacing(10)
        grid.setUniformItemSizes(True)
        grid.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        return grid

    def _switch_view(self, index: int):
        self.stack.setCurrentIndex(index)
        self.videos_btn.setChecked(index == 0)
        self.photos_btn.setChecked(index == 1)
        for btn, active in ((self.videos_btn, index == 0), (self.photos_btn, index == 1)):
            btn.setStyleSheet(f"background-color: {CARD_HOVER}; border: 1px solid {ACCENT};" if active else "")

    # ---------------------------------------------------------- Daten laden
    def refresh(self):
        items = scan_gallery(self.config.target_folder)
        self.videos = [m for m in items if m.kind == "video"]
        self.photos = [m for m in items if m.kind == "photo"]

        self.empty_label.setVisible(len(items) == 0)
        self.stack.setVisible(len(items) > 0)

        self._populate_videos()
        self._populate_photos()

    def _populate_videos(self):
        self.video_list.clear()
        global PLACEHOLDER_VIDEO_THUMB
        if PLACEHOLDER_VIDEO_THUMB is None:
            PLACEHOLDER_VIDEO_THUMB = _placeholder_video_thumb()

        for media in self.videos:
            item = QListWidgetItem(QIcon(PLACEHOLDER_VIDEO_THUMB), self._label_for(media))
            item.setData(Qt.ItemDataRole.UserRole, media.path)
            item.setSizeHint(QSize(THUMB_SIZE.width() + 20, THUMB_SIZE.height() + 50))
            self.video_list.addItem(item)

            self.thumb_queue.request_thumbnail(
                media.path, self._make_thumb_callback(item)
            )

    def _populate_photos(self):
        self.photo_list.clear()
        for media in self.photos:
            pixmap = QPixmap(media.path).scaled(
                THUMB_SIZE, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            item = QListWidgetItem(QIcon(pixmap), self._label_for(media))
            item.setData(Qt.ItemDataRole.UserRole, media.path)
            item.setSizeHint(QSize(THUMB_SIZE.width() + 20, THUMB_SIZE.height() + 50))
            self.photo_list.addItem(item)

    @staticmethod
    def _label_for(media: MediaItem) -> str:
        return f"{media.filename}\n{human_size(media.size_bytes)} · {media.modified.strftime('%d.%m.%Y')}"

    def _make_thumb_callback(self, item: QListWidgetItem):
        def callback(pixmap: QPixmap):
            scaled = pixmap.scaled(
                THUMB_SIZE, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            item.setIcon(QIcon(scaled))
        return callback

    # ---------------------------------------------------------- Öffnen
    def _open_video(self, item: QListWidgetItem):
        path = item.data(Qt.ItemDataRole.UserRole)
        dialog = VideoPlayerDialog(path, parent=self.window())
        dialog.exec()

    def _open_photo(self, item: QListWidgetItem):
        row = self.photo_list.row(item)
        paths = [m.path for m in self.photos]
        dialog = ImageViewerDialog(paths, row, parent=self.window())
        dialog.exec()
