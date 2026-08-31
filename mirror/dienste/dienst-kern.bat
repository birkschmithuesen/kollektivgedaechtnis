@echo off
rem Der Kern: Graph, Telegram-Fotoeingang, Interviewablauf.
title Kollektivtraum: Kern
cd /d "C:\Users\birk\kollektivgedaechtnis"
.venv\Scripts\python.exe -m kg --config config.toml
echo.
echo Der Kern ist beendet.
pause
