#!/usr/bin/env bash
# Holt beim oeffentlichen Spiegel eingeworfene Fotos ab und gibt sie der Station.
#
# 🔴 WARUM ES DIESE DATEI GIBT (2026-09-02):
# Ein Handy OHNE Tailnet erreicht die Station nicht -- sie sitzt hinter
# Venue-NAT. Der Spiegel ist die einzige Stelle, die beide sehen: Das Foto
# liegt dort zwischen, und die Station HOLT es ab. Dieselbe Richtung wie beim
# Uploader daneben -- die Station spricht nach draussen, nie umgekehrt.
#
# `mirror/abholer.py` gibt es laengst und er funktioniert. Zum Starten gab es
# aber nur `mirror/abholer-start.bat`, den Windows-Weg von vor dem
# Rechnerwechsel am 2026-09-01 -- dieselbe Luecke wie beim Uploader.
#
# DER GANZE WEG IST AN DIESEM RECHNER DURCHGEMESSEN (2026-09-02, 07:15):
#   POST /ingest/photo (Foto-Token)     -> 200, liegt im Posteingang
#   Abholer: GET /eingang               -> die Datei
#   Abholer: POST /api/photo            -> 200
#   Abholer: DELETE /eingang/<datei>    -> quittiert
#   Station: p9 mit Foto UND Portrait; Posteingang danach leer
#
# 🔴 ER LAEUFT NICHT IM SAMMELSTART MIT.
# Anders als beim Uploader ist der Grund nicht der Datenschutz, sondern die
# BEFUGNIS: Der Abholer braucht das STARKE Uploader-Token und darf damit beim
# Spiegel loeschen. Ein Dienst, der loeschen darf, geht nicht als Nebenwirkung
# eines Startknopfs an. `tests/test_abholer_start_mac.py` haelt das fest.
#
# 🔴 UND ER BRAUCHT EIN OFFENES INTERVIEW. Seit dem 2026-09-01 weist die
# Station ein Foto ohne laufendes Interview ab (409) -- ein Portrait, das zu
# keiner Person gehoert, waere ein Gesicht auf der Platte, das niemand mehr
# zuordnen kann. Der Abholer merkt das nicht von sich aus; die abgewiesene
# Datei bleibt im Posteingang liegen und wird beim naechsten Versuch erneut
# zugestellt. Das ist richtig so, sieht im Log aber nach einer Schleife aus.
#
# Aufruf:
#     ./scripts/abholer-start-mac.sh
#     ./scripts/abholer-start-mac.sh --pruefen   # nur nachsehen, nichts holen
#
# Beenden: Strg-C in diesem Fenster.

set -u

KG_REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$KG_REPO" || exit 1

rot()  { printf '\033[31m%s\033[0m\n' "$*"; }
grau() { printf '\033[2m%s\033[0m\n' "$*"; }

# --- Das Token --------------------------------------------------------------
# Dieselbe Datei wie beim Uploader, und zwar mit Absicht: Es IST dasselbe
# Token. Der Abholer braucht das starke, nicht das Foto-Token -- abholen und
# quittieren darf nur die Station (mirror/abholer.py).
TOKENDATEI="${KG_TOKENDATEI:-$HOME/.kg-mirror-token}"
KG_MIRROR_URL="${KG_MIRROR_URL:-https://kollektivgedaechtnis.flashclash.de}"
KG_STATION_URL="${KG_STATION_URL:-http://127.0.0.1:8800}"
# 2 s, nicht die 3 des Uploaders: Hier haengt eine Wartezeit VOR der Wand dran
# (Birk: „das sollte ja schon relativ instantan gehen"), beim Uploader nur die
# Frische einer Anzeige. Begruendung und Messung in mirror/abholer.py.
KG_ABHOL_INTERVALL="${KG_ABHOL_INTERVALL:-2}"
PRUEF_TIMEOUT="${KG_ABHOL_PRUEF_TIMEOUT:-5}"

fehlt_token() {
  rot "FEHLER: $TOKENDATEI fehlt."
  echo "        Ohne Token antwortet der Spiegel auf jede Abfrage mit 401 --"
  echo "        den ganzen Tag lang, ohne dass ein Foto ankommt."
  echo ""
  echo "        Anlegen (der Wert kommt von herkules und wird nie ausgegeben):"
  echo "            scripts/token-verteilen.sh datei ~/.kg-mirror-token"
  echo ""
  echo "        Vorher pruefen, ob dort ueberhaupt eins liegt:"
  echo "            scripts/token-verteilen.sh pruefen"
}

