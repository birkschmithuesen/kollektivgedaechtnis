import math

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

# Every node placed — what the server hands back after a restart (spec 10.5).
GRAPH_1_PLACED = {
    "version": 1,
    "min_mentions": 1,
    "nodes": [
        {"id": "p1", "type": "person", "portrait": "", "hidden": False, "x": 100, "y": 100},
        {"id": "t1", "type": "term", "label": "Holzbau", "mentions": 1, "hidden": False, "x": 400, "y": 250},
    ],
    "edges": [{"id": "e1", "source": "p1", "target": "t1"}],
    "quotes": [],
}


@pytest.fixture()
def view(page, static_server):
    page.goto(f"{static_server}/frontend/static/render-harness.html")
    page.wait_for_function("window.kgView !== undefined")
    return page


def wait_for_layout(page):
    """A migration is a computation (fcose + settlePlacement) followed by a
    2.5s animated glide, and positions are final only when both are done. Wait
    for the real signal — any fixed timeout would make these tests flaky."""
    page.wait_for_function("() => window.kgView.layoutPending === false", timeout=60000)


def update(page, graph, min_mentions=1):
    page.evaluate("(args) => window.kgView.update(args[0], args[1])", [graph, min_mentions])
    wait_for_layout(page)


def test_nodes_and_edges_are_rendered(view):
    update(view, GRAPH_1)
    assert view.evaluate("window.kgView.cy.nodes().length") == 2
    assert view.evaluate("window.kgView.cy.edges().length") == 1
    assert view.evaluate("window.kgView.cy.$('#p1').hasClass('person')") is True


def test_a_restored_graph_comes_back_exactly_where_it_was(view):
    # Crash recovery (spec 10.5 / 11): the first paint of a session whose every
    # node already carries a persisted position must reproduce the wall as it
    # stood. This is the ONE case that does not migrate — a restart must not
    # re-arrange the net while nobody is looking.
    update(view, GRAPH_1_PLACED)

    assert view.evaluate("window.kgView.cy.$('#p1').position()") == {"x": 100, "y": 100}
    assert view.evaluate("window.kgView.cy.$('#t1').position()") == {"x": 400, "y": 250}


def test_the_whole_net_migrates_when_a_new_node_arrives(view):
    # The spec change of 2026-08-14 (Birk), replacing the old "existing nodes
    # stay put" rule: a graph change re-distributes EVERY node so the net fills
    # the freed space. What is forbidden is the jump, not the movement.
    update(view, GRAPH_1)
    before = view.evaluate("window.kgView.cy.$('#t1').position()")

    update(view, GRAPH_2)

    after = view.evaluate("window.kgView.cy.$('#t1').position()")
    assert after != before
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


def positions(page):
    return page.evaluate(
        "() => Object.fromEntries(window.kgView.cy.nodes().map(n => [n.id(), n.position()]))"
    )


def _grow(page, base_graph, new_person="pX", anchor_term="t0"):
    """`base_graph` as it currently sits on the wall, plus one new person.

    The positions are read back off the live view, which is what the server
    would have persisted — so the only unplaced node in the result is the one
    that just joined.
    """
    grown = {**base_graph, "nodes": [dict(n) for n in base_graph["nodes"]], "edges": list(base_graph["edges"])}
    live = positions(page)
    for node in grown["nodes"]:
        node["x"], node["y"] = live[node["id"]]["x"], live[node["id"]]["y"]
    grown["nodes"].append(
        {"id": new_person, "type": "person", "portrait": "", "hidden": False, "x": None, "y": None}
    )
    grown["edges"].append({"id": f"e{new_person}", "source": new_person, "target": anchor_term})
    return grown


def _pairwise_distances(placement, ids):
    return [
        math.dist(
            (placement[a]["x"], placement[a]["y"]),
            (placement[b]["x"], placement[b]["y"]),
        )
        for i, a in enumerate(ids)
        for b in ids[i + 1 :]
    ]


