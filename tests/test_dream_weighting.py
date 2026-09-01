"""Spec §5.1 — what goes into stage 1, and what deliberately does not."""

from __future__ import annotations

import copy

from kg2.weighting import (
    Material,
    build_material,
    render_material,
    select_marginal,
    select_recent,
)


def graph(nodes, edges, quotes=(), *, min_mentions=1, generated_at=1000.0) -> dict:
    return {
        "version": 1,
        "generated_at": generated_at,
        "min_mentions": min_mentions,
        "nodes": nodes,
        "edges": [
            {"id": f"e{i}", "source": s, "target": t} for i, (s, t) in enumerate(edges, 1)
        ],
        "quotes": [
            {"id": f"q{i}", "person_id": p, "text": text}
            for i, (p, text) in enumerate(quotes, 1)
        ],
    }


def person(pid, hidden=False) -> dict:
    return {
        "id": pid, "type": "person", "portrait": None, "created_at": 1.0,
        "hidden": hidden, "x": None, "y": None,
    }


def term(tid, label, mentions, hidden=False, created_at=2.0) -> dict:
    return {
        "id": tid, "type": "term", "label": label, "mentions": mentions,
        "created_at": created_at, "hidden": hidden, "x": None, "y": None,
    }


def test_shared_terms_are_ordered_by_how_many_people_said_them():
    material = build_material(
        graph(
            [person("p1"), person("p2"), person("p3"),
             term("t1", "Weiterbauen im Bestand", 3), term("t2", "Holzbau", 2)],
            [("p1", "t1"), ("p2", "t1"), ("p3", "t1"), ("p1", "t2"), ("p2", "t2")],
        )
    )

    assert [(w.label, w.mentions) for w in material.shared] == [
        ("Weiterbauen im Bestand", 3),
        ("Holzbau", 2),
    ]
    assert material.marginal == []


def test_a_term_said_by_one_person_is_marginal_not_shared():
    material = build_material(
        graph(
            [person("p1"), person("p2"),
             term("t1", "Holzbau", 2), term("t2", "Sickerfähige Beläge", 1)],
            [("p1", "t1"), ("p2", "t1"), ("p1", "t2")],
        )
    )

    assert [w.label for w in material.shared] == ["Holzbau"]
    assert [w.label for w in material.marginal] == ["Sickerfähige Beläge"]


def test_min_mentions_is_never_applied():
    """Spec §5.1: that dial is the wall's legibility filter, not a statement
    about what was said. The dream reads everything."""
    material = build_material(
        graph(
            [person("p1"), term("t1", "Sickerfähige Beläge", 1)],
            [("p1", "t1")],
            min_mentions=3,
        )
    )

    assert [w.label for w in material.marginal] == ["Sickerfähige Beläge"]


def test_a_hidden_term_is_excluded():
    """T1§8's emergency exit: something pulled from the wall must not reappear
    in the dream."""
    material = build_material(
        graph(
            [person("p1"), person("p2"),
             term("t1", "Holzbau", 2), term("t2", "Peinlich", 2, hidden=True)],
            [("p1", "t1"), ("p2", "t1"), ("p1", "t2"), ("p2", "t2")],
        )
    )

    labels = [w.label for w in material.shared + material.marginal]
    assert labels == ["Holzbau"]
    assert material.term_count == 1


def test_a_hidden_person_is_excluded_and_their_mentions_do_not_count():
    """The payload's `mentions` counts edges from hidden persons too. Reading it
    off the node would leave a hidden visitor's voice in the dream."""
    material = build_material(
        graph(
            [person("p1"), person("p2", hidden=True), term("t1", "Holzbau", 2)],
            [("p1", "t1"), ("p2", "t1")],
        )
    )

    assert material.person_count == 1
    # Recomputed from the surviving edges: 1, not the payload's 2.
    assert [(w.label, w.mentions) for w in material.marginal] == [("Holzbau", 1)]
    assert material.shared == []


def test_a_term_left_with_no_speakers_disappears_entirely():
    material = build_material(
        graph(
            [person("p1", hidden=True), term("t1", "Holzbau", 1)],
            [("p1", "t1")],
        )
    )

    assert material.shared == []
    assert material.marginal == []
    assert material.term_count == 0
    assert material.edge_count == 0


