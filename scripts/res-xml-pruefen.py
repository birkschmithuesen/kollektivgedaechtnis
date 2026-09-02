#!/usr/bin/env python3
"""Prueft alle Android-Ressourcen mit demselben strengen Parser wie der Build.

Warum es das gibt: Am 2026-09-02 ist ZWEIMAL dasselbe passiert -- ein "--" in
einem XML-Kommentar. Das ist in XML verboten, sieht aber voellig harmlos aus
(im Deutschen setzt man den Gedankenstrich genau so), und der Android-Build
meldet es erst nach gut zwei Minuten in `mergeDebugResources`. Zwei Minuten
Wartezeit fuer einen Tippfehler, der lokal in einer Sekunde auffaellt.

Aufruf vor jedem Bauen -- oder besser: von `scripts/apk-bauen.sh`, das es
selbst tut.

    uv run python scripts/res-xml-pruefen.py
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1] / "android" / "app" / "src" / "main" / "res"


def main() -> int:
    if not WURZEL.is_dir():
        print(f"Kein res-Verzeichnis unter {WURZEL}", file=sys.stderr)
        return 2

    kaputt = []
    geprueft = 0
    for datei in sorted(WURZEL.rglob("*.xml")):
        geprueft += 1
        try:
            ET.parse(datei)
        except ET.ParseError as fehler:
            kaputt.append((datei, fehler))

    for datei, fehler in kaputt:
        pfad = datei.relative_to(WURZEL.parents[3])
        print(f"FEHLER  {pfad}: {fehler}", file=sys.stderr)
        # Der haeufigste Fall beim Namen nennen, statt den Parser-Text
        # entziffern zu lassen.
        if "invalid token" in str(fehler):
            try:
                zeile = int(str(fehler).split("line ")[1].split(",")[0])
                inhalt = datei.read_text(encoding="utf-8").splitlines()[zeile - 1]
                if "--" in inhalt:
                    print(
                        "        Vermutlich ein '--' in einem Kommentar. "
                        "In XML verboten; im Deutschen durch ':' oder ',' ersetzen.",
                        file=sys.stderr,
                    )
            except (IndexError, ValueError, OSError):
                pass

    if kaputt:
        print(f"\n{len(kaputt)} von {geprueft} Dateien kaputt.", file=sys.stderr)
        return 1

    print(f"res-XML: {geprueft} Dateien, alle in Ordnung.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
