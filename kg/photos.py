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


def ring_glow(size: int, inner: float = 0.72, gamma: float = 1.6) -> Image.Image:
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

    Das Maximum sitzt bei 0.18 der Übergangszone, also FRÜH. Zwei Fassungen
    lagen weiter außen (0.75, dann 0.45) und waren nachgemessen zu dunkel: Das
    kräftigste Gold traf dort auf Alpha 19 bzw. 141, und was das Auge sieht,
    ist Farbe MAL Deckkraft. Bei 0.18 liegt die Spitze bei Alpha ≈ 245 — der
    Ring leuchtet, und weil das Gewicht selbst der weiche Verlauf ist, bleibt
    der Übergang trotzdem stufenlos.
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
            # Glockenkurve mit Spitze bei t = 0.75.
            staerke = math.exp(-(((t - 0.18) / 0.30) ** 2))
            px[x, y] = int(round(255 * staerke))
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
