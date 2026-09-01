import json
import logging

import pytest

from kg.config import Config
from kg.embeddings import HashEmbedder
from kg.extraction import ExtractionResult
from kg.llm import LLMError
from kg.merging import MergeGroup, MergeResult
from kg.pipeline import process_interview
from kg.store import Store
from kg.transcript import TranscriptionEvent, TranscriptLog


@pytest.fixture()
def env(tmp_path):
    cfg = Config(data_dir=tmp_path / "state", terms_per_interview=3)
    store = Store.open(cfg.db_path)
    log = TranscriptLog(cfg.transcript_log_path)
    yield cfg, store, log
    store.close()


class ScriptedLLM:
    """Returns one queued result per call and records the prompts it saw."""

    def __init__(self, results):
        self.results = list(results)
        self.prompts = []

    def parse(self, system, user, output_model):
        self.prompts.append(user)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def fill_log(log, texts_at):
    for text, at in texts_at:
        log.append(TranscriptionEvent(type="final", text=text, timestamp=at))


def test_happy_path_creates_edges_quotes_and_graph_json(env):
    cfg, store, log = env
    fill_log(
        log,
        [
            ("Wir sollten mit Recycling-Beton bauen.", 105.0),
            ("Und Genossenschaften stärken.", 115.0),
            ("So, Interview beendet.", 160.0),
            ("Nächste Person bitte.", 200.0),
        ],
    )
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM(
        [
            ExtractionResult(
                interview_end_index=10_000,
                terms=[
                    {"label": "Recycling-Beton", "evidence": "Recycling-Beton bauen"},
                    {"label": "Genossenschaftliches Wohnen", "evidence": "Genossenschaften"},
                ],
                quotes=[{"text": "Wir sollten mit Recycling-Beton bauen."}],
            ),
            MergeResult(groups=[]),
        ]
    )

    result = process_interview(
        store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 160.0
    )

    assert result.status == "done"
    assert len(result.term_ids) == 2
    assert len(store.list_edges()) == 2
    assert len(store.list_quotes()) == 1
    assert store.get_person(person.id).status == "done"
    graph = json.loads(cfg.graph_json_path.read_text(encoding="utf-8"))
    assert {n["type"] for n in graph["nodes"]} == {"person", "term"}


def test_only_one_quote_ever_reaches_the_store_even_if_the_model_sends_two(env):
    cfg, store, log = env
    fill_log(log, [("Recycling-Beton ist die Zukunft.", 105.0)])
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM(
        [
            ExtractionResult(
                interview_end_index=9999,
                terms=[],
                quotes=[{"text": "Erstes Zitat."}, {"text": "Zweites Zitat."}],
            )
        ]
    )  # no MergeResult queued — terms is empty, so a second call would raise IndexError

    process_interview(store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 150.0)

    quotes = store.list_quotes()
    assert len(quotes) == 1
    assert quotes[0].text == "Erstes Zitat."


def test_zero_quotes_from_the_model_creates_no_quote_and_does_not_crash(env):
    cfg, store, log = env
    fill_log(log, [("Recycling-Beton ist die Zukunft.", 105.0)])
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM([ExtractionResult(interview_end_index=9999, terms=[], quotes=[])])

    result = process_interview(
        store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 150.0
    )

    assert result.status == "done"
    assert store.list_quotes() == []


def test_a_blank_quote_text_is_dropped(env):
    cfg, store, log = env
    fill_log(log, [("Recycling-Beton ist die Zukunft.", 105.0)])
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM([ExtractionResult(interview_end_index=9999, terms=[], quotes=[{"text": "   "}])])

    process_interview(store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 150.0)

    assert store.list_quotes() == []


