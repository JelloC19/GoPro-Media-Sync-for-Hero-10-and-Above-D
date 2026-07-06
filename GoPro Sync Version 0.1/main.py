"""GoPro Sync Pro - Vollversion mit perfekten Video-Rändern und Timing-Fix."""

import sys
import os
import re
import time
import json
import subprocess
import math
import urllib.request
import urllib.error
import asyncio

# PySide6
from PySide6.QtCore import (Qt, QTimer, QThread, Signal, Slot, QRectF, QUrl,
                             QPropertyAnimation, QEasingCurve, Property, QEvent, QObject)
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QGraphicsDropShadowEffect, QDialog,
                               QStackedWidget, QCheckBox, QFrame, QFileDialog,
                               QGridLayout, QScrollArea, QColorDialog, QGraphicsView, QGraphicsScene,
                               QSlider, QGraphicsBlurEffect)
from PySide6.QtGui import (QPixmap, QPainter, QColor, QPainterPath, QImage, 
                           QLinearGradient, QFont, QKeySequence, QShortcut, QRegion, QPen)
# Multimedia
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget, QGraphicsVideoItem

# Optional: OpenCV for Video Thumbnails
try:
    import cv2
    _HAS_CV2 = True
except Exception:
    _HAS_CV2 = False

# Optional: bleak (Bluetooth LE) für das Auslesen des Akkustands per BLE,
# UNABHÄNGIG vom USB-Verbindungsmodus der Kamera (siehe read_battery_via_ble
# weiter unten für die ausführliche Erklärung, warum das der beste Weg ist).
# Ohne installiertes "bleak"-Paket (pip install bleak) wird dieser Weg
# einfach übersprungen und die alten Methoden greifen weiter.
try:
    from bleak import BleakScanner, BleakClient
    _HAS_BLEAK = True
except Exception:
    _HAS_BLEAK = False

CONFIG_DIR = os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), "GoProSyncPro")
CONFIG_FILE = os.path.join(CONFIG_DIR, "sync_config.json")
FONT_STACK = "'Poppins', 'Montserrat', 'Century Gothic', 'Segoe UI Semibold', 'Segoe UI', sans-serif"

# --- [ UNTERSTUETZTE GOPRO-MODELLE ] ---
#
# Jedes unterstuetzte Modell hat einen MTP-Namensteil (wie es im Windows-
# Explorer unter "Dieser PC" auftaucht, z.B. "HERO11 Black"), eine Anzeige-
# Ueberschrift fuer die Sync-Seite und ein Video aus dem assets-Ordner, das
# beim Verbinden abgespielt wird. Neue Modelle koennen einfach hier ergaenzt
# werden, ohne den restlichen Code anzufassen.
GOPRO_MODELS = {
    "HERO11": {"display": "HERO 11 BLACK", "video": "GoPro Hero 11 .mp4"},
    "HERO9":  {"display": "HERO 9 BLACK",  "video": "GoPro Hero 9.mp4"},
}
# Reihenfolge, in der die Namensteile geprueft werden.
GOPRO_MODEL_ORDER = ["HERO11", "HERO9"]
# Fuer die PowerShell-Skripte (Akku/Speicher lesen, Dateien auflisten/kopieren):
# ein Regex-Muster, das JEDES unterstuetzte Modell matcht, z.B. "HERO11|HERO9".
GOPRO_MODEL_MATCH_PATTERN = "|".join(GOPRO_MODEL_ORDER)

# Globaler Cache für den API-Akkuwert
GLOBAL_CACHED_BATTERY = None

DEFAULT_CONFIG = {
    "target_dir": os.path.expanduser("~/Videos/GoProSync"),
    "accent_color": "#00f2fe",
    "delete_after_sync": False,
    "background_image": "",   # Pfad zu einem eigenen Hintergrundbild, leer = Standard-Verlauf
    "background_blur": 0      # Weichzeichner-Stärke (px) fürs Hintergrundbild
}

def load_config():
    # HINWEIS: Die Konfiguration liegt bewusst in %APPDATA% statt im
    # Programmordner. Liegt das Programm z.B. auf dem Desktop, blockiert
    # Windows (z.B. per "Kontrollierter Ordnerzugriff" im Defender-
    # Ransomware-Schutz) das Schreiben von Dateien dort oft fuer nicht
    # explizit erlaubte Programme -> PermissionError. %APPDATA% ist davon
    # nicht betroffen und genau fuer sowas gedacht.
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                merged = dict(DEFAULT_CONFIG)
                merged.update(loaded)
                return merged
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)

def save_config(config_dict):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_dict, f)
    except Exception as e:
        # Speichern der Einstellungen darf die App niemals zum Absturz bringen -
        # im schlimmsten Fall gehen nur die zuletzt geaenderten Einstellungen
        # (Zielordner/Farbe/Checkbox) beim naechsten Start verloren.
        print(f"Konnte Konfiguration nicht speichern: {e}")

def asset_path(filename):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", filename)

def add_drop_shadow(widget, blur_radius=25, offset_y=5, alpha=100, color_hex="#000000"):
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(blur_radius)
    c = QColor(color_hex)
    c.setAlpha(alpha)
    shadow.setColor(c)
    shadow.setOffset(0, offset_y)
    widget.setGraphicsEffect(shadow)


