#!/usr/bin/env bash
# Gibt die Station in der macOS-Firewall frei, damit sie ueber Tailscale und
# LAN erreichbar ist. Braucht einmal das Passwort (sudo).
#
# 🔴 WARUM ES DIESE DATEI GIBT (Birk, 2026-09-01: „der plenum screen ist nicht
# von einem anderen rechner im tailscale erreichbar"):
#
# `server_host = "0.0.0.0"` allein reicht auf dem Mac NICHT. Die
# Anwendungs-Firewall von macOS filtert nach BINARY, nicht nach Port -- und sie
# filtert Loopback nicht. Ergebnis: 127.0.0.1 antwortet tadellos, jede andere
# Adresse nimmt die TCP-Verbindung an und legt dann ohne Antwort auf
# („Empty reply from server"). Im Zugriffslog von uvicorn steht dabei NICHTS,
# weil die Anfrage den Dienst nie erreicht -- es sieht also nicht nach Firewall
# aus, sondern nach einem kaputten Server.
#
# Am 2026-09-01 gegengeprueft, gleiche Maschine, gleiche 0.0.0.0-Bindung:
#   /usr/bin/python3 (in der Freigabe)   -> 127.0.0.1, Tailscale, LAN: alle 200
#   Brew-Python (nicht in der Freigabe)  -> nur 127.0.0.1
#
# 🔴 Der Pfad enthaelt die Python-VERSION. Nach `brew upgrade python` zeigt die
# Freigabe auf ein Binary, das es nicht mehr gibt, und die Station ist wieder
# nur lokal erreichbar -- ohne dass sich an der Konfiguration etwas geaendert
# haette. Dann dieses Skript einfach erneut laufen lassen: es fragt das Binary
# jedes Mal neu beim laufenden Dienst ab, statt einen Pfad fest zu verdrahten.
#
# Aufruf (die Station muss laufen, damit das Binary gefunden wird):
#     ./scripts/firewall-freigeben.sh

set -u
FW=/usr/libexec/ApplicationFirewall/socketfilterfw

if [ ! -x "$FW" ]; then
  echo "FEHLER: $FW gibt es nicht. Kein macOS?" >&2
  exit 1
fi

# Das Binary beim laufenden Dienst abfragen statt es zu raten: `uv` und `brew`
# verschieben es, und ein geratener Pfad wird stillschweigend zur falschen
# Freigabe.
BIN=""
for p in $(lsof -t -nP -iTCP -sTCP:LISTEN 2>/dev/null | sort -u); do
  cmd=$(ps -o command= -p "$p" 2>/dev/null | head -1)
  case "$cmd" in
    *stt_server*|*"-m kg"*|*"-m kg2"*) BIN=$(echo "$cmd" | awk '{print $1}'); break ;;
  esac
done

if [ -z "$BIN" ]; then
  echo "FEHLER: Auf 5051/8800/8810 laeuft nichts von der Station." >&2
  echo "        Erst starten:  ./scripts/start-station.sh" >&2
  exit 1
fi

echo ""
echo "Binary der Station:"
echo "  $BIN"
echo ""

if "$FW" --listapps 2>/dev/null | grep -qF "$BIN"; then
  echo "  steht schon in der Freigabe — setze sie trotzdem neu (unblock)."
fi

sudo "$FW" --add "$BIN" >/dev/null
sudo "$FW" --unblockapp "$BIN" >/dev/null

echo "  eingetragen und entsperrt."
echo ""

# Beleg statt Vertrauen: ueber die echte Tailscale-Adresse anfragen, nicht ueber
# Loopback -- Loopback war ja die ganze Zeit in Ordnung und beweist nichts.
TS=$(/usr/local/bin/tailscale ip -4 2>/dev/null | head -1)
PORT=${KG_PORT:-8800}
if [ -z "$TS" ]; then
  echo "  (keine Tailscale-Adresse gefunden — Gegenprobe uebersprungen)"
  exit 0
fi

echo "Gegenprobe ueber $TS:"
code=$(curl -s -o /dev/null -m 6 -w "%{http_code}" "http://$TS:$PORT/api/state")
if [ "$code" = "200" ]; then
  echo "  ✓ HTTP $code — von anderen Rechnern im Tailnet erreichbar."
  echo ""
  echo "  Plenum-Schirm dort oeffnen:"
  echo "    http://$TS:$PORT/plenum"
  echo "    http://$TS:$PORT/operator-plenum"
  echo ""
else
  echo "  ✗ HTTP $code — noch nicht erreichbar."
  echo "    Naechster Verdacht: lauscht der Dienst wirklich auf 0.0.0.0?"
  echo "      lsof -nP -iTCP -sTCP:LISTEN | grep 8800"
  echo "    Steht dort 127.0.0.1 statt *, dann server_host in config.toml aendern"
  echo "    und die Station neu starten."
  exit 1
fi
