"""Merging: embedding preselection, LLM judgement and naming (spec 6.2).

One LLM call per interview, roughly 50 over the whole festival. Decisions are
persisted as aliases and a decision log; they are never re-derived, so the
graph cannot wobble in live operation.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

from pydantic import BaseModel

from kg.embeddings import Embedder, nearest

MERGE_SYSTEM = """\
Du pflegst die Begriffsknoten eines wachsenden Beziehungsgraphen über Bauen, \
Stadt und Zukunft. Aus einem neuen Interview kommen NEUE Begriffe. Dazu \
bekommst du je Begriff die ähnlichsten BESTEHENDEN Knoten.

Wo vorhanden, steht neben jedem Begriff die STELLE, an der er im Gespräch \
fiel. Entscheide an ihr, nicht am Etikett: Zwei Wörter sehen sich schnell \
ähnlich, zwei Sätze aus zwei Gesprächen seltener. Die Probe: Würden die \
beiden Menschen, die das gesagt haben, einander zustimmen, dass sie dasselbe \
meinten? „Ich würde gerne in einem Lehmhaus leben" und „mehr so Tiny House \
Wohnen" sind beide Wünsche ans Wohnen — der eine spricht vom BAUSTOFF, der \
andere von der GRÖSSE. Das sind zwei Knoten.

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


#: Quote characters the model may wrap a label in — the German pair the merge
#: prompt itself uses, plus the ASCII and English forms it sometimes swaps in.
_QUOTE_CHARS = "„“”\"'"

#: Two garbled forms of a `\uXXXX` unicode escape observed in real judge
#: output (out/sim19c/sim.db): a literal backslash before the "u", or — when
#: the model instead typed a spurious "r" between the backslash and the "u"
#: ("\r" + "u201e") — the actual carriage-return control character JSON
#: decoded that "\r" into, immediately followed by the literal "uXXXX" text.
#: Exactly 4 hex digits is required, so this never matches a truncated or
#: non-hex lookalike, and `chr()` of any 4-hex value never raises.
_ESCAPE_RE = re.compile(r"[\\\r]u([0-9a-fA-F]{4})")


def unquote_label(label: str) -> str:
    """Strip a surrounding quote pair from a label the model produced.

    `build_merge_prompt` renders every label as „Label“, and the model answers
    in the notation it was shown: members come back with the quote characters
    attached. Looked up verbatim they match nothing, so the group resolves to
    no existing term and the merge silently does nothing (Task 19).

    The model also sometimes echoes a label with a literal, undecoded unicode
    escape instead of the character itself (Task: merge bugs). Escapes are
    decoded FIRST, before whitespace/quote stripping: a decoded escape can
    itself be a „ or " character sitting right at the boundary, and only the
    quote-stripping loop below removes those — reversing the order would
    leave them stuck on the label.

    Every model-produced label passes through here BEFORE it is used — for the
    lookup and for the alias that is written. One notion, one function:
    detection and storage cannot diverge.
    """
    text = _ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), label)
    text = text.strip()
    while len(text) >= 2 and text[0] in _QUOTE_CHARS and text[-1] in _QUOTE_CHARS:
        text = text[1:-1].strip()
    return text


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
    new_labels: Sequence[str],
    candidates: dict[str, list[str]],
    merge_style: str,
    belege: dict[str, str] | None = None,
    belege_bestehend: dict[str, str] | None = None,
) -> str:
    """🔴 Seit 2026-09-02 mit den BELEGSTELLEN (Birk).

    Bis dahin sah der Richter nur Etiketten: „Lehmhaus" gegen „Tiny House
    Wohnen", ohne jeden Kontext. An den echten Interviews desselben Tages hat
    er daraufhin „Lehmhaus" und „Earthship" in „Tiny House Wohnen" gelegt --
    eine Bauweise und eine Groesse in einen Topf -- und ein andermal
    „Naturverbundenes Wohnen" gleich mit.

    Der Massstab im Prompt war dabei nicht zu lasch („Fasse nur zusammen, was
    wirklich dasselbe meint"). Er half nur nicht, weil dem Richter das Material
    fehlte, an dem er es haette entscheiden koennen. Zwei Woerter sehen sich
    schnell aehnlich; zwei Saetze aus zwei Gespraechen tun das seltener.

    Beide Seiten, nicht nur die neue: Sonst vergleicht er eine Textstelle mit
    einem blossen Wort und entscheidet wieder am Etikett. Fehlt eine Stelle
    (aeltere Kanten haben keine), bleibt die Zeile wie vorher -- die Angabe ist
    eine Hilfe, keine Bedingung.
    """
    belege = belege or {}
    belege_bestehend = belege_bestehend or {}
    lines = [f"Maßstab für das Zusammenfassen: {merge_style}", "", "NEUE BEGRIFFE:"]
    for label in new_labels:
        stelle = (belege.get(label) or "").strip()
        kopf = f"- „{label}“"
        if stelle:
            kopf += f' — gesagt wurde: „{stelle}“'
        lines.append(kopf)
        neighbours = candidates.get(label) or []
        if not neighbours:
            lines.append("  ähnliche bestehende Knoten: (keine)")
            continue
        lines.append("  ähnliche bestehende Knoten:")
        for n in neighbours:
            n_stelle = (belege_bestehend.get(n) or "").strip()
            if n_stelle:
                lines.append(f'    · „{n}“ — dort wurde gesagt: „{n_stelle}“')
            else:
                lines.append(f'    · „{n}“')
    return "\n".join(lines)


