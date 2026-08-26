"""Spec §4.1 — when a dream is due, and the race that makes it hard.

Tool 1 broadcasts the graph TWICE per interview: once at the photo, when the
person node exists with no edges (`kg/core.py:156`), and once after the
pipeline, when the terms are in (`kg/core.py:198`). Only the second one means
„absorbed". Every test below exists because the first one must not fire a dream.
"""

from __future__ import annotations

import copy

from kg2.models import Dream
from kg2.trigger import TriggerState, absorbed_persons, evaluate, resume_state

EMPTY = TriggerState(frozenset(), None)


def graph(persons, edges=(), *, hidden_persons=(), generated_at=1000.0) -> dict:
    """A minimal graph.json in Tool 1's real shape. Terms only where edges need
    them — the trigger never looks at terms."""
    nodes = [
        {
            "id": pid,
            "type": "person",
            "portrait": None,
            "created_at": 1.0,
            "hidden": pid in hidden_persons,
            "x": None,
            "y": None,
        }
        for pid in persons
    ]
    targets = sorted({target for _, target in edges})
    nodes += [
        {
            "id": tid,
            "type": "term",
            "label": tid,
            "mentions": 1,
            "created_at": 2.0,
            "hidden": False,
            "x": None,
            "y": None,
        }
        for tid in targets
    ]
    return {
        "version": 1,
        "generated_at": generated_at,
        "min_mentions": 1,
        "nodes": nodes,
        "edges": [
            {"id": f"e{i}", "source": s, "target": t} for i, (s, t) in enumerate(edges, 1)
        ],
        "quotes": [],
    }


# -- the race itself --------------------------------------------------------


def test_a_person_node_without_edges_is_not_absorbed():
    """Tool 1 step 1: the photo landed, the pipeline has not run. THE bug."""
    assert absorbed_persons(graph(["p1"])) == set()


def test_a_person_node_with_an_edge_is_absorbed():
    """Tool 1 step 3: `broadcast_graph` after the pipeline."""
    assert absorbed_persons(graph(["p1"], [("p1", "t1")])) == {"p1"}


def test_a_bare_person_node_never_fires_a_dream():
    decision = evaluate(EMPTY, graph(["p1"]), now=5000.0, min_interval_s=240)

    assert decision.fire is False
    assert decision.reason == "nothing new"


def test_the_same_person_fires_once_the_pipeline_has_run():
    """The two polls a real interview produces, in order."""
    state = EMPTY
    at_photo = evaluate(state, graph(["p1"]), now=5000.0, min_interval_s=240)
    assert at_photo.fire is False

    after_pipeline = evaluate(
        state, graph(["p1"], [("p1", "t1")]), now=5030.0, min_interval_s=240
    )

    assert after_pipeline.fire is True
    assert after_pipeline.absorbed == frozenset({"p1"})
    assert after_pipeline.started_at == 5030.0


def test_a_new_bare_person_beside_an_absorbed_one_does_not_fire_again():
    """Person 2's photo lands while person 1's dream is done. Nothing new has
    been SAID yet, so nothing may happen."""
    state = TriggerState(frozenset({"p1"}), 5000.0)

    decision = evaluate(
        state, graph(["p1", "p2"], [("p1", "t1")]), now=6000.0, min_interval_s=240
    )

    assert decision.fire is False


# -- malformed payloads ------------------------------------------------------


def test_a_malformed_payload_yields_no_absorbed_persons():
    """`kg2.graph_client.fetch_graph` only checks that `version`, `nodes` and
    `edges` are present — never their value types (see review of an earlier
    task). A payload like this reaches `absorbed_persons` unfiltered; it must
    degrade to „nothing absorbed", never raise."""
    malformed = {"version": 1, "nodes": "corrupted", "edges": []}

    assert absorbed_persons(malformed) == set()


