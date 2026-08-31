@echo off
rem =====================================================================
rem  Kollektivtraum ? alles starten, was zur Station gehoert.
rem
rem  Ein Doppelklick, und die Station steht: Spracherkennung, der Graph,
rem  der Traum, der oeffentliche Spiegel, dazu die Fenster fuer Wand,
rem  Schirm B und die beiden Bedienpulte.
rem
rem  Jeder Teil laeuft in seinem eigenen Fenster. Das ist Absicht: faellt
rem  einer aus, sieht man WELCHER, und man startet nur ihn neu ? statt
rem  alles wegzuwerfen. Die Fenster tragen darum Namen in der Titelzeile.
rem
rem  Beenden: dieses Fenster schliessen beendet NICHT die anderen. Dafuer
rem  gibt es am Ende die Abfrage, oder kollektivtraum-stop.bat.
rem =====================================================================

setlocal
title Kollektivtraum ? Start

set "KG=C:\Users\birk\kollektivgedaechtnis"
set "FB=C:\Users\birk\fundusbot"
set "SPIEGEL=C:\Users\birk\kg-spiegel"
rem Nicht mehr fuer Logdateien (die Dienste zeigen ihre Ausgabe im eigenen
rem Fenster), sondern fuer die Browser-Profile der Anzeigefenster.
rem
rem Unter %USERPROFILE%, nicht fest unter birk: die Station wird mal als
rem `birk`, mal als `SF-Tracking` bedient. Zwei Benutzer, die sich denselben
rem Profilordner teilen, sperren einander den Browser aus ("profile is in
rem use") - und das faellt erst auf, wenn die Wand schwarz bleibt.
set "LOGS=%USERPROFILE%\kg-logs"
set "DIENSTE=%~dp0dienste"
set "OEFFENTLICH=https://kollektivgedaechtnis.flashclash.de"
set "EDGE=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

rem Wo die zweite Anzeige liegt. Beamer und Schirm B haengen rechts neben
rem dem Laptoppanel; passt das vor Ort nicht, hier aendern.
set "POS_WAND=1920,0"
set "POS_TRAUM=1920,0"

if not exist "%LOGS%" mkdir "%LOGS%"

echo.
echo   Kollektivtraum
echo   ==============
echo.

rem ---------------------------------------------------------------------
rem  Erst pruefen, dann starten. Ein fehlender Schluessel darf sich nicht
rem  als leerer Graph drei Interviews spaeter zeigen.
rem ---------------------------------------------------------------------

set FEHLT=

if not exist "%KG%\config.toml"  set FEHLT=%FEHLT% config.toml
if not exist "%KG%\config2.toml" set FEHLT=%FEHLT% config2.toml
if not exist "%KG%\.venv\Scripts\python.exe" set FEHLT=%FEHLT% kg-venv
if not exist "%FB%\venv\Scripts\python.exe"  set FEHLT=%FEHLT% stt-venv

if defined FEHLT (
  echo   FEHLER: es fehlt:%FEHLT%
  echo.
  pause
  exit /b 1
)

rem Die Schluessel liegen in der Benutzerumgebung, nicht in dieser Datei.
rem Geprueft wird nur, DASS sie da sind ? nie ihr Wert.
if "%HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY%"=="" (
  echo   FEHLER: HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY ist nicht gesetzt.
  echo   Ohne ihn laufen weder Auswertung noch Spracherkennung.
  echo.
  pause
  exit /b 1
)
if "%BFL_API_KEY%"=="" (
  echo   FEHLER: BFL_API_KEY ist nicht gesetzt ? keine Traumbilder.
  echo.
  pause
  exit /b 1
)
if "%KG_TELEGRAM_TOKEN%"=="" (
  echo   FEHLER: KG_TELEGRAM_TOKEN ist nicht gesetzt ? kein Fotoeingang.
  echo.
  pause
  exit /b 1
)

echo   Schluessel:      vollstaendig
echo   Fenster je Teil: sichtbar in der Taskleiste
echo.

rem ---------------------------------------------------------------------
rem  1. Spracherkennung. Muss vor dem Kern stehen: der Kern verbindet sich
rem     beim Start zu ihr und meldet sonst gleich einen Fehlversuch.
rem
rem     infomaniak-whisper, nicht elevenlabs-scribe: die Station laeuft in
rem     Europa, und das steht so auch auf der oeffentlichen Seite.
rem ---------------------------------------------------------------------
echo   [1/6] Spracherkennung (Infomaniak Whisper, Schweiz)
call :starte "Spracherkennung" "%DIENSTE%\dienst-stt.bat" stt

call :warte_auf http://127.0.0.1:5051/status "Spracherkennung" 30

rem ---------------------------------------------------------------------
rem  2. Der Kern: Graph, Telegram, Interviewablauf.
rem ---------------------------------------------------------------------
echo   [2/6] Kern (Graph, Telegram)
call :starte "Kern" "%DIENSTE%\dienst-kern.bat" kern

call :warte_auf http://127.0.0.1:8800/api/state "Kern" 60

rem ---------------------------------------------------------------------
rem  3. Der Traum. Haengt NICHT vom Kern ab (Spec 9): er kommt auch hoch,
rem     wenn der Kern fehlt, und traeumt weiter, sobald dieser antwortet.
rem     Deshalb wird hier auch nicht auf den Kern gewartet.
rem ---------------------------------------------------------------------
echo   [3/6] Traum (Kimi K2.6 Schweiz, FLUX Deutschland)
call :starte "Traum" "%DIENSTE%\dienst-traum.bat" traum

call :warte_auf http://127.0.0.1:8810/api/state "Traum" 60

rem ---------------------------------------------------------------------
rem  4. Der oeffentliche Spiegel. Schiebt Graph, Traum und Bilder auf den
rem     Server, damit Besucher es am eigenen Telefon sehen. Faellt er aus,
rem     merkt im Haus niemand etwas ? deshalb steht er hier hinten.
rem ---------------------------------------------------------------------
if exist "%SPIEGEL%\mirror\spiegel-start.bat" (
  if exist "%USERPROFILE%\.kg-mirror-token" (
    echo   [4/6] Oeffentlicher Spiegel  ^(%OEFFENTLICH%^)
    call :starte "Spiegel" "%SPIEGEL%\mirror\spiegel-start.bat" spiegel
  ) else (
    echo   [4/6] Spiegel UEBERSPRUNGEN: .kg-mirror-token fehlt.
  )
) else (
  echo   [4/6] Spiegel UEBERSPRUNGEN: %SPIEGEL% nicht vorhanden.
)

rem ---------------------------------------------------------------------
rem  5. Die Anzeigen. Kiosk auf der zweiten Anzeige, jeweils ein eigenes
rem     Benutzerprofil je Fenster: ohne --user-data-dir macht Edge aus dem
rem     zweiten Aufruf nur einen Tab im ersten Fenster, und dann steht
rem     eine der beiden Projektionen nicht.
rem ---------------------------------------------------------------------
echo   [5/6] Wand und Schirm B
rem Alles auf EINER Zeile. Die Fortsetzung mit `^` zerbricht hier: cmd
rem liest die Folgezeile als eigenen Befehl und meldet
rem ?Der Befehl --user-data-dir ... konnte nicht gefunden werden"
rem (gemessen 2026-08-31). Lang und unschoen, aber richtig.
start "" "%EDGE%" --kiosk --window-position=%POS_WAND% --user-data-dir="%LOGS%\edge-wand" --no-first-run --noerrdialogs --disable-session-crashed-bubble --disable-infobars --autoplay-policy=no-user-gesture-required "http://127.0.0.1:8800/projection"

ping -n 3 127.0.0.1 >nul

start "" "%EDGE%" --kiosk --window-position=%POS_TRAUM% --user-data-dir="%LOGS%\edge-traum" --no-first-run --noerrdialogs --disable-session-crashed-bubble --disable-infobars --autoplay-policy=no-user-gesture-required "http://127.0.0.1:8810/dream"

rem ---------------------------------------------------------------------
rem  6. Die Bedienpulte auf dem Laptop. Zwei Tabs in EINEM Fenster, damit
rem     man am Pult nicht zwischen Fenstern sucht.
rem ---------------------------------------------------------------------
echo   [6/6] Bedienpulte
start "" "%EDGE%" --new-window --window-position=0,0 --window-size=1400,950 --user-data-dir="%LOGS%\edge-pult" --no-first-run "http://127.0.0.1:8800/operator" "http://127.0.0.1:8810/operator"

echo.
echo   ------------------------------------------------------------------
echo   Es laeuft. Was wo liegt:
echo.
echo     Wand ^(Graph^)       http://127.0.0.1:8800/projection
echo     Schirm B ^(Traum^)   http://127.0.0.1:8810/dream
echo     Pult Graph          http://127.0.0.1:8800/operator
echo     Pult Traum          http://127.0.0.1:8810/operator
echo     Am Telefon          %OEFFENTLICH%
echo.
echo   Geht etwas schief: das Fenster des betroffenen Teils in der
 echo   Taskleiste oeffnen ? dort steht der Grund im Klartext.
echo   ------------------------------------------------------------------
echo.
echo   Dieses Fenster kann zu. Zum Beenden ALLER Teile:
echo   kollektivtraum-stop.bat
echo.
pause
exit /b 0

rem =====================================================================
rem  Startet einen Dienst in einem eigenen, benannten Fenster.
rem
rem  Der Umweg ueber eine eigene .bat je Dienst ist Absicht: `start "..."
rem  cmd /c "cd /d X && Y > Z"` zerbricht am Quoting, sobald einer der
rem  Pfade Leerzeichen enthaelt ? gemessen 2026-08-31, das Log enthielt
rem  dann nur ?Das System kann den angegebenen Pfad nicht finden.". Eine
rem  eigene Datei hat dieses Problem nicht und ist ausserdem einzeln
rem  startbar, wenn vor Ort genau ein Teil neu hochmuss.
rem
rem  Kein `> log`: die Ausgabe bleibt im Fenster sichtbar, und das Fenster
rem  ist bei einer Live-Station das ehrlichere Werkzeug als eine Datei,
rem  die niemand aufmacht. `tee` gibt es hier nicht.
rem =====================================================================
:starte
start "Kollektivtraum: %~1" /min cmd /k "%~2"
exit /b 0

rem =====================================================================
rem  Wartet, bis ein Dienst wirklich antwortet ? statt blind zu schlafen.
rem  Ein fester Schlafbefehl ist entweder zu kurz (Fenster oeffnet auf
rem  einem Verbindungsfehler) oder verschenkt Zeit am Ausstellungsmorgen.
rem =====================================================================
:warte_auf
setlocal
set "URL=%~1"
set "NAME=%~2"
set /a MAX=%~3
set /a N=0
:warte_schleife
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri '%URL%' | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
  echo         %NAME% antwortet.
  endlocal & exit /b 0
)
set /a N+=1
if %N% GEQ %MAX% (
  echo         %NAME% antwortet nach %MAX%s NICHT ? siehe Log. Weiter.
  endlocal & exit /b 1
)
rem `ping` statt `timeout`: `timeout` bricht ab, sobald die Eingabe
rem umgeleitet ist ("Die Eingabeumleitung wird nicht unterstuetzt") -
rem etwa beim Start ueber eine Fernwartung. `ping` wartet immer.
ping -n 2 127.0.0.1 >nul
goto warte_schleife
