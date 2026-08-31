import sqlite3
import threading

import pytest

from kg.store import Store


@pytest.fixture()
def store(tmp_path):
    s = Store.open(tmp_path / "kg.db")
    yield s
    s.close()


def test_ids_are_sequential_and_prefixed(store):
    a = store.create_person(started_at=100.0)
    b = store.create_person(started_at=200.0)
    assert (a.id, b.id) == ("p1", "p2")


def test_next_id_is_thread_safe_under_concurrent_creation(store):
    # kg.db.connect opens SQLite with check_same_thread=False so a single Store
    # (and its connection) can be shared across FastAPI's threadpool. Hammer
    # _next_id ("person" ids, as create_person does) from many threads at once:
    # if the upsert-then-read in _next_id were not atomic, two threads could
    # read the same counter value and mint the same id, which would then
    # collide against person's TEXT PRIMARY KEY.
    #
    # This calls _next_id directly rather than create_person: as of the
    # store-wide lock (task 12b), create_person's INSERT + commit *are*
    # covered too - the `@_locked` decorator serialises the whole method, not
    # just _next_id - and test_concurrent_pipeline_and_operator_writes_do_not_corrupt_state
    # below drives create_person concurrently to prove exactly that. This
    # test instead isolates the narrower race the finding originally
    # described: the upsert-then-read inside _next_id racing against itself
    # across threads and minting a duplicate id.
    # Small thread/iteration counts race too rarely to reliably catch a
    # regression (verified empirically: 8x25 and even 32x200 sometimes missed
    # the interleave in manual trials). 48x300 reproduced the duplicate-id
    # race on every trial observed (with the lock removed) while still
    # running in well under a second with the fix in place.
    thread_count = 48
    creations_per_thread = 300
    ids: list[str] = []
    ids_lock = threading.Lock()
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            for _ in range(creations_per_thread):
                new_id = store._next_id("person")
                with ids_lock:
                    ids.append(new_id)
        except BaseException as exc:  # noqa: BLE001 - surface any thread failure
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(ids) == thread_count * creations_per_thread
    assert len(set(ids)) == len(ids)


def test_concurrent_pipeline_and_operator_writes_do_not_corrupt_state(store):
    # Task 12b: kg/server.py's routes are plain sync `def`s, so FastAPI runs
    # them in its threadpool. An operator turning the mention dial
    # (set_setting), hiding a node (set_hidden) or dragging a node
    # (save_positions) can therefore run concurrently, on the same Store /
    # same shared connection, with the per-interview pipeline creating
    # persons, terms and edges. Each of those methods issues its own
    # execute()+commit() with no guard beyond `_next_id`'s own lock, so two
    # threads can interleave mid-transaction on Python sqlite3's implicit
    # BEGIN: both see "no transaction active" and both issue it, and the
    # second raises "cannot start a transaction within a transaction". Drive
    # that exact shape and check the resulting database state (no lost
    # writes, no duplicate ids), not merely that nothing raised.
    #
    # Reliability without the store-wide lock (measured against the
    # pre-12b Store, which only ever locked `_next_id`): failed on 15/15
    # manual trials. The exact exception varies run to run because several
    # distinct races are being hit at once (sqlite3.OperationalError:
    # "cannot start a transaction within a transaction" and "cannot commit -
    # no transaction is active", sqlite3.InterfaceError, even AttributeError
    # from a read observing a not-yet-committed row) - "cannot start a
    # transaction within a transaction" itself showed up in 5/15. With the
    # fix in place: 0 failures in 15 trials, each run finishing in a few
    # seconds.
    person_count = 200
    errors: list[BaseException] = []
    stop = threading.Event()

    def pipeline_worker() -> None:
        try:
            for i in range(person_count):
                person = store.create_person(started_at=float(i))
                term = store.get_or_create_term(f"term-{i}", created_at=float(i))
                store.add_edge(person.id, term.id, created_at=float(i))
        except BaseException as exc:  # noqa: BLE001 - surface any thread failure
            errors.append(exc)
        finally:
            stop.set()

    def operator_worker(tag: str) -> None:
        i = 0
        try:
            while not stop.is_set():
                store.set_setting("max_terms", str(i % 5 + 1))
                store.set_hidden("person:does-not-exist", i % 2 == 0)
                store.save_positions({f"pos-{tag}": (float(i), float(i))})
                i += 1
        except BaseException as exc:  # noqa: BLE001 - surface any thread failure
            errors.append(exc)

    threads = [
        threading.Thread(target=pipeline_worker),
        threading.Thread(target=operator_worker, args=("a",)),
        threading.Thread(target=operator_worker, args=("b",)),
    ]
    for t in threads:
        t.start()
    # A timeout, not a bare join(): the single most likely regression here is
    # reverting `threading.RLock()` back to `threading.Lock()` at
    # kg/store.py:62 (re-entrancy is the non-obvious half of the fix), and
    # that regression doesn't fail this test - it deadlocks it, in
    # create_person -> _next_id, forever. Bound the wait and assert the
    # thread actually finished, so that regression becomes a named failure
    # instead of a silent hang of the whole suite.
    for t in threads:
        t.join(timeout=60)
        assert not t.is_alive(), "thread did not finish within 60s - suspect a deadlock regression"

    assert not errors, errors
    persons = store.list_persons()
    assert len(persons) == person_count
    assert len(set(p.id for p in persons)) == person_count
    edges = store.list_edges()
    assert len(edges) == person_count
    assert len(set(e.id for e in edges)) == person_count
    assert len(store.list_terms()) == person_count

    # No lost writes on the operator side either: both operator threads'
    # position keys must be present, and the setting must hold one of the
    # values the operator threads actually wrote (never something else, and
    # never absent).
    positions = store.get_positions()
    assert "pos-a" in positions
    assert "pos-b" in positions
    assert store.get_setting("max_terms", "unset") in {"1", "2", "3", "4", "5"}


