@echo off
rem Startet den Abholer auf dem Ausstellungsrechner.
rem
rem Das Gegenstueck zum Uploader daneben, nur in die andere Richtung: der
rem Uploader SCHIEBT den Stand nach draussen, der Abholer HOLT Fotos herein.
rem
rem Wozu: Fotos von Handys OHNE Tailnet-Zugang (eine Kollegin, ein
rem geliehenes Geraet). Die App wirft beim oeffentlichen Spiegel ein, dieser
rem Dienst holt sie dort ab und reicht sie an den Kern weiter. Handys IM
rem Tailnet brauchen ihn nicht - die schicken direkt an Port 8800.
rem
rem Faellt er aus, merkt es im Haus niemand: die Wand laeuft weiter, nur
rem Fotos von aussen bleiben liegen. Deshalb steht er hinten in der
rem Startreihenfolge, direkt beim Spiegel.
rem
rem Das Token steht NICHT hier, sondern in %USERPROFILE%\.kg-mirror-token -
rem dieselbe Datei wie beim Uploader, und dasselbe starke Token. Abholen und
rem Quittieren darf nur die Station; das schwache Foto-Token aus der App
rem kann beides nicht.

setlocal

rem Feste Pfade, kein %USERPROFILE%: Die Station wird mal als `birk`, mal
rem als `SF-Tracking` bedient, und der Quelltext liegt nur einmal - unter
rem `birk`. Das Token dagegen gehoert dem angemeldeten Benutzer.
set "SPIEGEL=C:\Users\birk\kg-spiegel"
set "KGVENV=C:\Users\birk\kollektivgedaechtnis\.venv\Scripts\python.exe"
set "TOKENDATEI=%USERPROFILE%\.kg-mirror-token"

if not exist "%TOKENDATEI%" (
  echo FEHLER: %TOKENDATEI% fehlt.
  echo Ohne Token gibt der Spiegel nichts heraus. Auf dem vServer ausfuehren:
  echo   scripts/token-verteilen.sh windows ^<name-dieses-rechners^>
  pause
  exit /b 1
)

rem Token aus der Datei in die Umgebung dieses einen Prozesses holen.
rem `set /p` liest die Zeile, ohne sie auszugeben.
set /p KG_MIRROR_TOKEN=<"%TOKENDATEI%"

set "KG_MIRROR_URL=https://kollektivgedaechtnis.flashclash.de"
set "KG_STATION_URL=http://127.0.0.1:8800"

rem Wie oft nachgesehen wird. 2 Sekunden, weil der Takt hier bestimmt, wie
rem lange zwischen dem Ausloeser am Handy und dem Portrait an der Wand
rem vergeht (beim Uploader daneben geht es nur um die Frische einer
rem Anzeige, deshalb steht dort 3). Gemessen am 2026-09-01: eine Abfrage
rem kostet 88 ms, das sind rund 4 Prozent der Wartezeit - der Takt ist
rem also nicht die Last. Kleiner als 0.5 wird abgefangen.
set "KG_ABHOL_INTERVALL=2"

cd /d "%SPIEGEL%"
echo Abholer: %KG_MIRROR_URL%  --^>  %KG_STATION_URL%
echo Taktung: alle %KG_ABHOL_INTERVALL% Sekunden
echo.
echo Fuer Handys OHNE Tailnet. Wer im Tailnet ist, schickt direkt an 8800
echo und braucht diesen Dienst nicht.
echo.
echo Beenden mit Strg+C. Das Fenster darf den ganzen Tag offen bleiben:
echo der Abholer steht Netzaussetzer durch und faengt sich von selbst.
echo.

"%KGVENV%" -m mirror.abholer

echo.
echo Abholer ist beendet.
pause
