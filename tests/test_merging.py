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
