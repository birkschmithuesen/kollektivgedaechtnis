"""sim.seed_graph populates a Store directly (no simulation, no LLM — Task 20 brief)."""

from __future__ import annotations

from collections import Counter

from PIL import Image

from kg.config import Config
from kg.store import Store
from sim.seed_graph import TERM_LABELS, seed_graph

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
