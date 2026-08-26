"""Everything screen B shows survives a restart, because none of it is in RAM."""

from __future__ import annotations

from kg2.models import Dream
from kg2.store import DreamStore


def open_store(tmp_path) -> DreamStore:
    return DreamStore.open(tmp_path / "dreams.sqlite3")


def make_dream(store, *, at: float, persons=("p1",), sentence="Ein Satz.", image="a.png"):
    dream = store.create_dream(
        created_at=at,
        graph_generated_at=at - 1.0,
        person_count=len(persons),
        term_count=3,
        edge_count=4,
        contradiction=False,
        guiding_question="Wie leben und bauen wir in zehn Jahren?",
        absorbed_persons=list(persons),
    )
    store.set_stage1(dream.id, prompt="S1", sentence=sentence, model="claude-opus-5")
    store.set_stage2_prompt(dream.id, prompt="S2", model="google/gemini-3-pro-image")
    store.finish_dream(dream.id, image_path=image)
    return store.get_dream(dream.id)


def test_a_finished_dream_carries_every_field_the_record_needs(tmp_path):
    """Spec §5.3 — file + parameters + machine-readable record."""
    store = open_store(tmp_path)

    dream = make_dream(store, at=1000.0, persons=("p1", "p2"))

    assert isinstance(dream, Dream)
    assert dream.id == "d1"
    assert dream.created_at == 1000.0
    assert dream.graph_generated_at == 999.0
    assert dream.person_count == 2
    assert dream.term_count == 3
    assert dream.edge_count == 4
    assert dream.contradiction is False
    assert dream.guiding_question == "Wie leben und bauen wir in zehn Jahren?"
    assert dream.absorbed_persons == ["p1", "p2"]
    assert dream.stage1_prompt == "S1"
    assert dream.sentence == "Ein Satz."
    assert dream.stage2_prompt == "S2"
    assert dream.condense_model == "claude-opus-5"
    assert dream.image_model == "google/gemini-3-pro-image"
    assert dream.image_path == "a.png"
    assert dream.status == "done"
    assert dream.discarded is False
    store.close()


def test_a_dream_row_exists_before_the_first_cloud_call(tmp_path):
    """A crash between create and finish must leave an honest record, not a hole."""
    store = open_store(tmp_path)

    dream = store.create_dream(
        created_at=1.0, graph_generated_at=0.0, person_count=1, term_count=1,
        edge_count=1, contradiction=False, guiding_question="Q", absorbed_persons=["p1"],
    )

    assert dream.status == "running"
    assert store.current_dream() is None  # a running dream is not on screen yet
    store.close()


def test_current_is_the_newest_visible_dream_and_history_is_the_rest(tmp_path):
    store = open_store(tmp_path)
    make_dream(store, at=1.0, sentence="erst")
    make_dream(store, at=2.0, sentence="dann")
    make_dream(store, at=3.0, sentence="jetzt")

    assert store.current_dream().sentence == "jetzt"
    # Oldest to newest (spec §6) — the strip is a time axis, not a stack.
    assert [d.sentence for d in store.history()] == ["erst", "dann"]
    store.close()


def test_discard_removes_the_dream_from_the_screen_and_from_the_strip(tmp_path):
    """Spec §7, Birk: one step, both places. An image pulled for embarrassment
    must not live on below."""
    store = open_store(tmp_path)
    make_dream(store, at=1.0, sentence="erst")
    bad = make_dream(store, at=2.0, sentence="peinlich")

    store.set_discarded(bad.id, True)

    assert store.current_dream().sentence == "erst"  # the previous one returns
    assert [d.sentence for d in store.history()] == []
    assert all(d.sentence != "peinlich" for d in store.visible_dreams())
    store.close()


def test_a_discarded_dream_from_the_middle_leaves_no_hole_in_the_strip(tmp_path):
    store = open_store(tmp_path)
    make_dream(store, at=1.0, sentence="a")
    middle = make_dream(store, at=2.0, sentence="b")
    make_dream(store, at=3.0, sentence="c")

    store.set_discarded(middle.id, True)

    assert store.current_dream().sentence == "c"
    assert [d.sentence for d in store.history()] == ["a"]
    store.close()


def test_a_discarded_dream_is_kept_never_deleted(tmp_path):
    """Spec §7: the row stays so the record stays honest; the display filters."""
    store = open_store(tmp_path)
    bad = make_dream(store, at=1.0, sentence="peinlich")

    store.set_discarded(bad.id, True)

    assert store.get_dream(bad.id).discarded is True
    assert store.get_dream(bad.id).sentence == "peinlich"
    assert len(store.all_dreams()) == 1
    store.close()


