"""Beantwortet die Frage, die ueber die App entscheidet: kostet das
Verkleinern auf 1024 px Treffer?

Anlass (gemessen 2026-09-01): In `1788261234_app754.jpg` (3024x4032) findet
die Kaskade im Original ein Gesicht, nach dem Verkleinern auf 1024 px keines.
Die App verkleinert JEDES Foto auf 1024 px lange Kante (`Bildbytes.MAX_KANTE`)
-- also trifft dieser Effekt den Regelbetrieb, nicht einen Sonderfall.

Der Verdacht ist nicht "kleiner = schlechter": die Trefferzahl sprang
1,0,0,0,1,0,1 ueber die Stufen. Das riecht nach der `minSize`-Kopplung in
`kg/photos.py`:

    mindest = max(30, int(min(bild.size) * 0.08))

`minSize` haengt an der BILDGROESSE. Beim Verkleinern schrumpfen Gesicht UND
Mindestgroesse gemeinsam -- das allein erklaert kein Kippen. Wohl aber die
Sprungstellen der Skalenpyramide: `detectMultiScale` prueft Fenster in
Schritten von `scaleFactor=1.1`, und ein Gesicht kann zwischen zwei Stufen
fallen. Genau das wird hier ueber den ganzen Bestand ausgezaehlt, statt an
einem Foto geraten zu werden.

Ausgegeben werden nur Zahlen.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\birk\kollektivgedaechtnis")

BILDENDUNGEN = {".jpg", ".jpeg", ".png"}
# Die Stufen um 1024 herum eng, damit die Sprungstelle sichtbar wird.
STUFEN = [None, 2048, 1600, 1280, 1024, 900, 800, 640, 512]


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

    print("Aufloesungsreihe ueber den ganzen Bestand")
    print("Frage: kostet das Verkleinern auf 1024 px (App-Vorgabe) Treffer?")
    print("=" * 88)
    kopf = "".join(f"{('orig' if s is None else s):>7}" for s in STUFEN)
    print(f"{'datei':<26}{kopf}")

    zeilen = []
    for bild_pfad in bilder:
        with Image.open(bild_pfad) as roh:
            original = ImageOps.exif_transpose(roh).convert("RGB")

        treffer_je_stufe = {}
        for stufe in STUFEN:
            bild = original.copy()
            if stufe is not None:
                bild.thumbnail((stufe, stufe))
            grau = cv2.cvtColor(np.array(bild), cv2.COLOR_RGB2GRAY)
            mindest = max(30, int(min(bild.size) * 0.08))
            treffer = kaskade.detectMultiScale(grau, scaleFactor=1.1, minNeighbors=5,
                                               minSize=(mindest, mindest))
            treffer_je_stufe["orig" if stufe is None else str(stufe)] = len(treffer)

        zeilen.append({"datei": bild_pfad.name,
                       "original": list(original.size),
                       "treffer": treffer_je_stufe})
        werte = "".join(f"{treffer_je_stufe['orig' if s is None else str(s)]:>7}"
                        for s in STUFEN)
        print(f"{bild_pfad.name:<26}{werte}")

    # --- Auswertung im Code ---
    print("=" * 88)
    schluessel = ["orig" if s is None else str(s) for s in STUFEN]
    print("Fotos mit mindestens einem Treffer, je Stufe:")
    quoten = {}
    for s in schluessel:
        mit = sum(1 for z in zeilen if z["treffer"][s] > 0)
        quoten[s] = mit
        print(f"  {s:>6}: {mit}/{len(zeilen)}")

    print()
    print("Kippt ein Foto zwischen Original und 1024?")
    kipper = [z for z in zeilen if z["treffer"]["orig"] > 0 and z["treffer"]["1024"] == 0]
    gewinner = [z for z in zeilen if z["treffer"]["orig"] == 0 and z["treffer"]["1024"] > 0]
    for z in kipper:
        print(f"  VERLOREN durch Verkleinern: {z['datei']} "
              f"({z['original'][0]}x{z['original'][1]})")
    for z in gewinner:
        print(f"  ERST durch Verkleinern gefunden: {z['datei']}")
    if not kipper and not gewinner:
        print("  keines -- das Verkleinern ist an diesem Bestand folgenlos")

    print()
    nicht_monoton = []
    for z in zeilen:
        folge = [z["treffer"][s] for s in schluessel]
        # Nicht monoton = die Trefferzahl faellt und steigt wieder. Das ist der
        # Beleg dafuer, dass NICHT die Aufloesung entscheidet, sondern wo das
        # Gesicht in die Skalenpyramide faellt.
        binaer = [1 if t > 0 else 0 for t in folge]
        if 1 in binaer and 0 in binaer:
            erste_eins = binaer.index(1)
            if 0 in binaer[erste_eins:] and 1 in binaer[binaer.index(0, erste_eins):]:
                nicht_monoton.append(z["datei"])
    print(f"Fotos mit springender (nicht monotoner) Erkennung: {len(nicht_monoton)}")
    for d in nicht_monoton:
        print(f"  {d}")

    if args.json_pfad:
        Path(args.json_pfad).write_text(
            json.dumps({"stufen": schluessel, "quoten": quoten, "zeilen": zeilen},
                       indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nJSON: {args.json_pfad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
