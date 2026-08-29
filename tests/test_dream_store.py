"""Everything screen B shows survives a restart, because none of it is in RAM."""

from __future__ import annotations

import threading

from kg2.models import Dream
from kg2.store import DreamStore


def open_store(tmp_path) -> DreamStore:
    return DreamStore.open(tmp_path / "dreams.sqlite3")


def make_dream(
    store, *, at: float, persons=("p1",), sentence="Ein Satz.", image="a.png",
    sentence_en="A sentence.", image_description="A long description.",
    tension_source="a while b", mood=3, tension=3,
):
    dream = store.create_dream(
        created_at=at,
        graph_generated_at=at - 1.0,
        person_count=len(persons),
        term_count=3,
        edge_count=4,
        guiding_question="Wie leben und bauen wir in zehn Jahren?",
        absorbed_persons=list(persons),
    )
    store.set_stage1(
        dream.id, prompt="S1", sentence=sentence, sentence_en=sentence_en,
        image_description=image_description, tension_source=tension_source,
        mood=mood, tension=tension, model="claude-opus-5",
    )
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
    assert dream.sentence_en == "A sentence."
    assert dream.image_description == "A long description."
    assert dream.tension_source == "a while b"
    assert dream.mood == 3
    assert dream.tension == 3
    assert dream.stage2_prompt == "S2"
    assert dream.condense_model == "claude-opus-5"
    assert dream.image_model == "google/gemini-3-pro-image"
    assert dream.image_path == "a.png"
    assert dream.status == "done"
    assert dream.discarded is False
    store.close()


def test_a_row_with_no_english_sentence_or_mood_or_tension_stays_readable(tmp_path):
    """A row from before 2026-08-28 (or a dream that failed before stage 1
    finished) has no value in these columns. `get_dream` must not choke on
    the NULLs — `set_stage1` is never even called for a row this shape."""
    store = open_store(tmp_path)

    dream = store.create_dream(
        created_at=1.0, graph_generated_at=0.0, person_count=1, term_count=1,
        edge_count=1, guiding_question="Q", absorbed_persons=["p1"],
    )

    assert dream.sentence_en is None
    assert dream.mood is None
    assert dream.tension is None
    store.close()


def test_a_row_with_no_image_description_or_tension_source_stays_readable(tmp_path):
    """The 2026-08-29 columns are additive and NULL for every earlier row —
    the same treatment sentence_en/mood/tension got, and no migration
    (docs: „neue Spalten additiv, NULL für Altbestand"). A reader must treat
    NULL as „not available" and fall back, never as an error."""
    store = open_store(tmp_path)

    dream = store.create_dream(
        created_at=1.0, graph_generated_at=0.0, person_count=1, term_count=1,
        edge_count=1, guiding_question="Q", absorbed_persons=["p1"],
    )

    assert dream.image_description is None
    assert dream.tension_source is None
    store.close()


def test_a_stage1_call_that_omits_the_new_fields_still_writes_the_row(tmp_path):
    """A caller with nothing to put in the new columns (sim/seed_dreams.py, a
    test fake) must keep working unchanged — NULL is written, which is the
    same value an untouched old row carries, and the strip still renders."""
    store = open_store(tmp_path)
    dream = store.create_dream(
        created_at=1.0, graph_generated_at=0.0, person_count=1, term_count=1,
        edge_count=1, guiding_question="Q", absorbed_persons=["p1"],
    )

    store.set_stage1(dream.id, prompt="S1", sentence="Ein Satz.", model="claude-opus-5")

    stored = store.get_dream(dream.id)
    assert stored.sentence == "Ein Satz."
    assert stored.image_description is None
    assert stored.tension_source is None
    store.close()


def test_an_empty_tension_source_is_stored_as_empty_not_as_missing(tmp_path):
    """„No contradiction in the material" is a real answer stage 1 gives
    (kg2/condense.py), and it is recorded as such: an empty string, which the
    row tells apart from the NULL of a row whose column was never filled."""
    store = open_store(tmp_path)

    answered_none = make_dream(store, at=1.0, tension_source="")
    never_filled = store.create_dream(
        created_at=2.0, graph_generated_at=1.0, person_count=1, term_count=1,
        edge_count=1, guiding_question="Q", absorbed_persons=["p2"],
    )

    assert answered_none.tension_source == ""
    assert never_filled.tension_source is None
    store.close()


