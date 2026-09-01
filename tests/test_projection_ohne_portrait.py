"""Die Scheibe ohne Portraet: wie ein Mensch ohne Foto auf der Wand steht.

Seit 2026-09-01 eroeffnet der Mikrofonschalter ein Interview ohne Foto
(kg/session.py, docs/stt-contract.md) -- wer kein Bild von sich will, soll
trotzdem teilnehmen koennen. Auf der Wand darf dieser Mensch dann nicht
unsichtbar sein.

GEMESSEN, nicht vermutet, vor der Aenderung an theme-f: Fuellung rgb(0,0,0)
auf --bg #000000, --ring-width 0, --halo-opacity 0, --ring-echo-width 0 --
alles, was die Scheibe traegt, kommt in theme-f aus dem PNG selbst. Ein
Knoten ohne Bild war damit buchstaeblich nichts: im Kasten um ihn herum
waren 247 von 28392 Pixeln nicht schwarz, und die kamen von der Kante zum
Begriff, nicht von der Scheibe. In den aelteren Themes (a, b, c, e) trug der
Ring sie noch (13775 von 32041 Pixeln).

KEIN Platzhalter-Avatar, kein Fragezeichen, kein Icon: Die Person hat sich
gegen ein Bild entschieden, das ist keine fehlende Datei. Eine einfarbige,
ruhige Scheibe genuegt.
"""

from __future__ import annotations

import io

import pytest

# Ein winziges, gueltiges PNG als Portrait. Data-URI, damit der Test kein Bild
# vom Server holen muss und die Konsole sauber bleibt.
PORTRAIT = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def graph(portrait=None):
    return {
        "version": 1,
        "generated_at": 1.0,
        "max_terms": 32,
        "nodes": [
            {"id": "p1", "type": "person", "portrait": portrait, "created_at": 1.0,
             "hidden": False, "x": 0, "y": 0},
            {"id": "t1", "type": "term", "label": "Selbstbestimmung", "mentions": 3,
             "created_at": 2.0, "hidden": False, "x": 400, "y": 0},
        ],
        "edges": [{"id": "e1", "source": "p1", "target": "t1"}],
        "quotes": [],
    }


@pytest.fixture()
def wall(page, static_server):
    page.goto(f"{static_server}/frontend/projection.html?theme=f")
    page.wait_for_function("window.kgView !== undefined", timeout=15000)
    return page


def zeige(page, g):
    page.evaluate("(g) => window.kgView.update(g)", g)
    page.wait_for_timeout(600)
    return page


def scheibe(page):
    """Die gerenderte Mitte des Personenknotens, als Pixel."""
    masse = page.evaluate(
        """() => {
             const n = window.kgView.cy.$id('p1');
             const p = n.renderedPosition();
             return { x: p.x, y: p.y, w: n.renderedWidth() };
           }"""
    )
    from PIL import Image

    bild = Image.open(io.BytesIO(page.screenshot())).convert("RGB")
    halb = masse["w"] * 0.3
    return list(
        bild.crop(
            (
                int(masse["x"] - halb),
                int(masse["y"] - halb),
                int(masse["x"] + halb),
                int(masse["y"] + halb),
            )
        ).getdata()
    )


def test_die_scheibe_ohne_portrait_ist_auf_der_wand_zu_sehen(wall):
    """Der Kern: sichtbar, nicht unsichtbar. Am Bild gemessen, nicht am Stil --
    ein Stilwert, den das Theme wieder auf Schwarz zieht, saehe im Stiltest
    richtig aus und auf der Wand nach nichts."""
    zeige(wall, graph(portrait=None))

    pixel = scheibe(wall)
    hell = sum(1 for p in pixel if sum(p) > 30)

    assert hell > 0.9 * len(pixel), f"die Scheibe ist nicht da: {hell}/{len(pixel)}"


def test_die_scheibe_ohne_portrait_bleibt_ruhig(wall):
    """Ruhig heisst: eine Farbe, keine Schrift, kein Bild -- und dunkler als
    das hellste, was die Wand sonst zeigt (die weisse Schrift)."""
    zeige(wall, graph(portrait=None))

    stil = wall.evaluate(
        """() => {
             const n = window.kgView.cy.$id('p1');
             return { bild: n.style('background-image'), label: n.style('label'),
                      fuellung: n.style('background-color') };
           }"""
    )
    assert stil["bild"] == "none"
    assert stil["label"] == ""

    pixel = scheibe(wall)
    farben = {p for p in pixel}
    assert len(farben) == 1, f"einfarbig, nicht gemustert: {sorted(farben)[:8]}"
    (farbe,) = farben
    assert max(farbe) < 200, f"zu laut fuer eine Scheibe ohne Bild: {farbe}"


def test_ein_portrait_liegt_weiter_auf_schwarz(wall):
    """Die Gegenprobe zur Aenderung: Der schwarze Grund HINTER einem echten
    Portrait bleibt schwarz. Er ist es, der in theme-f die harte Knotenkante
    verschwinden laesst (--person-fill: #000000); ein grauer Grund unter dem
    auslaufenden Alpha des PNG haette genau die Kante zurueckgeholt."""
    zeige(wall, graph(portrait=PORTRAIT))

    assert wall.evaluate("window.kgView.cy.$id('p1').style('background-color')") == "rgb(0,0,0)"


def test_ein_nachgereichtes_portrait_erreicht_die_wand(wall):
    """Wer sich mitten im Gespraech doch fotografieren laesst, soll sein Bild
    auch sehen. Der Knoten ist zu diesem Zeitpunkt laengst auf der Wand --
    `toCytoscape` setzt die Daten nur beim ANLEGEN, also muss das Portrait
    wie die Traummarkierung nachgezogen werden."""
    zeige(wall, graph(portrait=None))
    zeige(wall, graph(portrait=PORTRAIT))

    stil = wall.evaluate(
        """() => {
             const n = window.kgView.cy.$id('p1');
             return { bild: n.style('background-image'), daten: n.data('portrait'),
                      fuellung: n.style('background-color') };
           }"""
    )
    assert stil["daten"] == PORTRAIT
    assert PORTRAIT in stil["bild"]
    assert stil["fuellung"] == "rgb(0,0,0)"
