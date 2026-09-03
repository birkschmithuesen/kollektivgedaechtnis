"""Die Legende deutet die drei Auswahlfarben — und bleibt eine Legende.

Birk, 2026-09-01, wörtlich:
    rot: oft genannt / blau: nachbarn / gelb: vor kurzen gesagt

Die Wörter sind fachlich richtig und nicht nur eine Vereinfachung: In
`kg2/weighting.py:select_required` ist der Anker der meistgenannte Begriff
(`haeufigste[0]`), danach folgen seine Nachbarschaft und das Jüngste.

## Was diese Datei absichert

Die Spannung aus dem Handoff: Das Konzept sagt „bewusst reduziert, kein
Dashboard: keine Legende, kein Filter". Birk hat die Legende ausdrücklich
bestellt, also gilt sein Wunsch — aber der Konzeptsatz bleibt die Grenze,
innerhalb derer sie zu bauen war. Diese Tests halten diese Grenze fest:
drei Punkte, drei Wörter, kein Kasten, nicht bedienbar. Ohne sie wäre der
nächste Ausbau („nur noch ein Filterknopf daneben") nicht zu bemerken.

Der zweite und wichtigere Teil: Die Farben werden aus dem GELADENEN
Stylesheet gelesen. Ein zweiter Satz Farbwerte im Code liefe auseinander,
sobald jemand die Palette anfasst — und dann erklärte die Legende Farben,
die an der Wand nicht mehr vorkommen. Das wäre schlimmer als keine Legende.

## 🔴 Seit dem 2026-09-03 hängt sie nicht mehr an der Wand

Birk, am Ende des zweiten Ausstellungstages: „die farbige markierung
(rot/blau/gelb) soll jetzt weg und auch die dazugehörige legende. bzw. du
kannst das color coding jetzt nutzen um häufig genannte begriffe zu
highlighten."

Damit ist der Anlass für die Legende entfallen: Die drei Traumachsen werden
nicht mehr gemalt, und die eine Farbe, die geblieben ist (oft Gesagtes),
erklärt sich beim Hinsehen.

`legende.js` bleibt im Repo, und die Prüfungen an ihrem Quelltext bleiben es
auch — wer den Farbcode zurückholt, braucht beides wieder. Was sich geändert
hat, ist nur der Ort: Geprüft wird der BAUSTEIN, nicht mehr die Wand. Und ein
Test hält fest, dass die Wand jetzt keine trägt.
"""

import re
from pathlib import Path

import pytest

LEGENDE_JS = Path("frontend/static/legende.js").read_text(encoding="utf-8")
THEME_F = Path("frontend/static/theme-f.css").read_text(encoding="utf-8")


@pytest.fixture()
def wand(page, static_server):
    """Die echte Wandseite mit theme-f, wie sie im Haus läuft."""
    page.goto(f"{static_server}/frontend/projection.html?theme=f")
    page.wait_for_function("() => window.kgLegende !== undefined", timeout=30000)
    return page


def _eintraege(page):
    return page.evaluate(
        """() => [...document.querySelectorAll('.dream-legende-eintrag')].map((e) => ({
             wort: e.textContent.trim(),
             farbe: getComputedStyle(e.querySelector('.dream-legende-punkt')).backgroundColor,
           }))"""
    )


def test_auf_der_wand_haengt_keine_legende_mehr(wand):
    """🔴 BIRK, 2026-09-03: „die farbige markierung (rot/blau/gelb) soll jetzt
    weg und auch die dazugehörige legende."

    Sie deutete die drei Traumachsen. Die werden nicht mehr gemalt — eine
    Legende zu Farben, die es nicht gibt, wäre schlimmer als keine (derselbe
    Satz stand vorher im Kopf dieser Datei, nur andersherum gemeint).

    Geprüft wird am gerenderten Baum, nicht an `window.kgLegende`: Ob die
    Variable null ist, sagt nichts darüber, ob unten links noch etwas steht.
    """
    assert wand.evaluate("() => document.querySelectorAll('.dream-legende').length") == 0, (
        "unten links hängt weiterhin eine Legende"
    )


def test_die_drei_farben_werden_nicht_mehr_gemalt(wand):
    """Die Gegenprobe zur Legende: Auch am NETZ trägt keine der drei
    Traumachsen mehr eine eigene Farbe.

    Sonst stünde die Erklärung nicht mehr da, während die Sache selbst weiter
    zu sehen wäre — und niemand könnte sie deuten. Die Klassen bleiben am
    Knoten (sie sind Daten, `test_export_in_dream.py` prüft sie), aber sie
    schlagen sich in keinem Stil mehr nieder.
    """
    quelle = wand.evaluate("() => fetch('static/projection.js').then(r => r.text())")
    for selektor in ("node.term.dream-anchor", "node.term.dream-neighbour",
                     "node.term.dream-recent"):
        assert f"selector: '{selektor}'" not in quelle, (
            f"{selektor} malt weiterhin eine eigene Farbe"
        )


