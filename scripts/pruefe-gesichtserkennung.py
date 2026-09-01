"""Prueft, ob die Gesichtserkennung auf DIESEM Rechner wirklich laeuft.

Nicht "ist cv2 installiert" -- das war schon einmal irrefuehrend: OpenCV 5
laesst sich installieren, hat aber `CascadeClassifier` und die
Kaskadendateien entfernt, und die Erkennung faellt danach still auf den
mittigen Schnitt zurueck. Geprueft wird deshalb die ganze Kette bis zu einem
tatsaechlich gefundenen Gesicht.

Aufruf:
    C:\\Users\\birk\\kollektivgedaechtnis\\.venv\\Scripts\\python.exe pruefe-gesichtserkennung.py [bild.jpg]

Ohne Bild werden nur die Voraussetzungen geprueft. Mit Bild wird zusaetzlich
gemeldet, wie viele Gesichter darin gefunden werden und wie der Ausschnitt
danach liegt -- das ist die Zahl, die bei einer Testreihe zaehlt.
"""

import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\birk\kollektivgedaechtnis")


def main() -> int:
    print("Gesichtserkennung auf diesem Rechner")
    print("=" * 40)

    try:
        import cv2
    except ImportError:
        print("cv2:            NICHT installiert")
        print()
        print("-> Die Station schneidet mittig. Das ist kein Fehler, aber eine")
        print("   Testreihe zur Gesichtserkennung misst dann nichts.")
        print('   Installieren mit:  pip install "opencv-python-headless<5"')
        return 1

    print(f"cv2:            {cv2.__version__}")

    if not hasattr(cv2, "CascadeClassifier"):
        print("CascadeClassifier: FEHLT")
        print()
        print("-> OpenCV 5 hat ihn entfernt. Die Erkennung laeuft NICHT,")
        print("   obwohl cv2 installiert ist. Zurueck auf 4.x:")
        print('   pip install "opencv-python-headless<5"')
        return 2

    pfad = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    if not pfad.exists():
        print(f"Kaskadendatei:  FEHLT ({pfad})")
        return 3

    kaskade = cv2.CascadeClassifier(str(pfad))
    if kaskade.empty():
        print("Kaskade:        laedt NICHT")
        return 4

    print("Kaskadendatei:  vorhanden")
    print("Kaskade:        geladen")
    print()
    print("-> Die Erkennung ist aktiv.")

    if len(sys.argv) < 2:
        print()
        print("Fuer eine Messung an einem echten Foto:")
        print("   pruefe-gesichtserkennung.py <bild.jpg>")
        return 0

    # Mit Bild: die eigentliche Messung, ueber den ECHTEN Code der Station.
    from PIL import Image, ImageOps

    from kg.photos import GESICHTS_BIAS, GESICHTS_ZOOM, _gesicht_finden

    bild = Path(sys.argv[1])
    if not bild.exists():
        print(f"FEHLER: {bild} nicht gefunden")
        return 5

    print()
    print(f"Messung an {bild.name}")
    print("-" * 40)

    with Image.open(bild) as roh:
        image = ImageOps.exif_transpose(roh).convert("RGB")

    breite, hoehe = image.size
    print(f"Bildgroesse:    {breite} x {hoehe}")

    # Alle Treffer, nicht nur den groessten -- bei mehreren Personen ist
    # genau das die Frage.
    import numpy as np

    grau = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    mindest = max(30, int(min(image.size) * 0.08))
    treffer = kaskade.detectMultiScale(grau, scaleFactor=1.1, minNeighbors=5,
                                       minSize=(mindest, mindest))
    print(f"Gesichter:      {len(treffer)}")
    for i, (x, y, w, h) in enumerate(sorted(treffer, key=lambda t: -t[2] * t[3]), 1):
        anteil = (w * h) / (breite * hoehe) * 100
        print(f"  {i}. bei ({x},{y}) groesse {w}x{h}  ({anteil:.1f} % der Flaeche)")

    gewaehlt = _gesicht_finden(image)
    if gewaehlt is None:
        print()
        print("Gewaehlt:       KEINES -> mittiger Schnitt")
        return 0

    gx, gy, gw, gh = gewaehlt
    seite = min(int(round(gw * GESICHTS_ZOOM)), breite, hoehe)
    links = max(0, min(int(round(gx + gw / 2 - seite / 2)), breite - seite))
    oben = max(0, min(int(round(gy + gh / 2 - seite * GESICHTS_BIAS)), hoehe - seite))

    print()
    print(f"Gewaehlt:       das groesste, bei ({gx},{gy}) {gw}x{gh}")
    print(f"Ausschnitt:     {seite}x{seite} ab ({links},{oben})")
    if seite >= min(breite, hoehe):
        print("                (am Anschlag -- Person steht weit weg)")
    if links in (0, breite - seite) or oben in (0, hoehe - seite):
        print("                (an den Bildrand geschoben -- Person steht sehr seitlich)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
