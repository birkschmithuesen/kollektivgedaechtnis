#!/usr/bin/env bash
# Startet die ganze Station: Spracherkennung, Kern, Traum. Ein Fenster, leise.
#
# 🔴 WARUM ES DIESE DATEI GIBT (Birk, 2026-09-01, am Gerät):
#   „Ich will, dass ein Script alles startet und dann nicht so viel printed
#    in der Console. Nur super wichtige Sachen. Die Browser-Fenster will ich
#    selbst öffnen."
#
# Diese Datei startet NICHTS selbst. Sie ruft die zwei Skripte auf, die es
# schon gibt, und schaltet sie leise:
#     scripts/start-stt-mac.sh                  (Spracherkennung, mit Mikrofonschalter)
#     KG_FENSTER=0 scripts/start-mac.sh         (Kern + Traum, ohne Browserfenster)
#
# Das ist Absicht. In den beiden Skripten steckt Wissen, das teuer erarbeitet
# wurde — kein `--channels` am Mono-Mikrofon, `config2.toml` statt
# `config.toml` für den Traum, `?touch=1`, die Neustartschleifen. Eine zweite
# Fassung davon wäre eine zweite Stelle, an der es falsch werden kann; beim
# nächsten Umbau würde genau eine der beiden vergessen.
#
# Die Regel für die Ausgabe: **auf den Schirm kommt nur, was eine Handlung
# auslöst.** Ein Dienst, der da ist, bekommt eine Zeile; ein Dienst, der fehlt,
# bekommt die Zeilen, die man dann braucht. Alles andere steht im Log. Eine
# Warnung, die bei jedem Start erscheint, liest am Ausstellungstag niemand mehr
# — genau daran ist die /health-Prüfung in start-mac.sh gescheitert: sie fragte
# eine Route ab, die es gar nicht gibt, und warnte deshalb auch bei tadellos
# laufendem Dienst.
#
# Aufruf:
#     ./scripts/start-station.sh
#     KG_MIC_GATE=0 ./scripts/start-station.sh    # ohne Mikrofonschalter
#
# Beenden: Strg-C in diesem Fenster. Das nimmt alle drei Dienste mit.

set -u
cd "$(dirname "$0")/.."

LOGS="$HOME/kg-logs"
mkdir -p "$LOGS"

HOST=${KG_HOST:-127.0.0.1}
PORT=${KG_PORT:-8800}
TRAUM_PORT=${KG_TRAUM_PORT:-8810}
STT_PORT=5051

rot()  { printf '\033[31m%s\033[0m\n' "$*"; }
grau() { printf '\033[2m%s\033[0m\n' "$*"; }

# --- Was nach DRAUSSEN geht: aus, bis du es sagst ----------------------------
# 🔴 Die Voreinstellung ist und bleibt AUS. Der Uploader schiebt Portraits und
# Zitate von Menschen ins oeffentliche Netz, der Abholer darf beim Spiegel
# LOESCHEN. Beides ist Birks Entscheidung, kein Nebeneffekt eines Startknopfs.
#
# Ein getippter Schalter IST diese Entscheidung -- ausdruecklicher sogar als
# ein zweites Fenster, das man aufmacht und dann vergisst. Was die Trennung
# schuetzen soll, ist nicht das Fenster, sondern dass es nie von selbst
# passiert. `tests/test_spiegel_start_mac.py` und `tests/test_abholer_start_mac.py`
# pruefen genau das -- und zwar durch AUSFUEHREN (`--trocken`), nicht durch
# Lesen des Quelltextes.
MIT_SPIEGEL=0
MIT_ABHOLER=0
TROCKEN=0

hilfe() {
  cat <<'ENDE'
Aufruf: ./scripts/start-station.sh [Schalter]

  (ohne)            Spracherkennung, Kern, Traum. Nichts geht nach draussen.

  --mit-spiegel     zusaetzlich den Uploader: Graph, Traum und Portraits
                    hoch auf kollektivgedaechtnis.flashclash.de.
                    🔴 Damit werden Interviewdaten oeffentlich.
  --mit-abholer     zusaetzlich den Abholer: Fotos, die Handys OHNE Tailnet
                    beim Spiegel eingeworfen haben, herunter an die Station.
                    Braucht ein offenes Interview, sonst 409.
  --mit-allem       beides.

  --trocken         nur sagen, was gestartet wuerde. Startet nichts.
  --hilfe           dieser Text.

Umgebung:
  KG_MIC_GATE=0     ohne Mikrofonschalter, es wird durchgehend erkannt.

Beenden: Strg-C in diesem Fenster, oder ./scripts/stop-station.sh
ENDE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --mit-spiegel) MIT_SPIEGEL=1 ;;
    --mit-abholer) MIT_ABHOLER=1 ;;
    --mit-allem)   MIT_SPIEGEL=1; MIT_ABHOLER=1 ;;
    --trocken)     TROCKEN=1 ;;
    --hilfe|-h|--help) hilfe; exit 0 ;;
    *) rot "Unbekannter Schalter: $1"; echo ""; hilfe; exit 2 ;;
  esac
  shift
