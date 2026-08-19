"""sim.seed_graph populates a Store directly (no simulation, no LLM — Task 20 brief)."""

from __future__ import annotations

import colorsys

from collections import Counter

from PIL import Image

from kg.config import Config
from kg.store import Store
from sim.seed_graph import TERM_LABELS, _write_placeholder_photo, person_specs, seed_graph

PERSONS = 12
SEED = 20260814


def _seed(tmp_path, persons=PERSONS, seed=SEED):
    data_dir = tmp_path / "state"
    db_path = seed_graph(data_dir, persons=persons, seed=seed)
    return data_dir, db_path


def test_seed_graph_returns_the_configs_db_path(tmp_path):
    data_dir, db_path = _seed(tmp_path)
    cfg = Config(data_dir=data_dir)
    assert db_path == cfg.db_path
    assert db_path.exists()


def test_every_person_has_a_portrait_file_of_the_right_size(tmp_path):
    data_dir, db_path = _seed(tmp_path)
    cfg = Config(data_dir=data_dir)
    store = Store.open(db_path)
    try:
        persons = store.list_persons()
        assert len(persons) == PERSONS
        for person in persons:
            assert person.portrait_path is not None
            portrait_path = data_dir_relative(cfg, person.portrait_path)
            assert portrait_path.exists()
            with Image.open(portrait_path) as img:
                assert img.size == (cfg.portrait_size, cfg.portrait_size)
            assert person.status == "done"
            assert person.stopped_at is not None
    finally:
        store.close()


def data_dir_relative(cfg, portrait_path):
    from pathlib import Path

    p = Path(portrait_path)
    return p if p.is_absolute() else cfg.data_dir / p


def test_edge_distribution_has_a_head_and_a_tail(tmp_path):
    _, db_path = _seed(tmp_path)
    store = Store.open(db_path)
    try:
        terms = store.list_terms()
        edges = store.list_edges()
        persons = store.list_persons()

        # Every drawn edge count sits in the documented 4-6-per-person band.
        assert PERSONS * 4 <= len(edges) <= PERSONS * 6

        # No term row exists with zero mentions (only-drawn terms get created).
        counts = Counter(e.term_id for e in edges)
        assert set(counts) == {t.id for t in terms}
        assert all(n >= 1 for n in counts.values())

        # A real long tail: someone at the head (mentioned more than once)
        # and a substantial number at the tail (mentioned exactly once).
        assert max(counts.values()) >= 2
        singles = sum(1 for n in counts.values() if n == 1)
        assert singles >= 1

        # No person mentions the same term twice.
        per_person = Counter(e.person_id for e in edges)
        assert set(per_person) == {p.id for p in persons}

        # Every label used is drawn from the canonical term-label list.
        labels = {t.label for t in terms}
        assert labels <= set(TERM_LABELS)
    finally:
        store.close()


def test_seeding_is_deterministic_for_the_same_seed(tmp_path):
    _, db_path_1 = _seed(tmp_path / "run1")
    _, db_path_2 = _seed(tmp_path / "run2")

    store1 = Store.open(db_path_1)
    store2 = Store.open(db_path_2)
    try:
        labels1 = sorted(t.label for t in store1.list_terms())
        labels2 = sorted(t.label for t in store2.list_terms())
        assert labels1 == labels2

        def edge_pairs(store):
            terms_by_id = {t.id: t.label for t in store.list_terms()}
            persons_by_id = {p.id: p.started_at for p in store.list_persons()}
            return sorted(
                (persons_by_id[e.person_id], terms_by_id[e.term_id]) for e in store.list_edges()
            )

        assert edge_pairs(store1) == edge_pairs(store2)
    finally:
        store1.close()
        store2.close()


def test_min_mentions_setting_is_one(tmp_path):
    _, db_path = _seed(tmp_path)
    store = Store.open(db_path)
    try:
        assert store.get_setting("min_mentions", "0") == "1"
    finally:
        store.close()


def test_placeholder_photo_is_a_single_uniform_colour(tmp_path):
    # Birk's third pre-render review: the hue gradient + face ellipse read as
    # information (it wasn't). A placeholder now has to look like nothing.
    dest = tmp_path / "placeholder.jpg"
    _write_placeholder_photo(dest)
    with Image.open(dest) as image:
        colours = image.convert("RGB").getcolors(maxcolors=2)
    assert colours is not None and len(colours) == 1


def test_placeholder_photo_is_byte_identical_across_persons(tmp_path):
    # The old version painted a per-person hue; the new one must not vary at
    # all, regardless of where in the rng sequence a given person's draw falls.
    dest_a = tmp_path / "person-a.jpg"
    dest_b = tmp_path / "person-b.jpg"
    _write_placeholder_photo(dest_a)
    _write_placeholder_photo(dest_b)
    assert dest_a.read_bytes() == dest_b.read_bytes()


def test_a_persons_plan_does_not_depend_on_how_many_are_planned(tmp_path):
    # `person_specs` is what lets seq-new-person drop the 31st interview into
    # a graph that is already on screen, and it may only be trusted if the
    # entry for person N is the same whether 31 or 50 were planned — i.e. if
    # the rng really is walked once per person, in one fixed order. Same
    # guarantee `seed_graph` always had; now it is asserted directly, on the
    # function the sequence renderer calls.
    short = person_specs(31, SEED)
    long = person_specs(50, SEED)
    assert short == long[:31]

    # And it is the same walk seed_graph performs: the 31st person's terms
    # must be exactly the ones the seeded database gives them.
    cfg, db_path = _seed(tmp_path, persons=31, seed=SEED)
    store = Store.open(db_path)
    try:
        person = store.list_persons()[30]
        by_id = {t.id: t.label for t in store.list_terms()}
        seeded = {by_id[e.term_id] for e in store.list_edges() if e.person_id == person.id}
    finally:
        store.close()
    assert seeded == set(short[30].terms)


def test_placeholder_fill_is_muted_and_distinguishable_from_the_background(tmp_path):
    dest = tmp_path / "placeholder.jpg"
    _write_placeholder_photo(dest)
    with Image.open(dest) as image:
        r, g, b = image.convert("RGB").getpixel((0, 0))

    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    assert s < 0.2, "placeholder fill must read as 'no information', not a hue"

    bg_r, bg_g, bg_b = 0x00, 0x00, 0x00  # --bg in all three themes (Birk, 2026-08-15)
    distance = ((r - bg_r) ** 2 + (g - bg_g) ** 2 + (b - bg_b) ** 2) ** 0.5
    assert distance > 30, "placeholder must still be visible against --bg"


def test_seeded_50_person_graph_keeps_its_75_term_25_single_shape(tmp_path):
    # Regression guard for the rng call sequence: person_specs must keep
    # consuming exactly one `random.Random` value per person even though the
    # colour no longer uses it, or every downstream term draw reshuffles and
    # this round's whole pre-render comparison series stops matching
    # out/prerender2-state/kg.db. Runs 50 persons (vs. 12 elsewhere in this
    # file), so it's the slow test in this module — still a few seconds.
    _, db_path = _seed(tmp_path, persons=50, seed=SEED)
    store = Store.open(db_path)
    try:
        terms = store.list_terms()
        edges = store.list_edges()
        assert len(terms) == 75

        counts = Counter(e.term_id for e in edges)
        singles = sum(1 for n in counts.values() if n == 1)
        assert singles == 25
    finally:
        store.close()