def test_person_lifecycle(store):
    person = store.create_person(started_at=100.0, photo_path="photos/a.jpg")
    assert person.status == "open"
    assert store.open_person().id == person.id

    store.close_person(person.id, stopped_at=160.0, reason="spoken")
    reloaded = store.get_person(person.id)
    assert reloaded.stopped_at == 160.0
    assert reloaded.stop_reason == "spoken"
    assert reloaded.status == "closed"
    assert store.open_person() is None

    store.set_person_transcript(person.id, "Guten Tag.")
    store.set_person_status(person.id, "done")
    assert store.get_person(person.id).transcript == "Guten Tag."
    assert store.get_person(person.id).status == "done"


def test_a_person_starts_without_a_name_and_can_be_given_one(store):
    """Der Name kommt aus dem Transkript, nicht aus der Aufnahme — zwischen
    `create_person` und dem Ende der Verdichtung ist er schlicht unbekannt."""
    person = store.create_person(started_at=100.0)
    assert person.name is None

    store.set_person_name(person.id, "Frau Kirchner")
    assert store.get_person(person.id).name == "Frau Kirchner"


def test_clearing_a_misheard_name_stores_null_not_an_empty_string(store):
    """Die Spracherkennung verhört Namen, also leert der Operator das Feld.

    Das Ergebnis muss derselbe Zustand sein wie bei einer Person, die sich nie
    vorgestellt hat — sonst gäbe es zwei Arten von „kein Name", und die
    Anzeige müsste beide kennen.
    """
    person = store.create_person(started_at=100.0)
    store.set_person_name(person.id, "Frau Kirchnau")

    store.set_person_name(person.id, "")
    assert store.get_person(person.id).name is None

    # Auch reine Leerzeichen sind kein Name: sie stünden sonst als leere Zeile
    # über dem Zitat auf der Wand.
    store.set_person_name(person.id, "Frau Kirchner")
    store.set_person_name(person.id, "   ")
    assert store.get_person(person.id).name is None


def test_terms_are_unique_by_label_and_aliases_resolve(store):
    t1 = store.get_or_create_term("Recycling-Beton", created_at=1.0)
    t2 = store.get_or_create_term("Recycling-Beton", created_at=2.0)
    assert t1.id == t2.id == "t1"

    store.add_alias(t1.id, "Beton aus Abbruch")
    assert store.find_term_by_alias("Beton aus Abbruch").id == t1.id
    assert store.find_term_by_alias("unbekannt") is None

    store.rename_term(t1.id, "Recyclingbeton")
    assert store.get_term(t1.id).label == "Recyclingbeton"
    # The old label survives as an alias so the decision is never re-derived.
    assert store.find_term_by_alias("Recycling-Beton").id == t1.id


def test_a_term_one_person_has_mentioned_can_still_be_renamed(store):
    # D5 leaves the early correction of an unlucky first name open: while a term
    # belongs to exactly one person, its label is not yet public property.
    term = store.get_or_create_term("Baustoff mit Geschichte", created_at=1.0)
    p1 = store.create_person(started_at=1.0)
    store.add_edge(p1.id, term.id, created_at=1.0)

    assert store.rename_term(term.id, "Beton aus Abbruchmaterial") is True
    assert store.get_term(term.id).label == "Beton aus Abbruchmaterial"
    assert store.find_term_by_alias("Baustoff mit Geschichte").id == term.id