def test_quotes_are_included():
    """T1§11 stores them for Tool 2's benefit even though the wall never shows
    them (spec §5.1)."""
    material = build_material(
        graph(
            [person("p1"), term("t1", "Holzbau", 1)],
            [("p1", "t1")],
            [("p1", "Wir bauen zu viel Neues.")],
        )
    )

    assert material.quotes == ["Wir bauen zu viel Neues."]


def test_a_hidden_persons_quote_is_excluded():
    material = build_material(
        graph(
            [person("p1"), person("p2", hidden=True), term("t1", "Holzbau", 2)],
            [("p1", "t1"), ("p2", "t1")],
            [("p1", "bleibt"), ("p2", "verschwindet")],
        )
    )

    assert material.quotes == ["bleibt"]


def test_counts_describe_what_the_dream_actually_saw():
    material = build_material(
        graph(
            [person("p1"), person("p2"), term("t1", "a", 2), term("t2", "b", 1)],
            [("p1", "t1"), ("p2", "t1"), ("p1", "t2")],
            generated_at=1700000000.0,
        )
    )

    assert material == Material(
        person_count=2,
        term_count=2,
        edge_count=3,
        generated_at=1700000000.0,
        shared=material.shared,
        marginal=material.marginal,
        quotes=[],
        # Seit 2026-08-30 traegt Material die zuletzt hinzugekommene Person:
        # sie verankert den Bildausschnitt (`select_required`). Beide Personen
        # dieses Fixtures haben dasselbe created_at, also gewinnt die erste,
        # die durchlaeuft — hier p1.
        last_person_id="p1",
    )


def test_an_empty_graph_produces_empty_material():
    material = build_material(graph([], []))

    assert material.person_count == 0
    assert material.shared == []
    assert material.marginal == []
    assert material.quotes == []


def test_render_labels_the_marginal_terms_as_detail_not_theme():
    """Spec §5.1: single mentions enter „explicitly labelled as such so the
    model can place them as a detail rather than a theme".

    🔴 Der Graph ist am 2026-09-01 GEWACHSEN, und das gehoert zur Aussage.
    Vorher standen hier zwei Begriffe, „Holzbau" (2x) und „Sickerfaehige
    Belaege" (1x) -- und `select_required` nahm bei so wenig Material BEIDE in
    die Pflichtliste. Der Test bestand also nur, solange derselbe Begriff
    gleichzeitig als Pflicht und als „Detail und Beiwerk, nicht Thema" im
    Prompt stand. Genau dieser Widerspruch ist am ersten Ausstellungsabend an
    Traum d1 aufgeschlagen (3 von 3 Pflichtbegriffen betroffen).

    Die Absicht der Spec bleibt unveraendert pruefbar -- sie braucht nur einen
    Graphen, in dem eine Einmal-Nennung wirklich KEINE Pflicht ist.
    """
    nodes = [person(f"p{i}") for i in range(1, 4)]
    nodes.append(term("t1", "Holzbau", 3))
    # Mehr Einmal-Nennungen als die Pflichtliste fasst, damit unten wirklich
    # etwas uebrigbleibt.
    nodes += [
        term(f"t{i}", f"Sickerfähige Beläge {i}", 1, created_at=float(i))
        for i in range(2, 9)
    ]
    edges = [("p1", "t1"), ("p2", "t1"), ("p3", "t1")]
    edges += [(f"p{(i % 3) + 1}", f"t{i}") for i in range(2, 9)]

    text = render_material(build_material(graph(nodes, edges)))

    assert "Holzbau" in text
    assert "3×" in text
    # The label is what makes the weighting legible to the model.
    assert "Detail" in text
    assert "Randnotiz" in text


def test_render_omits_a_section_that_has_nothing_in_it():
    """An empty heading reads to the model as „there were no quotes", which is
    true but noisy; leaving it out is the same statement, shorter."""
    material = build_material(
        graph([person("p1"), person("p2"), term("t1", "Holzbau", 2)],
              [("p1", "t1"), ("p2", "t1")])
    )

    text = render_material(material)

    assert "Randnotiz" not in text
    assert "Stimmen" not in text


# -- the header (removed) ----------------------------------------------------


def test_render_no_longer_prints_the_person_term_edge_header():
    """Contributed nothing the weighting did not already say, and tempted the
    model to write the count into the sentence (observed: „...zu sechzig im
    Hof...")."""
    material = build_material(
        graph(
            [person("p1"), person("p2"), term("t1", "Holzbau", 2)],
            [("p1", "t1"), ("p2", "t1")],
        )
    )

    text = render_material(material)

    assert "Der Graph umfasst" not in text
    assert "Verbindungen." not in text


