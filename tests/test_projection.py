import pytest

GRAPH_1 = {
    "version": 1,
    "min_mentions": 1,
    "nodes": [
        {"id": "p1", "type": "person", "portrait": "", "hidden": False, "x": 100, "y": 100},
        {"id": "t1", "type": "term", "label": "Holzbau", "mentions": 1, "hidden": False, "x": None, "y": None},
    ],
    "edges": [{"id": "e1", "source": "p1", "target": "t1"}],
    "quotes": [],
}

GRAPH_2 = {
    "version": 1,
    "min_mentions": 1,
    "nodes": GRAPH_1["nodes"]
    + [
        {"id": "p2", "type": "person", "portrait": "", "hidden": False, "x": None, "y": None},
        {"id": "t2", "type": "term", "label": "Bodenpreise", "mentions": 1, "hidden": False, "x": None, "y": None},
    ],
    "edges": GRAPH_1["edges"] + [{"id": "e2", "source": "p2", "target": "t2"}],
    "quotes": [],
}


@pytest.fixture()
def view(page, static_server):
    page.goto(f"{static_server}/frontend/static/render-harness.html")
    page.wait_for_function("window.kgView !== undefined")
    return page


def wait_for_layout(page):
    """The cose layout is animated (LAYOUT.animationDuration) and positions are
    only reported at `layoutstop`. Wait for the real signal — a fixed timeout
    shorter than the animation would make these tests flaky."""
    page.wait_for_function("() => window.kgView.layoutPending === false")


def update(page, graph, min_mentions=1):
    page.evaluate("(args) => window.kgView.update(args[0], args[1])", [graph, min_mentions])
    wait_for_layout(page)


def test_nodes_and_edges_are_rendered(view):
    update(view, GRAPH_1)
    assert view.evaluate("window.kgView.cy.nodes().length") == 2
    assert view.evaluate("window.kgView.cy.edges().length") == 1
    assert view.evaluate("window.kgView.cy.$('#p1').hasClass('person')") is True


def test_a_persisted_position_is_honoured_exactly(view):
    update(view, GRAPH_1)
    assert view.evaluate("window.kgView.cy.$('#p1').position()") == {"x": 100, "y": 100}


def test_existing_nodes_never_move_when_new_nodes_arrive(view):
    update(view, GRAPH_1)
    before = view.evaluate("window.kgView.cy.$('#t1').position()")

    update(view, GRAPH_2)

    after = view.evaluate("window.kgView.cy.$('#t1').position()")
    assert after == before
    assert view.evaluate("window.kgView.cy.nodes().length") == 4


def test_new_node_positions_are_reported_for_persistence(view):
    update(view, GRAPH_1)
    view.evaluate("window.kgPositions.length = 0")

    update(view, GRAPH_2)

    reported = view.evaluate("Object.keys(Object.assign({}, ...window.kgPositions))")
    assert "p2" in reported and "t2" in reported


def _unplaced_net(persons=8, terms_per_person=4, term_pool=12):
    """A graph with no persisted positions: the layout places all of it."""
    nodes = [
        {"id": f"p{i}", "type": "person", "portrait": "", "hidden": False, "x": None, "y": None}
        for i in range(persons)
    ] + [
        {
            "id": f"t{i}",
            "type": "term",
            "label": f"Kreislaufgerechte Bauteilkataloge {i}",
            "mentions": 2,
            "hidden": False,
            "x": None,
            "y": None,
        }
        for i in range(term_pool)
    ]
    edges = [
        {"id": f"e{i}-{j}", "source": f"p{i}", "target": f"t{(i * 3 + j) % term_pool}"}
        for i in range(persons)
        for j in range(terms_per_person)
    ]
    return {"version": 1, "min_mentions": 1, "nodes": nodes, "edges": edges, "quotes": []}


CANVAS_ASPECT = 1920 / 1080