def test_discard_is_reversible(tmp_path):
    """Same logic as Tool 1's hide flag (T1§8, docs/operations.md: „Wieder
    einblenden ist derselbe Knopf"). An emergency exit that cannot be undone
    turns a misclick into a permanent loss."""
    store = open_store(tmp_path)
    dream = make_dream(store, at=1.0, sentence="doch nicht peinlich")

    store.set_discarded(dream.id, True)
    store.set_discarded(dream.id, False)

    assert store.current_dream().sentence == "doch nicht peinlich"
    store.close()


def test_a_failed_dream_never_reaches_the_screen(tmp_path):
    """Spec §8: „the current image stays up"."""
    store = open_store(tmp_path)
    make_dream(store, at=1.0, sentence="gut")
    broken = store.create_dream(
        created_at=2.0, graph_generated_at=1.5, person_count=1, term_count=1,
        edge_count=1, contradiction=False, guiding_question="Q", absorbed_persons=["p9"],
    )

    store.fail_dream(broken.id, "read timeout")

    assert store.current_dream().sentence == "gut"
    assert store.get_dream(broken.id).status == "failed"
    assert store.get_dream(broken.id).error == "read timeout"
    store.close()


def test_a_stage_2_failure_still_records_the_sentence(tmp_path):
    """Reproducibility (spec §5.3) does not depend on the run succeeding — the
    prompt that produced nothing is exactly the one worth being able to read."""
    store = open_store(tmp_path)
    dream = store.create_dream(
        created_at=1.0, graph_generated_at=0.0, person_count=6, term_count=9,
        edge_count=12, contradiction=True, guiding_question="Q", absorbed_persons=["p1"],
    )
    store.set_stage1(dream.id, prompt="S1", sentence="Der Satz kam durch.", model="claude-opus-5")
    store.set_stage2_prompt(dream.id, prompt="S2", model="google/gemini-3-pro-image")

    store.fail_dream(dream.id, "502 from the image model")

    stored = store.get_dream(dream.id)
    assert stored.sentence == "Der Satz kam durch."
    assert stored.stage1_prompt == "S1"
    assert stored.stage2_prompt == "S2"
    assert stored.status == "failed"
    store.close()


def test_last_started_at_counts_failed_and_discarded_dreams_too(tmp_path):
    """Spec §8: „Retry at the next trigger — never a retry storm." A failure
    that did not move the floor would retry on the very next poll."""
    store = open_store(tmp_path)
    make_dream(store, at=100.0)
    failed = store.create_dream(
        created_at=200.0, graph_generated_at=199.0, person_count=1, term_count=1,
        edge_count=1, contradiction=False, guiding_question="Q", absorbed_persons=["p2"],
    )
    store.fail_dream(failed.id, "timeout")

    assert store.last_started_at() == 200.0
    store.close()


def test_an_empty_store_has_no_last_start(tmp_path):
    store = open_store(tmp_path)

    assert store.last_started_at() is None
    assert store.current_dream() is None
    assert store.history() == []
    store.close()


def test_the_whole_strip_and_every_setting_survive_a_restart(tmp_path):
    """Spec §8 / T1§14 run 21: the screen comes back exactly as it stood."""
    store = open_store(tmp_path)
    for index in range(5):
        make_dream(store, at=float(index), sentence=f"traum {index}", image=f"d{index}.png")
    store.set_setting("fade_ms", "800")
    store.set_setting("typewriter", "1")
    store.set_setting("paused", "1")
    before = [d.id for d in store.visible_dreams()]
    store.close()  # the crash

    reopened = DreamStore.open(tmp_path / "dreams.sqlite3")

    assert [d.id for d in reopened.visible_dreams()] == before
    assert reopened.current_dream().sentence == "traum 4"
    assert len(reopened.history()) == 4
    assert reopened.get_setting("fade_ms", "1200") == "800"
    assert reopened.get_setting("typewriter", "0") == "1"
    assert reopened.get_setting("paused", "0") == "1"
    reopened.close()


def test_set_setting_default_never_overwrites_the_operator(tmp_path):
    """A restart must restore the operator's value, not config's start value —
    the same rule Tool 1 holds for min_mentions."""
    store = open_store(tmp_path)
    store.set_setting_default("fade_ms", "1200")
    store.set_setting("fade_ms", "400")

    store.set_setting_default("fade_ms", "1200")

    assert store.get_setting("fade_ms", "1200") == "400"
    store.close()


def test_ids_never_repeat_even_after_a_discard(tmp_path):
    """Image files are named after the dream id and are never overwritten
    (spec §5.2), so a reused id would be a silent overwrite."""
    store = open_store(tmp_path)
    first = make_dream(store, at=1.0)
    store.set_discarded(first.id, True)
    second = make_dream(store, at=2.0)

    assert first.id == "d1"
    assert second.id == "d2"
    store.close()
