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
    unquote_label,
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


def test_apply_merges_does_not_rename_a_node_two_people_already_share(store):
    # D5 (Birk, 2026-08-19), Task 19c. Run 19b: p7 and p22 had grown
    # „Baustoff mit Geschichte"; interview 037 then correctly merged a fourth
    # phrasing into it and renamed the node to „Vorzeitiger Gebäudeabriss" —
    # the opposite meaning, and the label is the embedder's text for the node,
    # so the next recycling interview no longer found it. From the second
    # distinct person on, the name stays put. The merge itself still happens.
    established = store.get_or_create_term("Baustoff mit Geschichte", created_at=1.0)
    p1 = store.create_person(started_at=1.0)
    p2 = store.create_person(started_at=2.0)
    store.add_edge(p1.id, established.id, created_at=1.0)
    store.add_edge(p2.id, established.id, created_at=2.0)

    result = MergeResult(
        groups=[
            MergeGroup(
                canonical_label="Vorzeitiger Gebäudeabriss",
                members=["Baustoff mit Geschichte", "Abbruchschutt als Wandmaterial"],
            )
        ]
    )
    person = store.create_person(started_at=3.0)

    term_ids = apply_merges(
        store, person.id, ["Abbruchschutt als Wandmaterial"], result, at=4.0
    )

    terms = store.list_terms()
    assert len(terms) == 1
    assert terms[0].id == established.id
    assert terms[0].label == "Baustoff mit Geschichte"  # the visible label stays put
    assert term_ids == [established.id]  # the fold happened regardless
    assert store.find_term_by_alias("Abbruchschutt als Wandmaterial").id == established.id
    # The refused name is still the judge's finding: it stays reachable as a
    # synonym, so a later interview using that phrasing lands on this node.
    assert store.find_term_by_alias("Vorzeitiger Gebäudeabriss").id == established.id
    assert store.mention_count(established.id) == 2


def test_a_group_merging_two_one_mention_nodes_may_still_name_itself(store):
    # The lock is judged against the winner's mention count BEFORE the fold:
    # the merge and its naming are ONE decision. Two nodes of one person each
    # are both still private, so the group they form may carry a new name —
    # even though the winner counts two people the instant the fold is done.
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

    apply_merges(store, person.id, ["Photovoltaik am Haus"], result, at=4.0)

    winner = store.list_terms()[0]
    assert winner.label == "Sonnenenergie am Haus"
    assert store.mention_count(winner.id) == 2


def test_a_refused_rename_still_folds_and_still_writes_the_aliases(store):
    # The other half of the same rule: the winner is already shared by two
    # people AND the group's chosen name belongs to a second existing node
    # that is being folded in. The fold must go through — nothing may be left
    # stranded on an unreachable node — and only the visible label stays put.
    established = store.get_or_create_term("Gemeinsamer Hausbesitz", created_at=1.0)
    other = store.get_or_create_term("Baugruppen", created_at=2.0)
    p1 = store.create_person(started_at=1.0)
    p2 = store.create_person(started_at=2.0)
    p3 = store.create_person(started_at=3.0)
    store.add_edge(p1.id, established.id, created_at=1.0)
    store.add_edge(p2.id, established.id, created_at=2.0)
    store.add_edge(p3.id, other.id, created_at=3.0)

    result = MergeResult(
        groups=[
            MergeGroup(
                canonical_label="Baugruppen",
                members=["Gemeinsamer Hausbesitz", "Baugruppen"],
            )
        ]
    )
    person = store.create_person(started_at=4.0)

    term_ids = apply_merges(store, person.id, ["Baugruppen"], result, at=5.0)

    terms = store.list_terms()
    assert len(terms) == 1  # the loser is gone, not stranded
    assert terms[0].id == established.id
    assert terms[0].label == "Gemeinsamer Hausbesitz"
    assert term_ids == [established.id]
    assert store.find_term_by_alias("Baugruppen").id == established.id
    assert store.mention_count(established.id) == 3  # p3's mention moved over


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


