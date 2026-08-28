import json

import pytest

from kg.export import build_graph, write_graph_json
from kg.store import Store


@pytest.fixture()
def store(tmp_path):
    s = Store.open(tmp_path / "kg.db")
    yield s
    s.close()


def seed(store):
    p1 = store.create_person(started_at=100.0, portrait_path="portraits/a.png")
    p2 = store.create_person(started_at=200.0, portrait_path="portraits/b.png")
    t1 = store.get_or_create_term("Recycling-Beton", created_at=110.0)
    t2 = store.get_or_create_term("Holzbau", created_at=210.0)
    store.add_edge(p1.id, t1.id, created_at=111.0)
    store.add_edge(p2.id, t1.id, created_at=211.0)
    store.add_edge(p2.id, t2.id, created_at=212.0)
    store.add_quote(p1.id, "Wir bauen zu viel Neues.", created_at=112.0)
    store.save_positions({p1.id: (10.0, 20.0)})
    return p1, p2, t1, t2


def test_graph_carries_full_state_with_counts_flags_and_positions(store):
    p1, p2, t1, t2 = seed(store)

    graph = build_graph(store)

    nodes = {n["id"]: n for n in graph["nodes"]}
    assert nodes[p1.id]["type"] == "person"
    assert nodes[p1.id]["portrait"] == "/media/portraits/a.png"
    assert nodes[p1.id]["x"] == 10.0 and nodes[p1.id]["y"] == 20.0
    assert nodes[p2.id]["x"] is None
    assert nodes[t1.id]["label"] == "Recycling-Beton"
    assert nodes[t1.id]["mentions"] == 2
    assert nodes[t2.id]["mentions"] == 1
    assert len(graph["edges"]) == 3
    assert graph["quotes"][0]["text"] == "Wir bauen zu viel Neues."
    assert graph["version"] == 1


def test_hidden_entries_are_exported_with_the_flag_not_removed(store):
    p1, _, t1, _ = seed(store)
    store.set_hidden(f"term:{t1.id}", True)
    store.set_hidden(f"person:{p1.id}", True)

    graph = build_graph(store)
    nodes = {n["id"]: n for n in graph["nodes"]}

    assert nodes[t1.id]["hidden"] is True
    assert nodes[p1.id]["hidden"] is True
    # Nothing is discarded: hiding is reversible (spec 8).
    assert len(graph["edges"]) == 3


def test_min_mentions_is_reported_but_not_applied(store):
    seed(store)
    store.set_setting("min_mentions", "2")

    graph = build_graph(store)

    assert graph["min_mentions"] == 2
    assert len(graph["nodes"]) == 4  # filtering happens in the consumer


def test_write_is_atomic_and_leaves_valid_json(store, tmp_path):
    seed(store)
    path = tmp_path / "out" / "graph.json"

    graph = write_graph_json(store, path)

    assert path.exists()
    assert not list(path.parent.glob("*.tmp"))
    assert json.loads(path.read_text(encoding="utf-8")) == graph


def test_export_of_an_empty_graph_is_valid(store, tmp_path):
    graph = write_graph_json(store, tmp_path / "graph.json")
    assert graph["nodes"] == [] and graph["edges"] == [] and graph["quotes"] == []


def test_a_persons_second_quote_is_dropped_from_the_export(store):
    """Altbestand may still carry >1 quote per person (no migration, Birk's
    call) — the export keeps only the first so a person never appears twice.
    """
    p1 = store.create_person(started_at=100.0)
    store.add_quote(p1.id, "Erstes Zitat.", created_at=101.0)
    store.add_quote(p1.id, "Zweites Zitat.", created_at=102.0)

    graph = build_graph(store)

    texts = [q["text"] for q in graph["quotes"] if q["person_id"] == p1.id]
    assert texts == ["Erstes Zitat."]
