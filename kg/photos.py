"""Portrait normalisation: arbitrary phone resolution in, uniform circle out (spec 10.2)."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageChops, ImageOps

# Faces sit above the vertical centre in booth portraits.
VERTICAL_BIAS = 0.35


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
    width, height = image.size
    side = min(width, height)
    left = (width - side) // 2
    if height > side:
        top = int((height - side) * VERTICAL_BIAS)
    else:
        top = 0
    return image.crop((left, top, left + side, top + side))
