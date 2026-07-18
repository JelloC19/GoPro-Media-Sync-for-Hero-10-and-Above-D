"""Extrahiert Vorschaubilder aus Videodateien, ohne die UI zu blockieren.

Läuft im Hauptthread über die Qt-Eventloop (QMediaPlayer ist async), verarbeitet
aber Aufträge strikt nacheinander, damit nicht Dutzende Player gleichzeitig
Ressourcen belegen.
"""
from __future__ import annotations

from collections import deque
from typing import Callable

from PySide6.QtCore import QObject, QUrl, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QMediaPlayer, QVideoSink


class VideoThumbnailQueue(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue: deque[tuple[str, Callable[[QPixmap], None]]] = deque()
        self._busy = False
        self._player: QMediaPlayer | None = None
        self._sink: QVideoSink | None = None
        self._current_callback: Callable[[QPixmap], None] | None = None
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_timeout)

    def request_thumbnail(self, filepath: str, callback: Callable[[QPixmap], None]):
        self._queue.append((filepath, callback))
        if not self._busy:
            self._process_next()

    def _process_next(self):
        if not self._queue:
            self._busy = False
            return
        self._busy = True
        filepath, callback = self._queue.popleft()
        self._current_callback = callback

        try:
            self._sink = QVideoSink()
            self._player = QMediaPlayer()
            self._player.setVideoSink(self._sink)
            self._player.setAudioOutput(None)
            self._sink.videoFrameChanged.connect(self._on_frame)
            self._player.mediaStatusChanged.connect(self._on_status_changed)
            self._player.errorOccurred.connect(lambda *_: self._finish_current(None))
            self._player.setSource(QUrl.fromLocalFile(filepath))
            self._timeout_timer.start(4000)
        except Exception:
            self._finish_current(None)

    def _on_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.LoadedMedia and self._player:
            duration = self._player.duration()
            seek_pos = min(1000, max(0, duration // 4)) if duration else 0
            self._player.setPosition(seek_pos)
            self._player.play()
            QTimer.singleShot(150, self._pause_player)

    def _pause_player(self):
        if self._player:
            self._player.pause()

    def _on_frame(self, frame):
        if not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        pixmap = QPixmap.fromImage(image)
        self._finish_current(pixmap)

    def _on_timeout(self):
        self._finish_current(None)

    def _finish_current(self, pixmap: QPixmap | None):
        self._timeout_timer.stop()
        callback = self._current_callback
        self._current_callback = None

        if self._player:
            self._player.stop()
            self._player.deleteLater()
            self._player = None
        if self._sink:
            self._sink.deleteLater()
            self._sink = None

        if callback and pixmap is not None:
            callback(pixmap)

        QTimer.singleShot(0, self._process_next)
