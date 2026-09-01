"""Wertet die NEUESTEN Fotos der Station aus -- fuer den Test mit dem Handy.

Gedacht fuer den Moment, in dem Birk am Booth steht und fotografiert: das
Skript sieht nach, was seit einem Zeitpunkt neu hereingekommen ist, und sagt
je Foto, ob die Erkennung gegriffen hat, wie gross das Gesicht war und ob die
Untergrenze eingesprungen ist.

Der Unterschied zu `messreihe-gesichtserkennung.py`: das misst einen ganzen
Ordner und aggregiert. Hier geht es um die letzten paar Fotos, mit der Frage
"hat es bei DIESEM Bild funktioniert" -- und um die Groesse, die ankam,
weil die daran haengt, welche APK auf dem Handy liegt.

Aufruf auf der Station:
    C:\\Users\\birk\\kollektivgedaechtnis\\.venv\\Scripts\\python.exe ^
        pruefe-neue-fotos.py --seit-minuten 30

Ausgegeben werden nur Zahlen und Dateinamen, keine Bildinhalte.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, r"C:\Users\birk\kollektivgedaechtnis")

FOTOS = Path(r"C:\Users\birk\kollektivgedaechtnis\data\photos")
PORTRAITS = Path(r"C:\Users\birk\kollektivgedaechtnis\data\portraits")
BILDENDUNGEN = {".jpg", ".jpeg", ".png"}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--seit-minuten", type=float, default=30.0)
    p.add_argument("--ordner", default=str(FOTOS))
    args = p.parse_args()

    import cv2
    import numpy as np
    from PIL import Image, ImageOps

    from kg import photos

    grenze = time.time() - args.seit_minuten * 60
    ordner = Path(args.ordner)
    neue = sorted(
        (b for b in ordner.iterdir()
         if b.suffix.lower() in BILDENDUNGEN and b.stat().st_mtime >= grenze),
        key=lambda b: b.stat().st_mtime,
    )

    print(f"Neue Fotos der letzten {args.seit_minuten:.0f} Minuten: {len(neue)}")
    print(f"MINDEST_AUSSCHNITT = {photos.MINDEST_AUSSCHNITT}  "
          f"GESICHTS_ZOOM = {photos.GESICHTS_ZOOM}")
    print("=" * 96)
    if not neue:
        print("Nichts angekommen. Kommt das Foto ueber den Spiegel, dauert es bis zu 2 s")
        print("laenger (der Abholer holt im Takt). Sonst: Adresse in der App pruefen.")
        return 0

    kaskade = cv2.CascadeClassifier(
        str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))

    for bild_pfad in neue:
        kb = bild_pfad.stat().st_size / 1024
        with Image.open(bild_pfad) as roh:
            bild = ImageOps.exif_transpose(roh).convert("RGB")
        breite, hoehe = bild.size

        # Die Groesse verraet die APK: die App verkleinert die LANGE Kante auf
        # 1024 px (Bildbytes.MAX_KANTE, seit v2 -- v1 hat das nicht). Kommt
        # etwas Groesseres an, lief es nicht durch die aktuelle App.
        #
        # Gemessen wird die lange Kante, NICHT die Dateigroesse: ein
        # 768x1024-Foto kann je nach Motiv 100 oder 300 kB haben, das sagt
        # nichts. Und nicht max(breite,hoehe) > 1200 (erster Versuch): das
        # meldete ein korrektes 720x1280 als Fehler, obwohl 1280 hier die
        # lange Kante eines Bildes ist, das gar nicht von der App kam.
        lange_kante = max(breite, hoehe)
        apk_hinweis = ""
        if lange_kante > 1024:
            apk_hinweis = (f"  >>> lange Kante {lange_kante} px > 1024 "
                           f"-- kam NICHT durch die aktuelle App (v1? Telegram? Altfoto?)")

        grau = cv2.cvtColor(np.array(bild), cv2.COLOR_RGB2GRAY)
        mindest = max(30, int(min(bild.size) * 0.08))
        treffer = kaskade.detectMultiScale(grau, scaleFactor=1.1, minNeighbors=5,
                                           minSize=(mindest, mindest))

        print(f"\n{bild_pfad.name}   {breite}x{hoehe}, {kb:.0f} kB{apk_hinweis}")
        print(f"  Gesichter gefunden: {len(treffer)}")
        for i, (x, y, w, h) in enumerate(
                sorted(treffer, key=lambda t: -t[2] * t[3]), 1):
            anteil = (w * h) / (breite * hoehe) * 100
            print(f"    {i}. {w}x{h} bei ({x},{y})  {anteil:.1f} % der Flaeche")

        gewaehlt = photos._gesicht_finden(bild)
        if gewaehlt is None:
            print("  -> mittiger Schnitt (kein Gesicht erkannt)")
        else:
            gx, gy, gw, gh = (int(v) for v in gewaehlt)
            roh_seite = min(int(round(gw * photos.GESICHTS_ZOOM)), breite, hoehe)
            seite = min(max(roh_seite, photos.MINDEST_AUSSCHNITT), breite, hoehe)
            print(f"  -> Gesicht {gw}x{gh} gewaehlt, Ausschnitt {seite} px")
            if seite > roh_seite:
                print(f"     UNTERGRENZE GRIFF: {roh_seite} -> {seite} px "
                      f"(haette sonst {512 / roh_seite:.1f}x hochgerechnet)")
            if len(treffer) > 1:
                print("     (mehrere Gesichter -- das groesste hat gewonnen; "
                      "stimmt das am Bild?)")

        portrait = PORTRAITS / (bild_pfad.stem + ".png")
        if portrait.exists():
            with Image.open(portrait) as pim:
                hg = Image.new("RGB", pim.size, (0, 0, 0))
                rgba = pim.convert("RGBA")
                hg.paste(rgba, (0, 0), rgba)
            pgrau = cv2.cvtColor(np.array(hg), cv2.COLOR_RGB2GRAY)
            schaerfe = float(cv2.Laplacian(pgrau, cv2.CV_64F).var())
            print(f"  Portrait: {portrait.name}, {pim.size[0]}x{pim.size[1]}, "
                  f"Schaerfe {schaerfe:.1f}")
            if schaerfe < 50:
                print("     >>> SEHR WEICH -- am Bild ansehen.")
                # Wichtige Unterscheidung, sonst sucht man den Fehler im
                # Zuschnitt, obwohl schon das Foto verwackelt war (gemessen
                # 2026-09-01 an app043: Quelle 129 gegen 430 bei einem
                # scharfen Foto derselben Serie).
                qgrau = cv2.cvtColor(np.array(bild), cv2.COLOR_RGB2GRAY)
                qschaerfe = float(cv2.Laplacian(qgrau, cv2.CV_64F).var())
                print(f"     Quellfoto selbst: Schaerfe {qschaerfe:.1f}")
                if qschaerfe < 200:
                    print("     -> schon das FOTO ist weich (verwackelt/unscharf),")
                    print("        nicht der Zuschnitt. Nochmal ausloesen.")
                else:
                    print("     -> das Foto ist scharf, der Zuschnitt macht es weich.")
        else:
            print("  >>> KEIN Portrait geschrieben")

    print("\n" + "=" * 96)
    print("Die Schaerfe ist nur im Vergleich lesbar: unter ~50 war es bisher matschig,")
    print("ueber ~200 sauber. Das Urteil faellt am Bild, nicht an der Zahl.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