def test_a_from_scratch_layout_is_shaped_like_the_16_9_canvas(view):
    # A force layout is isotropic, so its settled cloud is round and leaves
    # the sides of a 16:9 wall empty (measured 2026-08-14: the node cloud
    # covered 30% of the canvas width). The placement is framed to the
    # canvas instead of the camera over-zooming, which would clip top and
    # bottom.
    update(view, _unplaced_net())

    box = view.evaluate(
        "() => window.kgView.cy.nodes().boundingBox({ includeLabels: true })"
    )
    assert box["w"] / box["h"] == pytest.approx(CANVAS_ASPECT, rel=0.1)


def test_the_framed_net_covers_the_canvas_width_after_a_fit(view):
    # The number that matters is what reaches the wall, so measure the
    # rendered box under the camera's own fit, not just the model box.
    update(view, _unplaced_net())

    covered = view.evaluate(
        """() => {
             const cy = window.kgView.cy;
             const box = cy.nodes().renderedBoundingBox({ includeLabels: true });
             return box.w / cy.width();
           }"""
    )
    assert covered > 0.8


def test_framing_never_reshuffles_an_already_placed_net(view):
    # Framing is part of placing a net from scratch. Once nodes carry
    # positions, spec 11 rules: nothing already on the wall may move.
    update(view, _unplaced_net())
    before = view.evaluate("window.kgView.cy.$('#p0').position()")

    grown = _unplaced_net()
    for node in grown["nodes"]:
        position = view.evaluate("(id) => window.kgView.cy.$id(id).position()", node["id"])
        node["x"], node["y"] = position["x"], position["y"]
    grown["nodes"].append(
        {"id": "pX", "type": "person", "portrait": "", "hidden": False, "x": None, "y": None}
    )
    grown["edges"].append({"id": "eX", "source": "pX", "target": "t0"})
    update(view, grown)

    assert view.evaluate("window.kgView.cy.$('#p0').position()") == before


THEME_LABEL_SIZE = {
    # Declared --label-size tokens from the theme files. Since 2026-08-14 the
    # series is three dark variants that differ in type size and stroke
    # weight only (the inverted variant is gone), so this is the token that
    # separates them — and the one the whole series exists to decide.
    "a": "22px",
    "b": "32px",
    "c": "44px",
}

THEME_RING_WIDTH = {"a": "5px", "b": "7px", "c": "10px"}

ONE_PERSON = {
    "version": 1,
    "min_mentions": 1,
    "nodes": [
        {"id": "p1", "type": "person", "portrait": "", "hidden": False, "x": 0, "y": 0},
        {
            "id": "t1",
            "type": "term",
            "label": "Holzbau",
            "mentions": 1,
            "hidden": False,
            "x": 200,
            "y": 0,
        },
    ],
    "edges": [{"id": "e1", "source": "p1", "target": "t1"}],
    "quotes": [],
}


def test_theme_query_param_reaches_the_baked_cytoscape_style(page, static_server):
    # Regression test for a bug where createGraphView() ran before the
    # `?theme=` stylesheet swap had actually loaded: cssVar() reads through
    # getComputedStyle synchronously, so it silently baked in the PREVIOUS
    # (default theme-a) stylesheet's values regardless of `?theme=`. Only the
    # live CSS background (base.css `background: var(--bg)`) ever switched.
    # A test that only checks the background would not catch this — it must
    # read a value Cytoscape itself baked into style, through Cytoscape's own
    # API, on a real Chromium page loading the actual `projection.html`.
    sizes = {}
    rings = {}
    for theme in ("a", "b", "c"):
        page.goto(f"{static_server}/frontend/projection.html?theme={theme}")
        page.wait_for_function("window.kgView !== undefined")
        page.evaluate("(g) => window.kgView.update(g, 1)", ONE_PERSON)
        wait_for_layout(page)
        sizes[theme] = page.evaluate("window.kgView.cy.$('#t1').style('font-size')")
        rings[theme] = page.evaluate("window.kgView.cy.$('#p1').style('border-width')")

    assert sizes == THEME_LABEL_SIZE
    assert rings == THEME_RING_WIDTH