def _correlation(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return cov / (sx * sy)


def test_the_migration_is_incremental_and_never_a_re_roll(view):
    # The anti-jump requirement, stated as a measurement rather than as
    # "nothing moves". fcose runs with randomize:false from the CURRENT
    # positions, so the new arrangement is a deformation of the old one: the
    # net keeps its shape while it re-distributes. Correlating the pairwise
    # distance matrix before and after catches the failure this rules out —
    # a layout re-rolled from random would score around zero, and no amount
    # of "every node moved a bit" can fake a high score.
    update(view, _unplaced_net())
    before = positions(view)

    update(view, _grow(view, _unplaced_net()))

    after = positions(view)
    shared = sorted(set(before) & set(after))
    assert len(shared) > 10
    correlation = _correlation(
        _pairwise_distances(before, shared), _pairwise_distances(after, shared)
    )
    assert correlation > 0.8


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


def test_every_graph_theme_paints_pure_black_and_pure_white(page, static_server):
    # Birk's 2026-08-15 colour correction, binding: the ground is #000000 and
    # the label text #FFFFFF, in ALL THREE graph themes, with the label
    # outline following the ground exactly (a near-black outline over a pure
    # black ground shows as a halo). Projection is additive onto a whiteboard,
    # so on-site black is whatever ambient light sits on the surface (spec
    # 10.4): a tint gains nothing there and costs contrast.
    #
    # Read through Cytoscape's baked style and the live CSS, not by parsing
    # the .css files — what matters is what reaches the wall, and the theme
    # swap is asynchronous (see the test above it).
    for theme in ("a", "b", "c"):
        page.goto(f"{static_server}/frontend/projection.html?theme={theme}")
        page.wait_for_function("window.kgView !== undefined")
        page.evaluate("(g) => window.kgView.update(g, 1)", ONE_PERSON)
        wait_for_layout(page)

        assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(0, 0, 0)"
        baked = page.evaluate(
            """() => {
                 const term = window.kgView.cy.$('#t1');
                 const person = window.kgView.cy.$('#p1');
                 return {
                   label: term.style('color'),
                   outline: term.style('text-outline-color'),
                   dot: term.style('background-color'),
                   ring: person.style('border-color'),
                 };
               }"""
        )
        assert baked["label"] == "rgb(255,255,255)"
        assert baked["outline"] == "rgb(0,0,0)"
        # The dot is the label's own node; nothing asks it to differ from it.
        assert baked["dot"] == "rgb(255,255,255)"
        # The one element that is NOT greyscale: the golden ring is the
        # concept's signature and survives the correction untouched.
        assert baked["ring"] == "rgb(201,162,39)"


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


def test_raising_the_dial_removes_terms_and_lowering_it_brings_them_back(view):
    update(view, GRAPH_2)

    view.evaluate("window.kgView.setMinMentions(2)")
    wait_for_layout(view)

    assert view.evaluate("window.kgView.cy.$('#t1').length") == 0
    assert view.evaluate("window.kgView.cy.$('#p1').length") == 1
    view.evaluate("window.kgView.setMinMentions(1)")
    wait_for_layout(view)
    assert view.evaluate("window.kgView.cy.$('#t1').length") == 1
    assert view.evaluate("window.kgView.cy.$('#p1').length") == 1


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


def test_count_label_overlaps_also_counts_person_discs_sitting_on_each_other(page, static_server):
    # Birk's seventh brief, 2026-08-15: two portrait discs overlapping is a
    # defect in its own right and had never been measured. Same hand-placed
    # geometry as above: two discs half a diameter apart must count as one
    # pair, a third far away must not.
    page.goto(f"{static_server}/frontend/static/render-harness.html")
    page.wait_for_function("window.kgView !== undefined")
    result = page.evaluate(
        """async () => {
             const { countLabelOverlaps } = await import('/frontend/static/projection.js');
             const cy = window.kgView.cy;
             cy.add([
               { data: { id: 'pa', type: 'person' }, classes: 'person', position: { x: 0, y: 0 } },
               { data: { id: 'pb', type: 'person' }, classes: 'person', position: { x: 28, y: 0 } },
               { data: { id: 'pc', type: 'person' }, classes: 'person', position: { x: 900, y: 900 } },
             ]);
             return countLabelOverlaps(cy);
           }"""
    )
    # render-harness.html is pinned to theme-a: --person-size: 56.
    assert result["personPairs"] == 1


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


def test_a_grown_dense_net_stays_clear_of_overlaps(view):
    # Growing an already-placed net runs the whole pipeline again, over a
    # starting state that is already settled. The picture that comes out the
    # other side must be at least as clean as the one that went in — a
    # migration that fills the freed space by piling labels on portraits has
    # bought nothing.
    update(view, _dense_net())

    update(view, _grow(view, _dense_net()))

    assert view.evaluate("() => window.kgView.labelOverlaps()") == {
        "labelPairs": 0,
        "labelsOnPersons": 0,
        "personPairs": 0,
    }


def test_the_settled_net_is_both_landscape_and_clear(view):
    # Two requirements at once, because either alone would pass over a picture
    # that is still wrong. fcose settles an isotropic, near-round cloud (1.18:1
    # on the seeded graph, measured 2026-08-15) which a 16:9 fit can only show
    # at 59% of the canvas width, and it leaves 42 overlapping label pairs and
    # 26 labels on portrait discs behind. settlePlacement plus the declutter
    # pass answer both — which is the measurement that kept them through the
    # fcose migration instead of deleting them with the rest.
    update(view, _dense_net())

    box = view.evaluate(
        "() => window.kgView.cy.nodes().boundingBox({ includeLabels: true })"
    )
    assert box["w"] > box["h"]
    assert view.evaluate("() => window.kgView.labelOverlaps()") == {
        "labelPairs": 0,
        "labelsOnPersons": 0,
        "personPairs": 0,
    }


def _crowded_persons_net(persons=20, terms=3, edges_per_person=3):
    """Many persons around very few, very short terms.

    The shape that exposes what settlePlacement used to be blind to: the
    labels are short enough to clear each other on their own, so the pass
    scored the picture as perfect while the portrait discs those persons carry
    were still lying on top of each other (measured 2026-08-15: 0 label pairs,
    0 labels on discs, 7 disc pairs).
    """
    nodes = [
        {"id": f"p{i}", "type": "person", "portrait": "", "hidden": False, "x": None, "y": None}
        for i in range(persons)
    ] + [
        {"id": f"t{i}", "type": "term", "label": f"Ort {i}", "mentions": 2, "hidden": False, "x": None, "y": None}
        for i in range(terms)
    ]
    edges = [
        {"id": f"e{i}-{j}", "source": f"p{i}", "target": f"t{(i * 3 + j) % terms}"}
        for i in range(persons)
        for j in range(edges_per_person)
    ]
    return {"version": 1, "min_mentions": 1, "nodes": nodes, "edges": edges, "quotes": []}


def test_the_settled_net_leaves_no_person_disc_lying_on_another(view):
    # Birk's seventh brief, 2026-08-15: overlapping portrait discs are a defect
    # of their own, and the placement is the only pass that can fix them —
    # declutter moves labels, never nodes. So the disc pairs have to be part of
    # what settlePlacement scores, or it stops working the moment the labels
    # happen to be clear.
    update(view, _crowded_persons_net())

    assert view.evaluate("() => window.kgView.labelOverlaps()")["personPairs"] == 0


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
    # "Worse" is the pass's OWN score, not either count on its own — rule (c)
    # outranks rule (b), so a label on a portrait disc is deliberately worth
    # three label-on-label pairs (PERSON_COLLISION_WEIGHT in projection.js) and
    # trading the cheaper collision for the dearer one is the pass working, not
    # regressing. Measured 2026-08-15 on this net from that deliberately bad
    # start: 7 pairs and 23 labels on discs in, 9 and 15 out.
    def score(overlaps):
        return overlaps["labelPairs"] + 3 * overlaps["labelsOnPersons"]

    assert score(after) <= score(before)
    assert after["labelsOnPersons"] <= before["labelsOnPersons"]


def test_lowering_the_dial_lets_the_returning_terms_rejoin_without_jumping(view):
    # Raising min_mentions REMOVES term nodes from cy, so lowering it again
    # re-adds them. In a session whose positions the server has not yet
    # persisted back into the graph data those nodes carry x/y null, so
    # without `lastSeen` they would start from the origin — and the migration
    # that follows would be a jump for exactly the half of the net that
    # returned. They start where they left instead, so what a visitor sees is
    # the same glide the rest of the net makes.
    update(view, _dense_net())
    before = positions(view)

    view.evaluate("() => window.kgView.setMinMentions(3)")
    wait_for_layout(view)
    view.evaluate("() => window.kgView.setMinMentions(1)")
    wait_for_layout(view)

    after = positions(view)
    shared = sorted(set(before) & set(after))
    correlation = _correlation(
        _pairwise_distances(before, shared), _pairwise_distances(after, shared)
    )
    assert correlation > 0.8


def test_raising_the_dial_spreads_the_net_into_the_freed_space(view):
    # The whole point of the 2026-08-14 spec change. Before it, hiding terms
    # left the survivors sitting in their old holes and the picture shrank:
    # measured on the seeded graph, the node cloud went from 93% of the canvas
    # width at min_mentions=1 to 73% at min_mentions=3. Now the net
    # re-distributes, so the freed space is used, not left empty.
    update(view, _dense_net())

    view.evaluate("() => window.kgView.setMinMentions(3)")
    wait_for_layout(view)

    covered = view.evaluate(
        """() => {
             const cy = window.kgView.cy;
             const box = cy.nodes().renderedBoundingBox({ includeLabels: true });
             return box.w / cy.width();
           }"""
    )
    assert covered > 0.8


def test_the_net_glides_into_its_new_arrangement_instead_of_cutting_to_it(view):
    # A PNG cannot show motion and neither can a position assertion taken
    # after the fact, so this samples the live view every animation frame
    # while the dial change is in flight. At least one frame must catch the
    # net strictly between its old arrangement and its new one — that is the
    # difference between a glide and a cut.
    update(view, _dense_net())

    view.evaluate(
        """() => {
             const cy = window.kgView.cy;
             window.kgView.setMinMentions(2);
             const ids = cy.nodes().map((n) => n.id()).sort();
             window.__samples = [];
             const sample = () => {
               window.__samples.push(ids.map((id) => {
                 const p = cy.$id(id).position();
                 return [p.x, p.y];
               }));
               if (window.kgView.layoutPending) requestAnimationFrame(sample);
             };
             requestAnimationFrame(sample);
           }"""
    )
    wait_for_layout(view)

    samples = view.evaluate("() => window.__samples")
    first, last = samples[0], samples[-1]
    in_flight = [s for s in samples if s != first and s != last]
    assert in_flight, "the net snapped straight to its new arrangement"
    # And the frames really are interpolating, not a second layout's output:
    # somewhere in the middle a node sits between where it started and where
    # it ended, on both axes.
    def between(a, b, c):
        return min(a, c) < b < max(a, c)

    assert any(
        between(first[i][0], sample[i][0], last[i][0]) and between(first[i][1], sample[i][1], last[i][1])
        for sample in in_flight
        for i in range(len(first))
    )


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


def test_the_kept_passes_still_beat_fcoses_own_label_handling(page, static_server):
    # The measurement behind the one decision the fourth pre-render brief left
    # open: fcose's `nodeDimensionsIncludeLabels` was expected to REPLACE the
    # hand-built label-aware placement, and on the numbers it does not.
    #
    # A force layout is a compromise between forces, not an overlap solver —
    # it knows how big a term node's label box is and still lets boxes cross.
    # Measured 2026-08-15 on theme-b (32px labels) at 50 persons / 75 distinct
    # long labels, from the identical deterministic golden-angle start state
    # so this isolates the passes rather than comparing two different runs:
    # fcose alone settles at 42 overlapping label-box pairs and 26 labels on
    # person discs; settlePlacement plus the declutter pass clear both to zero
    # — and lift the node cloud from 59% to 89% of the canvas width, which no
    # fcose option addresses at all.
    #
    # The thresholds below are far lower than those numbers on purpose. This
    # module's net gives every person exactly five terms, where the seeded
    # graph draws them Zipf-skewed and so builds hubs; the regular net is
    # measurably the easier one (6 pairs / 3 on discs / 71% width, same date).
    # What is asserted is therefore the direction and the fact that fcose does
    # not get there alone — the margin belongs to the seeded graph.
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
             if (cy.layoutUtilities) cy.layoutUtilities({ desiredAspectRatio: 16 / 9, componentSpacing: 80 });
             // Mirror projection.js's own from-scratch seeding exactly (golden
             // angle at one ideal edge length, around the origin), so the only
             // difference from window.kgView's own run is settlePlacement and
             // the declutter pass that follow the layout in production.
             graph.nodes.forEach((n, index) => {
               const angle = index * 2.39996;
               cy.$id(n.id).position({
                 x: Math.cos(angle) * LAYOUT.idealEdgeLength,
                 y: Math.sin(angle) * LAYOUT.idealEdgeLength,
               });
             });
             await new Promise((resolve) => {
               const layout = cy.layout(LAYOUT);
               layout.one('layoutstop', resolve);
               layout.run();
             });
             cy.fit(60);
             const box = cy.nodes().renderedBoundingBox({ includeLabels: true });
             const overlaps = { ...countLabelOverlaps(cy), width: box.w / cy.width() };
             cy.destroy();
             el.remove();
             return overlaps;
           }""",
        graph,
    )

    assert raw["labelPairs"] >= 3
    assert raw["labelsOnPersons"] >= 1
    assert raw["width"] < 0.8
    assert after == {"labelPairs": 0, "labelsOnPersons": 0, "personPairs": 0}


# --- Fill the screen (Birk's fourth pre-render brief, 2026-08-14) ---------
#
# "Node size and font size must adapt so the graph ALWAYS fills the screen
# without overcrowding. Two or three nodes -> everything large. A hundred
# nodes -> everything small. Never a fixed scale that eventually becomes
# unreadable." Nothing in this repo scales type: everything is sized in MODEL
# units, and the viewport fit does the scaling for free. These tests pin that
# down, because a stray `min-zoomed-font-size` or a rendered-pixel node size
# would silently break it and no other test would notice.


def _rendered_scale(page):
    return page.evaluate(
        """() => {
             const cy = window.kgView.cy;
             const box = cy.nodes().renderedBoundingBox({ includeLabels: true });
             return {
               zoom: cy.zoom(),
               // What a viewer actually measures with a ruler on the wall.
               font: Number(cy.nodes('.term')[0].numericStyle('font-size')) * cy.zoom(),
               disc: Number(cy.nodes('.person')[0].numericStyle('width')) * cy.zoom(),
               width: box.w / cy.width(),
               height: box.h / cy.height(),
             };
           }"""
    )


@pytest.mark.parametrize("persons", [5, 20, 50])
def test_the_net_fills_the_canvas_at_every_size(page, static_server, persons):
    page.goto(f"{static_server}/frontend/projection.html?theme=b")
    page.wait_for_function("window.kgView !== undefined")

    update(page, _dense_net(persons=persons, terms=max(6, persons * 3 // 2)))

    scale = _rendered_scale(page)
    # One axis is always the binding one after a fit; both must be well used,
    # or the wall is showing a stamp in the middle of a black field.
    assert max(scale["width"], scale["height"]) > 0.85
    assert min(scale["width"], scale["height"]) > 0.6


def test_type_grows_as_the_net_shrinks(page, static_server):
    # The comparison the brief asks for as evidence: the SAME renderer, the
    # same theme, the same model-unit type token — and a font that reaches the
    # wall larger when there is less to show.
    scales = {}
    for persons in (5, 20, 50):
        page.goto(f"{static_server}/frontend/projection.html?theme=b")
        page.wait_for_function("window.kgView !== undefined")
        update(page, _dense_net(persons=persons, terms=max(6, persons * 3 // 2)))
        scales[persons] = _rendered_scale(page)

    assert scales[5]["font"] > scales[20]["font"] > scales[50]["font"]
    assert scales[5]["disc"] > scales[20]["disc"] > scales[50]["disc"]