done

# 🔴 VOR dem `trap`. Der raeumt mit `kill 0` die ganze Prozessgruppe ab -- ein
# `exit` danach wuerde die aufrufende Shell mitnehmen.
if [ "$TROCKEN" = 1 ]; then
  echo "im Haus:      Spracherkennung, Kern, Traum"
  if [ "$MIT_SPIEGEL" = 1 ]; then
    echo "nach draussen: Uploader (spiegel-start-mac.sh)"
  else
    echo "nach draussen: kein Uploader"
  fi
  if [ "$MIT_ABHOLER" = 1 ]; then
    echo "nach draussen: Abholer (abholer-start-mac.sh)"
  else
    echo "nach draussen: kein Abholer"
  fi
  exit 0
fi

# `kill 0` nimmt die ganze Prozessgruppe. Ohne das überlebt eine der
# Neustartschleifen das Strg-C und hält Port oder Mikrofon besetzt. Beim
# nächsten Start stünde dann ein zweiter Dienst am selben Mikrofon — das
# teuerste Fehlerbild von allen, weil es nicht wie ein Fehler aussieht: der
# Pegel schlägt aus, aber der Prozess mit dem Mikrofon ist nicht der mit dem
# offenen Port, also kommt nie ein Transkript an
# (docs/BETRIEB-stt-infomaniak.md, Falle 1).
aufraeumen() {
  echo ""
  grau "fahre herunter …"
  kill 0
}
trap aufraeumen EXIT INT TERM

# --- Schlüssel: früh und laut ------------------------------------------------
if [ -f .env ]; then
  # shellcheck disable=SC1091
  set -a; . ./.env; set +a
fi
if [ -z "${HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY:-}" ]; then
  rot "FEHLER: HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY fehlt in .env."
  echo "        Daran hängen Analyse, Weckwort, Embeddings UND Spracherkennung."
  echo "        Vorlage: docs/env-vorlage-eu.txt"
  exit 1
fi

echo ""
echo "Kollektivgedächtnis — Station startet"

# --- Warten, bis ein Dienst wirklich ANTWORTET -------------------------------
# Nicht auf gut Glück schlafen: „Prozess gestartet" ist kein Beleg dafür, dass
# der Dienst erreichbar ist (docs/ARBEITSREGELN-ausstellungsrechner.md, Regel 4).
warte_auf() {
  local name="$1" url="$2" log="$3" pid="$4" sekunden="${5:-90}"
  local i
  for ((i = 1; i <= sekunden; i++)); do
    if curl -fsS -o /dev/null --max-time 3 "$url" 2>/dev/null; then
      printf '  ✓ %-16s %s\n' "$name" "nach ${i}s"
      return 0
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      rot "  ✗ $name: der Prozess ist gestorben. Letzte Zeilen aus $log:"
      tail -n 15 "$log" | sed 's/^/      /'
      return 1
    fi
    sleep 1
  done
  rot "  ✗ $name antwortet nach ${sekunden}s nicht. Letzte Zeilen aus $log:"
  tail -n 15 "$log" | sed 's/^/      /'
  return 1
}

# --- 1. Spracherkennung ------------------------------------------------------
# Zuerst, damit der Kern beim Start schon einen offenen Ereignisstrom vorfindet
# statt erst über seinen Reconnect-Umweg hineinzukommen.
STT_LOG="$LOGS/stt.start.log"
: > "$STT_LOG"
./scripts/start-stt-mac.sh > "$STT_LOG" 2>&1 &
STT_PID=$!
if warte_auf "Spracherkennung" "http://127.0.0.1:$STT_PORT/status" "$STT_LOG" "$STT_PID"; then
  # Welches Mikrofon es WIRKLICH geworden ist. Der Wert in der .env des
  # Dienstes ist nur ein Substring; der Name im Log ist das Gerät. Eine Zeile,
  # aber sie beantwortet die Frage, die sonst zehn Minuten kostet.
  geraet=$(sed -n "s/.*Found audio device '\([^']*\)'.*/\1/p" "$STT_LOG" | tail -1)
  [ -n "$geraet" ] && printf '    %-14s %s\n' "Mikrofon" "$geraet"
  if [ "${KG_MIC_GATE:-1}" = "0" ]; then
    printf '    %-14s %s\n' "Schalter" "AUS — es wird durchgehend erkannt"
  else
    printf '    %-14s %s\n' "Schalter" "an — der Pegel startet und beendet das Interview"
  fi
else
  rot "  → Ohne Spracherkennung gibt es KEIN Interview. Der Rest startet trotzdem."
fi

