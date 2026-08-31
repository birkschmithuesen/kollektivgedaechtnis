"""Tool 1's `graph.json` is Tool 2's entire input. This file pins the contract.

Two halves, and the second is the important one:

1. The fixture is a REAL artefact of `sim/replay.py` (see
   `sim/data/graph-19c.provenance.md`), not a hand-written dict.
2. The DRIFT GUARD builds a graph through the live `kg.export.build_graph` and
   asserts the key sets and types still agree with that artefact. Values are
   deliberately never compared: interview content changes legitimately, and a
   test that goes red for that teaches the reader to ignore it.

Spec §13 names five properties of Tool 1 that are now load-bearing. Four of
them are pinned here; the fifth (`broadcast_graph` firing after the pipeline)
is a timing property and lives in `tests/test_dream_trigger.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kg.config import Config
from kg.export import build_graph
from kg.store import Store
from kg2.graph_client import fetch_graph

# graph-20a.json seit 2026-08-30: der Replay ueber das neue Drei-Fragen-Korpus.
# graph-19c stammt aus den alten fuenf Fragen und kennt weder `in_dream` noch
# `dream_role` — ein Vertragstest gegen ein Artefakt, das die Felder nicht hat,
# prueft den Vertrag von gestern.
FIXTURE = Path(__file__).resolve().parent.parent / "sim" / "data" / "graph-20a.json"
REAL_GRAPH = json.loads(FIXTURE.read_text(encoding="utf-8"))

# Every JSON path Tool 2 reads, and the type it must find there. This list is
# the contract, written out rather than derived, so that deleting a field from
# Tool 1's export fails here with the field's name in the message.
REQUIRED: dict[str, set[str]] = {
    ".version": {"int"},
    ".generated_at": {"float"},
    ".nodes[].id": {"str"},
    ".nodes[].type": {"str"},
    ".nodes[].created_at": {"float"},
    ".nodes[].hidden": {"bool"},
    ".nodes[].label": {"str"},  # terms only
    ".nodes[].mentions": {"int"},  # terms only — spec §13(3), the weighting input
    ".edges[].id": {"str"},
    ".edges[].source": {"str"},
    ".edges[].target": {"str"},
    ".quotes[].id": {"str"},  # spec §13(2), kept for Tool 2's benefit alone
    ".quotes[].person_id": {"str"},
    ".quotes[].text": {"str"},
}


def type_map(value, prefix: str = "") -> dict[str, set[str]]:
    """Every JSON path in `value`, mapped to the set of types found there.

    List indices collapse to `[]`, so 60 person nodes contribute one entry per
    field rather than sixty. Values themselves are never recorded — this is a
    contract check, and the contract is shape, not content.
    """
    out: dict[str, set[str]] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            for path, types in type_map(item, f"{prefix}.{key}").items():
                out.setdefault(path, set()).update(types)
    elif isinstance(value, list):
        for item in value:
            for path, types in type_map(item, f"{prefix}[]").items():
                out.setdefault(path, set()).update(types)
    else:
        out[prefix] = {type(value).__name__}
    return out


def live_graph(tmp_path) -> dict:
    """A graph built through the REAL exporter, covering every optional branch.

    Deliberately exercises both sides of every nullable field — a person with a
    portrait and one without, a placed node and an unplaced one, a hidden term —
    so the type map below carries `NoneType` exactly where the export really can
    produce it.
    """
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    with_portrait = store.create_person(started_at=100.0, portrait_path="portraits/a.png")
    without = store.create_person(started_at=200.0)
    shared = store.get_or_create_term("Recycling-Beton", created_at=110.0)
    lonely = store.get_or_create_term("Sickerfähige Beläge", created_at=210.0)
    store.add_edge(with_portrait.id, shared.id, created_at=120.0)
    store.add_edge(without.id, shared.id, created_at=220.0)
    store.add_edge(without.id, lonely.id, created_at=221.0)
    store.add_quote(with_portrait.id, "Wir bauen zu viel Neues.", created_at=130.0)
    # Eine Person mit Namen, eine ohne — dieselbe Disziplin wie beim Porträt:
    # die meisten Personen stellen sich nicht vor, und beide Fälle müssen im
    # Typmap unter `.nodes[].name` auftauchen.
    store.set_person_name(with_portrait.id, "Frau Kirchner")
    store.set_hidden(f"term:{lonely.id}", True)
    store.save_positions({shared.id: (12.0, -8.0)})  # the other nodes stay null
    graph = build_graph(store)
    store.close()
    return graph


def test_the_fixture_is_the_real_run_and_not_a_toy(tmp_path):
    """Geprüft wird die EIGENSCHAFT „echter Lauf", nicht eine Zahlenliste.

    Bis 2026-08-30 standen hier die exakten Kennzahlen von Lauf 19c (60/163/
    267/117). Die brechen bei jedem neuen Replay, und zwar ohne dass etwas
    kaputt wäre — der Test hätte dann nur festgehalten, dass niemand das
    Korpus anfasst. Was er wirklich absichern soll, steht im Modul-Docstring:
    dass die Fixture aus `sim/replay.py` stammt und keine handgeschriebene
    Attrappe ist. Genau das prüfen die Schwellen unten.
    """
    persons = [n for n in REAL_GRAPH["nodes"] if n["type"] == "person"]
    terms = [n for n in REAL_GRAPH["nodes"] if n["type"] == "term"]

    # Ein voller Ausstellungstag, keine Handvoll Beispielknoten.
    assert len(persons) >= 50
    assert len(terms) >= 100
    assert len(REAL_GRAPH["edges"]) >= 200
    assert REAL_GRAPH["quotes"], "ein echter Lauf trägt Zitate"
    # Jede Person hat gesprochen: ein erfundener Graph hätte lose Knoten.
    beteiligt = {e["source"] for e in REAL_GRAPH["edges"]}
    assert len(beteiligt) >= len(persons) * 0.9
    # A hand-written fixture would not have a long tail of single mentions.
    singletons = [t for t in terms if t["mentions"] == 1]
    assert len(singletons) > 50


def test_every_path_tool_2_reads_exists_in_the_real_artefact():
    found = type_map(REAL_GRAPH)

    for path, types in REQUIRED.items():
        assert path in found, f"{path} is missing from sim/data/graph-20a.json"
        assert types <= found[path], f"{path}: expected {types}, found {found[path]}"


def test_every_path_tool_2_reads_is_still_produced_by_the_live_exporter(tmp_path):
    """The drift guard. If Tool 1's export loses a field, this fails here —
    not silently, months later, on the festival morning."""
    found = type_map(live_graph(tmp_path))

    for path, types in REQUIRED.items():
        assert path in found, f"kg.export.build_graph no longer produces {path}"
        assert types <= found[path], f"{path}: expected {types}, found {found[path]}"


def test_the_committed_artefact_and_the_live_exporter_agree_on_the_key_set(tmp_path):
    """Key sets, not values (Birk, 2026-08-25): content changes legitimately."""
    fixture_paths = set(type_map(REAL_GRAPH))
    live_paths = set(type_map(live_graph(tmp_path)))

    assert fixture_paths == live_paths, (
        "sim/data/graph-20a.json and kg.export.build_graph have drifted apart:\n"
        f"  only in the fixture: {sorted(fixture_paths - live_paths)}\n"
        f"  only in the export:  {sorted(live_paths - fixture_paths)}"
    )


def test_graph_json_is_complete_state_with_no_delta_mechanism():
    """Spec §13(1). A `changed`/`removed`/`since` key would mean Tool 2's poll
    is no longer sufficient and the whole §4.1 design has to be revisited."""
    assert set(REAL_GRAPH) == {"version", "generated_at", "max_terms", "nodes", "edges", "quotes"}


def test_hidden_stays_in_the_payload():
    """Spec §13(4) — it is Tool 2's exclusion input (§5.1)."""
    assert all("hidden" in node for node in REAL_GRAPH["nodes"])


