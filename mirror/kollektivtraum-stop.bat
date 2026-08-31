@echo off
rem =====================================================================
rem  Kollektivtraum ? alles beenden.
rem
rem  Beendet die vier Dienste und die Anzeigefenster, die
rem  kollektivtraum.bat gestartet hat. Nichts anderes: der Browser, in dem
rem  jemand nebenher etwas nachschlaegt, bleibt offen, weil hier nur die
rem  Fenster mit den eigenen Benutzerprofilen getroffen werden.
rem =====================================================================

setlocal
title Kollektivtraum ? Stopp

set "LOGS=C:\Users\birk\kg-logs"

echo.
echo   Kollektivtraum beenden
echo   ======================
echo.

rem Die Dienste: erkannt an ihrer Kommandozeile, nicht am Fenstertitel.
rem Ein Titel laesst sich verlieren (Minimieren, Neustart eines Teils),
rem die Kommandozeile nicht.
powershell -NoProfile -Command ^
  "$muster = @('fundusapps.stt_server','-m kg --config','-m kg2 --config','mirror.uploader');" ^
  "$treffer = Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $z=$_.CommandLine; $muster | Where-Object { $z -like ('*'+$_+'*') } };" ^
  "if (-not $treffer) { Write-Output '  Es lief nichts.' } else { foreach ($p in $treffer) { $was = switch -Wildcard ($p.CommandLine) { '*stt_server*' {'Spracherkennung'} '*-m kg --config*' {'Kern'} '*-m kg2*' {'Traum'} '*uploader*' {'Spiegel'} default {'unbekannt'} }; Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue; Write-Output ('  beendet: ' + $was + ' (PID ' + $p.ProcessId + ')') } }"

rem Die Anzeigefenster: nur die mit UNSEREN Benutzerprofilen. Deshalb wurde
rem beim Start ueberhaupt --user-data-dir vergeben ? es ist die einzige
rem Spur, an der sich die Stationsfenster von Birks eigenem Browser
rem unterscheiden lassen.
powershell -NoProfile -Command ^
  "$eigene = Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | Where-Object { $_.CommandLine -like '*kg-logs\edge-*' };" ^
  "if ($eigene) { $eigene | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Write-Output ('  beendet: ' + $eigene.Count + ' Anzeigefenster') } else { Write-Output '  Keine Anzeigefenster der Station offen.' }"

echo.
echo   Fertig.
echo.
pause
