"""Per-interview condensation (spec 6.1). Deterministic, plain Python, no agent."""

from __future__ import annotations

import json

import logging
from dataclasses import dataclass, field

from kg.export import write_graph_json
from kg.widerspruch import finde_widersprueche
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


def _aktualisiere_widersprueche(store, llm) -> None:
    """Die Widerspruchsliste neu bestimmen und ablegen.

    Wirft nie und schreibt nur bei Erfolg: Eine leere Antwort — das Modell hat
    keinen gefunden, der Anbieter war weg — darf die Liste nicht löschen, die
    seit dem letzten Mal an der Wand steht.
    """
    # 🔴 FESTGENAGELT (Birk, 2026-09-03, gegen Ende des zweiten Tages: „die
    # drei widersprüche vorher fand ich besser. bringe sie zurück. fixiere sie.
    # es werden keine neuen interviews mehr kommen").
    #
    # Der Aufruf sucht bei jedem Interview neu, und das Ergebnis fällt jedes
    # Mal etwas anders aus — an einem laufenden Tag ist das richtig, am Ende
    # nicht mehr: Dann steht eine Auswahl an der Wand, die jemand angesehen und
    # für gut befunden hat, und die soll bleiben.
    #
    # Ein Schalter in den Einstellungen und keine auskommentierte Zeile: Wer
    # ihn auf 0 setzt, bekommt das alte Verhalten zurück, ohne Code anzufassen.
    if store.get_setting("widersprueche_fixiert", "0") == "1":
        log.info("Widersprüche sind festgenagelt — keine Neuberechnung")
        return
    try:
        etikett = {t.id: t.label for t in store.list_terms() if not t.hidden}
        namen = {p.id: (p.name or "") for p in store.list_persons() if not p.hidden}
        stimmen: dict[str, list[tuple[str, str]]] = {}
        for kante in store.list_edges():
            if kante.term_id not in etikett or kante.person_id not in namen:
                continue
            if kante.evidence:
                stimmen.setdefault(kante.term_id, []).append(
                    (namen[kante.person_id], kante.evidence)
                )
        begriffe = [
            {"label": etikett[tid], "stimmen": liste} for tid, liste in stimmen.items()
        ]
        paare = finde_widersprueche(llm, begriffe)
        if paare:
            store.set_setting("widersprueche", json.dumps(paare, ensure_ascii=False))
            log.info("Widersprüche aktualisiert: %d Paare", len(paare))
    except Exception as fehler:  # noqa: BLE001 — siehe Docstring
        log.warning("Widersprüche nicht aktualisierbar: %s", fehler)


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
        # 🔴 DER VOLLE TEXT WIRD GESPEICHERT (Birk, 2026-09-02). Vorher stand
        # hier `text[: result.interview_end_index]` — das gespeicherte
        # Transkript endete also dort, wo das Modell das Gespraech fuer beendet
        # hielt.
        #
        # Was das kostete, zeigt Steffen (p3): Sein Transkript bricht mitten im
        # Wort ab („also aus historischer Sicht tatsä"), 1490 Zeichen fuer ein
        # fuenfminuetiges Gespraech, davon die Haelfte Foto-Gefummel. Seine
        # Antworten sind darin gar nicht mehr enthalten — obwohl die Auswertung
        # sie gesehen und ihre Begriffe daraus gezogen hat. Von 91 Belegstellen
        # liessen sich 26 im gespeicherten Transkript nicht wiederfinden, und
        # das war der Grund.
        #
        # Der Index bleibt wirksam, wo er hingehoert: `extract()` wendet ihn
        # INTERN an — Begriffe und Zitat kommen nur von davor. Diese Zeile
        # betraf allein den BELEG, und ein Beleg, der die Aussage nicht mehr
        # enthaelt, ist keiner. `interview_end_index` ist ausserdem instabil
        # (docs/STAND.md §2h), also raten wir hier nicht mit.
        transcript = text.strip()
        labels = [t.label.strip() for t in result.terms if t.label.strip()]
        # 🔴 Die Belegstelle je Begriff aufheben (Birk, 2026-09-02). Das Modell
        # liefert sie laengst -- `ExtractedTerm.evidence`, im Prompt verlangt
        # als „die kurze Textstelle, auf die sich der Begriff stuetzt" -- und
        # bis heute wurde sie gelesen und weggeworfen. Ohne sie bekommt der
        # Traum nur das Etikett: Aus „Ich hoffe, dass alle
        # Rohstoffabhaengigkeiten von der KI geplant werden" wurde der Begriff
        # „Rohstoffabhaengigkeiten", und das Bild malte Faesser auf einem
        # Containerterminal -- die Sache war weg, das Wort geblieben.
        #
        # Nach LABEL geschluesselt und nicht nach Reihenfolge: Die Zuordnung
        # unten laeuft ueber `labels`, und ein Begriff kann durch die
        # Zusammenfuehrung auf eine andere Kennung zeigen als den Text, unter
        # dem er genannt wurde.
        belege = {
            t.label.strip(): (t.evidence or "").strip()
            for t in result.terms
            if t.label.strip()
        }

        # 4. Merge: persisted decisions first, one LLM call for the rest.
        known, unknown = split_known(store, labels)
        if unknown:
            candidates = build_candidates(
                unknown, [t.label for t in store.list_terms()], embedder, cfg.merge_neighbours
            )
            # 🔴 Die Belegstellen BEIDER Seiten mitgeben (2026-09-02). Ohne
            # sie entscheidet der Richter am Etikett und legt „Lehmhaus" zu
            # „Tiny House Wohnen" — gemessen an den echten Interviews dieses
            # Tages. Fuer die bestehenden Knoten wird je eine Stelle geholt;
            # die erste genuegt, sie soll den Knoten kenntlich machen, nicht
            # ihn ausmessen.
            bestehende_belege: dict[str, str] = {}
            labels_je_term = {term.id: term.label for term in store.list_terms()}
            for kante in store.list_edges():
                marke = labels_je_term.get(kante.term_id)
                if marke and kante.evidence and marke not in bestehende_belege:
                    bestehende_belege[marke] = kante.evidence
            decision = decide_merges(
                llm, unknown, candidates, cfg.merge_style,
                belege={label: belege.get(label, "") for label in unknown},
                belege_bestehend=bestehende_belege,
            )
            resolved = dict(zip(unknown, apply_merges(store, person_id, unknown, decision, stopped_at)))
        else:
            resolved = {}
        term_ids: list[str] = []
        beleg_je_term: dict[str, str] = {}
        for label in labels:
            term_id = known.get(label) or resolved.get(label)
            if term_id and term_id not in term_ids:
                term_ids.append(term_id)
                # Der erste gewinnt: Nennt jemand zwei Woerter, die auf
                # denselben Begriff zusammengefuehrt werden, ist die erste
                # Stelle die, an der er ihn eingefuehrt hat.
                if belege.get(label):
                    beleg_je_term[term_id] = belege[label]

        # 5. Persist.
        store.set_person_transcript(person_id, transcript)

        # 🔴 DIE WIDERSPRÜCHE, nach JEDEM Interview (Birk, 2026-09-02: „der
        # extra LLM-Call soll nach jedem Interview passieren").
        #
        # Hier und nicht in `extract`: Die Extraktion sieht EIN Interview, ein
        # Widerspruch braucht zwei — und zwar zwei von verschiedenen Menschen.
        # Er entsteht beim Vergleichen, nicht beim Zuhören, also erst wenn
        # beide Seiten im Graphen stehen.
        #
        # Der Aufruf kostet nichts, was das Interview braucht: Die Begriffe
        # sind geschrieben, die Person hängt an der Wand. Fällt er aus, bleibt
        # die Liste, die zuletzt galt.
        _aktualisiere_widersprueche(store, llm)
        for term_id in term_ids:
            store.add_edge(
                person_id, term_id, created_at=stopped_at,
                evidence=beleg_je_term.get(term_id),
            )
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