# Schaelt ein evtl. vorangestelltes `KG_MIRROR_TOKEN=` ab: `token-verteilen.sh
# datei` schreibt die .env-Form, der Windows-Weg die nackte. Sonst waere ein
# Token mit 16 Zeichen Praefix unterwegs -- ein 401, das nach einem falschen
# Token aussieht statt nach einem falsch gelesenen.
token_lesen() {
  head -1 "$TOKENDATEI" | tr -d '\r\n' | sed 's/^KG_MIRROR_TOKEN=//'
}

# --- Nur nachsehen ----------------------------------------------------------
# Ein BERICHT, kein Tor: laeuft bis zur letzten Zeile durch und sagt zu jeder
# Gegenstelle, ob sie da ist.
#
# 🔴 Ausschliesslich LESEND. Der Abholer quittiert im Betrieb mit DELETE --
# eine Probe, die das tut, wuerde ein Foto wegwerfen, das noch niemand hat.
if [ "${1:-}" = "--pruefen" ]; then
  echo ""
  echo "Abholer — Pruefung (es wird nichts geholt und nichts geloescht)"
  echo ""
  if [ ! -f "$TOKENDATEI" ]; then
    fehlt_token
    exit 1
  fi
  TOKEN="$(token_lesen)"
  if [ -z "$TOKEN" ]; then
    rot "  Token: $TOKENDATEI ist leer."
    exit 1
  fi
  # Laenge und Fingerabdruck, nie der Wert.
  printf '  Token:    %s Zeichen, Fingerabdruck %s, Rechte %s\n' \
    "${#TOKEN}" "$(printf '%s' "$TOKEN" | shasum | cut -c1-8)" \
    "$(stat -f '%Lp' "$TOKENDATEI" 2>/dev/null || echo '?')"

  code=$(curl -s -o /dev/null -m "$PRUEF_TIMEOUT" -w "%{http_code}" "$KG_MIRROR_URL/healthz")
  [ "$code" = "200" ] && echo "  Spiegel:  $KG_MIRROR_URL — da (HTTP $code)" \
                      || rot "  Spiegel:  $KG_MIRROR_URL — HTTP $code"

  # Der Posteingang sagt, ob das starke Token wirklich gilt: 200 = ja,
  # 401 = das Token ist nicht das, fuer das wir es halten.
  code=$(curl -s -o /dev/null -m "$PRUEF_TIMEOUT" -w "%{http_code}" \
         -H "Authorization: Bearer $TOKEN" "$KG_MIRROR_URL/eingang")
  case "$code" in
    200) echo "  Posteingang: erreichbar, Token gilt" ;;
    401|403) rot "  Posteingang: HTTP $code — das Token wird nicht angenommen" ;;
    *)   rot "  Posteingang: HTTP $code" ;;
  esac

  code=$(curl -s -o /dev/null -m "$PRUEF_TIMEOUT" -w "%{http_code}" "$KG_STATION_URL/api/state")
  [ "$code" = "200" ] && echo "  Station:  $KG_STATION_URL — da" \
                      || rot "  Station:  $KG_STATION_URL — HTTP $code (laeuft sie?)"

  # Der Punkt, an dem am Ausstellungstag die Verwirrung entsteht.
  offen=$(curl -s -m "$PRUEF_TIMEOUT" "$KG_STATION_URL/api/state" 2>/dev/null \
          | tr ',' '\n' | grep -c '"interview": *null' || true)
  if [ "${offen:-0}" != "0" ]; then
    echo ""
    grau "  Hinweis: gerade laeuft kein Interview. Ein abgeholtes Foto wuerde"
    grau "  mit 409 abgewiesen und bliebe im Posteingang liegen."
  fi
  echo ""
  exit 0
fi

# --- Lauf -------------------------------------------------------------------
if [ ! -f "$TOKENDATEI" ]; then
  fehlt_token
  exit 1
fi
TOKEN="$(token_lesen)"
if [ -z "$TOKEN" ]; then
  rot "FEHLER: $TOKENDATEI ist leer."
  exit 1
fi

echo ""
echo "Abholer — Fotos vom Spiegel an die Station"
grau "  Spiegel:  $KG_MIRROR_URL"
grau "  Station:  $KG_STATION_URL"
grau "  Takt:     ${KG_ABHOL_INTERVALL} s"
grau "  Beenden:  Strg-C"
echo ""

# `exec`, damit Strg-C den Python-Prozess direkt trifft und nicht diese Shell
# stehenbleibt (dieselbe Ueberlegung wie in start-stt-mac.sh).
KG_MIRROR_URL="$KG_MIRROR_URL" \
KG_MIRROR_TOKEN="$TOKEN" \
KG_STATION_URL="$KG_STATION_URL" \
KG_ABHOL_INTERVALL="$KG_ABHOL_INTERVALL" \
exec uv run python -m mirror.abholer
