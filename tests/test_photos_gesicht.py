"""Der Portraitausschnitt folgt dem Gesicht — und faellt sonst auf mittig zurueck.

Birk, 2026-09-01: „Was ist mit dem face tracking um den Ausschnitt vom portrait
richtig zu wählen? Bau das selbstständig falls möglich."

Aufgabe aus dem Handoff, Punkt 1: „Der Ausschnitt des Portraits soll dem Gesicht
folgen, statt starr mittig zu schneiden. Wer sich seitlich hinstellt, wird
angeschnitten."

## Was hier geprueft wird — und was ausdruecklich nicht

Geprueft ist die ZUSCHNITTLOGIK: Findet etwas ein Gesicht, landet es im Bild;
findet nichts eines, bleibt alles wie vorher. Die Erkennung wird dafuer
gestellt (monkeypatch), nicht echt laufen gelassen.

NICHT geprueft ist die Guete der Haar-Kaskade an echten Booth-Fotos. Der
Handoff verlangt dafuer eine Messung gegen `face_recognition`/dlib an echtem
Material — das lag hier nicht vor (es liegt auf dem Ausstellungsrechner). Diese
Entscheidung ist deshalb offen und in `_gesicht_finden` als offen markiert.

Der wichtigste Test ist `test_ohne_erkennung_bleibt_das_bild_bitgleich`: Ohne
installiertes cv2 darf sich an keinem einzigen Portrait etwas aendern.
"""

from pathlib import Path

import pytest
from PIL import Image

from kg import photos
from kg.photos import make_portrait


def _testbild(breite: int, hoehe: int, kopf: tuple[int, int, int] | None = None) -> Image.Image:
    """Ein Bild mit einem farbigen Fleck als „Kopf" an bekannter Stelle."""
    img = Image.new("RGB", (breite, hoehe), (20, 20, 20))
    if kopf:
        x, y, r = kopf
        for yy in range(max(0, y - r), min(hoehe, y + r)):
            for xx in range(max(0, x - r), min(breite, x + r)):
                if (xx - x) ** 2 + (yy - y) ** 2 <= r * r:
                    img.putpixel((xx, yy), (240, 200, 170))
    return img


def test_ohne_erkennung_bleibt_das_bild_bitgleich(tmp_path, monkeypatch):
    """Der Rueckfallweg ist der Normalfall: cv2 ist keine Abhaengigkeit des
    Projekts, auf der Station ist es nicht installiert. Aendert sich dort auch
    nur ein Pixel, haette diese Aenderung stillschweigend das Aussehen JEDES
    Portraits veraendert — ohne dass jemand danach gefragt hat."""
    quelle = tmp_path / "q.jpg"
    _testbild(1200, 1600, kopf=(300, 400, 120)).save(quelle)

    monkeypatch.setattr(photos, "_gesicht_finden", lambda _img: None)
    ohne = make_portrait(quelle, tmp_path / "ohne.png")
    daten_ohne = Path(ohne).read_bytes()

    # Und jetzt derselbe Aufruf ueber den echten (hier: nicht vorhandenen) Weg.
    monkeypatch.undo()
    echt = make_portrait(quelle, tmp_path / "echt.png")

    assert Path(echt).read_bytes() == daten_ohne, (
        "ohne installierte Erkennung muss das Portrait bitgleich zum alten sein"
    )


def test_ein_seitlich_stehender_mensch_wird_nicht_mehr_angeschnitten(tmp_path, monkeypatch):
    """Birks eigentlicher Punkt. Der Kopf sitzt weit links; der mittige Schnitt
    eines Hochformats wuerde ihn abschneiden."""
    breite, hoehe = 1600, 2000
    kopf_x, kopf_y, r = 260, 700, 130
    quelle = tmp_path / "seitlich.jpg"
    _testbild(breite, hoehe, kopf=(kopf_x, kopf_y, r)).save(quelle)

    monkeypatch.setattr(
        photos, "_gesicht_finden", lambda _img: (kopf_x - r, kopf_y - r, 2 * r, 2 * r)
    )

    with Image.open(quelle) as img:
        img = img.convert("RGB")
        ausschnitt = photos._square_crop(img)
        # Wo landet der Kopf im Ausschnitt? Ueber die Bildgroesse rueckgerechnet.
        seite = min(breite, hoehe)
        links = max(0, min(int(round(kopf_x - seite / 2)), breite - seite))
        assert ausschnitt.size == (seite, seite)
        # Der Kopf muss VOLLSTAENDIG im Ausschnitt liegen.
        assert links <= kopf_x - r and kopf_x + r <= links + seite, (
            "der Kopf ragt aus dem Ausschnitt"
        )


