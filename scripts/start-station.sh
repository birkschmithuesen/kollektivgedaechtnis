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

# --- Was nach DRAUSSEN geht --------------------------------------------------
# 🔴 SPIEGEL AN, ABHOLER AUS -- Birks Entscheidung am 2026-09-02, 11:20, am
# Ausstellungstag: „baue ihn auch in die start routine ein, dass ich ihn beim
# naechsten manuellen start auch mit starte."
#
# Vorher stand der Spiegel hier auf AUS. Der Grund dafuer gilt weiter und ist
# nicht widerlegt -- der Uploader schiebt Portraits und Zitate von Menschen ins
# oeffentliche Netz. Was sich geaendert hat, ist WER entscheidet: Nicht mehr
# der Schalter traegt die Entscheidung, sondern diese Zeile, und sie steht auf
# Birks ausdrueckliche Ansage. Der Ausstellungstag laeuft, die Wand traegt
# einen QR-Code auf genau diese Seite; ein vergessener Schalter hiess an
# diesem Tag: der QR-Code fuehrt ins Leere. Genau das war heute frueh der Fall
# (`docs/STAND.md` §4z: „Der Spiegel zeigte die Simulationsdaten").
#
# 🔴 Was die Regel schuetzen sollte, bleibt geschuetzt: dass niemand
# UNBEMERKT veroeffentlicht. Deshalb sagt das Skript beim Start in Rot, dass
# der Spiegel laeuft, und `--ohne-spiegel` schaltet ihn in einem Wort ab.
#
# Der ABHOLER bleibt aus. Er darf beim Spiegel LOESCHEN (starkes Token) und
# ist kein Teil dieser Ansage. Zwei Dienste, zwei Entscheidungen.
#
# `tests/test_spiegel_start_mac.py` und `tests/test_abholer_start_mac.py`
# pruefen das -- durch AUSFUEHREN (`--trocken`), nicht durch Lesen des
# Quelltextes.
MIT_SPIEGEL=1
MIT_ABHOLER=0
TROCKEN=0

hilfe() {
  cat <<'ENDE'
Aufruf: ./scripts/start-station.sh [Schalter]

  (ohne)            Spracherkennung, Kern, Traum -- UND den Uploader zum
                    oeffentlichen Spiegel.
                    🔴 Damit sind Portraits und Zitate oeffentlich sichtbar.

  --ohne-spiegel    ohne den Uploader. Nichts geht dann nach draussen.
  --mit-spiegel     (Vorgabe, seit 2026-09-02) -- der Schalter bleibt, damit
                    eine getippte Gewohnheit nicht als Fehler abbricht.
  --mit-abholer     zusaetzlich den Abholer: Fotos, die Handys OHNE Tailnet
                    beim Spiegel eingeworfen haben, herunter an die Station.
                    Braucht ein offenes Interview, sonst 409.
  --mit-allem       Spiegel und Abholer.

  --trocken         nur sagen, was gestartet wuerde. Startet nichts.
  --hilfe           dieser Text.

Umgebung:
  KG_MIC_GATE=0     ohne Mikrofonschalter, es wird durchgehend erkannt.

Beenden: Strg-C in diesem Fenster, oder ./scripts/stop-station.sh
ENDE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --mit-spiegel)  MIT_SPIEGEL=1 ;;
    --ohne-spiegel) MIT_SPIEGEL=0 ;;
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
  # 🔴 Erst nachsehen, ob schon einer laeuft. `spiegel-start-mac.sh` bleibt
  # einzeln aufrufbar, und seit der Spiegel hier VORGABE ist, treffen sich die
  # beiden Wege zwangslaeufig. Zwei Uploader gegen denselben Spiegel gab es am
  # 2026-09-02 schon (docs/STAND.md §3, PID 5348 + 11508): sie ueberschreiben
  # sich gegenseitig und fuehren zwei getrennte `mirror-uploaded.json`-Staende,
  # also laedt jeder hoch, was der andere gerade als erledigt abhakte.
  if pgrep -fi "mirror\.uploader" >/dev/null 2>&1; then
    grau "  Spiegel-Upload laeuft bereits (eigenes Fenster) — kein zweiter gestartet."
    rot  "  ! Der Spiegel ist AN — Portraits und Zitate sind im oeffentlichen Netz."
  else
    rot "  ! Der Spiegel ist AN — ab jetzt gehen Portraits und Zitate ins oeffentliche Netz."
    grau "    Nicht gewollt? Strg-C, dann: ./scripts/start-station.sh --ohne-spiegel"
    starte_draussen "Spiegel-Upload" "./scripts/spiegel-start-mac.sh" "$LOGS/spiegel.log"
  fi
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
# 🔴 HINWEIS, KEIN AUFRUF — fuer das, was gerade NICHT nach draussen geht.
# Seit 2026-09-02 laeuft der Spiegel als Vorgabe mit; genannt wird er hier also
# nur noch nach `--ohne-spiegel`. Der Abholer bleibt aus (er darf beim Spiegel
# loeschen und braucht das starke Token) und steht deshalb immer hier.
# `tests/test_spiegel_start_mac.py` und `tests/test_abholer_start_mac.py`
# halten beides fest.
if [ "$MIT_SPIEGEL" = 0 ] || [ "$MIT_ABHOLER" = 0 ]; then
  grau "  Nach draussen — laeuft NICHT, entweder als Schalter hier:"
  [ "$MIT_SPIEGEL" = 0 ] && grau "    --mit-spiegel   Graph, Traum und Portraits an den oeffentlichen Spiegel"
  [ "$MIT_ABHOLER" = 0 ] && grau "    --mit-abholer   Fotos vom Spiegel holen (Handys ohne Tailnet)"
  grau "  … oder als eigenes Fenster, wenn du es getrennt an- und ausschalten willst:"
  [ "$MIT_SPIEGEL" = 0 ] && grau "    ./scripts/spiegel-start-mac.sh"
  [ "$MIT_ABHOLER" = 0 ] && grau "    ./scripts/abholer-start-mac.sh"
fi
echo ""

wait $STATION_PID
