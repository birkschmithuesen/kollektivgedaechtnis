#!/usr/bin/env bash
# On-site launcher for Tool 2 (Kollektivtraum, screen B): watcher + server,
# plus the two browser windows, each restarted if it dies.
#
# The counterpart to scripts/start.sh, and deliberately a SEPARATE script:
# the two tools do not depend on each other (spec §9). Tool 2 may start
# before Tool 1, after it, or on another machine entirely — and if Tool 1 is
# missing, Tool 2 must come up anyway and simply not dream, rather than
# refuse to start. That independence is the whole point of polling
# graph.json instead of being launched by Tool 1.
#
# WHAT THIS SCRIPT WILL NOT DO: block until Tool 1 is reachable. It CHECKS,
# reports plainly, and carries on. A hard wait here would mean a Tool 1 that
# dies at 14:00 could never be replaced without also restarting screen B —
# and screen B holding its last dream through a Tool 1 outage is exactly
# the designed behaviour (docs/operations.md, „Wenn etwas ausfällt").
set -u
cd "$(dirname "$0")/.."

# Fail loudly and early. Stage 1 needs Anthropic, stage 2 needs OpenRouter;
# a missing key must surface now, not as a dream that silently fails at 10:00.
: "${ANTHROPIC_API_KEY:?export ANTHROPIC_API_KEY first}"
: "${OPENROUTER_API_KEY:?export OPENROUTER_API_KEY first}"

CONFIG=${KG2_CONFIG:-config2.toml}
HOST=${KG2_HOST:-127.0.0.1}
PORT=${KG2_PORT:-8810}
# Which display screen B is on. `xrandr --listmonitors` tells you the offset.
DREAM_POS=${KG2_DREAM_POS:-1920,0}

if [ ! -f "$CONFIG" ]; then
  echo "no $CONFIG — copy config2.example.toml and set tool1_url first" >&2
  exit 1
fi

# The address Tool 2 will poll, read from the config it is about to use, so
# this check can never disagree with what the process actually does.
TOOL1_URL=$(sed -n 's/^[[:space:]]*tool1_url[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "$CONFIG" | head -1)
TOOL1_URL=${TOOL1_URL:-http://127.0.0.1:8800}

echo "Tool 1 laut $CONFIG: $TOOL1_URL"
# `-s` as well as `-fsS`: on the failure path curl's own "Connection refused"
# line would otherwise print above the explanation below it, and the useful
# message is the one that says what to check.
if curl -fs -o /dev/null --max-time 5 "$TOOL1_URL/graph.json"; then
  echo "  erreichbar — Träume entstehen, sobald ein Interview fertig ist."
else
  echo "  NICHT erreichbar. Screen B startet trotzdem und zeigt seinen letzten" >&2
  echo "  Traum weiter; sobald Tool 1 antwortet, träumt es von selbst weiter." >&2
  echo "  Prüfen: Bind (server_host = \"0.0.0.0\" in Tool 1s config.toml)," >&2
  echo "  Firewall, und ob tool1_url auf die gedruckte Adresse zeigt." >&2
fi

cleanup() {
  echo "shutting down…" >&2
  # Kill the whole process group so no restart loop survives the Ctrl-C.
  kill 0
}
trap cleanup EXIT INT TERM

while true; do
  uv run python -m kg2 --config "$CONFIG"
  echo "kg2 exited ($?), restarting in 3s" >&2
  sleep 3
done &
DREAM_PID=$!

# Wait for Tool 2's OWN server to answer before opening browsers — same
# reason as scripts/start.sh: a slow first start would otherwise open both
# windows on a connection error.
for _ in $(seq 1 60); do
  if curl -fsS -o /dev/null "http://$HOST:$PORT/api/state"; then break; fi
  sleep 1
done

# Screen B: fullscreen kiosk. This is the dream itself.
while true; do
  chromium --kiosk --window-position="$DREAM_POS" --noerrdialogs \
    --disable-session-crashed-bubble --disable-infobars --incognito \
    --autoplay-policy=no-user-gesture-required \
    "http://$HOST:$PORT/dream"
  echo "dream window exited, restarting" >&2
  sleep 2
done &

# Operator: ordinary window. Never the same window as the dream.
while true; do
  chromium --new-window --window-position=0,0 --window-size=1280,900 \
    "http://$HOST:$PORT/operator"
  sleep 2
done &

wait $DREAM_PID