def cover_scaled_pixmap(pixmap, target_size):
    """Skaliert ein QPixmap wie CSS 'background-size: cover': füllt die
    Zielgröße komplett aus (kein Verzerren), überschüssige Ränder werden
    mittig abgeschnitten."""
    if pixmap.isNull() or target_size.width() <= 0 or target_size.height() <= 0:
        return pixmap
    scaled = pixmap.scaled(target_size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                            Qt.TransformationMode.SmoothTransformation)
    x = max(0, (scaled.width() - target_size.width()) // 2)
    y = max(0, (scaled.height() - target_size.height()) // 2)
    return scaled.copy(x, y, target_size.width(), target_size.height())


def trim_transparent_margins(pixmap):
    """Schneidet komplett transparente Ränder rund um ein Logo/PNG ab, damit
    kein unnötiger Leerraum (der wie ein "Rand" wirken kann) übrig bleibt.
    Hat das Bild keinen Alphakanal, wird es unverändert zurückgegeben."""
    if pixmap.isNull():
        return pixmap
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    if not image.hasAlphaChannel():
        return pixmap

    w, h = image.width(), image.height()
    if w * h > 2_000_000:
        # Sehr große Bilder ueberspringen wir hier - das ist fuer ein
        # kleines Sidebar-Logo ohnehin nicht der erwartete Anwendungsfall
        # und wuerde die Pixel-fuer-Pixel-Suche unnoetig verlangsamen.
        return pixmap
    min_x, min_y, max_x, max_y = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            if (image.pixel(x, y) >> 24) & 0xFF > 8:  # Alpha > ~3%
                if x < min_x: min_x = x
                if x > max_x: max_x = x
                if y < min_y: min_y = y
                if y > max_y: max_y = y

    if max_x < min_x or max_y < min_y:
        return pixmap  # komplett transparentes Bild - nichts zu tun

    cropped = image.copy(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)
    return QPixmap.fromImage(cropped)


# --- [ ANIMATIONEN & THEME ] ---

class GlowHoverAnimator(QObject):
    def __init__(self, get_color_callback):
        super().__init__()
        self.get_color = get_color_callback

    def eventFilter(self, obj, event):
        if isinstance(obj, QPushButton) and obj.isEnabled():
            if event.type() == QEvent.Type.Enter:
                self._animate_glow(obj, True)
            elif event.type() == QEvent.Type.Leave:
                self._animate_glow(obj, False)
        return False

    def _animate_glow(self, btn, is_hover):
        effect = btn.graphicsEffect()
        if not isinstance(effect, QGraphicsDropShadowEffect):
            effect = QGraphicsDropShadowEffect(btn)
            effect.setOffset(0, 0)
            btn.setGraphicsEffect(effect)
        
        anim = QPropertyAnimation(effect, b"color", btn)
        anim.setDuration(200)
        anim.setStartValue(effect.color())
        
        theme_color = QColor(self.get_color())
        theme_color.setAlpha(180)
        target_color = theme_color if is_hover else QColor(0, 0, 0, 0)
        anim.setEndValue(target_color)
        
        blur_anim = QPropertyAnimation(effect, b"blurRadius", btn)
        blur_anim.setDuration(200)
        blur_anim.setStartValue(effect.blurRadius())
        blur_anim.setEndValue(30 if is_hover else 0)

        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        blur_anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        btn._glow_anim = anim 
        btn._blur_anim = blur_anim


# --- [ GOPRO STATUS & API SWITCH ] ---

def _hidden_startupinfo():
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return si

def detect_connected_gopro_model():
    """Prueft, welche der unterstuetzten GoPro-Modelle (siehe GOPRO_MODELS)
    gerade per MTP am PC haengt. Gibt den Modell-Key (z.B. "HERO11") zurueck
    oder None, falls keine unterstuetzte GoPro gefunden wurde."""
    try:
        cmd = ['powershell', '-NoProfile', '-Command',
               '$shell = New-Object -ComObject Shell.Application; $shell.Namespace(17).Items() | Select-Object -ExpandProperty Name']
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                 startupinfo=_hidden_startupinfo(), timeout=10)
        names = result.stdout or ""
        for model in GOPRO_MODEL_ORDER:
            if model in names:
                return model
    except Exception:
        pass
    return None

def check_gopro_connected():
    """Rueckwaerts-kompatibler bool-Check: True sobald irgendeine
    unterstuetzte GoPro erkannt wird (siehe detect_connected_gopro_model)."""
    return detect_connected_gopro_model() is not None

def parse_battery_percent(raw):
    if not raw: return None
    match = re.search(r'(\d{1,3})\s*%?', str(raw))
    if match: return max(0, min(100, int(match.group(1))))
    return None

def parse_size_to_bytes(raw):
    if not raw: return None
    match = re.match(r'^\s*([\d.,]+)\s*([A-Za-zµ]+)?', str(raw))
    if not match: return None
    num_str, unit = match.group(1), (match.group(2) or "").lower()
    if ',' in num_str and '.' in num_str: num_str = num_str.replace('.', '').replace(',', '.')
    elif ',' in num_str: num_str = num_str.replace(',', '.')
    try: num = float(num_str)
    except Exception: return None
    if unit.startswith('t'): mult = 1024 ** 4
    elif unit.startswith('g'): mult = 1024 ** 3
    elif unit.startswith('m'): mult = 1024 ** 2
    elif unit.startswith('k'): mult = 1024
    else: mult = 1
    return num * mult

def attempt_api_battery_and_force_mtp():
    global GLOBAL_CACHED_BATTERY
    try:
        base_url = "http://172.29.171.51:8080"
        # Timeout erhöht auf 3.0 Sekunden
        req_state = urllib.request.Request(f"{base_url}/gopro/camera/state", method="GET")
        with urllib.request.urlopen(req_state, timeout=3.0) as response:
            data = json.loads(response.read().decode('utf-8'))
            bat = data.get('status', {}).get('70')
            if bat is not None:
                GLOBAL_CACHED_BATTERY = int(bat)
                
        req_mtp = urllib.request.Request(f"{base_url}/gopro/camera/setting?setting=112&option=1", method="GET")
        urllib.request.urlopen(req_mtp, timeout=2.0)
    except Exception:
        pass

# --- [ ADDED FROM Code 1: BLE + OPEN GOPRO + DIAG LOG ] ---
BLE_BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"  # Standard-BLE "Battery Level"
_DIAG_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gopro_akku_diagnose.txt")

async def _ble_read_battery_async(name_match="HERO11", timeout=6.0):
    device = await BleakScanner.find_device_by_filter(
        lambda d, adv: d.name and name_match.lower() in d.name.lower(),
        timeout=timeout,
    )
    if device is None:
        # Manche Kameras werben unter "GoPro XXXX" statt dem Modellnamen -
        # als zweiten Versuch danach suchen.
        device = await BleakScanner.find_device_by_filter(
            lambda d, adv: d.name and "gopro" in d.name.lower(),
            timeout=timeout,
        )
    if device is None:
        return None
    async with BleakClient(device, timeout=8.0) as client:
        value = await client.read_gatt_char(BLE_BATTERY_LEVEL_UUID)
        if value:
            return int(value[0])
    return None

def read_battery_via_ble(model=None):
    """Liest den Akkustand per Bluetooth LE (siehe Erklärung oben). Läuft
    synchron in einem eigenen kleinen Event-Loop - wird ausschließlich im
    DeviceMonitorThread (Hintergrund-Thread) aufgerufen, blockiert also nie
    die Oberfläche.

    BUGFIX: Vorher wurde hier IMMER der Default "HERO11" an
    _ble_read_battery_async() durchgereicht, unabhängig davon, welches
    Modell tatsächlich per MTP erkannt wurde. Für eine angeschlossene
    Hero 9 bedeutete das: der erste (gezielte) Scan-Versuch suchte nach
    einem Geraet mit "HERO11" im Namen, lief garantiert ins Leere, und erst
    der generische Fallback-Scan (irgendein Geraet mit "gopro" im Namen)
    konnte ueberhaupt etwas finden - das kostet unnoetig Zeit (bis zu
    ~12 statt ~6 Sekunden) und macht den Ansatz unnoetig fehleranfaelliger.
    Jetzt wird das tatsaechlich erkannte Modell (z.B. "HERO9") als
    name_match uebergeben."""
    if not _HAS_BLEAK:
        return None
    try:
        return asyncio.run(_ble_read_battery_async(name_match=model or "HERO11"))
    except Exception:
        return None

def _get_usb_subnet_candidates():
    candidates = []
    try:
        result = subprocess.run(['ipconfig'], capture_output=True, text=True, encoding="utf-8", errors="replace",
                                 startupinfo=_hidden_startupinfo(), timeout=5)
        for m in re.finditer(r'IPv4[^:]*:\s*([\d.]+)', result.stdout or ""):
            ip = m.group(1)
            if re.match(r'^172\.2\d\.', ip):
                candidates.append(ip)
    except Exception:
        pass
    return candidates

def read_battery_via_open_gopro(timeout=1.2):
    for local_ip in _get_usb_subnet_candidates():
        parts = local_ip.split(".")
        if len(parts) != 4:
            continue
        camera_ip = f"{parts[0]}.{parts[1]}.{parts[2]}.51"
        base = f"http://{camera_ip}:8080"
        try:
            with urllib.request.urlopen(f"{base}/gopro/camera/state", timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            pct = data.get("status", {}).get("70")
            if pct is not None:
                return max(0, min(100, int(pct)))
        except Exception:
            continue
    return None

def read_gopro_status(write_diag=True, model=None):
    """Liest Akkustand und Speicherbelegung der GoPro direkt vom Gerät.

    Reihenfolge:
    1. Bluetooth LE (read_battery_via_ble) - funktioniert bei aktivem
       Bluetooth IMMER, unabhängig vom USB-Modus, OHNE die MTP-
       Dateiübertragung zu stören. Das ist der bevorzugte Weg.
    2. Open GoPro HTTP über USB (nur falls Kamera zufällig im
       Wired-Control-Modus steht).
    3. Windows-Explorer-Detailspalten per MTP (alter Fallback, siehe unten).

    Die Speicherbelegung kommt weiterhin über die MTP-Spalten, da das
    zuverlässig funktioniert und mit dem normalen Dateizugriffsmodus
    kompatibel ist.
    """
    battery_pct = None
    storage_pct = None
    capacity_str = None
    free_str = None

    # 1) Bluetooth LE (bevorzugt - kein Moduswechsel nötig)
    try:
        battery_pct = read_battery_via_ble(model=model)
    except Exception:
        battery_pct = None

    # 2) Open GoPro HTTP über USB (nur falls Kamera zufällig im Wired-Control-Modus ist)
    if battery_pct is None:
        try:
            battery_pct = read_battery_via_open_gopro()
        except Exception:
            pass

    try:
        ps_script = r'''
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch {}
$ErrorActionPreference = "SilentlyContinue"
$s = New-Object -ComObject Shell.Application
$ns17 = $s.Namespace(17)
if (!$ns17) { Write-Output "{}"; exit }
$gopro = $ns17.Items() | Where-Object {$_.Name -match "__GOPRO_PATTERN__"} | Select-Object -First 1
if (!$gopro) { Write-Output "{}"; exit }

function Get-DetailValue($folder, $item, [string[]]$keywords) {
    for ($i = 0; $i -le 320; $i++) {
        $header = $folder.GetDetailsOf($folder.Items, $i)
        if ([string]::IsNullOrWhiteSpace($header)) { continue }
        $h = $header.ToLower()
        foreach ($k in $keywords) {
            if ($h.Contains($k)) {
                $val = $folder.GetDetailsOf($item, $i)
                if (![string]::IsNullOrWhiteSpace($val)) { return $val }
            }
        }
    }
    return $null
}

$battery = $null
$propCandidates = @(
    "System.DeviceCapabilities.DeviceBatteryLevel",
    "System.Battery.ChargeLevel",
    "System.Battery.PercentRemaining",
    "System.PercentFull"
)
foreach ($p in $propCandidates) {
    try {
        $v = $gopro.ExtendedProperty($p)
        if ($v -ne $null -and "$v" -ne "") { $battery = "$v"; break }
    } catch {}
}
if (!$battery) {
    $battery = Get-DetailValue $ns17 $gopro @("akku", "battery", "batterie", "ladezustand", "charge")
}

$capacity = $null
$free = $null
$vol = $gopro.GetFolder.Items() | Select-Object -First 1
if ($vol) {
    $goproFolder = $gopro.GetFolder
    $capacity = Get-DetailValue $goproFolder $vol @("gesamtgroesse", "gesamtgröße", "total size", "kapazitaet", "kapazität", "capacity")
    $free = Get-DetailValue $goproFolder $vol @("frei", "free space", "verfuegbar", "verfügbar")
}

$diag = @()
if (!$battery) {
    for ($i = 0; $i -le 320; $i++) {
        $header = $ns17.GetDetailsOf($ns17.Items, $i)
        if ([string]::IsNullOrWhiteSpace($header)) { continue }
        $val = $ns17.GetDetailsOf($gopro, $i)
        if (![string]::IsNullOrWhiteSpace($val)) { $diag += "$header=$val" }
    }
}

$result = [PSCustomObject]@{ battery = $battery; capacity = $capacity; free = $free; diag = ($diag -join "; ") }
Write-Output ($result | ConvertTo-Json -Compress)
'''
        ps_script = ps_script.replace("__GOPRO_PATTERN__", GOPRO_MODEL_MATCH_PATTERN)
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command', ps_script],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            startupinfo=_hidden_startupinfo(), timeout=20
        )
        raw = (result.stdout or "").strip()
        data = json.loads(raw) if raw else {}

        # 3) MTP-Spalten - nur als letzter Fallback für den Akku verwenden
        if battery_pct is None:
            battery_pct = parse_battery_percent(data.get("battery"))

        capacity_str = data.get("capacity")
        free_str = data.get("free")

        if battery_pct is None and write_diag:
            diag = data.get("diag")
            try:
                with open(_DIAG_LOG_PATH, "w", encoding="utf-8") as f:
                    if diag:
                        f.write("Akku-Wert nicht gefunden (weder per Bluetooth LE, Open-GoPro-HTTP "
                                "noch MTP-Spalten). Vom Gerät per MTP gemeldete Spalten:\n\n")
                        f.write(diag.replace("; ", "\n"))
                    else:
                        f.write("Akku-Wert nicht gefunden.\n\n"
                                "- Bluetooth LE: pruefen, ob 'bleak' installiert ist (pip install bleak), "
                                "Bluetooth am PC aktiv ist und die Kamera in Reichweite/gekoppelt ist.\n"
                                "- Open GoPro HTTP: nur relevant, wenn die Kamera auf 'GoPro-Verbindung' "
                                "statt 'MTP' steht.\n"
                                "- MTP-Spalten: liefern auf manchen Firmware-Staenden schlicht keinen Wert.")
            except Exception:
                pass

        cap_bytes = parse_size_to_bytes(capacity_str)
        free_bytes = parse_size_to_bytes(free_str)
        if cap_bytes and free_bytes is not None and cap_bytes > 0:
            used_bytes = max(0, cap_bytes - free_bytes)
            storage_pct = int(round((used_bytes / cap_bytes) * 100))

    except Exception as e:
        print("Status-Lesefehler:", e)

    return {
        "battery": battery_pct,
        "storage_pct": storage_pct,
        "capacity_str": capacity_str,
        "free_str": free_str,
    }

# --- [ DeviceMonitorThread remains using attempt_api_battery_and_force_mtp if desired ] ---

class DeviceMonitorThread(QThread):
    # connected (bool), Modell-Key wie "HERO11"/"HERO9" (leerer String, wenn
    # nicht verbunden) - siehe GOPRO_MODELS weiter oben.
    connection_changed = Signal(bool, str)
    status_ready = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True
        self._connected = False
        self._connected_model = None

    def stop(self): self._running = False

    def run(self):
        cycle = 0
        while self._running:
            if not self._connected:
                attempt_api_battery_and_force_mtp()

            model = detect_connected_gopro_model()
            connected = model is not None
            if model != self._connected_model:
                self._connected_model = model
                self._connected = connected
                self.connection_changed.emit(connected, model or "")
                if connected:
                    if self._running: self.status_ready.emit(read_gopro_status(model=model))
                    cycle = 0
            elif connected:
                cycle += 1
                if cycle >= 5: 
                    cycle = 0
                    if self._running: self.status_ready.emit(read_gopro_status(model=model))
            for _ in range(20):
                if not self._running: break
                self.msleep(100)


# --- [ SYNC: DATEIEN VON DER GOPRO AUF DEN PC KOPIEREN ] ---
#
# Die GoPro haengt per MTP (Media Transfer Protocol) am PC und taucht deshalb
# NICHT als normales Laufwerk mit Buchstaben auf. Ein einfaches os.walk /
# shutil.copy funktioniert daher nicht. Stattdessen wird - genau wie beim
# Auslesen von Akku/Speicher weiter oben - die Windows-Shell (Shell.Application
# COM-Objekt) benutzt, um die Dateien auf dem Geraet zu finden und per
# CopyHere() in den Zielordner zu kopieren.

SYNC_MEDIA_EXTENSIONS = [".mp4", ".jpg", ".jpeg", ".png"]

def _ps_str(s):
    """Erzeugt ein sicheres, single-quoted PowerShell-Stringliteral (keine
    Variablen-Interpolation, nur ' muss verdoppelt werden)."""
    return "'" + str(s).replace("'", "''") + "'"


def _ps_str_array(items):
    return "@(" + ", ".join(_ps_str(i) for i in items) + ")"


# --- PHASE 1: Nur auflisten (schnell, KEIN CopyHere) -----------------------
#
# Frueher wurde in EINEM einzigen, lange laufenden PowerShell-Prozess sowohl
# der komplette Ordnerbaum der GoPro durchsucht ALS AUCH direkt in derselben
# Schleife jede Datei per CopyHere() kopiert. Bei vielen Dateien (bzw. wenn
# die MTP-Verbindung kurz ins Stocken kommt) blieb dieser eine Prozess dann
# haengen - ohne Fehlermeldung, weil `$ErrorActionPreference = "SilentlyContinue"`
# alles verschluckt. Das sah fuer den Nutzer so aus, als wuerde "der Sync
# nicht mehr funktionieren".
#
# Jetzt (nach Vorschlag von Gemini, hier sauber zu Ende gebaut): PowerShell
# wird nur noch als "dummer Ausfuehrer" benutzt:
#   1) EIN kurzer Befehl listet nur Namen/Groessen/Ordnerpfade auf (billig).
#   2) Python vergleicht das komplett selbst mit dem Zielordner (Duplikat-
#      Check), OHNE nochmal PowerShell/COM anzufassen.
#   3) Fuer jede tatsaechlich fehlende Datei startet Python einen neuen,
#      winzigen, isolierten PowerShell-Prozess, der NUR diese eine Datei
#      per CopyHere() ueberträgt. Haengt sich einer dieser Mini-Prozesse
#      auf, betrifft das nur diese eine Datei (Timeout) statt den ganzen Sync.
#
# WICHTIG: Das Akku/Speicher-Auslesen (read_gopro_status, DeviceMonitorThread,
# attempt_api_battery_and_force_mtp) wird hier bewusst NICHT angefasst -
# genau das war bei Geminis eigenem Versuch kaputtgegangen.

def build_list_script():
    ext_list_literal = _ps_str_array(SYNC_MEDIA_EXTENSIONS)
    script = r'''
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch {}
$ErrorActionPreference = "SilentlyContinue"
$exts = ''' + ext_list_literal + r'''

$shell = New-Object -ComObject Shell.Application
$ns17 = $shell.Namespace(17)
if (!$ns17) { Write-Output 'RESULT:{"error":"no_namespace"}'; exit }
$gopro = $ns17.Items() | Where-Object {$_.Name -match "__GOPRO_PATTERN__"} | Select-Object -First 1
if (!$gopro) { Write-Output 'RESULT:{"error":"not_found"}'; exit }

$results = New-Object System.Collections.ArrayList
$queue = New-Object System.Collections.ArrayList
[void]$queue.Add(@{ folder = $gopro.GetFolder; path = @() })

while ($queue.Count -gt 0) {
    $entry = $queue[0]
    $queue.RemoveAt(0)
    $currentFolder = $entry.folder
    $currentPath = $entry.path

    foreach ($item in $currentFolder.Items()) {
        $subFolder = $null
        try { $subFolder = $item.GetFolder } catch { $subFolder = $null }

        if ($subFolder -ne $null) {
            $newPath = @($currentPath) + $item.Name
            [void]$queue.Add(@{ folder = $subFolder; path = $newPath })
        } else {
            $lname = $item.Name.ToLower()
            $matched = $false
            foreach ($ext in $exts) {
                if ($lname.EndsWith($ext)) { $matched = $true; break }
            }
            if ($matched) {
                $size = 0
                try { $size = [int64]$item.ExtendedProperty("System.Size") } catch {}
                [void]$results.Add([PSCustomObject]@{ name = $item.Name; size = $size; path = ($currentPath -join "|") })
            }
        }
    }
}

Write-Output ("RESULT:" + ($results | ConvertTo-Json -Compress -Depth 6))
'''
    return script.replace("__GOPRO_PATTERN__", GOPRO_MODEL_MATCH_PATTERN)


# --- PHASE 3: Genau eine Datei isoliert kopieren ----------------------------

def build_single_copy_script(path_components, file_name, target_dir, dest_name, delete_after):
    target_dir_escaped = os.path.normpath(target_dir).replace('"', '""')
    path_array_literal = _ps_str_array(path_components)
    delete_literal = "$true" if delete_after else "$false"

    return f'''
try {{ [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) }} catch {{}}
$ErrorActionPreference = "SilentlyContinue"
$targetDir = "{target_dir_escaped}"
$destName = {_ps_str(dest_name)}
$fileName = {_ps_str(file_name)}
$pathParts = {path_array_literal}
$deleteAfter = {delete_literal}

$shell = New-Object -ComObject Shell.Application
$ns17 = $shell.Namespace(17)
if (!$ns17) {{ Write-Output 'RESULT:{{"error":"no_namespace"}}'; exit }}
$gopro = $ns17.Items() | Where-Object {{$_.Name -match "{GOPRO_MODEL_MATCH_PATTERN}"}} | Select-Object -First 1
if (!$gopro) {{ Write-Output 'RESULT:{{"error":"not_found"}}'; exit }}

$currentFolder = $gopro.GetFolder
foreach ($part in $pathParts) {{
    $next = $null
    foreach ($it in $currentFolder.Items()) {{
        if ($it.Name -eq $part) {{
            try {{ $next = $it.GetFolder }} catch {{ $next = $null }}
            break
        }}
    }}
    if (!$next) {{ Write-Output 'RESULT:{{"error":"path_not_found"}}'; exit }}
    $currentFolder = $next
}}

$fileItem = $null
foreach ($it in $currentFolder.Items()) {{
    if ($it.Name -eq $fileName) {{ $fileItem = $it; break }}
}}
if (!$fileItem) {{ Write-Output 'RESULT:{{"error":"file_not_found"}}'; exit }}

if (!(Test-Path $targetDir)) {{ New-Item -ItemType Directory -Path $targetDir -Force | Out-Null }}
$destFolder = $shell.Namespace($targetDir)
if (!$destFolder) {{ Write-Output 'RESULT:{{"error":"no_dest"}}'; exit }}

$destPath = Join-Path $targetDir $destName
$destFolder.CopyHere($fileItem, 4 + 16 + 512 + 1024)

$timeout = 0
$lastSize = -1
$stableCount = 0
while ($timeout -lt 3600) {{
    Start-Sleep -Milliseconds 500
    if (Test-Path $destPath) {{
        $curSize = (Get-Item $destPath).Length
        if ($curSize -eq $lastSize -and $curSize -gt 0) {{
            # Groesse muss ZWEIMAL hintereinander gleich sein, bevor wir
            # "fertig" annehmen - verhindert, dass ein kurzer Stocker bei
            # grossen Dateien faelschlich als "abgeschlossen" gewertet wird.
            $stableCount++
            if ($stableCount -ge 2) {{ break }}
        }} else {{
            $stableCount = 0
        }}
        $lastSize = $curSize
    }}
    $timeout++
}}

$ok = Test-Path $destPath
$deleted = $false
if ($ok -and $deleteAfter) {{
    try {{
        foreach ($verb in $fileItem.Verbs()) {{
            if ($verb.Name -match "[Ll]öschen" -or $verb.Name -match "[Dd]elete") {{
                $verb.DoIt()
                $deleted = $true
                break
            }}
        }}
    }} catch {{}}
}}

$result = [PSCustomObject]@{{ ok = $ok; deleted = $deleted }}
Write-Output ("RESULT:" + ($result | ConvertTo-Json -Compress))
'''


def _extract_result_json(stdout_text):
    """Nimmt die LETZTE Zeile, die mit RESULT: beginnt (falls PowerShell
    vorher noch andere Ausgaben/Warnungen schreibt) und parst sie als JSON."""
    result_line = None
    for line in (stdout_text or "").splitlines():
        line = line.strip()
        if line.startswith("RESULT:"):
            result_line = line
    if result_line is None:
        return None
    try:
        return json.loads(result_line.split(":", 1)[1])
    except Exception:
        return None


class SyncWorkerThread(QThread):
    progress = Signal(int, int, str)
    finished_sync = Signal(bool, str, dict)

    def __init__(self, target_dir, delete_after, parent=None):
        super().__init__(parent)
        self.target_dir = target_dir
        self.delete_after = delete_after

    def run(self):
        # --- Phase 1: einmalig und schnell auflisten ---
        list_script = build_list_script()
        try:
            list_proc = subprocess.run(
                ['powershell', '-NoProfile', '-Command', list_script],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                startupinfo=_hidden_startupinfo(), timeout=40
            )
        except Exception as e:
            self.finished_sync.emit(False, f"Konnte PowerShell nicht starten: {e}", {})
            return

        payload = _extract_result_json(list_proc.stdout)
        if payload is None:
            detail = (list_proc.stdout or list_proc.stderr or "").strip()[:300]
            if detail:
                self.finished_sync.emit(False, f"Sync fehlgeschlagen: {detail}", {})
            else:
                self.finished_sync.emit(False, "Sync fehlgeschlagen: Keine Rückmeldung von der Kamera.", {})
            return

        if isinstance(payload, dict) and "error" in payload:
            messages = {
                "not_found": "GoPro wurde nicht gefunden. Bitte Verbindung prüfen.",
                "no_namespace": "Konnte nicht auf die Geräteliste zugreifen.",
            }
            self.finished_sync.emit(False, messages.get(payload["error"], "Unbekannter Fehler."), {})
            return

        # PowerShell/ConvertTo-Json liefert bei genau einem Treffer ein
        # einzelnes Objekt statt eines Arrays - hier vereinheitlichen.
        if isinstance(payload, dict):
            items = [payload]
        else:
            items = payload or []

        total = len(items)

        if total == 0:
            self.finished_sync.emit(True, "Keine neuen Bilder oder Videos gefunden.", {"total": 0, "copied": 0, "deleted": 0, "errors": 0})
            return

        try:
            os.makedirs(self.target_dir, exist_ok=True)
        except Exception:
            pass

        copied = 0
        deleted = 0
        errors = 0

        # --- Phase 2 + 3: pro Datei einzeln vergleichen und ggf. kopieren ---
        for idx, entry in enumerate(items, start=1):
            name = entry.get("name") or ""
            size = entry.get("size") or 0
            path_str = entry.get("path") or ""
            path_components = [p for p in path_str.split("|") if p]

            self.progress.emit(idx, total, name)

            dest_name = name
            dest_path = os.path.join(self.target_dir, dest_name)
            skip_copy = False

            if os.path.exists(dest_path):
                try:
                    existing_size = os.path.getsize(dest_path)
                except Exception:
                    existing_size = -1
                if size and size == existing_size:
                    # Gleicher Name, gleiche Groesse -> schon synchronisiert
                    copied += 1
                    skip_copy = True
                else:
                    base, ext = os.path.splitext(name)
                    counter = 1
                    while True:
                        candidate = f"{base}_{counter}{ext}"
                        candidate_path = os.path.join(self.target_dir, candidate)
                        if not os.path.exists(candidate_path):
                            dest_name = candidate
                            dest_path = candidate_path
                            break
                        counter += 1

            if skip_copy:
                continue

            copy_script = build_single_copy_script(path_components, name, self.target_dir, dest_name, self.delete_after)
            try:
                copy_proc = subprocess.run(
                    ['powershell', '-NoProfile', '-Command', copy_script],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    # WICHTIG: Das PowerShell-Skript selbst wartet intern bis zu
                    # 30 Minuten (siehe $timeout -lt 3600 in build_single_copy_script)
                    # auf den Abschluss der Kopie - das ist bei grossen GoPro-Videos
                    # (mehrere GB per MTP) durchaus noetig. Der Python-seitige
                    # subprocess-Timeout MUSS daher spuerbar groesser sein als der
                    # interne PowerShell-Timeout, sonst killt Python den Prozess
                    # (TimeoutExpired), BEVOR die eigentliche Kopie fertig ist -
                    # genau das fuehrte bisher bei grossen Videos zum Abbruch
                    # mitten im Sync (timeout stand vorher bei nur 90 Sekunden).
                    startupinfo=_hidden_startupinfo(), timeout=2000
                )
            except subprocess.TimeoutExpired:
                # Sollte dank des hohen Timeouts praktisch nie mehr passieren -
                # falls doch (z.B. USB-Verbindung haengt komplett), zaehlt die
                # Datei als Fehler, der Sync laeuft aber mit der naechsten
                # Datei weiter statt komplett abzubrechen.
                errors += 1
                continue
            except Exception:
                errors += 1
                continue

            copy_result = _extract_result_json(copy_proc.stdout)
            if isinstance(copy_result, dict) and copy_result.get("ok"):
                copied += 1
                if copy_result.get("deleted"):
                    deleted += 1
            else:
                errors += 1

        result_data = {"total": total, "copied": copied, "deleted": deleted, "errors": errors}

        msg = f"✅ {copied} von {total} Dateien übertragen."
        if self.delete_after:
            msg += f" {deleted} auf der GoPro gelöscht."
        if errors:
            msg += f" ⚠️ {errors} Fehler."

        self.finished_sync.emit(errors == 0, msg, result_data)


# --- [ UI KOMPONENTEN ] ---

class RoundedVideoContainer(QWidget):
    """
    Neue Implementierung: rendert Video über QGraphicsVideoItem in einer QGraphicsView.
    Die View bekommt eine abgerundete Maske, sodass das Video exakt runde Ecken hat.
    """
    def __init__(self, parent=None, radius=20):
        super().__init__(parent)
        self.radius = radius
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setContentsMargins(0, 0, 0, 0)

        # GraphicsView / Scene / VideoItem
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene, self)
        self.view.setStyleSheet("background: transparent; border: none;")
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.view.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)

        # QGraphicsVideoItem zum Rendern des Videos
        self.video_item = QGraphicsVideoItem()
        self.video_item.setSize(self.size())
        self.scene.addItem(self.video_item)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()

        # View und Scene anpassen
        self.view.setGeometry(0, 0, w, h)
        self.scene.setSceneRect(0, 0, w, h)

        # VideoItem auf die Scene-Größe setzen (Video füllt den Bereich)
        try:
            self.video_item.setSize(self.scene.sceneRect().size())
            self.video_item.setPos(0, 0)
        except Exception:
            pass

        # Abgerundete Maske für die gesamte View/Widget
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, self.radius, self.radius)
        region = QRegion(path.toFillPolygon().toPolygon())
        try:
            self.setMask(region)
        except Exception:
            pass
        try:
            self.view.viewport().setMask(region)
        except Exception:
            pass

    def paintEvent(self, event):
        # Leichtes Hintergrund-Fill, damit die Ecken sauber aussehen
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        path = QPainterPath()
        path.addRoundedRect(rect, self.radius, self.radius)
        painter.fillPath(path, QColor(20, 20, 30))
        painter.end()


