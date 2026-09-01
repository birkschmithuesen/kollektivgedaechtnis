"""Misst die SCHAERFE des fertigen Portraits, statt sie zu beurteilen.

Birk, 2026-09-01: die App soll nicht so stark verkleinern, weil das Portrait
auf der grossen Projektionsflaeche sonst matschig aussieht.

Das ist messbar. Der entscheidende Punkt steckt in `kg/photos.py`:

    square = _square_crop(image)          # bei Gesichtstreffer NUR ein Ausschnitt
    square = square.resize((size, size))  # dieser Ausschnitt wird auf 512 gezogen

Bei einem erkannten Gesicht ist der Ausschnitt `2.0 * Gesichtsbreite` -- also
oft deutlich KLEINER als das gelieferte Bild. Genau dieser Ausschnitt wird auf
`portrait_size` (512) hochgerechnet. Liefert die App ein 1024er Bild und der
Ausschnitt ist 250 px breit, dann werden 250 px auf 512 HOCHskaliert: das
Portrait ist dann rechnerisch 512, aber nur 250 px scharf.

Gemessen werden deshalb zwei Zahlen je Foto und je App-Aufloesung:

  * `ausschnitt_px`  -- wieviele echte Pixel der Zuschnitt hat, BEVOR skaliert
                        wird. Das ist die tatsaechliche Detailmenge.
  * `skalierung`     -- ausschnitt_px / portrait_size. Unter 1.0 wird
                        HOCHgerechnet, und ab da ist das Portrait weich.

Zusaetzlich die Kantenschaerfe des fertigen Portraits als Varianz des
Laplace-Operators -- der uebliche Schaerfe-Kennwert. Er ist NICHT absolut
lesbar, nur im Vergleich zwischen den Stufen; deshalb wird er auf die beste
Stufe je Foto normiert.

Ausgegeben werden nur Zahlen, keine Bildinhalte.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\birk\kollektivgedaechtnis")

BILDENDUNGEN = {".jpg", ".jpeg", ".png"}
# Was die App liefern koennte. 1024 ist der aktuelle Wert (Bildbytes.MAX_KANTE).
STUFEN = [1024, 1280, 1600, 2048, None]
PORTRAIT_SIZE = 512


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("ordner")
    p.add_argument("--portrait-size", type=int, default=PORTRAIT_SIZE)
    p.add_argument("--json", dest="json_pfad", default=None)
    args = p.parse_args()

    import cv2
    import numpy as np
    from PIL import Image, ImageOps

    from kg.photos import _square_crop

    ordner = Path(args.ordner)
    bilder = sorted(b for b in ordner.iterdir() if b.suffix.lower() in BILDENDUNGEN)
    ziel = args.portrait_size

    print("Schaerfe des fertigen Portraits, je Aufloesung der App")
    print(f"portrait_size = {ziel} px  |  Skalierung < 1.0 heisst HOCHgerechnet = weich")
    print("=" * 94)

    zeilen = []
    for bild_pfad in bilder:
        with Image.open(bild_pfad) as roh:
            original = ImageOps.exif_transpose(roh).convert("RGB")

        eintrag = {"datei": bild_pfad.name, "original": list(original.size), "stufen": {}}
        for stufe in STUFEN:
            bild = original.copy()
            if stufe is not None:
                bild.thumbnail((stufe, stufe))

            # Exakt der Weg der Station: erst zuschneiden, dann auf Zielgroesse.
            ausschnitt = _square_crop(bild)
            ausschnitt_px = ausschnitt.size[0]
            portrait = ausschnitt.resize((ziel, ziel), Image.LANCZOS)

            grau = cv2.cvtColor(np.array(portrait), cv2.COLOR_RGB2GRAY)
            schaerfe = float(cv2.Laplacian(grau, cv2.CV_64F).var())

            eintrag["stufen"]["orig" if stufe is None else str(stufe)] = {
                "geliefert": list(bild.size),
                "ausschnitt_px": ausschnitt_px,
                "skalierung": round(ausschnitt_px / ziel, 2),
                "schaerfe": round(schaerfe, 1),
            }
        zeilen.append(eintrag)

    # --- Ausgabe je Foto ---
    for z in zeilen:
        print(f"\n{z['datei']}  (Original {z['original'][0]}x{z['original'][1]})")
        beste = max(s["schaerfe"] for s in z["stufen"].values()) or 1.0
        print(f"  {'App liefert':>12}{'Ausschnitt':>12}{'Skalierung':>12}"
              f"{'Schaerfe':>10}{'relativ':>9}")
        for name, s in z["stufen"].items():
            marke = "  <- hochgerechnet" if s["skalierung"] < 1.0 else ""
            print(f"  {name:>12}{s['ausschnitt_px']:>12}{s['skalierung']:>12.2f}"
                  f"{s['schaerfe']:>10.1f}{s['schaerfe'] / beste * 100:>8.0f}%{marke}")

    # --- Auswertung im Code ---
    print("\n" + "=" * 94)
    print("Wieviele Fotos werden je Stufe HOCHgerechnet (= sichtbar weich)?")
    schluessel = ["orig" if s is None else str(s) for s in STUFEN]
    zusammenfassung = {}
    for name in schluessel:
        hoch = [z for z in zeilen if z["stufen"][name]["skalierung"] < 1.0]
        mittel = sum(z["stufen"][name]["schaerfe"] for z in zeilen) / len(zeilen)
        zusammenfassung[name] = {"hochgerechnet": len(hoch),
                                 "mittlere_schaerfe": round(mittel, 1)}
        print(f"  {name:>6}: {len(hoch)}/{len(zeilen)} hochgerechnet, "
              f"mittlere Schaerfe {mittel:>7.1f}")

    print()
    jetzt = zusammenfassung["1024"]["mittlere_schaerfe"]
    for name in schluessel:
        if name == "1024":
            continue
        d = zusammenfassung[name]["mittlere_schaerfe"]
        print(f"  {name:>6} gegenueber 1024: {(d / jetzt - 1) * 100:+6.0f} % Schaerfe")

    if args.json_pfad:
        Path(args.json_pfad).write_text(
            json.dumps({"portrait_size": ziel, "zusammenfassung": zusammenfassung,
                        "zeilen": zeilen}, indent=2, ensure_ascii=False),
            encoding="utf-8")
        print(f"\nJSON: {args.json_pfad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
