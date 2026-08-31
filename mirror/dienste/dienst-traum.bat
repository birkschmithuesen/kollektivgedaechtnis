@echo off
rem Der Traum. Haengt bewusst NICHT vom Kern ab (Spec 9): kommt auch hoch,
rem wenn der Kern fehlt, und traeumt weiter, sobald dieser antwortet.
title Kollektivtraum: Traum
cd /d "C:\Users\birk\kollektivgedaechtnis"
.venv\Scripts\python.exe -m kg2 --config config2.toml
echo.
echo Der Traum ist beendet.
pause
