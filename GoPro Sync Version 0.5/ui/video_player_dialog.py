"""Eingebauter Video-Player zum Abspielen von GoPro-Clips direkt in der Galerie."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QUrl, QTime
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, QLabel, QStyle, QSizePolicy
)


def _format_ms(ms: int) -> str:
    t = QTime(0, 0, 0).addMSecs(max(ms, 0))
    if t.hour() > 0:
        return t.toString("hh:mm:ss")
    return t.toString("mm:ss")


class VideoPlayerDialog(QDialog):
    def __init__(self, filepath: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(os.path.basename(filepath))
        self.resize(960, 600)
        self.setStyleSheet(parent.styleSheet() if parent else "")

        self._build_ui()

        self.audio_output = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)

        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playbackStateChanged.connect(self._on_state_changed)

        self.player.setSource(QUrl.fromLocalFile(filepath))
        self.player.play()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.video_widget = QVideoWidget()
        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.video_widget, 1)

        controls = QHBoxLayout()
        controls.setContentsMargins(16, 10, 16, 14)
        controls.setSpacing(12)

        self.play_btn = QPushButton()
        self.play_btn.setObjectName("iconButton")
        self.play_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        self.play_btn.clicked.connect(self._toggle_play)
        controls.addWidget(self.play_btn)

        self.time_label = QLabel("00:00")
        controls.addWidget(self.time_label)

        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderMoved.connect(self._seek)
        controls.addWidget(self.position_slider, 1)

        self.duration_label = QLabel("00:00")
        controls.addWidget(self.duration_label)

        volume_icon = QLabel("🔊")
        controls.addWidget(volume_icon)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setFixedWidth(90)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.valueChanged.connect(lambda v: self.audio_output.setVolume(v / 100))
        controls.addWidget(self.volume_slider)

        layout.addLayout(controls)

    def _toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_state_changed(self, state):
        icon = QStyle.StandardPixmap.SP_MediaPlay if state != QMediaPlayer.PlaybackState.PlayingState \
            else QStyle.StandardPixmap.SP_MediaPause
        self.play_btn.setIcon(self.style().standardIcon(icon))

    def _on_position_changed(self, position: int):
        if not self.position_slider.isSliderDown():
            self.position_slider.setValue(position)
        self.time_label.setText(_format_ms(position))

    def _on_duration_changed(self, duration: int):
        self.position_slider.setRange(0, duration)
        self.duration_label.setText(_format_ms(duration))

    def _seek(self, position: int):
        self.player.setPosition(position)

    def closeEvent(self, event):
        self.player.stop()
        super().closeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self._toggle_play()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
