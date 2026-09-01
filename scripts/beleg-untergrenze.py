"""Belegt die Untergrenze am ECHTEN Foto, vorher gegen nachher.

Die Tests zeigen, dass die Regel greift. Diese Messung zeigt, dass sie das
Problem tatsaechlich loest -- an `1788105156_5.jpg`, dem Foto, das den Matsch
verursacht hat (61x61-Gesicht, 122 px Ausschnitt, Faktor 4,2 Hochrechnung).

Gemessen wird die Kantenschaerfe (Varianz des Laplace) des FERTIGEN Portraits,
einmal mit der alten und einmal mit der neuen Regel. Der Wert ist nicht
absolut lesbar, nur im Vergleich -- deshalb stehen beide nebeneinander.

Ausgegeben werden nur Zahlen.
"""

import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\birk\kollektivgedaechtnis")

# 🔴 Zeigt auf den Code der STATION. Solange die Station noch auf dem alten
# Stand steht (der Kern laeuft, ein Pull im Betrieb ist Birks Entscheidung),
# misst dieses Skript die ALTE Fassung und beide Zeilen sind identisch.
#
# Fuer die Vorher/Nachher-Messung am 2026-09-01 lag die neue `kg/photos.py`
# deshalb in einer Kopie unter `kg-start\probe\`, und diese Zeile zeigte
# dorthin. Wer die Messung wiederholen will, bevor die Station nachgezogen
# hat, macht es genauso -- den laufenden Kern dafuer NICHT anfassen.


def main() -> int:
    import cv2
    import numpy as np
    from PIL import Image, ImageOps

    from kg import photos

    bild_pfad = Path(sys.argv[1])
    ziel = 512

    with Image.open(bild_pfad) as roh:
        original = ImageOps.exif_transpose(roh).convert("RGB")

    print(f"Untergrenze am echten Foto: {bild_pfad.name}")
    print(f"Original {original.size[0]}x{original.size[1]}, portrait_size {ziel}")
    print(f"MINDEST_AUSSCHNITT = {photos.MINDEST_AUSSCHNITT}")
    print("=" * 74)
    print(f"{'Regel':<22}{'Ausschnitt':>12}{'Skalierung':>12}{'Schaerfe':>11}")

    ergebnisse = {}
    for etikett, grenze in (("vorher (ohne Grenze)", 0), ("nachher (mit Grenze)", None)):
        # Die Regel wird ueber die Konstante geschaltet, damit BEIDE Laeufe
        # durch denselben echten `_square_crop` gehen -- eine nachgebaute
        # Formel wuerde hier wieder nur sich selbst messen.
        alt = photos.MINDEST_AUSSCHNITT
        if grenze is not None:
            photos.MINDEST_AUSSCHNITT = grenze
        try:
            ausschnitt = photos._square_crop(original)
        finally:
            photos.MINDEST_AUSSCHNITT = alt

        portrait = ausschnitt.resize((ziel, ziel), Image.LANCZOS)
        grau = cv2.cvtColor(np.array(portrait), cv2.COLOR_RGB2GRAY)
        schaerfe = float(cv2.Laplacian(grau, cv2.CV_64F).var())
        px = ausschnitt.size[0]
        ergebnisse[etikett] = (px, schaerfe)
        print(f"{etikett:<22}{px:>12}{px / ziel:>12.2f}{schaerfe:>11.1f}")

    vorher = ergebnisse["vorher (ohne Grenze)"][1]
    nachher = ergebnisse["nachher (mit Grenze)"][1]
    print("=" * 74)
    if vorher > 0:
        print(f"Schaerfe: {vorher:.1f} -> {nachher:.1f}  "
              f"({(nachher / vorher - 1) * 100:+.0f} %)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