def test_the_self_given_name_is_persisted_with_the_rest_of_the_interview(env):
    """Schritt 5 schreibt Transkript, Kanten, Zitat — und den Namen.

    Kein eigener Bedienschritt und keine zusätzliche Frage an der Station: Die
    Person stellt sich ohnehin zu Beginn vor, also kommt der Name aus demselben
    einen Modellaufruf wie alles andere.
    """
    cfg, store, log = env
    fill_log(log, [("Mein Name ist Anna Weber. Recycling-Beton ist die Zukunft.", 105.0)])
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM(
        [
            ExtractionResult(
                interview_end_index=9999,
                terms=[],
                quotes=[{"text": "Recycling-Beton ist die Zukunft."}],
                names=[{"text": "Anna Weber"}],
            )
        ]
    )

    process_interview(store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 150.0)

    assert store.get_person(person.id).name == "Anna Weber"
    graph = json.loads(cfg.graph_json_path.read_text(encoding="utf-8"))
    assert [n["name"] for n in graph["nodes"] if n["type"] == "person"] == ["Anna Weber"]


def test_a_blank_name_is_dropped_exactly_like_a_blank_quote(env):
    """Wer sich nicht vorgestellt hat, bleibt namenlos — nicht leer benannt."""
    cfg, store, log = env
    fill_log(log, [("Recycling-Beton ist die Zukunft.", 105.0)])
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM(
        [ExtractionResult(interview_end_index=9999, terms=[], quotes=[], names=[{"text": "  "}])]
    )

    process_interview(store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 150.0)

    assert store.get_person(person.id).name is None


def test_the_stop_command_is_stripped_before_the_llm_sees_the_text(env):
    cfg, store, log = env
    fill_log(log, [("Holzbau ist gut.", 105.0), ("Interview beendet", 150.0)])
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM(
        [ExtractionResult(interview_end_index=9999, terms=[], quotes=[]), MergeResult(groups=[])]
    )

    process_interview(store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 150.0)

    assert "Interview beendet" not in llm.prompts[0]
    assert "Holzbau ist gut." in llm.prompts[0]


def test_the_bots_name_never_reaches_the_llm_with_the_command(env):
    """Spec 5: 'Utopia' must not be left standing where a term is extracted."""
    cfg, store, log = env
    fill_log(log, [("Holzbau ist gut.", 105.0), ("Utopia, das Interview ist beendet", 150.0)])
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM(
        [ExtractionResult(interview_end_index=9999, terms=[], quotes=[]), MergeResult(groups=[])]
    )

    process_interview(store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 150.0)

    assert "Utopia" not in llm.prompts[0]
    assert "beendet" not in llm.prompts[0]
    assert "Holzbau ist gut." in llm.prompts[0]


def test_the_settled_cut_end_is_handed_to_the_llm_but_transcript_stops_at_the_detected_end(env):
    cfg, store, log = env
    # A final at 150.9 lands just inside a plausible 3s settle window after a
    # stop marker at 150.0 (kg.core.settle_cut_end handles the actual wait;
    # here the caller just passes the resulting cut_end straight through).
    fill_log(log, [("Bodenpreise sind das Problem.", 105.0), ("Wo ist der Kaffee?", 150.9)])
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM(
        [
            ExtractionResult(interview_end_index=len("Bodenpreise sind das Problem."), terms=[], quotes=[]),
            MergeResult(groups=[]),
        ]
    )

    process_interview(
        store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 150.0, cut_end=150.9
    )

    # The settled final was offered to the model...
    assert "Wo ist der Kaffee?" in llm.prompts[0]
    # ...but the stored transcript stops where the interview really ended.
    assert store.get_person(person.id).transcript == "Bodenpreise sind das Problem."


def test_without_cut_end_the_cut_stops_at_stopped_at(env):
    cfg, store, log = env
    fill_log(log, [("Bodenpreise sind das Problem.", 105.0), ("Wo ist der Kaffee?", 150.9)])
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM(
        [ExtractionResult(interview_end_index=9999, terms=[], quotes=[]), MergeResult(groups=[])]
    )

    process_interview(store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 150.0)

    assert "Bodenpreise sind das Problem." in llm.prompts[0]
    assert "Wo ist der Kaffee?" not in llm.prompts[0]