def test_apply_merges_folds_members_the_model_echoed_back_in_typographic_quotes(store):
    # Task 19: build_merge_prompt renders every label as „Label“, and the model
    # answers in the same notation — it echoes the quote characters as part of
    # the member string. Looked up verbatim, „Zugepflasterte Landschaft“ never
    # matches the stored term Zugepflasterte Landschaft, so the group resolved
    # to nothing, a duplicate term was created for the canonical label, and the
    # two real terms stayed unmerged. This is the exact p43 case from the first
    # full calibration run (out/sim19/sim.db), which scored 0 of 5.
    a = store.get_or_create_term("Zugepflasterte Landschaft", created_at=1.0)
    b = store.get_or_create_term("Zugebaute Freiflächen", created_at=1.0)
    p1 = store.create_person(started_at=1.0)
    p2 = store.create_person(started_at=2.0)
    store.add_edge(p1.id, a.id, created_at=1.0)
    store.add_edge(p2.id, b.id, created_at=2.0)

    result = MergeResult(
        groups=[
            MergeGroup(
                canonical_label="Zugebaute Freiflächen",
                members=["„Zugepflasterte Landschaft“", "„Zugebaute Freiflächen“"],
            )
        ]
    )
    person = store.create_person(started_at=3.0)

    term_ids = apply_merges(store, person.id, ["Zugepflasterte Landschaft"], result, at=4.0)

    terms = store.list_terms()
    assert len(terms) == 1  # no duplicate term for the canonical label
    winner = terms[0]
    assert winner.label == "Zugebaute Freiflächen"
    assert term_ids == [winner.id]  # the input label resolves to the merged node
    assert store.mention_count(winner.id) == 2  # the loser's edge moved over
    # Detection and storage must not diverge: the alias written is the plain
    # surface form, so a later interview saying the same thing resolves here.
    assert store.find_term_by_alias("Zugepflasterte Landschaft").id == winner.id
    assert store.find_term_by_alias("„Zugepflasterte Landschaft“") is None


def test_apply_merges_strips_quotes_from_a_canonical_label_too(store):
    # The model quotes the name it invents just as readily as the members; a
    # quoted canonical label would put „…“ on the wall and collide with nothing.
    person = store.create_person(started_at=1.0)
    result = MergeResult(
        groups=[
            MergeGroup(
                canonical_label="„Ländlicher Leerstand“",
                members=["„leere Dörfer“", "„Leerstand auf dem Land“"],
            )
        ]
    )

    term_ids = apply_merges(
        store, person.id, ["leere Dörfer", "Leerstand auf dem Land"], result, at=2.0
    )

    assert len(store.list_terms()) == 1
    assert store.list_terms()[0].label == "Ländlicher Leerstand"
    assert term_ids[0] == term_ids[1] == store.list_terms()[0].id


def test_apply_merges_falls_back_to_a_member_when_the_canonical_label_is_all_quotes(store):
    # Stripping can empty a canonical label out („“ -> ""). A term named "" must
    # never reach the wall — but the merge judgement itself is still worth
    # keeping, so the group falls back to naming itself after its first member.
    person = store.create_person(started_at=1.0)
    result = MergeResult(
        groups=[MergeGroup(canonical_label="„“", members=["„leere Dörfer“", "„Leerstand auf dem Land“"])]
    )

    term_ids = apply_merges(
        store, person.id, ["leere Dörfer", "Leerstand auf dem Land"], result, at=2.0
    )

    assert len(store.list_terms()) == 1
    assert store.list_terms()[0].label == "leere Dörfer"
    assert term_ids[0] == term_ids[1]


def test_apply_merges_folds_a_single_member_group_whose_canonical_label_matches_an_existing_term(
    store,
):
    # Bug A (out/sim19c/sim.db): the judge sometimes puts the EXISTING node in
    # canonical_label and only the NEW term in members, e.g.
    # {"canonical_label": "Bodenpolitik", "members": ["Bodenpolitik und Baurecht"]}.
    # That is a complete, valid merge statement — the old `len(members) < 2`
    # guard threw it away, leaving "Bodenpolitik" and "Bodenpolitik und
    # Baurecht" as two separate one-mention nodes instead of one node with two.
    existing = store.get_or_create_term("Bodenpolitik", created_at=1.0)
    result = MergeResult(
        groups=[
            MergeGroup(canonical_label="Bodenpolitik", members=["Bodenpolitik und Baurecht"])
        ]
    )
    person = store.create_person(started_at=2.0)

    term_ids = apply_merges(store, person.id, ["Bodenpolitik und Baurecht"], result, at=2.0)

    assert term_ids == [existing.id]
    assert len(store.list_terms()) == 1
    assert store.find_term_by_alias("Bodenpolitik und Baurecht").id == existing.id


def test_apply_merges_folds_a_single_member_group_whose_canonical_label_is_only_an_alias(store):
    # The spec asks for resolution via `find_term_by_alias` OR
    # `get_term_by_label` — a canonical_label that only matches a past alias
    # (not the node's current displayed label) must still resolve.
    existing = store.get_or_create_term("Weiterbauen im Bestand", created_at=1.0)
    store.add_alias(existing.id, "Sanieren, Umbauen, Weiterbauen")
    result = MergeResult(
        groups=[
            MergeGroup(
                canonical_label="Sanieren, Umbauen, Weiterbauen",
                members=["Neu denken statt abreißen"],
            )
        ]
    )
    person = store.create_person(started_at=2.0)

    term_ids = apply_merges(store, person.id, ["Neu denken statt abreißen"], result, at=2.0)

    assert term_ids == [existing.id]
    assert len(store.list_terms()) == 1
    assert store.find_term_by_alias("Neu denken statt abreißen").id == existing.id