# -- quotes (opt-in only) -----------------------------------------------------


def test_render_omits_quotes_by_default():
    """Spec §5.1 (revised): on the wall only the terms are visible; a prompt
    that is three quarters invisible-in-the-room material would break the
    graph-to-image link (the same argument spec §10 uses against graph-driven
    style)."""
    material = build_material(
        graph(
            [person("p1"), term("t1", "Holzbau", 1)],
            [("p1", "t1")],
            [("p1", "Wir bauen zu viel Neues.")],
        )
    )

    text = render_material(material)

    assert "Wir bauen zu viel Neues." not in text
    assert "Stimmen" not in text


def test_render_includes_quotes_when_asked_for_a_comparison_run():
    material = build_material(
        graph(
            [person("p1"), term("t1", "Holzbau", 1)],
            [("p1", "t1")],
            [("p1", "Wir bauen zu viel Neues.")],
        )
    )

    text = render_material(material, include_quotes=True)

    assert "Wir bauen zu viel Neues." in text


# -- the gliding single-mention selection ------------------------------------


def _shared_terms(n: int) -> list[dict]:
    return [term(f"s{i}", f"shared-{i}", 2) for i in range(n)]


def _shared_edges(n: int) -> list[tuple[str, str]]:
    edges = []
    for i in range(n):
        edges.append((f"p{2*i}", f"s{i}"))
        edges.append((f"p{2*i+1}", f"s{i}"))
    return edges


def _persons_for_shared(n: int) -> list[dict]:
    return [person(f"p{i}") for i in range(2 * n)]


def test_all_shared_terms_are_never_capped():
    """Unlike the wall, the dream has no space problem — a term two people
    said must never be dropped."""
    shared_count = 40
    material = build_material(
        graph(_persons_for_shared(shared_count) + _shared_terms(shared_count),
              _shared_edges(shared_count))
    )

    text = render_material(material)

    for i in range(shared_count):
        assert f"shared-{i}" in text


def test_select_marginal_follows_the_gliding_formula():
    """erlaubt = round(N * max(0, 1 - len(shared) / X)) — this proves the
    formula, not just an endpoint."""
    budget, saturation = 20, 25

    # 0 shared -> all N single mentions allowed.
    zero_shared = build_material(
        graph([person("p1")] + [term(f"m{i}", f"m{i}", 1) for i in range(25)],
              [("p1", f"m{i}") for i in range(25)])
    )
    assert len(select_marginal(zero_shared, budget=budget, saturation=saturation)) == budget

    # len(shared) >= X -> zero single mentions allowed.
    saturated = build_material(
        graph(_persons_for_shared(saturation) + _shared_terms(saturation)
              + [term("m0", "m0", 1, created_at=99.0)],
              _shared_edges(saturation) + [("p0", "m0")])
    )
    assert select_marginal(saturated, budget=budget, saturation=saturation) == []

    # In between: the rounded intermediate value. 12 shared terms, plenty of
    # single mentions available so the formula's count is never capped by
    # how many marginal terms actually exist.
    shared_n = 12
    shared_persons = _persons_for_shared(shared_n)
    marginal_persons = [person(f"q{i}") for i in range(25)]
    halfway = build_material(
        graph(
            shared_persons + marginal_persons + _shared_terms(shared_n)
            + [term(f"m{i}", f"m{i}", 1) for i in range(25)],
            _shared_edges(shared_n) + [(f"q{i}", f"m{i}") for i in range(25)],
        )
    )
    expected = round(budget * max(0, 1 - shared_n / saturation))
    assert len(select_marginal(halfway, budget=budget, saturation=saturation)) == expected


def test_select_marginal_keeps_the_most_recent_single_mentions():
    """Newest, not oldest: the just-finished interview must be represented."""
    material = build_material(
        graph(
            [person("p1"), person("p2"),
             term("old", "Altes Detail", 1, created_at=1.0),
             term("new", "Neues Detail", 1, created_at=99.0)],
            [("p1", "old"), ("p2", "new")],
        )
    )

    selected = select_marginal(material, budget=1, saturation=25)

    assert [w.label for w in selected] == ["Neues Detail"]


# -- the recency block ("Zuletzt gesagt") ------------------------------------