def test_a_merge_maps_a_new_label_onto_an_existing_node(env):
    cfg, store, log = env
    existing = store.get_or_create_term("Betonspritzen mit Drohnen", created_at=1.0)
    fill_log(log, [("Roboter drucken Beton auf der Baustelle.", 105.0)])
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM(
        [
            ExtractionResult(
                interview_end_index=9999,
                terms=[{"label": "3D-Druck vor Ort", "evidence": "Roboter drucken Beton"}],
                quotes=[],
            ),
            MergeResult(
                groups=[
                    MergeGroup(
                        canonical_label="Roboter auf der Baustelle",
                        members=["3D-Druck vor Ort", "Betonspritzen mit Drohnen"],
                    )
                ]
            ),
        ]
    )

    result = process_interview(
        store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 150.0
    )

    assert result.term_ids == [existing.id]
    assert store.get_term(existing.id).label == "Roboter auf der Baustelle"
    assert len(store.list_terms()) == 1


def test_an_already_decided_label_skips_the_merge_call(env):
    cfg, store, log = env
    term = store.get_or_create_term("Holzbau", created_at=1.0)
    fill_log(log, [("Holzbau überall.", 105.0)])
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM(
        [
            ExtractionResult(
                interview_end_index=9999,
                terms=[{"label": "Holzbau", "evidence": "Holzbau"}],
                quotes=[],
            )
        ]
    )  # note: no MergeResult queued — a second call would raise IndexError

    result = process_interview(
        store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 150.0
    )

    assert result.term_ids == [term.id]
    assert len(llm.prompts) == 1


def test_an_llm_failure_marks_the_interview_failed_and_keeps_the_person(env):
    cfg, store, log = env
    fill_log(log, [("Irgendwas.", 105.0)])
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM([LLMError("boom")])

    result = process_interview(
        store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 150.0
    )

    assert result.status == "failed"
    assert store.get_person(person.id).status == "failed"
    assert store.list_edges() == []
    # The wall still shows the portrait, and graph.json is still written.
    assert cfg.graph_json_path.exists()


def test_a_person_who_got_nothing_out_of_the_analysis_is_logged_as_an_outage(env, caplog):
    """Kein Begriff, kein Zitat, kein Name — das ist eine leere Scheibe an der Wand.

    Bis heute lief dieser Fall als `status="done"` durch, ohne eine einzige
    Zeile im Log: der sichtbarste Fehler der Station war der einzige, den
    hinterher niemand nachzählen konnte (gemessen 2026-09-01: 17 von 30
    Läufen leer). Der Status bleibt `done` — die Analyse ist gelaufen —, aber
    das Ereignis wird protokolliert.
    """
    cfg, store, log = env
    fill_log(log, [("Ähm. Ja. Also. Mhm.", 105.0)])
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM([ExtractionResult(interview_end_index=9999, terms=[], quotes=[], names=[])])

    with caplog.at_level(logging.WARNING, logger="kg.pipeline"):
        result = process_interview(
            store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 150.0
        )

    assert result.status == "done"
    meldungen = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any(person.id in m for m in meldungen), meldungen


def test_a_person_with_only_a_name_and_no_terms_is_not_reported_as_an_outage(env, caplog):
    """Ein Name allein ist wenig, aber es ist nicht nichts — kein Fehlalarm."""
    cfg, store, log = env
    fill_log(log, [("Ich bin Mara.", 105.0)])
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM(
        [
            ExtractionResult(
                interview_end_index=9999, terms=[], quotes=[], names=[{"text": "Mara"}]
            )
        ]
    )

    with caplog.at_level(logging.WARNING, logger="kg.pipeline"):
        process_interview(store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 150.0)

    assert [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING] == []


def test_an_empty_transcript_is_not_sent_to_the_llm(env):
    cfg, store, log = env
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM([])

    result = process_interview(
        store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 150.0
    )

    assert result.status == "done"
    assert result.term_ids == []
    assert llm.prompts == []
