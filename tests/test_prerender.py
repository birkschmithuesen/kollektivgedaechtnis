"""sim.prerender shoots the live renderer headless (Task 20 brief).

Adapted from the plan's Task 20 Step 1, but fed by sim.seed_graph through the
Store instead of fixture edges (Birk's 2026-08-14 decision: no simulation
dependency), and against a small seeded db so the test stays fast.
"""

from __future__ import annotations

import pytest
from PIL import Image

from sim.prerender import render_series
from sim.seed_graph import seed_graph

PERSONS = 6
SEED = 20260814


@pytest.fixture(scope="module")
def seeded_db(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("prerender-state")
    return seed_graph(data_dir, persons=PERSONS, seed=SEED)


def _placement_by_id(coverage):
    # coverage["placement"] is a list of [id, x, y] triples from MEASURE,
    # arriving from Playwright as JSON (lists, not tuples) — reshape once here
    # instead of repeating the conversion in every test.
    return {row[0]: (row[1], row[2]) for row in coverage["placement"]}


def test_the_series_renders_one_png_per_variant_at_1920x1080(tmp_path, seeded_db):
    out_dir = tmp_path / "prerender"

    shots = render_series(seeded_db, out_dir)

    # Third iteration's default: the density dial's four shots on theme B
    # (Birk's settled choice) and nothing else. No separate theme-B shot —
    # min_mentions=1 hides nothing, so that IS the full-graph theme-B
    # picture; a/c, the camera series and the test pattern are all opt-in
    # this round (see CLI flags).
    names = [s.path.name for s in shots]
    assert names[0].startswith("theme-b-min-mentions-1-all-") and names[0].endswith("-terms.png")
    assert names[1].startswith("theme-b-min-mentions-2-") and names[1].endswith("-terms.png")
    assert names[2].startswith("theme-b-min-mentions-3-") and names[2].endswith("-terms.png")
    assert names[3] == "theme-b-min-mentions-1-labels-BEFORE-declutter.png"
    assert len(names) == 4
    for shot in shots:
        with Image.open(shot.path) as img:
            assert img.size == (1920, 1080)


def test_the_variants_differ_from_each_other(tmp_path, seeded_db):
    out_dir = tmp_path / "prerender"

    shots = render_series(
        seeded_db,
        out_dir,
        themes=("a", "b"),
        include_testpattern=False,
        include_camera_views=False,
        include_density_series=False,
    )

    assert shots[0].path.read_bytes() != shots[1].path.read_bytes()


def test_every_graph_variant_shares_one_placement(tmp_path, seeded_db):
    # The variants differ in type size. If each got its own layout, the bigger
    # type would spread the net out and the camera's fit would zoom back out
    # by the same factor — the labels would reach the wall at the same size
    # and the series would compare nothing.
    shots = render_series(
        seeded_db,
        tmp_path / "prerender",
        themes=("a", "b", "c"),
        include_testpattern=False,
        include_camera_views=False,
        include_density_series=False,
    )

    placements = {tuple(tuple(row) for row in shot.coverage["placement"]) for shot in shots}
    assert len(placements) == 1


def test_the_placement_fills_the_16_9_canvas(tmp_path, seeded_db):
    # The measurement Birk asked for: before the layout was framed to the
    # canvas, the node cloud covered 30% of the width (2026-08-14 baseline).
    shots = render_series(
        seeded_db,
        tmp_path / "prerender",
        themes=("a",),
        include_testpattern=False,
        include_camera_views=False,
        include_density_series=False,
    )

    assert shots[0].coverage["width_fraction_with_labels"] > 0.8


def test_the_camera_views_frame_progressively_less_of_the_net(tmp_path, seeded_db):
    shots = render_series(
        seeded_db,
        tmp_path / "prerender",
        themes=(),
        include_testpattern=False,
        include_camera_views=True,
        include_density_series=False,
    )

    assert [s.path.name for s in shots] == [
        "camera-1-fit-all-reference.png",
        "camera-2-zoom2x-half-the-net.png",
        "camera-3-cluster-closeup.png",
    ]
    zooms = [s.coverage["zoom"] for s in shots]
    assert zooms[0] < zooms[1] < zooms[2]
    # Fit-all is the only view that holds the whole net; both zoomed views
    # trade coverage for size. Which of the two holds more depends on how
    # dense the chosen cluster is, so only the fit-all baseline is ordered.
    in_frame = [s.coverage["nodes_in_frame"] for s in shots]
    assert in_frame[0] == 1.0
    assert in_frame[1] < 1.0 and in_frame[2] < 1.0


def test_the_density_dial_shows_the_same_graph_at_three_thresholds(tmp_path, seeded_db):
    # Item 3 of the third brief: the SAME graph at min_mentions 1/2/3,
    # through the real display-filter path (window.kgView.setMinMentions ->
    # render() -> graph-model.js visibleGraph), never a second renderer.
    shots = render_series(
        seeded_db,
        tmp_path / "prerender",
        themes=(),
        include_testpattern=False,
        include_camera_views=False,
        include_density_series=True,
        min_mentions_values=(1, 2, 3),
    )

    dial_shots = shots[:3]
    for shot in dial_shots:
        with Image.open(shot.path) as img:
            assert img.size == (1920, 1080)

    terms = [s.coverage["term_nodes"] for s in dial_shots]
    edges = [s.coverage["edges"] for s in dial_shots]
    persons = [s.coverage["person_nodes"] for s in dial_shots]
    assert terms[0] > terms[1] > terms[2]
    assert edges[0] > edges[1] > edges[2]
    assert persons[0] == persons[1] == persons[2] == PERSONS


def test_the_density_shots_share_one_placement(tmp_path, seeded_db):
    # Raising the dial only hides term nodes — it must never re-run the
    # layout. min_mentions=3 shows the fewest nodes, so its ids are a subset
    # of the other two; every id it has must sit at the identical position.
    shots = render_series(
        seeded_db,
        tmp_path / "prerender",
        themes=(),
        include_testpattern=False,
        include_camera_views=False,
        include_density_series=True,
        min_mentions_values=(1, 2, 3),
    )

    by_id = [_placement_by_id(s.coverage) for s in shots[:3]]
    shared_ids = set(by_id[2])
    assert shared_ids  # the graph must not be filtered down to nothing
    assert shared_ids <= set(by_id[0])
    assert shared_ids <= set(by_id[1])
    for node_id in shared_ids:
        assert by_id[0][node_id] == by_id[1][node_id] == by_id[2][node_id]


def test_the_declutter_off_shot_has_more_overlapping_pairs_than_the_declutter_on_shot(
    tmp_path, seeded_db
):
    # Birk has only seen the label-overlap count, never the picture: this
    # comparison shot proves the declutter pass does something, on the exact
    # graph the min_mentions=1 dial shot above it also shows.
    shots = render_series(
        seeded_db,
        tmp_path / "prerender",
        themes=(),
        include_testpattern=False,
        include_camera_views=False,
        include_density_series=True,
        min_mentions_values=(1,),
    )

    after_shot, before_shot = shots[0], shots[1]
    assert before_shot.path.name == "theme-b-min-mentions-1-labels-BEFORE-declutter.png"
    assert (
        before_shot.coverage["label_overlaps"]["labelPairs"]
        > after_shot.coverage["label_overlaps"]["labelPairs"]
    )
    # Same graph, same placement — the ids present are identical, and every
    # id's position matches, so the two shots really are the same picture.
    before_ids = _placement_by_id(before_shot.coverage)
    after_ids = _placement_by_id(after_shot.coverage)
    assert before_ids == after_ids
