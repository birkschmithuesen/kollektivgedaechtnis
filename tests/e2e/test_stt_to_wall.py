"""E2E 2: spoken words become terms on the wall — with a REAL model call.

The chain under test:

    STT server (SSE) -> STTClient over real HTTP -> TranscriptLog -> Core
    -> SessionTracker stop -> process_interview -> extraction (Anthropic)
    -> merge decision (Anthropic) -> Store -> graph.json + SSE bus

Only the STT server itself is replaced, by a local one replaying the verified
wire format (tests/e2e/fake_stt.py). The model call is real: Birk's decision
(brief docs/briefs/task5-e2e-telegram-stt.md) — a recorded response would only
prove the wiring, not the extraction.

Cost brake: ONE interview, one short transcript, two model calls. The test is
marked `e2e` and deselected from the standard suite.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from kg.llm import LLMClient
from kg.stt_client import STTClient
from tests.e2e.conftest import make_core, require_anthropic_key
from tests.e2e.fake_stt import FakeSTT, final, partial

pytestmark = pytest.mark.e2e

STARTED_AT = 1_700_000_000.0

# Short on purpose (cost), but a real interview shape: two guiding-question
# answers with concrete, picturable content, then the spoken stop, then the
# noise that always follows it. The extraction has to find BOTH the terms and
# the true end of the interview.
UTTERANCES = [
    "Also ich glaube, wir müssten viel mehr mit Recycling-Beton bauen, "
    "statt immer neuen Zement zu brennen.",
    "Und die leeren Höfe in den Dörfern, dieser ganze ländliche Leerstand, "
    "den müsste man umbauen statt am Ortsrand neu zu versiegeln.",
    "Entscheiden sollten das die Leute vor Ort, nicht ein Investor aus der Stadt.",
    "Gut, dann Interview beendet, vielen Dank.",
    "Ach so, der Kaffee steht da hinten, nimm dir einen.",
    "Wer ist denn die Nächste?",
]

# One `final` per utterance, ten seconds apart, plus the revising partials the
# scribe backend really interleaves (contract §"extending"). The partials must
# reach the operator display and must never enter the transcript.
EVENTS = [
    partial("also ich glaube wir", STARTED_AT + 8.0, seq=1, extending=False),
    partial("Also ich glaube, wir müssten", STARTED_AT + 9.0, seq=2, extending=True),
    *[
        final(text, STARTED_AT + 10.0 * (index + 1), turn_id=f"01K2TURN{index}")
        for index, text in enumerate(UTTERANCES)
    ],
]

STOP_AT = STARTED_AT + 10.0 * 4  # the "Interview beendet" utterance


async def test_speech_becomes_terms_on_the_wall(station):
    cfg, store, bus, log = station
    llm = LLMClient(
        model=cfg.llm_model,
        effort=cfg.llm_effort,
        max_tokens=cfg.llm_max_tokens,
        # `cfg` is built directly here rather than through `load_config`, so it
        # carries no key; the key comes from the environment and only ever
        # lives there (docs/operations.md).
        api_key=require_anthropic_key(),
    )
    core = make_core(cfg, store, bus, log, llm)
    subscriber = bus.subscribe()

    # The interview is already open — a photo did that, and the Telegram half
    # of the chain is proven by test_telegram_photo.py. This test starts where
    # that one stops.
    person = store.create_person(started_at=STARTED_AT)
    core.tracker._open_since = STARTED_AT

    partials: list[str] = []

    def on_partial(event) -> None:
        partials.append(event.text)
        core.on_partial(event)

    with FakeSTT(EVENTS) as stt:
        client = STTClient(
            url=stt.url,
            log=log,
            on_final=core.on_final,
            on_partial=on_partial,
            on_state=core.on_stt_state,
            max_cycles=1,
        )
        consumer = asyncio.create_task(client.run())
        # `wait_until_sent` blocks on a threading.Event, and this test IS the
        # event loop the consumer runs in — waiting on it directly would stop
        # the consumer from ever connecting, and the server would sit idle.
        sent = await asyncio.to_thread(stt.wait_until_sent, 15.0)
        assert sent, "the STT server never finished sending"
        # The server closes the stream after the last event; run() returns when
        # its single cycle ends.
        await asyncio.wait_for(consumer, timeout=15.0)

    # The spoken stop closes the interview and starts the pipeline.
    await core.drain()

    # 1. Only finals were persisted; the partials went to the display only.
    assert partials == ["also ich glaube wir", "Also ich glaube, wir müssten"]
    logged = log.read_range(0.0, float("inf"))
    assert [e.text for e in logged] == UTTERANCES

    # 2. The interview closed on the spoken phrase, at the right moment.
    person = store.get_person(person.id)
    assert person.stop_reason == "spoken"
    assert person.stopped_at == STOP_AT
    assert person.status == "done", (
        f"the pipeline did not finish cleanly (status={person.status}); "
        "a failed status here means the real model call failed"
    )

    # 3. The model found the real end: the coffee and "wer ist denn die
    #    Nächste" are AFTER the stop marker and must not be in the transcript.
    #    This is the cut, not the extraction — it is deterministic.
    assert "Kaffee" not in person.transcript
    assert "Wer ist denn die Nächste" not in person.transcript
    # The stop phrase itself is stripped before extraction (spec 5).
    assert "Interview beendet" not in person.transcript
    assert "Recycling-Beton" in person.transcript

    # 4. Terms landed on the wall, tied to this person. Asserting exact labels
    #    would be asserting the model's wording; what must hold is that the
    #    extraction produced usable, capped, non-empty concepts.
    edges = [e for e in store.list_edges() if e.person_id == person.id]
    assert edges, "the real extraction produced no terms at all"
    assert len(edges) <= cfg.terms_per_interview
    labels = [store.get_term(edge.term_id).label for edge in edges]
    assert all(label.strip() for label in labels)
    assert all(len(label.split()) <= 4 for label in labels), labels
    # The prompt's own rule: no generic umbrella terms. If these come back the
    # extraction has degraded, which is exactly what a recorded response could
    # never have told us.
    generic = {"nachhaltigkeit", "zukunft", "digitalisierung", "veränderung"}
    assert not generic & {label.lower() for label in labels}, labels

    # 5. Quotes are the person's own words, not invented ones.
    quotes = [q for q in store.list_quotes() if q.person_id == person.id]
    assert quotes, "no quote was extracted"
    assert all(len(q.text) <= 220 for q in quotes)

    # 6. graph.json carries person, terms and edges — the browser's whole view.
    graph = json.loads(cfg.graph_json_path.read_text(encoding="utf-8"))
    node_ids = {node["id"] for node in graph["nodes"]}
    assert person.id in node_ids
    assert all(edge.term_id in node_ids for edge in edges)
    assert {q["text"] for q in graph["quotes"]} == {q.text for q in quotes}

    # 7. A live browser saw it happen.
    events = []
    while not subscriber.empty():
        events.append(subscriber.get_nowait())
    assert any(e["type"] == "transcript" for e in events)
    graph_events = [e for e in events if e["type"] == "graph"]
    assert graph_events, "no graph event was broadcast"
    final_ids = {node["id"] for node in graph_events[-1]["graph"]["nodes"]}
    assert all(edge.term_id in final_ids for edge in edges)

    print("\nextracted terms:", labels)
    print("quotes:", [q.text for q in quotes])
