"""Die Kamerafahrt springt nicht mehr, und sie zoomt nicht mehr ins Leere.

Birk, 2026-08-31, Punkte 7 und 8 aus dem Handoff:

  7: „Bei der automatischen Kamerafahrt springt das Bild von Zeit zu Zeit von
      einer Stelle zur anderen, statt weich zu ueberblenden. Nicht durchgehend
      -- immer mal wieder."
  8: „Die Fahrt fokussiert oft einen Begriff am Rand des Graphen. Weil der
      Ausschnitt mittig um diesen Knoten gelegt wird, liegt die Haelfte des
      Bildes ausserhalb des Graphen."

Drei Ursachen GEMESSEN (2026-09-01, dichtes Testnetz im Browser), nicht
geraten -- der Handoff verlangte das ausdruecklich. Mit ihrem jeweiligen
Beitrag am groessten Pan-Sprung eines einzelnen Frames:

  a) `_roamBaseLevel` wurde beim ERSTEN Aufruf berechnet und nie verworfen.
     Nach Graph-Wachstum lag es bis zu 30 % daneben (25 Personen: 0.4919
     richtig; 55 Personen: weiterhin 0.4919 statt 0.3783).   618px -> 238px
  b) `roam.to` wurde beim Fahrtbeginn eingefroren. Waehrend der ~5 s langen
     Fahrt ordnet fcose um, das Ziel wandert 244-536px weg.  238px -> 255px
     (allein kaum Wirkung, zusammen mit c entscheidend)
  c) Die Kamera fuhr WAEHREND des Layout-Umbaus weiter und mass in jedem
     Frame eine andere Wolke.                                255px ->  65px

Zusammen: groesster Sprung 618px -> 65px, Median 6,2px -> 0,0px.

Diese Tests halten die ABSICHTEN fest, nicht die Messzahlen: Ein Test, der
„Maximalsprung < 65px" behauptet, wuerde bei jedem Layout-Tuning rot, ohne
dass etwas kaputt ist. Ursache (c) liegt zur Haelfte in `projection.js`;
hier steht die Haelfte, die `camera.js` beisteuert.
"""

import pytest

from test_camera import CY_STUB
from test_camera_traumzoom import DREAM_STUB


# Was der Stub der Hauptsuite nicht kann: `elements().boundingBox()`. Er
# liefert dort nur `{length: 4}` -- fuer die Rand-Bremse aus Punkt 8 braucht es
# aber eine messbare Knotenwolke. Ergaenzt aus denselben Stub-Begriffen, die
# `DREAM_STUB` schon kennt, damit beide dieselbe Geometrie sehen.
WOLKE_STUB = """
window.cyStub.elements = function () {
  const t = window.cyStub._terms;
  const xs = t.map((n) => n.x), ys = t.map((n) => n.y);
  const x1 = Math.min(...xs) - 50, x2 = Math.max(...xs) + 50;
  const y1 = Math.min(...ys) - 50, y2 = Math.max(...ys) + 50;
  return {
    length: t.length,
    boundingBox: () => ({x1, y1, x2, y2, w: x2 - x1, h: y2 - y1}),
  };
};
"""


@pytest.fixture()
def kamera(page, static_server):
    page.goto(f"{static_server}/frontend/static/test-harness.html")
    page.evaluate(CY_STUB)
    page.evaluate(DREAM_STUB)
    page.evaluate(WOLKE_STUB)
    page.evaluate(
        """async () => {
             const { Camera } = await import('./camera.js');
             window.cam = new Camera(window.cyStub, { panSpeed: 100 });
           }"""
    )
    return page


