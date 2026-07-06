"""Persistente Einstellungen (Zielordner, letzte Optionen) via QSettings."""
from PySide6.QtCore import QSettings

ORG_NAME = "HomeLab"
APP_NAME = "GoProSync"


class ConfigManager:
    def __init__(self):
        self._settings = QSettings(ORG_NAME, APP_NAME)

    @property
    def target_folder(self) -> str:
        return self._settings.value("target_folder", "", type=str)

    @target_folder.setter
    def target_folder(self, path: str):
        self._settings.setValue("target_folder", path)

    @property
    def ask_before_sync(self) -> bool:
        return self._settings.value("ask_before_sync", True, type=bool)

    @ask_before_sync.setter
    def ask_before_sync(self, value: bool):
        self._settings.setValue("ask_before_sync", value)

    @property
    def delete_after_copy(self) -> bool:
        return self._settings.value("delete_after_copy", False, type=bool)

    @delete_after_copy.setter
    def delete_after_copy(self, value: bool):
        self._settings.setValue("delete_after_copy", value)

    @property
    def organize_by_date(self) -> bool:
        return self._settings.value("organize_by_date", True, type=bool)

    @organize_by_date.setter
    def organize_by_date(self, value: bool):
        self._settings.setValue("organize_by_date", value)
