"""Portrait normalisation: arbitrary phone resolution in, uniform circle out (spec 10.2)."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageOps

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


def make_portrait(src: Path, dest: Path, size: int = 512) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(src) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGB")
        square = _square_crop(image)
        square = square.resize((size, size), Image.LANCZOS)

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