def test_renaming_a_term_two_people_share_is_refused(store):
    # D5 (Birk, 2026-08-19), from the damage in run 19b: t25 had grown to four
    # people as a recycling node and a later merge renamed it to „Vorzeitiger
    # Gebäudeabriss" — nearly the opposite meaning, on the wall, and the label
    # is also the embedder's text for the node, so it stopped attracting the
    # concept it was built from. From the second distinct person on, the name
    # is public property: rename_term refuses, silently, and changes nothing.
    term = store.get_or_create_term("Baustoff mit Geschichte", created_at=1.0)
    p1 = store.create_person(started_at=1.0)
    p2 = store.create_person(started_at=2.0)
    store.add_edge(p1.id, term.id, created_at=1.0)
    store.add_edge(p2.id, term.id, created_at=2.0)

    assert store.rename_term(term.id, "Vorzeitiger Gebäudeabriss") is False
    assert store.get_term(term.id).label == "Baustoff mit Geschichte"
    # A refused rename writes nothing at all — no alias for the rejected name,
    # or the node would start answering to it in the next interview's lookup.
    assert store.find_term_by_alias("Vorzeitiger Gebäudeabriss") is None


def test_edges_are_idempotent_and_drive_mention_count(store):
    p1 = store.create_person(started_at=1.0)
    p2 = store.create_person(started_at=2.0)
    term = store.get_or_create_term("Modulares Bauen", created_at=1.0)

    store.add_edge(p1.id, term.id, created_at=3.0)
    store.add_edge(p1.id, term.id, created_at=4.0)  # same pair again
    assert len(store.list_edges()) == 1
    assert store.mention_count(term.id) == 1

    store.add_edge(p2.id, term.id, created_at=5.0)
    assert store.mention_count(term.id) == 2


def test_quotes_are_stored_even_though_the_wall_does_not_show_them(store):
    person = store.create_person(started_at=1.0)
    store.add_quote(person.id, "Wir bauen zu viel Neues.", created_at=2.0)
    quotes = store.list_quotes()
    assert [q.text for q in quotes] == ["Wir bauen zu viel Neues."]
    assert quotes[0].person_id == person.id


def test_hidden_flag_applies_to_persons_and_terms(store):
    person = store.create_person(started_at=1.0)
    term = store.get_or_create_term("Nachhaltigkeit", created_at=1.0)

    store.set_hidden(f"person:{person.id}", True)
    store.set_hidden(f"term:{term.id}", True)

    assert store.get_person(person.id).hidden is True
    assert store.get_term(term.id).hidden is True

    store.set_hidden(f"term:{term.id}", False)
    assert store.get_term(term.id).hidden is False

    with pytest.raises(ValueError):
        store.set_hidden("nonsense:1", True)


def test_positions_round_trip(store):
    store.save_positions({"p1": (10.5, -3.25), "t2": (0.0, 0.0)})
    store.save_positions({"p1": (11.0, -3.25)})  # update, not duplicate
    assert store.get_positions() == {"p1": (11.0, -3.25), "t2": (0.0, 0.0)}


def test_merge_decisions_are_persisted(store):
    person = store.create_person(started_at=1.0)
    store.record_merge_decision(person.id, {"groups": [{"canonical_label": "X"}]}, created_at=9.0)
    decisions = store.list_merge_decisions()
    assert decisions[0]["person_id"] == person.id
    assert decisions[0]["payload"]["groups"][0]["canonical_label"] == "X"


def test_settings_round_trip_with_default(store):
    assert store.get_setting("max_terms", "1") == "1"
    store.set_setting("max_terms", "2")
    assert store.get_setting("max_terms", "1") == "2"


def test_set_setting_default_seeds_once_and_never_clobbers(store):
    """Startup seeds the configured density; an operator's live change wins."""
    store.set_setting_default("max_terms", "3")
    assert store.get_setting("max_terms", "1") == "3"

    store.set_setting("max_terms", "1")  # operator turns the dial down
    store.set_setting_default("max_terms", "3")  # next restart
    assert store.get_setting("max_terms", "1") == "1"


def test_transaction_commits_all_writes_together_on_clean_exit(store):
    with store.transaction():
        store.create_person(started_at=1.0)
        store.create_person(started_at=2.0)
    assert len(store.list_persons()) == 2


def test_transaction_rolls_back_all_writes_on_exception(store):
    with pytest.raises(RuntimeError, match="boom"):
        with store.transaction():
            store.create_person(started_at=1.0)
            raise RuntimeError("boom")
    assert store.list_persons() == []


