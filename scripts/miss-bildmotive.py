#!/usr/bin/env python3
"""Zaehlt, welche Motive in den Bildbeschreibungen wiederkehren — und ob sie
im Material standen oder erfunden wurden.

🔴 WARUM ES DIESES SKRIPT GIBT (Birk, 2026-09-02, am Ausstellungstag):
„Es gab immer sehr klischeehafte Rollenbilder, fast immer Familie. Das konnte
ich so aus den Interviews nicht raushoeren."

Gemessen an den ersten 9 Traeumen des Tages: Kinder standen in 3 von 9
Prompts als Begriff — und erschienen in 7 von 9 Bildern. „Frau" 6/9 gegen
„Mann" 1/9.

Es gibt dieses Skript, weil eine Prompt-Aenderung sonst Glueckssache ist. Die
Pflichtbegriff-Auswahl war bis zum 2026-08-30 Prosa im Prompt und kippte an
EINEM Tag in beide Richtungen, je nachdem wie die Bitte formuliert war
(kg2/weighting.py::select_required). Wer den Prompt gegen Klischees aendert,
braucht dieselbe Disziplin: vorher messen, aendern, nachher messen.

Aufruf:
    uv run python scripts/miss-bildmotive.py
    uv run python scripts/miss-bildmotive.py --db dream-data/dreams.sqlite3 --seit 2026-09-02
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sqlite3
import sys
from pathlib import Path

#: Was gezaehlt wird. Zwei Sorten, und die Trennung ist der Punkt:
#: MENSCHEN sind das, was das Modell erfindet, wenn es Personal braucht;
#: FORM ist die Bildsprache, die sich wiederholt, ohne dass jemand sie wollte.
#: 🔴 ZWEI MUSTER JE GRUPPE, und daran haengt der ganze Nutzen des Skripts.
#: Die Bildbeschreibung ist ENGLISCH, das Material im Prompt ist DEUTSCH. Die
#: erste Fassung verglich beide mit demselben englischen Muster und meldete
#: darum „Kinder: 7 von 7 ohne Grundlage" — obwohl in drei Prompts der Begriff
#: „Kinder als Akteure der Entwicklung" stand. Ein Messwerkzeug, das den
#: gesuchten Befund selbst herstellt, ist schlimmer als keins.
MENSCHEN = {
    "Familie": (r"\bfamil", r"famili"),
    "Kinder": (r"\bchild|\btoddler|\bkids?\b", r"\bkind"),
    "Frau": (r"\bwoman\b|\bwomen\b", r"\bfrau"),
    "Mann": (r"\bman\b|\bmen\b", r"\bmann|\bmaenner|\bmänner"),
    "aeltere Menschen": (
        r"older wom|older man|elderly|grandmoth|grandfath",
        r"\balt|\bsenior|\brentner|generation",
    ),
}
FORM = {
    "Haende": r"\bhands?\b",
    "Blick von oben": r"from an? (upper|second|first|third|low)|looks? down|window, one looks",
    "Schild mit Text": r"German text reading|text reads|reading \"",
    "Wiese/Brache": r"\bmeadow\b|unmown|overgrown",
}


def hole(db: Path, seit: float | None) -> list[tuple[str, str, str]]:
    """(id, image_description, stage1_prompt) je verwendetem Traum."""
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        sql = (
            "select id, image_description, coalesce(stage1_prompt,'') from dream "
            "where discarded=0 and image_description is not null"
        )
        werte: tuple = ()
        if seit is not None:
            sql += " and created_at >= ?"
            werte = (seit,)
        return list(conn.execute(sql + " order by created_at", werte))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default="dream-data/dreams.sqlite3", type=Path)
    p.add_argument("--seit", help="nur Traeume ab diesem Tag, YYYY-MM-DD")
    args = p.parse_args()

    if not args.db.exists():
        print(f"FEHLER: {args.db} gibt es nicht.", file=sys.stderr)
        return 2

    seit = None
    if args.seit:
        seit = dt.datetime.strptime(args.seit, "%Y-%m-%d").timestamp()

    zeilen = hole(args.db, seit)
    if not zeilen:
        print("Keine Bildbeschreibungen gefunden.")
        return 0

    n = len(zeilen)
    print(f"{n} Bildbeschreibungen aus {args.db}\n")

    for titel, gruppe, mit_beleg in (
        ("MENSCHEN — wer taucht auf", MENSCHEN, True),
        ("FORM — welche Bildsprache wiederholt sich", FORM, False),
    ):
        print(titel)
        for name, muster in gruppe.items():
            im_bild, im_material = muster if isinstance(muster, tuple) else (muster, muster)
            treffer = [z for z in zeilen if re.search(im_bild, z[1], re.I)]
            zeile = f"  {name:18s} {len(treffer)}/{n}  {'#' * len(treffer)}"
            if mit_beleg:
                # 🔴 Der eigentliche Befund steht in DIESER Spalte: nicht „wie
                # oft kommt es vor", sondern „wie oft kommt es vor, OHNE dass
                # das Material es hergab". Ein Bild mit Kindern ist kein
                # Klischee, wenn jemand ueber Kinder gesprochen hat.
                erfunden = sum(1 for z in treffer if not re.search(im_material, z[2], re.I))
                zeile += f"   davon ohne Grundlage im Material: {erfunden}"
            print(zeile)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
