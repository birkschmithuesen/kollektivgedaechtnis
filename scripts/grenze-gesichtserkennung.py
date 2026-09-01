"""Misst die GRENZE der Haar-Kaskade, statt sie zu behaupten.

Der Handoff sagt: "findet nur frontale Gesichter, Halbprofil faellt durch".
Das ist bisher eine Behauptung aus der Literatur, keine Messung an diesem
Bestand. Hier wird sie geprueft -- und zwar ohne neue Fotos, weil die
vorhandenen reichen, um zwei Fragen deterministisch zu beantworten:

1. AB WELCHEM NEIGUNGSWINKEL faellt ein Gesicht durch? Jedes Foto wird in
   Schritten gedreht und erneut vorgelegt. Das simuliert den geneigten Kopf,
   den die Kaskade nicht mag. Ergebnis ist ein Winkel in Grad, keine Vermutung.

2. HILFT EINE ZWEITE KASKADE? Neben `frontalface_default` liegen
   `frontalface_alt2` und `profileface` im selben Ordner -- kostenlos,
   ohne dlib, ohne Installation. Gemessen wird, ob sie Treffer liefern, wo die
   erste Kaskade durchfaellt.

Es werden ausschliesslich Zahlen ausgegeben, keine Bildinhalte.

Aufruf auf der Station:
    C:\\Users\\birk\\kollektivgedaechtnis\\.venv\\Scripts\\python.exe ^
        grenze-gesichtserkennung.py C:\\Users\\birk\\kollektivgedaechtnis\\data\\photos
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\birk\kollektivgedaechtnis")

BILDENDUNGEN = {".jpg", ".jpeg", ".png"}
WINKEL = [0, 5, 10, 15, 20, 25, 30, 40, 50]
KASKADEN = [
    "haarcascade_frontalface_default.xml",  # die aktuell benutzte
    "haarcascade_frontalface_alt2.xml",     # Alternative, gleiche Familie
    "haarcascade_profileface.xml",          # fuer Halbprofil gedacht
]


def finde(kaskade, cv2, np, bild) -> list:
    """Ruft die Kaskade mit DENSELBEN Parametern wie kg/photos.py auf."""
    grau = cv2.cvtColor(np.array(bild), cv2.COLOR_RGB2GRAY)
    mindest = max(30, int(min(bild.size) * 0.08))
    return list(kaskade.detectMultiScale(grau, scaleFactor=1.1, minNeighbors=5,
                                         minSize=(mindest, mindest)))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("ordner")
    p.add_argument("--json", dest="json_pfad", default=None)
    args = p.parse_args()

    import cv2
    import numpy as np
    from PIL import Image, ImageOps

    basis = Path(cv2.data.haarcascades)
    kaskaden = {}
    for name in KASKADEN:
        k = cv2.CascadeClassifier(str(basis / name))
        if k.empty():
            print(f"WARNUNG: {name} laedt nicht -- uebersprungen")
            continue
        kaskaden[name] = k

    ordner = Path(args.ordner)
    bilder = sorted(b for b in ordner.iterdir() if b.suffix.lower() in BILDENDUNGEN)

    print(f"Grenzmessung Gesichtserkennung -- {len(bilder)} Fotos, "
          f"{len(WINKEL)} Neigungen, {len(kaskaden)} Kaskaden")
    print("=" * 78)

    ergebnisse = []
    for bild in bilder:
        with Image.open(bild) as roh:
            original = ImageOps.exif_transpose(roh).convert("RGB")
        # Grosse Fotos verkleinern: die Kaskade skaliert ohnehin, und ein
        # 3024x4032-Bild neunmal zu drehen dauert sonst Minuten.
        if max(original.size) > 1600:
            original.thumbnail((1600, 1600))

        zeile = {"datei": bild.name, "groesse": list(original.size), "winkel": {}}
        for grad in WINKEL:
            # expand=True, damit beim Drehen keine Bildecken abgeschnitten
            # werden -- sonst misst man das Beschneiden statt der Neigung.
            gedreht = original.rotate(grad, expand=True, fillcolor=(0, 0, 0)) if grad else original
            pro_kaskade = {}
            for name, k in kaskaden.items():
                pro_kaskade[name] = len(finde(k, cv2, np, gedreht))
            zeile["winkel"][grad] = pro_kaskade
        ergebnisse.append(zeile)

        kurz = " ".join(
            f"{g}:{zeile['winkel'][g]['haarcascade_frontalface_default.xml']}"
            for g in WINKEL)
        print(f"{bild.name:<26} default je Winkel -> {kurz}")

    # --- Auswertung: die beiden Fragen beantworten, im Code, nicht im Kopf ---
    print("=" * 78)
    haupt = "haarcascade_frontalface_default.xml"

    print("Frage 1: ab welchem Winkel faellt das Gesicht durch?")
    grenzen = []
    for z in ergebnisse:
        if z["winkel"][0][haupt] == 0:
            print(f"  {z['datei']:<26} schon bei 0 Grad kein Treffer")
            continue
        letzter = 0
        for g in WINKEL:
            if z["winkel"][g][haupt] > 0:
                letzter = g
            else:
                break
        grenzen.append(letzter)
        print(f"  {z['datei']:<26} haelt bis {letzter} Grad")
    if grenzen:
        print(f"  -> Bestand: schlechtester {min(grenzen)} Grad, "
              f"bester {max(grenzen)} Grad")

    print()
    print("Frage 2: bringt eine zweite Kaskade Treffer, wo die erste nichts findet?")
    for name in kaskaden:
        if name == haupt:
            continue
        gerettet = 0
        gesamt_luecken = 0
        for z in ergebnisse:
            for g in WINKEL:
                if z["winkel"][g][haupt] == 0:
                    gesamt_luecken += 1
                    if z["winkel"][g][name] > 0:
                        gerettet += 1
        anteil = (gerettet / gesamt_luecken * 100) if gesamt_luecken else 0
        print(f"  {name:<38} {gerettet}/{gesamt_luecken} Luecken gefuellt ({anteil:.0f} %)")

    if args.json_pfad:
        Path(args.json_pfad).write_text(
            json.dumps({"winkel": WINKEL, "kaskaden": list(kaskaden),
                        "ergebnisse": ergebnisse}, indent=2, ensure_ascii=False),
            encoding="utf-8")
        print(f"\nJSON: {args.json_pfad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