def test_a_well_shaped_list_of_ill_shaped_nodes_yields_no_absorbed_persons():
    """The harder half of the same gap: `nodes` IS a list, but an entry is a
    person dict with no `id`. Subscripting it would raise on a payload the
    client waved through, so the watcher would die on the poll instead of
    reading it as silence."""
    for nodes in (
        [{"type": "person"}],  # person, no id
        [{"type": "person", "id": None}],  # person, null id
        [{"type": "person"}, {"type": "person", "id": "p1"}],  # one of each
    ):
        graph = {"version": 1, "nodes": nodes, "edges": [{"id": "e1", "source": "p1"}]}
        assert absorbed_persons(graph) <= {"p1"}

    # And an edge with no `source` must not resurrect a person with no id.
    graph = {"version": 1, "nodes": [{"type": "person"}], "edges": [{"id": "e1"}]}
    assert absorbed_persons(graph) == set()


def test_an_unhashable_person_id_does_not_crash_the_set_comprehension():
    """`node.get("id")` used to go straight into a set comprehension. A list id
    (never produced by Tool 1, but never ruled out by `fetch_graph` either) is
    unhashable and raised `TypeError` before ids were filtered to strings."""
    bad = {
        "version": 1,
        "nodes": [{"id": ["weird"], "type": "person", "hidden": False}],
        "edges": [{"id": "e1", "source": ["weird"]}],
    }

    assert absorbed_persons(bad) == set()


def test_mixed_type_person_ids_do_not_crash_a_later_sort():
    """Not a bug in this function directly, but the property it must uphold
    for its caller: two ids of different types must never both survive into
    the returned set, or `sorted()` downstream in kg2.cycle raises trying to
    compare a str to an int."""
    mixed = {
        "version": 1,
        "nodes": [
            {"id": "p1", "type": "person", "hidden": False},
            {"id": 2, "type": "person", "hidden": False},
        ],
        "edges": [
            {"id": "e1", "source": "p1"},
            {"id": "e2", "source": 2},
        ],
    }

    result = absorbed_persons(mixed)

    assert result == {"p1"}
    assert sorted(result) == ["p1"]  # would raise if the int id survived


# -- the floor --------------------------------------------------------------


def test_the_floor_blocks_a_second_dream():
    state = TriggerState(frozenset({"p1"}), 5000.0)

    decision = evaluate(
        state, graph(["p1", "p2"], [("p1", "t1"), ("p2", "t2")]), now=5100.0, min_interval_s=240
    )

    assert decision.fire is False
    assert decision.reason == "floor"


def test_an_interview_that_lands_inside_the_floor_is_not_lost():
    """The floor is a DELAY, not a drop. If `evaluate` folded p2 into the seen
    set while declining, p2's dream would never happen at all."""
    state = TriggerState(frozenset({"p1"}), 5000.0)
    full = graph(["p1", "p2"], [("p1", "t1"), ("p2", "t2")])

    blocked = evaluate(state, full, now=5100.0, min_interval_s=240)
    assert blocked.fire is False

    later = evaluate(state, full, now=5241.0, min_interval_s=240)

    assert later.fire is True
    assert later.absorbed == frozenset({"p1", "p2"})


def test_the_floor_is_measured_from_the_start_of_the_last_dream():
    state = TriggerState(frozenset({"p1"}), 5000.0)
    full = graph(["p1", "p2"], [("p1", "t1"), ("p2", "t2")])

    assert evaluate(state, full, now=5239.0, min_interval_s=240).fire is False
    assert evaluate(state, full, now=5240.0, min_interval_s=240).fire is True


def test_the_first_dream_of_the_day_has_no_floor():
    decision = evaluate(EMPTY, graph(["p1"], [("p1", "t1")]), now=1.0, min_interval_s=240)

    assert decision.fire is True


# -- collapsing -------------------------------------------------------------


def test_several_interviews_inside_the_floor_collapse_into_one_dream():
    """Spec §4.1: the dream is of the whole graph, not of one person, so there
    is nothing to queue."""
    state = TriggerState(frozenset({"p1"}), 5000.0)
    three_more = graph(
        ["p1", "p2", "p3", "p4"],
        [("p1", "t1"), ("p2", "t2"), ("p3", "t3"), ("p4", "t4")],
    )

    decision = evaluate(state, three_more, now=5300.0, min_interval_s=240)

    assert decision.fire is True
    assert decision.absorbed == frozenset({"p1", "p2", "p3", "p4"})


