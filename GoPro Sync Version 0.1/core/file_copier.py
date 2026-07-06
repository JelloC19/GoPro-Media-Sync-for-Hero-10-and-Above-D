"""Kopiert GoPro-Medien im Hintergrund und meldet laufend den Fortschritt."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import QThread, Signal

VIDEO_EXTENSIONS = {".mp4", ".lrv", ".360"}
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".gpr", ".dng"}
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | PHOTO_EXTENSIONS


@dataclass
class CopyStats:
    copied: int = 0
    skipped: int = 0
    failed: int = 0


def _collect_media_files(dcim_path: str) -> list[str]:
    files = []
    for root, _dirs, names in os.walk(dcim_path):
        for name in names:
            ext = os.path.splitext(name)[1].lower()
            if ext in MEDIA_EXTENSIONS and not name.upper().startswith("."):
                # LRV/THM sind Vorschau-/Low-Res-Beweisdateien der GoPro - überspringen
                if ext == ".lrv":
                    continue
                files.append(os.path.join(root, name))
    files.sort()
    return files


class FileCopier(QThread):
    """Kopiert alle neuen Mediendateien einer GoPro in den Zielordner."""

    progress = Signal(int, int, str, int)   # current, total, filename, percent
    finished_ok = Signal(object)             # CopyStats
    error = Signal(str)

    def __init__(
        self,
        dcim_path: str,
        target_folder: str,
        organize_by_date: bool = True,
        delete_after_copy: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.dcim_path = dcim_path
        self.target_folder = target_folder
        self.organize_by_date = organize_by_date
        self.delete_after_copy = delete_after_copy
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _destination_for(self, src_path: str) -> str:
        filename = os.path.basename(src_path)
        if self.organize_by_date:
            try:
                mtime = os.path.getmtime(src_path)
                date_folder = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            except OSError:
                date_folder = "Unbekanntes-Datum"
            return os.path.join(self.target_folder, date_folder, filename)
        return os.path.join(self.target_folder, filename)

    def run(self):
        try:
            files = _collect_media_files(self.dcim_path)
        except Exception as exc:
            self.error.emit(f"Konnte GoPro-Speicher nicht lesen: {exc}")
            return

        total = len(files)
        stats = CopyStats()

        if total == 0:
            self.finished_ok.emit(stats)
            return

        for index, src in enumerate(files, start=1):
            if self._cancel:
                break

            dest = self._destination_for(src)
            filename = os.path.basename(src)

            try:
                if os.path.exists(dest) and os.path.getsize(dest) == os.path.getsize(src):
                    stats.skipped += 1
                else:
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.copy2(src, dest)
                    stats.copied += 1
                    if self.delete_after_copy:
                        os.remove(src)
            except Exception:
                stats.failed += 1

            percent = int((index / total) * 100)
            self.progress.emit(index, total, filename, percent)

        self.finished_ok.emit(stats)
