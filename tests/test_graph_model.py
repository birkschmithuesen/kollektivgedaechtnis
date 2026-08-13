import pytest

GRAPH = {
    "version": 1,
    "min_mentions": 1,
    "nodes": [
        {"id": "p1", "type": "person", "portrait": "/media/portraits/a.png", "hidden": False, "x": 1, "y": 2},
        {"id": "p2", "type": "person", "portrait": "/media/portraits/b.png", "hidden": False, "x": None, "y": None},
        {"id": "p3", "type": "person", "portrait": None, "hidden": True, "x": None, "y": None},
        {"id": "t1", "type": "term", "label": "Holzbau", "mentions": 2, "hidden": False, "x": None, "y": None},
        {"id": "t2", "type": "term", "label": "Bodenpreise", "mentions": 1, "hidden": False, "x": None, "y": None},
        {"id": "t3", "type": "term", "label": "Unfug", "mentions": 5, "hidden": True, "x": None, "y": None},
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


def test_min_mentions_one_shows_every_unhidden_term(model):
    view = call(model, "visibleGraph", GRAPH, 1)
    assert sorted(n["id"] for n in view["nodes"]) == ["p1", "p2", "t1", "t2"]


def test_raising_the_dial_leaves_only_what_is_shared(model):
    view = call(model, "visibleGraph", GRAPH, 2)
    assert sorted(n["id"] for n in view["nodes"]) == ["p1", "p2", "t1"]
    assert [e["id"] for e in view["edges"]] == ["e1", "e2"]


def test_hidden_entries_never_appear_at_any_dial_setting(model):
    for value in (1, 2, 3):
        view = call(model, "visibleGraph", GRAPH, value)
        ids = {n["id"] for n in view["nodes"]}
        assert "t3" not in ids and "p3" not in ids


def test_the_dial_is_fully_reversible(model):
    before = call(model, "visibleGraph", GRAPH, 1)
    call(model, "visibleGraph", GRAPH, 3)
    after = call(model, "visibleGraph", GRAPH, 1)
    assert before == after


def test_edges_need_both_endpoints_visible(model):
    view = call(model, "visibleGraph", GRAPH, 3)
    assert view["edges"] == []


def test_person_nodes_stay_even_without_visible_terms(model):
    view = call(model, "visibleGraph", GRAPH, 5)
    assert sorted(n["id"] for n in view["nodes"]) == ["p1", "p2"]


def test_to_cytoscape_maps_positions_labels_and_classes(model):
    view = call(model, "visibleGraph", GRAPH, 1)
    elements = call(model, "toCytoscape", view)
    by_id = {e["data"]["id"]: e for e in elements}
    assert by_id["p1"]["classes"] == "person"
    assert by_id["p1"]["position"] == {"x": 1, "y": 2}
    assert "position" not in by_id["p2"]
    assert by_id["t1"]["data"]["label"] == "Holzbau"
    assert by_id["e1"]["data"]["source"] == "p1"


def test_new_node_ids_reports_only_what_the_renderer_has_not_placed(model):
    view = call(model, "visibleGraph", GRAPH, 1)
    assert sorted(call(model, "newNodeIds", ["p1", "t1"], view)) == ["p2", "t2"]
    assert call(model, "newNodeIds", ["p1", "p2", "t1", "t2"], view) == []
