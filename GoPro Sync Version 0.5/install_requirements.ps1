# =============================================================
#  GoPro Sync Pro - Setup-Skript
#  Installiert (falls noetig) Python und alle benoetigten
#  Python-Pakete (PySide6, opencv-python, bleak).
#
#  Einfach doppelklicken auf "install.bat" im selben Ordner,
#  oder dieses Skript manuell starten mit:
#    powershell -ExecutionPolicy Bypass -File install_requirements.ps1
# =============================================================

$ErrorActionPreference = "Stop"

Write-Host "=== GoPro Sync Pro - Setup ===" -ForegroundColor Cyan
Write-Host ""

function Test-PythonInstalled {
    try {
        $null = & python --version 2>&1
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

if (-not (Test-PythonInstalled)) {
    Write-Host "Python wurde nicht gefunden." -ForegroundColor Yellow

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "Installiere Python 3.12 automatisch ueber winget..." -ForegroundColor Yellow
        winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements

        Write-Host ""
        Write-Host "Python wurde installiert. Bitte dieses Fenster schliessen und" -ForegroundColor Yellow
        Write-Host "install.bat NOCH EINMAL starten, damit Windows Python im PATH erkennt." -ForegroundColor Yellow
        Read-Host "Enter zum Beenden druecken"
        exit 0
    } else {
        Write-Host "winget ist auf diesem PC nicht verfuegbar." -ForegroundColor Red
        Write-Host "Bitte Python manuell installieren: https://www.python.org/downloads/" -ForegroundColor Red
        Write-Host "WICHTIG: Bei der Installation unbedingt 'Add Python to PATH' ankreuzen!" -ForegroundColor Red
        Read-Host "Enter zum Beenden druecken"
        exit 1
    }
}

Write-Host "Python gefunden: $(python --version)" -ForegroundColor Green
Write-Host ""

Write-Host "Aktualisiere pip..." -ForegroundColor Cyan
python -m pip install --upgrade pip

$reqFile = Join-Path $PSScriptRoot "requirements.txt"

Write-Host ""
if (Test-Path $reqFile) {
    Write-Host "Installiere benoetigte Pakete aus requirements.txt..." -ForegroundColor Cyan
    python -m pip install --upgrade -r $reqFile
} else {
    Write-Host "requirements.txt nicht gefunden - installiere Pakete direkt..." -ForegroundColor Yellow
    python -m pip install --upgrade PySide6 opencv-python bleak
}

Write-Host ""
Write-Host "=== Fertig! ===" -ForegroundColor Green
Write-Host "Die App kannst du jetzt starten mit:" -ForegroundColor Green
Write-Host "    python main.py" -ForegroundColor White
Write-Host ""
Read-Host "Enter zum Beenden druecken"
