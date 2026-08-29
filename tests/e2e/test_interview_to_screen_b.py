"""E2E 3: an interview becomes a dream and an image on screen B.

The chain this test exists for — the one Handoff 2026-08-29 §4.1 names as the
biggest unknown before the festival, because until now only its individual
links had ever run:

    Tool 1 (real Store + Core + FastAPI, served over real HTTP on a real port)
      -> graph.json
      -> kg2.graph_client.fetch_graph  (real HTTP, across the process boundary)
      -> kg2.trigger.evaluate          (person node WITH an edge = absorbed)
      -> kg2.weighting.build_material
      -> kg2.condense                  (REAL Anthropic call, stage 1)
      -> kg2.imagegen                  (REAL OpenRouter call, stage 2)
      -> save_image                    (real bytes on real disk)
      -> DreamStore
      -> kg2.server /api/state         (what screen B actually renders)

Nothing between the two tools is stubbed. In particular `tool1_url` points at
a genuine `127.0.0.1:<port>` uvicorn server rather than at an ASGI transport,
because the thing most likely to break on the festival morning is exactly the
network hop between two machines — an in-process shortcut would prove the
Python and skip the part that fails.

## What IS replaced, and why that is honest

Tool 1's *ingest* side (Telegram, STT) is not driven here: `test_telegram_photo`
and `test_stt_to_wall` already prove a photo and speech reach the wall, and
re-running them would spend two more model calls to re-prove a covered link.
This test starts where they stop — from a processed interview in Tool 1's own
Store — and proves the half nobody has ever run: everything downstream of
`graph.json`.

Tool 1's *extraction* model call is therefore also not made. The person, terms,
edges and quotes are written straight through `kg.store.Store`, the same way
`sim/seed_graph.py` does it. This is a deliberate scope line, not a shortcut
around a hard part: what stage 1 consumes is `graph.json`, and `graph.json` is
built by `kg.export.build_graph` from the Store either way.

## Cost

Two real cloud calls, once: one Anthropic condense (stage 1) and one OpenRouter
image (stage 2, ≈ 0.14 USD — measured, `docs/dream-image-contract.md`). Both
are made exactly once; the test asserts the call counts so a future edit cannot
quietly turn this into a series.

Marked `e2e` and deselected from the standard suite. Both keys must be present
or the test skips — a skip is honest, a green run that silently stubbed the
cloud is not.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time

import httpx
import pytest
import uvicorn

from kg.bus import EventBus
from kg.export import write_graph_json
from kg.server import create_app
from kg.store import Store
from kg2.config import DreamConfig
from kg2.cycle import run_dream
from kg2.graph_client import fetch_graph
from kg2.imagegen import render_image as real_render_image
from kg2.server import create_dream_app, dream_state, seed_display_settings
from kg2.store import DreamStore
from kg2.trigger import evaluate, resume_state
from tests.e2e.conftest import require_anthropic_key

pytestmark = pytest.mark.e2e

STARTED_AT = 1_700_000_000.0

# A small but real interview graph: eight people, overlapping terms, so stage 1
# gets shared terms (>=2 mentions) as well as single mentions — the two halves
# of `kg2.weighting`'s gliding selection. Labels are drawn from the conference's
# actual subject matter, like sim/seed_graph.py's.
INTERVIEWS: list[tuple[str, list[str], str]] = [
    ("p1", ["Umbau statt Abriss", "Graue Energie im Bestand halten"],
     "Wir reißen viel zu schnell ab, statt weiterzubauen."),
    ("p2", ["Umbau statt Abriss", "Leerstand im Dorfkern"],
     "Bei uns stehen die Höfe leer und am Ortsrand wird neu versiegelt."),
    ("p3", ["Recyclingbeton", "Graue Energie im Bestand halten"],
     "Zement brennen ist das Problem, nicht der Beton selbst."),
    ("p4", ["Umbau statt Abriss", "Genossenschaftliches Wohnen"],
     "Wohnen sollte niemandem gehören, der damit Rendite macht."),
    ("p5", ["Leerstand im Dorfkern", "Entscheidungen vor Ort"],
     "Das müssen die Leute im Dorf entscheiden, nicht ein Investor."),
    ("p6", ["Recyclingbeton", "Materialpässe für jedes Gebäude"],
     "Jedes Haus müsste wissen, woraus es besteht."),
    ("p7", ["Genossenschaftliches Wohnen", "Entscheidungen vor Ort"],
     "Gemeinsam bauen ist billiger, aber niemand traut sich."),
    ("p8", ["Umbau statt Abriss", "Photovoltaik auf jedem Dach"],
     "Auf jedem Bestandsdach ist Platz, das kostet keinen Quadratmeter Boden."),
]

#: The person whose interview arrives LAST and must be the one that triggers
#: the dream. Kept separate from INTERVIEWS so the test can prove the trigger
#: fires on the new material rather than on the graph merely being non-empty.
LATE_PERSON = ("p9", ["Betonspritzen mit Drohnen", "Umbau statt Abriss"],
               "Irgendwann drucken Roboter die Wände und wir schauen zu.")


def _free_port() -> int:
    """An OS-assigned port, released immediately so uvicorn can take it.

    A hardcoded 8800 would collide with a Tool 1 the developer already has
    running — on the machine where this test is most likely to be run.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Tool1Server:
    """Tool 1's real FastAPI app on a real port, in a background thread.

    Not `TestClient` and not `httpx.ASGITransport`: those would let Tool 2 call
    Tool 1 in-process, which is precisely the hop this test exists to prove.
    """

    def __init__(self, app, port: int) -> None:
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self.url = f"http://127.0.0.1:{port}"

    def __enter__(self) -> "Tool1Server":
        self._thread.start()
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if self._server.started:
                return self
            time.sleep(0.05)
        raise AssertionError("Tool 1's server did not start within 20 s")

    def __exit__(self, *exc) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=20.0)


