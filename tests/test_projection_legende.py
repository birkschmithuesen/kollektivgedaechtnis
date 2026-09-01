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


def test_die_drei_achsen_stehen_mit_birks_worten_da(wand):
    eintraege = _eintraege(wand)
    assert [e["wort"] for e in eintraege] == [
        "oft genannt",
        "Nachbarn",
        "vor Kurzem gesagt",
    ]


def test_jeder_punkt_traegt_die_farbe_die_der_graph_benutzt(wand):
    """Der eigentliche Zweck: die Legende muss DIESELBEN Farben zeigen wie die
    Begriffe an der Wand. Deshalb gegen die CSS-Variablen des Themes geprüft
    und nicht gegen fest notierte Werte — ein Test mit eigenen Farbwerten
    bliebe grün, während die Legende längst etwas anderes erklärt."""
    aus_theme = wand.evaluate(
        """() => {
             const s = getComputedStyle(document.documentElement);
             const p = document.createElement('span');
             document.body.appendChild(p);
             // Über den Umweg eines echten Elements, damit der Vergleich in
             // derselben Einheit (rgb(...)) läuft wie die gemessenen Punkte.
             return ['--dream-anchor-color', '--dream-neighbour-color', '--dream-recent-color']
               .map((v) => {
                 p.style.background = s.getPropertyValue(v).trim();
                 return getComputedStyle(p).backgroundColor;
               });
           }"""
    )
    assert [e["farbe"] for e in _eintraege(wand)] == aus_theme


def test_die_legende_ist_keine_bedienung(wand):
    """Die Konzeptgrenze: keine Klickfläche, kein Kasten, kein Titel.

    `pointer-events: none` ist der load-bearing Teil — die Wand ist auf der
    Touchfläche bedienbar, und eine Einblendung unten links darf einer
    Besucherin niemals eine Berührung wegnehmen."""
    stil = wand.evaluate(
        """() => {
             const l = document.querySelector('.dream-legende');
             const s = getComputedStyle(l);
             return {
               pointer: s.pointerEvents,
               hintergrund: s.backgroundColor,
               rahmen: s.borderStyle,
               knoepfe: l.querySelectorAll('button, a, input').length,
               ueberschriften: l.querySelectorAll('h1,h2,h3,h4,h5,h6').length,
             };
           }"""
    )
    assert stil["pointer"] == "none", "die Legende fängt Berührungen ab"
    assert stil["knoepfe"] == 0, "die Legende ist bedienbar geworden"
    assert stil["ueberschriften"] == 0, "die Legende hat eine Überschrift bekommen"
    # Kein Kasten: durchsichtiger Hintergrund, kein sichtbarer Rahmen.
    assert stil["hintergrund"] in ("rgba(0, 0, 0, 0)", "transparent")
    assert stil["rahmen"] == "none"


def test_die_legende_verdeckt_das_zitat_nicht(wand):
    """Unten Mitte liegt das Zitat, unten links die Legende. Überschnitten sie
    sich, verdeckte die kleinere Einblendung die größere Aussage.

    Das Zitat muss dafür ERST SICHTBAR GEMACHT werden. Die erste Fassung dieses
    Tests maß die Karte im Ruhezustand — und die ist dann 0x0 Pixel groß
    (gemessen: x=0 y=0 b=0 h=0, opacity 0), weil sie erst beim Antippen einer
    Person Inhalt und Ausdehnung bekommt. Mit einem Rechteck ohne Fläche kann
    sich nichts überschneiden, also war der Test grün, egal wo die Legende lag:
    ein Mutant, der sie mitten über die Zitatkarte schob, überlebte ihn.

    Deshalb wird hier ein echtes Zitat eingeblendet und dann gemessen.
    """
    wand.evaluate(
        """() => {
             const q = document.querySelector('.quote-overlay');
             // `hidden` ist das Attribut, mit dem quote-overlay.js die Karte
             // wegnimmt (panel.hidden = true) — ohne es zu loesen bleibt sie
             // 0x0 gross, auch mit der Klasse `visible`.
             q.hidden = false;
             q.querySelector('.quote-text').textContent =
               'Ein Satz von der Laenge, wie ihn die Wand an einem vollen Tag wirklich zeigt, mit Umbruch.';
             const n = q.querySelector('.quote-name');
             n.hidden = false;
             n.textContent = 'Testperson';
             q.classList.add('visible');
           }"""
    )
    masse = wand.evaluate(
        """() => {
             const l = document.querySelector('.dream-legende').getBoundingClientRect();
             const q = document.querySelector('.quote-overlay').getBoundingClientRect();
             return {
               flaeche: q.width * q.height,
               ueberlappt: !(l.right < q.left || q.right < l.left ||
                             l.bottom < q.top || q.bottom < l.top),
             };
           }"""
    )
    # Erst beweisen, dass ueberhaupt etwas Messbares da ist — sonst prüft der
    # Test wieder nichts (genau der Fehler, den die Fassung davor hatte).
    assert masse["flaeche"] > 10000, (
        f"die Zitatkarte hat keine Ausdehnung ({masse['flaeche']} px²) — "
        "der Überlappungstest würde nichts messen"
    )
    assert not masse["ueberlappt"], "Legende und Zitatkarte überschneiden sich"


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