def test_nested_transaction_does_not_commit_until_the_outer_block_exits(tmp_path):
    # Finding 3 / task 12b: transaction() must be re-entrant so a helper method
    # that opens its own transaction() still works correctly when called from
    # inside a larger one — only the outermost block may commit. Observed from
    # a second, independent connection: uncommitted writes on the store's
    # connection are invisible there regardless of journal mode, so if the
    # inner block committed early, this would see 1 row instead of 0.
    path = tmp_path / "kg.db"
    store = Store.open(path)
    other_conn = sqlite3.connect(str(path))
    try:
        with store.transaction():
            store.create_person(started_at=1.0)
            with store.transaction():
                store.create_person(started_at=2.0)
            visible_mid_block = other_conn.execute("SELECT COUNT(*) FROM person").fetchone()[0]
            assert visible_mid_block == 0
        visible_after = other_conn.execute("SELECT COUNT(*) FROM person").fetchone()[0]
        assert visible_after == 2
    finally:
        other_conn.close()
        store.close()


def test_transaction_rolls_back_on_base_exception_not_just_exception(tmp_path):
    # Finding 5 / task 12b review: transaction() only caught `Exception`, so a
    # BaseException raised inside the block (KeyboardInterrupt when the
    # operator stops the station, a thread's SystemExit) skipped the
    # rollback while `finally` still dropped `_tx_depth` back to 0 and
    # released the lock, leaving `conn` sitting in an uncommitted implicit
    # transaction. That partial write is invisible from another connection
    # right after the exception (nothing has committed it yet either way),
    # but the *next* unrelated write's own `_commit()` then commits
    # everything still pending together, permanently persisting the partial
    # write alongside it. That is a half-applied `fold_term` (loser deleted,
    # its edges not yet moved) reaching disk permanently.
    path = tmp_path / "kg.db"
    store = Store.open(path)
    other_conn = sqlite3.connect(str(path))
    try:
        with pytest.raises(KeyboardInterrupt):
            with store.transaction():
                store.create_person(started_at=1.0)
                raise KeyboardInterrupt()

        # Not committed yet, so invisible even under the bug.
        assert other_conn.execute("SELECT COUNT(*) FROM person").fetchone()[0] == 0

        # The Store must still be usable, and this unrelated write must not
        # resurrect the partial write from the failed transaction.
        later = store.create_person(started_at=2.0)

        rows = other_conn.execute("SELECT id FROM person ORDER BY id").fetchall()
        assert [r[0] for r in rows] == [later.id]
    finally:
        other_conn.close()
        store.close()


def test_fold_term_moves_edges_aliases_and_deletes_the_loser(store):
    winner = store.get_or_create_term("Sonnenenergie am Haus", created_at=1.0)
    loser = store.get_or_create_term("Solarzellen aufs Dach", created_at=1.0)
    p1 = store.create_person(started_at=1.0)
    p2 = store.create_person(started_at=2.0)
    store.add_edge(p1.id, winner.id, created_at=1.0)
    store.add_edge(p2.id, loser.id, created_at=2.0)
    store.save_positions({f"term:{loser.id}": (1.0, 2.0)})

    store.fold_term(loser.id, winner.id)

    assert store.get_term(loser.id) is None
    assert [t.id for t in store.list_terms()] == [winner.id]
    assert store.find_term_by_alias("Solarzellen aufs Dach").id == winner.id
    assert store.mention_count(winner.id) == 2
    assert f"term:{loser.id}" not in store.get_positions()


def test_fold_term_does_not_duplicate_an_edge_shared_by_both_terms(store):
    # A person who already has an edge to the winner must not end up with two
    # edges after the fold (edge has UNIQUE(person_id, term_id)).
    winner = store.get_or_create_term("Sonnenenergie am Haus", created_at=1.0)
    loser = store.get_or_create_term("Solarzellen aufs Dach", created_at=1.0)
    same_person = store.create_person(started_at=1.0)
    store.add_edge(same_person.id, winner.id, created_at=1.0)
    store.add_edge(same_person.id, loser.id, created_at=2.0)

    store.fold_term(loser.id, winner.id)

    assert len(store.list_edges()) == 1
    assert store.mention_count(winner.id) == 1


def test_state_survives_reopening(tmp_path):
    path = tmp_path / "kg.db"
    s1 = Store.open(path)
    person = s1.create_person(started_at=1.0)
    term = s1.get_or_create_term("Ländlicher Leerstand", created_at=1.0)
    s1.add_edge(person.id, term.id, created_at=2.0)
    s1.save_positions({person.id: (5.0, 6.0)})
    s1.close()

    s2 = Store.open(path)
    assert [p.id for p in s2.list_persons()] == [person.id]
    assert [t.label for t in s2.list_terms()] == ["Ländlicher Leerstand"]
    assert len(s2.list_edges()) == 1
    assert s2.get_positions() == {person.id: (5.0, 6.0)}
    s2.close()
