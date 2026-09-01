# Beendet die Dienste der Station - dieselben Muster wie kollektivtraum-stop.bat,
# aber ohne `pause`, damit es ueber SSH nicht haengen bleibt.
#
# Als Datei abgelegt statt inline durchgereicht: verschachtelte
# Anfuehrungszeichen ueber SSH -> cmd -> PowerShell werden gefressen
# (windows-remote-ops, Pitfall 1). Das hat hier schon einmal Murks erzeugt.

$muster = @(
    'fundusapps.stt_server',
    '-m kg --config',
    '-m kg2 --config',
    'mirror.uploader',
    'mirror.abholer'
)

$treffer = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object {
        $zeile = $_.CommandLine
        ($muster | Where-Object { $zeile -like ('*' + $_ + '*') }) -ne $null
    }

if (-not $treffer) {
    Write-Output 'Es lief nichts.'
} else {
    foreach ($p in $treffer) {
        $was = switch -Wildcard ($p.CommandLine) {
            '*stt_server*'      { 'Spracherkennung' }
            '*-m kg --config*'  { 'Kern' }
            '*-m kg2*'          { 'Traum' }
            '*uploader*'        { 'Spiegel' }
            '*abholer*'         { 'Abholer' }
            default             { 'unbekannt' }
        }
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Output ("beendet: $was (PID " + $p.ProcessId + ")")
    }
}

# Die Anzeigefenster der Station (Edge mit eigenem Profil) mit schliessen.
$eigene = Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*kg-logs\edge-*' }
if ($eigene) {
    $eigene | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Write-Output ('beendet: ' + @($eigene).Count + ' Anzeigefenster')
}

Start-Sleep -Seconds 3

# Belegen statt behaupten: welche Ports lauschen noch?
$offen = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in 8800, 8810, 8899, 5051 } |
    Select-Object -ExpandProperty LocalPort | Sort-Object -Unique
if ($offen) {
    Write-Output ('NOCH OFFEN: ' + ($offen -join ', '))
} else {
    Write-Output 'Alle Ports frei.'
}
