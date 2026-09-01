"""Die Wand darf waehrend einer Uebergabefahrt nicht stehenbleiben.

🔴 Gemessen 2026-09-01 an der echten Wand (render-harness.html, echtes
cytoscape, Replay-Graph 19c):

    Handover nach 1000 ms echter Zeit:  elapsed = 300 ms
    Handover nach weiteren 1000 ms:     elapsed = 300 ms   (unveraendert)
    Seitenfehler:                       "capped is not defined"

`ROAM.handoverMs` sind 5000 ms — die Fahrt kam also 300 ms weit und stand
dann fuer immer. Ursache war ein uebersehener Bezeichner in
`projection.js::portraitWidth()`: der Commit „Beide Regler wirken wieder"
(7e6307c, 2026-09-01) hat `capped` in `gewuenscht` umbenannt, an drei von
vier Stellen. Die vierte liegt im Blend-Zweig, also in genau dem Ast, den
NUR ein laufender Handover betritt (`portraitCapBlend` liegt sonst auf
glatt 0 oder 1 und kehrt vorher um).

Warum das die ganze Wand anhaelt und nicht nur die Portraitgroesse:
`applyPortraitSize()` haengt am `zoom`-Ereignis von cytoscape. Der Fehler
fliegt also aus `cy.zoom()` heraus, mitten durch `Camera._advanceHandover()`
hindurch, bis in `tick()` — und `tick()` kommt nie bis zu seinem
`requestAnimationFrame(tick)`. Damit ist die Bildschleife der Projektion
tot, `_handover` wird nie geraeumt und jede spaetere Ansichtsaenderung
passiert nur noch hart und synchron.

Geprueft wird die WIRKUNG (die Fahrt kommt an, die Seite wirft nichts), nicht
der Bezeichner: ein Test auf `gewuenscht` im Quelltext waere eine Kopie der
Zeile und liesse den naechsten Tippfehler in einer anderen Zeile durch.
"""

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def wand(browser, static_server):
    """Die echte Wand mit dem echten Replay-Graphen.

    Modulweit und nicht je Test: das fcose-Layout über 223 Knoten kostet 8 bis
    16 Sekunden, und `-k camera` ist die Schleife, in der am Aufbautag
    gearbeitet wird — neunmal dasselbe Layout zu rechnen hat die von 40 s auf
    3:39 gebracht. Jeder Test hier setzt Modus, Zoomregler und Traumgebiet zu
    Beginn seiner eigenen Messung selbst, hängt also nicht daran, was der
    vorige hinterlassen hat.

    Der Graph wird dabei NICHT verändert (keine Knoten verschoben, keine
    Neuberechnung) — das ist die Bedingung, unter der das Teilen zulässig ist.
    """
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    page.goto(f"{static_server}/frontend/static/render-harness.html")
    page.wait_for_function("window.kgView !== undefined")
    graph = json.loads((REPO / "sim" / "data" / "graph-19c.json").read_text(encoding="utf-8"))
    page.evaluate(
        "(args) => window.kgView.update(args[0], args[1])",
        [graph, graph["max_terms"]],
    )
    page.wait_for_function("() => window.kgView.layoutPending === false", timeout=60000)
    yield page
    page.close()


def test_die_uebergabefahrt_kommt_an_statt_die_bildschleife_zu_toeten(wand):
    fehler = []
    wand.on("pageerror", lambda e: fehler.append(str(e)))

    # Der Weg, den ein Besucher taeglich ausloest: Hand weg vom Touchscreen,
    # der Operator (oder die Autonomie) stellt auf 'fit' zurueck.
    wand.evaluate("window.kgView.camera.setMode('manual')")
    wand.evaluate("window.kgView.camera.setMode('fit')")
    assert wand.evaluate("window.kgView.camera.handoverActive") is True, (
        "ohne laufende Uebergabe misst dieser Test nichts"
    )

    # Der rAF-Tick der Projektion faehrt sie frei zu Ende: 5 s plus Reserve.
    wand.wait_for_function(
        "() => window.kgView.camera.handoverActive === false", timeout=15000
    )
    assert not fehler, f"die Wand wirft waehrend der Uebergabefahrt: {fehler}"


def test_die_bildschleife_laeuft_nach_der_uebergabe_weiter(wand):
    """Die Gegenprobe: nicht nur angekommen, sondern auch noch am Leben.

    Ein `handoverActive === false` allein waere zu wenig — es koennte auch
    heissen, dass die Fahrt im letzten Frame durchgereicht wurde und die
    Schleife danach starb. Deshalb hier ein Beweis fuer FORTLAUFENDE Frames.
    """
    wand.evaluate("window.kgView.camera.setMode('manual')")
    wand.evaluate("window.kgView.camera.setMode('fit')")
    wand.wait_for_function(
        "() => window.kgView.camera.handoverActive === false", timeout=15000
    )

    # Frames zaehlen, nachdem die Uebergabe durch ist.
    wand.evaluate(
        """() => {
             window.__frames = 0;
             const zaehle = () => { window.__frames += 1; requestAnimationFrame(zaehle); };
             requestAnimationFrame(zaehle);
           }"""
    )
    wand.wait_for_timeout(300)
    frames = wand.evaluate("window.__frames")
    assert frames > 5, f"nur {frames} Frames in 300 ms — die Bildschleife steht"

    # Und die Kamera bewegt sich darin auch wirklich noch.
    wand.evaluate("window.kgView.camera.setMode('pan')")
    vorher = wand.evaluate("window.kgView.cy.zoom()")
    wand.wait_for_timeout(500)
    nachher = wand.evaluate("window.kgView.cy.zoom()")
    assert nachher != vorher, (
        "der Zoom steht nach 500 ms exakt still — die Atembewegung der Fahrt "
        "schreibt jeden Frame, also laeuft `step()` nicht mehr"
    )
