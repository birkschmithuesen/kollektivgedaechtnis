#!/usr/bin/env bash
# Die Interviewdaten des Ausstellungstags in Birks Nextcloud sichern.
#
# 🔴 WARUM ES DIESE DATEI GIBT (Birk, 2026-09-02, am Ausstellungstag):
#   „Wo liegen die Interview-Daten? Sie werden nicht in das Repo geschrieben,
#    oder? Ich will sie in meiner Cloud sichern."
#
# Nein, sie liegen NICHT im Repo: `.gitignore` schliesst `/data/` und
# `dream-data/` aus, „weil das Repo oeffentlich ist. Betrifft Transkripte,
# kg.db, Portraits". Damit gibt es aber auch keine Sicherung durch `git push` —
# ein Plattenschaden am Abend haette den ganzen Tag gekostet.
#
# ## 🔴 Warum nicht einfach `cp kg.db`
#
# SQLite laeuft hier im WAL-Modus. Neben `kg.db` liegen `kg.db-wal` und
# `kg.db-shm`, und im WAL stehen Aenderungen, die noch nicht in der Hauptdatei
# angekommen sind — am 2026-09-02 waren das 4 MB, also mehr als die
# Hauptdatei selbst hatte. Wer nur `kg.db` kopiert, sichert einen alten Stand
# und merkt es nicht.
#
# `sqlite3 .backup` loest das: Es schreibt eine in sich stimmige Kopie, waehrend
# die Station weiterlaeuft. Genau so sind an diesem Tag alle Sicherungen vor
# Eingriffen entstanden.
#
# Aufruf (die Station darf dabei laufen):
#     ./scripts/sichern-in-cloud.sh
#     ./scripts/sichern-in-cloud.sh --ziel /anderer/ordner
#
# Jeder Lauf legt einen eigenen Ordner mit Zeitstempel an. Nichts wird
# ueberschrieben, nichts geloescht.

set -uo pipefail
cd "$(dirname "$0")/.."

ZIEL_BASIS="/Users/macbook/nextcloud/Hermes-Agent/RoboCloud/NewBauhaus-2026-Interviews"
if [ "${1:-}" = "--ziel" ] && [ -n "${2:-}" ]; then
  ZIEL_BASIS="$2"
fi

rot()  { printf '\033[31m%s\033[0m\n' "$*"; }
gruen(){ printf '\033[32m%s\033[0m\n' "$*"; }
grau() { printf '\033[2m%s\033[0m\n' "$*"; }

ZIEL="$ZIEL_BASIS/$(date +%Y-%m-%d_%H%M)"

echo ""
echo "Interviewdaten sichern"
grau "  nach $ZIEL"
echo ""

# --- 1. Erreichbar? --------------------------------------------------------
# Nextcloud haengt an einem Ordner, der auch mal nicht da ist (Client aus,
# Platte nicht eingehaengt). Ein Sicherungsskript, das dann munter in ein neu
# angelegtes Loch schreibt, ist schlimmer als keins: Es meldet Erfolg.
if [ ! -d "$ZIEL_BASIS" ]; then
  ELTERN="$(dirname "$ZIEL_BASIS")"
  if [ ! -d "$ELTERN" ]; then
    rot "FEHLER: $ELTERN gibt es nicht."
    rot "        Laeuft der Nextcloud-Client? Ist die Platte eingehaengt?"
    exit 1
  fi
  grau "  Zielordner wird angelegt"
fi
mkdir -p "$ZIEL" || { rot "FEHLER: $ZIEL nicht anlegbar."; exit 1; }

# --- 2. Die Datenbanken, konsistent ----------------------------------------
echo "=== 1/4  Datenbanken ============================================"
sichere_db() {
  local quelle="$1" name="$2"
  [ -f "$quelle" ] || { grau "  $name: nicht vorhanden, uebersprungen"; return; }
  if sqlite3 "$quelle" ".backup '$ZIEL/$name'" 2>/dev/null; then
    # Nachsehen, ob die Kopie lesbar ist. Eine Sicherung, die niemand
    # aufmacht, ist eine Vermutung.
    local zeilen
    zeilen=$(sqlite3 "$ZIEL/$name" "SELECT count(*) FROM sqlite_master;" 2>/dev/null || echo "")
    if [ -n "$zeilen" ]; then
      gruen "  ✓ $name ($(du -h "$ZIEL/$name" | cut -f1), $zeilen Tabellen/Indizes)"
    else
      rot "  ✗ $name kopiert, aber NICHT lesbar"
    fi
  else
    rot "  ✗ $name: .backup gescheitert"
  fi
}
sichere_db "data/kg.db"                 "kg.db"
sichere_db "data/embeddings.sqlite3"    "embeddings.sqlite3"
sichere_db "dream-data/dreams.sqlite3"  "dreams.sqlite3"

