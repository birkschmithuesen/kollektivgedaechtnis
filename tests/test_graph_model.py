import pytest

GRAPH = {
    "version": 1,
    "max_terms": 32,
    "nodes": [
        {"id": "p1", "type": "person", "portrait": "/media/portraits/a.png", "hidden": False, "x": 1, "y": 2},
        {"id": "p2", "type": "person", "portrait": "/media/portraits/b.png", "hidden": False, "x": None, "y": None},
        {"id": "p3", "type": "person", "portrait": None, "hidden": True, "x": None, "y": None},
        {"id": "t1", "type": "term", "label": "Holzbau", "mentions": 2, "created_at": 10.0, "hidden": False, "x": None, "y": None},
        {"id": "t2", "type": "term", "label": "Bodenpreise", "mentions": 1, "created_at": 20.0, "hidden": False, "x": None, "y": None},
        {"id": "t3", "type": "term", "label": "Unfug", "mentions": 5, "created_at": 5.0, "hidden": True, "x": None, "y": None},
    ],
    "edges": [
        {"id": "e1", "source": "p1", "target": "t1"},
        {"id": "e2", "source": "p2", "target": "t1"},
        {"id": "e3", "source": "p1", "target": "t2"},
        {"id": "e4", "source": "p3", "target": "t3"},
    ],
    "quotes": [],
}


@pytest.fixture()
def model(page, static_server):
    page.goto(f"{static_server}/frontend/static/test-harness.html")
    page.wait_for_function("window.kgModel !== undefined")
    return page


def call(page, fn, *args):
    return page.evaluate(f"(args) => window.kgModel.{fn}(...args)", list(args))


def test_max_terms_high_enough_shows_every_unhidden_term(model):
    view = call(model, "visibleGraph", GRAPH, 32)
    assert sorted(n["id"] for n in view["nodes"]) == ["p1", "p2", "t1", "t2"]


def test_hidden_entries_never_appear_at_any_cap(model):
    for cap in (1, 2, 3):
        view = call(model, "visibleGraph", GRAPH, cap)
        ids = {n["id"] for n in view["nodes"]}
        assert "t3" not in ids and "p3" not in ids


def test_the_cap_is_fully_reversible(model):
    before = call(model, "visibleGraph", GRAPH, 32)
    call(model, "visibleGraph", GRAPH, 1)
    after = call(model, "visibleGraph", GRAPH, 32)
    assert before == after


def test_edges_need_both_endpoints_visible(model):
    # Cap 1 keeps only t1 (2 mentions beats t2's 1) -- t2's edge must drop too.
    view = call(model, "visibleGraph", GRAPH, 1)
    assert [e["id"] for e in view["edges"]] == ["e1", "e2"]


def test_person_nodes_stay_even_without_visible_terms(model):
    no_terms = {
        **GRAPH,
        "nodes": [dict(n, hidden=True) if n["type"] == "term" else n for n in GRAPH["nodes"]],
    }
    view = call(model, "visibleGraph", no_terms, 32)
    assert sorted(n["id"] for n in view["nodes"]) == ["p1", "p2"]


def test_to_cytoscape_maps_positions_labels_and_classes(model):
    view = call(model, "visibleGraph", GRAPH, 32)
    elements = call(model, "toCytoscape", view)
    by_id = {e["data"]["id"]: e for e in elements}
    assert by_id["p1"]["classes"] == "person"
    assert by_id["p1"]["position"] == {"x": 1, "y": 2}
    assert "position" not in by_id["p2"]
    assert by_id["t1"]["data"]["label"] == "Holzbau"
    assert by_id["e1"]["data"]["source"] == "p1"


def test_new_node_ids_reports_only_what_the_renderer_has_not_placed(model):
    view = call(model, "visibleGraph", GRAPH, 32)
    assert sorted(call(model, "newNodeIds", ["p1", "t1"], view)) == ["p2", "t2"]
    assert call(model, "newNodeIds", ["p1", "p2", "t1", "t2"], view) == []


# --- The selection rule itself (spec 2026-08-29 §3) -----------------------
#
# Shared terms (>=2 mentions) come first, filled with the newest single
# mentions up to the cap. If the shared terms alone exceed the cap, they are
# capped too, most-mentioned first.

