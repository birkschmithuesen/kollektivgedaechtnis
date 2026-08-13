"""Merging: embedding preselection, LLM judgement and naming (spec 6.2).

One LLM call per interview, roughly 50 over the whole festival. Decisions are
persisted as aliases and a decision log; they are never re-derived, so the
graph cannot wobble in live operation.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic import BaseModel

from kg.embeddings import Embedder, nearest

MERGE_SYSTEM = """\
Du pflegst die Begriffsknoten eines wachsenden Beziehungsgraphen über Bauen, \
Stadt und Zukunft. Aus einem neuen Interview kommen NEUE Begriffe. Dazu \
bekommst du je Begriff die ähnlichsten BESTEHENDEN Knoten.

Entscheide:
- Welche neuen Begriffe meinen dasselbe wie ein bestehender Knoten?
- Welche neuen Begriffe meinen untereinander dasselbe?
- Wie heißt der gemeinsame Knoten?

Der Name des gemeinsamen Knotens ist die eigentliche Arbeit: er steht später \
auf der Wand. Er muss konkret, bildhaft und höchstens vier Wörter lang sein. \
Wähle bevorzugt eine der vorhandenen Formulierungen; erfinde nur dann eine \
neue, wenn keine der Formulierungen die Gruppe gut trifft. Steige NIE auf \
einen Oberbegriff hoch („Nachhaltigkeit", „Digitalisierung") — das zerstört \
das Bild.

Gib nur Gruppen mit mindestens zwei Mitgliedern zurück. Begriffe, die für sich \
stehen, lässt du weg.

Antworte ausschließlich im geforderten JSON-Schema.
"""


class MergeGroup(BaseModel):
    canonical_label: str
    members: list[str]


class MergeResult(BaseModel):
    groups: list[MergeGroup]


def split_known(store, labels: Sequence[str]) -> tuple[dict[str, str], list[str]]:
    """Labels with a persisted decision resolve directly; the rest go to the LLM."""
    known: dict[str, str] = {}
    unknown: list[str] = []
    for label in labels:
        term = store.find_term_by_alias(label)
        if term is not None:
            known[label] = term.id
        elif label not in unknown:
            unknown.append(label)
    return known, unknown


def build_candidates(
    new_labels: Sequence[str],
    existing_labels: Sequence[str],
    embedder: Embedder,
    k: int,
) -> dict[str, list[str]]:
    if not new_labels:
        return {}
    if not existing_labels:
        return {label: [] for label in new_labels}
    existing_vectors = dict(zip(existing_labels, embedder.embed(list(existing_labels))))
    new_vectors = embedder.embed(list(new_labels))
    return {
        label: nearest(vector, existing_vectors, k)
        for label, vector in zip(new_labels, new_vectors)
    }


def build_merge_prompt(
    new_labels: Sequence[str], candidates: dict[str, list[str]], merge_style: str
) -> str:
    lines = [f"Maßstab für das Zusammenfassen: {merge_style}", "", "NEUE BEGRIFFE:"]
    for label in new_labels:
        neighbours = candidates.get(label) or []
        suffix = ", ".join(f"„{n}“" for n in neighbours) if neighbours else "(keine)"
        lines.append(f"- „{label}“ — ähnliche bestehende Knoten: {suffix}")
    return "\n".join(lines)


def decide_merges(
    llm, new_labels: Sequence[str], candidates: dict[str, list[str]], merge_style: str
) -> MergeResult:
    if not new_labels:
        return MergeResult(groups=[])
    return llm.parse(
        system=MERGE_SYSTEM,
        user=build_merge_prompt(new_labels, candidates, merge_style),
        output_model=MergeResult,
    )


def apply_merges(
    store, person_id: str, new_labels: Sequence[str], result: MergeResult, at: float
) -> list[str]:
    """Persist the decision and return one term id per input label, in order."""
    resolved: dict[str, str] = {}

    for group in result.groups:
        members = [m for m in group.members if m]
        if not members:
            continue
        term = None
        for member in members:
            term = store.find_term_by_alias(member) or store.get_term_by_label(member)
            if term is not None:
                break
        if term is None:
            term = store.get_or_create_term(group.canonical_label, created_at=at)
        elif term.label != group.canonical_label:
            store.rename_term(term.id, group.canonical_label)
        for member in members:
            store.add_alias(term.id, member)
        for member in members:
            resolved[member] = term.id

    term_ids: list[str] = []
    for label in new_labels:
        term_id = resolved.get(label)
        if term_id is None:
            existing = store.find_term_by_alias(label)
            term = existing or store.get_or_create_term(label, created_at=at)
            term_id = term.id
            resolved[label] = term_id
        term_ids.append(term_id)

    store.record_merge_decision(
        person_id,
        json.loads(result.model_dump_json()) | {"labels": list(new_labels)},
        created_at=at,
    )
    return term_ids
