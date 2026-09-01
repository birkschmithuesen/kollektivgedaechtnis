#!/usr/bin/env bash
# Startet die Station auf dem MacBook — Kern, Traum, und die Fenster.
#
# 🔴 WARUM ES DIESE DATEI GIBT (Birk, 2026-09-01, vor Ort):
#   „Die Station läuft jetzt auf dem MacBook, nicht mehr auf dem Tracking-
#    Laptop. Bereite vor, dass wir das dort auch mit dem Skript alles starten
#    können. Das ist ja jetzt Mac, da laufen keine .bat-Dateien."
#
# Der Wechsel kam, weil der Windows-Rechner ruckelte. Der Grund dafür ist
# inzwischen gefunden (docs/STAND.md §2m: Windows stand auf „Balanced" und
# drosselte die GPU um 28 %) — der Mac bleibt trotzdem die Ausstellungsmaschine,
# solange Birk nicht anders entscheidet.
#
# Unterschiede zu `start.sh` (Linux) und `kollektivtraum.bat` (Windows):
#   * Browser ist Brave, nicht Chromium — auf dem Mac liegt er unter
#     /Applications, nicht im PATH.
#   * Kein `--kiosk` auf einem zweiten Schirm über `--window-position`: macOS
#     ordnet Fenster anders zu (siehe „Fensterplatzierung" unten).
#   * Zwei GETRENNTE Browserprofile, damit die zwei Fenster sich nicht
#     gegenseitig die Sitzung überschreiben.
#
# Aufruf:
#     ./scripts/start-mac.sh
#     KG_TOUCH_DISPLAY=2 ./scripts/start-mac.sh     # Touchfläche ist Schirm 2
#
# Beenden: Strg-C in diesem Fenster. Das räumt die ganze Prozessgruppe ab.

set -u
cd "$(dirname "$0")/.."

# --- Schlüssel: früh und laut scheitern ------------------------------------
# Ein fehlender Schlüssel um 10:00 am Ausstellungstag darf nicht als leerer
# Graph drei Interviews später auffallen. Wenn eine .env existiert, wird sie
# gelesen — auf dem Mac ist das der übliche Weg, weil die Schlüssel dort nicht
# in der Shell-Umgebung stehen.
if [ -f .env ]; then
  # shellcheck disable=SC1091
  set -a; . ./.env; set +a
fi
: "${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY fehlt — in .env eintragen oder exportieren}"
: "${OPENROUTER_API_KEY:?OPENROUTER_API_KEY fehlt — in .env eintragen oder exportieren}"

HOST=${KG_HOST:-127.0.0.1}
PORT=${KG_PORT:-8800}
TRAUM_PORT=${KG_TRAUM_PORT:-8810}

# --- Brave finden -----------------------------------------------------------
# Auf dem Mac liegt die ausführbare Datei IM App-Bündel und ist nicht im PATH.
BRAVE="/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
if [ ! -x "$BRAVE" ]; then
  # Chrome als Rückfall — derselbe Motor, dieselben Schalter.
  BRAVE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
fi
if [ ! -x "$BRAVE" ]; then
  echo "FEHLER: Weder Brave noch Chrome unter /Applications gefunden." >&2
  echo "        Erwartet: $BRAVE" >&2
  exit 1
fi

# --- Profile: zwei Fenster, zwei Sitzungen ----------------------------------
# Ohne getrennte Profile teilen sich beide Fenster eine Sitzung. Das ist auf
# dem Windows-Rechner mehrfach schiefgegangen: ein Fenster überschreibt die
# Fensterposition des anderen, und ein Absturz reißt beide mit.
PROFIL_WAND="${TMPDIR:-/tmp}/kg-profil-wand"
PROFIL_PULT="${TMPDIR:-/tmp}/kg-profil-pult"
mkdir -p "$PROFIL_WAND" "$PROFIL_PULT"

cleanup() {
  echo "" >&2
  echo "fahre herunter …" >&2
  # Die ganze Prozessgruppe, sonst überlebt eine Neustartschleife das Strg-C.
  kill 0
}
trap cleanup EXIT INT TERM

echo "[1/5] git pull"
git pull --ff-only 2>&1 | sed 's/^/      /' || echo "      (übersprungen — nicht kritisch)"

echo "[2/5] Kern startet auf Port $PORT"
while true; do
  uv run python -m kg --config config.toml
  echo "      Kern beendet ($?), Neustart in 3 s" >&2
  sleep 3
done &
CORE_PID=$!

echo "[3/5] warte, bis der Kern antwortet"
# Auf die Antwort warten statt auf gut Glück zu schlafen: ein langsamer erster
# Start öffnete sonst beide Fenster auf einer Fehlerseite.
for _ in $(seq 1 60); do
  if curl -fsS -o /dev/null "http://$HOST:$PORT/api/state"; then
    echo "      Kern ist da"
    break
  fi
  sleep 1
done

echo "[4/5] Traum startet auf Port $TRAUM_PORT"
while true; do
  uv run python -m kg2 --config config.toml
  echo "      Traum beendet ($?), Neustart in 5 s" >&2
  sleep 5
done &

echo "[5/5] Fenster"

# --- Fensterplatzierung -----------------------------------------------------
# 🔴 `--window-position` ist auf dem Mac unzuverlässig: macOS entscheidet
# selbst, auf welchem Schirm ein Fenster aufgeht, und ein Vollbild wechselt
# den Schirm gar nicht mehr. Deshalb wird hier NICHT versucht, das per Schalter
# zu erzwingen — das war schon auf dem Windows-Rechner die Ursache dafür, dass
# die Touchfläche auf dem falschen Schirm landete (beide Fenster starteten auf
# derselben Position 1920,0, siehe docs/STAND.md §2n).
#
# Stattdessen: Fenster gehen normal auf, und wer sie einmal von Hand auf den
# richtigen Schirm schiebt und dort per grünem Knopf auf Vollbild setzt, bekommt
# sie dank getrennter Profile beim nächsten Start wieder dorthin.

# Die Touchfläche im Foyer. `?touch=1` ist NICHT optional: ohne den Parameter
# hängt sich die Touch-Steuerung gar nicht erst ein — keine Zoomgeste, kein
# Zoomregler, keine Bedienleiste. Genau das war auf dem Windows-Rechner der
# Fehler (docs/STAND.md §2n).
while true; do
  "$BRAVE" --user-data-dir="$PROFIL_WAND" \
    --new-window --start-fullscreen --noerrdialogs \
    --disable-session-crashed-bubble --disable-infobars \
    --autoplay-policy=no-user-gesture-required \
    "http://$HOST:$PORT/projection?touch=1"
  echo "      Wandfenster beendet, Neustart" >&2
  sleep 2
done &

# Das Bedienpult. Gewöhnliches Fenster, eigenes Profil.
while true; do
  "$BRAVE" --user-data-dir="$PROFIL_PULT" \
    --new-window --window-size=1280,900 \
    "http://$HOST:$PORT/operator"
  sleep 2
done &

cat <<'HINWEIS'

      Offen:
        Touchfläche   http://127.0.0.1:8800/projection?touch=1
        Bedienpult    http://127.0.0.1:8800/operator

      Bei Bedarf von Hand:
        Plenarsaal    http://127.0.0.1:8800/plenum
        Saal-Pult     http://127.0.0.1:8800/operator-plenum
        Touch-Test    http://127.0.0.1:8800/touchtest
        Traum         http://127.0.0.1:8810/dream

      Beenden: Strg-C hier im Fenster.

HINWEIS

wait $CORE_PID
