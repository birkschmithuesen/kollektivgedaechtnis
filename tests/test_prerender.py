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


def test_the_series_renders_one_png_per_variant_at_1920x1080(tmp_path, seeded_db):
    out_dir = tmp_path / "prerender"

    paths = render_series(seeded_db, out_dir)

    assert [p.name for p in paths] == ["a.png", "b.png", "c.png", "d.png"]
    for path in paths:
        with Image.open(path) as img:
            assert img.size == (1920, 1080)


def test_the_variants_differ_from_each_other(tmp_path, seeded_db):
    out_dir = tmp_path / "prerender"

    paths = render_series(seeded_db, out_dir, themes=("a", "b"), include_testpattern=False)

    assert paths[0].read_bytes() != paths[1].read_bytes()