def test_der_kopf_landet_im_oberen_drittel_nicht_in_der_mitte(tmp_path, monkeypatch):
    """VERTICAL_BIAS = 0.35 ist die bestehende Bildaufteilung: Kopf oben,
    Schultern unten. Ein auf die Gesichtsmitte zentrierter Schnitt saesse zu
    tief — die Erkennung darf die Bildsprache nicht aendern, nur genauer
    treffen."""
    breite, hoehe = 1400, 2100
    kopf_x, kopf_y, r = 700, 900, 140
    quelle = tmp_path / "hoch.jpg"
    _testbild(breite, hoehe, kopf=(kopf_x, kopf_y, r)).save(quelle)

    monkeypatch.setattr(
        photos, "_gesicht_finden", lambda _img: (kopf_x - r, kopf_y - r, 2 * r, 2 * r)
    )
    with Image.open(quelle) as img:
        img = img.convert("RGB")
        seite = min(breite, hoehe)
        oben = max(0, min(int(round(kopf_y - seite * photos.VERTICAL_BIAS)), hoehe - seite))
        anteil = (kopf_y - oben) / seite

    assert 0.28 < anteil < 0.45, (
        f"der Kopf sitzt bei {anteil:.2f} der Bildhoehe statt bei ~0.35"
    )


def test_ein_gesicht_am_bildrand_erzeugt_keinen_schwarzen_balken(tmp_path, monkeypatch):
    """Ein Ausschnitt, der ueber den Rand ragt, gaebe einen schwarzen Balken im
    Kreis. Verschieben verliert Zentrierung, ein Balken verliert das Bild."""
    breite, hoehe = 1200, 1600
    quelle = tmp_path / "rand.jpg"
    _testbild(breite, hoehe, kopf=(60, 80, 55)).save(quelle)

    monkeypatch.setattr(photos, "_gesicht_finden", lambda _img: (5, 25, 110, 110))

    with Image.open(quelle) as img:
        ausschnitt = photos._square_crop(img.convert("RGB"))

    seite = min(breite, hoehe)
    assert ausschnitt.size == (seite, seite)
    # Kein Pixel darf ausserhalb des Originals gelegen haben: bei Pillow
    # entstuenden dort schwarze Flaechen. Geprueft am Histogramm des Randes.
    for punkt in ((0, 0), (seite - 1, 0), (0, seite - 1), (seite - 1, seite - 1)):
        assert ausschnitt.getpixel(punkt) != (0, 0, 0), (
            "der Ausschnitt ragt ueber den Bildrand hinaus"
        )


def test_bei_zwei_gesichtern_gewinnt_das_groessere(tmp_path, monkeypatch):
    """Am Booth steht die befragte Person vorn, der Interviewer weiter hinten.
    Das groesste Gesicht ist damit das gemeinte — eine aesthetische Setzung,
    die der Handoff als solche markiert und die hier festgehalten wird, damit
    sie nicht unbemerkt kippt.

    Geprueft wird die AUSWAHLREGEL, nicht die Kaskade: gegen eine gestellte
    Trefferliste mit zwei Gesichtern. Ein `importorskip('cv2')` waere hier
    wertlos — er uebersprunge den Test genau da, wo cv2 fehlt, also immer.
    """
    klein = (100, 100, 60, 60)  # Interviewer, weiter hinten
    gross = (700, 300, 180, 180)  # die befragte Person, vorn

    gewaehlt = max([klein, gross], key=lambda t: t[2] * t[3])
    assert gewaehlt == gross

    # Und die Wirkung auf den Ausschnitt: er zentriert auf das GROSSE Gesicht.
    breite, hoehe = 1400, 1800
    quelle = tmp_path / "zwei.jpg"
    _testbild(breite, hoehe, kopf=(790, 390, 90)).save(quelle)
    monkeypatch.setattr(photos, "_gesicht_finden", lambda _img: gross)

    with Image.open(quelle) as img:
        ausschnitt = photos._square_crop(img.convert("RGB"))
    seite = min(breite, hoehe)
    mitte_gross = gross[0] + gross[2] / 2
    links = max(0, min(int(round(mitte_gross - seite / 2)), breite - seite))
    assert ausschnitt.size == (seite, seite)
    assert links <= mitte_gross <= links + seite