SELECTION_GRAPH = {
    "version": 1,
    "max_terms": 32,
    "nodes": [
        {"id": "p1", "type": "person", "portrait": "", "hidden": False, "x": None, "y": None},
        # Two shared terms.
        {"id": "s1", "type": "term", "label": "Shared A", "mentions": 3, "created_at": 1.0, "hidden": False, "x": None, "y": None},
        {"id": "s2", "type": "term", "label": "Shared B", "mentions": 2, "created_at": 2.0, "hidden": False, "x": None, "y": None},
        # Three single mentions at different ages -- old, middle, newest.
        {"id": "o1", "type": "term", "label": "Old single", "mentions": 1, "created_at": 10.0, "hidden": False, "x": None, "y": None},
        {"id": "o2", "type": "term", "label": "Middle single", "mentions": 1, "created_at": 20.0, "hidden": False, "x": None, "y": None},
        {"id": "o3", "type": "term", "label": "New single", "mentions": 1, "created_at": 30.0, "hidden": False, "x": None, "y": None},
    ],
    "edges": [],
    "quotes": [],
}


def test_shared_terms_always_win_over_singles(model):
    # Cap 2: exactly room for the two shared terms, no singles at all.
    view = call(model, "visibleGraph", SELECTION_GRAPH, 2)
    assert sorted(n["id"] for n in view["nodes"] if n["type"] == "term") == ["s1", "s2"]


def test_singles_are_filled_in_by_recency_newest_first(model):
    # Cap 3: both shared terms, plus exactly one single -- the newest one.
    view = call(model, "visibleGraph", SELECTION_GRAPH, 3)
    ids = sorted(n["id"] for n in view["nodes"] if n["type"] == "term")
    assert ids == ["o3", "s1", "s2"]


def test_a_young_single_is_in_an_old_one_is_out(model):
    view = call(model, "visibleGraph", SELECTION_GRAPH, 3)
    ids = {n["id"] for n in view["nodes"] if n["type"] == "term"}
    assert "o3" in ids  # youngest single: in
    assert "o1" not in ids  # oldest single: out


def test_when_shared_terms_alone_exceed_the_cap_they_are_capped_by_mentions(model):
    # Cap 1 with two shared terms present: only the more-mentioned one survives,
    # and no single ever gets a look-in.
    view = call(model, "visibleGraph", SELECTION_GRAPH, 1)
    ids = {n["id"] for n in view["nodes"] if n["type"] == "term"}
    assert ids == {"s1"}


def test_raising_the_cap_only_adds_never_reorders_what_was_already_in(model):
    small = {n["id"] for n in call(model, "visibleGraph", SELECTION_GRAPH, 3)["nodes"] if n["type"] == "term"}
    large = {n["id"] for n in call(model, "visibleGraph", SELECTION_GRAPH, 5)["nodes"] if n["type"] == "term"}
    assert small <= large


# --- Hysteresis grace list (spec §7: no flicker at the boundary) ----------


def test_keep_ids_hold_a_term_past_its_natural_cutoff(model):
    # Cap 2 alone would drop 'o3' (only room for the two shared terms); the
    # grace list keeps it anyway, ON TOP of the cap -- not by displacing one
    # of the two shared terms. A grace hold protecting a stale entry must
    # never come at the cost of blocking a fresh one (see the docstring in
    # graph-model.js), and shared terms rank above every single mention
    # regardless, so bumping one of them would be exactly that.
    view = call(model, "visibleGraph", SELECTION_GRAPH, 2, ["o3"])
    ids = {n["id"] for n in view["nodes"] if n["type"] == "term"}
    assert ids == {"s1", "s2", "o3"}


def test_the_grace_list_can_briefly_exceed_the_cap(model):
    # The overflow is bounded by how many ids are actually in grace, not
    # unbounded -- two extra grace ids means at most two extra terms.
    view = call(model, "visibleGraph", SELECTION_GRAPH, 2, ["o3", "o2"])
    ids = {n["id"] for n in view["nodes"] if n["type"] == "term"}
    assert ids == {"s1", "s2", "o3", "o2"}


def test_keep_ids_cannot_resurrect_a_hidden_or_absent_term(model):
    hidden_graph = {
        **SELECTION_GRAPH,
        "nodes": [
            dict(n, hidden=True) if n["id"] == "o3" else n for n in SELECTION_GRAPH["nodes"]
        ],
    }
    view = call(model, "visibleGraph", hidden_graph, 3, ["o3", "does-not-exist"])
    ids = {n["id"] for n in view["nodes"] if n["type"] == "term"}
    assert "o3" not in ids and "does-not-exist" not in ids
