#!/usr/bin/env bash
# Beendet die Station vollstaendig und BELEGT, dass sie beendet ist.
#
# 🔴 WARUM ES DIESE DATEI GIBT (2026-09-01, real passiert):
# Ein `pkill -f "python -m kg --config"` sieht aus, als haette es gewirkt, und
# laesst den Kern am Leben. Zwei Gruende, beide am Geraet nachgesehen:
#
#   1. macOS nennt das Binary `Python` mit GROSSEM P
#      (/usr/local/Cellar/python@3.14/.../Resources/Python.app/Contents/MacOS/Python).
#      `pkill -f` unterscheidet Gross- und Kleinschreibung. Das Muster
#      "python -m kg" trifft deshalb NUR den `uv run`-Mantel, nie den Prozess,
#      der wirklich laeuft.
#   2. `uv run` ist ein eigener Prozess davor. Wer den Mantel trifft, hat das
#      Kind noch nicht.
#
# Folge: ein zweiter Kern lief weiter und stritt sich mit dem neuen um den
# Telegram-Bot -- `telegram.error.Conflict: terminated by other getUpdates
# request`. Beim Mikrofon waere dasselbe schlimmer: der Pegel schlaegt aus,
# aber der Prozess mit dem Mikrofon ist nicht der mit dem offenen Port, also
# kommt nie ein Transkript an (docs/BETRIEB-stt-infomaniak.md, Falle 1).
#
# Deshalb wird hier NICHT nach Namen gesucht, sondern nach dem, worauf es
# ankommt: wer haelt den Port. Und danach wird nachgesehen, ob er weg ist.
#
# Aufruf:
#     ./scripts/stop-station.sh
#
# Braucht man vor jedem `dichte-umschalten.py` -- das Skript verweigert den
# Dienst, solange 8800 oder 8810 lauscht.

set -u

PORTS=(5051 8800 8810)
rot()  { printf '\033[31m%s\033[0m\n' "$*"; }
grau() { printf '\033[2m%s\033[0m\n' "$*"; }

echo ""
echo "Station wird beendet"

# --- 1. Erst die Startskripte --------------------------------------------
# Sonst starten ihre Neustartschleifen genau das wieder, was gerade beendet
# wurde, und der Stopp sieht aus wie ein Flackern.
# `spiegel-start-mac.sh` und `abholer-start-mac.sh` stehen mit in der Liste,
# seit `start-station.sh --mit-spiegel` sie mitstarten kann. Ein Stopp, der
# einen Uploader ins oeffentliche Netz weiterlaufen laesst, waere schlimmer
# als gar kein Stopp: er sagt "frei" und meint es nicht.
for muster in "scripts/start-station.sh" "scripts/start-mac.sh" "scripts/start-stt-mac.sh" \
              "scripts/spiegel-start-mac.sh" "scripts/abholer-start-mac.sh"; do
  pkill -f "$muster" 2>/dev/null && grau "  Startskript beendet: $muster"
done
sleep 1

# --- 2. Dann, wer die Ports haelt ----------------------------------------
# `lsof -t` gibt die PID des Prozesses, der WIRKLICH lauscht -- unabhaengig
# davon, wie er heisst, wie er gestartet wurde und wie sein Binary geschrieben
# ist. Das ist der Punkt: kein Namensraten.
for port in "${PORTS[@]}"; do
  pids=$(lsof -t -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null)
  [ -z "$pids" ] && continue
  # Erst freundlich (SIGTERM): der Kern schliesst dann seine Datenbank sauber.
  # shellcheck disable=SC2086
  kill $pids 2>/dev/null
  grau "  Port $port: SIGTERM an $(echo $pids | tr '\n' ' ')"
done
sleep 3

# --- 3. Wer dann noch lauscht, bekommt SIGKILL ---------------------------
# Am 2026-09-01 haben zwei Kerne SIGTERM ausgesessen; die Telegram-Konflikte
# stiegen waehrenddessen weiter (3 -> 7 -> 13). Ohne diesen Schritt endet der
# Stopp in einem Zustand, den niemand nachprueft.
for port in "${PORTS[@]}"; do
  pids=$(lsof -t -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null)
  [ -z "$pids" ] && continue
  # shellcheck disable=SC2086
  kill -9 $pids 2>/dev/null
  grau "  Port $port: SIGKILL an $(echo $pids | tr '\n' ' ')"
done
sleep 2

# --- 4. Verwaiste Prozesse ohne Port -------------------------------------
# Ein Kern, dem der Port schon abgenommen wurde, kann weiterlaufen und dabei
# weiter am Telegram-Bot haengen -- genau der Fall vom 2026-09-01. `pgrep -fi`
# (klein i) ist hier Pflicht, siehe oben.
for muster in "\-m kg --config" "\-m kg2 --config" "fundusapps.stt_server" \
              "mirror\.uploader" "mirror\.abholer"; do
  pids=$(pgrep -fi "$muster" 2>/dev/null | grep -v "^$$\$")
  for p in $pids; do
    # Die eigene Shell und die Pipeline drumherum nicht mitnehmen.
    ps -o command= -p "$p" 2>/dev/null | grep -q "shell-snapshots\|stop-station" && continue
    kill -9 "$p" 2>/dev/null && grau "  verwaister Prozess $p beendet"
  done
done
sleep 1

# --- 5. Beleg statt Vertrauen --------------------------------------------
offen=""
for port in "${PORTS[@]}"; do
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1 && offen="$offen $port"
done
reste=$(pgrep -fi "\-m kg --config|\-m kg2 --config|fundusapps.stt_server|mirror\.uploader|mirror\.abholer" 2>/dev/null \
        | while read -r p; do
            ps -o command= -p "$p" 2>/dev/null | grep -q "shell-snapshots\|stop-station" || echo "$p"
          done)

echo ""
if [ -z "$offen" ] && [ -z "$reste" ]; then
  echo "  ✓ 5051, 8800, 8810 frei — keine Reste, auch nichts nach draussen."
  echo ""
  exit 0
fi
[ -n "$offen" ] && rot "  ✗ Noch belegt:$offen"
if [ -n "$reste" ]; then
  rot "  ✗ Noch laufende Prozesse:"
  for p in $reste; do ps -o pid,command= -p "$p" 2>/dev/null | sed 's/^/      /'; done
fi
echo ""
exit 1
