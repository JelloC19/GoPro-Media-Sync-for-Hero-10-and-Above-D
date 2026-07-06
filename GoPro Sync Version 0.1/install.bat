@echo off
REM Doppelklicken startet das Setup - keine PowerShell-Kenntnisse noetig.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_requirements.ps1"
pause
