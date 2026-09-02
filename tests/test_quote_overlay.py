"""Quote on touch — the parked nice-to-have from the design spec, built.

Runs against the REAL Cytoscape instance in render-harness.html, not a stub:
the whole feature is a bet that `tap` fires on person nodes even in the
automatic camera mode (where `autoungrabify` is on), and a stub would happily
confirm that bet without testing it.
"""

import pytest

GRAPH = {
    "version": 1,
    "max_terms": 99,
    "nodes": [
        {"id": "p1", "type": "person", "portrait": "", "hidden": False, "created_at": 1,
         "x": 100, "y": 100, "name": "Frau Kirchner"},
        # Zitat ja, Name nein: der Normalfall für jede Person, die sich nicht
        # vorgestellt hat oder deren verhörten Namen der Operator gelöscht hat.
        {"id": "p2", "type": "person", "portrait": "", "hidden": False, "created_at": 2,
         "x": 400, "y": 100, "name": None},
        # A person with no quote at all: extraction can fail (status=failed in
        # the runbook) and the node still stands.
        {"id": "p3", "type": "person", "portrait": "", "hidden": False, "created_at": 3,
         "x": 700, "y": 100},
        {"id": "t1", "type": "term", "label": "Holzbau", "mentions": 2, "hidden": False,
         "created_at": 4, "x": 250, "y": 300},
    ],
    "edges": [
        {"id": "e1", "source": "p1", "target": "t1"},
        {"id": "e2", "source": "p2", "target": "t1"},
    ],
    "quotes": [
        {"id": "q1", "person_id": "p1", "text": "Wir bauen viel zu viel neu."},
        {"id": "q2", "person_id": "p1", "text": "Der Bestand ist das Material."},
        {"id": "q3", "person_id": "p2", "text": "Ein Haus muss nach Zuhause riechen."},
    ],
}


@pytest.fixture()
def wall(page, static_server):
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(f"{static_server}/frontend/static/render-harness.html")
    page.wait_for_function("window.kgView !== undefined")
    page.evaluate(
        """async (graph) => {
             const { attachQuoteOverlay } = await import('./quote-overlay.js');
             window.kgQuotes = attachQuoteOverlay(window.kgView);
             window.kgView.update(graph);
             window.kgQuotes.setGraph(graph);
           }""",
        GRAPH,
    )
    page.wait_for_function("window.kgView.layoutPending === false")
    return page


def _tap(page, node_id):
    """Click the node where it is actually drawn — a real pointer event.

    Deliberately NOT `cy.getElementById(id).emit('tap')`: a synthetic tap
    crashes this vendored Chromium build outright ("Target crashed", measured
    2026-08-26 — it does so with no overlay attached at all, so it is the
    harness, not the feature). Clicking the rendered position is also the
    closer analogue of a finger on the iiyama.
    """
    pos = page.evaluate(
        "(id) => { const p = window.kgView.cy.getElementById(id).renderedPosition();"
        " return {x: p.x, y: p.y}; }",
        node_id,
    )
    page.mouse.click(pos["x"], pos["y"])
    page.wait_for_timeout(250)


def _tap_background(page):
    page.mouse.click(20, 20)
    page.wait_for_timeout(250)


def test_the_wall_shows_no_quote_until_someone_asks(wall):
    """Spec §10.2: quotes are deliberately absent from the default display."""
    assert wall.evaluate("window.kgQuotes.visible") is False
    assert wall.eval_on_selector("#quote-overlay", "el => el.hidden") is True


def test_tapping_a_portrait_reveals_that_persons_quote(wall):
    _tap(wall, "p1")
    assert wall.evaluate("window.kgQuotes.visible") is True
    assert wall.eval_on_selector("#quote-overlay .quote-text", "el => el.textContent") == (
        "Wir bauen viel zu viel neu."
    )


def test_each_portrait_shows_its_own_quote(wall):
    _tap(wall, "p2")
    assert wall.eval_on_selector("#quote-overlay .quote-text", "el => el.textContent") == (
        "Ein Haus muss nach Zuhause riechen."
    )


