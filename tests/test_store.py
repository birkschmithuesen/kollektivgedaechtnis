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
    assert store.get_setting("min_mentions", "1") == "1"
    store.set_setting("min_mentions", "2")
    assert store.get_setting("min_mentions", "1") == "2"


def test_set_setting_default_seeds_once_and_never_clobbers(store):
    """Startup seeds the configured density; an operator's live change wins."""
    store.set_setting_default("min_mentions", "3")
    assert store.get_setting("min_mentions", "1") == "3"

    store.set_setting("min_mentions", "1")  # operator turns the dial down
    store.set_setting_default("min_mentions", "3")  # next restart
    assert store.get_setting("min_mentions", "1") == "1"


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