# --- 3. Die Dateien --------------------------------------------------------
echo "=== 2/4  Bilder und Transkript =================================="
kopiere() {
  local quelle="$1"
  [ -e "$quelle" ] || { grau "  $quelle: nicht vorhanden"; return; }
  cp -R "$quelle" "$ZIEL/" && \
    gruen "  ✓ $quelle ($(du -sh "$quelle" | cut -f1))"
}
kopiere "data/photos"
kopiere "data/portraits"
kopiere "data/transcript.jsonl"
kopiere "data/graph.json"
kopiere "dream-data/images"

# --- 4. Was drinsteht, im Klartext -----------------------------------------
# Eine Sicherung ohne Inhaltsverzeichnis ist in einem halben Jahr ein Ordner
# mit undurchsichtigen Dateinamen.
echo "=== 3/4  Inhaltsverzeichnis ====================================="
{
  echo "Kollektivgedächtnis — Interviewdaten"
  echo "gesichert am $(date '+%Y-%m-%d %H:%M:%S') von $(hostname)"
  echo "Quelle: $(pwd)"
  echo ""
  if [ -f "$ZIEL/kg.db" ]; then
    echo "PERSONEN"
    sqlite3 -header -column "$ZIEL/kg.db" \
      "SELECT id, datetime(started_at,'unixepoch','localtime') AS start,
              name, hidden,
              (SELECT count(*) FROM edge e WHERE e.person_id=p.id) AS begriffe
       FROM person p ORDER BY started_at;" 2>/dev/null
    echo ""
    echo "ZUSAMMENFASSUNG"
    sqlite3 "$ZIEL/kg.db" \
      "SELECT '  Personen (sichtbar): ' || count(*) FROM person WHERE hidden=0;
       SELECT '  Begriffe: '           || count(*) FROM term WHERE hidden=0;
       SELECT '  Verbindungen: '       || count(*) FROM edge;
       SELECT '  Zitate: '             || count(*) FROM quote;" 2>/dev/null
  fi
  if [ -f "$ZIEL/dreams.sqlite3" ]; then
    echo ""
    echo "TRÄUME"
    sqlite3 "$ZIEL/dreams.sqlite3" \
      "SELECT '  ' || id || '  ' || datetime(created_at,'unixepoch','localtime')
              || '  ' || replace(coalesce(sentence,'—'), char(10), ' / ')
       FROM dream WHERE discarded=0 ORDER BY created_at;" 2>/dev/null
  fi
  echo ""
  echo "DATEIEN"
  echo "  Fotos:       $(ls "$ZIEL/photos" 2>/dev/null | wc -l | tr -d ' ')"
  echo "  Portraits:   $(ls "$ZIEL/portraits" 2>/dev/null | wc -l | tr -d ' ')"
  echo "  Traumbilder: $(ls "$ZIEL/images" 2>/dev/null | wc -l | tr -d ' ')"
} > "$ZIEL/INHALT.txt"
gruen "  ✓ INHALT.txt"

# --- 5. Pruefsummen --------------------------------------------------------
# 🔴 Damit in der Cloud nachpruefbar ist, ob alles heil angekommen ist.
# Nextcloud synchronisiert im Hintergrund; ein halb hochgeladener Ordner sieht
# im Finder vollstaendig aus.
echo "=== 4/4  Prüfsummen ============================================="
( cd "$ZIEL" && find . -type f ! -name PRUEFSUMMEN.txt -exec shasum -a 256 {} \; \
    | sort -k2 > PRUEFSUMMEN.txt )
gruen "  ✓ PRUEFSUMMEN.txt ($(wc -l < "$ZIEL/PRUEFSUMMEN.txt" | tr -d ' ') Dateien)"
grau  "    Nachprüfen (später, in der Cloud):"
grau  "      cd '$ZIEL' && shasum -a 256 -c PRUEFSUMMEN.txt"

echo ""
gruen "Fertig: $ZIEL"
echo "  Gesamt: $(du -sh "$ZIEL" | cut -f1)"
echo ""
