# GoPro Sync

Eine kleine, moderne Desktop-App, die deine **GoPro HERO11 Black** (oder jede andere
GoPro) automatisch erkennt, sobald du sie per USB anschließt, und Fotos/Videos in
einen von dir festgelegten Ordner kopiert. Zusätzlich gibt es eine Galerie mit
getrennter Video-/Foto-Ansicht und eingebautem Player.

## Funktionen

- **Automatische Erkennung**: Erkennt die GoPro anhand ihres `DCIM/xxxGOPRO`-Ordners,
  sobald sie per USB verbunden wird – kein manuelles Suchen nötig.
- **Abfrage oder Automatik**: Standardmäßig fragt die App "Jetzt synchronisieren?".
  Kann in den Optionen deaktiviert werden, dann startet der Sync sofort.
- **Fancy Progress Bubble**: Runde, animierte Fortschrittsanzeige mit Prozent,
  Dateizähler ("3 von 10 Dateien") und aktuellem Dateinamen.
- **Galerie-Tab**: Videos und Fotos getrennt als Kachel-Raster mit Thumbnails.
  Videos werden per Doppelklick in einem eingebauten Player abgespielt
  (Play/Pause, Zeitleiste, Lautstärke). Fotos öffnen sich in einem
  Vollbild-Viewer mit Vor/Zurück-Navigation (Pfeiltasten).
- **Optionen**: nach Datum sortieren, Originale auf der Kamera nach dem
  Kopieren löschen, bereits vorhandene Dateien werden übersprungen
  (inkrementeller Sync).

## Installation

Voraussetzung: Python 3.10 oder neuer.

```bash
cd GoProSync
pip install -r requirements.txt
python main.py
```

Unter Windows reicht ein Doppelklick auf `main.py`, wenn Python korrekt
installiert ist (oder `py main.py` in der Konsole).

## Eigenes Kamerafoto einbinden

Standardmäßig zeigt die App eine gezeichnete Platzhalter-Illustration einer
Actioncam (aus Copyright-Gründen kann ich kein echtes GoPro-Produktfoto
mitliefern). Um dein eigenes Foto zu verwenden:

1. Foto deiner HERO11 Black besorgen (am besten freigestellt, quadratisch,
   min. 400×400 px, PNG mit transparentem Hintergrund sieht am besten aus).
2. Datei als `hero11.png` speichern.
3. In den Ordner `assets/` legen (`GoProSync/assets/hero11.png`).
4. App neu starten – das Foto wird automatisch verwendet.

## Als eigenständige .exe packen (optional)

```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --name "GoProSync" --add-data "assets;assets" main.py
```

Die fertige `GoProSync.exe` liegt danach im Ordner `dist/`.

## Funktionsweise der Geräteerkennung

GoPros melden sich beim Anschluss per USB (im "Massenspeicher"-Modus) als
normales Laufwerk mit einem `DCIM`-Ordner, der Unterordner wie `100GOPRO`
enthält. Die App prüft alle 2 Sekunden im Hintergrund alle angeschlossenen
Laufwerke auf dieses Muster – das funktioniert zuverlässig unter Windows,
macOS und Linux, ganz ohne herstellerspezifische Treiber.

> **Hinweis:** Manche GoPro-Modelle bieten zusätzlich einen "GoPro Connect"-
> bzw. MTP-Modus an. Falls deine Kamera nicht erkannt wird, stelle im
> Kamera-Menü unter *Verbindungen → USB-Verbindung* sicher, dass
> **"MTP" bzw. "Massenspeicher"** ausgewählt ist (nicht "GoPro Connect").

## Projektstruktur

```
GoProSync/
├── main.py                      Einstiegspunkt
├── requirements.txt
├── core/
│   ├── config.py                Gespeicherte Einstellungen
│   ├── usb_watcher.py           Erkennt angeschlossene GoPros
│   ├── file_copier.py           Kopiert Dateien im Hintergrund-Thread
│   └── media_scanner.py         Scannt Zielordner für die Galerie
├── ui/
│   ├── theme.py                 Farbschema / Stylesheet
│   ├── circular_progress.py     Die "Progress Bubble"
│   ├── sync_tab.py               Tab 1: Kamera & Sync
│   ├── gallery_tab.py            Tab 2: Galerie
│   ├── video_thumbnail.py       Video-Vorschaubilder
│   ├── video_player_dialog.py   Eingebauter Video-Player
│   ├── image_viewer_dialog.py   Bildbetrachter
│   └── main_window.py           Hauptfenster
└── assets/
    ├── camera_placeholder.svg   Platzhalter-Illustration
    └── hero11.png                (optional, dein eigenes Foto)
```

## Anpassungsideen

- Farbschema in `ui/theme.py` ändern (z. B. eigenes Akzentgrün/-orange).
- In `core/file_copier.py` weitere Dateiendungen ergänzen (z. B. `.360` für
  MAX/360-Kameras ist bereits enthalten).
- Autostart beim Windows-Login: Verknüpfung der `GoProSync.exe` in den
  Autostart-Ordner (`shell:startup`) legen.