# -- silence ----------------------------------------------------------------


def test_silence_never_fires_a_dream():
    """Spec §4: nothing during silence. A dream appearing while nothing
    happened on the left exposes the station as a random generator."""
    state = TriggerState(frozenset({"p1", "p2"}), 5000.0)
    unchanged = graph(["p1", "p2"], [("p1", "t1"), ("p2", "t2")])

    for now in (5300.0, 9000.0, 50000.0):
        assert evaluate(state, unchanged, now=now, min_interval_s=240).fire is False


def test_an_empty_graph_never_fires():
    assert evaluate(EMPTY, graph([]), now=1.0, min_interval_s=240).fire is False


# -- hidden nodes -----------------------------------------------------------


def test_a_hidden_person_does_not_fire_a_dream():
    """The operator pulled them from the wall (T1§8); they must not drive the
    dream either, and §5.1 already excludes them from its material."""
    hidden = graph(["p1"], [("p1", "t1")], hidden_persons=["p1"])

    assert absorbed_persons(hidden) == set()
    assert evaluate(EMPTY, hidden, now=1.0, min_interval_s=240).fire is False


def test_hiding_and_unhiding_a_person_afterwards_never_fires_a_second_dream():
    """The seen set is monotone. Without that, hide-then-unhide reads as a new
    absorption and dreams twice on the same material."""
    state = TriggerState(frozenset({"p1"}), 5000.0)
    hidden = graph(["p1"], [("p1", "t1")], hidden_persons=["p1"])
    shown = graph(["p1"], [("p1", "t1")])

    assert evaluate(state, hidden, now=9000.0, min_interval_s=240).fire is False
    assert evaluate(state, shown, now=9000.0, min_interval_s=240).fire is False


# -- „Dream now" ------------------------------------------------------------


def test_force_ignores_the_floor():
    """Spec §7: needed the moment someone from the organiser stands in front of
    the screen and wants to see how it works."""
    state = TriggerState(frozenset({"p1"}), 5000.0)

    decision = evaluate(
        state, graph(["p1"], [("p1", "t1")]), now=5001.0, min_interval_s=240, force=True
    )

    assert decision.fire is True
    assert decision.reason == "forced"


def test_force_fires_even_in_total_silence():
    state = TriggerState(frozenset({"p1"}), 5000.0)

    decision = evaluate(
        state, graph(["p1"], [("p1", "t1")]), now=9000.0, min_interval_s=240, force=True
    )

    assert decision.fire is True
    assert decision.absorbed == frozenset({"p1"})


def test_force_on_an_empty_graph_still_fires():
    """A forced dream of an empty graph is a legitimate thing to ask for at
    9 a.m. — the cycle decides what to make of it, not the trigger."""
    assert evaluate(EMPTY, graph([]), now=1.0, min_interval_s=240, force=True).fire is True


# -- state transitions ------------------------------------------------------


def test_the_floor_stamp_is_adopted_separately_from_the_seen_set():
    """Spec §8: a failed dream must still move the floor (no retry storm) while
    leaving its material unconsumed (retry at the next trigger)."""
    state = TriggerState(frozenset(), None)
    decision = evaluate(state, graph(["p1"], [("p1", "t1")]), now=100.0, min_interval_s=240)

    after_failure = state.with_dream_started(decision.started_at)
    assert after_failure.seen_persons == frozenset()
    assert after_failure.last_started_at == 100.0

    after_success = after_failure.with_absorbed(decision.absorbed)
    assert after_success.seen_persons == frozenset({"p1"})
    assert after_success.last_started_at == 100.0


def test_a_failed_dream_retries_the_same_material_at_the_next_trigger():
    state = TriggerState(frozenset(), None)
    material = graph(["p1"], [("p1", "t1")])

    first = evaluate(state, material, now=100.0, min_interval_s=240)
    state = state.with_dream_started(first.started_at)  # failure: absorbed NOT adopted

    retry = evaluate(state, material, now=341.0, min_interval_s=240)

    assert retry.fire is True
    assert retry.absorbed == frozenset({"p1"})


