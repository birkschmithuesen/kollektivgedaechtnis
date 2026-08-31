@echo off
rem Startet den Uploader auf dem Ausstellungsrechner.
rem
rem Das Token steht NICHT hier, sondern in %USERPROFILE%\.kg-mirror-token
rem (nur fuer diesen Benutzer lesbar). Damit taucht es weder in dieser Datei
rem noch in einer Verknuepfung, einer geplanten Aufgabe oder im Verlauf der
rem Eingabeaufforderung auf.
rem
rem Doppelklick genuegt. Das Fenster bleibt offen und zeigt, was hochgeht.

setlocal

rem Feste Pfade, kein %USERPROFILE%: Die Station wird mal als `birk`, mal
rem als `SF-Tracking` bedient (beide melden sich an derselben Kiste an), und
rem der Quelltext liegt nur einmal - unter `birk`. Das Token dagegen gehoert
rem dem jeweils angemeldeten Benutzer, weil nur er es lesen darf.
set "SPIEGEL=C:\Users\birk\kg-spiegel"
set "KGVENV=C:\Users\birk\kollektivgedaechtnis\.venv\Scripts\python.exe"
set "TOKENDATEI=%USERPROFILE%\.kg-mirror-token"

if not exist "%TOKENDATEI%" (
  echo FEHLER: %TOKENDATEI% fehlt.
  echo Ohne Token nimmt der Server nichts an. Auf dem vServer ausfuehren:
  echo   scripts/token-verteilen.sh windows ^<name-dieses-rechners^>
  pause
  exit /b 1
)

rem Token aus der Datei in die Umgebung dieses einen Prozesses holen.
rem `set /p` liest die Zeile, ohne sie auszugeben.
set /p KG_MIRROR_TOKEN=<"%TOKENDATEI%"

set "KG_MIRROR_URL=https://kollektivgedaechtnis.flashclash.de"
set "KG_TOOL1_URL=http://127.0.0.1:8800"
set "KG_TOOL2_URL=http://127.0.0.1:8810"
set "KG_MIRROR_INTERVAL=3"

cd /d "%SPIEGEL%"
echo Spiegel: %KG_MIRROR_URL%
echo Quelle:  %KG_TOOL1_URL%  und  %KG_TOOL2_URL%
echo.
echo Beenden mit Strg+C. Das Fenster darf den ganzen Tag offen bleiben:
echo der Uploader steht Netzaussetzer durch und faengt sich von selbst.
echo.

"%KGVENV%" -m mirror.uploader

echo.
echo Der Uploader ist beendet.
pause
