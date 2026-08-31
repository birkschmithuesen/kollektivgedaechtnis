@echo off
rem Der Kern: Graph, Telegram-Fotoeingang, Interviewablauf.
rem
rem Die Ausgabe geht ins Fenster UND in eine Datei. Das Fenster ist vor Ort
rem das schnellere Werkzeug, die Datei die einzige, die man hinterher noch
rem lesen kann - und die einzige, die aus der Ferne erreichbar ist. Windows
rem kennt kein `tee`; PowerShell's Tee-Object kann es.
title Kollektivtraum: Kern
if not exist "%USERPROFILE%\kg-logs" mkdir "%USERPROFILE%\kg-logs"
cd /d "C:\Users\birk\kollektivgedaechtnis"
powershell -NoProfile -Command "& { .venv\Scripts\python.exe -m kg --config config.toml } 2>&1 | Tee-Object -FilePath ('~\kg-logs\kern.log' -replace '~',$env:USERPROFILE)"
echo.
echo Kern ist beendet.
pause
