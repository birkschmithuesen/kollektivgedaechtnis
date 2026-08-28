"""Spec §10 — the values are produced by the simulation, not guessed."""

from __future__ import annotations

from kg2.weighting import build_material
from sim.dream_calibrate import (
    SIZES,
    SYNTHETIC_CASES,
    TERMS_N,
    TERMS_X,
    _synthetic_graph,
    floor_table,
    prefix_graph,
)


def test_the_sizes_span_an_empty_morning_to_a_full_day():
    assert SIZES == (3, 10, 30, 60)


# -- prefix_graph -----------------------------------------------------------


def test_prefix_graph_keeps_the_first_n_persons(real_graph):
    small = prefix_graph(real_graph, 10)

    persons = [n for n in small["nodes"] if n["type"] == "person"]
    assert len(persons) == 10
    order = [n["id"] for n in sorted(persons, key=lambda n: (n["created_at"], n["id"]))]
    assert order[0] == "p1"


def test_prefix_graph_drops_edges_to_persons_who_are_not_there_yet(real_graph):
    small = prefix_graph(real_graph, 10)

    persons = {n["id"] for n in small["nodes"] if n["type"] == "person"}
    assert all(edge["source"] in persons for edge in small["edges"])


def test_prefix_graph_drops_terms_nobody_left_has_mentioned(real_graph):
    small = prefix_graph(real_graph, 5)

    mentioned = {edge["target"] for edge in small["edges"]}
    terms = {n["id"] for n in small["nodes"] if n["type"] == "term"}
    assert terms == mentioned


def test_prefix_graph_recomputes_mentions_for_the_smaller_graph(real_graph):
    """Carrying the 60-person counts into a 5-person graph would make the
    weighting describe a day that has not happened yet."""
    small = prefix_graph(real_graph, 5)

    counts = {}
    for edge in small["edges"]:
        counts[edge["target"]] = counts.get(edge["target"], 0) + 1
    for node in small["nodes"]:
        if node["type"] == "term":
            assert node["mentions"] == counts[node["id"]]
            assert node["mentions"] <= 5


def test_prefix_graph_keeps_only_the_quotes_of_the_people_present(real_graph):
    small = prefix_graph(real_graph, 5)

    persons = {n["id"] for n in small["nodes"] if n["type"] == "person"}
    assert all(quote["person_id"] in persons for quote in small["quotes"])
    assert small["quotes"]


def test_prefix_graph_grows_monotonically(real_graph):
    sizes = [prefix_graph(real_graph, n) for n in SIZES]

    counts = [len(g["edges"]) for g in sizes]
    assert counts == sorted(counts)
    assert all(counts[i] < counts[i + 1] for i in range(len(counts) - 1))


def test_the_full_prefix_is_the_whole_graph(real_graph):
    full = prefix_graph(real_graph, 60)

    assert len(full["edges"]) == len(real_graph["edges"])
    assert len(full["quotes"]) == len(real_graph["quotes"])


def test_prefix_graph_still_looks_like_a_graph_json(real_graph):
    """It goes straight into build_material, so it has to keep the contract."""
    small = prefix_graph(real_graph, 3)

    assert set(small) == set(real_graph)
    assert small["version"] == 1


# -- the `terms` calibration inputs -----------------------------------------


def test_terms_n_and_x_are_nonempty_candidate_sets():
    assert len(TERMS_N) >= 1
    assert len(TERMS_X) >= 1
    assert all(n > 0 for n in TERMS_N)
    assert all(x > 0 for x in TERMS_X)


# -- the `mood` calibration inputs -------------------------------------------


def test_there_are_four_synthetic_mood_cases():
    """Spec-decided (task brief, 2026-08-28): one clearly positive/unified,
    one clearly negative/conflicted, two in between."""
    assert len(SYNTHETIC_CASES) == 4


def test_the_synthetic_cases_are_not_a_recommendation():
    for label in SYNTHETIC_CASES:
        for forbidden in ("empfohlen", "recommended", "*", "(a)", "1."):
            assert forbidden not in label


def test_every_synthetic_case_produces_real_material():
    """Every synthetic term is said by every synthetic person, so
    build_material must see it as shared, real material — not something the
    gliding single-mention formula (kg2.weighting) could trim away."""
    for terms in SYNTHETIC_CASES.values():
        material = build_material(_synthetic_graph(terms))
        assert material.term_count == len(terms)
        assert material.marginal == []
        assert len(material.shared) == len(terms)


def test_synthetic_graphs_carry_distinct_content_per_case():
    """The four cases must not accidentally collapse to the same material —
    that would make the whole calibration prove nothing."""
    all_terms = [tuple(sorted(terms)) for terms in SYNTHETIC_CASES.values()]
    assert len(set(all_terms)) == len(all_terms)


# -- the floor --------------------------------------------------------------


def test_the_floor_table_reports_dreams_per_day_for_each_candidate():
    rows = floor_table(interview_count=60, day_seconds=8 * 3600, floors=(120, 240, 480))

    assert [row["min_interval_s"] for row in rows] == [120, 240, 480]
    assert all(row["dreams"] <= 60 for row in rows)


def test_a_floor_below_the_cadence_never_binds():
    """60 interviews over 8 h is one every 480 s. A 120 s floor cannot collapse
    anything, so every interview gets its own dream."""
    rows = floor_table(interview_count=60, day_seconds=8 * 3600, floors=(120,))

    assert rows[0]["dreams"] == 60
    assert rows[0]["collapsed"] == 0


def test_a_floor_above_the_cadence_collapses_interviews():
    rows = floor_table(interview_count=60, day_seconds=8 * 3600, floors=(1200,))

    assert rows[0]["dreams"] < 60
    assert rows[0]["collapsed"] > 0
    assert rows[0]["dreams"] + rows[0]["collapsed"] == 60


def test_the_floor_table_reports_the_cadence_it_assumed():
    """The number that actually decides the answer must be visible, or the
    table reads as a fact about the floor when it is a fact about the day."""
    rows = floor_table(interview_count=60, day_seconds=8 * 3600, floors=(240,))

    assert rows[0]["cadence_s"] == 480.0


def test_a_day_with_no_interviews_produces_no_dreams():
    rows = floor_table(interview_count=0, day_seconds=8 * 3600, floors=(240,))

    assert rows[0]["dreams"] == 0