def test_tapping_the_same_face_again_does_not_change_the_quote(wall):
    """Exactly one quote per person now — repeated taps are a no-op, not a cycle.

    p1 still carries two quotes in the fixture on purpose: it doubles as the
    Altbestand case (a store from before the one-quote-per-person rule) and
    proves the frontend keeps only the first there too.
    """
    _tap(wall, "p1")
    _tap(wall, "p1")
    assert wall.eval_on_selector("#quote-overlay .quote-text", "el => el.textContent") == (
        "Wir bauen viel zu viel neu."
    )


def test_the_name_stands_above_the_quote_in_its_own_element(wall):
    """Der Name gehört nicht in den Zitattext.

    Die Anführungszeichen zeichnet `.quote-text` sich in CSS selbst
    (`::before`/`::after`, base.css) — ein hineinkonkatenierter Name stünde
    zwischen ihnen, als hätte die Person ihren eigenen Namen mitgesprochen.
    """
    _tap(wall, "p1")
    assert wall.eval_on_selector("#quote-overlay .quote-name", "el => el.textContent") == (
        "Frau Kirchner"
    )
    assert wall.eval_on_selector("#quote-overlay .quote-text", "el => el.textContent") == (
        "Wir bauen viel zu viel neu."
    )
    # Zuerst der Name, dann das Zitat — und beide sichtbar.
    #
    # 🔴 Geprueft wird die REIHENFOLGE, nicht mehr die Anzahl der Kinder
    # (2026-09-02). Seit dem Tipp auf einen Begriff haengt in derselben Karte
    # eine dritte Liste (`.quote-belege`), die bei einer PERSON verborgen
    # bleibt. Die Aussage dieses Tests war nie „genau zwei Elemente", sondern
    # „der Name steht ueber dem Zitat und nicht darin".
    kinder = wall.eval_on_selector(
        "#quote-overlay", "el => [...el.children].map(c => c.className)"
    )
    assert kinder[:2] == ["quote-name", "quote-text"]
    assert wall.eval_on_selector(
        "#quote-overlay .quote-belege", "el => el.hidden"
    ) is True, "die Begriffsliste darf bei einer Person nicht aufgehen"
    assert wall.eval_on_selector("#quote-overlay .quote-name", "el => el.hidden") is False


def test_a_person_without_a_name_leaves_no_gap_above_the_quote(wall):
    """Leer allein reicht nicht: Ein leeres Element belegt weiter eine Zeile.

    Die meisten Personen haben keinen Namen, also wäre die Lücke der
    Normalfall — und das Zitat säße auf jeder zweiten Karte anders.
    """
    _tap(wall, "p2")
    assert wall.evaluate("window.kgQuotes.visible") is True
    assert wall.eval_on_selector("#quote-overlay .quote-name", "el => el.textContent") == ""
    assert wall.eval_on_selector("#quote-overlay .quote-name", "el => el.hidden") is True
    assert wall.eval_on_selector("#quote-overlay .quote-name", "el => el.offsetHeight") == 0


def test_the_name_follows_the_person_the_panel_is_showing(wall):
    """Zwei Porträts nacheinander dürfen nicht denselben Namen tragen."""
    _tap(wall, "p1")
    assert wall.eval_on_selector("#quote-overlay .quote-name", "el => el.textContent") == (
        "Frau Kirchner"
    )
    _tap(wall, "p2")
    assert wall.eval_on_selector("#quote-overlay .quote-name", "el => el.hidden") is True


def test_a_name_corrected_by_the_operator_reaches_the_open_panel(wall):
    """Korrigiert wird gerade WEIL der falsche Name auf der Wand steht.

    Der Namensspeicher wird — wie `byPerson` — bei jedem Graph-Push neu aus den
    Personenknoten gebaut; das offene Overlay muss dabei mitgehen.
    """
    _tap(wall, "p1")
    korrigiert = {
        **GRAPH,
        "nodes": [
            {**n, "name": "Frau Kirchnauer"} if n["id"] == "p1" else n for n in GRAPH["nodes"]
        ],
    }
    wall.evaluate("(g) => window.kgQuotes.setGraph(g)", korrigiert)
    assert wall.eval_on_selector("#quote-overlay .quote-name", "el => el.textContent") == (
        "Frau Kirchnauer"
    )

    geleert = {
        **GRAPH,
        "nodes": [{**n, "name": None} if n["id"] == "p1" else n for n in GRAPH["nodes"]],
    }
    wall.evaluate("(g) => window.kgQuotes.setGraph(g)", geleert)
    assert wall.eval_on_selector("#quote-overlay .quote-name", "el => el.hidden") is True