class WaveProgressBar(QWidget):
    def __init__(self, show_battery_nub=False, parent=None):
        super().__init__(parent)
        self.show_battery_nub = show_battery_nub
        self.setFixedHeight(26)
        self.setMinimumWidth(70)
        self._value = -1
        self._display_value = 0.0
        self._color = QColor("#00cc66")
        
        self._anim = QPropertyAnimation(self, b"displayValue", self)
        self._anim.setDuration(700)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self._wave_phase = 0.0
        self._wave_timer = QTimer(self)
        self._wave_timer.timeout.connect(self._update_wave)
        self._wave_timer.start(30)

    def _update_wave(self):
        self._wave_phase += 0.15
        if self._value >= 0:
            self.update()

    def _get_display_value(self): return self._display_value
    def _set_display_value(self, v):
        self._display_value = v
        self.update()
    displayValue = Property(float, _get_display_value, _set_display_value)

    def set_value_and_color(self, value, hex_color):
        try: val = int(value)
        except Exception: val = -1
        self._value = val
        self._color = QColor(hex_color)
        
        target = float(max(2, min(100, val))) if val >= 0 else 0.0
        self._anim.stop()
        self._anim.setStartValue(self._display_value)
        self._anim.setEndValue(target)
        self._anim.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        
        if self.show_battery_nub:
            nub_w = max(4, h * 0.16)
            body_rect = QRectF(1, 2, w - nub_w - 3, h - 4)
            nub_rect = QRectF(body_rect.right() + 2, h * 0.28, nub_w, h * 0.44)
            painter.setPen(Qt.PenStyle.NoPen)
            nub_path = QPainterPath()
            nub_path.addRoundedRect(nub_rect, 2, 2)
            painter.fillPath(nub_path, QColor("#40404c"))
        else:
            body_rect = QRectF(1, 2, w - 2, h - 4)

        body_path = QPainterPath()
        body_path.addRoundedRect(body_rect, 5, 5)
        painter.fillPath(body_path, QColor("#1b1b20"))
        painter.setPen(QColor("#40404c"))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(body_path)

        if self._value < 0:
            painter.setPen(QColor("#ffffff")) 
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            painter.drawText(body_rect, Qt.AlignmentFlag.AlignCenter, "--")
            return

        pad = 3
        inner = QRectF(body_rect.left() + pad, body_rect.top() + pad,
                        body_rect.width() - 2 * pad, body_rect.height() - 2 * pad)
        
        fill_w = max(0.0, inner.width() * (self._display_value / 100.0))
        
        painter.save()
        clip_path = QPainterPath()
        clip_path.addRoundedRect(inner, 3, 3)
        painter.setClipPath(clip_path)

        wave_path = QPainterPath()
        wave_path.moveTo(inner.left(), inner.bottom())
        
        amplitude = 2.5
        for y in range(int(inner.height()), -1, -1):
            x = inner.left() + fill_w + math.sin((y * 0.3) + self._wave_phase) * amplitude
            wave_path.lineTo(x, inner.top() + y)
            
        wave_path.lineTo(inner.left(), inner.top())
        wave_path.closeSubpath()

        grad = QLinearGradient(inner.left(), 0, inner.left() + fill_w, 0)
        grad.setColorAt(0.0, self._color.darker(130))
        grad.setColorAt(1.0, self._color)
        
        painter.fillPath(wave_path, grad)
        painter.restore()

        # Draw percentage text centered over the bar
        try:
            pct_text = f"{int(round(self._display_value))}%"
        except Exception:
            pct_text = "--"
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.drawText(inner, Qt.AlignmentFlag.AlignCenter, pct_text)


