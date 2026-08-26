"""Spec §10 — the values are produced by the simulation, not guessed."""

from __future__ import annotations

from sim.dream_calibrate import QUESTIONS, SIZES, floor_table, prefix_graph


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


# -- the guiding-question candidates ---------------------------------------


def test_there_are_three_or_four_candidate_wordings():
    assert 3 <= len(QUESTIONS) <= 4


def test_every_candidate_is_a_german_question():
    for question in QUESTIONS:
        assert question.strip().endswith("?")
        assert len(question.split()) >= 4


def test_no_candidate_is_marked_as_recommended():
    """Standing rule: Birk reads them cold."""
    for question in QUESTIONS:
        for forbidden in ("empfohlen", "recommended", "*", "(a)", "1."):
            assert forbidden not in question


def test_no_candidate_narrows_to_a_single_theme():
    """Spec §10 / brainstorm §7: wide enough to carry the future of building,
    AI in building, AND new forms of living together. A question naming one
    material or one technology cannot carry the other two."""
    narrow = ("beton", "holz", "dämmung", "ziegel", "photovoltaik", "roboter", "drohne")
    for question in QUESTIONS:
        assert not any(word in question.lower() for word in narrow)


def test_the_candidates_are_distinct():
    assert len(set(QUESTIONS)) == len(QUESTIONS)


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