def test_a_person_without_a_quote_opens_nothing(wall):
    """Better silence than an empty panel that reads as broken."""
    _tap(wall, "p3")
    assert wall.evaluate("window.kgQuotes.visible") is False


def test_tapping_a_term_does_not_open_a_quote(wall):
    """Terms carry text already; only faces hide something."""
    _tap(wall, "t1")
    assert wall.evaluate("window.kgQuotes.visible") is False


def test_tapping_the_background_dismisses_it(wall):
    """The natural "done reading" gesture — must work without a button."""
    _tap(wall, "p1")
    assert wall.evaluate("window.kgQuotes.visible") is True
    _tap_background(wall)
    assert wall.evaluate("window.kgQuotes.visible") is False


def test_a_quote_hides_itself_so_it_cannot_burn_in(wall):
    """A visitor who taps and walks away must not leave a quote up all day."""
    wall.evaluate(
        """async (graph) => {
             const { attachQuoteOverlay } = await import('./quote-overlay.js');
             document.getElementById('quote-overlay').remove();
             window.fired = null;
             window.kgQuotes = attachQuoteOverlay(window.kgView, {
               setTimer: (fn, ms) => { window.fired = { fn, ms }; return 1; },
               clearTimer: () => { window.fired = null; },
             });
             window.kgQuotes.setGraph(graph);
           }""",
        GRAPH,
    )
    _tap(wall, "p1")
    assert wall.evaluate("window.fired.ms") == 12000
    wall.evaluate("window.fired.fn()")
    assert wall.evaluate("window.kgQuotes.visible") is False


def test_a_quote_whose_person_left_the_graph_disappears(wall):
    """Operator hid the person, or the density filter dropped them."""
    _tap(wall, "p1")
    assert wall.evaluate("window.kgQuotes.visible") is True
    without_p1 = {**GRAPH, "quotes": [q for q in GRAPH["quotes"] if q["person_id"] != "p1"]}
    wall.evaluate("(g) => window.kgQuotes.setGraph(g)", without_p1)
    assert wall.evaluate("window.kgQuotes.visible") is False


# --- Die Karte darf nicht unter der Bedienleiste liegen (Birk, 2026-09-02) ---
#
# „Beim Touchscreen erscheinen die Zitate, wenn man sie anklickt, unter dem
# Zoomregler." Die Karte stand auf `bottom: calc(104px * var(--quote-scale))`.
# Bei einem Massstab von 0,4 sind das 41,6 px — die Leiste ist 88 px hoch.
# Der Fehler war nicht die Zahl, sondern dass der Abstand, der die Leiste
# freihalten soll, MIT DER KARTE MITSCHRUMPFT.
#
# Gemessen wird an der ECHTEN Seite (`projection.html?touch=1`), nicht an der
# Harness: die Leiste entsteht nur dort, und genau ihre gemessene Hoehe ist
# der Wert, um den es geht.


def test_die_zitatkarte_liegt_ueber_der_bedienleiste(page, static_server):
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(f"{static_server}/frontend/projection.html?touch=1")
    page.wait_for_selector("#touch-controls")

    masse = page.evaluate(
        """() => {
             const karte = document.querySelector('.quote-overlay');
             const leiste = document.getElementById('touch-controls');
             if (!karte || !leiste) return null;
             // Die Karte ist unsichtbar, bis jemand tippt — sie steht aber
             // schon im Layout, und genau ihre Lage wird hier geprueft.
             karte.classList.add('visible');
             const k = karte.getBoundingClientRect();
             const l = leiste.getBoundingClientRect();
             return { karteUnten: k.bottom, leisteOben: l.top,
                      leisteHoehe: l.height,
                      variable: getComputedStyle(document.documentElement)
                                  .getPropertyValue('--touch-leiste-hoehe').trim() };
           }"""
    )
    assert masse is not None, "Karte oder Bedienleiste fehlen auf der Touchflaeche"

    # 1. Die Leiste meldet ihre Hoehe, sonst kann das CSS nichts damit tun.
    assert masse["variable"], "--touch-leiste-hoehe ist nicht gesetzt"
    assert masse["variable"] != "0px"

    # 2. Und die Karte endet ueber der Leiste, nicht darin.
    assert masse["karteUnten"] <= masse["leisteOben"], (
        f"Die Zitatkarte endet bei {masse['karteUnten']:.0f} px, die Leiste "
        f"beginnt schon bei {masse['leisteOben']:.0f} px — sie liegt darunter."
    )