class SyncProgressButton(QWidget):
    """
    Kombinierter Button + Fortschrittsanzeige fuer den Sync.
    Im Ruhezustand sieht er aus wie ein normaler Button ("Sync starten").
    Waehrend der Uebertragung fuellt er sich wie die Akku/Speicher-Wellen-Bars
    (gleiche Wellen-Animation, siehe WaveProgressBar) und zeigt den Fortschritt in %.
    """
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(250, 55)
        self._clickable = False
        self._is_syncing = False
        self._idle_text = "Sync starten"
        self._accent_color = QColor("#00f2fe")

        self._display_progress = 0.0
        self._progress_anim = QPropertyAnimation(self, b"displayProgress", self)
        self._progress_anim.setDuration(350)
        self._progress_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._wave_phase = 0.0
        self._wave_timer = QTimer(self)
        self._wave_timer.timeout.connect(self._tick_wave)
        self._wave_timer.start(30)

        self.setCursor(Qt.CursorShape.ArrowCursor)

    def _tick_wave(self):
        self._wave_phase += 0.15
        if self._is_syncing:
            self.update()

    def _get_display_progress(self): return self._display_progress
    def _set_display_progress(self, v):
        self._display_progress = v
        self.update()
    displayProgress = Property(float, _get_display_progress, _set_display_progress)

    def set_theme_color(self, hex_color):
        self._accent_color = QColor(hex_color)
        self.update()

    @property
    def is_syncing(self):
        return self._is_syncing

    def set_idle(self, clickable):
        """Ruhezustand: entweder normaler klickbarer Button oder deaktiviert (kein GoPro verbunden)."""
        self._is_syncing = False
        self._clickable = clickable
        self._display_progress = 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor if clickable else Qt.CursorShape.ArrowCursor)
        self.update()

    def start_sync_visual(self):
        self._is_syncing = True
        self._clickable = False
        self._display_progress = 0.0
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    def set_progress(self, current, total):
        pct = 0.0
        if total > 0:
            pct = max(0.0, min(100.0, (current / total) * 100.0))
        self._progress_anim.stop()
        self._progress_anim.setStartValue(self._display_progress)
        self._progress_anim.setEndValue(pct)
        self._progress_anim.start()

    def mousePressEvent(self, event):
        if self._clickable and not self._is_syncing:
            self.clicked.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        rect = QRectF(0, 0, w, h)
        path = QPainterPath()
        path.addRoundedRect(rect, 10, 10)

        if self._is_syncing:
            painter.fillPath(path, QColor("#1b1b20"))
            painter.setPen(QColor("#40404c"))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

            pad = 3
            inner = QRectF(rect.left() + pad, rect.top() + pad,
                            rect.width() - 2 * pad, rect.height() - 2 * pad)
            fill_w = max(0.0, inner.width() * (self._display_progress / 100.0))

            painter.save()
            clip_path = QPainterPath()
            clip_path.addRoundedRect(inner, 8, 8)
            painter.setClipPath(clip_path)

            wave_path = QPainterPath()
            wave_path.moveTo(inner.left(), inner.bottom())
            amplitude = 4
            for y in range(int(inner.height()), -1, -1):
                x = inner.left() + fill_w + math.sin((y * 0.25) + self._wave_phase) * amplitude
                wave_path.lineTo(x, inner.top() + y)
            wave_path.lineTo(inner.left(), inner.top())
            wave_path.closeSubpath()

            grad = QLinearGradient(inner.left(), 0, inner.left() + fill_w, 0)
            grad.setColorAt(0.0, self._accent_color.darker(130))
            grad.setColorAt(1.0, self._accent_color)
            painter.fillPath(wave_path, grad)
            painter.restore()

            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
            pct_text = f"{int(round(self._display_progress))}%"
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, pct_text)
        else:
            if self._clickable:
                grad = QLinearGradient(0, 0, w, 0)
                grad.setColorAt(0.0, self._accent_color)
                grad.setColorAt(1.0, QColor("#ffffff"))
                painter.fillPath(path, grad)
                painter.setPen(QColor("#ffffff"))
            else:
                painter.fillPath(path, QColor("#2c2c35"))
                painter.setPen(QColor("#888888"))
            painter.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._idle_text)


