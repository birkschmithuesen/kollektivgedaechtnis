"""Prueft einen konkreten Fix, statt ihn zu empfehlen.

Befund 2026-09-01: Beim Verkleinern auf 1024 px (die Vorgabe der App,
`Bildbytes.MAX_KANTE`) verliert die Kaskade an diesem Bestand 2 von 5
erkannten Gesichtern.

Verdaechtig ist die Kopplung in `kg/photos.py`:

    mindest = max(30, int(min(bild.size) * 0.08))
    detectMultiScale(..., minSize=(mindest, mindest))

`minSize` ist an die Bildgroesse gebunden. Bei 3024x4032 verlangt das
Gesichter von mindestens 241 px -- bei 768x1024 nur noch 61 px. Die
Mindestgroesse wandert also mit, und zusammen mit `scaleFactor=1.1` kann ein
Gesicht zwischen zwei Stufen der Skalenpyramide durchfallen.

Hier wird gemessen, ob eine ENTKOPPELTE Mindestgroesse (fester Anteil der
Bildhoehe statt der kurzen Kante, bzw. schlicht 30 px) die verlorenen Treffer
zurueckholt -- und ob sie anderswo Fehltreffer erzeugt. Beides zaehlt: ein
Fix, der die Trefferquote hebt und dafuer Schultern fuer Gesichter haelt,
waere keiner.

Ausgegeben werden nur Zahlen.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\birk\kollektivgedaechtnis")

BILDENDUNGEN = {".jpg", ".jpeg", ".png"}

# Die Varianten, die verglichen werden. Der Name ist die Beschriftung.
VARIANTEN = {
    "jetzt (8% kurze Kante)": lambda b: max(30, int(min(b.size) * 0.08)),
    "4% kurze Kante": lambda b: max(30, int(min(b.size) * 0.04)),
    "fest 30 px": lambda b: 30,
    "fest 60 px": lambda b: 60,
}

# Gemessen wird am Original UND an 1024 px -- weil die App 1024 schickt und
# genau dort das Problem auftrat.
STUFEN = [None, 1024]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("ordner")
    p.add_argument("--json", dest="json_pfad", default=None)
    args = p.parse_args()

    import cv2
    import numpy as np
    from PIL import Image, ImageOps

    kaskade = cv2.CascadeClassifier(
        str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))

    ordner = Path(args.ordner)
    bilder = sorted(b for b in ordner.iterdir() if b.suffix.lower() in BILDENDUNGEN)

    print("Gegentest: haengt der Trefferverlust an der minSize-Kopplung?")
    print(f"{len(bilder)} Fotos, {len(VARIANTEN)} Varianten, Stufen: Original und 1024 px")
    print("=" * 92)

    zeilen = []
    for bild_pfad in bilder:
        with Image.open(bild_pfad) as roh:
            original = ImageOps.exif_transpose(roh).convert("RGB")

        eintrag = {"datei": bild_pfad.name, "original": list(original.size), "messung": {}}
        for stufe in STUFEN:
            bild = original.copy()
            if stufe is not None:
                bild.thumbnail((stufe, stufe))
            grau = cv2.cvtColor(np.array(bild), cv2.COLOR_RGB2GRAY)
            etikett = "orig" if stufe is None else str(stufe)
            eintrag["messung"][etikett] = {}
            for vname, regel in VARIANTEN.items():
                m = regel(bild)
                treffer = kaskade.detectMultiScale(grau, scaleFactor=1.1, minNeighbors=5,
                                                   minSize=(m, m))
                eintrag["messung"][etikett][vname] = {
                    "minSize": m,
                    "treffer": len(treffer),
                    "boxen": [[int(v) for v in t] for t in treffer],
                }
        zeilen.append(eintrag)

    # --- Tabelle: Trefferzahl je Variante, bei 1024 px (der App-Fall) ---
    print(f"{'datei':<26}" + "".join(f"{v[:20]:>22}" for v in VARIANTEN))
    print(f"{'(bei 1024 px)':<26}")
    for z in zeilen:
        werte = "".join(f"{z['messung']['1024'][v]['treffer']:>22}" for v in VARIANTEN)
        print(f"{z['datei']:<26}{werte}")

    print("-" * 92)
    print("Fotos mit Treffer, je Variante und Stufe:")
    zusammenfassung = {}
    for etikett in ("orig", "1024"):
        zusammenfassung[etikett] = {}
        for v in VARIANTEN:
            mit = sum(1 for z in zeilen if z["messung"][etikett][v]["treffer"] > 0)
            zusammenfassung[etikett][v] = mit
        werte = "  ".join(f"{v}: {zusammenfassung[etikett][v]}/{len(zeilen)}"
                          for v in VARIANTEN)
        print(f"  {etikett:>5}  {werte}")

    print()
    print("Mehrfachtreffer (Verdacht auf Fehltreffer) bei 1024 px:")
    for v in VARIANTEN:
        mehr = [(z["datei"], z["messung"]["1024"][v]["treffer"])
                for z in zeilen if z["messung"]["1024"][v]["treffer"] > 1]
        if mehr:
            print(f"  {v}: " + ", ".join(f"{d} ({n})" for d, n in mehr))
        else:
            print(f"  {v}: keine")

    print()
    jetzt = "jetzt (8% kurze Kante)"
    beste = max(VARIANTEN, key=lambda v: zusammenfassung["1024"][v])
    if zusammenfassung["1024"][beste] > zusammenfassung["1024"][jetzt]:
        print(f"-> Bei 1024 px findet '{beste}' "
              f"{zusammenfassung['1024'][beste]}/{len(zeilen)} statt "
              f"{zusammenfassung['1024'][jetzt]}/{len(zeilen)}.")
        print("   ACHTUNG: das ist ein Befund an 7 Fotos, keine belastbare Reihe.")
    else:
        print("-> Keine Variante schlaegt die aktuelle Regel an diesem Bestand.")

    if args.json_pfad:
        Path(args.json_pfad).write_text(
            json.dumps({"varianten": list(VARIANTEN), "zusammenfassung": zusammenfassung,
                        "zeilen": zeilen}, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nJSON: {args.json_pfad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
