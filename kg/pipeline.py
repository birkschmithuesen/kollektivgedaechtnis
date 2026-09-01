"""Per-interview condensation (spec 6.1). Deterministic, plain Python, no agent."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from kg.export import write_graph_json
from kg.extraction import extract
from kg.merging import apply_merges, build_candidates, decide_merges, split_known
from kg.segmentation import strip_stop_phrases

log = logging.getLogger(__name__)


@dataclass
class ProcessResult:
    person_id: str
    status: str
    term_ids: list[str] = field(default_factory=list)
    transcript: str = ""


def process_interview(
    store,
    cfg,
    llm,
    embedder,
    transcript_log,
    person_id: str,
    started_at: float,
    stopped_at: float,
    *,
    cut_end: float | None = None,
) -> ProcessResult:
    store.set_person_status(person_id, "processing")

    # 1. Cut between the markers. Only the Telegram-text stop path extends the
    # end past stopped_at, to the final that landed inside its settle window
    # (kg.core.settle_cut_end); every other path leaves cut_end at stopped_at.
    raw = transcript_log.text_between(started_at, stopped_at if cut_end is None else cut_end)
    text = strip_stop_phrases(raw, cfg.stop_phrases, cfg.wake_word)
    # The mechanical stripper only knows the CONFIGURED phrases, so a freely
    # worded stop that only the LLM gate recognised (reason "spoken_llm",
    # kg.session) survives this line — deliberately. Step 2 below removes it:
    # extract() puts `interview_end_index` where the interview ends in
    # substance and terms are taken from BEFORE that index only, which is the
    # same mechanism that already drops every farewell, bit of smalltalk and
    # next person's voice at the tail of the cut. Nothing extra is built here;
    # a second, redundant cut would only cost content when it guessed wrong.

    if not text.strip():
        store.set_person_transcript(person_id, "")
        store.set_person_status(person_id, "done")
        write_graph_json(store, cfg.graph_json_path)
        return ProcessResult(person_id, "done", [], "")

    try:
        # 2.+3. Find the real end and extract, in one call.
        result = extract(llm, text, cfg.terms_per_interview)
        transcript = text[: result.interview_end_index].strip() or text.strip()
        labels = [t.label.strip() for t in result.terms if t.label.strip()]

        # 4. Merge: persisted decisions first, one LLM call for the rest.
        known, unknown = split_known(store, labels)
        if unknown:
            candidates = build_candidates(
                unknown, [t.label for t in store.list_terms()], embedder, cfg.merge_neighbours
            )
            decision = decide_merges(llm, unknown, candidates, cfg.merge_style)
            resolved = dict(zip(unknown, apply_merges(store, person_id, unknown, decision, stopped_at)))
        else:
            resolved = {}
        term_ids: list[str] = []
        for label in labels:
            term_id = known.get(label) or resolved.get(label)
            if term_id and term_id not in term_ids:
                term_ids.append(term_id)

        # 5. Persist.
        store.set_person_transcript(person_id, transcript)
        for term_id in term_ids:
            store.add_edge(person_id, term_id, created_at=stopped_at)
        # result.quotes has at most one entry — extract() caps it — so this
        # writes at most one quote per person.
        for quote in result.quotes:
            if quote.text.strip():
                store.add_quote(person_id, quote.text.strip(), created_at=stopped_at)
        # Der Name genauso: höchstens einer, und nur wenn wirklich etwas
        # dasteht. Ein leerer Treffer wird gar nicht erst geschrieben, damit
        # eine Person ohne Vorstellung nicht mit einem leeren Namen endet,
        # sondern ohne Namen.
        for name in result.names:
            if name.text.strip():
                store.set_person_name(person_id, name.text.strip())

        # Kein Begriff, kein Zitat, kein Name: die Person erscheint als leere
        # Scheibe an der Wand. Der Status bleibt „done" — die Analyse IST
        # gelaufen, und ein „failed" würde eine Person, die schlicht nichts
        # Verwertbares gesagt hat, als Systemfehler ausweisen. Aber es darf
        # nicht mehr lautlos passieren: bis heute war der sichtbarste Fehler
        # der Station der einzige, den hinterher niemand nachzählen konnte
        # (gemessen 2026-09-01: 17 von 30 Läufen leer, docs/STAND.md 2h).
        # Nur Kennzahlen ins Log, kein Transkripttext — die Zeile landet in
        # einer Datei, die nicht unter der PII-Disziplin der Transkripte steht.
        if not term_ids and not result.quotes and not result.names:
            log.warning(
                "interview %s produced nothing: no term, no quote, no name from %s chars",
                person_id,
                len(transcript),
            )

        store.set_person_status(person_id, "done")
        status = "done"
    except Exception as exc:  # a bad LLM turn must never stop the station
        log.error("interview %s failed: %s", person_id, exc)
        store.set_person_status(person_id, "failed")
        term_ids, transcript, status = [], text.strip(), "failed"
        store.set_person_transcript(person_id, transcript)

    write_graph_json(store, cfg.graph_json_path)
    return ProcessResult(person_id, status, term_ids, transcript)