def test_recent_terms_are_drawn_from_shared_and_marginal_alike():
    """The core case: a young term with exactly ONE mention shows up here even
    though it would never make it into the main block by frequency alone —
    the recency axis is independent of the weighting axis."""
    material = build_material(
        graph(
            [person("p1"), person("p2"), person("p3"),
             term("t1", "Altes Thema", 3, created_at=1.0),
             term("t2", "Neues Detail", 1, created_at=99.0)],
            [("p1", "t1"), ("p2", "t1"), ("p3", "t1"), ("p1", "t2")],
        )
    )

    selected = select_recent(material, count=2)

    assert [w.label for w in selected] == ["Neues Detail", "Altes Thema"]


def test_recent_terms_break_ties_on_created_at_by_label():
    """Same created_at: label is the deterministic second key, same discipline
    as select_marginal (spec §5.3)."""
    material = build_material(
        graph(
            [person("p1"), person("p2"), person("p3"),
             term("t1", "Zebra", 1, created_at=5.0),
             term("t2", "Anfang", 1, created_at=5.0),
             term("t3", "Mitte", 1, created_at=5.0)],
            [("p1", "t1"), ("p2", "t2"), ("p3", "t3")],
        )
    )

    selected = select_recent(material, count=3)

    assert [w.label for w in selected] == ["Anfang", "Mitte", "Zebra"]


def test_select_recent_respects_the_count():
    material = build_material(
        graph(
            [person(f"p{i}") for i in range(5)]
            + [term(f"t{i}", f"term-{i}", 1, created_at=float(i)) for i in range(5)],
            [(f"p{i}", f"t{i}") for i in range(5)],
        )
    )

    assert len(select_recent(material, count=2)) == 2
    assert len(select_recent(material, count=0)) == 0


def test_render_includes_the_recency_block():
    material = build_material(
        graph(
            [person("p1"), person("p2"), person("p3"),
             term("t1", "Altes Thema", 3, created_at=1.0),
             term("t2", "Neues Detail", 1, created_at=99.0)],
            [("p1", "t1"), ("p2", "t1"), ("p3", "t1"), ("p1", "t2")],
        )
    )

    text = render_material(material)

    assert "Zuletzt gesagt" in text
    assert "Neues Detail" in text


def test_a_shared_term_may_reappear_in_the_recency_block():
    """The point of the second block: a term already in the main block gets
    doubly emphasised by showing up again here.

    Counted against the two blocks by name rather than over the whole text:
    since 2026-08-30 `render_material` opens with the mechanically computed
    block of required terms (`select_required`), where the same term legitimately
    appears a third time. Counting the whole string would make this test fail
    for a reason that has nothing to do with the property it guards.
    """
    material = build_material(
        graph(
            [person("p1"), person("p2"), term("t1", "Holzbau", 2, created_at=50.0)],
            [("p1", "t1"), ("p2", "t1")],
        )
    )

    text = render_material(material, recent_terms=1)

    geteilt = text.split("Geteilte Begriffe")[1].split("Zuletzt gesagt")[0]
    zuletzt = text.split("Zuletzt gesagt")[1]
    assert "Holzbau" in geteilt
    assert "Holzbau" in zuletzt


def test_render_omits_the_recency_block_when_material_is_empty():
    material = build_material(graph([], []))

    text = render_material(material)

    assert text == ""
    assert "Zuletzt gesagt" not in text


def test_render_is_deterministic_across_two_calls():
    material = build_material(
        graph(
            [person("p1"), person("p2"), person("p3"),
             term("t1", "Altes Thema", 3, created_at=1.0),
             term("t2", "Neues Detail", 1, created_at=99.0)],
            [("p1", "t1"), ("p2", "t1"), ("p3", "t1"), ("p1", "t2")],
        )
    )

    assert render_material(material) == render_material(material)


# -- malformed payloads -------------------------------------------------------


def test_a_malformed_payload_degrades_to_empty_material():
    """`kg2.graph_client.fetch_graph` only checks that `version`, `nodes` and
    `edges` are present — never their value types (see review of an earlier
    task). `kg2.trigger.absorbed_persons` was hardened against exactly this
    shape; `build_material` must degrade the same way rather than raise."""
    malformed = {"version": 1, "nodes": "corrupted", "edges": []}

    material = build_material(malformed)

    assert material == Material(0, 0, 0, None, [], [], [])