def test_ohne_bedienleiste_sitzt_die_karte_wie_zuvor(page, static_server):
    """Die Gegenrichtung: Wand und Saal haben keine Leiste, dort darf sich
    nichts verschoben haben — sonst waere der Fix eine Aenderung am Foyer."""
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(f"{static_server}/frontend/projection.html?plenum=1")
    page.wait_for_function("window.kgView !== undefined")

    masse = page.evaluate(
        """() => {
             const karte = document.querySelector('.quote-overlay');
             const stil = getComputedStyle(karte);
             return { bottom: stil.bottom,
                      leiste: !!document.getElementById('touch-controls'),
                      variable: getComputedStyle(document.documentElement)
                                  .getPropertyValue('--touch-leiste-hoehe').trim() };
           }"""
    )
    assert masse["leiste"] is False, "ohne ?touch=1 darf es keine Bedienleiste geben"
    assert masse["variable"] == "", "ohne Leiste darf die Variable nicht gesetzt sein"
    # 104 * 0.4 = 41.6 — exakt der Wert von vor der Aenderung.
    assert masse["bottom"].startswith("41."), masse["bottom"]


def test_die_zitatschrift_haengt_nicht_an_der_kartengroesse(page, static_server):
    """Birk, 2026-09-02: „viel zu klein, die Schrift wesentlich groesser."

    `--quote-scale` kam auf 0,4, weil die KARTE zu gross war — und nahm die
    Schrift mit auf 13,6 px. Zwei Regler, weil es zwei Fragen sind: wieviel
    Flaeche die Karte nimmt, und ob man den Text von dort liest, wo man steht.

    Geprueft wird die ENTKOPPLUNG, nicht der Zahlenwert: Wer `--quote-scale`
    weiter verkleinert, darf die Schrift nicht mitreissen. Sonst waere derselbe
    Fehler beim naechsten Verkleinern wieder da.
    """
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(f"{static_server}/frontend/projection.html?touch=1")
    # `state="attached"`: die Karte steht von Anfang an im DOM, ist aber
    # `hidden`, bis jemand eine Person antippt. Gemessen wird ihre BERECHNETE
    # Schriftgroesse, und die gilt auch im verborgenen Zustand.
    page.wait_for_selector(".quote-overlay", state="attached")
    page.wait_for_selector(".quote-text", state="attached")

    def schriftgroesse():
        return page.evaluate(
            """() => {
                 const t = document.querySelector('.quote-text');
                 const n = document.querySelector('.quote-name');
                 return { zitat: parseFloat(getComputedStyle(t).fontSize),
                          name: parseFloat(getComputedStyle(n).fontSize) };
               }"""
        )

    vorher = schriftgroesse()
    # Gross genug, um aus mehreren Metern gelesen zu werden — 13,6 px war es
    # nicht. Untergrenze, kein Sollwert: Birk stellt den Rest vor Ort ein.
    assert vorher["zitat"] >= 24, f"Zitat rendert mit {vorher['zitat']} px"
    assert vorher["name"] >= 15, f"Name rendert mit {vorher['name']} px"

    # Und jetzt die Karte kleiner stellen — die Schrift darf NICHT mitgehen.
    page.evaluate(
        "() => document.documentElement.style.setProperty('--quote-scale', '0.2')"
    )
    nachher = schriftgroesse()
    assert nachher == vorher, (
        "die Schrift ist mit der Kartengroesse geschrumpft — genau die "
        f"Kopplung, die weg sollte ({vorher} -> {nachher})"
    )


