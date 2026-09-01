#!/usr/bin/env bash
# Macht die Station im TAILNET erreichbar -- und nur dort.
#
# 🔴 WARUM SO (Birk, 2026-09-01): „es soll unbedingt nur im tailscale
# erreichbar bleiben!"
#
# Der naheliegende Weg waere `server_host = "0.0.0.0"` plus eine Freigabe in
# der macOS-Firewall. Der ist VERWORFEN: er oeffnet die Bedienpulte auch im
# Ausstellungs-WLAN, und die haben keine Anmeldung -- wer im selben Netz ist,
# koennte /operator aufmachen und Regler verstellen.
#
# Stattdessen bleiben alle drei Dienste auf 127.0.0.1, und `tailscale serve`
# nimmt die Anfrage im Tailnet an und reicht sie an Loopback weiter. Zwei
# Nebenwirkungen, beide erwuenscht:
#   * Ausserhalb des Tailnets ist kein Port offen (gemessen: LAN-Adresse
#     antwortet auf allen drei Ports gar nicht).
#   * Die macOS-Firewall muss nicht angefasst werden. Sie filtert nach BINARY
#     und blockte den Brew-Python; `tailscaled` ist laengst freigegeben.
#
# 🔴 `--tcp`, nicht `--http`. Mit `--http` bindet serve an den MagicDNS-NAMEN:
# `http://birk:8800` antwortet dann, `http://100.95.122.67:8800` aber mit 404.
# Wer auf dem zweiten Rechner kein MagicDNS hat, steht vor einer Station, die
# laut Statusausgabe laeuft und trotzdem nicht aufgeht. Der TCP-Weiterleiter
# ist namensunabhaengig -- Name UND IP funktionieren.
#
# Aufruf (die Station muss laufen):
#     ./scripts/tailscale-freigeben.sh
#
# Rueckgaengig:  tailscale serve reset

set -u
TS_BIN=/usr/local/bin/tailscale
PORTS=(8800 8810 5051)

command -v "$TS_BIN" >/dev/null 2>&1 || TS_BIN=/Applications/Tailscale.app/Contents/MacOS/Tailscale
[ -x "$TS_BIN" ] || { echo "FEHLER: tailscale-CLI nicht gefunden." >&2; exit 1; }

TS_IP=$("$TS_BIN" ip -4 2>/dev/null | head -1)
[ -n "$TS_IP" ] || { echo "FEHLER: keine Tailscale-Adresse. Ist Tailscale an?" >&2; exit 1; }

echo ""
echo "Station im Tailnet freigeben ($TS_IP)"

for P in "${PORTS[@]}"; do
  # Erst einen etwaigen --http-Eintrag desselben Ports raeumen: die beiden
  # Modi teilen sich den Port und wuerden einander sonst blockieren.
  "$TS_BIN" serve --http="$P" off  >/dev/null 2>&1 || true
  "$TS_BIN" serve --bg --yes --tcp="$P" "tcp://127.0.0.1:$P" >/dev/null 2>&1 \
    && echo "  ✓ Port $P weitergeleitet" \
    || echo "  ✗ Port $P: serve fehlgeschlagen"
done

echo ""
echo "Gegenprobe:"
alles_gut=1
for P in "${PORTS[@]}"; do
  pfad=/; [ "$P" = 8800 ] && pfad=/api/state; [ "$P" = 8810 ] && pfad=/dream; [ "$P" = 5051 ] && pfad=/status
  code=$(curl -s -L -o /dev/null -m 8 -w "%{http_code}" "http://$TS_IP:$P$pfad")
  [ "$code" = "200" ] && echo "  ✓ Tailnet  $TS_IP:$P  HTTP $code" \
                      || { echo "  ✗ Tailnet  $TS_IP:$P  HTTP $code"; alles_gut=0; }
done

# Das WICHTIGERE Ergebnis: dass es im WLAN NICHT aufgeht. Eine Freigabe, die
# man nur von der guten Seite prueft, ist keine geprueft.
LAN=$(ipconfig getifaddr en0 2>/dev/null || true)
if [ -n "$LAN" ]; then
  for P in "${PORTS[@]}"; do
    code=$(curl -s -o /dev/null -m 5 -w "%{http_code}" "http://$LAN:$P/")
    [ "$code" = "000" ] && echo "  ✓ WLAN     $LAN:$P  zu (das ist gewollt)" \
                        || { echo "  🔴 WLAN   $LAN:$P  ANTWORTET (HTTP $code) — offen!"; alles_gut=0; }
  done
else
  echo "  (keine WLAN-Adresse auf en0 — Gegenprobe uebersprungen)"
fi

echo ""
if [ "$alles_gut" = "1" ]; then
  echo "  Auf dem zweiten Rechner (im Tailnet) oeffnen:"
  echo "    http://$TS_IP:8800/plenum"
  echo "    http://$TS_IP:8800/operator-plenum"
  echo "    (oder http://birk:8800/plenum, wenn dort MagicDNS an ist)"
  echo ""
  exit 0
fi
exit 1