def test_a_well_shaped_list_of_ill_shaped_nodes_does_not_raise():
    """`nodes` IS a list, but entries are missing `id`/`label`, or are not
    dicts at all. Subscripting one would raise on a payload the client waved
    through."""
    bad_graph = {
        "version": 1,
        "generated_at": None,
        "nodes": [
            "not-a-dict",
            {"type": "person"},  # person, no id
            {"type": "person", "id": None},
            {"type": "term"},  # term, no id or label
            {"type": "term", "id": "t1"},  # term, no label
            None,
        ],
        "edges": [{"id": "e1", "source": "p1", "target": "t1"}, "not-a-dict", None],
        "quotes": ["not-a-dict", {"person_id": "p1", "text": "hi"}, None],
    }

    material = build_material(bad_graph)

    assert material.person_count == 0
    assert material.shared == []
    assert material.marginal == []


def test_a_none_graph_degrades_to_empty_material():
    assert build_material(None) == Material(0, 0, 0, None, [], [], [])


def test_an_unhashable_person_id_does_not_crash_the_set_comprehension():
    """`node.get("id")` used to go straight into a set comprehension. A list
    id is unhashable and raised `TypeError` before ids were filtered to
    strings — the same landmine as `kg2.trigger.absorbed_persons`."""
    bad = graph(
        [person(["weird"]), term("t1", "x", 1)],
        [(["weird"], "t1")],
    )

    material = build_material(bad)

    assert material == Material(0, 0, 0, 1000.0, [], [], [])


def test_non_comparable_term_labels_tied_on_mentions_do_not_crash_the_sort():
    """Two terms tied on mention count, one with a string label and one with
    a non-string label: `weights.sort(key=lambda w: (-w.mentions, w.label))`
    raised comparing str to int before labels were filtered to strings."""
    bad = graph(
        [person("p1"), term("t1", "x", 1), term("t2", 42, 1)],
        [("p1", "t1"), ("p1", "t2")],
    )

    material = build_material(bad)

    # t2's non-string label is dropped, so only t1 survives as marginal.
    assert [w.label for w in material.marginal] == ["x"]


def test_an_unhashable_edge_source_does_not_crash_the_membership_check():
    """`source in persons` hashes `source`. A list source is unhashable and
    would raise even though `persons` itself only ever contains strings."""
    bad = graph(
        [person("p1"), term("t1", "x", 1)],
        [],
    )
    bad["edges"] = [{"id": "e1", "source": ["weird"], "target": "t1"}]

    material = build_material(bad)

    assert material.edge_count == 0
    assert material.marginal == []


def test_an_unhashable_quote_person_id_does_not_crash_the_membership_check():
    """`quote.get("person_id") in persons` has the same hashability landmine
    as the edge loop above."""
    bad = graph(
        [person("p1"), term("t1", "x", 1)],
        [("p1", "t1")],
    )
    bad["quotes"] = [{"id": "q1", "person_id": ["weird"], "text": "hi"}]

    material = build_material(bad)

    assert material.quotes == []


# -- against the real thing -------------------------------------------------


def test_the_real_replay_graph_yields_realistic_material(real_graph):
    """Spec §11: contract against a real artefact. Run 19c has a long tail of
    single mentions — the shape the weighting exists to handle."""
    material = build_material(real_graph)

    assert material.person_count == 60
    assert material.term_count == 163
    assert material.edge_count == 267
    assert len(material.quotes) == 117
    assert len(material.shared) + len(material.marginal) == 163
    # 114 of 163 terms were said by exactly one person (docs/operations.md).
    assert len(material.marginal) == 114
    assert material.shared[0].mentions == 7


def test_the_real_graph_renders_into_a_prompt_of_workable_size(real_graph):
    """~50 persons is the ceiling (T1§2), so this stays bounded — and nothing
    about the SHARED terms is silently truncated to make it so. At 60 people
    the real graph has 49 shared terms (docs/operations.md) — already at or
    above the default saturation, so the single-mention budget is exhausted
    and the block is materially smaller than before quotes and the header
    were dropped."""
    text = render_material(build_material(real_graph))

    assert "Scheinbeteiligung pro forma" in text  # the most-mentioned term
    assert 500 < len(text) < 10_000


def test_hiding_a_person_in_the_real_graph_removes_their_voice(real_graph):
    graph_with_hidden = copy.deepcopy(real_graph)
    for node in graph_with_hidden["nodes"]:
        if node["id"] == "p1":
            node["hidden"] = True

    material = build_material(graph_with_hidden)
    quotes_of_p1 = [q["text"] for q in real_graph["quotes"] if q["person_id"] == "p1"]

    assert material.person_count == 59
    assert all(quote not in material.quotes for quote in quotes_of_p1)


