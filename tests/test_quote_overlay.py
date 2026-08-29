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
         "x": 100, "y": 100},
        {"id": "p2", "type": "person", "portrait": "", "hidden": False, "created_at": 2,
         "x": 400, "y": 100},
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
