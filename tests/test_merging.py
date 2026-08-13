import pytest

from kg.embeddings import HashEmbedder
from kg.merging import (
    MERGE_SYSTEM,
    MergeGroup,
    MergeResult,
    apply_merges,
    build_candidates,
    build_merge_prompt,
    decide_merges,
    split_known,
)
from kg.store import Store


@pytest.fixture()
def store(tmp_path):
    s = Store.open(tmp_path / "kg.db")
    yield s
    s.close()


class FakeLLM:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def parse(self, system, user, output_model):
        self.calls.append((system, user))
        return self.result


def test_split_known_resolves_persisted_decisions_without_an_llm(store):
    term = store.get_or_create_term("Recycling-Beton", created_at=1.0)
    store.add_alias(term.id, "Beton aus Abbruch")

    known, unknown = split_known(store, ["Beton aus Abbruch", "Holzbau"])

    assert known == {"Beton aus Abbruch": term.id}
    assert unknown == ["Holzbau"]


def test_build_candidates_offers_the_nearest_existing_labels():
    embedder = HashEmbedder(dim=64)
    existing = ["modulares Bauen im Bestand", "Bodenversiegelung", "Genossenschaft"]

    candidates = build_candidates(["modulares Bauen"], existing, embedder, k=2)

    assert candidates["modulares Bauen"][0] == "modulares Bauen im Bestand"
    assert len(candidates["modulares Bauen"]) == 2


def test_merge_prompt_carries_the_style_dial_and_both_sides():
    prompt = build_merge_prompt(
        ["Drohnenbeton"], {"Drohnenbeton": ["Betonspritzen mit Drohnen"]}, "STYLE-DIAL"
    )
    assert "STYLE-DIAL" in prompt
    assert "Drohnenbeton" in prompt
    assert "Betonspritzen mit Drohnen" in prompt
    assert "konkret" in MERGE_SYSTEM


def test_decide_merges_makes_exactly_one_call():
    llm = FakeLLM(MergeResult(groups=[]))
    decide_merges(llm, ["a", "b", "c"], {"a": ["x"], "b": [], "c": []}, "style")
    assert len(llm.calls) == 1


def test_apply_merges_reuses_an_existing_term_and_renames_it(store):
    existing = store.get_or_create_term("Betonspritzen mit Drohnen", created_at=1.0)
    result = MergeResult(
        groups=[
            MergeGroup(
                canonical_label="Roboter auf der Baustelle",
                members=["Betonspritzen mit Drohnen", "3D-Druck vor Ort"],
            )
        ]
    )
    person = store.create_person(started_at=1.0)

    term_ids = apply_merges(store, person.id, ["3D-Druck vor Ort"], result, at=2.0)

    assert term_ids == [existing.id]
    assert store.get_term(existing.id).label == "Roboter auf der Baustelle"
    # Every surface form now resolves to the same node — never re-derived.
    assert store.find_term_by_alias("3D-Druck vor Ort").id == existing.id
    assert store.find_term_by_alias("Betonspritzen mit Drohnen").id == existing.id
    assert store.list_merge_decisions()[0]["person_id"] == person.id


def test_apply_merges_creates_one_node_for_a_group_of_only_new_labels(store):
    person = store.create_person(started_at=1.0)
    result = MergeResult(
        groups=[MergeGroup(canonical_label="Ländlicher Leerstand", members=["leere Dörfer", "Leerstand auf dem Land"])]
    )

    term_ids = apply_merges(store, person.id, ["leere Dörfer", "Leerstand auf dem Land"], result, at=2.0)

    assert term_ids[0] == term_ids[1]
    assert len(store.list_terms()) == 1
    assert store.list_terms()[0].label == "Ländlicher Leerstand"


def test_labels_outside_any_group_stay_separate(store):
    person = store.create_person(started_at=1.0)
    result = MergeResult(groups=[])

    term_ids = apply_merges(store, person.id, ["Holzbau", "Bodenpreise"], result, at=2.0)

    assert len(set(term_ids)) == 2
    assert sorted(t.label for t in store.list_terms()) == ["Bodenpreise", "Holzbau"]


