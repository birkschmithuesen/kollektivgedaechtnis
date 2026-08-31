#!/usr/bin/env bash
# Einen Ausstellungsdurchlauf abschließen: ARCHIVIEREN statt löschen.
#
# Ersetzt die beiden `rm`-Zeilen, die bis 2026-09-01 im Runbook standen
# (docs/operations.md, „Neuer Ausstellungstag"). Birks stehende Regel: nie
# etwas endgültig löschen, immer archivieren — und über Löschungen entscheidet
# er selbst. Dieses Skript löscht deshalb NICHTS, es verschiebt nur.
#
# Warum Verschieben und nicht Kopieren: `mv` ist auf demselben Datenträger
# atomar und kostet keine Zeit, auch bei tausenden Bildern. Ein Kopieren würde
# den Platz verdoppeln und bei einem Abbruch einen halben Bestand hinterlassen.
#
# Aufruf AUF DER TRAUM-MASCHINE, bei gestoppten Diensten:
#
#     scripts/neuer-durchlauf.sh "Probelauf Freitagnachmittag"
#
# Der Text ist die Notiz, die im Archivordner landet. Ohne sie weiß in einer
# Woche niemand mehr, welcher Ordner der echte Ausstellungstag war.
set -euo pipefail

NOTIZ=${1:-""}
ZEITSTEMPEL=$(date +%Y-%m-%d_%H%M)
ARCHIV="archiv/$ZEITSTEMPEL"

# `data/` gehoert Werkzeug 1 (Interviews/Graph), `dream-data/` Werkzeug 2
# (Traeume/Bilder) -- die beiden data_dir aus config.toml und config2.toml.
BESTAENDE=(data dream-data)

# Der Einbettungs-Cache ist der AUSNAHMEFALL: er spart Geld und macht
# Wiederholungen offlinefaehig (docs/operations.md: „diese Datei nicht
# loeschen"). Er wandert mit ins Archiv und wird danach zurueckkopiert, damit
# der frische Durchlauf ihn weiter nutzt.
CACHE="data/embeddings.sqlite3"

echo "=== 1/4  Pruefen, dass nichts laeuft ============================="
# SQLite haelt offene Handles: ein Verschieben unter laufendem Prozess ergibt
# eine halbe Datenbank. Ueber die Datei pruefen, NICHT ueber `ps | grep` --
# der Check matcht sonst seine eigene Kommandozeile (docs/operations.md).
#
# Zwei Werkzeuge, weil KEINES ueberall da ist: auf dem vServer fehlt `fuser`
# (gemessen 2026-09-01), `lsof` ist vorhanden; anderswo ist es umgekehrt. Ohne
# diesen Rueckfall faellt die Pruefung still auf eine blosse Warnung zurueck --
# also genau dann, wenn sie gebraucht wird.
if command -v fuser >/dev/null 2>&1; then
  OFFEN_PRUEFER="fuser"
elif command -v lsof >/dev/null 2>&1; then
  OFFEN_PRUEFER="lsof"
else
  OFFEN_PRUEFER=""
fi

ist_offen() {
  case "$OFFEN_PRUEFER" in
    fuser) fuser "$1" >/dev/null 2>&1 ;;
    lsof)  lsof -- "$1" >/dev/null 2>&1 ;;
    *)     return 1 ;;
  esac
}

if [ -n "$OFFEN_PRUEFER" ]; then
  for datenbank in data/*.sqlite3 dream-data/*.sqlite3; do
    [ -e "$datenbank" ] || continue
    if ist_offen "$datenbank"; then
      echo "FEHLER: '$datenbank' ist noch geoeffnet - erst STOP druecken." >&2
      echo "        Ein Verschieben jetzt ergaebe eine halbe Datenbank." >&2
      exit 1
    fi
  done
  echo "  keine offenen Datenbanken (geprueft mit $OFFEN_PRUEFER)"
else
  echo "  WARNUNG: weder 'fuser' noch 'lsof' vorhanden - kann offene Dateien" >&2
  echo "           nicht pruefen. Bitte selbst sicherstellen, dass gestoppt ist." >&2
fi

echo "=== 2/4  Rueckfrage ============================================="
# Ein versehentlicher Doppelklick mitten am Ausstellungstag waere teuer,
# deshalb steht hier eine Frage und keine Automatik.
VORHANDEN=()
for ordner in "${BESTAENDE[@]}"; do
  [ -e "$ordner" ] && VORHANDEN+=("$ordner")
done
if [ ${#VORHANDEN[@]} -eq 0 ]; then
  echo "Nichts zu archivieren - weder data/ noch dream-data/ existieren."
  exit 0
fi
echo "Diese Bestaende wandern nach $ARCHIV/ :"
for ordner in "${VORHANDEN[@]}"; do
  echo "  - $ordner  ($(du -sh "$ordner" 2>/dev/null | cut -f1))"
done
echo
read -r -p "Durchlauf abschliessen und archivieren? [ja/NEIN] " ANTWORT
if [ "$ANTWORT" != "ja" ]; then
  echo "Abgebrochen - es wurde nichts verschoben."
  exit 0
fi

echo "=== 3/4  Verschieben ============================================"
mkdir -p "$ARCHIV"
for ordner in "${VORHANDEN[@]}"; do
  mv "$ordner" "$ARCHIV/$ordner"
  echo "  $ordner -> $ARCHIV/$ordner"
done

# Notiz schreiben, bevor irgendetwas anderes passiert: der Ordner ohne Notiz
# ist genau das Problem, das diese Zeile verhindert.
{
  echo "Durchlauf archiviert am $(date '+%Y-%m-%d %H:%M:%S')"
  echo
  if [ -n "$NOTIZ" ]; then
    echo "$NOTIZ"
  else
    echo "(keine Notiz angegeben - wofuer war dieser Durchlauf?)"
  fi
} > "$ARCHIV/NOTIZ.txt"
echo "  Notiz: $ARCHIV/NOTIZ.txt"

echo "=== 4/4  Einbettungs-Cache zurueckholen ========================="
if [ -f "$ARCHIV/$CACHE" ]; then
  mkdir -p "$(dirname "$CACHE")"
  cp -p "$ARCHIV/$CACHE" "$CACHE"
  echo "  $CACHE zurueckkopiert (spart Geld, haelt den Start offlinefaehig)"
else
  echo "  kein Cache im Archiv - der naechste Lauf baut ihn neu auf"
fi

echo
echo "Fertig. Der naechste Start legt data/ und dream-data/ leer neu an."
echo "Geloescht wurde nichts: alles liegt in $ARCHIV/"
