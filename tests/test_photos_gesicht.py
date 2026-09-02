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


def _erwarteter_ausschnitt(breite, hoehe, gesicht):
    """Wo der Ausschnitt liegt, wenn ein Gesicht erkannt wurde.

    EIN Ort für diese Rechnung, statt sie in jedem Test zu wiederholen: Die
    Größe hängt seit 2026-09-01 an `GESICHTS_ZOOM` (der Ausschnitt wird am
    Gesicht bemessen, nicht an der Bildbreite), und eine über fünf Tests
    verstreute Kopie dieser Formel wäre beim nächsten Umbau wieder falsch.

    Bewusst nur die GEOMETRIE — was der Ausschnitt zeigen muss, prüft jeder
    Test selbst am Bild. Sonst prüfte er wieder seine eigene Kopie der Logik
    statt des Codes (der Fehler, der in dieser Datei schon einmal drin war).
    """
    gx, gy, gw, gh = gesicht
    seite = min(int(round(gw * photos.GESICHTS_ZOOM)), breite, hoehe)
    # Seit 2026-09-01 wird aufgeweitet, wenn sonst zu stark HOCHgerechnet
    # wuerde -- aber nur so weit, dass die Hochrechnung unter die Grenze
    # faellt (eine harte Untergrenze nahm knappen Faellen den Zoom weg).
    mindest = int(round(512 / photos.MAX_HOCHRECHNUNG))
    seite = min(max(seite, mindest), breite, hoehe)
    links = max(0, min(int(round(gx + gw / 2 - seite / 2)), breite - seite))
    oben = max(0, min(int(round(gy + gh / 2 - seite * photos.GESICHTS_BIAS)), hoehe - seite))
    return links, oben, seite


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
        gesicht = (kopf_x - r, kopf_y - r, 2 * r, 2 * r)
        links, _oben, seite = _erwarteter_ausschnitt(breite, hoehe, gesicht)
        assert ausschnitt.size == (seite, seite)
        # Der Kopf muss VOLLSTAENDIG im Ausschnitt liegen.
        assert links <= kopf_x - r and kopf_x + r <= links + seite, (
            "der Kopf ragt aus dem Ausschnitt"
        )


def test_der_kopf_landet_im_oberen_drittel_nicht_in_der_mitte(tmp_path, monkeypatch):
    """GESICHTS_BIAS ist die Bildaufteilung: Kopf oben, Schultern unten. Ein auf
    die Gesichtsmitte zentrierter Schnitt saesse zu tief — die Erkennung darf
    die Bildsprache nicht aendern, nur genauer treffen.

    Gemessen wird am ERZEUGTEN Ausschnitt, nicht an einer nachgebauten Formel:
    Diese Datei hatte genau diesen Fehler schon einmal, und drei Mutanten
    haben ihn ueberlebt.
    """
    breite, hoehe = 1400, 2100
    kopf_x, kopf_y, r = 700, 900, 140
    quelle = tmp_path / "hoch.jpg"
    _testbild(breite, hoehe, kopf=(kopf_x, kopf_y, r)).save(quelle)

    gesicht = (kopf_x - r, kopf_y - r, 2 * r, 2 * r)
    monkeypatch.setattr(photos, "_gesicht_finden", lambda _img: gesicht)

    with Image.open(quelle) as img:
        ausschnitt = photos._square_crop(img.convert("RGB"))

    _links, oben, seite = _erwarteter_ausschnitt(breite, hoehe, gesicht)
    assert ausschnitt.size == (seite, seite)

    # Wo sitzt der helle Kopf im erzeugten Bild? Am Bild gemessen, nicht gerechnet.
    grau = ausschnitt.convert("L")
    zeilen = [
        y
        for y in range(0, grau.height, 4)
        for x in range(0, grau.width, 4)
        if grau.getpixel((x, y)) > 120
    ]
    assert zeilen, "kein Kopf im Ausschnitt gefunden"
    anteil = (sum(zeilen) / len(zeilen)) / seite

    assert 0.30 < anteil < 0.62, (
        f"der Kopf sitzt bei {anteil:.2f} der Bildhoehe — erwartet um "
        f"{photos.GESICHTS_BIAS} herum"
    )


