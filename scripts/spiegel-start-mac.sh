#!/usr/bin/env bash
# Startet den Uploader zum oeffentlichen Spiegel auf dem MacBook.
#
# 🔴 WARUM ES DIESE DATEI GIBT (Birk, 2026-09-02):
#   „Ich bin dort draufgegangen. Der verbindet sich gar nicht zu dem MacBook."
#
# Gemessen an genau diesem Rechner, bevor die Datei entstand:
#   * kein Uploader-Prozess in `ps aux` -- nur macOS' eigenes MirrorDisplays,
#   * in `mirror/` zum Starten nur `.bat` (`spiegel-start.bat`), also der
#     Windows-Weg von vor dem Rechnerwechsel am 2026-09-01,
#   * `~/.kg-mirror-token` fehlt.
# Der oeffentliche Spiegel antwortete trotzdem -- mit dem SIMULATIONSSTAND
# (138 Knoten, `person-000.png`). Er zeigte also etwas, nur nicht das Haus.
#
# Die Uebertragung selbst ist in Ordnung: ein Empfaenger auf 127.0.0.1:8899 und
# eine einzelne `Uploader.runde()` gegen die laufende Station haben Graph,
# Traum und alle drei echten Portraits uebertragen. Es fehlte der Prozess.
#
# 🔴 DIESES SKRIPT LAEUFT NICHT IM SAMMELSTART MIT.
# `scripts/start-station.sh` startet, was IM HAUS laeuft. Hier gehen
# Interviewdaten ins OEFFENTLICHE Netz -- Portraits und Zitate von Menschen,
# die heute vor der Kamera standen. Ob das heute passiert, entscheidet Birk,
# nicht eine Startreihenfolge. Deshalb ein eigenes Fenster, eigener Knopf.
# `tests/test_spiegel_start_mac.py` haelt die Trennung fest.
#
# Aufruf:
#     ./scripts/spiegel-start-mac.sh
#     ./scripts/spiegel-start-mac.sh --pruefen    # nur nachsehen, nichts senden
#
# Beenden: Strg-C in diesem Fenster. Das Fenster darf den ganzen Tag offen
# bleiben -- der Uploader steht Netzaussetzer durch und faengt sich von selbst
# (mirror/uploader.py: jede Netz-Operation in try/except, Timeouts ueberall,
# Rueckwaerts-Abstand bis 60 s).

set -u

KG_REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$KG_REPO" || exit 1

rot()  { printf '\033[31m%s\033[0m\n' "$*"; }
grau() { printf '\033[2m%s\033[0m\n' "$*"; }

# --- Das Token --------------------------------------------------------------
# Es steht NICHT hier und in keiner .env des Repos, sondern in einer Datei im
# Heimatverzeichnis -- dieselbe Stelle wie auf dem Windows-Rechner
# (%USERPROFILE%\.kg-mirror-token), nur mit Unix-Rechten. Damit taucht es
# weder in dieser Datei noch in einer Prozessliste noch in einem Verlauf auf.
#
# 🔴 DIESE DATEI EXISTIERT AUF DIESEM MAC NOCH NICHT (Stand 2026-09-02).
# Anlegen -- der Wert kommt von herkules und darf nirgends dazwischen stehen:
#
#     scripts/token-verteilen.sh datei ~/.kg-mirror-token
#
# `token-verteilen.sh datei` schreibt eine `.env`-Zeile (`KG_MIRROR_TOKEN=…`);
# dieses Skript kommt mit beiden Formen zurecht, mit und ohne Praefix.
TOKENDATEI="${KG_TOKENDATEI:-$HOME/.kg-mirror-token}"