# --- Der Widerspruch Pflicht/Randnotiz (Birk, 2026-09-01) -------------------
#
# Am ersten Ausstellungsabend stand im selben Prompt ueber dieselben drei
# Woerter „DIESE BEGRIFFE MUESSEN INS BILD" und „Das sind Detail und Beiwerk,
# nicht Thema. Sie duerfen im Bild vorkommen, aber klein und am Rand."
# Gemessen an d1: 3 von 3 Pflichtbegriffen waren betroffen, und der
# bildstaerkste davon (Earthship) fehlte im Bild.
#
# Das trifft nicht einen Sonderfall, sondern den ganzen VORMITTAG: solange
# kein Begriff von zwei Menschen genannt wurde, ist `shared` leer, jeder
# Begriff ist eine Einmal-Nennung -- und landet damit zwangslaeufig in beiden
# Listen.


def test_ein_pflichtbegriff_steht_nicht_zugleich_unter_den_randnotizen():
    g = graph(
        [person("p1"), term("t1", "Lehmhaus", 1), term("t2", "Earthship", 1)],
        [("p1", "t1"), ("p1", "t2")],
    )
    text = render_material(build_material(g))

    pflicht = text.split("Randnotizen")[0]
    rand = "Randnotizen" + text.split("Randnotizen")[1] if "Randnotizen" in text else ""

    assert "Lehmhaus" in pflicht and "Earthship" in pflicht
    # Der Kern: was oben Pflicht ist, darf unten nicht als Beiwerk stehen.
    assert "Lehmhaus" not in rand
    assert "Earthship" not in rand


def test_eine_randnotiz_die_keine_pflicht_ist_bleibt_stehen():
    """Die Gegenrichtung -- der Block darf nicht einfach verschwinden.

    Ohne diesen Test waere „alle Randnotizen weglassen" eine bestandene
    Loesung, und die Einmal-Nennungen, die NICHT Pflicht sind, waeren still
    aus dem Traum verschwunden.
    """
    nodes = [person(f"p{i}") for i in range(1, 4)]
    # Ein geteilter Begriff, damit die Pflichtliste nicht alles aufsaugt.
    nodes.append(term("t1", "Lehmbau", 3))
    nodes += [term(f"t{i}", f"Randbegriff {i}", 1, created_at=float(i)) for i in range(2, 8)]
    edges = [("p1", "t1"), ("p2", "t1"), ("p3", "t1")]
    edges += [(f"p{(i % 3) + 1}", f"t{i}") for i in range(2, 8)]

    text = render_material(build_material(graph(nodes, edges)))
    assert "Randnotizen" in text, "der Block darf nicht komplett wegfallen"


# --- Zitate: nur die juengsten Personen (Birk, 2026-09-01) ------------------
#
# „zitat: nur von der letzten person mit rein nehmen. nicht alle zitate. oder
# nur von den letzten drei personen." Bei 60 Personen waren alle Zitate 76 %
# des Materialblocks; bei dreien ist genau das die Stimme, auf die das Bild
# reagieren soll.


def test_zitate_kommen_nur_von_den_juengsten_personen():
    nodes = [
        {**person("alt1"), "created_at": 10.0},
        {**person("alt2"), "created_at": 20.0},
        {**person("neu1"), "created_at": 30.0},
        {**person("neu2"), "created_at": 40.0},
        {**person("neu3"), "created_at": 50.0},
        term("t1", "Lehmhaus", 5),
    ]
    edges = [(p, "t1") for p in ("alt1", "alt2", "neu1", "neu2", "neu3")]
    quotes = [
        ("alt1", "Satz der aeltesten Person"),
        ("alt2", "Satz der zweitaeltesten"),
        ("neu1", "Satz von neu1"),
        ("neu2", "Satz von neu2"),
        ("neu3", "Satz von neu3"),
    ]
    text = render_material(build_material(graph(nodes, edges, quotes)), include_quotes=True)

    assert "Satz von neu1" in text
    assert "Satz von neu2" in text
    assert "Satz von neu3" in text
    assert "Satz der aeltesten Person" not in text
    assert "Satz der zweitaeltesten" not in text


def test_zitate_bleiben_auf_wunsch_ganz_draussen():
    g = graph(
        [person("p1"), term("t1", "Lehmhaus", 1)],
        [("p1", "t1")],
        [("p1", "Ein Satz")],
    )
    assert "Ein Satz" not in render_material(build_material(g), include_quotes=False)
