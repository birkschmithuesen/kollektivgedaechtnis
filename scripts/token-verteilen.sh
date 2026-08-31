#!/usr/bin/env bash
# Holt das Spiegel-Token von herkules und setzt es dort ein, wo es gebraucht
# wird — OHNE dass es je in einer Agenten-Sitzung, in einem Chatverlauf oder in
# einer Logzeile auftaucht.
#
# Der Punkt dieses Skripts: der Wert wandert ausschliesslich durch die
# SSH-Verbindung und landet direkt in einer Datei mit Rechten 600. Es wird
# nirgends ausgegeben. Wer das Skript liest, lernt das Token nicht.
#
# Aufruf:
#   scripts/token-verteilen.sh pruefen
#   scripts/token-verteilen.sh windows <tailscale-name-oder-ip>
#   scripts/token-verteilen.sh datei   <zielpfad>
#
set -euo pipefail

HERKULES="${KG_HERKULES:-fundusbot@91.98.143.165}"
QUELLE='$HOME/.config/kg-mirror.env'

# Das Token einmal holen. `local`/Subshell statt globaler Variable, und
# ausdruecklich NIE `echo`: der Wert existiert nur so lange wie noetig.
token_holen() {
  ssh -o BatchMode=yes "$HERKULES" \
    "grep -h '^KG_MIRROR_TOKEN=' $QUELLE | head -1 | cut -d= -f2-"
}

fall="${1:-pruefen}"

case "$fall" in

  pruefen)
    # Beweist, dass das Token da und brauchbar ist — ohne es zu zeigen.
    # Gemessen wird die LAENGE und ein kurzer Fingerabdruck; beides verraet
    # den Wert nicht, unterscheidet ihn aber zuverlaessig von einem anderen.
    ssh -o BatchMode=yes "$HERKULES" bash -s <<'FERN'
set -euo pipefail
q="$HOME/.config/kg-mirror.env"
[ -f "$q" ] || { echo "FEHLT: $q"; exit 1; }
rechte=$(stat -c '%a %U' "$q")
t=$(grep -h '^KG_MIRROR_TOKEN=' "$q" | head -1 | cut -d= -f2-)
[ -n "$t" ] || { echo "LEER: kein KG_MIRROR_TOKEN in $q"; exit 1; }
echo "Datei     : $q ($rechte)"
echo "Laenge    : ${#t} Zeichen"
echo "Fingerab. : $(printf '%s' "$t" | sha256sum | cut -c1-12)"
# Die eigentliche Probe: nimmt der laufende Empfaenger es an?
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 \
  -X POST http://127.0.0.1:8820/ingest/dream \
  -H "Authorization: Bearer $t" -H 'content-type: application/json' \
  -d '{"current":null,"history":[]}')
echo "Probe     : Empfaenger antwortet $code (200 = Token gilt)"
FERN
    ;;

  windows)
    # Legt das Token auf dem Ausstellungsrechner in %USERPROFILE%\.kg-mirror-token
    # ab. Von dort liest es das Startskript des Uploaders — der Wert steht damit
    # nie in einer Verknuepfung, nie in der Aufgabenplanung, nie im Verlauf der
    # PowerShell.
    #
    # Die Standard-Shell des Windows-OpenSSH-Servers ist `cmd`, nicht bash:
    # ein `cat > "$HOME/..."` scheitert dort mit „Das System kann den
    # angegebenen Pfad nicht finden." Deshalb schreibt PowerShell die Datei,
    # und zwar ueber die Standardeingabe — der Wert steht nirgends auf einer
    # Kommandozeile und taucht damit auch in keiner Prozessliste auf.
    ziel="${2:?Aufruf: $0 windows <tailscale-name-oder-ip>}"
    token_holen | ssh -o BatchMode=yes "$ziel" \
      'powershell -NoProfile -Command "$t=[Console]::In.ReadToEnd().Trim(); $p=Join-Path $env:USERPROFILE \".kg-mirror-token\"; [IO.File]::WriteAllText($p,$t); $a=Get-Acl $p; $a.SetAccessRuleProtection($true,$false); $a.Access | ForEach-Object { $a.RemoveAccessRule($_) | Out-Null }; $a.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($env:USERNAME,\"FullControl\",\"Allow\"))); Set-Acl $p $a; Write-Output (\"abgelegt: \" + $p + \" (\" + $t.Length + \" Zeichen, nur \" + $env:USERNAME + \")\")"'
    ;;

  datei)
    # Schreibt eine .env-Zeile an einen beliebigen lokalen Pfad, Rechte 600.
    ziel="${2:?Aufruf: $0 datei <zielpfad>}"
    umask 077
    { printf 'KG_MIRROR_TOKEN='; token_holen; } > "$ziel"
    chmod 600 "$ziel"
    echo "geschrieben: $ziel ($(stat -c '%a' "$ziel"), $(wc -c < "$ziel") Bytes)"
    ;;

  *)
    echo "Unbekannt: $fall" >&2
    sed -n '1,20p' "$0" >&2
    exit 2
    ;;
esac
