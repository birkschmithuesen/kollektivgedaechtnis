"""sim.prerender shoots the live renderer headless (Task 20 brief).

Adapted from the plan's Task 20 Step 1, but fed by sim.seed_graph through the
Store instead of fixture edges (Birk's 2026-08-14 decision: no simulation
dependency), and against small seeded dbs so the suite stays fast.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from PIL import Image

from sim.prerender import MIGRATION_FRACTIONS, WALL_MIGRATION_MS, render_series, seed_sizes

SEED = 20260814
# Small on purpose: this module checks the wiring of each series, not the
# density question. The numbers that decide the layout are measured against
# the real 50-person net in tests/test_projection.py and in the delivered
# out/prerender4 report.
SIZES = (3, 6)


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    return seed_sizes(tmp_path_factory.mktemp("prerender4-state"), SIZES, SEED)


def _placement_by_id(coverage):
    # coverage["placement"] is a list of [id, x, y] triples from MEASURE,
    # arriving from Playwright as JSON (lists, not tuples) — reshape once here
    # instead of repeating the conversion in every test.
    return {row[0]: (row[1], row[2]) for row in coverage["placement"]}


def _render(tmp_path, seeded, **kwargs):
    options = dict(
        include_fill_series=False,
        include_density_series=False,
        include_migration_series=False,
    )
    options.update(kwargs)
    return render_series(seeded, tmp_path / "prerender", **options)


def test_the_wall_and_the_report_agree_on_the_glide_length():
    # WALL_MIGRATION_MS only exists so the printed report can name the
    # default. The single source of truth is the front end, so pin them
    # together here rather than trusting a comment to stay true.
    source = (Path(__file__).resolve().parent.parent / "frontend/static/projection.js").read_text()
    declared = re.search(r"MIGRATION_DURATION_MS = (\d+)", source)
    assert declared and int(declared.group(1)) == WALL_MIGRATION_MS


def test_every_shot_is_a_1920x1080_png(tmp_path, seeded):
    shots = _render(
        tmp_path,
        seeded,
        include_fill_series=True,
        include_density_series=True,
        include_migration_series=True,
    )

    assert shots
    for shot in shots:
        with Image.open(shot.path) as img:
            assert img.size == (1920, 1080)


def test_the_fill_series_shoots_one_shot_per_size(tmp_path, seeded):
    shots = _render(tmp_path, seeded, include_fill_series=True)

    assert [s.path.name for s in shots] == [
        f"theme-b-fill-{size:02d}-persons-{s.coverage['term_nodes']}-terms.png"
        for size, s in zip(sorted(SIZES), shots)
    ]
    assert [s.coverage["person_nodes"] for s in shots] == list(sorted(SIZES))


def test_a_smaller_net_reaches_the_wall_larger(tmp_path, seeded):
    # Birk's fourth brief: "Two or three nodes -> everything large. A hundred
    # nodes -> everything small. Never a fixed scale." Nothing in the theme
    # differs between these shots — the viewport fit does all of it, because
    # type and node sizes are in model units.
    shots = _render(tmp_path, seeded, include_fill_series=True)

    small, large = shots[0].coverage, shots[-1].coverage
    assert small["label_px_on_wall"] > large["label_px_on_wall"]
    assert small["person_px_on_wall"] > large["person_px_on_wall"]
    # And both still fill the canvas, which is the other half of the claim.
    for coverage in (small, large):
        assert max(coverage["width_fraction_with_labels"], coverage["height_fraction_with_labels"]) > 0.85


def test_the_density_dial_shows_the_same_graph_at_three_thresholds(tmp_path, seeded):
    # The SAME graph at min_mentions 1/2/3, through the real display-filter
    # path (window.kgView.setMinMentions -> render() -> graph-model.js
    # visibleGraph), never a second renderer.
    shots = _render(tmp_path, seeded, include_density_series=True, min_mentions_values=(1, 2, 3))

    terms = [s.coverage["term_nodes"] for s in shots]
    edges = [s.coverage["edges"] for s in shots]
    persons = [s.coverage["person_nodes"] for s in shots]
    assert terms[0] > terms[1] >= terms[2]
    assert edges[0] > edges[1] >= edges[2]
    assert persons[0] == persons[1] == persons[2] == max(SIZES)


def test_raising_the_dial_re_lays_the_net_out_instead_of_leaving_holes(tmp_path, seeded):
    # The 2026-08-14 spec change, as a delivered measurement. Up to the third
    # round every dial step shared one placement and the picture shrank as
    # terms were hidden (93% -> 73% of the canvas width on the seeded
    # 50-person graph). Now each step migrates: the survivors must have MOVED,
    # and the canvas must still be full.
    shots = _render(tmp_path, seeded, include_density_series=True, min_mentions_values=(1, 3))

    loose, tight = (_placement_by_id(s.coverage) for s in shots)
    shared = set(loose) & set(tight)
    assert shared
    assert any(loose[node_id] != tight[node_id] for node_id in shared)
    assert shots[-1].coverage["width_fraction_with_labels"] > 0.8


def test_the_migration_series_is_a_numbered_sequence_through_one_glide(tmp_path, seeded):
    shots = _render(tmp_path, seeded, include_migration_series=True, migration_ms=4000)

    assert len(shots) == len(MIGRATION_FRACTIONS)
    names = [s.path.name for s in shots]
    for index, name in enumerate(names, start=1):
        assert f"-frame-{index}-of-{len(MIGRATION_FRACTIONS)}-" in name
    # The timestamps in the filenames are measured, not intended, so they are
    # what proves the frames really do span the animation rather than bunching
    # at one end of it.
    stamps = [float(re.search(r"-t([0-9.]+)s\.png$", name).group(1)) for name in names]
    assert stamps == sorted(stamps)
    assert stamps[0] < stamps[-1]
    # Only the closing frame is the settled picture, and only it is measured.
    assert not shots[0].coverage
    assert shots[-1].coverage["label_overlaps"] == {"labelPairs": 0, "labelsOnPersons": 0}


def test_the_frames_catch_the_net_in_mid_flight(tmp_path, seeded):
    # The claim the series exists to support: this is a glide, not a cut. Two
    # consecutive frames of a cut would be byte-identical (the old picture,
    # then the new one); frames of a glide are all different pictures.
    shots = _render(tmp_path, seeded, include_migration_series=True, migration_ms=4000)

    frames = [s.path.read_bytes() for s in shots]
    assert len(set(frames)) == len(frames)


def test_the_camera_views_frame_progressively_less_of_the_net(tmp_path, seeded):
    shots = _render(tmp_path, seeded, include_camera_views=True)

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


def test_two_cold_runs_produce_the_same_placement(tmp_path, seeded):
    # The brief's determinism requirement. fcose runs with randomize:false, so
    # the layout is a pure function of the starting state — and the starting
    # state is a pure function of the seed, because render_series serves a
    # throwaway COPY of each seeded db rather than the db itself. Two runs
    # that disagreed would mean one of those two claims is false, and the
    # whole comparison series would stop being a comparison.
    first = _render(tmp_path / "a", seeded, include_fill_series=True, include_density_series=True)
    second = _render(tmp_path / "b", seeded, include_fill_series=True, include_density_series=True)

    assert [s.coverage["placement"] for s in first] == [s.coverage["placement"] for s in second]


def test_the_theme_variants_differ_from_each_other(tmp_path, seeded):
    shots = _render(tmp_path, seeded, themes=("a", "c"))

    assert shots[0].path.read_bytes() != shots[1].path.read_bytes()