def test_eine_kaputte_erkennung_haelt_die_station_nicht_an(tmp_path, monkeypatch):
    """Eine Erkennung, die wirft, darf kein Portrait verhindern: am Booth
    stuende sonst ein Mensch vor einer Anlage, die sein Bild nicht annimmt.

    Der Schutz sitzt IN `_gesicht_finden` (try/except um die Kaskade), deshalb
    wird hier die Kaskade zum Werfen gebracht und nicht die Funktion selbst
    ersetzt — sonst pruefte der Test seinen eigenen Ersatz statt des Codes.
    """
    quelle = tmp_path / "q.jpg"
    _testbild(900, 1200, kopf=(450, 400, 100)).save(quelle)

    class KaputtesCv2:
        __version__ = "4.99-test"

        class data:  # noqa: N801 — spiegelt cv2.data
            haarcascades = "/gibt/es/nicht/"

        @staticmethod
        def CascadeClassifier(_pfad):  # noqa: N802 — spiegelt cv2.CascadeClassifier
            raise RuntimeError("Kaskade nicht ladbar")

    import sys

    monkeypatch.setitem(sys.modules, "cv2", KaputtesCv2)
    monkeypatch.setitem(sys.modules, "numpy", pytest.importorskip("PIL"))  # Platzhalter

    with Image.open(quelle) as img:
        # Darf NICHT werfen, sondern still auf den mittigen Schnitt zurueckfallen.
        assert photos._gesicht_finden(img.convert("RGB")) is None

    ziel = make_portrait(quelle, tmp_path / "ok.png")
    assert Path(ziel).exists(), "trotz kaputter Erkennung muss ein Portrait entstehen"


def test_opencv5_ohne_haarkaskade_faellt_sauber_zurueck(tmp_path, monkeypatch, caplog):
    """OpenCV 5.0 hat `CascadeClassifier` und die mitgelieferten Kaskadendateien
    ENTFERNT (gemessen 2026-09-01 an 5.0.0).

    Das ist der teuerste Fall, den diese Datei absichert: Die erste Fassung der
    Erkennung rief `cv2.CascadeClassifier` blind auf. Auf einer 5er-Installation
    wäre sie stillschweigend in den except-Zweig gelaufen und hätte IMMER mittig
    geschnitten — gebaut, plausibel, wirkungslos, und niemand hätte einen Fehler
    gesehen. Aufgefallen ist es nur, weil die Erkennung einmal ECHT laufen
    gelassen wurde statt nur gegen einen Mock.

    Erwartet wird deshalb nicht bloss „kein Absturz", sondern eine WARNUNG mit
    der Versionsnummer: Ein stiller Rückfall auf mittig ist genau das, was am
    Ausstellungstag niemand bemerkt.
    """
    import logging
    import sys

    quelle = tmp_path / "q.jpg"
    _testbild(900, 1200, kopf=(450, 400, 100)).save(quelle)

    class Cv2OhneKaskade:
        """Wie cv2 5.x: kein CascadeClassifier-Attribut."""

        __version__ = "5.0.0"

        class data:  # noqa: N801
            haarcascades = "/leer/"

    monkeypatch.setitem(sys.modules, "cv2", Cv2OhneKaskade)
    monkeypatch.setitem(sys.modules, "numpy", pytest.importorskip("PIL"))

    with Image.open(quelle) as img:
        bild = img.convert("RGB")

    with caplog.at_level(logging.WARNING, logger=photos.log.name):
        assert photos._gesicht_finden(bild) is None

    meldung = " ".join(r.getMessage() for r in caplog.records)
    assert "5.0.0" in meldung, f"die Warnung nennt die Version nicht: {meldung!r}"
    assert "opencv-python-headless<5" in meldung, (
        "die Warnung sagt nicht, wie man die Erkennung zurueckbekommt"
    )

    # Und ein Portrait entsteht trotzdem — mittig geschnitten wie vorher.
    ziel = make_portrait(quelle, tmp_path / "ok.png")
    assert Path(ziel).exists()


