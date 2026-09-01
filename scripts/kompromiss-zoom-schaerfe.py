"""Sucht den Kompromiss zwischen Zoom aufs Gesicht und Schaerfe.

Birk am Material, 2026-09-01, an einem Foto mit drei Personen: *„waren alle
drei Gesichter drauf, nicht auf das zentrale Gesicht gezoomed"*.

Ursache ist die Untergrenze von heute Mittag: `MINDEST_AUSSCHNITT = 512`
weitet JEDEN Ausschnitt unter 512 px auf -- auch dort, wo gar kein Matsch
drohte. Gemessen an seinem Foto: Gesicht 201 px, Ausschnitt 402 px, aufgeweitet
auf 512. Die Hochrechnung waere nur 1,27x gewesen (kaum sichtbar), der
Zoomverlust ist dagegen deutlich.

Die Untergrenze war also zu grob: sie behandelt 1,27x wie 4,2x. Richtiger ist
eine Grenze fuer die HOCHRECHNUNG selbst -- bis zu einem Faktor wird gezoomt,
darueber wird aufgeweitet. Diese Zahl wird hier gesucht, nicht geraten.

Gemessen wird je Kandidat:
  * wieviel Zoom bleibt (Ausschnitt gegen den ungebremsten Wunschausschnitt)
  * wie scharf das FERTIGE Portrait wird (durch make_portrait, mit Maske)

Ausgegeben werden nur Zahlen.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\birk\kollektivgedaechtnis")

BILDENDUNGEN = {".jpg", ".jpeg", ".png"}
# Kandidaten: bis zu welchem Faktor darf make_portrait hochrechnen?
# 1.0 = die heutige harte Untergrenze (nie hochrechnen)
FAKTOREN = [1.0, 1.3, 1.5, 1.8, 2.0, 99.0]  # 99 = gar keine Grenze (Zustand vor heute)
ZIEL = 512


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("ordner")
    p.add_argument("--json", dest="json_pfad", default=None)
    args = p.parse_args()

    import cv2
    import numpy as np
    from PIL import Image, ImageOps

    from kg import photos

    ordner = Path(args.ordner)
    bilder = sorted(b for b in ordner.iterdir() if b.suffix.lower() in BILDENDUNGEN)

    print("Kompromiss Zoom gegen Schaerfe")
    print(f"portrait_size {ZIEL}, GESICHTS_ZOOM {photos.GESICHTS_ZOOM}")
    print("Faktor = wieviel Hochrechnung erlaubt ist, bevor aufgeweitet wird")
    print("=" * 92)

    zeilen = []
    for bild_pfad in bilder:
        with Image.open(bild_pfad) as roh:
            bild = ImageOps.exif_transpose(roh).convert("RGB")
        breite, hoehe = bild.size

        gesicht = photos._gesicht_finden(bild)
        if gesicht is None:
            continue
        gx, gy, gw, gh = (int(v) for v in gesicht)
        # Der ungebremste Wunsch: so wollte der Zuschnitt sein, bevor irgendeine
        # Grenze eingreift. Alles Weitere wird DARAN gemessen.
        wunsch = min(int(round(gw * photos.GESICHTS_ZOOM)), breite, hoehe)

        eintrag = {"datei": bild_pfad.name, "gesicht": gw, "wunsch": wunsch,
                   "bild": [breite, hoehe], "kandidaten": {}}

        print(f"\n{bild_pfad.name}  Gesicht {gw} px, Wunschausschnitt {wunsch} px")
        print(f"  {'Faktor':>8}{'Ausschnitt':>12}{'Zoom bleibt':>13}"
              f"{'Hochrechnung':>14}{'Schaerfe':>10}")

        for faktor in FAKTOREN:
            # Erlaubt ist ein Ausschnitt bis herunter zu ZIEL/faktor.
            mindest = int(round(ZIEL / faktor))
            seite = min(max(wunsch, mindest), breite, hoehe)

            # Das Portrait wirklich bauen, statt die Schaerfe zu schaetzen:
            # Maske und Ring senken sie systematisch, eine Rechnung am nackten
            # Zuschnitt waere nicht vergleichbar (der Fehler von heute Mittag).
            alt = photos.MINDEST_AUSSCHNITT
            photos.MINDEST_AUSSCHNITT = mindest
            try:
                ziel_datei = Path(rf"C:\Users\SF-Tracking\kg-start\_kompromiss.png")
                photos.make_portrait(bild_pfad, ziel_datei, ZIEL)
            finally:
                photos.MINDEST_AUSSCHNITT = alt

            with Image.open(ziel_datei) as pim:
                hg = Image.new("RGB", pim.size, (0, 0, 0))
                rgba = pim.convert("RGBA")
                hg.paste(rgba, (0, 0), rgba)
            grau = cv2.cvtColor(np.array(hg), cv2.COLOR_RGB2GRAY)
            schaerfe = float(cv2.Laplacian(grau, cv2.CV_64F).var())

            zoom_bleibt = wunsch / seite * 100      # 100 % = voller Zoom erhalten
            hochrechnung = ZIEL / seite             # >1 heisst hochgerechnet
            eintrag["kandidaten"][str(faktor)] = {
                "ausschnitt": seite, "zoom_prozent": round(zoom_bleibt, 1),
                "hochrechnung": round(hochrechnung, 2), "schaerfe": round(schaerfe, 1),
            }
            etikett = "ohne" if faktor > 90 else f"{faktor:.1f}x"
            print(f"  {etikett:>8}{seite:>12}{zoom_bleibt:>12.0f} %"
                  f"{hochrechnung:>13.2f}x{schaerfe:>10.1f}")
        zeilen.append(eintrag)

    print("\n" + "=" * 92)
    print("Lesart: 'Zoom bleibt 100 %' heisst, der Ausschnitt sitzt so eng am Gesicht")
    print("wie gewuenscht. Weniger heisst aufgeweitet -- mehr Umgebung, mehr Nachbarn.")
    if args.json_pfad:
        Path(args.json_pfad).write_text(
            json.dumps({"faktoren": FAKTOREN, "ziel": ZIEL, "zeilen": zeilen},
                       indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nJSON: {args.json_pfad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
