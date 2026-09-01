#!/usr/bin/env python3
"""Erzeugt den QR-Code für die Wand — einmal, als Datei.

Aufruf (aus dem Repo-Wurzelverzeichnis):

    uv run --with segno python scripts/qr-erzeugen.py

Warum ein SKRIPT und keine Bibliothek in der Wandseite (Handoff, Punkt 3):
Der Code ist statisch — die Adresse ändert sich während des Festivals nicht.
Eine QR-Bibliothek in `projection.html` zu laden hieße, auf einer
unbeaufsichtigten Wand bei jedem Seitenaufbau etwas zu rechnen, das sich nie
ändert, und einen weiteren Weg zu haben, auf dem die Wand scheitern kann.

Deshalb ist `segno` auch KEINE Laufzeit-Abhängigkeit der Station: Es wird
einmal beim Erzeugen gebraucht, die Wand liefert danach nur noch die fertige
SVG-Datei aus. `pyproject.toml` bleibt unangetastet; `--with segno` holt es
für genau diesen Aufruf.

🔴 Warum nicht selbst kodieren: Genau das wurde am 2026-09-01 versucht und
verworfen. Ein handgeschriebener Encoder (Byte-Modus, Stufe M, Version 1–10)
stimmte nach zwei Fehlerbehebungen bei GENAU EINER Adresse bit-identisch mit
der Referenz überein — und bei 8 von 9 anderen Testfällen nicht. Ein QR-Code,
der fast richtig ist, sieht aus wie ein QR-Code und wird von keinem Telefon
gelesen; auf der Wand fiele das erst auf, wenn Besucher davorstehen. `segno`
ist reines Python (506 KB, keine C-Abhängigkeit) und damit auch auf der
offlinefähigen Station unproblematisch.

🔴 Die Adresse ist `kollektivgedaechtnis.flashclash.de` (Birk, 2026-09-01
ausdrücklich bestätigt). NICHT `kollektivtraum.flashclash.de` — dieser Name
war einmal im Gespräch, hat aber kein Zertifikat; ein QR-Code darauf ergäbe
auf jedem Telefon einen Sicherheitswarn-Bildschirm statt der Seite.
"""

from __future__ import annotations

from pathlib import Path

import segno

ADRESSE = "https://kollektivgedaechtnis.flashclash.de"
ZIEL = Path(__file__).resolve().parent.parent / "frontend" / "static" / "qr-handyseite.svg"

# Fehlerkorrektur M (~15 %): Der Code hängt an einer Wand und wird aus einigen
# Metern Entfernung schräg fotografiert. L wäre knapp, Q und H machen den Code
# dichter und damit aus der Entfernung schlechter lesbar — bei gleicher
# Anzeigegröße zählt die Modulgröße mehr als die Reserve.
STUFE = "m"

# Ruhezone: vier Module an jeder Seite sind Vorschrift. Ohne sie finden viele
# Leser den Code auf einer gemusterten Projektion nicht.
RUHEZONE = 4


def main() -> int:
    qr = segno.make(ADRESSE, error=STUFE, micro=False)

    ZIEL.parent.mkdir(parents=True, exist_ok=True)
    # SVG und nicht PNG: Die Wand läuft in 4K, und der Code wird vor Ort in
    # der Größe angepasst. Ein PNG müsste dafür in einer festen Auflösung
    # erzeugt werden und sähe bei jeder anderen Größe weich oder ausgefranst
    # aus; ein SVG ist an jeder Beamergröße scharf und als Datei kleiner.
    qr.save(
        ZIEL,
        kind="svg",
        border=RUHEZONE,
        dark="#000000",
        light="#ffffff",
        # Ohne XML-Deklaration und Namespace-Präfix: Die Datei wird als
        # <img>-Quelle eingebunden, nicht als eigenständiges Dokument.
        xmldecl=False,
        svgns=True,
        nl=True,
    )

    print(f"Adresse : {ADRESSE}")
    print(f"Version : {qr.version} ({qr.symbol_size()[0]}x{qr.symbol_size()[1]} px bei Skalierung 1)")
    print(f"Stufe   : {qr.error.upper()}  Maske: {qr.mask}")
    print(f"Datei   : {ZIEL}")
    print(f"Bytes   : {ZIEL.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
