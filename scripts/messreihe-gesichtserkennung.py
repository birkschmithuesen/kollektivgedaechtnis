"""Faehrt die Testreihe zur Gesichtserkennung ueber ALLE Fotos eines Ordners.

Das Einzelwerkzeug `pruefe-gesichtserkennung.py` beantwortet eine Frage pro
Foto. Fuer eine Testreihe zaehlt die Verteilung ueber alle Fotos -- und die
gehoert in den Code, nicht in den Kopf einer Session.

Ausgegeben wird eine Zeile je Foto und am Ende eine Zusammenfassung; mit
`--json <datei>` zusaetzlich maschinenlesbar, damit das Ergebnis auch dann
noch existiert, wenn niemand mitgeschrieben hat.

Aufruf auf der Station:
    C:\\Users\\birk\\kollektivgedaechtnis\\.venv\\Scripts\\python.exe ^
        messreihe-gesichtserkennung.py C:\\Users\\birk\\kollektivgedaechtnis\\data\\photos

Es werden KEINE Bildinhalte ausgegeben, nur Zahlen: Anzahl Gesichter,
Position, Groesse, Flaechenanteil, resultierender Ausschnitt.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\birk\kollektivgedaechtnis")

BILDENDUNGEN = {".jpg", ".jpeg", ".png"}


def messe_ein_bild(bild: Path, kaskade, cv2, np, Image, ImageOps,
                   _gesicht_finden, GESICHTS_ZOOM, GESICHTS_BIAS) -> dict:
    """Misst ein Foto ueber den ECHTEN Stationscode und gibt nur Zahlen zurueck."""
    with Image.open(bild) as roh:
        image = ImageOps.exif_transpose(roh).convert("RGB")

    breite, hoehe = image.size
    grau = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    mindest = max(30, int(min(image.size) * 0.08))
    treffer = kaskade.detectMultiScale(grau, scaleFactor=1.1, minNeighbors=5,
                                       minSize=(mindest, mindest))

    gesichter = []
    for (x, y, w, h) in sorted(treffer, key=lambda t: -t[2] * t[3]):
        gesichter.append({
            "x": int(x), "y": int(y), "w": int(w), "h": int(h),
            "flaechenanteil_prozent": round((w * h) / (breite * hoehe) * 100, 2),
        })

    ergebnis = {
        "datei": bild.name,
        "breite": breite,
        "hoehe": hoehe,
        "gesichter_gefunden": len(gesichter),
        "gesichter": gesichter,
        "weg": "mittiger Schnitt",
        "ausschnitt": None,
        "am_anschlag": False,
        "am_bildrand": False,
    }

    gewaehlt = _gesicht_finden(image)
    if gewaehlt is None:
        return ergebnis

    gx, gy, gw, gh = (int(v) for v in gewaehlt)
    seite = min(int(round(gw * GESICHTS_ZOOM)), breite, hoehe)
    links = max(0, min(int(round(gx + gw / 2 - seite / 2)), breite - seite))
    oben = max(0, min(int(round(gy + gh / 2 - seite * GESICHTS_BIAS)), hoehe - seite))

    ergebnis["weg"] = "Gesicht"
    ergebnis["gewaehlt"] = {"x": gx, "y": gy, "w": gw, "h": gh}
    ergebnis["ausschnitt"] = {"seite": seite, "links": links, "oben": oben}
    # Am Anschlag: der Ausschnitt kann nicht mehr wachsen, die Person steht weit weg.
    ergebnis["am_anschlag"] = seite >= min(breite, hoehe)
    # Am Bildrand: der Ausschnitt musste geschoben werden, die Person steht seitlich.
    ergebnis["am_bildrand"] = links in (0, breite - seite) or oben in (0, hoehe - seite)

    # 🔴 Der Zuschnitt ist DETERMINISTISCH, sobald ein Gesicht gefunden wurde:
    # Haar-Boxen sind quadratisch (gw == gh), also ist die Kopfhoehe im
    # Portrait immer 1/GESICHTS_ZOOM (= 50 %) und der Sitz immer GESICHTS_BIAS
    # (= 46 %). Wer diese Werte als "Messergebnis" ausgibt, misst seine eigene
    # Formel -- die erste Fassung dieses Skripts tat genau das und meldete bei
    # vier verschiedenen Fotos identisch 25,0 % (nachgerechnet 2026-09-01).
    #
    # Die EINZIGE Quelle echter Abweichung ist das Klemmen an den Bildrand.
    # Nur dort weichen Kopfhoehe und Sitz vom Soll ab -- und nur diese Faelle
    # sind eine Aussage ueber das Verfahren.
    ergebnis["kopfhoehe_im_portrait_prozent"] = round(gh / seite * 100, 1)
    mitte_y = gy + gh / 2 - oben
    ergebnis["gesichtsmitte_im_portrait_prozent"] = round(mitte_y / seite * 100, 1)
    ergebnis["bias_abweichung_punkte"] = round(
        ergebnis["gesichtsmitte_im_portrait_prozent"] - GESICHTS_BIAS * 100, 1)
    return ergebnis


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("ordner", help="Ordner mit den Booth-Fotos")
    p.add_argument("--json", dest="json_pfad", default=None)
    args = p.parse_args()

    try:
        import cv2
        import numpy as np
        from PIL import Image, ImageOps
        from kg.photos import GESICHTS_BIAS, GESICHTS_ZOOM, _gesicht_finden
    except ImportError as fehler:
        print(f"FEHLER: {fehler}")
        return 1

    if not hasattr(cv2, "CascadeClassifier"):
        print("FEHLER: CascadeClassifier fehlt (OpenCV 5?) -- die Erkennung laeuft nicht.")
        return 2

    pfad = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    kaskade = cv2.CascadeClassifier(str(pfad))
    if kaskade.empty():
        print("FEHLER: Kaskade laedt nicht.")
        return 3

    ordner = Path(args.ordner)
    bilder = sorted(b for b in ordner.iterdir() if b.suffix.lower() in BILDENDUNGEN)
    if not bilder:
        print(f"Keine Bilder in {ordner}")
        return 4

    print(f"Messreihe Gesichtserkennung -- {len(bilder)} Fotos")
    print(f"cv2 {cv2.__version__} | GESICHTS_ZOOM={GESICHTS_ZOOM} GESICHTS_BIAS={GESICHTS_BIAS}")
    print("=" * 78)

    zeilen = []
    for bild in bilder:
        try:
            z = messe_ein_bild(bild, kaskade, cv2, np, Image, ImageOps,
                               _gesicht_finden, GESICHTS_ZOOM, GESICHTS_BIAS)
        except Exception as fehler:  # ein kaputtes Foto darf die Reihe nicht kippen
            z = {"datei": bild.name, "fehler": str(fehler)}
        zeilen.append(z)

        if "fehler" in z:
            print(f"{bild.name:<28} FEHLER: {z['fehler']}")
            continue
        marken = []
        if z["am_anschlag"]:
            marken.append("Anschlag")
        if z["am_bildrand"]:
            marken.append("Bildrand")
        zusatz = f"  [{', '.join(marken)}]" if marken else ""
        sitz = z.get("gesichtsmitte_im_portrait_prozent")
        sitz_txt = (f" Kopfhoehe {z['kopfhoehe_im_portrait_prozent']:>4.1f} %"
                    f" Sitz {sitz:>4.1f} % (Soll 46)") if sitz is not None else ""
        print(f"{z['datei']:<28} {z['breite']}x{z['hoehe']:<6} "
              f"Gesichter {z['gesichter_gefunden']}  -> {z['weg']}{sitz_txt}{zusatz}")

    gueltig = [z for z in zeilen if "fehler" not in z]
    mit_gesicht = [z for z in gueltig if z["weg"] == "Gesicht"]
    mehrere = [z for z in gueltig if z["gesichter_gefunden"] > 1]
    anschlag = [z for z in mit_gesicht if z["am_anschlag"]]
    bildrand = [z for z in mit_gesicht if z["am_bildrand"]]
    abweichungen = sorted(abs(z["bias_abweichung_punkte"]) for z in mit_gesicht)

    print("=" * 78)
    print(f"Fotos gemessen:            {len(gueltig)}")
    print(f"Gesicht gefunden:          {len(mit_gesicht)}"
          + (f"  ({len(mit_gesicht) / len(gueltig) * 100:.0f} %)" if gueltig else ""))
    print(f"mittiger Schnitt:          {len(gueltig) - len(mit_gesicht)}")
    print(f"mehrere Gesichter im Bild: {len(mehrere)}")
    print(f"Ausschnitt am Anschlag:    {len(anschlag)}")
    print(f"Ausschnitt am Bildrand:    {len(bildrand)}")
    if abweichungen:
        mitte = abweichungen[len(abweichungen) // 2]
        print(f"Abweichung vom Soll-Sitz:  min {abweichungen[0]:.1f} | "
              f"Median {mitte:.1f} | max {abweichungen[-1]:.1f} Punkte")

    if args.json_pfad:
        zusammenfassung = {
            "cv2": cv2.__version__,
            "gesichts_zoom": GESICHTS_ZOOM,
            "gesichts_bias": GESICHTS_BIAS,
            "fotos": len(gueltig),
            "mit_gesicht": len(mit_gesicht),
            "mehrere_gesichter": len(mehrere),
            "am_anschlag": len(anschlag),
            "am_bildrand": len(bildrand),
            "kopfhoehen": [z["kopfhoehe_im_portrait_prozent"] for z in mit_gesicht],
            "bias_abweichungen": abweichungen,
            "zeilen": zeilen,
        }
        Path(args.json_pfad).write_text(
            json.dumps(zusammenfassung, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nJSON: {args.json_pfad}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