def test_unknown_theme_falls_back_and_still_renders(page, static_server):
    # Regression test: a `?theme=` value that does not resolve to an existing
    # stylesheet must never leave the theme-load promise unresolved forever.
    # That is the worst failure mode for an unattended wall — window.kgView
    # never gets set, /events never connects, and the projection shows
    # nothing indefinitely with no operator recourse. A bad theme must
    # degrade to the default theme and still render, not hang. The wait is
    # bounded so a regression fails the suite instead of hanging it.
    page.goto(f"{static_server}/frontend/projection.html?theme=nonexistent")
    page.wait_for_function("window.kgView !== undefined", timeout=5000)
    page.evaluate("(g) => window.kgView.update(g, 1)", ONE_PERSON)
    page.wait_for_function("() => window.kgView.layoutPending === false", timeout=5000)
    assert page.evaluate("window.kgView.cy.nodes().length") == len(ONE_PERSON["nodes"])


def test_raising_the_dial_removes_terms_without_touching_the_rest(view):
    update(view, GRAPH_2)
    person_position = view.evaluate("window.kgView.cy.$('#p1').position()")

    view.evaluate("window.kgView.setMinMentions(2)")
    wait_for_layout(view)

    assert view.evaluate("window.kgView.cy.$('#t1').length") == 0
    assert view.evaluate("window.kgView.cy.$('#p1').length") == 1
    view.evaluate("window.kgView.setMinMentions(1)")
    wait_for_layout(view)
    assert view.evaluate("window.kgView.cy.$('#t1').length") == 1
    assert view.evaluate("window.kgView.cy.$('#p1').position()") == person_position


# --- Label declutter (Birk's third pre-render review, 2026-08-14) ---------
#
# series-b-dark-larger-label32.png (50 persons, 75 terms) showed labels
# piled on top of each other and on top of person discs. Three fixes:
#   a) the from-scratch placement must know a term node is its dot PLUS its
#      label box, not just the dot (cose's own nodeDimensionsIncludeLabels
#      is not enough on its own — measured below);
#   b) a post-layout pass nudges label OFFSETS (never positions) apart;
#   c) that pass treats person discs as fixed obstacles labels may not sit on.

# The real labels the pre-render shoots, not a short cycled sample of them.
# An earlier version of this module cycled 18 strings across 75 term nodes,
# which made the harness net measurably easier than the wall's own graph: the
# whole pipeline came out at 0 overlaps here while the seeded 50-person graph
# came out at 44 (2026-08-14). Distinct labels of very mixed length are the
# thing that makes this hard, so the fixture uses the same source the seeded
# graph does.
from sim.seed_graph import TERM_LABELS


def _dense_net(persons=50, terms=75, edges_per_person=5):
    """The density and label mix that first showed the label collisions this
    module exists to fix (Birk's 3rd pre-render review: 50 persons, 75
    distinct long German term labels, ~250 edges, on a 1920x1080 wall).
    Mentions cycle 1-2-3 so raising min_mentions removes some terms, not all
    of them, which is what the redeclutter-on-filter-change test needs."""
    nodes = [
        {"id": f"p{i}", "type": "person", "portrait": "", "hidden": False, "x": None, "y": None}
        for i in range(persons)
    ] + [
        {
            "id": f"t{i}",
            "type": "term",
            "label": TERM_LABELS[i % len(TERM_LABELS)],
            "mentions": (i % 3) + 1,
            "hidden": False,
            "x": None,
            "y": None,
        }
        for i in range(terms)
    ]
    edges = [
        {"id": f"e{i}-{j}", "source": f"p{i}", "target": f"t{(i * 7 + j * 3) % terms}"}
        for i in range(persons)
        for j in range(edges_per_person)
    ]
    return {"version": 1, "min_mentions": 1, "nodes": nodes, "edges": edges, "quotes": []}