def test_ein_neuer_graph_verwirft_das_gemerkte_fahrtniveau(kamera):
    """🔴 Punkt 7, Ursache (a).

    `_fitLevel()` merkt sich den Zoom, bei dem das ganze Netz ins Bild passt
    -- ein `cy.fit()` pro Frame waere sonst ein zweiter Schreiber auf dem
    Viewport neben `step()`. Der Cache war aber NUR ueber den Zoomregler zu
    verwerfen, nicht ueber einen gewachsenen Graphen. Nach ein paar Interviews
    fuhr die Kamera damit auf einem Niveau, das zu einer Wolke gehoerte, die es
    nicht mehr gab -- und der naechste Neuaufbau riss den Zoom hart um.

    Der Cache hiess bis zum 2026-09-02 `_roamBaseLevel` und sass in
    `_travelLevel()`; seit die Mindestschrift den Regler ersetzt hat, sitzt er
    eine Ebene tiefer und heisst `_fitLevelCache`. Die Zusicherung ist
    dieselbe geblieben.
    """
    # Eine Mindestschrift unterhalb dessen, was die Vollansicht ohnehin
    # liefert: Dann IST das Fahrtniveau das Fit-Niveau, und ein veralteter
    # Cache ist am Fahrtniveau direkt abzulesen.
    kamera.evaluate("window.cam.setMinLabel(13)")  # 13/26 = 0,5
    kamera.evaluate("window.cam.setMode('pan')")
    erst = kamera.evaluate("window.cam._travelLevel()")
    assert erst > 0
    assert kamera.evaluate("window.cam._fitLevelCache !== undefined"), (
        "der Cache wurde gar nicht erst gefuellt -- dann misst dieser Test nichts"
    )

    # Das Netz waechst: dieselbe Wolke passt jetzt nur noch bei halbem Zoom.
    kamera.evaluate(
        """() => {
             window.cyStub.fit = function (a, b) {
               this._zoom = 0.25;
               this._pan = {x: 0, y: 0};
               this.calls.push(['fit', a]);
             };
           }"""
    )
    kamera.evaluate("window.cam.onGraphChanged()")
    assert kamera.evaluate("window.cam._travelLevel()") == pytest.approx(0.5, rel=1e-6), (
        "onGraphChanged() hat das gemerkte Fahrtniveau nicht verworfen -- "
        f"die Kamera faehrt weiter auf {erst}, das zu einer Wolke gehoert, die es nicht mehr gibt"
    )


def test_die_fahrt_verfolgt_ein_wanderndes_ziel(kamera):
    """🔴 Punkt 7, Ursache (b).

    Eine Fahrt dauert rund fuenf Sekunden. Kommt ein Interview dazu, ordnet
    fcose um und der Zielknoten steht am Ende woanders. War `roam.to` beim
    Start eingefroren, landete die Fahrt neben dem Ziel (gemessen 244-536px)
    -- und der naechste Abschnitt riss das Bild dorthin.
    """
    ziel = kamera.evaluate(
        """() => {
             const c = window.cam;
             c.setMode('pan');
             c._roam = { phase: 'travel', elapsed: 0, clock: 0,
                         targetId: 't1',
                         from: { x: 0, y: 0 },
                         to: { x: -99999, y: -99999 },   // absichtlich falsch
                         duration: 5000 };
             c.step(0.016);
             return { ...c._roam.to };
           }"""
    )
    assert ziel["x"] != -99999, (
        "das Fahrtziel wurde nicht nachgefuehrt -- ein Ziel, das waehrend der "
        "Fahrt wandert, wird nie wieder eingeholt"
    )


def test_der_startpunkt_der_fahrt_bleibt_stehen(kamera):
    """Die Kehrseite von (b): `roam.from` darf sich NICHT bewegen.

    Wanderte der Startpunkt mit dem aktuellen Pan mit, verkuerzte sich die
    Bahn in jedem Frame -- die Fahrt liefe in sich selbst zurueck und kaeme
    nie an. Nur das Ziel wird nachgefuehrt, nie der Ausgangspunkt.
    """
    start = kamera.evaluate(
        """() => {
             const c = window.cam;
             c.setMode('pan');
             c._roam = { phase: 'travel', elapsed: 0, clock: 0,
                         targetId: 't1', from: { x: 111, y: 222 },
                         to: { x: 0, y: 0 }, duration: 5000 };
             c.step(0.016); c.step(0.016);
             return { ...c._roam.from };
           }"""
    )
    assert start == {"x": 111, "y": 222}, (
        f"der Startpunkt der Fahrt hat sich bewegt ({start}) -- die Bahn "
        "verkuerzt sich dann in jedem Frame"
    )


def test_die_kamera_meldet_ob_eine_uebergabe_laeuft(kamera):
    """🔴 Punkt 7, Ursache (c) -- der Teil, der in camera.js liegt.

    Die Wand setzt die Kamera waehrend des Layout-Umbaus aus (`projection.js`,
    tick()), MUSS aber den Handover davon ausnehmen: Der ist eine gewollte,
    1,5 s kurze Bewegung und bliebe sonst mitten in der Luft stehen. Dafuer
    braucht die Wand diese Auskunft.
    """
    assert kamera.evaluate("window.cam.handoverActive") is False

    kamera.evaluate("window.cam.setMode('manual')")
    kamera.evaluate("window.cam.setMode('fit')")
    assert kamera.evaluate("window.cam.handoverActive") is True, (
        "der Rueckweg aus 'manual' loest eine Uebergabe aus, die Kamera meldet "
        "sie aber nicht -- die Wand wuerde sie beim Layout-Umbau abwuergen"
    )


