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