def require_openrouter_key() -> str:
    """Stage 2's credential — environment only, never a file (spec §9).

    Skips rather than fails when absent: a machine without the key cannot run
    this test, and pretending otherwise by stubbing the render would leave the
    contract unproven while the test still went green.
    """
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        pytest.skip("OPENROUTER_API_KEY is not set — this test renders a real image")
    return key


def seed_interview(store, labels: list[str], quote: str, at: float):
    """Write one processed interview straight into Tool 1's Store.

    The same route `sim/seed_graph.py` takes (`get_or_create_term` +
    `add_edge` + `set_person_status`), and for the same reason: what Tool 2
    consumes is `graph.json`, which `kg.export.build_graph` derives from the
    Store regardless of whether the terms came from a model or from here.
    Re-running Tool 1's extraction would spend a model call to re-prove a link
    `test_stt_to_wall.py` already covers.

    Ids are assigned by the Store, never chosen here — the labels in
    INTERVIEWS are what carries the meaning, and a person id is Tool 1's to
    mint.
    """
    person = store.create_person(started_at=at)
    for index, label in enumerate(labels):
        term = store.get_or_create_term(label, created_at=at + index)
        store.add_edge(person.id, term.id, created_at=at + index)
    store.add_quote(person.id, quote, at)
    store.set_person_status(person.id, "done")
    return person


