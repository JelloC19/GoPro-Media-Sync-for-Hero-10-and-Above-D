from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QTabWidget

from core.config import ConfigManager
from ui.sync_tab import SyncTab
from ui.gallery_tab import GalleryTab
from ui.theme import STYLESHEET


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GoPro Sync")
        self.resize(1180, 760)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(STYLESHEET)

        self.config = ConfigManager()

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.setCentralWidget(self.tabs)

        self.gallery_tab = GalleryTab(self.config)
        self.sync_tab = SyncTab(self.config, on_gallery_should_refresh=self.gallery_tab.refresh)

        self.tabs.addTab(self.sync_tab, "Sync")
        self.tabs.addTab(self.gallery_tab, "Galerie")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.gallery_tab.refresh()

    def _on_tab_changed(self, index: int):
        if self.tabs.widget(index) is self.gallery_tab:
            self.gallery_tab.refresh()

    def closeEvent(self, event):
        self.sync_tab.shutdown()
        super().closeEvent(event)