# --- 2. Kern und Traum -------------------------------------------------------
# KG_FENSTER=0: keine Browserfenster. Die Ausgabe von start-mac.sh (git pull,
# die [n/5]-Schritte, uvicorn) geht ins Log — hier zählt nur, ob die zwei Ports
# antworten.
STATION_LOG="$LOGS/station.log"
: > "$STATION_LOG"
KG_FENSTER=0 ./scripts/start-mac.sh > "$STATION_LOG" 2>&1 &
STATION_PID=$!
warte_auf "Kern"  "http://$HOST:$PORT/api/state"   "$STATION_LOG" "$STATION_PID" || exit 1
warte_auf "Traum" "http://$HOST:$TRAUM_PORT/dream" "$STATION_LOG" "$STATION_PID"

# --- Nur warnen, wenn es etwas zu tun gibt -----------------------------------
if [ -z "${BFL_API_KEY:-}" ]; then
  rot "  ! BFL_API_KEY fehlt — der Traum erzeugt keine Bilder. Alles andere läuft."
fi

# --- 3. Was nach draussen geht, nur auf Ansage -------------------------------
# Erst hier, nicht oben: beide sprechen mit dem Kern auf 8800. Wer sie vorher
# startet, bekommt eine Runde Verbindungsfehler ins Log, bevor es von selbst
# gut geht -- Laerm, der wie ein Fehler aussieht.
#
# Beide sind Dauerlaeufer mit eigener Fehlerbehandlung (mirror/uploader.py:
# jede Netz-Operation in try/except, Rueckwaerts-Abstand bis 60 s). Sie
# brauchen deshalb KEIN warte_auf: es gibt nichts, was antwortet. Was zaehlt,
# ist, ob der Prozess die ersten Sekunden ueberlebt -- stirbt er am fehlenden
# Token, steht das im Log und die letzten Zeilen kommen auf den Schirm.
starte_draussen() {
  local name="$1" skript="$2" log="$3"
  : > "$log"
  "$skript" > "$log" 2>&1 &
  local pid=$!
  sleep 3
  if kill -0 "$pid" 2>/dev/null; then
    printf '  ✓ %-16s %s\n' "$name" "laeuft (Log: $log)"
  else
    rot "  ✗ $name ist sofort beendet. Letzte Zeilen aus $log:"
    tail -n 15 "$log" | sed 's/^/      /'
  fi
}

if [ "$MIT_SPIEGEL" = 1 ]; then
  rot "  ! Der Spiegel ist AN — ab jetzt gehen Portraits und Zitate ins oeffentliche Netz."
  starte_draussen "Spiegel-Upload" "./scripts/spiegel-start-mac.sh" "$LOGS/spiegel.log"
fi
if [ "$MIT_ABHOLER" = 1 ]; then
  starte_draussen "Foto-Abholer" "./scripts/abholer-start-mac.sh" "$LOGS/abholer.log"
fi

cat <<HINWEIS

  Fenster selbst öffnen:

    Touchfläche   http://$HOST:$PORT/projection?touch=1&theme=f
    Bedienpult    http://$HOST:$PORT/operator

    Plenarsaal    http://$HOST:$PORT/plenum
    Saal-Pult     http://$HOST:$PORT/operator-plenum
    Traum         http://$HOST:$TRAUM_PORT/dream
    Traum-Pult    http://$HOST:$TRAUM_PORT/operator
    Mikrofon      http://127.0.0.1:$STT_PORT/operator

HINWEIS
grau "  ?touch=1 ist nicht optional — ohne den Parameter gibt es weder"
grau "  Zoomregler noch Bedienleiste. theme=f ist das Layout vom 2026-09-01."
grau "  Beenden: Strg-C. Mitlesen: tail -f $LOGS/station.log"
echo ""
# 🔴 HINWEIS, KEIN AUFRUF. Beide Dienste unten gehen nach DRAUSSEN und laufen
# deshalb bewusst nicht mit: der Uploader schiebt Interviewdaten ins
# oeffentliche Netz, der Abholer darf beim Spiegel loeschen (er braucht das
# starke Token). Ob das heute passiert, entscheidet Birk, nicht eine
# Startreihenfolge. Genannt werden sie trotzdem — wer sie sucht, sucht sie
# hier. `tests/test_spiegel_start_mac.py` und `tests/test_abholer_start_mac.py`
# halten fest, dass sie nicht aufgerufen werden.
if [ "$MIT_SPIEGEL" = 0 ] || [ "$MIT_ABHOLER" = 0 ]; then
  grau "  Nach draussen — laeuft nur auf Ansage, entweder als Schalter hier:"
  [ "$MIT_SPIEGEL" = 0 ] && grau "    --mit-spiegel   Graph, Traum und Portraits an den oeffentlichen Spiegel"
  [ "$MIT_ABHOLER" = 0 ] && grau "    --mit-abholer   Fotos vom Spiegel holen (Handys ohne Tailnet)"
  grau "  … oder als eigenes Fenster, wenn du es getrennt an- und ausschalten willst:"
  [ "$MIT_SPIEGEL" = 0 ] && grau "    ./scripts/spiegel-start-mac.sh"
  [ "$MIT_ABHOLER" = 0 ] && grau "    ./scripts/abholer-start-mac.sh"
fi
echo ""

wait $STATION_PID
