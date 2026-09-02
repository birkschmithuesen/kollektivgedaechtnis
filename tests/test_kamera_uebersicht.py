"""„Übersicht" heißt: das ganze Netz. Auch wenn die Schrift zu klein wird.

🔴 WARUM ES DIESE DATEI GIBT (Birk, 2026-09-02, am Gerät):
„Auch wenn ich auf Übersicht klicke, dann zoomt er nicht ganz raus, erst wenn
ich den Zoom-Slider auf ganz Minus mache. Übersicht scheint also falsch
definiert zu sein. Übersicht soll bedeuten, ich sehe alles, das komplette Netz,
auch wenn die Schrift zu klein ist."

VORHER GEMESSEN, an der laufenden Wand:

    nach focusDream     Zoom 2,296     (der Traumausschnitt)
    nach „Übersicht"    Zoom 2,296     ← unverändert, nur der Modus wechselte
    Vollansicht wäre    Zoom 1,520

`setMode('fit')` fährt bei geltendem Traumgebiet dorthin und nicht aufs Netz
(camera.js, `_automaticView`). Der Knopf tat also nicht, was er verspricht.

ZWEI FALLEN, die diese Tests offen halten:

1. **Das Traumgebiet muss verworfen werden.** Ohne das zöge `_automaticView()`
   in derselben Sekunde zurück — der Knopf wäre ein Blinzeln. Ein NEUER Traum
   ruft `focusDream()` und holt die Kamera erneut; verworfen wird allein das
   gerade geltende Gebiet (mit Birk bestätigt: „Übersicht schlägt den laufenden
   Traum, der nächste Traum zieht wieder").

2. **Nicht die Fahransicht.** Ist das Netz zu groß, um es in der Mindestschrift
   zu lesen, liegt `_travelLevel()` ENGER als das Netz. „Alles, auch wenn die
   Schrift zu klein ist" heißt ausdrücklich: die Vollansicht gewinnt gegen die
   Lesbarkeit.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("static_server")


GRAPH = {
    "version": 1,
    "max_terms": 32,
    "nodes": [
        {"id": "p1", "type": "person", "x": 0, "y": 0},
        {"id": "t1", "type": "term", "label": "Hochhaus", "x": 900, "y": 40},
        {"id": "t2", "type": "term", "label": "Ausblick", "x": -900, "y": -40},
        {"id": "t3", "type": "term", "label": "Regelabbau", "x": 60, "y": 700},
    ],
    # `id` ist Pflicht: `term-plate.js::edgeCurve` streut die Boegen ueber
    # `hash32(id)`, damit zwei Kanten zwischen denselben Knoten nicht
    # uebereinanderliegen. Ohne id wirft es.
    "edges": [
        {"id": "e1", "source": "p1", "target": "t1"},
        {"id": "e2", "source": "p1", "target": "t2"},
        {"id": "e3", "source": "p1", "target": "t3"},
    ],
}


@pytest.fixture()
def wand(page, static_server):
    page.goto(f"{static_server}/frontend/projection.html?touch=1&theme=f")
    page.wait_for_function("window.kgView !== undefined", timeout=15000)
    page.evaluate("(g) => window.kgView.update(g)", GRAPH)
    page.wait_for_timeout(800)
    return page


def _zoom(page) -> float:
    return page.evaluate("() => window.kgView.cy.zoom()")


def _vollansicht(page) -> float:
    """Der Zoom, den `cy.fit()` einstellen würde — gemessen und zurückgenommen."""
    return page.evaluate(
        """() => {
             const cy = window.kgView.cy;
             const vor = { p: { ...cy.pan() }, z: cy.zoom() };
             cy.fit(60);
             const z = cy.zoom();
             cy.zoom(vor.z); cy.pan(vor.p);
             return z;
           }"""
    )


def _traumGesetzt(page):
    page.evaluate(
        "() => window.kgView.camera.focusDream(window.kgView.cy.nodes('.term').slice(0, 1))"
    )
    page.wait_for_timeout(6500)  # die Etappe ist 5 s


def test_uebersicht_zeigt_das_ganze_netz_trotz_traumgebiet(wand):
    """Der Fehler vom 2026-09-02, in einem Test."""
    _traumGesetzt(wand)
    im_traum = _zoom(wand)
    voll = _vollansicht(wand)
    assert im_traum > voll * 1.05, (
        f"Vorbedingung kaputt: der Traumausschnitt ist nicht enger als das Netz "
        f"({im_traum:.3f} gegen {voll:.3f})"
    )

    wand.click("text=Übersicht")
    wand.wait_for_timeout(6500)

    assert _zoom(wand) == pytest.approx(voll, rel=0.02), (
        '„Übersicht' + '" zeigt nicht das ganze Netz'
    )


def test_uebersicht_verwirft_das_geltende_traumgebiet(wand):
    """Ohne dieses Vergessen zöge die Automatik sofort zurück — der Knopf wäre
    ein Blinzeln."""
    _traumGesetzt(wand)
    assert wand.evaluate("() => !!window.kgView.camera._dream") is True

    wand.click("text=Übersicht")
    wand.wait_for_timeout(6500)

    assert wand.evaluate("() => !!window.kgView.camera._dream") is False


def test_ein_neuer_traum_holt_die_kamera_wieder(wand):
    """Die Gegenprobe zum Verwerfen. Verworfen wird das GELTENDE Gebiet, nicht
    die Mechanik — sonst stünde die Wand nach einem Druck für immer still."""
    wand.click("text=Übersicht")
    wand.wait_for_timeout(6500)
    voll = _zoom(wand)

    _traumGesetzt(wand)

    assert _zoom(wand) > voll * 1.05, "ein neuer Traum zieht die Kamera nicht mehr"


def test_uebersicht_springt_nicht(wand):
    """🔴 „Ein harter Sprung soll es nie geben, es sollte immer ein Fade sein"
    (Birk). Aus dem Traumausschnitt heraus war ein hartes Rahmen am 2026-09-01
    ein Zoomsprung von 45 % in EINEM Frame.

    Gemessen wird die Bewegung kurz nach dem Druck: Wäre es ein Sprung, stünde
    die Kamera nach 300 ms bereits am Ziel."""
    _traumGesetzt(wand)
    im_traum = _zoom(wand)
    voll = _vollansicht(wand)

    wand.click("text=Übersicht")
    wand.wait_for_timeout(300)
    unterwegs = _zoom(wand)

    assert unterwegs != pytest.approx(voll, rel=0.02), (
        f"nach 300 ms schon am Ziel — das ist ein Sprung, keine Fahrt "
        f"({unterwegs:.3f})"
    )
    assert unterwegs != pytest.approx(im_traum, rel=0.001), (
        "nach 300 ms noch gar nicht losgefahren"
    )


def test_der_regler_laeuft_mit_der_kamera_mit(wand):
    """Vorher stand er immer auf dem linken Anschlag, während die Wand 2,3x
    zeigte — die nächste Hand bewegte ihn um eine Kleinigkeit und das Bild
    sprang um zwei Stufen."""
    wand.click("text=Übersicht")
    wand.wait_for_timeout(6500)
    unten = wand.evaluate("() => Number(document.getElementById('touch-zoom').value)")

    _traumGesetzt(wand)
    wand.wait_for_timeout(400)  # die Nachfuehrung laeuft mit 10 Hz
    im_traum = wand.evaluate("() => Number(document.getElementById('touch-zoom').value)")

    assert im_traum > unten, (
        f"der Griff folgt der Kamera nicht ({unten} -> {im_traum})"
    )


def test_uebersicht_gewinnt_gegen_die_lesbarkeit(wand):
    """🔴 „Auch wenn die Schrift zu klein ist" — Birks zweiter Satz, und der
    schwerer zu treffende.

    Ist das Netz zu gross, um es in der Mindestschrift zu lesen, liegt die
    FAHRANSICHT (`_travelLevel()` = max(Vollansicht, Mindestschrift)) enger als
    das Netz. Ein `uebersicht()`, das auf `_automaticView()` zielt, zeigt dann
    genau nicht alles — und der Fehler faellt nur auf einem grossen Netz auf.

    Ohne diesen Test blieb die Mutation „auf die Fahransicht zielen" gruen: Im
    kleinen Testnetz fallen beide Ansichten zusammen. Der Testgraph hier ist
    derselbe; scharf gestellt wird ueber `setMinLabel`, weil die Mindestschrift
    genau die Groesse ist, die die Fahransicht von der Vollansicht trennt.
    """
    voll = _vollansicht(wand)
    # 🔴 Modus `pan`, sonst wirkt die Mindestschrift gar nicht: `fit` zeigt
    # ohnehin die Vollansicht, die Fahransicht gibt es nur in `pan`. Ohne
    # diese Zeile stand die Vorbedingung bei 0,934 gegen 0,934 — der Test
    # haette nichts geprueft und waere trotzdem gruen zu bekommen gewesen.
    wand.evaluate("() => window.kgView.camera.setMode('pan')")
    # 200 px Mindestschrift auf einer Schrift von 26 Modelleinheiten heisst
    # Zielniveau ~7,7 — weit ueber jeder Vollansicht dieses Netzes.
    wand.evaluate("() => window.kgView.camera.setMinLabel(200)")
    wand.wait_for_timeout(6500)
    eng = _zoom(wand)
    assert eng > voll * 1.5, (
        f"Vorbedingung kaputt: die Fahransicht ist nicht enger als das Netz "
        f"({eng:.3f} gegen {voll:.3f})"
    )

    wand.click("text=Übersicht")
    wand.wait_for_timeout(6500)

    assert _zoom(wand) == pytest.approx(voll, rel=0.02), (
        "die Mindestschrift schlaegt die Uebersicht — sie darf es nicht"
    )
