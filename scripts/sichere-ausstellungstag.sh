#!/usr/bin/env bash
# Ausstellungsdaten eines Tages sichern: Ausstellungsrechner -> vServer -> Nextcloud.
#
# Warum dieser Umweg: Der Ausstellungsrechner hat bewusst KEINE
# Nextcloud-Zugangsdaten (er bekommt nur die Schlüssel, die er im Betrieb
# braucht). rclone ist auf dem vServer eingerichtet, also läuft der Transfer
# dort durch. Direkt vom Rechner in die Cloud ginge nur, wenn wir ihm
# Credentials geben — will man nicht.
#
# Aufruf AUF DEM VSERVER, nach dem Ausstellungstag:
#
#     scripts/sichere-ausstellungstag.sh 2026-09-02 birk@192.168.1.42
#
# Erst wenn "0 differences" bestätigt ist, darf lokal gelöscht werden. Diese
# Aufnahmen gibt es genau einmal.
set -euo pipefail

TAG=${1:?"Datum des Ausstellungstags, z.B. 2026-09-02"}
RECHNER=${2:?"user@host des Ausstellungsrechners"}
FERNPFAD=${3:-"~/kollektivgedaechtnis"}

ZIEL="hermes-vault:Hermes-Agent/RoboCloud/NewBauhaus-2026-Interviews/$TAG"
STAGE="$HOME/tmp/nb-$TAG"

if ! [[ "$TAG" =~ ^2[0-9]{3}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "FEHLER: '$TAG' ist kein Datum der Form YYYY-MM-DD" >&2
  exit 1
fi

echo "=== 1/4  Vom Ausstellungsrechner holen ==========================="
mkdir -p "$STAGE"
# -a erhält Zeitstempel: bei Aufnahmen ist die Uhrzeit ein Teil der Daten.
rsync -a --info=progress2 "$RECHNER:$FERNPFAD/data/"       "$STAGE/"
rsync -a --info=progress2 "$RECHNER:$FERNPFAD/dream-data/" "$STAGE/dream/"

echo
echo "=== 2/4  Was wurde geholt? ======================================="
du -sh "$STAGE"
find "$STAGE" -maxdepth 2 -type d | sed "s|$STAGE|  .|"
if [ ! -s "$STAGE/kg.db" ]; then
  echo "WARNUNG: kg.db fehlt oder ist leer — lief die Station an diesem Tag?" >&2
fi

echo
echo "=== 3/4  In die Nextcloud schieben ==============================="
rclone copy "$STAGE" "$ZIEL" --progress

echo
echo "=== 4/4  Gegenprüfen (Pflicht, vor jedem Löschen) ================"
if rclone check "$STAGE" "$ZIEL" --one-way; then
  echo
  echo "OK — vollständig angekommen unter:"
  echo "  $ZIEL"
  echo
  echo "Die lokale Kopie liegt noch unter $STAGE."
  echo "Löschen ERST, wenn die Daten in der Nextcloud sichtbar sind:"
  echo "  rm -rf $STAGE"
else
  echo
  echo "FEHLER: Unterschiede gefunden. NICHTS löschen, Transfer wiederholen." >&2
  exit 1
fi