def test_count_label_overlaps_detects_overlapping_labels_and_person_collisions(page, static_server):
    # A narrow, hand-placed unit test of the geometry itself, independent of
    # layout: two identical labels 5px apart must overlap (1 pair), a third
    # label placed exactly on a person disc must count against that person,
    # and a label far from everything must not pollute either count.
    page.goto(f"{static_server}/frontend/static/render-harness.html")
    page.wait_for_function("window.kgView !== undefined")
    result = page.evaluate(
        """async () => {
             const { countLabelOverlaps } = await import('/frontend/static/projection.js');
             const cy = window.kgView.cy;
             cy.add([
               { data: { id: 'pa', type: 'person' }, classes: 'person', position: { x: 0, y: 0 } },
               { data: { id: 'ta', type: 'term', label: 'Alpha Beta Gamma' }, classes: 'term', position: { x: 500, y: 500 } },
               { data: { id: 'tb', type: 'term', label: 'Alpha Beta Gamma' }, classes: 'term', position: { x: 505, y: 500 } },
               { data: { id: 'tc', type: 'term', label: 'Far Away Label' }, classes: 'term', position: { x: 0, y: 0 } },
             ]);
             return countLabelOverlaps(cy);
           }"""
    )
    assert result["labelPairs"] == 1
    assert result["labelsOnPersons"] == 1


def test_reset_label_offsets_returns_to_the_theme_default(view):
    update(view, GRAPH_1)
    result = view.evaluate(
        """async () => {
             const { resetLabelOffsets } = await import('/frontend/static/projection.js');
             const cy = window.kgView.cy;
             const node = cy.$('#t1');
             node.style({ 'text-margin-x': 40, 'text-margin-y': 90 });
             resetLabelOffsets(cy);
             return { x: node.numericStyle('text-margin-x'), y: node.numericStyle('text-margin-y') };
           }"""
    )
    # render-harness.html is pinned to theme-a: --label-margin-y: 6.
    assert result == {"x": 0, "y": 6}


def test_declutter_never_moves_a_node_position(view):
    # Position persistence (spec 11) is untouchable: decluttering is only
    # ever allowed to change where a LABEL sits relative to its own dot.
    update(view, _dense_net())
    before = view.evaluate(
        "() => Object.fromEntries(window.kgView.cy.nodes().map(n => [n.id(), n.position()]))"
    )

    view.evaluate("() => window.kgView.declutterLabels()")

    after = view.evaluate(
        "() => Object.fromEntries(window.kgView.cy.nodes().map(n => [n.id(), n.position()]))"
    )
    assert after == before


def test_declutter_clears_every_label_on_person_overlap(view):
    # Hard rule (c): text on a portrait disc is worse than text on text,
    # because the disc becomes a real photo later.
    update(view, _dense_net())
    overlaps = view.evaluate("() => window.kgView.labelOverlaps()")
    assert overlaps["labelsOnPersons"] == 0


def test_label_overlap_stats_record_before_and_after_declutter(view):
    update(view, _dense_net())
    stats = view.evaluate("() => window.kgView.labelOverlapStats")
    assert set(stats.keys()) == {"before", "after"}
    assert stats["after"]["labelPairs"] <= stats["before"]["labelPairs"]
    assert stats["after"]["labelsOnPersons"] <= stats["before"]["labelsOnPersons"]


def test_declutter_and_placement_are_deterministic(page, static_server):
    # Same seed, same picture: two independent from-scratch runs over the
    # identical graph must settle on identical node positions AND identical
    # label offsets, or the pre-render series (A-D at the same seed) would
    # stop being a fair comparison.
    graph = _dense_net()

    def run_once():
        page.goto(f"{static_server}/frontend/static/render-harness.html")
        page.wait_for_function("window.kgView !== undefined")
        update(page, graph)
        return page.evaluate(
            """() => {
                 const cy = window.kgView.cy;
                 const positions = {};
                 const offsets = {};
                 cy.nodes().forEach((n) => {
                   positions[n.id()] = n.position();
                   offsets[n.id()] = {
                     x: n.numericStyle('text-margin-x'),
                     y: n.numericStyle('text-margin-y'),
                   };
                 });
                 return { positions, offsets };
               }"""
        )

    first = run_once()
    second = run_once()
    assert first == second


