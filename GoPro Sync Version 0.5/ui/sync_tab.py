"""Erster Tab: Kamera-Status, Zielordner und der eigentliche Sync-Vorgang."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QFileDialog, QMessageBox, QCheckBox, QSizePolicy,
)

from core.config import ConfigManager
from core.usb_watcher import UsbWatcher, GoProDevice
from core.file_copier import FileCopier, CopyStats
from ui.circular_progress import CircularProgressBubble
from ui.theme import SUCCESS, DANGER, TEXT_SECONDARY

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


class SyncTab(QWidget):
    def __init__(self, config: ConfigManager, on_gallery_should_refresh, parent=None):
        super().__init__(parent)
        self.config = config
        self.on_gallery_should_refresh = on_gallery_should_refresh
        self.current_device: GoProDevice | None = None
        self.copier: FileCopier | None = None

        self._build_ui()

        self.watcher = UsbWatcher()
        self.watcher.device_connected.connect(self._on_device_connected)
        self.watcher.device_disconnected.connect(self._on_device_disconnected)
        self.watcher.start()

    # ---------------------------------------------------------- UI Aufbau
    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(24)

        outer.addWidget(self._build_camera_card(), 1)
        outer.addWidget(self._build_sync_card(), 1)

    def _build_camera_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        custom_photo = os.path.join(ASSETS_DIR, "hero11.png")
        if os.path.exists(custom_photo):
            from PySide6.QtGui import QPixmap
            image_label = QLabel()
            pixmap = QPixmap(custom_photo).scaled(
                260, 260, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            image_label.setPixmap(pixmap)
            image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(image_label)
        else:
            svg_widget = QSvgWidget(os.path.join(ASSETS_DIR, "camera_placeholder.svg"))
            svg_widget.setFixedSize(240, 240)
            layout.addWidget(svg_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(16)

        name_label = QLabel("HERO11 Black")
        name_label.setObjectName("heading")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_label)

        self.status_label = QLabel("Kein Gerät verbunden")
        self.status_label.setObjectName("subheading")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        layout.addSpacing(10)
        hint = QLabel("Tipp: Lege ein Foto deiner Kamera als\n\"hero11.png\" in den assets-Ordner,\num es hier anzuzeigen.")
        hint.setObjectName("subheading")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addStretch()
        return card

    def _build_sync_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(14)

        heading = QLabel("Synchronisieren")
        heading.setObjectName("heading")
        layout.addWidget(heading)

        # Zielordner
        folder_row = QHBoxLayout()
        self.path_label = QLabel(self.config.target_folder or "Kein Zielordner gewählt")
        self.path_label.setObjectName("pathLabel")
        self.path_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        choose_btn = QPushButton("Ordner wählen")
        choose_btn.setObjectName("secondary")
        choose_btn.clicked.connect(self._choose_folder)
        folder_row.addWidget(self.path_label)
        folder_row.addWidget(choose_btn)
        layout.addLayout(folder_row)

        # Optionen
        self.chk_ask = QCheckBox("Vor dem Sync nachfragen")
        self.chk_ask.setChecked(self.config.ask_before_sync)
        self.chk_ask.stateChanged.connect(lambda v: setattr(self.config, "ask_before_sync", bool(v)))

        self.chk_organize = QCheckBox("Nach Datum in Unterordnern sortieren")
        self.chk_organize.setChecked(self.config.organize_by_date)
        self.chk_organize.stateChanged.connect(lambda v: setattr(self.config, "organize_by_date", bool(v)))

        self.chk_delete = QCheckBox("Nach dem Kopieren von der Kamera löschen")
        self.chk_delete.setChecked(self.config.delete_after_copy)
        self.chk_delete.stateChanged.connect(lambda v: setattr(self.config, "delete_after_copy", bool(v)))

        layout.addWidget(self.chk_ask)
        layout.addWidget(self.chk_organize)
        layout.addWidget(self.chk_delete)

        layout.addSpacing(8)

        # Progress Bubble mittig
        bubble_row = QHBoxLayout()
        bubble_row.addStretch()
        self.bubble = CircularProgressBubble(diameter=190)
        bubble_row.addWidget(self.bubble)
        bubble_row.addStretch()
        layout.addLayout(bubble_row)

        layout.addSpacing(4)

        self.sync_btn = QPushButton("Jetzt synchronisieren")
        self.sync_btn.setEnabled(False)
        self.sync_btn.clicked.connect(self._start_sync)
        layout.addWidget(self.sync_btn)

        self.cancel_btn = QPushButton("Abbrechen")
        self.cancel_btn.setObjectName("secondary")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel_sync)
        layout.addWidget(self.cancel_btn)

        layout.addStretch()
        return card

    # ---------------------------------------------------------- Ordnerwahl
    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Zielordner wählen", self.config.target_folder or "")
        if folder:
            self.config.target_folder = folder
            self.path_label.setText(folder)

    # ---------------------------------------------------------- USB-Events
    def _on_device_connected(self, device: GoProDevice):
        self.current_device = device
        self.status_label.setText(f"Verbunden · {device.volume_label}")
        self.status_label.setStyleSheet(f"color: {SUCCESS};")
        self.sync_btn.setEnabled(True)
        self.bubble.set_idle("Bereit zum Sync")

        if self.config.ask_before_sync:
            answer = QMessageBox.question(
                self,
                "GoPro gefunden",
                f"Deine GoPro ({device.volume_label}) wurde erkannt.\n\nJetzt synchronisieren?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._start_sync()
        else:
            self._start_sync()

    def _on_device_disconnected(self, root_path: str):
        if self.current_device and self.current_device.root_path == root_path:
            self.current_device = None
            self.status_label.setText("Kein Gerät verbunden")
            self.status_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
            self.sync_btn.setEnabled(False)
            self.bubble.set_idle("Bereit")

    # ---------------------------------------------------------- Sync-Logik
    def _start_sync(self):
        if not self.current_device:
            QMessageBox.warning(self, "Kein Gerät", "Es ist aktuell keine GoPro angeschlossen.")
            return

        if not self.config.target_folder:
            self._choose_folder()
            if not self.config.target_folder:
                return

        os.makedirs(self.config.target_folder, exist_ok=True)

        self.sync_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)
        self.bubble.set_idle("Starte Übertragung …")

        self.copier = FileCopier(
            dcim_path=self.current_device.dcim_path,
            target_folder=self.config.target_folder,
            organize_by_date=self.chk_organize.isChecked(),
            delete_after_copy=self.chk_delete.isChecked(),
        )
        self.copier.progress.connect(self._on_progress)
        self.copier.finished_ok.connect(self._on_finished)
        self.copier.error.connect(self._on_error)
        self.copier.start()

    def _cancel_sync(self):
        if self.copier:
            self.copier.cancel()

    def _on_progress(self, current: int, total: int, filename: str, percent: int):
        self.bubble.set_progress(current, total, percent, status_text=filename)

    def _on_finished(self, stats: CopyStats):
        self.cancel_btn.setVisible(False)
        self.sync_btn.setEnabled(self.current_device is not None)

        if stats.copied == 0 and stats.skipped > 0:
            self.bubble.set_complete("Bereits aktuell")
        elif stats.copied == 0 and stats.skipped == 0:
            self.bubble.set_idle("Keine Dateien gefunden")
        else:
            self.bubble.set_complete(f"{stats.copied} kopiert, {stats.skipped} übersprungen")

        if stats.failed:
            QMessageBox.warning(
                self, "Teilweise fehlgeschlagen",
                f"{stats.failed} Datei(en) konnten nicht kopiert werden."
            )

        self.on_gallery_should_refresh()

    def _on_error(self, message: str):
        self.cancel_btn.setVisible(False)
        self.sync_btn.setEnabled(True)
        self.bubble.set_idle("Fehler")
        QMessageBox.critical(self, "Fehler beim Synchronisieren", message)

    def shutdown(self):
        self.watcher.stop()
        self.watcher.wait(1000)