def test_apply_merges_is_idempotent_for_a_repeated_label(store):
    person = store.create_person(started_at=1.0)
    apply_merges(store, person.id, ["Holzbau"], MergeResult(groups=[]), at=2.0)
    person2 = store.create_person(started_at=3.0)

    term_ids = apply_merges(store, person2.id, ["Holzbau"], MergeResult(groups=[]), at=4.0)

    assert len(store.list_terms()) == 1
    assert term_ids == [store.list_terms()[0].id]


def test_apply_merges_folds_two_existing_terms_together_and_combines_mention_counts(store):
    # Finding 1: a group whose members are BOTH already-existing terms must not
    # orphan the second one — it has to fold onto one winner, edges and all.
    a = store.get_or_create_term("Photovoltaik am Haus", created_at=1.0)
    b = store.get_or_create_term("Solarzellen aufs Dach", created_at=1.0)
    p1 = store.create_person(started_at=1.0)
    p2 = store.create_person(started_at=2.0)
    store.add_edge(p1.id, a.id, created_at=1.0)
    store.add_edge(p2.id, b.id, created_at=2.0)

    result = MergeResult(
        groups=[
            MergeGroup(
                canonical_label="Sonnenenergie am Haus",
                members=["Photovoltaik am Haus", "Solarzellen aufs Dach"],
            )
        ]
    )
    person = store.create_person(started_at=3.0)

    term_ids = apply_merges(store, person.id, ["Photovoltaik am Haus"], result, at=4.0)

    remaining = store.list_terms()
    assert len(remaining) == 1  # the loser is gone, not just aliased away
    winner = remaining[0]
    assert winner.label == "Sonnenenergie am Haus"
    assert term_ids == [winner.id]
    # Both people's mentions now count toward the one surviving node.
    assert store.mention_count(winner.id) == 2
    assert store.find_term_by_alias("Photovoltaik am Haus").id == winner.id
    assert store.find_term_by_alias("Solarzellen aufs Dach").id == winner.id


def test_apply_merges_folds_three_existing_terms_together_and_combines_mention_counts(store):
    # Finding B (Task 9 fix round 2): fold_term's winner_id, *loser_ids =
    # existing_ids unpacking is only exercised by the tests with exactly TWO
    # already-existing terms in a group. A group of THREE must fold every
    # loser onto the same winner, not just the first, and a person who
    # mentioned two of the three originals must count once toward the
    # winner's mention_count, not twice.
    a = store.get_or_create_term("Regenwasser sammeln", created_at=1.0)
    b = store.get_or_create_term("Zisterne im Garten", created_at=1.0)
    c = store.get_or_create_term("Grauwasser nutzen", created_at=1.0)
    p1 = store.create_person(started_at=1.0)
    p2 = store.create_person(started_at=2.0)
    p3 = store.create_person(started_at=3.0)
    store.add_edge(p1.id, a.id, created_at=1.0)
    store.add_edge(p2.id, b.id, created_at=2.0)
    # p3 mentioned both b and c — must count once toward the winner, not twice.
    store.add_edge(p3.id, b.id, created_at=3.0)
    store.add_edge(p3.id, c.id, created_at=3.0)

    result = MergeResult(
        groups=[
            MergeGroup(
                canonical_label="Wasser im Kreislauf",
                members=["Regenwasser sammeln", "Zisterne im Garten", "Grauwasser nutzen"],
            )
        ]
    )
    person = store.create_person(started_at=4.0)

    term_ids = apply_merges(store, person.id, ["Regenwasser sammeln"], result, at=5.0)

    remaining = store.list_terms()
    assert len(remaining) == 1  # both losers are gone, not just aliased away
    winner = remaining[0]
    assert winner.label == "Wasser im Kreislauf"
    assert term_ids == [winner.id]
    # p1, p2, p3 are three distinct people — p3's double mention (b and c)
    # must not inflate the count.
    assert store.mention_count(winner.id) == 3
    assert store.find_term_by_alias("Regenwasser sammeln").id == winner.id
    assert store.find_term_by_alias("Zisterne im Garten").id == winner.id
    assert store.find_term_by_alias("Grauwasser nutzen").id == winner.id


