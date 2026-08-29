"""sim.prerender shoots the live renderer headless (Task 20 brief).

Adapted from the plan's Task 20 Step 1, but fed by sim.seed_graph through the
Store instead of fixture edges (Birk's 2026-08-14 decision: no simulation
dependency), and against small seeded dbs so the suite stays fast.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
from PIL import Image

from sim import prerender
from sim.prerender import (
    FPS,
    MIGRATION_FRACTIONS,
    WALL_MIGRATION_MS,
    _print_shot,
    find_ffmpeg,
    render_sequences,
    render_series,
    seed_sizes,
)

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
    # The portraits are the exception since 2026-08-29 and now hold ONE size
    # on the wall (Birk, live at the station: a single person's portrait filled
    # the screen). Asserted here too, so the fill series cannot quietly go back
    # to sizing faces by how many of them there are.
    assert small["person_px_on_wall"] == pytest.approx(large["person_px_on_wall"], rel=0.02)
    # And both still fill the canvas, which is the other half of the claim.
    for coverage in (small, large):
        assert max(coverage["width_fraction_with_labels"], coverage["height_fraction_with_labels"]) > 0.85


def test_the_density_dial_shows_the_same_graph_at_three_caps(tmp_path, seeded):
    # The SAME graph at three term caps, through the real display-filter path
    # (window.kgView.setMaxTerms -> render() -> graph-model.js visibleGraph),
    # never a second renderer. 23/3/1 are this seeded graph's own tier
    # boundaries (all terms, then only the 3 shared ones, then only the single
    # most-mentioned one) -- chosen so the caps reproduce exactly the term
    # sets the old min_mentions thresholds 1/2/3 used to.
    shots = _render(tmp_path, seeded, include_density_series=True, max_terms_values=(23, 3, 1))

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
    shots = _render(tmp_path, seeded, include_density_series=True, max_terms_values=(23, 1))

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
    assert shots[-1].coverage["label_overlaps"] == {
        "labelPairs": 0,
        "labelsOnPersons": 0,
        "personPairs": 0,
    }


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


def test_each_ladder_variant_is_laid_out_for_its_own_type_and_disc_size(tmp_path, seeded):
    # Birk's seventh brief, 2026-08-15. Up to the sixth round the ladder shared
    # ONE placement, so that "only type size would differ" — which cannot work:
    # 44px labels and 100-unit discs need more room than 22px labels and
    # 56-unit ones, and laid into a net computed for the small ones they
    # collide. Each variant now runs its own fcose + settlePlacement +
    # declutter with its own sizes as the collision extents, so the placements
    # must genuinely differ.
    shots = _render(tmp_path, seeded, themes=("a", "c"))

    small, large = (_placement_by_id(s.coverage) for s in shots)
    assert set(small) == set(large)
    assert any(small[node_id] != large[node_id] for node_id in small)


def test_a_ladder_shot_reports_its_model_sizes_and_all_three_overlap_counts(tmp_path, seeded, capsys):
    # What Birk's seventh brief asks to be reported per variant. The model
    # sizes have to come from the rendered theme, not from a table in this
    # file, or the report could disagree with the picture it describes.
    (shot,) = _render(tmp_path, seeded, themes=("a",))

    assert shot.coverage["label_size_model"] == 22  # theme-a's --label-size
    # theme-a's --person-size. Since 2026-08-29 this is the size the PLACEMENT
    # reasons in, not what the disc is drawn at — the drawn size is
    # person_px_on_wall and is the operator's setting.
    assert shot.coverage["person_size_model"] == 56
    stats = shot.coverage["label_overlap_stats"]
    for side in ("before", "after"):
        assert set(stats[side]) == {"labelPairs", "labelsOnPersons", "personPairs"}

    _print_shot(shot)

    printed = capsys.readouterr().out
    assert "22px model type" in printed
    assert "discs on discs" in printed


def test_the_cli_can_shoot_the_ladder_on_its_own(tmp_path, monkeypatch):
    # The seventh round delivers three PNGs and nothing else, so the ladder has
    # to be requestable without the fill and density series it has always been
    # bundled with. Renders nothing: what is under test is the wiring from the
    # flags to render_series' own, separately tested, parameters.
    seen = {}

    def fake_render_series(dbs, out_dir, **kwargs):
        seen.update(kwargs, out_dir=out_dir, dbs=dbs)
        return []

    monkeypatch.setattr(prerender, "seed_sizes", lambda *a, **k: {50: tmp_path / "seed.sqlite3"})
    monkeypatch.setattr(prerender, "render_series", fake_render_series)
    monkeypatch.setattr(
        sys,
        "argv",
        ["sim.prerender", "--stills", "--themes", "a", "b", "c", "--sizes", "50",
         "--no-fill-stills", "--no-density-stills", "--no-migration-stills", "--no-sequences"],
    )

    prerender.main()

    assert seen["themes"] == ("a", "b", "c")
    assert seen["include_fill_series"] is False
    assert seen["include_density_series"] is False
    assert seen["include_migration_series"] is False
    # And the round's own directory is the default, so the delivered command
    # line is the short one.
    assert Path(seen["out_dir"]).name == "prerender7"


# --- Frame sequences (Birk's fifth brief, 2026-08-15) ----------------------
#
# Short glides on a tiny net, because these check the CAPTURE — the frame
# grid, the determinism, the two triggers — not the layout. The delivered
# sequences run the wall's own 2500ms over the 50-person graph.
SEQUENCE_GLIDE_MS = 400
SEQUENCE_TAIL_MS = 200
SEQUENCE_FRAMES = int(round((SEQUENCE_GLIDE_MS + SEQUENCE_TAIL_MS) / (1000 / FPS))) + 1


def _sequences(tmp_path, seeded, names, **kwargs):
    options = dict(
        names=names,
        glide_ms=SEQUENCE_GLIDE_MS,
        tail_ms=SEQUENCE_TAIL_MS,
        new_person_base=min(SIZES),
        encode=False,
    )
    options.update(kwargs)
    return render_sequences(seeded, tmp_path / "sequences", **options)


def test_a_sequence_is_a_sortable_directory_of_1920x1080_frames(tmp_path, seeded):
    # Birk's brief: dense enough to become video, zero-padded, sortable, one
    # directory per sequence so it can be globbed cleanly.
    (sequence,) = _sequences(tmp_path, seeded, ("dial-999-to-20",))

    frames = sorted(sequence.directory.glob("*.png"))
    assert sequence.directory.name == "seq-dial-999-to-20"
    assert [f.name for f in frames] == [f"frame-{i:04d}.png" for i in range(1, SEQUENCE_FRAMES + 1)]
    assert sequence.frames == SEQUENCE_FRAMES
    for frame in frames:
        with Image.open(frame) as img:
            assert img.size == (1920, 1080)


def test_a_sequence_covers_the_whole_glide_and_settles(tmp_path, seeded):
    # The two halves of "the whole transition plus a settled tail": every
    # frame of the glide is a different picture (a cut would repeat the old
    # one and then the new one), and the tail does not move at all.
    (sequence,) = _sequences(tmp_path, seeded, ("dial-999-to-20",))

    frames = [f.read_bytes() for f in sorted(sequence.directory.glob("*.png"))]
    glide = int(SEQUENCE_GLIDE_MS / (1000 / FPS)) + 1
    assert len(set(frames[:glide])) == glide
    assert len(set(frames[glide:])) == 1
    # And what plays back is the wall's own speed, not a slowed rehearsal.
    assert sequence.duration_s == pytest.approx(SEQUENCE_FRAMES / FPS)


def test_two_cold_runs_produce_the_same_motion(tmp_path, seeded):
    # The brief's determinism requirement, extended from placement to motion.
    # It holds because the frames are taken on a clock the driver owns:
    # sampling a freely running animation would land them wherever the
    # screenshot round trips allowed, differently on every run and machine.
    #
    # The comparison is over `motion.json` — the elapsed time, zoom, pan and
    # every node position of each frame — and NOT over the PNG bytes, which
    # are not byte-reproducible: Cytoscape rasterises a label into its texture
    # cache at a sub-pixel phase that depends on how the cache was packed.
    # Measured 2026-08-15 on the 50-person graph, two cold runs: identical
    # node positions, identical label offsets, identical measured label boxes
    # and identical zoom, but ~0.5% of pixels differing in a handful of
    # captions, each within 0.2px of the other's ink centroid.
    first = _sequences(tmp_path / "a", seeded, ("dial-999-to-20",))
    second = _sequences(tmp_path / "b", seeded, ("dial-999-to-20",))

    for one, two in zip(first, second):
        assert json.loads((one.directory / "motion.json").read_text()) == json.loads(
            (two.directory / "motion.json").read_text()
        )


def test_raising_the_dial_brings_the_hidden_terms_back(tmp_path, seeded):
    # The harder direction, and the one that used to re-shuffle: the sequence
    # has to START at the tighter setting and END with more terms on the wall.
    #
    # Named for RAISING the dial since 2026-08-29: the dial is now `max_terms`
    # (how many labels fit on the wall), so more terms means a HIGHER number.
    # Under the old `min_mentions` dial — a threshold on mention count — the
    # same direction meant lowering it, hence the previous name.
    (sequence,) = _sequences(tmp_path, seeded, ("dial-20-to-999",))

    before, after = (
        int(n) for n in re.search(r"(\d+) term nodes before, (\d+) after", sequence.description).groups()
    )
    assert after > before
    assert after == sequence.coverage["term_nodes"]


def test_a_new_person_arrives_over_sse_and_is_filmed(tmp_path, seeded):
    # The transition the audience sees most often. The person is written
    # through the Store and pushed as a complete graph event, exactly as the
    # Core does after every change (spec 11) — not injected into the renderer.
    (sequence,) = _sequences(tmp_path, seeded, ("new-person",))

    assert sequence.coverage["person_nodes"] == min(SIZES) + 1
    frames = [f.read_bytes() for f in sorted(sequence.directory.glob("*.png"))]
    assert len(set(frames)) > 1


def test_the_sequences_run_the_walls_own_glide_by_default(tmp_path, seeded):
    # Birk's brief is explicit: the real 2.5s, not the 8s the still series
    # slowed it to, because the speed is what he is judging.
    sequences = _sequences(tmp_path, seeded, ("dial-999-to-20",), glide_ms=WALL_MIGRATION_MS)

    assert sequences[0].glide_ms == WALL_MIGRATION_MS
    assert sequences[0].frames == int(round((WALL_MIGRATION_MS + SEQUENCE_TAIL_MS) / (1000 / FPS))) + 1


@pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg on this host")
def test_a_sequence_encodes_to_a_playable_mp4(tmp_path, seeded):
    (sequence,) = _sequences(tmp_path, seeded, ("dial-999-to-20",), encode=True)

    assert sequence.mp4 is not None and sequence.mp4.exists()
    assert sequence.mp4.name == "seq-dial-999-to-20.mp4"
    assert sequence.mp4.stat().st_size > 0
