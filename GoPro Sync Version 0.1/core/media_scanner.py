"""Durchsucht den Zielordner nach Fotos und Videos für die Galerie-Ansicht."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

from core.file_copier import PHOTO_EXTENSIONS, VIDEO_EXTENSIONS


@dataclass
class MediaItem:
    path: str
    filename: str
    kind: str          # "video" | "photo"
    size_bytes: int
    modified: datetime


def scan_gallery(target_folder: str) -> list[MediaItem]:
    items: list[MediaItem] = []
    if not target_folder or not os.path.isdir(target_folder):
        return items

    for root, _dirs, names in os.walk(target_folder):
        for name in names:
            ext = os.path.splitext(name)[1].lower()
            path = os.path.join(root, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue

            if ext in VIDEO_EXTENSIONS and ext != ".lrv":
                kind = "video"
            elif ext in PHOTO_EXTENSIONS:
                kind = "photo"
            else:
                continue

            items.append(
                MediaItem(
                    path=path,
                    filename=name,
                    kind=kind,
                    size_bytes=stat.st_size,
                    modified=datetime.fromtimestamp(stat.st_mtime),
                )
            )

    items.sort(key=lambda m: m.modified, reverse=True)
    return items


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