def test_apply_merges_folds_a_canonical_label_collision_instead_of_raising(store):
    # Finding 2: `term.label` is UNIQUE. If a group resolves to an existing
    # term (via a member match) but the chosen canonical_label already belongs
    # to some OTHER existing term, a plain rename raises IntegrityError. That
    # must be treated as a merge with the colliding term instead, never a crash.
    colliding = store.get_or_create_term("Modulares Bauen", created_at=1.0)
    earlier_person = store.create_person(started_at=1.0)
    store.add_edge(earlier_person.id, colliding.id, created_at=1.0)
    member_term = store.get_or_create_term("Vorgefertigte Module", created_at=1.0)

    result = MergeResult(
        groups=[
            MergeGroup(
                canonical_label="Modulares Bauen",
                members=["Vorgefertigte Module", "Serielles Sanieren"],
            )
        ]
    )
    person = store.create_person(started_at=2.0)

    term_ids = apply_merges(
        store, person.id, ["Vorgefertigte Module", "Serielles Sanieren"], result, at=3.0
    )

    terms = store.list_terms()
    assert len(terms) == 1  # the collision target folded in, it did not survive separately
    winner = terms[0]
    assert winner.label == "Modulares Bauen"
    assert term_ids == [winner.id, winner.id]
    assert store.find_term_by_alias("Vorgefertigte Module").id == winner.id
    assert store.find_term_by_alias("Serielles Sanieren").id == winner.id
    assert store.mention_count(winner.id) == 1  # the earlier person's mention survived the fold


def test_apply_merges_is_all_or_nothing_on_a_crash_before_the_decision_is_logged(
    store, monkeypatch
):
    # Finding 3: every store call auto-commits individually today, so a crash
    # partway through the loop would leave earlier renames/aliases committed
    # with no matching decision logged. Force a crash at the very last step
    # (record_merge_decision) and assert nothing from earlier in the call
    # survives.
    person = store.create_person(started_at=1.0)
    result = MergeResult(
        groups=[
            MergeGroup(
                canonical_label="Ländlicher Leerstand",
                members=["leere Dörfer", "Leerstand auf dem Land"],
            )
        ]
    )

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(store, "record_merge_decision", boom)

    with pytest.raises(RuntimeError, match="boom"):
        apply_merges(
            store, person.id, ["leere Dörfer", "Leerstand auf dem Land"], result, at=2.0
        )

    assert store.list_terms() == []
    assert store.list_merge_decisions() == []


def test_a_label_repeated_across_two_groups_does_not_conflate_them(store):
    # Finding 4: group 1's aliases become visible to group 2 within the same
    # call. A label appearing in both groups must not silently drag group 2's
    # other members into group 1's node — the chosen behaviour is that the
    # earlier group keeps the shared label, and the later group's remaining
    # member(s) fall back to standing alone.
    person = store.create_person(started_at=1.0)
    result = MergeResult(
        groups=[
            MergeGroup(canonical_label="Gruppe A", members=["gemeinsam", "nur A"]),
            MergeGroup(canonical_label="Gruppe B", members=["gemeinsam", "nur B"]),
        ]
    )

    term_ids = apply_merges(store, person.id, ["gemeinsam", "nur A", "nur B"], result, at=2.0)

    labels = sorted(t.label for t in store.list_terms())
    assert "Gruppe B" not in labels  # never created — its group lost its second member
    gruppe_a = store.get_term_by_label("Gruppe A")
    assert gruppe_a is not None
    assert term_ids[0] == gruppe_a.id  # "gemeinsam"
    assert term_ids[1] == gruppe_a.id  # "nur A"
    nur_b = store.find_term_by_alias("nur B")
    assert nur_b.id != gruppe_a.id
    assert nur_b.label == "nur B"  # standalone, not conflated into Gruppe A