def test_apply_merges_ignores_a_single_member_group_whose_canonical_label_does_not_resolve(store):
    # No existing node named or aliased "Kompostierbare Fassaden" — this is
    # not a valid merge statement, so it stays wirkungslos and the member
    # gets its own node via the usual get_or_create_term fallback.
    result = MergeResult(
        groups=[
            MergeGroup(
                canonical_label="Kompostierbare Fassaden", members=["Pilzbasierte Dämmstoffe"]
            )
        ]
    )
    person = store.create_person(started_at=1.0)

    term_ids = apply_merges(store, person.id, ["Pilzbasierte Dämmstoffe"], result, at=2.0)

    terms = store.list_terms()
    assert len(terms) == 1
    assert terms[0].label == "Pilzbasierte Dämmstoffe"
    assert term_ids == [terms[0].id]


def test_apply_merges_ignores_a_group_with_no_members(store):
    result = MergeResult(groups=[MergeGroup(canonical_label="Ghost", members=[])])
    person = store.create_person(started_at=1.0)

    term_ids = apply_merges(store, person.id, ["Holzbau"], result, at=2.0)

    assert store.list_terms()[0].label == "Holzbau"
    assert term_ids == [store.list_terms()[0].id]


def test_apply_merges_finds_an_existing_term_through_a_double_escaped_member(store):
    # Bug B (out/sim19c/sim.db): the judge occasionally echoes a member as
    # literal escaped text — "Betonsprühende Maschinen" as the six raw
    # characters backslash, u, 0, 0, f, c — instead of the decoded "ü". Left
    # undecoded, the alias is stored under a surface nobody ever types again.
    existing = store.get_or_create_term("Mauerroboter", created_at=1.0)
    result = MergeResult(
        groups=[
            MergeGroup(
                canonical_label="Mauerroboter",
                members=["Mauerroboter", "Betonspr\\u00fchende Maschinen"],
            )
        ]
    )
    person = store.create_person(started_at=1.0)

    term_ids = apply_merges(store, person.id, ["Betonsprühende Maschinen"], result, at=2.0)

    assert term_ids == [existing.id]
    assert store.find_term_by_alias("Betonsprühende Maschinen").id == existing.id
    assert store.find_term_by_alias("Betonspr\\u00fchende Maschinen") is None


def test_unquote_label_strips_typographic_and_ascii_pairs_but_not_inner_marks():
    assert unquote_label("„Zugebaute Freiflächen“") == "Zugebaute Freiflächen"
    assert unquote_label(" “Recycling-Beton” ") == "Recycling-Beton"
    assert unquote_label('"Holzbau"') == "Holzbau"
    assert unquote_label("'Holzbau'") == "Holzbau"
    assert unquote_label("Holzbau") == "Holzbau"
    # An apostrophe inside the label is part of the word, not a wrapper.
    assert unquote_label("Bauen fürs Übermorgen") == "Bauen fürs Übermorgen"
    assert unquote_label("„“") == ""


def test_unquote_label_decodes_a_double_escaped_unicode_sequence():
    # Bug B: the model sometimes emits the six raw characters \, u, 0, 0, f, c
    # instead of the decoded "ü" (out/sim19c/sim.db: "Betonsprühende
    # Maschinen"). unquote_label must decode this before the lookup.
    assert unquote_label('"Betonspr\\u00fchende Maschinen"') == "Betonsprühende Maschinen"


def test_unquote_label_decodes_the_carriage_return_escape_variant_and_strips_the_result():
    # Second observed form in the same DB: the escape prefix survives JSON
    # decoding as an actual carriage-return control character (not the two
    # characters "\" "r") immediately followed by literal "u201e"/"u201c" hex
    # digits. Decoding must happen BEFORE the quote-stripping loop below, or
    # the resulting „ / " characters are never stripped off the ends.
    label = "\ru201eBürgerversammlung als Pflichttermin\ru201c"
    assert unquote_label(label) == "Bürgerversammlung als Pflichttermin"


def test_unquote_label_leaves_a_lookalike_escape_sequence_unchanged():
    # Looks like an escape sequence but isn't a valid one (too few hex digits,
    # non-hex characters) — must pass through unchanged, never raise.
    assert unquote_label("Preis \\u12 Rabatt") == "Preis \\u12 Rabatt"
    assert unquote_label("Budget \\uZZZZ Rest") == "Budget \\uZZZZ Rest"


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