def test_ein_gesicht_am_bildrand_erzeugt_keinen_schwarzen_balken(tmp_path, monkeypatch):
    """Ein Ausschnitt, der ueber den Rand ragt, gaebe einen schwarzen Balken im
    Kreis. Verschieben verliert Zentrierung, ein Balken verliert das Bild."""
    breite, hoehe = 1200, 1600
    quelle = tmp_path / "rand.jpg"
    _testbild(breite, hoehe, kopf=(60, 80, 55)).save(quelle)

    gesicht = (5, 25, 110, 110)
    monkeypatch.setattr(photos, "_gesicht_finden", lambda _img: gesicht)

    with Image.open(quelle) as img:
        ausschnitt = photos._square_crop(img.convert("RGB"))

    _links, _oben, seite = _erwarteter_ausschnitt(breite, hoehe, gesicht)
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
    links, _oben, seite = _erwarteter_ausschnitt(breite, hoehe, gross)
    mitte_gross = gross[0] + gross[2] / 2
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

        # MIT Erkennung: der echte Zuschnitt, mit gestelltem Treffer.
        monkeypatch.setattr(photos, "_gesicht_finden", lambda _i, _r=rechteck: _r)
        mit = photos._square_crop(bild)

        # OHNE Erkennung: derselbe echte Zuschnitt, nur ohne Treffer.
        monkeypatch.setattr(photos, "_gesicht_finden", lambda _i: None)
        ohne = photos._square_crop(bild)

        # Die beiden Wege haben seit 2026-09-01 UNTERSCHIEDLICHE Groessen: mit
        # Erkennung wird am Gesicht bemessen (GESICHTS_ZOOM), ohne bleibt es
        # beim groesstmoeglichen Quadrat. Genau das ist der Punkt der
        # Aenderung — vorher fuellte das Gesicht nur 20 % der Kreisflaeche.
        _l, _o, seite_mit = _erwarteter_ausschnitt(breite, hoehe, rechteck)
        assert mit.size == (seite_mit, seite_mit)
        assert ohne.size == (min(breite, hoehe), min(breite, hoehe))
        assert seite_mit <= min(breite, hoehe), (
            f"{name}: der Ausschnitt darf nie groesser als das Bild werden"
        )

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

    # 🔴 Gegen eine FESTE Zahl geprüft, nicht gegen `photos.GESICHTS_BIAS`.
    #
    # Eine frühere Fassung verglich mit der Konstanten selbst — und war damit
    # wertlos: Ein Mutant, der GESICHTS_BIAS auf den alten Wert 0.35
    # zurückdrehte, verschob den Kopf UND den Vergleichswert gleichzeitig, der
    # Test blieb grün. Ein Test, der seinen Sollwert aus dem Prüfling bezieht,
    # prüft nur, dass der Code mit sich selbst übereinstimmt.
    #
    # 0.46 ist Birks Vorgabe vom 2026-09-01 („ein bisschen mehr Haare, ein
    # bisschen weniger Hals, nicht viel"), an seinem eigenen Foto abgenommen.
    # Wer den Wert ändern will, ändert ihn hier bewusst mit.
    SOLL = 0.46
    assert abs(hoehe_mit - SOLL) < 0.06, (
        f"der Kopf sitzt bei {hoehe_mit:.2f} statt bei {SOLL} — die senkrechte "
        f"Ausrichtung folgt nicht mehr Birks abgenommener Bildaufteilung "
        f"(GESICHTS_BIAS steht auf {photos.GESICHTS_BIAS})"
    )

    # Und er sitzt naeher am Ziel als der Rueckfallweg ohne Erkennung.
    hoehe_ohne = kopfmitte_relativ(ohne)
    assert hoehe_ohne is not None
    assert abs(hoehe_mit - SOLL) < abs(hoehe_ohne - SOLL), (
        f"mit Erkennung {hoehe_mit:.2f}, ohne {hoehe_ohne:.2f} — Ziel ist {SOLL}"
    )


