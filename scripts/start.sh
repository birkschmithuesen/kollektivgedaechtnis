#!/usr/bin/env bash
# On-site launcher: core + two browser windows, each restarted if it dies.
set -u
cd "$(dirname "$0")/.."

# Fail loudly and early: a missing key at 10:00 on the exhibition day must not
# surface as a silently empty graph three interviews later.
: "${ANTHROPIC_API_KEY:?export ANTHROPIC_API_KEY first}"
: "${KG_TELEGRAM_TOKEN:?export KG_TELEGRAM_TOKEN first}"
: "${OPENROUTER_API_KEY:?export OPENROUTER_API_KEY first}"

HOST=${KG_HOST:-127.0.0.1}
PORT=${KG_PORT:-8800}
# Which display the beamer is on. `xrandr --listmonitors` tells you the offset;
# 1920,0 is the second screen to the right of a 1920-wide laptop panel.
PROJECTION_POS=${KG_PROJECTION_POS:-1920,0}

cleanup() {
  echo "shutting down…" >&2
  # Kill the whole process group so no restart loop survives the Ctrl-C.
  kill 0
}
trap cleanup EXIT INT TERM

while true; do
  uv run python -m kg --config config.toml
  echo "core exited ($?), restarting in 3s" >&2
  sleep 3
done &
CORE_PID=$!

# Wait for the server to actually answer instead of guessing with a sleep:
# a slow first start would otherwise open both browsers on a connection error.
for _ in $(seq 1 60); do
  if curl -fsS -o /dev/null "http://$HOST:$PORT/api/state"; then break; fi
  sleep 1
done

# Projection: fullscreen kiosk on the beamer.
while true; do
  chromium --kiosk --window-position="$PROJECTION_POS" --noerrdialogs \
    --disable-session-crashed-bubble --disable-infobars --incognito \
    --autoplay-policy=no-user-gesture-required \
    "http://$HOST:$PORT/projection"
  echo "projection window exited, restarting" >&2
  sleep 2
done &

# Operator: ordinary window on the laptop display. Never the same window.
while true; do
  chromium --new-window --window-position=0,0 --window-size=1280,900 \
    "http://$HOST:$PORT/operator"
  sleep 2
done &

wait $CORE_PID
