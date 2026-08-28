"""Spec §10 — the values are produced by the simulation, not guessed."""

from __future__ import annotations

from kg2.weighting import build_material
from sim.dream_calibrate import (
    SIZES,
    SYNTHETIC_CASES,
    TENSION_CASES,
    TERMS_N,
    TERMS_X,
    TensionRun,
    _synthetic_graph,
    floor_table,
    prefix_graph,
    tension_axis_summary,
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


# -- the `tension` calibration inputs ----------------------------------------


def test_there_are_four_tension_cases():
    """The 2x2 grid: mood and tension axis, each positiv/negativ x
    einig/zerstritten, task brief 2026-08-28."""
    assert len(TENSION_CASES) == 4


def test_the_tension_cases_cover_the_2x2_grid_exactly_once():
    """The whole point of this test material is that the two axes vary
    independently — each of the four combinations must appear exactly once,
    or the grid does not actually decouple mood from tension."""
    axes = [(case.mood_axis, case.tension_axis) for case in TENSION_CASES]
    assert set(axes) == {
        ("positiv", "einig"),
        ("positiv", "zerstritten"),
        ("negativ", "einig"),
        ("negativ", "zerstritten"),
    }
    assert len(set(axes)) == len(axes)


def test_the_tension_cases_are_not_a_recommendation():
    for case in TENSION_CASES:
        for forbidden in ("empfohlen", "recommended", "*", "(a)", "1."):
            assert forbidden not in case.label


def test_every_tension_case_produces_real_material():
    """Same discipline as the mood cases: every term said by every synthetic
    person, so nothing is trimmed by the gliding single-mention formula and
    both sides of a contradiction carry equal weight."""
    for case in TENSION_CASES:
        material = build_material(_synthetic_graph(case.terms))
        assert material.term_count == len(case.terms)
        assert material.marginal == []
        assert len(material.shared) == len(case.terms)


def test_tension_graphs_carry_distinct_content_per_case():
    all_terms = [tuple(sorted(case.terms)) for case in TENSION_CASES]
    assert len(set(all_terms)) == len(all_terms)


def test_the_zerstritten_cases_have_an_even_number_of_terms():
    """Built as contradiction PAIRS (task brief: "zwei Begriffe, die nicht
    gleichzeitig wahr sein können") — an odd term out would not be a pair."""
    for case in TENSION_CASES:
        if case.tension_axis == "zerstritten":
            assert len(case.terms) % 2 == 0


def test_tension_axis_summary_separates_contradiction_from_mood():
    """Hand-built runs where tension tracks disagreement, not sentiment —
    the summary's gaps must reflect that, not require an LLM call."""
    runs = [
        TensionRun("A", "positiv", "einig", mood=5, tension=1),
        TensionRun("B", "positiv", "zerstritten", mood=4, tension=5),
        TensionRun("C", "negativ", "einig", mood=1, tension=1),
        TensionRun("D", "negativ", "zerstritten", mood=2, tension=5),
    ]

    summary = tension_axis_summary(runs)

    assert summary["einig_avg"] == 1.0
    assert summary["zerstritten_avg"] == 5.0
    assert summary["tension_axis_gap"] == 4.0
    assert summary["positiv_avg"] == summary["negativ_avg"] == 3.0
    assert summary["mood_axis_gap"] == 0.0


def test_tension_axis_summary_reports_spread_per_case():
    runs = [
        TensionRun("A", "positiv", "einig", mood=5, tension=1),
        TensionRun("A", "positiv", "einig", mood=5, tension=2),
        TensionRun("A", "positiv", "einig", mood=5, tension=1),
    ]

    summary = tension_axis_summary(runs)

    assert summary["spread_per_case"]["A"] == (1, 2)


def test_tension_axis_summary_handles_no_runs():
    summary = tension_axis_summary([])

    assert summary["einig_avg"] == 0.0
    assert summary["spread_per_case"] == {}


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