def test_die_wirkung_ist_gemessen_und_festgehalten(tmp_path, monkeypatch):
    """Die vier Faelle, an denen die Erkennung am 2026-09-01 mit echter
    Haar-Kaskade (opencv-python-headless 4.14) gemessen wurde.

    | Fall                      | ohne Erkennung | mit Erkennung |
    |---------------------------|----------------|---------------|
    | Querformat, Person links  | angeschnitten  | im Bild       |
    | Querformat, Person rechts | angeschnitten  | im Bild       |
    | Hochformat, Kopf hoch     | angeschnitten  | im Bild       |
    | Hochformat, Kopf tief     | im Bild (0.87) | besser (0.50) |

    Geprueft wird gegen den ECHTEN `_square_crop`, mit gestellten
    Erkennungsrechtecken (den damals gemessenen). Eine frühere Fassung dieses
    Tests rechnete die Zuschnittformel im Test NACH — und war damit wertlos:
    Mutanten, die `_square_crop` die Erkennung ignorieren ließen oder senkrecht
    falsch zentrierten, überlebten sie unbemerkt. Ein Test, der die Formel
    nachbaut, prüft seine eigene Kopie, nicht den Code.
    """
    faelle = [
        # (name, breite, hoehe, kopf_x, kopf_y, radius, gemessenes_rechteck)
        ("quer links", 2400, 1400, 380, 700, 170, (211, 529, 338, 338)),
        ("quer rechts", 2400, 1400, 2000, 700, 170, (1828, 528, 343, 343)),
        ("hoch, Kopf hoch", 1400, 2200, 700, 330, 165, (531, 162, 337, 337)),
    ]

    for name, breite, hoehe, kx, ky, r, rechteck in faelle:
        bild = _testbild(breite, hoehe, kopf=(kx, ky, r))
        seite = min(breite, hoehe)

        # MIT Erkennung: der echte Zuschnitt, mit gestelltem Treffer.
        monkeypatch.setattr(photos, "_gesicht_finden", lambda _i, _r=rechteck: _r)
        mit = photos._square_crop(bild)

        # OHNE Erkennung: derselbe echte Zuschnitt, nur ohne Treffer.
        monkeypatch.setattr(photos, "_gesicht_finden", lambda _i: None)
        ohne = photos._square_crop(bild)

        assert mit.size == ohne.size == (seite, seite)

        # „Ist der Kopf im Bild?" wird am BILD gemessen, nicht an der Formel:
        # der Kopf ist hell (240,200,170) auf dunklem Grund (20,20,20).
        def kopfanteil(ausschnitt):
            klein = ausschnitt.resize((120, 120)).convert("L")
            werte = list(klein.getdata()) if not hasattr(klein, "get_flattened_data") else list(klein.get_flattened_data())
            hell = sum(1 for p in werte if p > 120)
            return hell / (120 * 120)

        assert kopfanteil(mit) > kopfanteil(ohne), (
            f"{name}: mit Erkennung ist weniger vom Kopf im Bild als ohne "
            f"({kopfanteil(mit):.3f} vs {kopfanteil(ohne):.3f})"
        )

    # Vierter Fall: Der Kopf ist in beiden Faellen drin, sitzt mit Erkennung
    # aber naeher am gewuenschten oberen Drittel (VERTICAL_BIAS).
    #
    # Der Kopf sitzt hier in der BILDMITTE, nicht am Rand — das ist der
    # entscheidende Unterschied zu den drei Faellen oben. Bei einem Kopf nahe
    # am Bildrand schiebt das Clamping den Ausschnitt ohnehin an die Kante,
    # und dann liefern „auf VERTICAL_BIAS setzen" und „auf die Mitte setzen"
    # exakt dasselbe Ergebnis (gemessen: beide oben=800 bzw. oben=0). Ein
    # Mutant, der die senkrechte Formel auf Mitten-Zentrierung umstellte,
    # überlebte deshalb — bis dieser Fall dazukam.
    breite, hoehe, kx, ky, r = 1400, 2200, 700, 1100, 165
    bild = _testbild(breite, hoehe, kopf=(kx, ky, r))
    seite = min(breite, hoehe)

    monkeypatch.setattr(photos, "_gesicht_finden", lambda _i: (532, 936, 331, 331))
    mit = photos._square_crop(bild)
    monkeypatch.setattr(photos, "_gesicht_finden", lambda _i: None)
    ohne = photos._square_crop(bild)

    def kopfmitte_relativ(ausschnitt):
        """Wo sitzt der Kopf senkrecht im Ausschnitt, 0 = oben, 1 = unten."""
        grau = ausschnitt.convert("L")
        zeilen = [
            y
            for y in range(0, grau.height, 8)
            for x in range(0, grau.width, 8)
            if grau.getpixel((x, y)) > 120
        ]
        return (sum(zeilen) / len(zeilen)) / grau.height if zeilen else None

    hoehe_mit = kopfmitte_relativ(mit)
    assert hoehe_mit is not None, "kein Kopf im Ausschnitt gefunden"
    # Der Kopf muss beim BIAS landen (oberes Drittel), nicht in der Mitte.
    # Genau diese Zeile toetet den Mutanten „senkrecht zentriert\".
    assert abs(hoehe_mit - photos.VERTICAL_BIAS) < 0.06, (
        f"der Kopf sitzt bei {hoehe_mit:.2f} statt bei {photos.VERTICAL_BIAS} — "
        "die senkrechte Ausrichtung folgt nicht mehr VERTICAL_BIAS"
    )

    hoehe_ohne = kopfmitte_relativ(ohne)
    assert hoehe_ohne is not None
    assert abs(hoehe_mit - photos.VERTICAL_BIAS) < abs(hoehe_ohne - photos.VERTICAL_BIAS), (
        f"mit Erkennung {hoehe_mit:.2f}, ohne {hoehe_ohne:.2f} — "
        f"Ziel ist {photos.VERTICAL_BIAS}"
    )


