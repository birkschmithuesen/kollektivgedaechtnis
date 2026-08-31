@echo off
rem Der Kern: Graph, Telegram-Fotoeingang, Interviewablauf.
rem
rem Die Ausgabe geht ins Fenster UND in eine Datei.
rem
rem Die Pipe baut CMD, nicht PowerShell - PowerShell bekommt den Text nur
rem noch ueber die Standardeingabe. Der Grund (gemessen 2026-08-31): ruft
rem PowerShell das Programm SELBST auf, wertet es jede stderr-Zeile als
rem Fehlerobjekt. uvicorn und das Protokoll schreiben ihre voellig
rem harmlosen INFO-Zeilen aber nach stderr - die Folge waren seitenweise
rem rote "NativeCommandError"-Bloecke mit "In Zeile:1 Zeichen:5" um jede
rem einzelne Startmeldung. Es sah aus, als sei die Station kaputt, dabei
rem war nur die Verrohrung falsch herum.
title Kollektivtraum: Kern
if not exist "%USERPROFILE%\kg-logs" mkdir "%USERPROFILE%\kg-logs"
cd /d "C:\Users\birk\kollektivgedaechtnis"
.venv\Scripts\python.exe -m kg --config config.toml 2>&1 | powershell -NoProfile -Command "$input | Tee-Object -FilePath '%USERPROFILE%\kg-logs\kern.log'"
echo.
echo Kern ist beendet.
pause