def test_der_ausschnitt_verlaesst_die_knotenwolke_nicht(kamera):
    """🔴 Punkt 8.

    Ein Ziel am Rand hat nur auf einer Seite Nachbarschaft; mittig darauf
    zentriert liegt der halbe Schirm im Leeren. Gemessen 2026-09-01 an der
    echten Wand bei Fahrtniveau 2,5x: schlechtester Ausschnitt 56 % Fuellung,
    mit der Bremse 85 %.

    Hier am Stub geprueft, und zwar die Absicht: Der Ausschnitt fuer den
    aeussersten Knoten darf nicht beliebig weit ueber die Wolke hinausragen.
    """
    ergebnis = kamera.evaluate(
        """() => {
             const c = window.cam, cy = window.cyStub;
             c.setMode('pan');
             c.setMinLabel(65);  // 65/26 = 2,5 -- dasselbe Niveau wie frueher
             const bb = cy.elements().boundingBox({ includeLabels: false });
             // Der aeusserste Stub-Knoten -- der Fall, um den es geht.
             const rand = cy.getElementById('t3');
             const pan = c._panForCentering(rand);
             const z = cy.zoom();
             const links = -pan.x / z, oben = -pan.y / z;
             const rechts = links + cy.width() / z, unten = oben + cy.height() / z;
             // Wie weit ragt das Bild ueber die Wolke hinaus, relativ zur
             // Bildbreite? Ohne Bremse waechst das mit dem Abstand des
             // Zielknotens vom Wolkenrand.
             const ueberLinks = Math.max(0, bb.x1 - links) / (rechts - links);
             const ueberRechts = Math.max(0, rechts - bb.x2) / (rechts - links);
             const ueberOben = Math.max(0, bb.y1 - oben) / (unten - oben);
             const ueberUnten = Math.max(0, unten - bb.y2) / (unten - oben);
             return { ueberLinks, ueberRechts, ueberOben, ueberUnten,
                      wolkeBreiter: bb.w > cy.width() / z,
                      wolkeHoeher: bb.h > cy.height() / z };
           }"""
    )
    # Nur pruefen, wo die Wolke ueberhaupt groesser als das Bild ist -- sonst
    # ist Zentrieren richtig und ein Ueberstand unvermeidlich.
    if ergebnis["wolkeBreiter"]:
        assert ergebnis["ueberLinks"] < 0.2 and ergebnis["ueberRechts"] < 0.2, (
            f"das Bild ragt waagerecht zu weit ueber die Wolke hinaus: {ergebnis}"
        )
    if ergebnis["wolkeHoeher"]:
        assert ergebnis["ueberOben"] < 0.2 and ergebnis["ueberUnten"] < 0.2, (
            f"das Bild ragt senkrecht zu weit ueber die Wolke hinaus: {ergebnis}"
        )


def test_die_bremse_zentriert_ein_kleines_netz_statt_es_an_die_kante_zu_ziehen(kamera):
    """Passt die Wolke ohnehin ins Bild, darf die Bremse nichts festhalten.

    Sonst zoege sie ein Netz, das kleiner als das Fenster ist, an eine Kante,
    und der Bildaufbau waere SCHLECHTER als ohne sie. Genau dieser Fall hat
    beim ersten Messversuch die Messung entwertet: bei Fahrtniveau 1 passte die
    ganze Wolke ins Bild, alle 60 Ziele lieferten identisch 82 % Fuellung --
    gemessen wurde da nicht die Bremse, sondern dass es nichts zu klemmen gab.
    """
    mittig = kamera.evaluate(
        """() => {
             const c = window.cam, cy = window.cyStub;
             c.setMode('pan');
             c.setMinLabel(26);  // 26/26 = 1,0 -- die Vollansicht
             // Eine bewusst KLEINE Wolke: kleiner als das Fenster, damit
             // dieser Fall wirklich eintritt. Frueher stand hier ein
             // pytest.skip, wenn die Wolke zu gross war -- das hiess, der
             // Test prueft nie und meldet trotzdem Erfolg.
             cy.elements = () => ({
               length: 3,
               boundingBox: () => ({x1: -100, y1: -80, x2: 100, y2: 80,
                                    w: 200, h: 160}),
             });
             const bb = cy.elements().boundingBox();
             const z = cy.zoom();
             if (bb.w > cy.width() / z || bb.h > cy.height() / z) return 'zu gross';
             const pan = c._panForCentering(cy.getElementById('t3'));
             const mx = ((bb.x1 + bb.x2) / 2) * z + pan.x;
             const my = ((bb.y1 + bb.y2) / 2) * z + pan.y;
             return { dx: Math.abs(mx - cy.width() / 2),
                      dy: Math.abs(my - cy.height() / 2) };
           }"""
    )
    assert mittig != "zu gross", (
        "die Stub-Wolke passt nicht ins Fenster -- dieser Test misst dann "
        "nichts und darf sich nicht selbst ueberspringen"
    )
    assert mittig["dx"] < 2 and mittig["dy"] < 2, (
        f"die Wolke sitzt {mittig} neben der Bildmitte, obwohl sie ganz "
        "hineinpasst -- die Bremse zieht sie an eine Kante"
    )
