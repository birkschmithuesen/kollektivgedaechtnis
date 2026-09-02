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
grau "  Nach draussen, jeweils eigenes Fenster und eigene Entscheidung:"
grau "    ./scripts/spiegel-start-mac.sh    Graph und Traum an den Spiegel"
grau "    ./scripts/abholer-start-mac.sh    Fotos vom Spiegel abholen"
grau "                                      (Handys ohne Tailnet)"
echo ""

wait $STATION_PID