# --- [ THUMBNAILS & GALERIEN ] ---

THUMB_W, THUMB_H = 220, 150

def make_cover_thumbnail(pixmap, w=THUMB_W, h=THUMB_H, radius=12):
    if pixmap is None or pixmap.isNull():
        pixmap = QPixmap(w, h)
        pixmap.fill(QColor("#222228"))

    scaled = pixmap.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    x = max(0, (scaled.width() - w) // 2)
    y = max(0, (scaled.height() - h) // 2)
    cropped = scaled.copy(x, y, w, h)

    result = QPixmap(w, h)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, w, h, radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, cropped)
    painter.end()
    return result

def draw_play_badge(pixmap):
    result = QPixmap(pixmap)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy = result.width() / 2, result.height() / 2
    r = min(result.width(), result.height()) * 0.16
    painter.setBrush(QColor(0, 0, 0, 130))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
    
    triangle = QPainterPath()
    triangle.moveTo(cx - r * 0.35, cy - r * 0.55)
    triangle.lineTo(cx - r * 0.35, cy + r * 0.55)
    triangle.lineTo(cx + r * 0.6, cy)
    triangle.closeSubpath()
    painter.setBrush(QColor(255, 255, 255, 235))
    painter.drawPath(triangle)
    painter.end()
    return result

class ClickableThumbnail(QLabel):
    def __init__(self, pixmap, on_click, tooltip="", parent=None):
        super().__init__(parent)
        self.setPixmap(pixmap)
        self.setFixedSize(pixmap.size())
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if tooltip: self.setToolTip(tooltip)
        self._on_click = on_click
        self.setStyleSheet("QLabel { border-radius: 12px; outline: none; } QLabel:hover { outline: 2px solid #00f2fe; }")

    def mousePressEvent(self, event):
        if self._on_click: self._on_click()
        super().mousePressEvent(event)

class GalleryBase(QWidget):
    def __init__(self, folder, title, empty_icon, empty_text):
        super().__init__()
        self.folder = folder
        self.col_count = 3
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 22px; font-weight: bold;")
        outer.addWidget(title_lbl)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(self.grid_host)
        outer.addWidget(self.scroll)

        self.empty_lbl = QLabel(f"{empty_icon}\n{empty_text}")
        self.empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_lbl.setStyleSheet("font-size: 16px; color: #888;")
        outer.addWidget(self.empty_lbl)
        self.empty_lbl.hide()

    def show_empty(self):
        self.scroll.hide()
        self.empty_lbl.show()

    def get_files(self, exts):
        try: return sorted([f for f in os.listdir(self.folder) if f.lower().endswith(exts)])
        except: return []

    def refresh(self):
        """Leert das Grid und laedt die Dateien neu (z.B. nach einem Sync oder Ordnerwechsel)."""
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.empty_lbl.hide()
        self.scroll.show()
        self.populate()

class VideoGallery(GalleryBase):
    def __init__(self, folder):
        super().__init__(folder, "🎬 Videos", "🎬", "Noch keine Videos synchronisiert.")
        self.populate()

    def create_thumbnail(self, path):
        raw = None
        if _HAS_CV2:
            try:
                cap = cv2.VideoCapture(path)
                ret, frame = cap.read()
                cap.release()
                if ret:
                    h, w, ch = frame.shape
                    bytes_per_line = ch * w
                    img = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_BGR888)
                    raw = QPixmap.fromImage(img.copy())
            except Exception: pass
        
        cover = make_cover_thumbnail(raw, THUMB_W, THUMB_H)
        return draw_play_badge(cover)

    def populate(self):
        files = self.get_files((".mp4",))
        if not files: self.show_empty(); return
        for i, f in enumerate(files):
            p = os.path.join(self.folder, f)
            thumb = self.create_thumbnail(p)
            lbl = ClickableThumbnail(thumb, lambda checked=False, path=p: self.play_video(path), tooltip=f)
            self.grid.addWidget(lbl, i // self.col_count, i % self.col_count)

    def play_video(self, path):
        dlg = QDialog(self)
        dlg.resize(800, 500)
        dlg.setStyleSheet("background: #000;")
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0,0,0,0)
        vw = QVideoWidget()
        layout.addWidget(vw)
        
        player = QMediaPlayer(dlg)
        audio = QAudioOutput(dlg)
        player.setAudioOutput(audio)
        player.setVideoOutput(vw)
        player.setSource(QUrl.fromLocalFile(path))
        player.play()
        dlg.exec()
        player.stop()

