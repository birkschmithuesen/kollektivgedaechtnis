"""graph.json -> the material stage 1 reasons over (spec §5.1).

Four rules, each with a reason that has to survive a later edit:

* **Weight by structure.** The numbers already exist in the payload, so nothing
  is computed on Tool 1's side. Frequently mentioned terms are dominant; single
  mentions are marginal detail, and are LABELLED as such in the rendered block
  so the model can place them as a detail rather than as a theme.
* **Quotes are collected but not rendered.** They stay in `graph.json` and in
  `Material.quotes` (T1§11 stores them for Tool 2's benefit), but
  `render_material` leaves them out by default (decided 2026-08-28): on the
  wall only the terms are visible, quotes appear only when a visitor taps a
  person. At 60 people they were 76% of the material block for something
  invisible in the room — the same argument spec §10 uses against
  graph-driven style. `include_quotes=True` exists for a side-by-side
  comparison run, not for production.
* **Hidden nodes are out.** `hidden: true` is the operator's emergency exit on
  the wall (T1§8); something pulled from the wall must not reappear in the
  dream.
* **`min_mentions` is NOT applied — Tool 1 and Tool 2 share the SAME rule, but
  are NOT coupled.** Both now read „all shared terms, topped up with the most
  recent single mentions" (see `select_marginal` below) — but each computes it
  independently, from its own two constants, not from one shared dial. This is
  deliberate, not an oversight to "clean up" later: the wall's `min_mentions`
  is a **physical** limit (screen area, font size) that an operator turns
  while thinking about legibility, not about content. If it also controlled
  what the dream reads, an operator adjusting font size at 14:00 would
  unknowingly change what the images are made from, and two exhibition days
  would stop being comparable. The dream's cap (`SINGLE_MENTION_BUDGET`,
  `SHARED_TERMS_SATURATION` below) is a **content** limit — keeping the model
  from drowning in footnotes — and is a property of the condensing procedure,
  not a knob either tool's operator turns.

* **A second axis: recency (added 2026-08-29).** The blocks above rank purely
  by final mention count, which encodes no order in time — at the end of the
  day seven mentions are seven mentions, whichever interview said the
  seventh one last, and a term that started late still catches up as more
  people repeat it. That is NOT what today's prompt gets wrong. The problem
  is a DELAY effect: at the moment THIS dream is rendered, a term that was
  first said in the interview that just finished has whatever count it has
  accumulated so far — usually one or two — and cannot compete with a term
  that has been repeated all morning. The dream can therefore fail to react
  to the interview that produced it, which the two screens standing side by
  side make visible. The fix chosen (2026-08-29, over multiplying the count
  by an aging factor — rejected because it would put an invented number in
  the prompt instead of the honest one) is `select_recent`/the „Zuletzt
  gesagt" block below: a second, independent block, unchanged mention counts,
  drawn from shared AND marginal terms alike so a just-said single mention
  that could never out-weigh the count-based block still gets to appear.

One thing the spec does not spell out and the code must: the payload's
`mentions` counts edges from hidden persons too, so it is RECOMPUTED here from
the surviving edges. Reading it off the node would leave a hidden visitor's
voice weighting the dream they were pulled out of.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class TermWeight:
    label: str
    mentions: int
    #: The term node's `created_at` (0.0 if the payload did not carry a valid
    #: one) — the only thing `select_marginal` below uses to break ties among
    #: single mentions: the newest interview must be the one represented.
    created_at: float = 0.0


@dataclass(frozen=True)
class Material:
    person_count: int
    term_count: int
    edge_count: int
    generated_at: float | None
    #: Said by two or more people, most-said first.
    shared: list[TermWeight]
    #: Said by exactly one person. Detail, not theme.
    marginal: list[TermWeight]
    quotes: list[str]


# Gefahren am 2026-08-28 (`sim.dream_calibrate terms`,
# `out/calibrate-terms.txt`): vier Graphgrößen × N ∈ {10, 20, 30} × X ∈ {15,
# 25, 40}, 36 echte Stufe-1-Läufe. Befund: Ab 30 Personen ist die Wahl
# WIRKUNGSLOS — dort liegen 25 bzw. 49 geteilte Begriffe vor, also über jedem
# geprüften X, und es kommen ohnehin null Einmal-Nennungen mehr durch. Ein
# Unterschied entsteht nur bei 3 und 10 Personen, und dort war unter allen
# neun Kombinationen kein Qualitätsunterschied lesbar (die Sätze sind
# durchweg brauchbar, sie greifen nur andere Randbegriffe auf).
#
# Deshalb bewusst NICHT weiter kalibriert: Die Werte sind gesetzt, nicht
# gemessen, weil die Messung gezeigt hat, dass es hier nichts zu messen gibt.
# N=20 ist die Mitte des geprüften Bereichs; X=25 ist die Zahl geteilter
# Begriffe, die der reale Graph bei 30 Personen erreicht — also etwa zur
# Tagesmitte, ab wann der Traum nur noch aus Geteiltem entsteht.
# Wer sie später ändert, sollte den Lauf wiederholen statt zu raten.
SINGLE_MENTION_BUDGET = 20  # N
SHARED_TERMS_SATURATION = 25  # X

#: How many of the newest terms go into the „Zuletzt gesagt" block (module
#: docstring). Deliberately small: an accent, not a second theme list — too
#: many and it competes with the weighting it is not meant to override.
RECENT_TERMS = 5


def _empty_material() -> Material:
    return Material(0, 0, 0, None, [], [], [])


def _as_list(value) -> list:
    """Coerce whatever `graph.get(key, ())` returned into a list to iterate.

    `kg2.graph_client.fetch_graph` only validates that `version`, `nodes` and
    `edges` are present — never their value types (see review of an earlier
    task, and `kg2.trigger.absorbed_persons`, hardened against exactly this).
    A payload can therefore reach here with `nodes`, `edges` or `quotes` being
    a string, a dict, or anything else non-list. Treating that as „nothing
    there" rather than raising is what lets this module degrade to empty
    material instead of crashing whatever calls it.
    """
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, dict)):
        return []
    return list(value)


def build_material(graph: dict | None) -> Material:
    if not isinstance(graph, dict):
        return _empty_material()

    nodes = _as_list(graph.get("nodes", ()))
    # `.get("id")` rather than `node["id"]`: a person/term dict with no `id`
    # (or no `label`) is exactly the malformed shape this function promises to
    # survive. The `isinstance(..., str)` checks do double duty, same as in
    # `kg2.trigger.absorbed_persons`: a Tool 1 id/label is always a string, so
    # anything else is dropped before it can reach a set or dict key — an
    # unhashable value (a list) would otherwise crash the comprehension below,
    # and a hashable-but-wrong-type one (an int label) would later make
    # `weights.sort()` crash by comparing a str to it.
    persons = {
        node.get("id")
        for node in nodes
        if isinstance(node, dict)
        and node.get("type") == "person"
        and not node.get("hidden")
        and isinstance(node.get("id"), str)
    }
    terms = {
        node.get("id"): (node.get("label"), node.get("created_at"))
        for node in nodes
        if isinstance(node, dict)
        and node.get("type") == "term"
        and not node.get("hidden")
        and isinstance(node.get("id"), str)
        and isinstance(node.get("label"), str)
    }

    counts: dict[str, int] = {}
    edge_count = 0
    for edge in _as_list(graph.get("edges", ())):
        if not isinstance(edge, dict):
            continue
        source, target = edge.get("source"), edge.get("target")
        # `source`/`target` must themselves be checked before the `in` test
        # below: set/dict membership hashes its argument, so an unhashable
        # source (e.g. a list) would raise here even though `persons`/`terms`
        # are already guaranteed to contain only strings.
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        if source in persons and target in terms:
            counts[target] = counts.get(target, 0) + 1
            edge_count += 1

    weights = []
    for tid, count in counts.items():
        label, created_at = terms[tid]
        if not isinstance(created_at, (int, float)):
            created_at = 0.0
        weights.append(TermWeight(label, count, created_at))
    # Descending by count, then by label: two runs over the same graph must
    # produce the same prompt, or the record in spec §5.3 explains nothing.
    weights.sort(key=lambda w: (-w.mentions, w.label))

    quotes = [
        quote["text"]
        for quote in _as_list(graph.get("quotes", ()))
        if isinstance(quote, dict)
        # Same hashability landmine as the edge loop above: `in persons` hashes
        # `person_id`, so an unhashable value (a list) must be filtered first.
        and isinstance(quote.get("person_id"), str)
        and quote.get("person_id") in persons
        and "text" in quote
    ]

    generated_at = graph.get("generated_at")
    if not isinstance(generated_at, (int, float)):
        generated_at = None

    return Material(
        person_count=len(persons),
        term_count=len(weights),
        edge_count=edge_count,
        generated_at=generated_at,
        shared=[w for w in weights if w.mentions >= 2],
        marginal=[w for w in weights if w.mentions == 1],
        quotes=quotes,
    )


def select_marginal(
    material: Material,
    *,
    budget: int = SINGLE_MENTION_BUDGET,
    saturation: int = SHARED_TERMS_SATURATION,
) -> list[TermWeight]:
    """The single mentions that make it into the prompt (decided 2026-08-28).

    All shared terms always go in — there is no cap on them, unlike the wall.
    Single mentions are topped up on a gliding budget that shrinks linearly to
    zero as the number of shared terms grows from 0 to `saturation`, so the
    transition falls out of the graph itself rather than a threshold or a
    stored day-part. The newest single mentions are kept, not the oldest, so
    the interview that just finished is guaranteed to be represented.
    """
    allowed = round(budget * max(0, 1 - len(material.shared) / saturation))
    if allowed <= 0:
        return []
    newest_first = sorted(material.marginal, key=lambda w: (-w.created_at, w.label))
    return newest_first[:allowed]


def select_recent(material: Material, *, count: int = RECENT_TERMS) -> list[TermWeight]:
    """The terms behind the „Zuletzt gesagt" block (module docstring).

    Drawn from `shared` AND `marginal` together — the recency axis is
    independent of the weighting axis, so a term that just entered the graph
    with a single mention belongs here exactly as much as one repeated all
    day. `shared` and `marginal` never overlap (a term is one or the other by
    construction), so this cannot itself produce a duplicate; the same term
    reappearing in BOTH this block and the weighted block above is expected,
    not a bug — it is how one gets doubly emphasised.
    """
    if count <= 0:
        return []
    newest_first = sorted(
        material.shared + material.marginal, key=lambda w: (-w.created_at, w.label)
    )
    return newest_first[:count]


def render_material(
    material: Material,
    *,
    include_quotes: bool = False,
    single_mention_budget: int = SINGLE_MENTION_BUDGET,
    shared_terms_saturation: int = SHARED_TERMS_SATURATION,
    recent_terms: int = RECENT_TERMS,
) -> str:
    """The German block that goes into stage 1's user message.

    Shared terms are never truncated. At Tool 1's documented ceiling of ~50
    persons (T1§2) this stays comfortably inside the model's window, and a
    silent cap would make the dream quietly stop reading the day's later
    interviews — the one failure this station cannot afford, because the
    strip is what makes drift visible. Single mentions ARE limited, by
    `select_marginal` above — on purpose, see the module docstring.

    `single_mention_budget`/`shared_terms_saturation`/`recent_terms` default
    to this module's constants and only exist as parameters so
    `sim.dream_calibrate terms`/`recency` can try other values (including 0,
    to switch the recency block off for comparison) without duplicating this
    function.
    """
    blocks: list[str] = []

    if material.shared:
        lines = "\n".join(f"  {w.mentions}× {w.label}" for w in material.shared)
        blocks.append(
            "Geteilte Begriffe — die Zahl sagt, wie viele Menschen sie genannt "
            "haben. Was oft genannt wurde, beherrscht das Bild:\n" + lines
        )

    marginal = select_marginal(
        material, budget=single_mention_budget, saturation=shared_terms_saturation
    )
    if marginal:
        lines = "\n".join(f"  {w.label}" for w in marginal)
        blocks.append(
            "Randnotizen — jede davon hat genau ein Mensch gesagt. Das sind "
            "Detail und Beiwerk, nicht Thema. Sie dürfen im Bild vorkommen, "
            "aber klein und am Rand:\n" + lines
        )

    recent = select_recent(material, count=recent_terms)
    if recent:
        lines = "\n".join(f"  {w.label}" for w in recent)
        blocks.append(
            "Zuletzt gesagt — die jüngsten Begriffe aus den letzten Interviews, "
            "unabhängig davon wie oft sie insgesamt genannt wurden. Mindestens "
            "einer davon soll im Bild vorkommen:\n" + lines
        )

    if include_quotes and material.quotes:
        # Single-quoted f-string: the German quotation marks are literal text,
        # and a double-quoted one would end at the closing „ ".
        lines = "\n".join(f'  „{quote}"' for quote in material.quotes)
        blocks.append("Stimmen aus den Interviews, wörtlich:\n" + lines)

    return "\n\n".join(blocks)
