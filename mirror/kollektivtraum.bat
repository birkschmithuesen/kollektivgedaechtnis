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
rem  0. Stand vom GitHub holen (Birk, 2026-09-01: "bei der Start.bat am
rem     Anfang immer vom github gepulled werden").
rem
rem     Warum ueberhaupt: Am 2026-09-01 stand die Station 28 Commits hinter
rem     `master`. Fertig gebaute Sachen liefen deshalb nicht - der Name der
rem     Person erschien nicht am Zitat, weil die Datenbankspalte dort nie
rem     angelegt worden war. Das sah wie ein Programmfehler aus und war
rem     keiner. Ein Pull beim Start schliesst genau diese Luecke.
rem
rem     Gezogen wird ins REPO (%KG%), nicht in dieses Startverzeichnis:
rem     diese Datei laeuft aus einer Kopie unter kg-start\, das Repo mit
rem     den Diensten liegt woanders.
rem
rem     🔴 Der Pull darf den Ausstellungstag NIE blockieren. Deshalb:
rem     - `--ff-only`: nur vorspulen. Gibt es lokale Commits oder ist der
rem       Baum auseinandergelaufen, bricht der Pull ab statt einen Merge
rem       (womoeglich mit Konflikt) mitten in den Start zu legen.
rem     - Kein `pause` im Fehlerfall: die Station startet mit dem
rem       vorhandenen Stand weiter. Ein alter Stand ist unangenehm, eine
rem       Station die gar nicht hochkommt ist schlimmer.
rem     - Ein Zeitlimit, damit ein totes Netz im Festivalhaus den Start
rem       nicht minutenlang haengen laesst.
rem
rem     Ueberspringen (kein Netz, bewusst alter Stand): `set KG_KEIN_PULL=1`
rem     vor dem Aufruf.
rem ---------------------------------------------------------------------
if "%KG_KEIN_PULL%"=="1" (
  echo   [0/6] Aktualisierung uebersprungen ^(KG_KEIN_PULL=1^)
) else (
  echo   [0/6] Stand von GitHub holen
  call :aktualisiere "%KG%" "Kollektivgedaechtnis"
  if exist "%SPIEGEL%\.git" call :aktualisiere "%SPIEGEL%" "Spiegel"
)
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

rem ---------------------------------------------------------------------
rem  Die Schluessel liegen in der Benutzerumgebung, nicht in dieser Datei.
rem
rem  Sie werden hier AUS DER REGISTRY nachgeladen, nicht einfach aus %VAR%
rem  gelesen. Der Grund (gemessen 2026-08-31, und es hat uns eine Stunde
rem  gekostet): Windows reicht die Benutzerumgebung beim Anmelden EINMAL an
rem  den Explorer weiter. Wird eine Variable spaeter gesetzt, sieht jedes
rem  Programm, das per Doppelklick startet, sie NICHT - erst nach Ab- und
rem  Anmelden. Ein frisch gestarteter Dienst sieht sie dagegen sofort.
rem  Genau daran lag es, dass derselbe Start aus der Ferne lief und per
rem  Doppelklick "API key fehlt" meldete.
rem
rem  Ausgegeben wird nur, OB ein Schluessel da ist - nie sein Wert.
rem ---------------------------------------------------------------------
for /f "usebackq delims=" %%K in (`powershell -NoProfile -Command "foreach($n in 'HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY','BFL_API_KEY','KG_TELEGRAM_TOKEN'){ $v=[Environment]::GetEnvironmentVariable($n,'User'); if(-not $v){ $v=[Environment]::GetEnvironmentVariable($n,'Machine') }; if($v){ 'set '+$n+'='+$v } }"`) do @%%K

set FEHLTSCHLUESSEL=
if "%HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY%"=="" set FEHLTSCHLUESSEL=%FEHLTSCHLUESSEL% Infomaniak
if "%BFL_API_KEY%"=="" set FEHLTSCHLUESSEL=%FEHLTSCHLUESSEL% BFL
if "%KG_TELEGRAM_TOKEN%"=="" set FEHLTSCHLUESSEL=%FEHLTSCHLUESSEL% Telegram

if defined FEHLTSCHLUESSEL (
  echo   FEHLER: diese Schluessel fehlen:%FEHLTSCHLUESSEL%
  echo.
  echo   Setzen ^(einmal, als der Benutzer der die Station startet^):
  echo     setx HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY "..."
  echo     setx BFL_API_KEY "..."
  echo     setx KG_TELEGRAM_TOKEN "..."
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
rem  5. Der Abholer. Holt Fotos, die von Handys OHNE Tailnet-Zugang beim
rem     oeffentlichen Spiegel eingeworfen wurden, und reicht sie an den
rem     Kern weiter. Handys IM Tailnet brauchen ihn nicht.
rem
rem     Wie der Spiegel darueber: faellt er aus, laeuft die Wand weiter,
rem     nur Fotos von aussen bleiben liegen. Deshalb steht er hier hinten.
rem ---------------------------------------------------------------------
if exist "%SPIEGEL%\mirror\abholer-start.bat" (
  if exist "%USERPROFILE%\.kg-mirror-token" (
    echo   [5/6] Foto-Abholer  ^(Handys ohne Tailnet^)
    call :starte "Abholer" "%SPIEGEL%\mirror\abholer-start.bat" abholer
  ) else (
    echo   [5/6] Abholer UEBERSPRUNGEN: .kg-mirror-token fehlt.
  )
) else (
  echo   [5/6] Abholer UEBERSPRUNGEN: abholer-start.bat nicht vorhanden.
)

rem ---------------------------------------------------------------------
rem  6. Die Anzeigen.
rem
rem     Nur auf ausdruecklichen Wunsch (%KG_FENSTER%=1). Vorgabe ist AUS,
rem     und das ist Birks Entscheidung von 2026-08-31: die Fensterautomatik
rem     scheiterte auf dieser Kiste still - kein Fenster ging auf, keine
rem     Meldung kam. Ein Start, der die Adressen sauber HINSCHREIBT, ist
rem     ehrlicher als einer, der Fenster verspricht und keine liefert.
rem     Die Adressen stehen unten und lassen sich mit der Maus markieren.
rem
rem     Wer die Automatik doch will: `set KG_FENSTER=1` vor dem Aufruf.
rem     Dann bekommt jedes Fenster ein eigenes Benutzerprofil, sonst macht
rem     Edge aus dem zweiten Aufruf nur einen Tab im ersten.
rem ---------------------------------------------------------------------
if "%KG_FENSTER%"=="1" (
  echo   [6/6] Fenster oeffnen ^(KG_FENSTER=1^)
  rem Alles auf EINER Zeile. Die Fortsetzung mit ^ zerbricht hier: cmd liest
  rem die Folgezeile als eigenen Befehl und meldet
  rem "Der Befehl --user-data-dir ... konnte nicht gefunden werden".
  start "" "%EDGE%" --kiosk --window-position=%POS_WAND% --user-data-dir="%LOGS%\edge-wand" --no-first-run --noerrdialogs --disable-session-crashed-bubble --disable-infobars --autoplay-policy=no-user-gesture-required "http://127.0.0.1:8800/projection"
  ping -n 3 127.0.0.1 >nul
  start "" "%EDGE%" --kiosk --window-position=%POS_TRAUM% --user-data-dir="%LOGS%\edge-traum" --no-first-run --noerrdialogs --disable-session-crashed-bubble --disable-infobars --autoplay-policy=no-user-gesture-required "http://127.0.0.1:8810/dream"
  start "" "%EDGE%" --new-window --window-position=0,0 --window-size=1400,950 --user-data-dir="%LOGS%\edge-pult" --no-first-run "http://127.0.0.1:8800/operator" "http://127.0.0.1:8810/operator"
) else (
  echo   [6/6] Fenster: keine ^(Adressen stehen unten^)
)

echo.
echo   ==================================================================
echo.
echo    ZUM OEFFNEN - anklickbar im Ordner "Kollektivtraum Ansichten"
echo    auf dem Schreibtisch. Oder hier markieren und kopieren:
echo.
echo      Wand ^(Graph^)        http://127.0.0.1:8800/projection?theme=f^&touch=1
echo      Schirm B ^(Traum^)    http://127.0.0.1:8810/dream
echo.
echo      Pult Graph           http://127.0.0.1:8800/operator
echo      Pult Traum           http://127.0.0.1:8810/operator
echo.
echo      Am Telefon           %OEFFENTLICH%
echo.
echo    Die Wand ohne Beruehrung ^(zweiter Schirm, nur Anzeige^):
echo      http://127.0.0.1:8800/projection?theme=f
echo.
echo   ==================================================================
echo.
echo   Markieren geht mit der Maus; Rechtsklick kopiert. Ist der
echo   Schnellbearbeitungsmodus aus, hilft: Rechtsklick auf die
echo   Titelleiste, Bearbeiten, Markieren.
echo.
echo   Geht etwas schief: das Fenster des betroffenen Teils in der
echo   Taskleiste oeffnen - dort steht der Grund im Klartext. Dasselbe
echo   steht in %%USERPROFILE%%\kg-logs\ als Datei.
echo.
echo   Dieses Fenster kann zu. Zum Beenden ALLER Teile:
echo   "Kollektivtraum STOP" auf dem Schreibtisch.
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
rem  Die Ausgabe geht ins Fenster UND in eine Datei unter
rem  %USERPROFILE%\kg-logs (das erledigt die jeweilige dienst-*.bat per
rem  Tee-Object). Das Fenster ist vor Ort das schnellere Werkzeug, die
rem  Datei die einzige, die man aus der Ferne oder hinterher lesen kann.
rem =====================================================================
rem =====================================================================
rem  Holt den Stand eines Repos von GitHub - vorspulen oder gar nicht.
rem
rem  Der Ausstellungstag hat Vorrang vor Aktualitaet. Diese Routine darf
rem  deshalb unter keinen Umstaenden haengen bleiben oder auf eine Eingabe
rem  warten; sie meldet, was war, und gibt IMMER 0 zurueck.
rem
rem  `--ff-only` ist die eigentliche Sicherung: gibt es auf der Station
rem  lokale Commits, wird NICHT gemerged. Ein Merge-Konflikt mitten im
rem  Start waere genau der Ausfall, den ein Pull verhindern soll. Statt
rem  dessen bleibt der vorhandene Stand stehen und es kommt ein Hinweis.
rem
rem  Uncommittete Aenderungen an versionierten Dateien blockieren einen
rem  Pull ebenfalls - deshalb wird vorher geprueft und im Zweifel gar
rem  nicht gezogen. config.toml, config2.toml und die Interviewdaten sind
rem  ohnehin ignoriert (.gitignore), die stoeren also nie.
rem
rem  GIT_TERMINAL_PROMPT=0: ohne das fragt git bei fehlendem Zugang nach
rem  Benutzername und Passwort - und der Start stuende still, bis jemand
rem  Enter drueckt. Genau das darf am Ausstellungsmorgen nicht passieren.
rem =====================================================================
:aktualisiere
setlocal
set "ZIEL=%~1"
set "WIE=%~2"
set "GIT_TERMINAL_PROMPT=0"

if not exist "%ZIEL%\.git" (
  echo         %WIE%: kein Repo, uebersprungen.
  endlocal & exit /b 0
)

pushd "%ZIEL%" 2>nul
if errorlevel 1 (
  echo         %WIE%: Ordner nicht erreichbar, uebersprungen.
  endlocal & exit /b 0
)

rem Erst schauen, ob etwas Eigenes im Weg liegt. Ein Pull, der an einer
rem geaenderten Datei scheitert, soll gar nicht erst versucht werden.
rem
rem 🔴 `--untracked-files=no` ist hier entscheidend, nicht Kosmetik --
rem gemessen an der echten Station am 2026-09-01: Dort lagen 11
rem unversionierte Dateien im Repo (Sicherungskopien wie
rem `config.toml.bak-vor-eu-llm`, Messsonden, Testdateien aus einer
rem Sitzung). Mit dem nackten `--porcelain` haette die Schutzpruefung
rem deshalb JEDES MAL angeschlagen und nie gezogen -- der ganze Schritt
rem waere eine wirkungslose Zeile im Startprotokoll gewesen.
rem
rem Unversionierte Dateien koennen einen `--ff-only`-Pull auch nicht in
rem einen Konflikt fuehren: Kaeme eine Datei neu dazu, die dort schon
rem liegt, meldet git das sauber und bricht ab. Wovor die Pruefung wirklich
rem schuetzt, sind GEAENDERTE versionierte Dateien.
set "SCHMUTZIG="
for /f "delims=" %%S in ('git status --porcelain --untracked-files^=no 2^>nul') do set "SCHMUTZIG=1"
if defined SCHMUTZIG (
  echo         %WIE%: lokale Aenderungen - NICHT gezogen, alter Stand bleibt.
  popd
  endlocal & exit /b 0
)

rem 🔴 Gezogen wird von GITHUB, ausdruecklich benannt statt ueber den
rem eingestellten `origin` -- gemessen an der Station am 2026-09-01:
rem Dort zeigte `origin` auf eine lokale Datei `C:\Users\birk\kg.bundle`
rem vom 29.08. Ein `git pull` ohne Ziel meldete brav "Already up to
rem date", waehrend die Station in Wahrheit 28 Commits zurueckhing. Der
rem Schritt haette also funktioniert AUSGESEHEN und nichts getan -- die
rem schlechteste aller Varianten, weil niemand nachsieht.
git remote get-url github >nul 2>&1
if errorlevel 1 git remote add github https://github.com/birkschmithuesen/kollektivgedaechtnis.git >nul 2>&1

rem Zeitlimit ueber PowerShell: ein totes Netz im Festivalhaus darf den
rem Start nicht minutenlang aufhalten. 45 s sind ein Vielfaches dessen,
rem was ein normaler Pull braucht.
powershell -NoProfile -Command "$p = Start-Process git -ArgumentList 'pull','--ff-only','--quiet','github','master' -NoNewWindow -PassThru; if (-not $p.WaitForExit(45000)) { $p.Kill(); exit 2 }; exit $p.ExitCode" >nul 2>&1

if errorlevel 2 (
  echo         %WIE%: Zeitlimit ^(Netz?^) - alter Stand bleibt, weiter.
) else if errorlevel 1 (
  echo         %WIE%: Pull nicht moeglich - alter Stand bleibt, weiter.
) else (
  echo         %WIE%: aktuell.
  call :startdatei_nachziehen
)

popd
endlocal & exit /b 0

rem ---------------------------------------------------------------------
rem  Die laufende Startdatei sich selbst nachziehen.
rem
rem  Die Station startet aus einer KOPIE (`kg-start\`), nicht aus dem Repo:
rem  Ein Doppelklick auf dem Schreibtisch soll nicht in einen Git-Ordner
rem  fuehren. Der Pull oben holt aber nur das REPO -- die Kopie daneben
rem  bleibt stehen, bis jemand sie von Hand ersetzt.
rem
rem  🔴 Genau das ist am 2026-09-01 aufgefallen: Die laufende Kopie war
rem  eine alte Fassung OHNE den Pull-Schritt. Der Schritt existierte im
rem  Repo und lief trotzdem nie -- ein Feature, das da ist und nicht
rem  wirkt, ist schlechter als eines, das fehlt: Niemand sucht danach.
rem
rem  Kopiert wird NACH dem Lauf, nicht davor: Eine .bat, die sich waehrend
rem  der Ausfuehrung selbst ueberschreibt, laeuft in cmd.exe ab der
rem  naechsten Zeile im NEUEN Text weiter -- cmd liest die Datei
rem  zeilenweise nach, nicht einmal am Anfang. Deshalb wird die neue
rem  Fassung nur DANEBEN gelegt und beim naechsten Start wirksam.
rem
rem  Fehler sind hier folgenlos: Klappt das Kopieren nicht, laeuft die
rem  Station mit der Datei weiter, die sie ohnehin schon benutzt.
rem ---------------------------------------------------------------------
:startdatei_nachziehen
setlocal
set "MEINE=%~f0"
set "IM_REPO=%KG%\mirror\kollektivtraum.bat"

if not exist "%IM_REPO%" endlocal & exit /b 0

rem Laeuft die Station ohnehin aus dem Repo, gibt es nichts nachzuziehen.
if /i "%MEINE%"=="%IM_REPO%" endlocal & exit /b 0

fc "%MEINE%" "%IM_REPO%" >nul 2>&1
if not errorlevel 1 endlocal & exit /b 0

copy /y "%IM_REPO%" "%MEINE%" >nul 2>&1
if errorlevel 1 (
  echo         Startdatei: neuere Fassung im Repo, Kopieren fehlgeschlagen.
) else (
  echo         Startdatei erneuert - gilt ab dem naechsten Start.
  copy /y "%KG%\mirror\kollektivtraum-stop.bat" "%~dp0kollektivtraum-stop.bat" >nul 2>&1
)
endlocal & exit /b 0

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
