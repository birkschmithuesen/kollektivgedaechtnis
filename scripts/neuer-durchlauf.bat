@echo off
rem =====================================================================
rem  Kollektivgedaechtnis - neuen Durchlauf beginnen.
rem
rem  ARCHIVIERT den bisherigen Bestand, es wird NICHTS geloescht.
rem  Ersetzt die beiden `rm`-Zeilen, die bis 2026-09-01 im Runbook
rem  standen (docs/operations.md, "Neuer Ausstellungstag").
rem
rem  Birks stehende Regel: nie endgueltig loeschen, immer archivieren -
rem  und ueber Loeschungen entscheidet er selbst. Dieses Skript verschiebt
rem  nur; was weg soll, loescht spaeter jemand von Hand aus archiv\.
rem
rem  Verschieben statt kopieren, weil `move` auf demselben Datentraeger
rem  atomar ist und auch bei tausenden Bildern keine Zeit kostet.
rem
rem  VORHER: kollektivtraum-stop.bat! SQLite haelt offene Handles, ein
rem  Verschieben unter laufendem Prozess ergibt eine halbe Datenbank.
rem =====================================================================

setlocal EnableDelayedExpansion
title Kollektivgedaechtnis ? neuer Durchlauf

rem Ins Projektverzeichnis wechseln: die Verknuepfung auf dem Desktop
rem startet sonst im Benutzerordner und faende data\ gar nicht.
cd /d "%~dp0.."

for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmm"') do set "STEMPEL=%%t"
set "ARCHIV=archiv\%STEMPEL%"

echo.
echo   Neuen Durchlauf beginnen
echo   ========================
echo.

rem --- 1/4  Laeuft noch etwas? ---------------------------------------
rem Ueber die Prozessliste, wie kollektivtraum-stop.bat es tut - erkannt
rem an der Kommandozeile, nicht am Fenstertitel.
powershell -NoProfile -Command ^
  "$muster = @('fundusapps.stt_server','-m kg --config','-m kg2 --config','mirror.uploader');" ^
  "$treffer = Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $z=$_.CommandLine; $muster | Where-Object { $z -like ('*'+$_+'*') } };" ^
  "if ($treffer) { Write-Output '  FEHLER: Es laeuft noch etwas.'; exit 1 } else { Write-Output '  Es laeuft nichts - gut.'; exit 0 }"
if errorlevel 1 (
  echo.
  echo   Bitte zuerst STOP druecken ^(kollektivtraum-stop.bat^).
  echo   Ein Verschieben jetzt ergaebe eine halbe Datenbank.
  echo.
  pause
  exit /b 1
)

rem --- 2/4  Rueckfrage -----------------------------------------------
rem Ein versehentlicher Doppelklick mitten am Ausstellungstag waere teuer.
set "GEFUNDEN="
if exist "data" set "GEFUNDEN=1"
if exist "dream-data" set "GEFUNDEN=1"
if not defined GEFUNDEN (
  echo   Nichts zu archivieren - weder data\ noch dream-data\ vorhanden.
  echo.
  pause
  exit /b 0
)

echo   Diese Bestaende wandern nach %ARCHIV%\ :
if exist "data" echo     - data\
if exist "dream-data" echo     - dream-data\
echo.
set /p ANTWORT="  Durchlauf abschliessen und archivieren? [ja/NEIN] "
if /i not "%ANTWORT%"=="ja" (
  echo   Abgebrochen - es wurde nichts verschoben.
  echo.
  pause
  exit /b 0
)

rem --- 3/4  Verschieben ----------------------------------------------
mkdir "%ARCHIV%" 2>nul
if exist "data" (
  move "data" "%ARCHIV%\data" >nul
  echo     data\ -^> %ARCHIV%\data\
)
if exist "dream-data" (
  move "dream-data" "%ARCHIV%\dream-data" >nul
  echo     dream-data\ -^> %ARCHIV%\dream-data\
)

rem Notiz sofort schreiben: ein Archivordner ohne Notiz ist genau das
rem Problem, das diese Zeilen verhindern.
echo.
set /p NOTIZ="  Wofuer war dieser Durchlauf? (eine Zeile) "
> "%ARCHIV%\NOTIZ.txt" echo Durchlauf archiviert am %DATE% %TIME%
>>"%ARCHIV%\NOTIZ.txt" echo.
if defined NOTIZ (
  >>"%ARCHIV%\NOTIZ.txt" echo %NOTIZ%
) else (
  >>"%ARCHIV%\NOTIZ.txt" echo ^(keine Notiz angegeben^)
)
echo     Notiz: %ARCHIV%\NOTIZ.txt

rem --- 4/4  Einbettungs-Cache zurueckholen ----------------------------
rem Ausnahmefall: der Cache spart Geld und macht Wiederholungen
rem offlinefaehig (docs/operations.md: "diese Datei nicht loeschen").
if exist "%ARCHIV%\data\embeddings.sqlite3" (
  mkdir "data" 2>nul
  copy "%ARCHIV%\data\embeddings.sqlite3" "data\embeddings.sqlite3" >nul
  echo     Einbettungs-Cache zurueckkopiert
) else (
  echo     Kein Cache im Archiv - der naechste Lauf baut ihn neu auf
)

echo.
echo   Fertig. Der naechste Start legt data\ und dream-data\ leer neu an.
echo   Geloescht wurde nichts: alles liegt in %ARCHIV%\
echo.
pause