def test_a_failed_dream_does_not_retry_before_the_floor():
    state = TriggerState(frozenset(), None).with_dream_started(100.0)

    assert evaluate(
        state, graph(["p1"], [("p1", "t1")]), now=101.0, min_interval_s=240
    ).fire is False


# -- restart ----------------------------------------------------------------


def dream(dream_id, at, persons, status="done", discarded=False) -> Dream:
    return Dream(
        id=dream_id,
        created_at=at,
        absorbed_persons=list(persons),
        status=status,
        discarded=discarded,
        sentence="x",
        image_path=f"{dream_id}.png",
    )


def test_a_restart_does_not_re_dream_everything_already_dreamt():
    state = resume_state([dream("d1", 100.0, ["p1"]), dream("d2", 400.0, ["p1", "p2"])])

    assert state.seen_persons == frozenset({"p1", "p2"})
    assert state.last_started_at == 400.0


def test_a_restart_keeps_the_floor_of_a_failed_dream():
    state = resume_state([dream("d1", 100.0, ["p1"]), dream("d2", 400.0, ["p2"], status="failed")])

    assert state.seen_persons == frozenset({"p1"})  # p2 was never condensed
    assert state.last_started_at == 400.0


def test_a_restart_counts_a_discarded_dream_as_dreamt():
    """Discard removes it from the SCREEN (spec §7). It was still dreamt, and
    re-dreaming the same material would just produce the same embarrassment."""
    state = resume_state([dream("d1", 100.0, ["p1"], discarded=True)])

    assert state.seen_persons == frozenset({"p1"})


def test_a_restart_on_an_empty_store_starts_from_nothing():
    assert resume_state([]) == TriggerState(frozenset(), None)


def test_a_restart_ignores_a_dream_left_running_by_the_crash():
    state = resume_state([dream("d1", 100.0, ["p1"], status="running")])

    assert state.seen_persons == frozenset()
    assert state.last_started_at == 100.0  # it did start, so the floor applies


# -- against the real thing -------------------------------------------------


def test_every_person_in_the_real_replay_graph_is_absorbed(real_graph):
    """Spec §11: contract against the real artefact, never a hand-written one.
    All 60 interviews in run 19c ran the full pipeline, so all 60 have edges."""
    assert len(absorbed_persons(real_graph)) == 60


def test_a_bare_person_appended_to_the_real_graph_is_not_absorbed(real_graph):
    """The §4.1 race on real data: exactly what Tool 1 publishes at the photo."""
    graph_with_photo = copy.deepcopy(real_graph)
    graph_with_photo["nodes"].append(
        {
            "id": "p61",
            "type": "person",
            "portrait": "/media/portraits/p61.jpg",
            "created_at": 1700020000.0,
            "hidden": False,
            "x": None,
            "y": None,
        }
    )

    assert "p61" not in absorbed_persons(graph_with_photo)

    state = TriggerState(frozenset(absorbed_persons(real_graph)), 1700019000.0)
    assert evaluate(
        state, graph_with_photo, now=1700020000.0, min_interval_s=240
    ).fire is False


def test_the_real_graph_fires_once_the_appended_person_has_an_edge(real_graph):
    graph_after_pipeline = copy.deepcopy(real_graph)
    graph_after_pipeline["nodes"].append(
        {
            "id": "p61",
            "type": "person",
            "portrait": None,
            "created_at": 1700020000.0,
            "hidden": False,
            "x": None,
            "y": None,
        }
    )
    graph_after_pipeline["edges"].append({"id": "e999", "source": "p61", "target": "t9"})

    state = TriggerState(frozenset(absorbed_persons(real_graph)), 1700019000.0)
    decision = evaluate(state, graph_after_pipeline, now=1700020000.0, min_interval_s=240)

    assert decision.fire is True
    assert "p61" in decision.absorbed
