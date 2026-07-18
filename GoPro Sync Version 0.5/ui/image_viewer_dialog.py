"""Vollbild-Bildbetrachter mit Vor-/Zurück-Navigation für die Foto-Galerie."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy


class ImageViewerDialog(QDialog):
    def __init__(self, filepaths: list[str], start_index: int, parent=None):
        super().__init__(parent)
        self.filepaths = filepaths
        self.index = start_index
        self.setStyleSheet(parent.styleSheet() if parent else "")
        self.resize(1000, 700)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(16, 12, 16, 0)
        self.title_label = QLabel()
        self.title_label.setObjectName("subheading")
        top_bar.addWidget(self.title_label)
        top_bar.addStretch()
        close_btn = QPushButton("Schließen")
        close_btn.setObjectName("secondary")
        close_btn.clicked.connect(self.close)
        top_bar.addWidget(close_btn)
        layout.addLayout(top_bar)

        body = QHBoxLayout()
        prev_btn = QPushButton("‹")
        prev_btn.setObjectName("iconButton")
        prev_btn.setFixedWidth(50)
        prev_btn.clicked.connect(self._show_prev)
        body.addWidget(prev_btn)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        body.addWidget(self.image_label, 1)

        next_btn = QPushButton("›")
        next_btn.setObjectName("iconButton")
        next_btn.setFixedWidth(50)
        next_btn.clicked.connect(self._show_next)
        body.addWidget(next_btn)

        layout.addLayout(body, 1)

        self._load_current()

    def _load_current(self):
        path = self.filepaths[self.index]
        self.title_label.setText(f"{os.path.basename(path)}  ·  {self.index + 1} / {len(self.filepaths)}")
        pixmap = QPixmap(path)
        self._raw_pixmap = pixmap
        self._rescale()

    def _rescale(self):
        if hasattr(self, "_raw_pixmap") and not self._raw_pixmap.isNull():
            scaled = self._raw_pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.image_label.setPixmap(scaled)

    def resizeEvent(self, event):
        self._rescale()
        super().resizeEvent(event)

    def _show_prev(self):
        self.index = (self.index - 1) % len(self.filepaths)
        self._load_current()

    def _show_next(self):
        self.index = (self.index + 1) % len(self.filepaths)
        self._load_current()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Left:
            self._show_prev()
        elif event.key() == Qt.Key.Key_Right:
            self._show_next()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
