@echo off
rem Spracherkennung. Infomaniak Whisper (Schweiz), nicht ElevenLabs (US) -
rem die Station laeuft in Europa, und das steht so auf der oeffentlichen Seite.
rem
rem Die Ausgabe geht ins Fenster UND in eine Datei. Das Fenster ist vor Ort
rem das schnellere Werkzeug, die Datei die einzige, die man hinterher noch
rem lesen kann - und die einzige, die aus der Ferne erreichbar ist. Windows
rem kennt kein `tee`; PowerShell's Tee-Object kann es.
title Kollektivtraum: Spracherkennung
if not exist "%USERPROFILE%\kg-logs" mkdir "%USERPROFILE%\kg-logs"
cd /d "C:\Users\birk\fundusbot"
powershell -NoProfile -Command "& { venv\Scripts\python.exe -m fundusapps.stt_server --language de infomaniak-whisper --channels regie --api-key-env HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY } 2>&1 | Tee-Object -FilePath ('~\kg-logs\stt.log' -replace '~',$env:USERPROFILE)"
echo.
echo Spracherkennung ist beendet.
pause
