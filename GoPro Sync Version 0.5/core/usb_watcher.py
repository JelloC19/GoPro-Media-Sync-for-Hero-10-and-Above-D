"""Überwacht angeschlossene Laufwerke und erkennt GoPro-Kameras (MTP/USB-Massenspeicher).

Eine GoPro meldet sich beim Anschluss per USB i. d. R. als Massenspeicher mit
einem DCIM-Ordner, der Unterordner wie "100GOPRO", "101GOPRO" etc. enthält.
Wir pollen die verbundenen Laufwerke in einem Hintergrund-Thread und prüfen
genau dieses Muster - das funktioniert zuverlässig unter Windows, macOS und Linux.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

import psutil
from PySide6.QtCore import QThread, Signal


@dataclass
class GoProDevice:
    root_path: str          # z. B. "E:\\" oder "/media/user/GoPro"
    dcim_path: str           # Pfad zum DCIM-Ordner
    volume_label: str        # Anzeigename des Laufwerks


def _find_dcim_gopro_folders(mountpoint: str) -> str | None:
    """Gibt den DCIM-Pfad zurück, wenn dieser mind. einen *GOPRO-Unterordner hat."""
    dcim = os.path.join(mountpoint, "DCIM")
    if not os.path.isdir(dcim):
        return None
    try:
        for entry in os.listdir(dcim):
            full = os.path.join(dcim, entry)
            if os.path.isdir(full) and "GOPRO" in entry.upper():
                return dcim
    except (PermissionError, OSError):
        return None
    return None


def _volume_label(mountpoint: str) -> str:
    label = os.path.basename(os.path.normpath(mountpoint))
    return label or mountpoint


class UsbWatcher(QThread):
    """Läuft dauerhaft im Hintergrund und meldet an-/abgesteckte GoPros."""

    device_connected = Signal(object)   # GoProDevice
    device_disconnected = Signal(str)   # root_path

    def __init__(self, poll_interval: float = 2.0, parent=None):
        super().__init__(parent)
        self._poll_interval = poll_interval
        self._running = True
        self._known_devices: dict[str, GoProDevice] = {}

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            try:
                self._scan_once()
            except Exception:
                pass
            for _ in range(int(self._poll_interval * 10)):
                if not self._running:
                    break
                time.sleep(0.1)

    def _scan_once(self):
        current_roots = set()
        for part in psutil.disk_partitions(all=False):
            mountpoint = part.mountpoint
            if not mountpoint or not os.path.exists(mountpoint):
                continue
            # Netzwerklaufwerke / System-Mounts überspringen
            if part.fstype == "" and os.name != "nt":
                continue
            dcim = _find_dcim_gopro_folders(mountpoint)
            if dcim:
                current_roots.add(mountpoint)
                if mountpoint not in self._known_devices:
                    device = GoProDevice(
                        root_path=mountpoint,
                        dcim_path=dcim,
                        volume_label=_volume_label(mountpoint),
                    )
                    self._known_devices[mountpoint] = device
                    self.device_connected.emit(device)

        # Abgesteckte Geräte erkennen
        for root in list(self._known_devices.keys()):
            if root not in current_roots:
                del self._known_devices[root]
                self.device_disconnected.emit(root)
