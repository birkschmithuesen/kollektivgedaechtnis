@echo off
rem Der Traum. Haengt bewusst NICHT vom Kern ab (Spec 9): kommt auch hoch,
rem wenn der Kern fehlt, und traeumt weiter, sobald dieser antwortet.
rem
rem Die Ausgabe geht ins Fenster UND in eine Datei. Das Fenster ist vor Ort
rem das schnellere Werkzeug, die Datei die einzige, die man hinterher noch
rem lesen kann - und die einzige, die aus der Ferne erreichbar ist. Windows
rem kennt kein `tee`; PowerShell's Tee-Object kann es.
title Kollektivtraum: Traum
if not exist "%USERPROFILE%\kg-logs" mkdir "%USERPROFILE%\kg-logs"
cd /d "C:\Users\birk\kollektivgedaechtnis"
powershell -NoProfile -Command "& { .venv\Scripts\python.exe -m kg2 --config config2.toml } 2>&1 | Tee-Object -FilePath ('~\kg-logs\traum.log' -replace '~',$env:USERPROFILE)"
echo.
echo Traum ist beendet.
pause