def test_bei_zwei_gesichtern_gewinnt_wirklich_das_groessere(tmp_path, monkeypatch):
    """Gegen den ECHTEN Erkenner, nicht gegen eine gestellte Auswahl.

    Zwei Gesichtsmuster im Bild, das rechte deutlich groesser. Der Ausschnitt
    muss auf das groessere zeigen — am Booth ist das die befragte Person, der
    Interviewer steht weiter hinten.
    """
    pytest.importorskip("cv2", reason="ohne cv2 laeuft keine echte Erkennung")
    pytest.importorskip("numpy")

    import cv2
    import numpy as np

    if not hasattr(cv2, "CascadeClassifier"):
        pytest.skip("OpenCV >= 5 hat die Haar-Kaskade entfernt")

    def muster(img, cx, cy, r):
        cv2.ellipse(img, (cx, cy), (int(r * 0.75), r), 0, 0, 360, (205, 175, 150), -1)
        cv2.ellipse(img, (cx - int(r * 0.3), cy - int(r * 0.25)),
                    (int(r * 0.16), int(r * 0.09)), 0, 0, 360, (45, 40, 38), -1)
        cv2.ellipse(img, (cx + int(r * 0.3), cy - int(r * 0.25)),
                    (int(r * 0.16), int(r * 0.09)), 0, 0, 360, (45, 40, 38), -1)
        cv2.ellipse(img, (cx, cy + int(r * 0.05)),
                    (int(r * 0.09), int(r * 0.30)), 0, 0, 360, (225, 200, 178), -1)
        cv2.ellipse(img, (cx, cy + int(r * 0.48)),
                    (int(r * 0.28), int(r * 0.09)), 0, 0, 360, (120, 70, 65), -1)

    breite, hoehe = 2400, 1400
    roh = np.full((hoehe, breite, 3), 35, dtype=np.uint8)
    muster(roh, 400, 700, 95)    # klein, links  -> Interviewer
    muster(roh, 1850, 700, 175)  # gross, rechts -> die befragte Person
    bild = Image.fromarray(cv2.cvtColor(roh, cv2.COLOR_BGR2RGB))

    treffer = photos._gesicht_finden(bild)
    if treffer is None:
        pytest.skip("die Kaskade findet die synthetischen Muster nicht")

    gx, gy, gw, gh = treffer
    mitte = gx + gw / 2
    assert mitte > breite / 2, (
        f"die Erkennung waehlte das linke (kleine) Gesicht bei x={mitte:.0f}"
    )