# --- Wohin, und woher ------------------------------------------------------
# Die Adresse ist der oeffentliche Spiegel. Sie steht hier fest und nicht in
# einer Konfigurationsdatei, weil sie zum Aufbau gehoert und nicht zum Betrieb
# -- dieselbe Zeile wie in `mirror/spiegel-start.bat`.
KG_MIRROR_URL="${KG_MIRROR_URL:-https://kollektivgedaechtnis.flashclash.de}"
# Die beiden Werkzeuge auf diesem Rechner. Vorgaben aus
# `mirror/uploader.py::main` -- Kern 8800, Traum 8810, wie sie
# `scripts/start-mac.sh` startet.
KG_TOOL1_URL="${KG_TOOL1_URL:-http://127.0.0.1:8800}"
KG_TOOL2_URL="${KG_TOOL2_URL:-http://127.0.0.1:8810}"
# Sekunden zwischen zwei Runden. 3 wie auf dem Windows-Rechner: hier geht es
# um die Frische einer ANZEIGE, nicht um eine Wartezeit vor der Wand (der
# Abholer daneben taktet deshalb schneller).
KG_MIRROR_INTERVAL="${KG_MIRROR_INTERVAL:-3}"

PRUEF_TIMEOUT="${KG_MIRROR_PRUEF_TIMEOUT:-5}"

fehlt_token() {
  rot "FEHLER: $TOKENDATEI fehlt."
  echo "        Ohne Token nimmt der Spiegel nichts an -- er antwortet auf jede"
  echo "        Aufnahme mit 401, und zwar den ganzen Tag lang stillschweigend."
  echo ""
  echo "        Anlegen (der Wert kommt von herkules und wird dabei nie ausgegeben):"
  echo "            scripts/token-verteilen.sh datei ~/.kg-mirror-token"
  echo ""
  echo "        Vorher pruefen, ob dort ueberhaupt eins liegt:"
  echo "            scripts/token-verteilen.sh pruefen"
}

# Liest die Datei und schaelt ein evtl. vorangestelltes `KG_MIRROR_TOKEN=`
# ab. Zwei Formen, weil `token-verteilen.sh datei` die .env-Form schreibt und
# der Windows-Weg die nackte. Eine Fehlbedienung hier waere sonst ein Token
# mit 16 Zeichen Praefix -- und damit ein 401, das nach einem falschen Token
# aussieht statt nach einem falsch gelesenen.
token_lesen() {
  head -1 "$TOKENDATEI" | tr -d '\r\n' | sed 's/^KG_MIRROR_TOKEN=//'
}

# --- Nur nachsehen ----------------------------------------------------------
# Ein BERICHT, kein Tor: es laeuft bis zur letzten Zeile durch und sagt zu
# jeder Gegenstelle, ob sie da ist. Wer am Morgen prueft, will alle Zeilen
# sehen und nicht nach der ersten stehenbleiben.
#
# 🔴 Ausschliesslich LESEND. Kein `POST`, nichts unter `/ingest/` -- ein
# Probe-Upload wuerde den Stand des Tages auf dem oeffentlichen Server
# ersetzen (`mirror/receiver.py`: jede Aufnahme ist ein vollstaendiger Ersatz).
# `tests/test_spiegel_start_mac.py::test_er_veroeffentlicht_beim_pruefen_nichts`
# haelt das fest.
if [ "${1:-}" = "--pruefen" ]; then
  echo ""
  echo "Spiegel-Uploader — Pruefung (es wird nichts gesendet)"
  echo ""

  if [ ! -f "$TOKENDATEI" ]; then
    fehlt_token
    exit 1
  fi

  # Ueber das Token wird berichtet, nicht aus ihm zitiert: Laenge und ein
  # kurzer Fingerabdruck unterscheiden zwei Token zuverlaessig und verraten
  # keines (dasselbe Muster wie `scripts/token-verteilen.sh pruefen`).
  T=$(token_lesen)
  if [ -z "$T" ]; then
    rot "  ✗ Token       $TOKENDATEI ist leer"
    exit 1
  fi
  printf '  ✓ %-11s %s Zeichen, Fingerabdruck %s, Rechte %s\n' \
    "Token" "${#T}" \
    "$(printf '%s' "$T" | shasum -a 256 | cut -c1-12)" \
    "$(stat -f '%Lp' "$TOKENDATEI")"
  unset T

  for paar in "Kern|$KG_TOOL1_URL/graph.json" "Traum|$KG_TOOL2_URL/api/state"; do
    name="${paar%%|*}"; url="${paar#*|}"
    if curl -fsS -o /dev/null --max-time "$PRUEF_TIMEOUT" "$url" 2>/dev/null; then
      printf '  ✓ %-11s %s\n' "$name" "$url"
    else
      rot "  ✗ $name antwortet nicht: $url"
      grau "      Dann fehlt dem Spiegel genau dieser Teil -- der andere geht"
      grau "      trotzdem hoch (Tool 1 und Tool 2 fallen unabhaengig aus)."
    fi
  done

  # `/healthz` ist die einzige Adresse, die ohne Token etwas ueber den Stand
  # sagt. `graph_age_s: null` heisst: seit dem Start des Dienstes ist dort
  # nichts eingegangen.
  antwort=$(curl -fsS --max-time "$PRUEF_TIMEOUT" "$KG_MIRROR_URL/healthz" 2>/dev/null)
  if [ -n "$antwort" ]; then
    printf '  ✓ %-11s %s\n' "Spiegel" "$KG_MIRROR_URL"
    grau "      $antwort"
    grau "      graph_age_s ueber 90 heisst: dort steht ein alter Stand."
  else
    rot "  ✗ Spiegel antwortet nicht: $KG_MIRROR_URL/healthz"
    grau "      Venue-WLAN, DNS, oder der Empfaenger auf herkules liegt."
  fi

  echo ""
  grau "  Starten:  ./scripts/spiegel-start-mac.sh"
  echo ""
  exit 0
