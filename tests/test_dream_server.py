"""Spec §7 — Tool 2's own operator API, and what it deliberately cannot do."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from kg.bus import EventBus
from kg2.config import DreamConfig
from kg2.server import create_dream_app, dream_state, seed_display_settings
from kg2.store import DreamStore


@pytest.fixture()
def app(tmp_path):
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    seed_display_settings(store, cfg)
    bus = EventBus()
    client = TestClient(create_dream_app(store, cfg, bus))
    yield client, store, cfg, bus
    store.close()


def add_dream(store, cfg, *, at, sentence, discarded=False):
    dream = store.create_dream(
        created_at=at, graph_generated_at=at - 1, person_count=6, term_count=5,
        edge_count=9, guiding_question=cfg.guiding_question,
        absorbed_persons=["p1"],
    )
    store.set_stage1(dream.id, prompt="S1", sentence=sentence, model="claude-opus-5")
    store.set_stage2_prompt(dream.id, prompt="S2", model="google/gemini-3-pro-image")
    store.finish_dream(dream.id, image_path=f"{dream.id}.png")
    (cfg.image_dir / f"{dream.id}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    if discarded:
        store.set_discarded(dream.id, True)
    return store.get_dream(dream.id)


# -- state ------------------------------------------------------------------


def test_state_carries_the_question_the_current_dream_and_the_strip(app):
    client, store, cfg, _ = app
    add_dream(store, cfg, at=1.0, sentence="erst")
    add_dream(store, cfg, at=2.0, sentence="dann")

    state = client.get("/api/state").json()

    assert state["question"] == cfg.guiding_question
    assert state["current"]["sentence"] == "dann"
    assert state["current"]["image"] == "/media/images/d2.png"
    assert [d["sentence"] for d in state["history"]] == ["erst"]


def test_state_starts_empty_on_a_fresh_machine(app):
    client, _, _, _ = app

    state = client.get("/api/state").json()

    assert state["current"] is None
    assert state["history"] == []
    assert state["paused"] is False


def test_display_settings_start_from_config_and_are_then_owned_by_the_operator(app):
    client, store, cfg, _ = app

    state = client.get("/api/state").json()
    assert state["fade_ms"] == cfg.default_fade_ms
    assert state["typewriter"] == cfg.default_typewriter
    assert state["strip_ratio"] == cfg.default_strip_ratio
    assert state["question_visible"] == cfg.default_question_visible
    assert state["question_seconds"] == cfg.default_question_seconds

    client.post("/api/display", json={"fade_ms": 400})
    seed_display_settings(store, cfg)  # a restart re-seeds; it must not win

    assert client.get("/api/state").json()["fade_ms"] == 400


def test_strip_max_defaults_to_ten_when_nothing_is_set(app):
    client, _, cfg, _ = app

    state = client.get("/api/state").json()

    assert cfg.default_strip_max == 10
    assert state["strip_max"] == 10


def test_strip_max_survives_a_restart(app):
    client, store, cfg, _ = app

    client.post("/api/display", json={"strip_max": 5})
    seed_display_settings(store, cfg)  # a restart re-seeds; it must not win

    assert client.get("/api/state").json()["strip_max"] == 5


def test_the_strip_keeps_the_newest_dreams_not_the_oldest(app):
    client, store, cfg, _ = app
    for index in range(1, 6):
        add_dream(store, cfg, at=float(index), sentence=f"traum {index}")
    # d6 is "current" (the newest visible dream); history is d1..d5.
    add_dream(store, cfg, at=6.0, sentence="traum 6")

    client.post("/api/display", json={"strip_max": 3})

    state = client.get("/api/state").json()
    assert [d["sentence"] for d in state["history"]] == ["traum 3", "traum 4", "traum 5"]


def test_raising_strip_max_makes_older_dreams_visible_again_nothing_deleted(app):
    client, store, cfg, _ = app
    for index in range(1, 6):
        add_dream(store, cfg, at=float(index), sentence=f"traum {index}")
    add_dream(store, cfg, at=6.0, sentence="traum 6")

    client.post("/api/display", json={"strip_max": 2})
    assert len(client.get("/api/state").json()["history"]) == 2

    client.post("/api/display", json={"strip_max": 5})

    state = client.get("/api/state").json()
    assert [d["sentence"] for d in state["history"]] == \
        ["traum 1", "traum 2", "traum 3", "traum 4", "traum 5"]
    assert len(store.all_dreams()) == 6  # nothing was ever removed from the record


# -- display controls (spec §7) --------------------------------------------


def test_every_display_setting_can_be_changed(app):
    client, _, _, _ = app

    response = client.post(
        "/api/display",
        json={
            "question_visible": False,
            "question_seconds": 20,
            "fade_ms": 800,
            "strip_ratio": 0.2,
            "strip_max": 7,
            "typewriter": True,
        },
    )

    assert response.status_code == 200
    state = client.get("/api/state").json()
    assert state["question_visible"] is False
    assert state["question_seconds"] == 20
    assert state["fade_ms"] == 800
    assert state["strip_ratio"] == 0.2
    assert state["strip_max"] == 7
    assert state["typewriter"] is True


def test_a_partial_display_update_leaves_the_rest_alone(app):
    client, _, _, _ = app
    client.post("/api/display", json={"fade_ms": 800, "typewriter": True})

    client.post("/api/display", json={"fade_ms": 400})

    state = client.get("/api/state").json()
    assert state["fade_ms"] == 400
    assert state["typewriter"] is True


@pytest.mark.parametrize(
    "payload",
    [
        {"fade_ms": 0},  # a 0 ms "cross-fade" is a cut, which Birk ruled out
        {"fade_ms": 20000},
        {"strip_ratio": 0.0},  # no strip at all — the evidence would vanish
        {"strip_ratio": 0.3},  # above the measured dominance ceiling (0.25) —
        # the strip would start to rival the stage it is evidence for
        {"strip_max": 0},  # an empty strip is not what this control is for
        {"strip_max": 41},  # above the largest count the wall design was judged at
        {"question_seconds": -1},
    ],
)
def test_out_of_range_display_values_are_rejected(app, payload):
    client, _, _, _ = app

    assert client.post("/api/display", json=payload).status_code == 422


def test_a_rejected_write_does_not_move_the_stored_value(app):
    client, _, _, _ = app
    before = client.get("/api/state").json()["fade_ms"]

    client.post("/api/display", json={"fade_ms": 99999})

    assert client.get("/api/state").json()["fade_ms"] == before


# -- flow control (spec §7) -------------------------------------------------


def test_dream_now_raises_a_flag_the_watcher_will_pick_up(app):
    """Needed the moment someone from the organiser stands in front of the
    screen and wants to see how it works."""
    client, store, _, _ = app

    assert client.post("/api/dream_now").status_code == 200

    assert store.get_setting("dream_requested", "0") == "1"


def test_pause_and_resume_round_trip(app):
    client, store, _, _ = app

    client.post("/api/pause", json={"paused": True})
    assert client.get("/api/state").json()["paused"] is True
    assert store.get_setting("paused", "0") == "1"

    client.post("/api/pause", json={"paused": False})
    assert client.get("/api/state").json()["paused"] is False


def test_discard_removes_the_dream_from_the_screen_and_the_strip(app):
    """Spec §7, Birk: one step, both places."""
    client, store, cfg, _ = app
    add_dream(store, cfg, at=1.0, sentence="erst")
    add_dream(store, cfg, at=2.0, sentence="peinlich")

    assert client.post("/api/discard", json={"dream_id": "d2", "discarded": True}).status_code == 200

    state = client.get("/api/state").json()
    assert state["current"]["sentence"] == "erst"  # the previous one returns
    assert state["history"] == []


def test_discard_is_reversible(app):
    client, store, cfg, _ = app
    add_dream(store, cfg, at=1.0, sentence="doch nicht")

    client.post("/api/discard", json={"dream_id": "d1", "discarded": True})
    client.post("/api/discard", json={"dream_id": "d1", "discarded": False})

    assert client.get("/api/state").json()["current"]["sentence"] == "doch nicht"


def test_discarding_an_unknown_dream_is_a_400_not_a_500(app):
    client, _, _, _ = app

    assert client.post("/api/discard", json={"dream_id": "d99", "discarded": True}).status_code == 400


# -- what the interface must NOT be able to do (spec §7) --------------------


def test_no_route_can_change_the_guiding_question_or_the_register():
    """Spec §7: changing the question mid-day destroys exactly the
    comparability the strip exists for. Both are morning settings, in
    config2.toml, and the API must have no way to touch them."""
    import kg2.server
    from pathlib import Path

    source = Path(kg2.server.__file__).read_text(encoding="utf-8")

    assert "guiding_question=" not in source.replace("cfg.guiding_question", "")
    assert "visual_register" not in source


def test_no_request_can_move_the_guiding_question_however_it_is_spelled(app):
    """The behavioural half of the same guarantee.

    The source check above only catches the literal spelling `guiding_question=`.
    A future route storing a `question_override` setting would slip past it
    while breaking the constraint outright — so this one ignores how the code
    is written and asserts the property: whatever you POST, the question the
    screen is told to display does not move.
    """
    client, store, cfg, _ = app
    before = client.get("/api/state").json()["question"]

    for path in ("/api/display", "/api/pause", "/api/discard", "/api/dream_now"):
        for payload in (
            {"question": "Wem gehört die Stadt?"},
            {"guiding_question": "Wem gehört die Stadt?"},
            {"question_override": "Wem gehört die Stadt?"},
            {"visual_register": "Radierung, harte Linien"},
            {"register": "Radierung"},
        ):
            client.post(path, json=payload)

    assert client.get("/api/state").json()["question"] == before == cfg.guiding_question
    # And nothing smuggled itself into the store under a neighbouring key.
    for key in ("question", "guiding_question", "question_override",
                "visual_register", "register"):
        assert store.get_setting(key, "<unset>") == "<unset>"


def test_the_state_payload_never_exposes_the_image_prompt(app):
    """Spec §5.2: showing stage 2's prompt would put lighting instructions on
    the wall. It belongs in the operator UI, and reaches it through /api/dreams."""
    client, store, cfg, _ = app
    add_dream(store, cfg, at=1.0, sentence="ein Satz")

    state = client.get("/api/state").json()

    assert "stage2_prompt" not in json.dumps(state)
    assert "S2" not in json.dumps(state)


def test_the_operator_can_read_the_full_record(app):
    """Spec §5.3 / §7: the image prompt is stored for reproducibility and shown
    ONLY in the operator UI."""
    client, store, cfg, _ = app
    add_dream(store, cfg, at=1.0, sentence="ein Satz")

    dreams = client.get("/api/dreams").json()["dreams"]

    assert dreams[0]["stage1_prompt"] == "S1"
    assert dreams[0]["stage2_prompt"] == "S2"
    assert dreams[0]["condense_model"] == "claude-opus-5"


def test_the_operator_sees_failed_and_discarded_dreams_too(app):
    """The record stays honest (spec §7). The DISPLAY filters; the record does not."""
    client, store, cfg, _ = app
    add_dream(store, cfg, at=1.0, sentence="verworfen", discarded=True)
    broken = store.create_dream(
        created_at=2.0, graph_generated_at=1.0, person_count=1, term_count=1,
        edge_count=1, guiding_question="Q", absorbed_persons=["p2"],
    )
    store.fail_dream(broken.id, "timeout")

    dreams = client.get("/api/dreams").json()["dreams"]

    assert {d["id"] for d in dreams} == {"d1", "d2"}
    assert [d for d in dreams if d["id"] == "d1"][0]["discarded"] is True
    assert [d for d in dreams if d["id"] == "d2"][0]["status"] == "failed"


# -- pages and assets -------------------------------------------------------


def test_the_two_pages_are_served(app):
    client, _, _, _ = app

    assert client.get("/dream").status_code == 200
    assert client.get("/operator").status_code == 200
    assert client.get("/", follow_redirects=False).status_code in (307, 302)


def test_images_are_served_from_the_dream_machines_own_directory(app):
    client, store, cfg, _ = app
    add_dream(store, cfg, at=1.0, sentence="x")

    response = client.get("/media/images/d1.png")

    assert response.status_code == 200
    assert response.content.startswith(b"\x89PNG")


# -- SSE --------------------------------------------------------------------


def test_a_control_change_is_pushed_to_every_subscriber(app):
    client, store, cfg, bus = app
    queue = bus.subscribe()

    client.post("/api/display", json={"fade_ms": 700})

    event = queue.get_nowait()
    assert event["type"] == "state"
    assert event["state"]["fade_ms"] == 700


async def test_the_event_stream_opens_with_the_current_state(app):
    """The synchronous TestClient cannot exercise this route end-to-end here:
    httpx's ASGITransport (both starlette's TestClient wrapper and a plain
    httpx.AsyncClient against the same transport) fully drains an ASGI
    response body before returning anything at all — confirmed with a
    minimal FastAPI app: a two-chunk generator comes back fine, a
    never-ending one hangs forever, in this installed httpx 0.28.1. `/events`
    must not terminate (the whole point is a heartbeat that keeps the
    connection open indefinitely), so it can never be observed through that
    transport. This drives the real route coroutine registered on the app
    instead, and reads the first chunk directly off its `body_iterator` —
    the same object `StreamingResponse` would feed to the ASGI `send`."""
    client, store, cfg, _ = app
    add_dream(store, cfg, at=1.0, sentence="beim Verbinden schon da")

    route = next(r for r in client.app.routes if r.path == "/events")
    response = await route.endpoint()
    assert response.status_code == 200

    chunk = await response.body_iterator.__anext__()
    await response.body_iterator.aclose()

    assert chunk.startswith("data:")
    payload = json.loads(chunk[len("data:"):].strip())
    assert payload["type"] == "state"
    assert payload["state"]["current"]["sentence"] == "beim Verbinden schon da"


# -- restart ----------------------------------------------------------------


def test_every_setting_and_the_whole_strip_come_back_after_a_restart(tmp_path):
    """Spec §8: the screen comes back exactly as it stood."""
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    seed_display_settings(store, cfg)
    client = TestClient(create_dream_app(store, cfg, EventBus()))
    for index in range(3):
        add_dream(store, cfg, at=float(index), sentence=f"traum {index}")
    client.post("/api/display", json={"fade_ms": 400, "typewriter": True})
    client.post("/api/pause", json={"paused": True})
    before = client.get("/api/state").json()
    store.close()

    reopened = DreamStore.open(cfg.db_path)
    seed_display_settings(reopened, cfg)  # startup re-seeds; must not overwrite
    after = TestClient(create_dream_app(reopened, cfg, EventBus())).get("/api/state").json()

    assert after == before
    reopened.close()


async def test_a_slow_tick_sends_a_keep_alive_rather_than_closing(app):
    """15 s of silence is the normal state of this stream — dreams are minutes
    apart. Without the heartbeat an idle proxy closes the connection and the
    screen stops receiving state it never knows it missed."""
    import asyncio

    client, store, cfg, _ = app
    route = next(r for r in client.app.routes if r.path == "/events")
    response = await route.endpoint()

    await response.body_iterator.__anext__()  # the opening state

    real_wait_for = asyncio.wait_for

    async def instant_timeout(awaitable, timeout):
        awaitable.close()
        raise TimeoutError

    asyncio.wait_for = instant_timeout
    try:
        chunk = await response.body_iterator.__anext__()
    finally:
        asyncio.wait_for = real_wait_for
        await response.body_iterator.aclose()

    assert chunk == ": keep-alive\n\n"


async def test_closing_the_stream_unsubscribes_from_the_bus(app):
    """A screen that reloads all day must not leave a queue behind on every
    reload — the bus would fan out to a growing list of dead subscribers."""
    client, store, cfg, bus = app
    route = next(r for r in client.app.routes if r.path == "/events")

    before = len(bus._subscribers)
    response = await route.endpoint()
    await response.body_iterator.__anext__()
    assert len(bus._subscribers) == before + 1

    await response.body_iterator.aclose()

    assert len(bus._subscribers) == before
