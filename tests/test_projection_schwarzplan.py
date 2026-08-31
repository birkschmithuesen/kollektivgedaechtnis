"""theme-f „Schwarzplan": Begriffe sind beschriftete Flächen, keine Punkte.

Entwurf vom 2026-08-30, an Cytoscape 3.30.2 headless entwickelt. Diese Tests
sichern die drei Eigenschaften, an denen der Entwurf hängt — und eine Falle,
die ihn still unwirksam machen würde.

Die Falle zuerst, weil sie die teuerste ist: Die offizielle Cytoscape-Doku
beschreibt eine NEUERE Version als die vendorierte 3.30.2. `stripe-*` und
`pie-hole` stehen dort und fehlen im Bundle. Ein Stil, der eine nicht
existierende Eigenschaft setzt, wirft keinen Fehler — er tut einfach nichts.
Deshalb prüft `test_der_stil_erzeugt_keine_warnungen` gegen die Konsole statt
gegen die Doku.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def wall(page, static_server):
    """Die echte Projektionsseite mit theme-f, plus ein kleiner Graph."""
    fehler = []
    page.on("console", lambda m: fehler.append(m.text) if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: fehler.append(str(e)))
    page.goto(f"{static_server}/frontend/projection.html?theme=f")
    page.wait_for_function("window.kgView !== undefined", timeout=15000)
    page.__fehler = fehler
    return page


GRAPH = {
    "version": 1,
    "generated_at": 1.0,
    "max_terms": 32,
    "nodes": [
        {"id": "p1", "type": "person", "portrait": None, "created_at": 1.0,
         "hidden": False, "x": 0, "y": 0},
        {"id": "t1", "type": "term", "label": "Pseudo-Abstimmung vor Baubeginn",
         "mentions": 16, "created_at": 2.0, "hidden": False, "x": 200, "y": 0,
         "in_dream": True, "dream_role": "anchor"},
        {"id": "t2", "type": "term", "label": "Normen-Inventur",
         "mentions": 7, "created_at": 3.0, "hidden": False, "x": 400, "y": 0,
         "in_dream": True, "dream_role": "neighbour"},
        {"id": "t3", "type": "term", "label": "Grün gegen Parkplätze",
         "mentions": 1, "created_at": 4.0, "hidden": False, "x": 600, "y": 0,
         "in_dream": True, "dream_role": "recent"},
        {"id": "t4", "type": "term", "label": "Ruhender Begriff",
         "mentions": 2, "created_at": 5.0, "hidden": False, "x": 800, "y": 0,
         "in_dream": False, "dream_role": ""},
    ],
    "edges": [
        {"id": "e1", "source": "p1", "target": "t1"},
        {"id": "e2", "source": "p1", "target": "t2"},
    ],
    "quotes": [],
}


def zeige(page, graph=None):
    page.evaluate("(g) => window.kgView.update(g)", graph or GRAPH)
    page.wait_for_timeout(400)
    return page


def test_ein_begriff_ist_eine_flaeche_und_kein_punkt(wall):
    """Der Kern des Entwurfs. Ein 14px-Punkt mit Text daneben kostet den Blick
    einen Sprung und verschwindet hinter Portraits; die Fläche löst beides."""
    zeige(wall)

    masse = wall.evaluate(
        """() => {
             const n = window.kgView.cy.$id('t1');
             return { w: n.width(), h: n.height(),
                      valign: n.style('text-valign'),
                      radius: n.style('corner-radius'),
                      randbreite: n.style('border-width'),
                      opacity: Number(n.style('background-opacity')) };
           }"""
    )
    # Deutlich breiter als der alte Punkt (14) — die Tafel trägt die Schrift.
    assert masse["w"] > 100, f"Tafel zu schmal: {masse}"
    assert masse["h"] > 20, f"Tafel zu flach: {masse}"
    # Die Schrift steht IM Knoten, nicht darunter.
    assert masse["valign"] == "center"
    # Seit der zweiten Fassung (Birks echtes Rendering, 2026-08-30) ist der
    # Knoten NICHT mehr unsichtbar: Er ist der runde, nur schwach gefüllte
    # Ring, durch den der Grund durchscheint. Die frühere Fassung malte
    # massive Rechtecke — Birk: „so'n quadratisches Kästchen ist auch nicht
    # cool".
    assert 0 < masse["opacity"] < 1, f"Ring, nicht Fläche: {masse}"


def test_die_tafel_folgt_der_laenge_des_begriffs(wall):
    """Die Größe wird vorab gemessen (`termBox`), weil fcose sie VOR dem
    Zeichnen braucht. Rechnet das Layout mit falschen Flächen, legt es Tafeln
    übereinander, die es für Punkte hält."""
    zeige(wall)

    breiten = wall.evaluate(
        """() => ({
             lang: window.kgView.cy.$id('t1').width(),
             kurz: window.kgView.cy.$id('t2').width(),
           })"""
    )
    assert breiten["lang"] > breiten["kurz"], breiten


def test_die_achsenfarben_faerben_den_ring_und_nicht_die_schrift(wall):
    """Zweite Fassung, nach Birks echtem Rendering (2026-08-30).

    Die erste Fassung füllte die Tafel mit der Achsenfarbe und musste dafür
    die Schriftfarbe pro Fläche nachrechnen (weiß auf Gelb = 1.66:1,
    unlesbar → schwarz). Mit dem RING entfällt das Problem an der Wurzel: Die
    Schrift steht wieder auf schwarzem Grund, also überall 21:1, und die
    Farbe sitzt dort, wo sie im Rendering sitzt — in der Kontur.
    """
    zeige(wall)

    farben = wall.evaluate(
        """() => {
             const f = (id) => {
               const n = window.kgView.cy.$id(id);
               return { rand: n.style('border-color'), schrift: n.style('color') };
             };
             return { anker: f('t1'), nachbar: f('t2'), neu: f('t3') };
           }"""
    )

    def hell(wert):
        zahlen = [int(x) for x in wert.replace("rgb(", "").replace(")", "").split(",")[:3]]
        return sum(zahlen) / 3

    # Die Schrift ist ÜBERALL weiß — das ist der Gewinn des Rings.
    for rolle in ("anker", "nachbar", "neu"):
        assert hell(farben[rolle]["schrift"]) > 200, (rolle, farben[rolle])
    # Und die drei Ringe tragen drei verschiedene Farben.
    raender = {farben[k]["rand"] for k in farben}
    assert len(raender) == 3, raender


def test_ruhende_begriffe_treten_zurueck(wall):
    """Farbe ist Funktion: Nur die fünf Begriffe, aus denen das Bild entsteht,
    tragen eine massive Tafel. Wären alle bunt, hieße die Farbe nichts."""
    zeige(wall)

    werte = wall.evaluate(
        """() => {
             const f = (id) => {
               const n = window.kgView.cy.$id(id);
               return { rand: parseFloat(n.style('border-width')),
                        fuell: Number(n.style('background-opacity')) };
             };
             return { ruhend: f('t4'), imBild: f('t1') };
           }"""
    )
    # Der Ring eines Bildbegriffs ist kräftiger als der eines ruhenden.
    assert werte["imBild"]["rand"] > werte["ruhend"]["rand"], werte
    # Und keiner von beiden ist massiv gefüllt: der Grund scheint durch.
    assert werte["imBild"]["fuell"] < 1, werte
    assert werte["ruhend"]["fuell"] < werte["imBild"]["fuell"], werte


def test_kanten_sind_geschwungen_und_bleiben_es(wall):
    """Der Bogen kommt aus einem Hash der Kanten-ID: eigener Schwung je Kante,
    aber über acht Stunden konstant. Zufall pro Frame würde bei jedem
    Re-Layout zappeln."""
    zeige(wall)

    erst = wall.evaluate(
        """() => {
             const e = window.kgView.cy.$id('e1');
             return { stil: e.style('curve-style'), punkte: e.data('cpd') };
           }"""
    )
    assert erst["stil"] == "unbundled-bezier"
    assert erst["punkte"], "ohne Kontrollpunkte bleibt die Kante gerade"

    # Nach einem erneuten Update derselbe Bogen.
    zeige(wall)
    nochmal = wall.evaluate("() => window.kgView.cy.$id('e1').data('cpd')")
    assert nochmal == erst["punkte"]


def test_der_stil_erzeugt_keine_warnungen(wall):
    """Die teuerste Falle: Eine Stil-Eigenschaft, die es im Bundle nicht gibt,
    wirft keinen Fehler — sie tut nichts. Die Doku beschreibt eine neuere
    Version als die vendorierte 3.30.2 (`stripe-*`, `pie-hole` fehlen dort).
    Gefiltert wird zweierlei, das nichts über den Stil aussagt: das Fehlen von
    `/events` und Favicon (die Seite läuft hier ohne Server), und Cytoscapes
    Hinweis zur `wheelSensitivity` — der stand schon vor diesem Entwurf im
    Code und betrifft die Maussteuerung, nicht die Darstellung. Ein Test, der
    an solchem Rauschen scheitert, wird nach dem dritten Mal ignoriert statt
    gelesen.

    Gegenprobe gefahren: Mit einer erfundenen Eigenschaft (`stripe-size`, in
    3.30.2 nicht vorhanden) schlägt dieser Test fehl. Er beisst also.
    """
    zeige(wall)

    rauschen = (
        "favicon",
        "/events",
        "failed to load resource",
        "eventsource",
        "wheel sensitivity",
    )
    laut = [m for m in wall.__fehler if not any(r in m.lower() for r in rauschen)]
    assert not laut, f"Cytoscape hat gemeckert: {laut}"