def test_an_interview_becomes_a_dream_and_an_image_on_screen_b(tmp_path):
    anthropic_key = require_anthropic_key()
    openrouter_key = require_openrouter_key()

    # -- Tool 1: real store, real app, real port ---------------------------
    from kg.config import Config

    tool1_cfg = Config(data_dir=tmp_path / "tool1", portrait_size=64)
    tool1_store = Store.open(tool1_cfg.db_path)
    tool1_bus = EventBus()

    persons = []
    for index, (_, labels, quote) in enumerate(INTERVIEWS):
        persons.append(
            seed_interview(tool1_store, labels, quote, STARTED_AT + 60.0 * index)
        )
    write_graph_json(tool1_store, tool1_cfg.graph_json_path)

    port = _free_port()
    app = create_app(tool1_store, tool1_cfg, tool1_bus)

    with Tool1Server(app, port) as tool1:
        # -- 1. The hop itself. Tool 2's own client, over real HTTP. -------
        graph = fetch_graph(f"{tool1.url}/graph.json", timeout=10.0)
        assert graph is not None, (
            "kg2.graph_client could not read Tool 1's graph.json over HTTP — "
            "this is the exact failure the runbook's cross-machine curl check "
            "is meant to catch"
        )
        assert graph["version"] == 1
        term_labels = {n["label"] for n in graph["nodes"] if n["type"] == "term"}
        assert "Umbau statt Abriss" in term_labels

        # -- 2. Tool 2's config points at Tool 1 by URL, as in production --
        dream_cfg = DreamConfig(
            data_dir=tmp_path / "dream",
            tool1_url=tool1.url,
            min_interval_s=240,
            anthropic_api_key=anthropic_key,
            openrouter_api_key=openrouter_key,
        )
        dream_store = DreamStore.open(dream_cfg.db_path)
        seed_display_settings(dream_store, dream_cfg)
        dream_bus = EventBus()

        # -- 3. The trigger. Nothing has been dreamt, so all nine are fresh.
        state = resume_state(dream_store.all_dreams())
        assert state.seen_persons == frozenset()

        decision = evaluate(state, graph, time.time(), dream_cfg.min_interval_s)
        assert decision.fire, f"the trigger did not fire on fresh material: {decision.reason}"
        assert decision.absorbed == {p.id for p in persons}, (
            "the trigger must absorb exactly the persons whose interviews are "
            "processed (person node WITH an edge)"
        )

        # -- 4. The cycle. Both cloud calls, counted. ----------------------
        from kg.llm import LLMClient

        llm = LLMClient(
            model=dream_cfg.condense_model,
            effort=dream_cfg.condense_effort,
            max_tokens=dream_cfg.condense_max_tokens,
            api_key=anthropic_key,
        )

        renders: list[str] = []

        def counting_render(prompt, **kwargs):
            """The real renderer, wrapped only to count and capture.

            Deliberately not a stub: `real_render_image` is called through,
            so the OpenRouter contract, the base64 decode and the PNG/JPEG
            byte-header branch all run for real.
            """
            renders.append(prompt)
            return real_render_image(prompt, **kwargs)

        sentences: list[str] = []
        dream = run_dream(
            dream_store,
            dream_cfg,
            llm,
            graph,
            decision.started_at,
            render_fn=counting_render,
            on_sentence=sentences.append,
        )

        assert dream is not None, (
            "the cycle failed — read dreams.sqlite3's `error` column; a None "
            "here means stage 1 or stage 2 raised against the live endpoint"
        )
        assert len(renders) == 1, f"stage 2 was called {len(renders)} times, not once"

        # -- 5. Stage 1's product. --------------------------------------
        assert dream.status == "done"
        assert dream.sentence and dream.sentence.strip()
        assert dream.sentence_en and dream.sentence_en.strip()
        # The image channel (2026-08-29): the longer description the picture
        # is actually built from. `tension_source` is deliberately NOT
        # asserted non-empty — material without a real contradiction must
        # leave it blank, and this fixture's material may well be such a case.
        assert dream.image_description and dream.image_description.strip()
        assert len(dream.image_description.split()) > len(dream.sentence_en.split()), (
            "the image description must be RICHER than the 16-word wall "
            "sentence — that is the whole point of the second field"
        )
        assert sentences == [dream.sentence], (
            "the display must be told the sentence before the image exists "
            "(spec §6) — that announcement is what the typewriter builds on"
        )
        assert 1 <= dream.mood <= 5
        assert 1 <= dream.tension <= 5
        # The sentence is what goes on the wall: one clause, no newline.
        assert "\n" not in dream.sentence
        # The material actually reached the prompt — not a dream from nothing.
        assert dream.person_count == len(persons)
        assert dream.term_count > 0
        assert "Umbau statt Abriss" in dream.stage1_prompt

        # -- 6. Stage 2's product: a real file, real bytes. ---------------
        assert dream.image_path, "the dream finished without an image"
        image_file = dream_cfg.image_dir / dream.image_path
        assert image_file.exists(), f"{image_file} was recorded but is not on disk"
        assert image_file.suffix in (".png", ".jpg"), (
            f"unexpected extension {image_file.suffix} — the contract records "
            "PNG or JPEG per call, decided by the byte header"
        )
        data = image_file.read_bytes()
        assert len(data) > 10_000, f"only {len(data)} bytes — that is not a photograph"
        assert data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8\xff"), (
            "the bytes on disk are neither PNG nor JPEG"
        )
        # The extension on disk must match the bytes, not the declared MIME.
        expected = ".png" if data.startswith(b"\x89PNG") else ".jpg"
        assert image_file.suffix == expected

        # The image prompt is the documented blocks, English, with the
        # register appended — the fixed part of the measurement series. The
        # motif is the long description, not the literal wall translation
        # (2026-08-29, kg2/imagegen.py).
        assert dream.stage2_prompt
        assert dream.image_description in dream.stage2_prompt
        assert dream_cfg.visual_register in dream.stage2_prompt
        assert dream_cfg.image_aspect_ratio in dream.stage2_prompt
        assert renders[0] == dream.stage2_prompt, (
            "what was recorded must be exactly what was sent"
        )

        # -- 7. Screen B. What the browser actually renders. --------------
        state_payload = dream_state(dream_store, dream_cfg)
        assert state_payload["current"] is not None
        assert state_payload["current"]["id"] == dream.id
        assert state_payload["current"]["sentence"] == dream.sentence
        assert state_payload["current"]["image"] == f"/media/images/{dream.image_path}"
        assert state_payload["question"] == dream_cfg.guiding_question
        # The strip carries the EARLIER dreams only: `store.history()` is
        # `visible_dreams()[:-1]`, because the current dream hangs on the big
        # screen rather than in the strip beneath it (spec §6). With exactly
        # one dream on the day, the strip is therefore correctly empty — the
        # evidence chain starts once there is something to compare against.
        assert state_payload["history"] == []

        # ...and over HTTP, from the server screen B talks to, including the
        # image bytes themselves through the static mount.
        from fastapi.testclient import TestClient

        with TestClient(create_dream_app(dream_store, dream_cfg, dream_bus)) as client:
            api_state = client.get("/api/state").json()
            assert api_state["current"]["id"] == dream.id
            image_response = client.get(api_state["current"]["image"])
            assert image_response.status_code == 200
            assert image_response.content == data, (
                "screen B would serve different bytes than the cycle wrote"
            )
            page = client.get("/dream")
            assert page.status_code == 200

        # -- 8. A restart is a resume, not a reset (spec §8). -------------
        resumed = resume_state(dream_store.all_dreams())
        assert resumed.seen_persons == frozenset(dream.absorbed_persons)
        assert resumed.last_started_at == dream.created_at

        # The same graph must NOT produce a second dream: nothing new was said.
        again = evaluate(resumed, graph, time.time(), dream_cfg.min_interval_s)
        assert not again.fire, (
            f"the same material dreamt twice (reason={again.reason}) — at the "
            "festival that is the same picture appearing again for no reason"
        )

        # -- 9. A NEW interview arrives. The whole loop, once more. -------
        _, late_labels, late_quote = LATE_PERSON
        late = seed_interview(
            tool1_store, late_labels, late_quote,
            STARTED_AT + 60.0 * len(INTERVIEWS),
        )
        write_graph_json(tool1_store, tool1_cfg.graph_json_path)

        graph2 = fetch_graph(f"{tool1.url}/graph.json", timeout=10.0)
        assert graph2 is not None
        assert late.id in {n["id"] for n in graph2["nodes"]}

        # Fresh material, but the floor has not expired: the dream is DELAYED,
        # not dropped. This is the property the runbook warns must not be
        # "tuned" away — a dropped interview is invisible on screen.
        soon = evaluate(resumed, graph2, dream.created_at + 10.0, dream_cfg.min_interval_s)
        assert not soon.fire and soon.reason == "floor"

        # Past the floor, the same fresh person is still fresh and fires.
        later = evaluate(
            resumed, graph2, dream.created_at + dream_cfg.min_interval_s + 1.0,
            dream_cfg.min_interval_s,
        )
        assert later.fire, f"the delayed interview never fired: {later.reason}"
        assert late.id in later.absorbed

    tool1_store.close()

    print("\n--- Probedurchlauf, eine Kette ---")
    print("Satz  :", dream.sentence)
    print("EN    :", dream.sentence_en)
    print("Motiv :", dream.image_description)
    print("Wider.:", dream.tension_source or "— (kein Widerspruch im Material)")
    print(f"mood  : {dream.mood}   tension: {dream.tension}")
    print("Bild  :", image_file.resolve(), f"({len(data) // 1024} KB)")