def test_fetch_graph_returns_the_payload(tmp_path):
    calls = []

    def fake_get(url, timeout):
        calls.append((url, timeout))
        return REAL_GRAPH

    graph = fetch_graph("http://10.0.0.2:8800/graph.json", timeout=7.0, get=fake_get)

    assert graph["version"] == 1
    assert calls == [("http://10.0.0.2:8800/graph.json", 7.0)]


def test_fetch_graph_returns_none_when_tool_1_is_unreachable():
    """Spec §8: „Poll keeps failing quietly." Never an exception, because an
    exception in the watcher loop is one restart away from a blank screen B."""

    def dead(url, timeout):
        raise OSError("connection refused")

    assert fetch_graph("http://10.0.0.2:8800/graph.json", get=dead) is None


def test_fetch_graph_returns_none_for_a_truncated_body():
    def half_written(url, timeout):
        raise ValueError("Expecting value: line 1 column 1 (char 0)")

    assert fetch_graph("http://x/graph.json", get=half_written) is None


def test_fetch_graph_rejects_a_payload_that_is_not_a_graph():
    """An HTML error page parsed as JSON, or a proxy's `{"error": ...}`, must
    not be handed on as if it were state."""

    def wrong(url, timeout):
        return {"error": "bad gateway"}

    assert fetch_graph("http://x/graph.json", get=wrong) is None


def test_the_graph_client_has_no_way_to_write_to_tool_1():
    """Spec §2 is a guarantee, and the cheapest guarantee is having no verb.

    A source-level check on purpose: a future edit that adds a POST „just for
    the operator" fails here with the reason attached, which a behavioural test
    over the current code could never do.
    """
    import kg2.graph_client

    source = Path(kg2.graph_client.__file__).read_text(encoding="utf-8")

    for verb in (".post(", ".put(", ".patch(", ".delete("):
        assert verb not in source, f"kg2/graph_client.py must never {verb}"