def test_declutter_never_reshuffles_an_already_placed_dense_net(view):
    # Mirrors test_framing_never_reshuffles_an_already_placed_net at the
    # density where declutter actually does work: growing an already-placed
    # net must not move any existing node, even though every render re-runs
    # the full declutter pass over the whole graph (including those nodes).
    update(view, _dense_net())
    before = view.evaluate("window.kgView.cy.$('#p0').position()")

    grown = _dense_net()
    for node in grown["nodes"]:
        position = view.evaluate("(id) => window.kgView.cy.$id(id).position()", node["id"])
        node["x"], node["y"] = position["x"], position["y"]
    grown["nodes"].append(
        {"id": "pX", "type": "person", "portrait": "", "hidden": False, "x": None, "y": None}
    )
    grown["edges"].append({"id": "eX", "source": "pX", "target": "t0"})
    update(view, grown)

    assert view.evaluate("window.kgView.cy.$('#p0').position()") == before


def test_the_net_is_turned_to_landscape_before_it_is_separated(view):
    # The bug this pins down (found in the 3rd pre-render run, 2026-08-14):
    # frameToAspect may turn the whole net a quarter turn, and a rotation
    # moves the dots while every label stays horizontal. Separating first and
    # rotating after therefore throws the result away — measured on the
    # seeded graph, separation took 43 overlapping pairs down to 20 and the
    # rotation put it straight back to 48. So by the time the net is settled,
    # it must be BOTH landscape and clear; landscape alone or clear alone
    # would have passed while the picture on the wall was still a pile.
    update(view, _dense_net())

    box = view.evaluate(
        "() => window.kgView.cy.nodes().boundingBox({ includeLabels: true })"
    )
    assert box["w"] > box["h"]
    assert view.evaluate("() => window.kgView.labelOverlaps()") == {
        "labelPairs": 0,
        "labelsOnPersons": 0,
    }


def test_declutter_never_hands_back_a_worse_net_than_it_was_given(view):
    # Relaxation is not monotone: pushing a label clear of a person disc at
    # full strength drops it onto two others, and on the seeded graph a run
    # measured 44 overlapping pairs in and 49 out (2026-08-14). Whatever it
    # does in between, the pass must keep the best state it saw — and its own
    # untouched input is one of the candidates, so it can never regress.
    update(view, _dense_net())
    # Start from a deliberately bad state: every label shoved the same way,
    # so the pass has real work to do and a real chance to overshoot.
    # The braces matter: cy's forEach returns the collection, and serialising
    # that back to the driver crashes the page (same trap as PORTRAITS_LOADED
    # in sim/prerender.py). Return nothing.
    view.evaluate(
        "() => { window.kgView.cy.nodes('.term').forEach(n => n.style({'text-margin-x': 120})); }"
    )
    before = view.evaluate("() => window.kgView.labelOverlaps()")

    view.evaluate("() => window.kgView.declutterLabels()")

    after = view.evaluate("() => window.kgView.labelOverlaps()")
    assert after["labelPairs"] <= before["labelPairs"]
    assert after["labelsOnPersons"] <= before["labelsOnPersons"]