# --- Ein Tipp auf einen BEGRIFF (Birk, 2026-09-02) --------------------------
#
# „Das könnte beim Anklicken auf diesen Begriff angezeigt werden, ähnlich wie
# die Zitate, die bei Personen angezeigt werden. Bei Begriffen, die von
# mehreren Menschen genannt wurden, könnte der jeweilige Kontext, in dem der
# Begriff genannt wurde, pro Person mit dem Namen der Person dargestellt
# werden."
#
# Die Stellen liegen seit dem 2026-09-02 an den KANTEN (`evidence` in
# graph.json), je Person eine eigene.

BEGRIFFS_GRAPH = {
    "version": 1,
    "max_terms": 99,
    "nodes": [
        {"id": "p1", "type": "person", "portrait": "", "hidden": False, "created_at": 1,
         "x": 100, "y": 100, "name": "Frau Kirchner"},
        {"id": "p2", "type": "person", "portrait": "", "hidden": False, "created_at": 2,
         "x": 400, "y": 100, "name": None},
        {"id": "t1", "type": "term", "label": "Genossenschaftliches Wohnen", "mentions": 2,
         "hidden": False, "created_at": 4, "x": 250, "y": 300},
        {"id": "t2", "type": "term", "label": "Holzbau", "mentions": 1,
         "hidden": False, "created_at": 5, "x": 600, "y": 300},
    ],
    "edges": [
        {"id": "e1", "source": "p1", "target": "t1",
         "evidence": "Das Haus gehört allen zusammen"},
        {"id": "e2", "source": "p2", "target": "t1",
         "evidence": "Wir haben eine Genossenschaft gegründet"},
        {"id": "e3", "source": "p1", "target": "t2"},
    ],
    "quotes": [{"id": "q1", "person_id": "p1", "text": "Wir bauen zu viel Neues."}],
}


@pytest.fixture()
def wand_mit_begriffen(page, static_server):
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(f"{static_server}/frontend/static/render-harness.html")
    page.wait_for_function("window.kgView !== undefined")
    page.evaluate(
        """async (graph) => {
             const { attachQuoteOverlay } = await import('./quote-overlay.js');
             window.kgQuotes = attachQuoteOverlay(window.kgView);
             window.kgView.update(graph);
             window.kgQuotes.setGraph(graph);
           }""",
        BEGRIFFS_GRAPH,
    )
    page.wait_for_function("window.kgView.layoutPending === false")
    return page


def test_ein_tipp_auf_einen_begriff_zeigt_die_belegstellen(wand_mit_begriffen):
    _tap(wand_mit_begriffen, "t1")

    karte = wand_mit_begriffen.locator(".quote-overlay")
    assert karte.is_visible()
    text = karte.inner_text()
    assert "Das Haus gehört allen zusammen" in text
    assert "Wir haben eine Genossenschaft gegründet" in text


def test_bei_mehreren_menschen_steht_der_name_an_seiner_stelle(wand_mit_begriffen):
    _tap(wand_mit_begriffen, "t1")

    text = wand_mit_begriffen.locator(".quote-overlay").inner_text()
    # Frau Kirchner hat sich vorgestellt, die zweite Person nicht — dort darf
    # kein leerer Name und kein Platzhalter stehen.
    assert "Frau Kirchner" in text
    assert "null" not in text.lower()


def test_ein_begriff_ohne_belegstelle_oeffnet_keine_leere_karte(wand_mit_begriffen):
    """Wie bei einer Person ohne Zitat: lieber nichts als eine Karte, die
    kaputt aussieht."""
    _tap(wand_mit_begriffen, "t2")

    assert not wand_mit_begriffen.locator(".quote-overlay").is_visible()


def test_ein_tipp_auf_eine_person_zeigt_weiter_ihr_zitat(wand_mit_begriffen):
    """Die Gegenrichtung — der bestehende Weg darf nicht kaputtgehen."""
    _tap(wand_mit_begriffen, "p1")

    text = wand_mit_begriffen.locator(".quote-overlay").inner_text()
    assert "Wir bauen zu viel Neues." in text