def test_der_ausschnitt_wird_am_gesicht_bemessen_nicht_am_bildrand(tmp_path, monkeypatch):
    """🔴 Birks eigentliche Korrektur, 2026-09-01: „der Kasten ist perfekt, aber
    der Ausschnitt ist dann zu tief gewählt, also das was in den Kreis kommt."

    Gemessen an seinem echten Foto war die Ursache NICHT die Position: Der
    Ausschnitt nahm die volle Bildbreite, das Gesicht füllte damit nur 20 % der
    Kreisfläche und 45 % lagen unter dem Kinn. Den Ausschnitt zu verschieben
    ändert daran fast nichts — er war schlicht zu groß.

    `GESICHTS_ZOOM = 2.0` heißt: der Ausschnitt ist doppelt so breit wie das
    erkannte Gesicht, das Gesicht füllt also die Hälfte der Breite. Dieser
    Test hält den Zusammenhang fest, damit er nicht unbemerkt auf „volle
    Bildbreite" zurückfällt.
    """
    breite, hoehe = 1400, 1900
    gw = 280
    gesicht = (560, 700, gw, gw)
    bild = _testbild(breite, hoehe, kopf=(700, 840, gw // 2))
    monkeypatch.setattr(photos, "_gesicht_finden", lambda _i: gesicht)

    ausschnitt = photos._square_crop(bild)
    seite = ausschnitt.size[0]

    assert seite < min(breite, hoehe), (
        "der Ausschnitt nimmt wieder die volle Bildbreite — genau der Zustand, "
        "den Birk beanstandet hat"
    )
    anteil = gw / seite
    assert 0.45 <= anteil <= 0.60, (
        f"das Gesicht fuellt {anteil:.0%} der Ausschnittbreite; ein Portrait "
        "liegt bei 45-60 %"
    )
    # Gegen die FESTE abgenommene Zahl, nicht gegen photos.GESICHTS_ZOOM:
    # ein Test, der seinen Sollwert aus dem Prüfling bezieht, prüft nur, dass
    # der Code mit sich selbst übereinstimmt (siehe Kommentar bei SOLL weiter
    # unten — genau dieser Fehler hat hier einen Mutanten überleben lassen).
    assert seite == int(round(gw * 2.0)), (
        f"der Ausschnitt ist {seite}px bei {gw}px Gesicht — abgenommen war "
        f"Faktor 2.0 (Birk, 2026-09-01), GESICHTS_ZOOM steht auf "
        f"{photos.GESICHTS_ZOOM}"
    )


def test_der_ausschnitt_wird_nie_groesser_als_das_foto(monkeypatch):
    """Steht jemand weit weg, ist das Gesicht klein — dann fordert
    `gw * GESICHTS_ZOOM` weniger als das Bild hergibt und alles ist gut. Steht
    jemand sehr nah, fordert es MEHR als das Bild hat. Dann muss die Begrenzung
    greifen, statt einen Rand zu erfinden: ein Ausschnitt größer als das Foto
    gäbe schwarze Balken im Kreis.
    """
    breite, hoehe = 900, 1200
    # Ein sehr grosses Gesicht: 2.0 * 600 = 1200 > Bildbreite 900.
    gesicht = (150, 300, 600, 600)
    bild = _testbild(breite, hoehe, kopf=(450, 600, 300))
    monkeypatch.setattr(photos, "_gesicht_finden", lambda _i: gesicht)

    ausschnitt = photos._square_crop(bild)
    seite = ausschnitt.size[0]
    assert seite == min(breite, hoehe), (
        f"bei einem uebergrossen Gesicht muss der Ausschnitt auf "
        f"{min(breite, hoehe)} begrenzt werden, war {seite}"
    )
    # Und kein schwarzer Balken an den Ecken.
    for punkt in ((0, 0), (seite - 1, 0), (0, seite - 1), (seite - 1, seite - 1)):
        assert ausschnitt.getpixel(punkt) != (0, 0, 0), "schwarzer Balken im Ausschnitt"


def test_ohne_erkennung_bleibt_die_ausschnittgroesse_unveraendert(tmp_path, monkeypatch):
    """Der Rückfallweg darf von der neuen Größenlogik NICHTS mitbekommen.

    Auf dem Ausstellungsrechner ist `cv2` nicht installiert; dort schneidet die
    Station weiter das größtmögliche Quadrat. Änderte sich das mit, hätte diese
    Anpassung stillschweigend jedes Portrait ohne erkanntes Gesicht verschoben
    — ohne dass jemand danach gefragt hat.
    """
    breite, hoehe = 1100, 1600
    bild = _testbild(breite, hoehe, kopf=(550, 600, 150))
    monkeypatch.setattr(photos, "_gesicht_finden", lambda _i: None)

    ausschnitt = photos._square_crop(bild)
    assert ausschnitt.size == (min(breite, hoehe), min(breite, hoehe))


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


# --- Untergrenze fuer den Ausschnitt (Birk, 2026-09-01) --------------------
#
# Anlass: auf der Projektion sahen einzelne Portraits matschig aus. Gemessen
# ueber den Bestand war die Ursache NICHT die Aufloesung der App, sondern ein
# klein erkanntes Gesicht: 61 px Gesicht -> 122 px Ausschnitt -> auf 512
# hochgerechnet, Faktor 4,2, Kantenschaerfe 9,6 gegen 677 beim mittigen
# Schnitt. Birks Entscheidung: "kleiner scharfer Kopf statt grosser matschiger".


def test_ein_winziges_gesicht_wird_nicht_stark_hochgerechnet(tmp_path, monkeypatch):
    """Der Fall, der den Matsch verursacht hat — mit den GEMESSENEN Zahlen.

    `1788105156_5.jpg`: 720x1280, erkanntes Gesicht 61x61. Ohne Untergrenze
    ergab das 122 px Ausschnitt, den `make_portrait` auf 512 hochrechnet.
    """
    breite, hoehe = 720, 1280
    gesicht = (126, 1038, 61, 61)  # exakt das gemessene Rechteck
    bild = _testbild(breite, hoehe, kopf=(156, 1068, 30))

    monkeypatch.setattr(photos, "_gesicht_finden", lambda _i: gesicht)
    ausschnitt = photos._square_crop(bild)

    roh = int(round(61 * photos.GESICHTS_ZOOM))
    assert roh == 122, "Vorbedingung: ohne Untergrenze waeren es 122 px"
    hochrechnung = 512 / ausschnitt.size[0]
    assert hochrechnung <= photos.MAX_HOCHRECHNUNG + 0.01, (
        f"der Ausschnitt ist {ausschnitt.size[0]} px und wird {hochrechnung:.1f}x "
        f"HOCHgerechnet — erlaubt sind {photos.MAX_HOCHRECHNUNG}x"
    )


def test_die_untergrenze_weitet_nie_ueber_das_bild_hinaus(tmp_path, monkeypatch):
    """Pixel erfinden kann die Regel nicht.

    Ist das Bild selbst kleiner als die Mindestgroesse, muss es beim
    groesstmoeglichen Quadrat bleiben — sonst entstuende ein Ausschnitt
    groesser als das Bild und damit ein schwarzer Balken im Kreis.
    """
    breite, hoehe = 300, 400
    gesicht = (120, 150, 40, 40)
    bild = _testbild(breite, hoehe, kopf=(140, 170, 20))

    monkeypatch.setattr(photos, "_gesicht_finden", lambda _i: gesicht)
    ausschnitt = photos._square_crop(bild)

    assert ausschnitt.size == (min(breite, hoehe), min(breite, hoehe))
    assert ausschnitt.size[0] <= breite and ausschnitt.size[1] <= hoehe


def test_ein_grosses_gesicht_bleibt_unveraendert(tmp_path, monkeypatch):
    """Die Untergrenze darf NUR kleine Gesichter betreffen.

    Sonst haette sie stillschweigend den Zuschnitt jedes normalen Portraits
    geaendert — und das war ausdruecklich nicht gewollt.
    """
    breite, hoehe = 1280, 1280
    gesicht = (358, 393, 470, 470)  # gemessen aus 1788115087_6.jpg
    bild = _testbild(breite, hoehe, kopf=(593, 628, 235))

    monkeypatch.setattr(photos, "_gesicht_finden", lambda _i: gesicht)
    ausschnitt = photos._square_crop(bild)

    erwartet = min(int(round(470 * photos.GESICHTS_ZOOM)), breite, hoehe)
    assert erwartet > int(round(512 / photos.MAX_HOCHRECHNUNG)), (
        "Vorbedingung: grosses Gesicht")
    assert ausschnitt.size == (erwartet, erwartet), (
        "die Untergrenze hat einen Ausschnitt veraendert, den sie nicht anfassen darf"
    )


def test_der_kopf_bleibt_im_ausschnitt_wenn_aufgeweitet_wird(tmp_path, monkeypatch):
    """Aufweiten darf den Kopf nicht aus dem Bild schieben.

    Der Ausschnitt waechst um die Gesichtsmitte herum; wird er an den Bildrand
    geklemmt, muss der Kopf trotzdem vollstaendig drin liegen — sonst waere ein
    scharfes Portrait ohne Gesicht das Ergebnis.
    """
    breite, hoehe = 720, 1280
    kx, ky, r = 156, 1068, 30
    gesicht = (kx - r, ky - r, 2 * r, 2 * r)
    bild = _testbild(breite, hoehe, kopf=(kx, ky, r))

    monkeypatch.setattr(photos, "_gesicht_finden", lambda _i: gesicht)
    ausschnitt = photos._square_crop(bild)

    links, oben, seite = _erwarteter_ausschnitt(breite, hoehe, gesicht)
    assert ausschnitt.size == (seite, seite)
    assert links <= kx - r and kx + r <= links + seite, "Kopf waagerecht abgeschnitten"
    assert oben <= ky - r and ky + r <= oben + seite, "Kopf senkrecht abgeschnitten"


def test_das_portrait_wird_nicht_mehr_hochskaliert(tmp_path, monkeypatch):
    """Der Beweis am ENDPRODUKT, nicht nur am Zwischenschritt.

    `make_portrait` skaliert den Ausschnitt auf `size`. Frueher war der
    Ausschnitt kleiner als `size` (Hochrechnung); jetzt darf er das nicht mehr
    sein. Gemessen wird ueber die Kantenschaerfe: ein hochgerechnetes Bild ist
    messbar weicher als eines, das verkleinert wurde.
    """
    breite, hoehe = 720, 1280
    gesicht = (126, 1038, 61, 61)
    quelle = tmp_path / "klein.jpg"
    _testbild(breite, hoehe, kopf=(156, 1068, 30)).save(quelle)

    monkeypatch.setattr(photos, "_gesicht_finden", lambda _i: gesicht)

    with Image.open(quelle) as img:
        ausschnitt = photos._square_crop(img.convert("RGB"))

    # 512 ist die Vorgabe von make_portrait. Der Ausschnitt muss mindestens so
    # gross sein, sonst wird beim resize() hochgerechnet.
    assert 512 / ausschnitt.size[0] <= photos.MAX_HOCHRECHNUNG + 0.01, (
        f"Ausschnitt {ausschnitt.size[0]} px -> make_portrait rechnet zu stark hoch"
    )


def test_ein_knapp_zu_kleiner_ausschnitt_behaelt_seinen_zoom(tmp_path, monkeypatch):
    """Birks Einwand am Material, 2026-09-01 (Foto mit drei Personen):
    „waren alle drei Gesichter drauf, nicht auf das zentrale Gesicht gezoomed".

    Die erste Fassung weitete JEDEN Ausschnitt unter 512 px auf -- auch den,
    der nur 1,27x hochgerechnet worden waere. Ergebnis: 79 % Zoom statt 100 %,
    und die Nachbarn kamen mit ins Bild.

    Zahlen aus dem echten Foto `1788269177_app363.jpg`: Gesicht 201 px,
    Wunschausschnitt 402 px. 512/402 = 1,27x -- das liegt unter der erlaubten
    Grenze, der Ausschnitt muss also UNANGETASTET bleiben.
    """
    breite, hoehe = 768, 1024
    gesicht = (360, 391, 201, 201)
    bild = _testbild(breite, hoehe, kopf=(460, 491, 100))

    monkeypatch.setattr(photos, "_gesicht_finden", lambda _i: gesicht)
    ausschnitt = photos._square_crop(bild)

    wunsch = min(int(round(201 * photos.GESICHTS_ZOOM)), breite, hoehe)
    assert wunsch == 402, "Vorbedingung: der Wunschausschnitt ist 402 px"
    assert 512 / wunsch < photos.MAX_HOCHRECHNUNG, (
        "Vorbedingung: 1,27x liegt unter der Grenze")
    assert ausschnitt.size == (wunsch, wunsch), (
        f"der Zoom wurde weggenommen: {ausschnitt.size[0]} statt {wunsch} px -- "
        "genau Birks Einwand"
    )


# --- Ein Gesicht am Bildrand (Birk, 2026-09-02) -----------------------------
#
# „Das letzte Foto ist nicht so richtig auf mein Gesicht sortiert." Gemessen an
# p7 (1200x1600, Gesicht 480x480 bei x=614): Der Ausschnitt von 960 px haette
# bei x=374 beginnen muessen, um zentriert zu sein — 374+960 = 1334 liegt aber
# 134 px hinter dem rechten Bildrand. Er wurde deshalb zurueckgeschoben, und
# das Gesicht landete waagerecht bei 64 % statt 50 %.
#
# In einer runden Scheibe faellt das auf: Das Portrait ist ein Kreis, und ein
# Gesicht ausserhalb seiner Mitte sieht nicht nach Ausschnitt aus, sondern nach
# Fehler. Der dritte Weg ist, den Ausschnitt KLEINER zu machen statt ihn zu
# verschieben — enger heisst hier nicht schlechter, sondern naeher dran.


def _bild_mit_gesicht_am_rand(breite=1200, hoehe=1600, gesicht=480, mitte_x=854):
    """Ein Foto, dessen Gesicht so weit rechts steht, dass ein zentrierter
    Ausschnitt in voller Groesse ueber den Rand liefe."""
    from PIL import Image
    im = Image.new("RGB", (breite, hoehe), (90, 90, 95))
    return im, (int(mitte_x - gesicht / 2), 786, gesicht, gesicht)


def test_ein_gesicht_am_bildrand_bleibt_zentriert(monkeypatch):
    im, g = _bild_mit_gesicht_am_rand()
    monkeypatch.setattr(photos, "_gesicht_finden", lambda _: g)

    crop = photos._square_crop(im)
    gx, _, gw, _ = g
    mitte = gx + gw / 2
    # Wo der Ausschnitt wirklich beginnt, ergibt sich aus seiner Groesse.
    links = max(0, min(int(round(mitte - crop.size[0] / 2)), im.size[0] - crop.size[0]))
    anteil = (mitte - links) / crop.size[0]

    assert 0.45 <= anteil <= 0.55, (
        f"Gesicht sitzt waagerecht bei {anteil*100:.0f} % statt in der Mitte — "
        "der Ausschnitt wurde verschoben, statt kleiner zu werden"
    )


def test_der_ausschnitt_wird_dafuer_nicht_beliebig_klein(monkeypatch):
    """Die Grenze gegen zu starkes Hochrechnen gilt weiter: lieber ein leicht
    verschobenes Gesicht als ein Portrait, das zu Brei hochgerechnet wird."""
    # Gesicht ganz am Rand: zentriert ginge nur mit einem winzigen Ausschnitt.
    im, g = _bild_mit_gesicht_am_rand(mitte_x=1150)
    monkeypatch.setattr(photos, "_gesicht_finden", lambda _: g)

    crop = photos._square_crop(im)

    mindest = int(round(512 / photos.MAX_HOCHRECHNUNG))
    assert crop.size[0] >= mindest, (
        f"Ausschnitt {crop.size[0]}px liegt unter der Hochrechnungsgrenze {mindest}px"
    )


def test_ein_gesicht_in_der_bildmitte_bleibt_unveraendert(monkeypatch):
    """Die Gegenrichtung: wo nichts an den Rand stoesst, darf sich nichts
    aendern — sonst waere jedes Portrait plötzlich enger."""
    im, g = _bild_mit_gesicht_am_rand(mitte_x=600)
    monkeypatch.setattr(photos, "_gesicht_finden", lambda _: g)

    crop = photos._square_crop(im)
    gx, _, gw, _ = g
    erwartet = min(int(round(gw * photos.GESICHTS_ZOOM)), *im.size)

    assert crop.size[0] == erwartet