def test_lowering_the_dial_puts_the_returning_terms_back_where_they_were(view):
    # Raising min_mentions REMOVES term nodes from cy, so lowering it again
    # re-adds them. In a session whose positions the server has not yet
    # persisted back into the graph data, those nodes carry x/y null and would
    # read as brand new — which would re-run a layout and reshuffle half the
    # net under the visitor's eyes (spec 11). Found in the 3rd pre-render run:
    # the min_mentions 3 -> 1 shot came back 117% of the canvas height while
    # the identical picture on the way up had been 82%.
    update(view, _dense_net())
    before = view.evaluate(
        "() => Object.fromEntries(window.kgView.cy.nodes().map(n => [n.id(), n.position()]))"
    )

    view.evaluate("() => window.kgView.setMinMentions(3)")
    wait_for_layout(view)
    view.evaluate("() => window.kgView.setMinMentions(1)")
    wait_for_layout(view)

    after = view.evaluate(
        "() => Object.fromEntries(window.kgView.cy.nodes().map(n => [n.id(), n.position()]))"
    )
    assert after == before


def test_raising_min_mentions_redeclutters_and_lowers_overlap_count(view):
    # Removing labels only ever helps decluttering (fewer boxes to collide),
    # and render() must take that free win on every filter change, not just
    # on a from-scratch placement — a min_mentions change adds no new nodes
    # and so runs no layout at all.
    update(view, _dense_net())
    before = view.evaluate("() => window.kgView.labelOverlapStats.after")
    before_term_count = view.evaluate("() => window.kgView.cy.nodes('.term').length")

    view.evaluate("window.kgView.setMinMentions(2)")
    wait_for_layout(view)

    after = view.evaluate("() => window.kgView.labelOverlapStats.after")
    after_term_count = view.evaluate("() => window.kgView.cy.nodes('.term').length")

    assert after_term_count < before_term_count
    assert after["labelPairs"] <= before["labelPairs"]


def test_layout_separation_beats_coses_own_label_handling_alone(page, static_server):
    # cose's nodeDimensionsIncludeLabels only sizes a node's OWN repulsion
    # off its measured extent; it never learns that its neighbours are wide
    # too. Measured 2026-08-14 on theme-b (32px labels) at 50 persons / 75
    # terms, same deterministic golden-angle seeding both sides so this
    # isolates the fix rather than comparing against a differently-seeded
    # run: cose alone (nodeDimensionsIncludeLabels on, no post-layout
    # separation, no declutter) reproducibly settles at 9 overlapping
    # label-box pairs and 3 labels sitting on person discs. The full
    # from-scratch pipeline (separation pass + declutter) reproducibly
    # clears both to zero on this net — not just "fewer", gone.
    page.goto(f"{static_server}/frontend/projection.html?theme=b")
    page.wait_for_function("window.kgView !== undefined")
    graph = _dense_net()
    update(page, graph)

    after = page.evaluate("() => window.kgView.labelOverlaps()")

    raw = page.evaluate(
        """async (graph) => {
             const { toCytoscape } = await import('/frontend/static/graph-model.js');
             const { countLabelOverlaps, LAYOUT } = await import('/frontend/static/projection.js');
             const el = document.createElement('div');
             el.style.width = '1920px';
             el.style.height = '1080px';
             document.body.appendChild(el);
             const cy = cytoscape({
               container: el,
               style: window.kgView.cy.style().json(),
               elements: toCytoscape({ nodes: graph.nodes, edges: graph.edges }),
             });
             // Mirror projection.js's own from-scratch seeding exactly (golden
             // angle, radius 140, around the origin), so the only difference
             // from window.kgView's own run is the separation pass and the
             // declutter pass that follow layoutstop in production.
             graph.nodes.forEach((n, index) => {
               const angle = index * 2.39996;
               cy.$id(n.id).position({ x: Math.cos(angle) * 140, y: Math.sin(angle) * 140 });
             });
             await new Promise((resolve) => {
               const layout = cy.layout({ ...LAYOUT, animate: false });
               layout.one('layoutstop', resolve);
               layout.run();
             });
             const overlaps = countLabelOverlaps(cy);
             cy.destroy();
             el.remove();
             return overlaps;
           }""",
        graph,
    )

    assert raw["labelPairs"] >= 5
    assert raw["labelsOnPersons"] >= 1
    assert after == {"labelPairs": 0, "labelsOnPersons": 0}