class PictureGallery(GalleryBase):
    def __init__(self, folder):
        super().__init__(folder, "📸 Bilder", "📸", "Noch keine Bilder synchronisiert.")
        self.populate()

    def populate(self):
        files = self.get_files((".jpg", ".png", ".jpeg"))
        if not files: self.show_empty(); return
        for i, f in enumerate(files):
            p = os.path.join(self.folder, f)
            pix = QPixmap(p)
            thumb = make_cover_thumbnail(pix, THUMB_W, THUMB_H)
            lbl = ClickableThumbnail(thumb, lambda: None, tooltip=f)
            self.grid.addWidget(lbl, i // self.col_count, i % self.col_count)


# --- [ HAUPT-SYNC-TAB ] ---

class SyncTabWidget(QWidget):
    folder_changed = Signal(str)
    sync_finished = Signal()

    def __init__(self, get_theme_color_cb):
        super().__init__()
        self.get_theme_color = get_theme_color_cb
        self.gopro_connected = False
        self._current_model = None
        self.config = load_config()
        self.sync_target_dir = os.path.normpath(self.config.get("target_dir", os.path.expanduser("~/Videos/GoProSync")))
        self.init_ui()
        self.update_ui_state(False)

        self.monitor_thread = DeviceMonitorThread(self)
        self.monitor_thread.connection_changed.connect(self.update_ui_state)
        self.monitor_thread.status_ready.connect(self.apply_status)
        # HINWEIS: Thread wird hier NICHT mehr gestartet. Wird von main() aufgerufen,
        # wenn das Fenster sichtbar ist.

    def start_monitoring(self):
        """Wird aufgerufen, sobald die UI vollständig geladen und sichtbar ist."""
        self.monitor_thread.start()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(25)

        self.title_label = QLabel()
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)

        content_layout = QHBoxLayout()
        
        self.media_wrapper = QWidget()
        # FIX: Video-Container deutlich größer und quadratisch gemacht
        self.media_wrapper.setFixedSize(420, 420)
        add_drop_shadow(self.media_wrapper, 30, 10, 120) 
        media_wrapper_layout = QVBoxLayout(self.media_wrapper)
        media_wrapper_layout.setContentsMargins(0, 0, 0, 0)

        self.media_stack = QStackedWidget()
        
        self.placeholder = QLabel("🔌\nWarte auf Verbindung...")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff; background-color: rgba(20, 20, 30, 0.7); border-radius: 20px;")
        self.media_stack.addWidget(self.placeholder)

        # Use our RoundedVideoContainer which now renders via QGraphicsVideoItem
        self.rounded_video = RoundedVideoContainer()
        self.media_stack.addWidget(self.rounded_video)
        
        media_wrapper_layout.addWidget(self.media_stack)
        content_layout.addWidget(self.media_wrapper)

        self.connect_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.0) 
        self.connect_player.setAudioOutput(self.audio_output)
        # IMPORTANT: setVideoOutput to the QGraphicsVideoItem
        self.connect_player.setVideoOutput(self.rounded_video.video_item)
        
        clip_path = asset_path("GoPro Hero 11 .mp4")
        if os.path.exists(clip_path):
            self.connect_player.setSource(QUrl.fromLocalFile(clip_path))
            
        self.connect_player.positionChanged.connect(self._on_video_position_changed)

        stats_widget = QWidget()
        stats_widget.setStyleSheet("background-color: rgba(30, 30, 40, 0.8); border-radius: 15px;")
        stats_widget.setFixedWidth(280)
        add_drop_shadow(stats_widget, 20, 5, 80)
        stats_layout = QVBoxLayout(stats_widget)

        stats_title = QLabel("Geräte-Info")
        stats_title.setStyleSheet("font-size: 16px; font-weight: bold; border-bottom: 1px solid #444; padding-bottom: 10px;")
        stats_layout.addWidget(stats_title)

        self.stat_status = QLabel()
        stats_layout.addWidget(self.stat_status)
        
        self.bar_battery = WaveProgressBar(show_battery_nub=True)
        stats_layout.addWidget(QLabel("⚡ Akku"))
        stats_layout.addWidget(self.bar_battery)
        
        self.bar_storage = WaveProgressBar(show_battery_nub=False)
        self.lbl_store_detail = QLabel("")
        stats_layout.addWidget(QLabel("💾 Speicher"))
        stats_layout.addWidget(self.bar_storage)
        stats_layout.addWidget(self.lbl_store_detail)
        
        content_layout.addWidget(stats_widget)
        layout.addLayout(content_layout)

        settings_row = QHBoxLayout()
        self.lbl_folder = QLabel(f"📁 {self.sync_target_dir}")
        self.lbl_folder.setStyleSheet("color: #ccc; font-size: 13px;")
        self.btn_choose_folder = QPushButton("Ordner wählen")
        self.btn_choose_folder.setFixedHeight(32)
        self.btn_choose_folder.clicked.connect(self.choose_folder)
        settings_row.addWidget(self.lbl_folder, 1)
        settings_row.addWidget(self.btn_choose_folder)
        layout.addLayout(settings_row)

        self.chk_delete_after = QCheckBox("Nach der Übertragung von der GoPro löschen")
        self.chk_delete_after.setChecked(self.config.get("delete_after_sync", False))
        self.chk_delete_after.stateChanged.connect(self.on_delete_toggle)
        layout.addWidget(self.chk_delete_after, alignment=Qt.AlignmentFlag.AlignCenter)

        self.btn_sync = SyncProgressButton()
        self.btn_sync.clicked.connect(self.start_sync)
        layout.addWidget(self.btn_sync, alignment=Qt.AlignmentFlag.AlignCenter)

        self.sync_popup = QLabel("")
        self.sync_popup.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sync_popup.setStyleSheet("""
            QLabel {
                background-color: rgba(30, 30, 40, 0.9);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 10px;
                padding: 8px 16px;
                color: #ddd;
                font-size: 13px;
            }
        """)
        self.sync_popup.setFixedWidth(420)
        self.sync_popup.hide()
        layout.addWidget(self.sync_popup, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()

    def apply_theme(self):
        c = self.get_theme_color()
        self.btn_sync.set_theme_color(c)
        if self.gopro_connected:
            self.stat_status.setStyleSheet(f"color: {c}; font-size: 15px; font-weight: bold;")
        else:
            self.stat_status.setStyleSheet("color: #ff4c4c; font-size: 15px;")

    def _on_video_position_changed(self, pos):
        dur = self.connect_player.duration()
        if dur > 0 and pos >= dur - 50:
            self.connect_player.pause()

    def update_ui_state(self, connected, model=""):
        self.gopro_connected = connected
        c = self.get_theme_color()
        if connected:
            profile = GOPRO_MODELS.get(model, GOPRO_MODELS["HERO11"])

            # Video nur wechseln, wenn sich das Modell tatsaechlich geaendert
            # hat (spart unnoetiges Neuladen bei jedem Status-Update).
            if model != self._current_model:
                self._current_model = model
                clip_path = asset_path(profile["video"])
                self.connect_player.stop()
                if os.path.exists(clip_path):
                    self.connect_player.setSource(QUrl.fromLocalFile(clip_path))
                else:
                    # Kein passendes Video im assets-Ordner gefunden - Platzhalter
                    # anzeigen statt eines leeren/eingefrorenen Videobilds.
                    self.connect_player.setSource(QUrl())

            self.title_label.setText(profile["display"])
            self.title_label.setStyleSheet(f"font-size: 38px; font-weight: 900; letter-spacing: 2px;")
            if not self.btn_sync.is_syncing:
                self.btn_sync.set_idle(True)
            self.media_stack.setCurrentIndex(1)
            
            self.connect_player.setPosition(0)
            self.connect_player.play()
            
            self.stat_status.setText("🟢 Verbunden")
            self.stat_status.setStyleSheet(f"color: {c}; font-size: 15px; font-weight: bold;")
            self.lbl_store_detail.setText("Lese Status...")
        else:
            self._current_model = None
            self.title_label.setText("GoPro anschließen")
            self.title_label.setStyleSheet("font-size: 26px; font-weight: bold;")
            if not self.btn_sync.is_syncing:
                self.btn_sync.set_idle(False)
            self.connect_player.stop()
            self.media_stack.setCurrentIndex(0)
            self.stat_status.setText("🔴 Nicht verbunden")
            self.stat_status.setStyleSheet("color: #ff4c4c; font-size: 15px;")
            self.bar_battery.set_value_and_color(-1, "#333")
            self.bar_storage.set_value_and_color(0, "#333")
            self.lbl_store_detail.setText("")

    def choose_folder(self):
        new_dir = QFileDialog.getExistingDirectory(self, "Zielordner wählen", self.sync_target_dir)
        if new_dir:
            self.sync_target_dir = os.path.normpath(new_dir)
            self.config["target_dir"] = self.sync_target_dir
            save_config(self.config)
            self.lbl_folder.setText(f"📁 {self.sync_target_dir}")
            self.folder_changed.emit(self.sync_target_dir)

    def on_delete_toggle(self, state):
        self.config["delete_after_sync"] = bool(state)
        save_config(self.config)

    def start_sync(self):
        if not self.gopro_connected:
            return
        if hasattr(self, "sync_worker") and self.sync_worker is not None and self.sync_worker.isRunning():
            return

        self.btn_sync.start_sync_visual()
        self.btn_choose_folder.setEnabled(False)
        self.sync_popup.setText("🔎 Suche nach Dateien auf der GoPro...")
        self.sync_popup.show()

        delete_after = self.chk_delete_after.isChecked()
        self.sync_worker = SyncWorkerThread(self.sync_target_dir, delete_after, self)
        self.sync_worker.progress.connect(self.on_sync_progress)
        self.sync_worker.finished_sync.connect(self.on_sync_done)
        self.sync_worker.start()

    @Slot(int, int, str)
    def on_sync_progress(self, current, total, name):
        self.btn_sync.set_progress(current, total)
        self.sync_popup.setText(f"⬆️ Übertrage {current} von {total} Dateien\n{name}")
        self.sync_popup.show()

    @Slot(bool, str, dict)
    def on_sync_done(self, success, message, stats):
        self.btn_sync.set_idle(self.gopro_connected)
        self.btn_choose_folder.setEnabled(True)
        self.sync_popup.setText(message)
        self.sync_popup.show()
        self.sync_finished.emit()
        QTimer.singleShot(8000, self._hide_sync_popup)

    def _hide_sync_popup(self):
        if not (hasattr(self, "sync_worker") and self.sync_worker is not None and self.sync_worker.isRunning()):
            self.sync_popup.hide()

    @Slot(dict)
    def apply_status(self, status):
        if not self.gopro_connected: return
        bat = status["battery"]
        store = status["storage_pct"]
        if bat is not None:
            self.bar_battery.set_value_and_color(bat, "#00cc66" if bat >= 20 else "#ff4c4c")
        if store is not None:
            c = self.get_theme_color()
            self.bar_storage.set_value_and_color(store, c)
            self.lbl_store_detail.setText(f"{status['free_str']} frei")


# --- [ MAIN WINDOW ] ---

# --- [ THEME-EINSTELLUNGEN: FARBE, HINTERGRUNDBILD, WEICHZEICHNER ] ---

class ThemeSettingsDialog(QDialog):
    """Dialog für Akzentfarbe, ein eigenes Hintergrundbild und dessen
    Weichzeichner-Stärke. Jede Änderung wird sofort (Live-Vorschau) über
    on_apply an das MainWindow zurückgemeldet und dort gespeichert."""

    def __init__(self, parent, config, on_apply):
        super().__init__(parent)
        self.setWindowTitle("Theme")
        self.setMinimumWidth(400)
        self.config = config
        self.on_apply = on_apply
        self.setStyleSheet(f"""
            QDialog {{ background-color: #20222c; }}
            * {{ color: #ffffff; font-family: {FONT_STACK}; }}
            QPushButton {{
                background-color: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 8px; padding: 8px 14px;
            }}
            QPushButton:hover {{ background-color: rgba(255,255,255,0.16); }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        # --- Akzentfarbe ---
        color_row = QHBoxLayout()
        color_label = QLabel("Akzentfarbe")
        color_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        color_row.addWidget(color_label)
        color_row.addStretch()
        self.btn_color = QPushButton()
        self.btn_color.setFixedSize(48, 30)
        self._update_color_button()
        self.btn_color.clicked.connect(self.pick_color)
        color_row.addWidget(self.btn_color)
        layout.addLayout(color_row)

        # --- Eigenes Hintergrundbild ---
        bg_label = QLabel("Eigenes Hintergrundbild")
        bg_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(bg_label)

        bg_btn_row = QHBoxLayout()
        self.btn_choose_bg = QPushButton("🖼️ Bild wählen…")
        self.btn_choose_bg.clicked.connect(self.pick_background)
        self.btn_clear_bg = QPushButton("Entfernen")
        self.btn_clear_bg.clicked.connect(self.clear_background)
        bg_btn_row.addWidget(self.btn_choose_bg)
        bg_btn_row.addWidget(self.btn_clear_bg)
        layout.addLayout(bg_btn_row)

        self.lbl_bg_path = QLabel(self._bg_display_text())
        self.lbl_bg_path.setStyleSheet("color: #999; font-size: 11px;")
        self.lbl_bg_path.setWordWrap(True)
        layout.addWidget(self.lbl_bg_path)

        # --- Weichzeichner-Slider ---
        blur_row = QHBoxLayout()
        blur_title = QLabel("Weichzeichnung (Hintergrund)")
        blur_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        blur_row.addWidget(blur_title)
        blur_row.addStretch()
        self.lbl_blur_value = QLabel(f"{int(config.get('background_blur', 0))} px")
        self.lbl_blur_value.setStyleSheet("color: #ccc; font-size: 12px;")
        blur_row.addWidget(self.lbl_blur_value)
        layout.addLayout(blur_row)

        self.slider_blur = QSlider(Qt.Orientation.Horizontal)
        self.slider_blur.setRange(0, 60)
        self.slider_blur.setValue(int(config.get("background_blur", 0)))
        self.slider_blur.valueChanged.connect(self.on_blur_changed)
        layout.addWidget(self.slider_blur)

        hint = QLabel("Damit lassen sich die Bedienelemente optisch vom Hintergrundbild abheben.")
        hint.setStyleSheet("color: #777; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addStretch()

        btn_close = QPushButton("Schließen")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    def _bg_display_text(self):
        path = self.config.get("background_image", "")
        if path:
            return f"Aktuell: {os.path.basename(path)}"
        return "Kein eigenes Bild gesetzt – Standard-Verlauf ist aktiv."

    def _update_color_button(self):
        c = self.config.get("accent_color", "#00f2fe")
        self.btn_color.setStyleSheet(
            f"background-color: {c}; border-radius: 6px; border: 1px solid rgba(255,255,255,0.3);"
        )

    def pick_color(self):
        current = QColor(self.config.get("accent_color", "#00f2fe"))
        new_color = QColorDialog.getColor(current, self, "Theme Farbe wählen")
        if new_color.isValid():
            self.config["accent_color"] = new_color.name()
            self._update_color_button()
            self.on_apply()

    def pick_background(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Hintergrundbild wählen", "",
            "Bilder (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if path:
            self.config["background_image"] = path
            self.lbl_bg_path.setText(self._bg_display_text())
            self.on_apply()

    def clear_background(self):
        self.config["background_image"] = ""
        self.lbl_bg_path.setText(self._bg_display_text())
        self.on_apply()

    def on_blur_changed(self, value):
        self.config["background_blur"] = value
        self.lbl_blur_value.setText(f"{value} px")
        self.on_apply()


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.setWindowTitle("GoPro Sync Pro")
        self.resize(1000, 650)
        
        self.setObjectName("MainWindow")
        self.setStyleSheet(f"""
            QWidget#MainWindow {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1a1b26, stop:1 #2d3340);
            }}
            * {{ color: #ffffff; font-family: {FONT_STACK}; }}
        """)

        # Eigenes Hintergrundbild (optional) - liegt als "freier" Kind-Widget
        # unterhalb von Sidebar/Seiten und wird per resizeEvent passend zur
        # Fenstergröße zugeschnitten (wie CSS "background-size: cover").
        # Ohne eigenes Bild bleibt es unsichtbar und man sieht den normalen
        # Verlaufshintergrund von oben.
        self.bg_label = QLabel(self)
        self.bg_label.setScaledContents(False)
        self._bg_source_pixmap = None
        self.bg_blur_effect = QGraphicsBlurEffect(self.bg_label)
        self.bg_blur_effect.setBlurRadius(0)
        self.bg_label.setGraphicsEffect(self.bg_blur_effect)
        self.bg_label.hide()
        self.bg_label.lower()

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(220)
        self.sidebar.setStyleSheet("background-color: rgba(15, 15, 20, 0.6); border-right: 1px solid rgba(255,255,255,0.1);")
        sidebar_layout = QVBoxLayout(self.sidebar)
        
        app_logo = QLabel()
        app_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Kein Rahmen/Hintergrund/Frame auf dem Label selbst - falls der
        # "komische Rand" von einer Qt-Standardumrandung kam statt vom Bild.
        app_logo.setStyleSheet("background: transparent; border: none; padding: 0px; margin: 0px;")
        app_logo.setFrameShape(QFrame.Shape.NoFrame)
        app_logo.setContentsMargins(0, 0, 0, 0)
        logo_pix = QPixmap(asset_path("GoPro Logo.png"))
        if not logo_pix.isNull():
            # Transparente Ränder rund um das eigentliche Logo abschneiden,
            # damit kein unnötiger Leerraum/Rand mehr sichtbar ist.
            logo_pix = trim_transparent_margins(logo_pix)
            app_logo.setPixmap(logo_pix.scaledToWidth(140, Qt.TransformationMode.SmoothTransformation))
        sidebar_layout.addWidget(app_logo)
        sidebar_layout.addSpacing(30)

        self.btn_style = """
            QPushButton { background-color: transparent; font-size: 15px; font-weight: bold; text-align: left; padding: 12px; border: none; border-radius: 8px;}
            QPushButton:hover { background-color: rgba(255, 255, 255, 0.1); }
            QPushButton:checked { background-color: %s; }
        """
        
        self.btn_nav_sync = QPushButton("🔄 Sync")
        self.btn_nav_sync.setCheckable(True)
        self.btn_nav_sync.setChecked(True)
        
        self.btn_nav_videos = QPushButton("🎬 Videos")
        self.btn_nav_videos.setCheckable(True)
        
        self.btn_nav_pictures = QPushButton("📸 Bilder")
        self.btn_nav_pictures.setCheckable(True)

        sidebar_layout.addWidget(self.btn_nav_sync)
        sidebar_layout.addWidget(self.btn_nav_videos)
        sidebar_layout.addWidget(self.btn_nav_pictures)
        sidebar_layout.addStretch()

        self.btn_theme = QPushButton("🎨 Theme")
        self.btn_theme.setStyleSheet("QPushButton { background-color: transparent; font-size: 14px; text-align: left; padding: 10px; color: #aaa; border-radius: 8px; } QPushButton:hover { color: #fff; background-color: rgba(255,255,255,0.1); }")
        self.btn_theme.clicked.connect(self.change_theme)
        sidebar_layout.addWidget(self.btn_theme)

        self.pages = QStackedWidget()
        self.sync_page = SyncTabWidget(self.get_current_theme_color)
        self.videos_page = VideoGallery(self.sync_page.sync_target_dir)
        self.pictures_page = PictureGallery(self.sync_page.sync_target_dir)
        
        self.pages.addWidget(self.sync_page)
        self.pages.addWidget(self.videos_page)
        self.pages.addWidget(self.pictures_page)

        self.btn_nav_sync.clicked.connect(lambda: self.switch_page(0, self.btn_nav_sync))
        self.btn_nav_videos.clicked.connect(lambda: self.switch_page(1, self.btn_nav_videos))
        self.btn_nav_pictures.clicked.connect(lambda: self.switch_page(2, self.btn_nav_pictures))

        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(self.pages)

        self.sync_page.folder_changed.connect(self.on_sync_folder_changed)
        self.sync_page.sync_finished.connect(self.on_sync_finished)

        self.update_sidebar_theme()
        self.apply_background()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_bg_pixmap_geometry()

    def apply_background(self):
        """Liest background_image/background_blur aus der Config und zeigt
        entweder das eigene Hintergrundbild (weichgezeichnet) oder - falls
        keins gesetzt ist - lässt einfach den normalen Verlauf durchscheinen."""
        path = self.config.get("background_image", "")
        blur_val = int(self.config.get("background_blur", 0) or 0)

        if path and os.path.exists(path):
            pix = QPixmap(path)
            if not pix.isNull():
                self._bg_source_pixmap = pix
                self.bg_blur_effect.setBlurRadius(blur_val)
                self.bg_label.show()
                self._update_bg_pixmap_geometry()
                return

        self._bg_source_pixmap = None
        self.bg_label.hide()

    def _update_bg_pixmap_geometry(self):
        if self._bg_source_pixmap is None:
            return
        self.bg_label.setGeometry(0, 0, self.width(), self.height())
        cover = cover_scaled_pixmap(self._bg_source_pixmap, self.bg_label.size())
        self.bg_label.setPixmap(cover)
        self.bg_label.lower()

    def on_sync_folder_changed(self, new_dir):
        self.videos_page.folder = new_dir
        self.pictures_page.folder = new_dir
        self.videos_page.refresh()
        self.pictures_page.refresh()

    def on_sync_finished(self):
        self.videos_page.refresh()
        self.pictures_page.refresh()

    def get_current_theme_color(self):
        return self.config.get("accent_color", "#00f2fe")

    def update_sidebar_theme(self):
        c = self.get_current_theme_color()
        style = self.btn_style % c
        self.btn_nav_sync.setStyleSheet(style)
        self.btn_nav_videos.setStyleSheet(style)
        self.btn_nav_pictures.setStyleSheet(style)
        self.sync_page.apply_theme()
        if self.sync_page.gopro_connected:
            self.sync_page.stat_status.setStyleSheet(f"color: {c}; font-size: 15px; font-weight: bold;")
            self.sync_page.bar_storage.set_value_and_color(self.sync_page.bar_storage._value, c)

    def change_theme(self):
        def _apply_changes():
            save_config(self.config)
            self.update_sidebar_theme()
            self.apply_background()

        dlg = ThemeSettingsDialog(self, self.config, _apply_changes)
        dlg.exec()

    def switch_page(self, idx, btn):
        self.pages.setCurrentIndex(idx)
        self.btn_nav_sync.setChecked(False)
        self.btn_nav_videos.setChecked(False)
        self.btn_nav_pictures.setChecked(False)
        btn.setChecked(True)

    def closeEvent(self, event):
        monitor = getattr(self.sync_page, "monitor_thread", None)
        if monitor is not None:
            monitor.stop()
            monitor.wait(3000)
        super().closeEvent(event)


# --- [ ANIMATED SPLASH SCREEN ] ---

class AnimatedSplash(QWidget):
    def __init__(self, logo_path):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(560, 360)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.logo_pix = QPixmap(logo_path)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_spin)
        self.timer.start(16) 

    def _update_spin(self):
        self.angle = (self.angle + 6) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 15, 15)
        grad = QLinearGradient(0, 0, self.width(), self.height())
        grad.setColorAt(0, QColor("#1a1b26"))
        grad.setColorAt(1, QColor("#2d3340"))
        painter.fillPath(path, grad)
        
        if not self.logo_pix.isNull():
            scaled_logo = self.logo_pix.scaledToWidth(260, Qt.TransformationMode.SmoothTransformation)
            x = (self.width() - scaled_logo.width()) // 2
            y = (self.height() - scaled_logo.height()) // 2 - 20
            painter.drawPixmap(x, y, scaled_logo)
            
        cx, cy = self.width() // 2, self.height() - 60
        r = 15
        pen = QPen(QColor(0, 242, 254), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(cx - r, cy - r, r * 2, r * 2, -self.angle * 16, 120 * 16)


def main():
    app = QApplication(sys.argv)
    
    config = load_config()
    def get_glow_color():
        return config.get("accent_color", "#00f2fe")
        
    glow_animator = GlowHoverAnimator(get_glow_color)
    app.installEventFilter(glow_animator)
    app._glow_animator = glow_animator

    splash = AnimatedSplash(asset_path("GoPro Logo.png"))
    splash.show()
    app.processEvents()

    window = MainWindow()

    def _reveal_main_window():
        window.show()
        splash.timer.stop()
        splash.close()
        # FIX: Startet die Abfrage der GoPro erst HIER.
        # Dadurch triggert das Video garantiert erst, wenn die UI da ist!
        window.sync_page.start_monitoring()

    QTimer.singleShot(2000, _reveal_main_window)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()