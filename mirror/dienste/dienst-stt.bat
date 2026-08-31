@echo off
rem Spracherkennung. Infomaniak Whisper (Schweiz), nicht ElevenLabs (US) -
rem die Station laeuft in Europa, und das steht so auf der oeffentlichen Seite.
title Kollektivtraum: Spracherkennung
cd /d "C:\Users\birk\fundusbot"
venv\Scripts\python.exe -m fundusapps.stt_server --language de infomaniak-whisper --channels regie --api-key-env HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY
echo.
echo Die Spracherkennung ist beendet.
pause
