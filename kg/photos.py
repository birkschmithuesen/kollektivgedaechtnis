"""Portrait normalisation: arbitrary phone resolution in, uniform circle out (spec 10.2).

Der Ausschnitt folgt dem Gesicht, wenn eines gefunden wird, und schneidet sonst
mittig wie zuvor (Birk, 2026-09-01: „Was ist mit dem face tracking um den
Ausschnitt vom portrait richtig zu wählen?").
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageOps

log = logging.getLogger(__name__)

# Faces sit above the vertical centre in booth portraits.
#
# Zwei getrennte Werte, seit der Ausschnitt dem Gesicht folgt (Birk, 2026-09-01):
#
# GESICHTS_BIAS gilt, wenn ein Gesicht erkannt wurde. 0.46 heißt: über dem Kopf
# bleibt etwa ein Fünftel der Bildhöhe frei, unter dem Kinn knapp ein Drittel.
# Birks Vorgabe war „ein bisschen mehr Haare, ein bisschen weniger Hals, nicht
# viel" — gemessen an seinem eigenen Foto liegt der Kopf damit bei 21 % Luft
# oben statt 17 % (0.42) und ohne in Richtung „zu viel Decke" zu kippen (ab
# etwa 0.58).
#
# VERTICAL_BIAS gilt weiter für den Rückfall ohne Erkennung. Der Wert bleibt
# bei 0.35, weil dort die Bildmitte und nicht der Kopf der Bezugspunkt ist —
# ihn mitzuziehen würde jedes Portrait ohne erkanntes Gesicht verschieben,
# ohne dass jemand danach gefragt hat.
VERTICAL_BIAS = 0.35
GESICHTS_BIAS = 0.46

# Wie groß ist der Ausschnitt, gemessen an der Breite des erkannten Gesichts?
#
# Das war der eigentliche Fund hinter Birks „der Ausschnitt ist zu tief": Die
# Position war es gar nicht. Der Ausschnitt nahm die volle Bildbreite, und
# damit füllte das Gesicht nur 20 % der Kreisfläche — 45 % der Fläche lag
# unter dem Kinn. Den Ausschnitt zu verschieben ändert daran fast nichts, weil
# er schlicht zu groß ist.
#
# 2.0 bedeutet: der Ausschnitt ist doppelt so breit wie das Gesicht, das
# Gesicht füllt also 50 % der Breite. Das ist der übliche Bereich für ein
# Porträt (45–60 %); vorher waren es 40 %.
GESICHTS_ZOOM = 2.0

# Der Ausschnitt wird NIE kleiner als das fertige Portrait (Birk, 2026-09-01:
# „kleiner scharfer Kopf statt großer matschiger").
#
# Der Ausschnitt wird am Gesicht bemessen, das fertige Portrait ist aber immer
# `portrait_size` (512) groß. Steht jemand weit weg, ist das Gesicht klein —
# und ein kleiner Ausschnitt wird auf 512 HOCHgerechnet. Gemessen am 2026-09-01
# über den Bestand: ein Gesicht von 61 px ergab 122 px Ausschnitt, also Faktor
# 4,2 Hochrechnung, und eine Kantenschärfe von 9,6 gegenüber 677 beim mittigen
# Schnitt — 1 %. Das ist der Matsch, den Birk auf der Projektion gesehen hat.
#
# Deshalb: ein Ausschnitt unter der Zielgröße wird aufgeweitet, statt
# hochgerechnet zu werden. Der Kopf sitzt dann kleiner im Kreis (es kommt mehr
# Umgebung dazu), bleibt aber scharf. Die Alternative wäre gewesen, kleine
# Gesichter zu verwerfen und mittig zu schneiden — das hätte den Kopf aber auch
# aus der Mitte verloren, sobald jemand seitlich steht.
#
# 🔴 NICHT über eine höhere App-Auflösung lösbar. Gemessen: mehr Auflösung
# liefert UNSCHÄRFERE Portraits (−6 bis −11 %), weil die Erkennung dann öfter
# greift und der engere Gesichtsausschnitt weniger echte Pixel hat als der
# weite mittige Schnitt. Details in `docs/STAND.md` §2e.
MINDEST_AUSSCHNITT = 512


def soft_disc_mask(size: int, inner: float = 0.72, gamma: float = 1.6) -> Image.Image:
    """Alpha-Maske: voll deckend bis inner*r, dann glatt auf 0 am Rand.

    Birks Wunsch vom 2026-08-30 („mit 'nem kleinen Feather-Fadeout an der
    Seite"). Der weiche Rand MUSS aus dem PNG kommen: Cytoscape hat keine
    Eigenschaft, die eine Knotenkante ausblendet — kein Blur, kein Schatten,
    keine Maske. Headless nachgemessen läuft der Helligkeitsverlauf am Rand
    danach 48 → 29 → 24 aus statt hart 136 → 26.

    inner  Ab welchem Radiusanteil das Ausblenden beginnt. 0.72 lässt das
           Gesicht unangetastet und nimmt nur den Rand weg. Kleiner = weicher,
           aber unter ~0.6 franst das Portrait sichtbar aus.
    gamma  Krümmung des Verlaufs. >1 hält das Bild länger deckend und lässt es
           dann schneller weg — das sieht auf Schwarz sauberer aus als ein
           linearer Abfall, der einen grauen Saum stehen lässt.

    Der Doppelauflösungs-Trick der alten Maske (size*4 + LANCZOS) entfällt: Er
    existierte nur, um die harte Ellipsenkante zu glätten. Ein Verlauf braucht
    kein Antialiasing.
    """
    mask = Image.new("L", (size, size), 0)
    px = mask.load()
    centre = (size - 1) / 2.0
    radius = size / 2.0
    r_inner = inner * radius

    for y in range(size):
        dy = y - centre
        for x in range(size):
            d = math.hypot(x - centre, dy)
            if d <= r_inner:
                alpha = 255
            elif d >= radius:
                alpha = 0
            else:
                t = (radius - d) / (radius - r_inner)
                alpha = int(round(255 * (t**gamma)))
            px[x, y] = alpha
    return mask


#: Der Goldton des Rings — identisch mit `--ring-color` in theme-f.css. Er
#: steht hier ein zweites Mal, weil das PNG erzeugt wird, lange bevor ein
#: Stylesheet existiert; ändert jemand die Palette, muss er beide anfassen.
RING_RGB = (201, 162, 39)


def ring_glow(size: int, inner: float = 0.45, gamma: float = 1.6) -> Image.Image:
    """Das GEWICHT des Rings im Verlauf des Portraits (Graustufenmaske).

    Gibt bewusst eine Maske zurueck und kein eingefaerbtes Bild: Die zweite
    Fassung malte hier abgedunkeltes Gold und benutzte dasselbe Bild als
    Ueberblendgewicht — dadurch wurde der Ring doppelt gedaempft und kam als
    dunkler Graustich an (gemessen 106,96,66 statt 201,162,39).

    Birk, 2026-08-30: „Der Ring um die Porträts ist viel zu schwach und viel
    zu breit. Der Fadeout von den Porträts soll in ein Fade-in von dem Ring
    gehen. Der Ring soll gar nicht außerhalb um die Porträts liegen, sondern
    den Fade-Übergang der Porträts darstellen."

    Genau dort, wo das Bild ausblendet, blendet der Goldton ein — beides in
    derselben Zone zwischen `inner*r` und `r`, nicht nacheinander. Ein
    Cytoscape-`border` kann das prinzipiell nicht: Er ist eine Linie AUF der
    Knotenkante, hat eine Breite und zwei harte Ränder, und er läge außerhalb
    genau des Verlaufs, den er ersetzen soll. Deshalb wird der Ring hier ins
    RGB des PNG gemalt und die Alpha-Maske darüber gelegt.

    MONOTON STEIGEND, keine Glocke (Birk, 2026-08-30, am Bild): „Der Fade-out
    soll einfach von hundert Prozent Porträt den Verlauf in hundert Prozent
    Gold machen." Und ausdrücklich: dahinter kein Ring mehr.

    Alle früheren Fassungen waren Glockenkurven mit einer Spitze irgendwo in
    der Zone — dadurch entstand genau das, was er wegwollte: erst das Bild,
    dann eine dunkle Lücke, dann ein separat wirkender Ring. Am gelieferten
    Bild nachgemessen fiel das Profil zwischen d=36 und d=48 auf (48,27,6) ab,
    bevor bei d=54 das Gold kam.

    Jetzt steigt das Gewicht stetig von 0 (innen, volles Portrait) auf 255
    (außen, volles Gold) und bleibt dort. Es gibt keine Stelle mehr, an der
    der Goldanteil wieder abnimmt, also auch keine Lücke und keinen zweiten
    Ring. Das Ausblenden übernimmt allein die Alpha-Maske.

    Der Exponent 0.8 macht den Verlauf leicht vorderlastig: Gold ist früh
    erkennbar, solange die Scheibe noch gut deckt — sichtbar ist Farbe MAL
    Deckkraft, und das Alpha fällt zum Rand hin ohnehin.
    """
    glow = Image.new("L", (size, size), 0)
    px = glow.load()
    centre = (size - 1) / 2.0
    radius = size / 2.0
    r_inner = inner * radius

    for y in range(size):
        dy = y - centre
        for x in range(size):
            d = math.hypot(x - centre, dy)
            if d <= r_inner or d >= radius:
                continue
            t = (d - r_inner) / (radius - r_inner)  # 0 innen … 1 außen
            # Voll bei t = 0.6 statt erst ganz aussen: Dort deckt die Scheibe
            # noch (Alpha ~200), und sichtbar ist Farbe MAL Deckkraft. Waere
            # das Gold erst bei t = 1 voll, faende es nur noch Alpha 0 vor.
            px[x, y] = int(round(255 * min(1.0, (t / 0.6) ** 0.9)))
    return glow


def _gesicht_finden(image: Image.Image) -> tuple[int, int, int, int] | None:
    """Das Gesicht im Bild, als (x, y, breite, hoehe) — oder None.

    OpenCVs Haar-Kaskade, und zwar OPTIONAL: `cv2` ist keine Abhängigkeit
    dieses Projekts. Fehlt es, gibt diese Funktion None zurück und der
    Ausschnitt bleibt exakt der mittige von vorher. Das ist bewusst so
    herum gebaut:

    - Die Station läuft auf einem Windows-Rechner ohne GPU und soll
      offlinefähig bleiben. `opencv-python-headless` sind ~50 MB plus numpy,
      und dieses Paket am Ausstellungstag nachzuinstallieren ist ein Eingriff
      in eine laufende Anlage — nicht die Sorte Änderung, die man zwischen
      zwei Interviews macht.
    - Der Handoff verlangt ausdrücklich, die Erkenner NICHT ohne Messung an
      echten Booth-Fotos gegeneinander zu entscheiden (Haar-Kaskade gegen
      `face_recognition`/dlib). Solche Fotos lagen hier nicht vor — sie
      liegen auf dem Ausstellungsrechner, der beim Bau nicht erreichbar war.

    Deshalb ist der Weg gebaut und abgeschaltbar, aber die Wahl des Erkenners
    ist NICHT getroffen: Ist `cv2` installiert, wird die Kaskade benutzt;
    ist sie es nicht, ändert sich am heutigen Verhalten nichts. Wer den
    Vergleich nachholt, tauscht genau diese Funktion.

    Bei mehreren Gesichtern gewinnt das GRÖSSTE. Am Booth steht die befragte
    Person vorn und der Interviewer weiter hinten, also ist das größte
    Gesicht das gemeinte. Das ist eine ästhetische Setzung, die der Handoff
    als solche markiert — sie steht hier an einer Stelle, an der man sie
    ändern kann, statt verteilt in der Zuschnittlogik.
    """
    try:
        import cv2  # noqa: PLC0415 — optional, siehe Docstring
        import numpy as np  # noqa: PLC0415
    except ImportError:
        return None

    try:
        # OpenCV 5 hat `CascadeClassifier` UND die mitgelieferten
        # Kaskadendateien entfernt (gemessen 2026-09-01 an 5.0.0:
        # `cv2.CascadeClassifier` existiert nicht mehr, `cv2/data/` enthält
        # nur noch `__init__.py`). Die erste Fassung dieser Funktion rief
        # genau das auf — auf einer 5er-Installation wäre sie stillschweigend
        # in den except-Zweig gelaufen und hätte IMMER mittig geschnitten,
        # ohne dass jemand einen Fehler gesehen hätte. Genau die Sorte
        # Änderung, die „gebaut, plausibel, wirkungslos" aussieht.
        #
        # Deshalb wird geprüft, was die installierte Fassung wirklich kann,
        # statt es anzunehmen.
        if not hasattr(cv2, "CascadeClassifier"):
            log.warning(
                "OpenCV %s kennt keine Haar-Kaskade mehr (ab 5.0 entfernt) — "
                "mittiger Schnitt. Für die Gesichtserkennung "
                "'opencv-python-headless<5' installieren.",
                getattr(cv2, "__version__", "?"),
            )
            return None

        kaskade_datei = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        if not Path(kaskade_datei).exists():
            log.warning("Kaskadendatei fehlt (%s) — mittiger Schnitt", kaskade_datei)
            return None

        grau = np.array(image.convert("L"))
        kaskade = cv2.CascadeClassifier(kaskade_datei)
        if kaskade.empty():
            return None
        # minSize relativ zur Bildbreite: ein Booth-Foto vom Handy ist mal
        # 1280 und mal 4032 Pixel breit, ein fester Pixelwert wäre auf dem
        # einen blind und auf dem anderen voller Fehltreffer.
        mindest = max(30, int(min(image.size) * 0.08))
        treffer = kaskade.detectMultiScale(
            grau, scaleFactor=1.1, minNeighbors=5, minSize=(mindest, mindest)
        )
        if len(treffer) == 0:
            return None
        x, y, w, h = max(treffer, key=lambda t: int(t[2]) * int(t[3]))
        return int(x), int(y), int(w), int(h)
    except Exception as exc:  # eine Erkennung darf die Station nie anhalten
        log.warning("Gesichtserkennung fehlgeschlagen, mittiger Schnitt (%s)", exc)
        return None


def make_portrait(src: Path, dest: Path, size: int = 512) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(src) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGB")
        square = _square_crop(image)
        square = square.resize((size, size), Image.LANCZOS)

    # Der Ring wird ÜBERBLENDET, nicht addiert. Erste Fassung addierte ihn,
    # damit er das ausblendende Bild „aufhellt" — nachgemessen kam davon nichts
    # an: Auf einem hellen Portrait (RGB um 185) verschwindet ein addierter
    # Goldton im Bildinhalt, gemessen (184,176,157), also Grau statt Gold.
    # Eine gewichtete Überblendung setzt den Ton dort durch, wo die Kurve ihn
    # will, unabhängig davon was im Bild liegt — und bleibt trotzdem weich,
    # weil das Gewicht selbst der weiche Verlauf ist.
    square = Image.composite(
        Image.new("RGB", (size, size), RING_RGB), square, ring_glow(size)
    )

    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(square, (0, 0), soft_disc_mask(size))
    out.save(dest, format="PNG")
    return dest


def _square_crop(image: Image.Image) -> Image.Image:
    """Der quadratische Ausschnitt — am Gesicht, sonst mittig.

    Bis 2026-09-01 schnitt diese Funktion immer mittig und wusste nichts
    davon, wo im Bild ein Mensch steht. Wer sich seitlich hinstellte, wurde
    angeschnitten (Birks Punkt 1 im Handoff).

    Der mittige Schnitt ist ausdrücklich KEIN Fehlerfall, sondern der
    Rückfallweg: kein Gesicht gefunden, `cv2` nicht installiert, Erkennung
    unsicher — dann gilt wieder, was vorher galt.

    Seit 2026-09-01 unterscheiden sich die beiden Wege auch in der GRÖSSE des
    Ausschnitts: mit erkanntem Gesicht wird er am Gesicht bemessen
    (`GESICHTS_ZOOM`), ohne bleibt es beim größtmöglichen Quadrat. Deshalb
    steht `side` in beiden Zweigen getrennt und nicht mehr davor.
    """
    width, height = image.size

    gesicht = _gesicht_finden(image)
    if gesicht is not None:
        gx, gy, gw, gh = gesicht
        # Der Ausschnitt wird AM GESICHT bemessen, nicht an der Bildbreite.
        # Vorher nahm er immer `min(breite, hoehe)` — bei einem Handyfoto also
        # die volle Breite. Gemessen an Birks Foto füllte das Gesicht damit nur
        # 20 % der Kreisfläche und 45 % lagen unter dem Kinn; „zu tief" war in
        # Wahrheit „zu weit weg". Der Ausschnitt kann nie größer werden als das
        # Bild — steht jemand weit weg, greift `min(...)` und es bleibt beim
        # bisherigen Verhalten, statt einen Rand zu erfinden.
        side = min(int(round(gw * GESICHTS_ZOOM)), width, height)

        # Untergrenze: lieber mehr Umgebung zeigen als hochrechnen. Steht die
        # Person weit weg, ist `gw * GESICHTS_ZOOM` kleiner als das fertige
        # Portrait, und `make_portrait` würde den Ausschnitt vergrößern —
        # gemessen bis Faktor 4,2 und damit sichtbar matschig. `min(...)` hält
        # die Aufweitung im Bild: ist das Bild selbst kleiner als
        # MINDEST_AUSSCHNITT, bleibt es beim größtmöglichen Quadrat, denn Pixel
        # erfinden kann auch diese Regel nicht.
        side = min(max(side, MINDEST_AUSSCHNITT), width, height)

        # Waagerecht auf die Gesichtsmitte.
        left = int(round(gx + gw / 2 - side / 2))
        # Senkrecht so, dass der Kopf dort landet, wo GESICHTS_BIAS ihn haben
        # will: über dem Kopf ein knappes Fünftel Luft, darunter Hals und
        # Schultern. Auf die Gesichtsmitte zentriert säße der Kopf zu tief.
        top = int(round(gy + gh / 2 - side * GESICHTS_BIAS))
        # In die Bildgrenzen schieben, statt zu beschneiden: ein Ausschnitt,
        # der über den Rand ragt, gäbe sonst einen schwarzen Balken im Kreis.
        # Verschieben verliert Zentrierung, ein Balken verliert das Bild.
        left = max(0, min(left, width - side))
        top = max(0, min(top, height - side))
        return image.crop((left, top, left + side, top + side))

    side = min(width, height)

    left = (width - side) // 2
    if height > side:
        top = int((height - side) * VERTICAL_BIAS)
    else:
        top = 0
    return image.crop((left, top, left + side, top + side))
