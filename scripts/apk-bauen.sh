#!/usr/bin/env bash
# Baut das APK auf herkules und liefert es aus -- ein Befehl statt fuenf.
#
# Anlass (2026-09-01/02): Dieselbe Kette wurde an einem Tag sechsmal von Hand
# getippt, und dabei ist dreimal etwas schiefgegangen:
#
#   * ein "--" im XML-Kommentar liess den Build erst nach zwei Minuten
#     scheitern (zweimal passiert) -> Schritt 1 prueft das lokal in Sekunden;
#   * ein APK wurde gebaut, aber nie in die RoboCloud gelegt, und lag damit
#     fuer kein Telefon erreichbar herum -> Schritt 5 macht das mit;
#   * ein Build entstand zwei Minuten VOR dem letzten Commit und trug
#     deshalb den alten Stand -> Schritt 2 warnt davor.
#
# Aufruf:
#     bash scripts/apk-bauen.sh 14        # baut v14
#
set -euo pipefail

VERSION="${1:?Aufruf: bash scripts/apk-bauen.sh <nummer>   (z. B. 14)}"
HERKULES="fundusbot@91.98.143.165"
FERN="~/kg-android"
ZIEL="out/kollektivgedaechtnis-foto-v${VERSION}.apk"
CLOUD="hermes-vault:Hermes-Agent/RoboCloud/NewBauhaus-2026-Interviews/"

cd "$(dirname "$0")/.."

echo "=== 1/5  Ressourcen pruefen (faengt das '--' im Kommentar)"
uv run python scripts/res-xml-pruefen.py

echo
echo "=== 2/5  Ist der Quellstand committet?"
if ! git diff --quiet -- android/ || ! git diff --cached --quiet -- android/; then
  echo "  ⚠ android/ hat uncommittete Aenderungen."
  echo "    Das APK traegt sie, die History nicht -- spaeter ist nicht mehr"
  echo "    nachvollziehbar, was in diesem Build steckt. Trotzdem weiter."
fi

echo
echo "=== 3/5  Bauen auf herkules (Tests laufen mit)"
rsync -a --delete --exclude build/ --exclude .gradle/ android/ "$HERKULES:$FERN/"
ssh "$HERKULES" "
  export JAVA_HOME=\$(ls -d ~/toolchains/jdk-17* | head -1)
  export PATH=\$JAVA_HOME/bin:\$PATH
  export ANDROID_HOME=\$HOME/toolchains/android-sdk
  cd $FERN && echo \"sdk.dir=\$ANDROID_HOME\" > local.properties
  ~/toolchains/gradle-8.9/bin/gradle --no-daemon testDebugUnitTest assembleRelease
" | grep -E "FAILED|error:|BUILD" || true

echo
echo "=== 4/5  Testergebnisse nachzaehlen (nicht aus 'BUILD SUCCESSFUL' schliessen)"
ssh "$HERKULES" "
  cd $FERN
  for f in app/build/test-results/testDebugUnitTest/*.xml; do
    grep -o 'tests=\"[0-9]*\" skipped=\"[0-9]*\" failures=\"[0-9]*\" errors=\"[0-9]*\"' \"\$f\" |
      head -1 | sed \"s|^|\$(basename \$f | sed 's/TEST-art.artesmobiles.kg.//;s/.xml//'): |\"
  done"

scp -q "$HERKULES:$FERN/app/build/outputs/apk/release/app-release.apk" "$ZIEL"
echo "  geholt: $ZIEL"

echo
echo "=== 5/5  Pruefen und ausliefern"
uv run python scripts/apk-layout-lesen.py "$ZIEL" | grep -E "Vorschau|Leuchte" || true
uv run python scripts/apk-zertifikat-lesen.py out/kollektivgedaechtnis-foto-v6.apk "$ZIEL" | tail -1

cp "$ZIEL" /tmp/
rclone copy "/tmp/$(basename "$ZIEL")" "$CLOUD"

FERN_SHA=$(rclone sha1sum "$CLOUD$(basename "$ZIEL")" | awk '{print $1}')
LOKAL_SHA=$(sha1sum "$ZIEL" | awk '{print $1}')
if [ "$FERN_SHA" = "$LOKAL_SHA" ]; then
  echo "  hochgeladen und geprueft: $LOKAL_SHA"
else
  echo "  🔴 SHA-1 stimmt NICHT: lokal $LOKAL_SHA, Cloud $FERN_SHA" >&2
  exit 1
fi
