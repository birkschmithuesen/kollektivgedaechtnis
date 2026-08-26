"""graph.json -> the material stage 1 reasons over (spec §5.1).

Four rules, each with a reason that has to survive a later edit:

* **Weight by structure.** The numbers already exist in the payload, so nothing
  is computed on Tool 1's side. Frequently mentioned terms are dominant; single
  mentions are marginal detail, and are LABELLED as such in the rendered block
  so the model can place them as a detail rather than as a theme.
* **Quotes are in.** They are in `graph.json` for exactly this reason (T1§11
  stores them for Tool 2's benefit even though the wall never renders them).
* **Hidden nodes are out.** `hidden: true` is the operator's emergency exit on
  the wall (T1§8); something pulled from the wall must not reappear in the dream.
* **`min_mentions` is NOT applied.** That dial is the wall's legibility filter,
  not a statement about what was said. The dream reads everything and the
  weighting handles prominence.

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
        node.get("id"): node.get("label")
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

    weights = [TermWeight(terms[tid], count) for tid, count in counts.items()]
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


def render_material(material: Material) -> str:
    """The German block that goes into stage 1's user message.

    Nothing is truncated. At Tool 1's documented ceiling of ~50 persons (T1§2)
    this stays comfortably inside the model's window, and a silent cap would
    make the dream quietly stop reading the day's later interviews — the one
    failure this station cannot afford, because the strip is what makes drift
    visible.
    """
    blocks: list[str] = []

    if material.shared:
        lines = "\n".join(f"  {w.mentions}× {w.label}" for w in material.shared)
        blocks.append(
            "Geteilte Begriffe — die Zahl sagt, wie viele Menschen sie genannt "
            "haben. Was oft genannt wurde, beherrscht das Bild:\n" + lines
        )

    if material.marginal:
        lines = "\n".join(f"  {w.label}" for w in material.marginal)
        blocks.append(
            "Randnotizen — jede davon hat genau ein Mensch gesagt. Das sind "
            "Detail und Beiwerk, nicht Thema. Sie dürfen im Bild vorkommen, "
            "aber klein und am Rand:\n" + lines
        )

    if material.quotes:
        # Single-quoted f-string: the German quotation marks are literal text,
        # and a double-quoted one would end at the closing „ ".
        lines = "\n".join(f'  „{quote}"' for quote in material.quotes)
        blocks.append("Stimmen aus den Interviews, wörtlich:\n" + lines)

    header = (
        f"Der Graph umfasst {material.person_count} Menschen, "
        f"{material.term_count} Begriffe und {material.edge_count} Verbindungen."
    )
    return "\n\n".join([header, *blocks])


def contradiction_enabled(material: Material, threshold: int) -> bool:
    """Spec §5.1: below the threshold the contradiction instruction is dropped
    and stage 1 runs on weighting alone. With three interviews there are no real
    oppositions and the model would invent one."""
    return material.person_count >= threshold