def decide_merges(
    llm,
    new_labels: Sequence[str],
    candidates: dict[str, list[str]],
    merge_style: str,
    belege: dict[str, str] | None = None,
    belege_bestehend: dict[str, str] | None = None,
) -> MergeResult:
    if not new_labels:
        return MergeResult(groups=[])
    return llm.parse(
        system=MERGE_SYSTEM,
        user=build_merge_prompt(
            new_labels, candidates, merge_style, belege, belege_bestehend
        ),
        output_model=MergeResult,
    )


def apply_merges(
    store, person_id: str, new_labels: Sequence[str], result: MergeResult, at: float
) -> list[str]:
    """Persist the decision and return one term id per input label, in order.

    Runs as a single `store.transaction()`: a crash partway through must
    leave no rename, fold or alias committed without the matching decision
    log, or the graph state could never be reproduced or undone.
    """
    resolved: dict[str, str] = {}
    claimed: set[str] = set()  # members an earlier group in this call already used

    with store.transaction():
        for group in result.groups:
            # The model echoes the prompt's „…“ notation back at us. Normalise
            # once, here, and use the result for the lookup AND the alias write
            # below — a quoted surface form matches no stored label and would
            # turn every merge into a silent no-op (Task 19).
            canonical_label = unquote_label(group.canonical_label)
            members = list(dict.fromkeys(filter(None, map(unquote_label, group.members))))
            # Group 1's aliases are visible to group 2 within the same call.
            # A member an earlier group already claimed must not silently
            # drag this group's *other* members along with it — drop it here
            # and let it resolve on its own (standalone) below.
            members = [m for m in members if m not in claimed]
            # The judge sometimes states a merge with the EXISTING node as
            # canonical_label and only the NEW term as the lone member —
            # {"canonical_label": "Bodenpolitik", "members": ["Bodenpolitik
            # und Baurecht"]} — instead of listing both as members. That is a
            # complete merge statement, not an incomplete one, PROVIDED
            # canonical_label actually names something that already exists;
            # otherwise it is just a single term standing for itself (the
            # system prompt tells the judge to omit those), and it must fall
            # through to get_or_create_term below like any other unmatched
            # label — no merge into the blue. A group that shrank to one
            # member via the claimed-filter above is judged by the exact same
            # rule: claiming happens first, so the meaning of "one member"
            # never depends on how many members the group started with.
            canonical_term = None
            if len(members) == 1:
                canonical_term = store.find_term_by_alias(
                    canonical_label
                ) or store.get_term_by_label(canonical_label)
                if canonical_term is None:
                    continue
            elif len(members) < 2:
                continue
            # A label of nothing but quotes strips to "" — keep the judgement,
            # drop the unusable name and let the group be called after a member.
            canonical_label = canonical_label or members[0]

            existing_ids: list[str] = []
            for member in members:
                term = store.find_term_by_alias(member) or store.get_term_by_label(member)
                if term is not None and term.id not in existing_ids:
                    existing_ids.append(term.id)

            # The model was told to prefer an existing formulation, so the
            # canonical label itself may already belong to some OTHER term
            # (`term.label` is UNIQUE). Treat that as a merge with that term
            # too, rather than letting the rename below raise.
            collision = store.get_term_by_label(canonical_label)
            if collision is not None and collision.id not in existing_ids:
                existing_ids.append(collision.id)
            # canonical_term may have resolved via an ALIAS rather than the
            # term's current label, which the collision check above (exact
            # label match only) would miss entirely.
            if canonical_term is not None and canonical_term.id not in existing_ids:
                existing_ids.append(canonical_term.id)

            if existing_ids:
                # Every existing term the group touches folds onto one
                # winner — the loser's edges and aliases move over, nothing
                # is left stranded on an unreachable second node.
                winner_id, *loser_ids = existing_ids
                # D5 (Task 19c): `store.rename_term` refuses to rename a node
                # two people already share. The merge and its naming are ONE
                # decision, so the lock is judged against the winner's mention
                # count from BEFORE the fold — two nodes of one person each may
                # still name the group they form, while a node that was already
                # shared keeps its name no matter what the group adds to it.
                # The rename itself has to come after the fold: the group is
                # told to prefer an existing formulation, so the chosen name is
                # often a loser's label, and `term.label` is UNIQUE.
                mentions_before_merge = store.mention_count(winner_id)
                for loser_id in loser_ids:
                    store.fold_term(loser_id, winner_id)
                store.rename_term(
                    winner_id, canonical_label, mentions_before_merge=mentions_before_merge
                )
                # A refused rename costs the visible label only: the fold above
                # happened, and the name the judge chose stays reachable as a
                # synonym, so the next interview phrasing it that way lands here.
                store.add_alias(winner_id, canonical_label)
            else:
                winner_id = store.get_or_create_term(canonical_label, created_at=at).id

            for member in members:
                store.add_alias(winner_id, member)
                resolved[member] = winner_id
                claimed.add(member)

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