def test_a_dream_row_exists_before_the_first_cloud_call(tmp_path):
    """A crash between create and finish must leave an honest record, not a hole."""
    store = open_store(tmp_path)

    dream = store.create_dream(
        created_at=1.0, graph_generated_at=0.0, person_count=1, term_count=1,
        edge_count=1, guiding_question="Q", absorbed_persons=["p1"],
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
        edge_count=1, guiding_question="Q", absorbed_persons=["p9"],
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
        edge_count=12, guiding_question="Q", absorbed_persons=["p1"],
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
        edge_count=1, guiding_question="Q", absorbed_persons=["p2"],
    )
    store.fail_dream(failed.id, "timeout")

    assert store.last_started_at() == 200.0

    # And a discarded dream must count too — set_discarded must not remove it
    # from the floor's reference point either. Made the most recent row, so a
    # `WHERE discarded = 0` regression in last_started_at() would return
    # 200.0 (the failed dream) instead of 300.0 and this assertion would
    # catch it.
    discarded = store.create_dream(
        created_at=300.0, graph_generated_at=299.0, person_count=1, term_count=1,
        edge_count=1, guiding_question="Q", absorbed_persons=["p3"],
    )
    store.set_stage1(discarded.id, prompt="S1", sentence="s", model="claude-opus-5")
    store.set_stage2_prompt(discarded.id, prompt="S2", model="google/gemini-3-pro-image")
    store.finish_dream(discarded.id, image_path="d.png")
    store.set_discarded(discarded.id, True)

    assert store.last_started_at() == 300.0
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


def test_consume_flag_reads_and_clears_as_one_fused_operation(tmp_path):
    """The watcher's dream_requested flag used to be a get_setting + a
    set_setting: two individually-locked calls, but not fused into one. An
    operator press landing between them would be overwritten back to "0" and
    lost, with the operator's only feedback being that nothing happened.
    consume_flag closes that window by doing both under a single lock
    acquisition (see kg2/store.py's rationale)."""
    store = open_store(tmp_path)

    assert store.consume_flag("dream_requested") is False  # never set

    store.set_setting("dream_requested", "1")
    assert store.consume_flag("dream_requested") is True
    # The clear is part of the same operation: a second consume right after
    # must see it already gone, not still "1".
    assert store.consume_flag("dream_requested") is False
    assert store.get_setting("dream_requested", "0") == "0"
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


def test_a_created_at_tie_breaks_on_insertion_order_not_id_text(tmp_path):
    """id is TEXT ("d1".."d10", ...), so ordering by id on a created_at tie
    would sort lexicographically (d1, d10, d2, ...) instead of by insertion
    order. Ten dreams sharing one created_at reproduces it directly: the
    lexicographic-last id among d1..d10 is "d9", so a regression back to
    `ORDER BY created_at, id` would make current_dream() return "d9" instead
    of the genuinely newest, "d10"."""
    store = open_store(tmp_path)
    dreams = [make_dream(store, at=1.0, sentence=f"traum {i}") for i in range(10)]

    assert [d.id for d in dreams] == [f"d{i + 1}" for i in range(10)]
    assert store.current_dream().id == "d10"
    assert [d.id for d in store.visible_dreams()] == [f"d{i + 1}" for i in range(10)]
    store.close()


def test_create_dream_is_thread_safe_under_concurrent_creation(tmp_path):
    # kg2.db.connect opens SQLite with check_same_thread=False so a single
    # DreamStore (and its connection) can be shared across FastAPI's
    # threadpool, the watcher loop, and the dream cycle. Hammer create_dream
    # from many threads at once: if the upsert-then-read in _next_id, or the
    # INSERT+commit around it, were not properly serialised, two threads
    # could mint the same id and collide against dream's TEXT PRIMARY KEY, or
    # corrupt the connection's transaction state.
    #
    # Modelled on kg/store.py's
    # test_next_id_is_thread_safe_under_concurrent_creation, sized down: a
    # reviewer verified by probe that 20 threads x 200 calls reliably yields
    # 4000 unique ids with no collisions, but this suite must stay fast, so a
    # few hundred total calls is enough to catch a lock regression.
    store = open_store(tmp_path)
    thread_count = 10
    creations_per_thread = 30
    dreams: list[Dream] = []
    dreams_lock = threading.Lock()
    errors: list[BaseException] = []

    def worker(tag: int) -> None:
        try:
            for i in range(creations_per_thread):
                dream = store.create_dream(
                    created_at=float(tag * creations_per_thread + i),
                    graph_generated_at=None,
                    person_count=1,
                    term_count=1,
                    edge_count=1,
                    guiding_question="Q",
                    absorbed_persons=["p1"],
                )
                with dreams_lock:
                    dreams.append(dream)
        except BaseException as exc:  # noqa: BLE001 - surface any thread failure
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(tag,)) for tag in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
        assert not t.is_alive(), "thread did not finish within 60s - suspect a deadlock regression"

    assert not errors, errors
    assert len(dreams) == thread_count * creations_per_thread
    ids = [d.id for d in dreams]
    assert len(set(ids)) == len(ids)
    assert len(store.all_dreams()) == thread_count * creations_per_thread
    store.close()