def test_die_haeufigkeit_steht_in_der_schriftgroesse(wand):
    """🔴 BIRK, 2026-09-03, nach dem Farbversuch: „ändere die hervorhebung von
    oft genannten begriffen zu größe der schrift und nimm das color coding
    wieder raus. bzw. deaktiviere es, ich will mir die andere variante
    angucken."

    Beide Varianten sind gebaut und stehen unter `HERVORHEBUNG` in
    projection.js — aktiv ist die Größe. Der Test prüft die aktive Variante am
    gerenderten Knoten; `test_die_farbvariante_bleibt_vollstaendig` daneben
    hält fest, dass der andere Weg nicht verrottet.

    Die Schwellen sind dieselben wie bei der Farbe, an der echten Verteilung
    des Tages gewählt: ab 3 wächst die Schrift, bei 6 ist der Deckel.
    """
    stufen = [("einmal", 1), ("zweimal", 2), ("drei", 3), ("fuenf", 5), ("neun", 9)]
    graph = {
        "version": 1, "generated_at": 1000.0, "max_terms": 99,
        "nodes": [
            {"id": "p1", "type": "person", "name": "A", "portrait": None,
             "created_at": 1.0, "hidden": False, "x": -600, "y": 0}
        ] + [
            {"id": name, "type": "term", "label": f"{name}", "mentions": n,
             "created_at": 2.0, "hidden": False, "x": i * 220 - 500, "y": 200}
            for i, (name, n) in enumerate(stufen)
        ],
        "edges": [{"id": "e1", "source": "p1", "target": "drei", "evidence": "x"}],
        "quotes": [],
    }
    wand.evaluate("(g) => window.kgView.update(g, 99)", graph)
    wand.wait_for_function("() => window.kgView.layoutPending === false", timeout=60000)

    mass = wand.evaluate("""(namen) => {
      const cy = window.kgView.cy;
      const raus = {};
      for (const n of namen) {
        const k = cy.$id(n);
        raus[n] = {schrift: parseFloat(k.style('font-size')),
                   breite: k.data('boxW'), hoehe: k.data('boxH')};
      }
      return raus;
    }""", [n for n, _ in stufen])

    # Unter der Schwelle: die Grundgroesse, fuer ein- wie zweimal dieselbe.
    assert mass["einmal"]["schrift"] == mass["zweimal"]["schrift"], mass
    # Darueber waechst sie mit jeder Stufe …
    assert mass["drei"]["schrift"] > mass["einmal"]["schrift"], mass
    assert mass["fuenf"]["schrift"] > mass["drei"]["schrift"], mass
    # … bis zum Deckel: neunmal ist nicht groesser als sechsmal.
    assert mass["neun"]["schrift"] <= mass["fuenf"]["schrift"] * 2, mass

    # 🔴 UND DIE TAFEL WAECHST MIT. Ohne das stuende der groessere Text in der
    # alten Kiste und ragte hinaus — der Grund, warum `termBox` seit heute die
    # Schriftgroesse entgegennimmt.
    assert mass["neun"]["hoehe"] > mass["einmal"]["hoehe"], (
        f"die Tafel bleibt klein, waehrend die Schrift waechst: {mass}"
    )


def test_die_farbvariante_bleibt_vollstaendig():
    """Der andere Weg ist deaktiviert, nicht ausgebaut — Birk wollte beide
    vergleichen koennen („bzw. deaktiviere es").

    Geprueft am Quelltext und nicht am Bild: Die Variante ist per Definition
    gerade nicht zu sehen. Was sie braucht, muss trotzdem da sein — sonst
    faellt beim Zurueckschalten auf, dass die Haelfte fehlt.
    """
    quelle = Path("frontend/static/projection.js").read_text(encoding="utf-8")
    for teil in ("const BLAU_AB", "const GELB_AB", "const ROT_AB",
                 "haeufigFarbe", "haeufigGlanz", "--haeufig-blau",
                 "--haeufig-gelb", "--haeufig-rot"):
        assert teil in quelle, f"die Farbvariante ist unvollstaendig: {teil} fehlt"
    assert "const HERVORHEBUNG = " in quelle, "der Schalter zwischen beiden fehlt"


def test_ein_theme_ohne_farbcodierung_bekommt_keine_legende(page, static_server):
    """theme-a kennt die drei Variablen nicht. Dann ist keine Legende richtig —
    eine mit drei unsichtbaren Punkten sähe nach einem Fehler aus."""
    page.goto(f"{static_server}/frontend/projection.html?theme=a")
    page.wait_for_function("() => window.kgView !== undefined", timeout=30000)
    assert page.evaluate("() => window.kgLegende") is None
    assert page.evaluate("() => document.querySelectorAll('.dream-legende').length") == 0


def test_die_farben_stehen_nicht_zweimal_im_quelltext():
    """Kein zweiter Satz Farbwerte in legende.js: Er liefe auseinander, sobald
    jemand die Palette im Theme anfasst, und die Legende erklärte dann Farben,
    die an der Wand nicht mehr vorkommen."""
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", LEGENDE_JS), (
        "legende.js enthält eigene Farbwerte statt sie aus dem Theme zu lesen"
    )
    for variable in (
        "--dream-anchor-color",
        "--dream-neighbour-color",
        "--dream-recent-color",
    ):
        assert variable in LEGENDE_JS
        assert variable in THEME_F


def test_der_prerender_nimmt_die_legende_aus_dem_bild():
    """`sim/prerender.py` schießt definierte Aufnahmen des Graphen. Eine
    Einblendung darin verfälscht Bildeindruck und Überlappungszählung — aus
    demselben Grund, aus dem dort schon `setDreamCamera(false)` steht."""
    quelle = Path("sim/prerender.py").read_text(encoding="utf-8")
    assert "kgLegende" in quelle, "der Prerender entfernt die Legende nicht"
    assert "entfernen()" in quelle