fi

# --- Der Betrieb ------------------------------------------------------------

if [ ! -f "$TOKENDATEI" ]; then
  fehlt_token
  exit 1
fi

# Das Token wandert von hier aus ausschliesslich in die Umgebung DIESES einen
# Prozesses. Nicht `export` in der Shell, nicht auf einer Kommandozeile (dort
# stuende es in jeder Prozessliste), nicht in eine Logdatei.
KG_MIRROR_TOKEN=$(token_lesen)
if [ -z "$KG_MIRROR_TOKEN" ]; then
  rot "FEHLER: $TOKENDATEI ist leer."
  echo "        Neu holen: scripts/token-verteilen.sh datei ~/.kg-mirror-token"
  exit 1
fi
export KG_MIRROR_TOKEN KG_MIRROR_URL KG_TOOL1_URL KG_TOOL2_URL KG_MIRROR_INTERVAL

mkdir -p "$HOME/kg-logs"
LOG="$HOME/kg-logs/spiegel.log"

echo ""
echo "Spiegel-Uploader — schiebt den Stand nach draussen"
echo "  Ziel:    $KG_MIRROR_URL"
echo "  Quelle:  $KG_TOOL1_URL (Kern)  und  $KG_TOOL2_URL (Traum)"
echo "  Takt:    alle ${KG_MIRROR_INTERVAL} s"
echo "  Log:     $LOG"
echo ""
grau "  Beenden mit Strg-C. Das Fenster darf den ganzen Tag offen bleiben."
grau "  Je Runde steht hier eine Zeile, WENN etwas schiefgeht -- Stille ist"
grau "  der Normalfall. Was schon oben liegt, merkt sich"
grau "  mirror/mirror-uploaded.json (loeschen erzwingt alle Bilder neu)."
echo ""

# Kein `exec … | tee`: eine Pipeline laeuft in einer Subshell, `exec` ersetzt
# dann nicht diese Shell, und der Exit-Code waere der von `tee` (immer 0) --
# ein abgestuerzter Dienst saehe aus wie ein sauberes Ende. Dieselbe Falle wie
# in `scripts/start-stt-mac.sh`.
set -o pipefail
uv run python -m mirror.uploader 2>&1 | tee -a "$LOG"
CODE=${PIPESTATUS[0]}

echo ""
if [ "$CODE" -ne 0 ]; then
  rot "🔴 Der Uploader ist mit Code $CODE beendet."
  echo "   Der Spiegel zeigt ab jetzt einen einfrierenden Stand und sagt das"
  echo "   den Besucherinnen nach 90 s auch an. Log: $LOG"
else
  echo "Uploader beendet. Der Spiegel behaelt den zuletzt gesendeten Stand."
fi
exit "$CODE"
