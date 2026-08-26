"""E2E 1: a photo message becomes a person node on the wall.

The chain under test is the real one, end to end:

    Telegram HTTP API -> Updater/Application polling -> TelegramSource.dispatch
    -> getFile + download -> make_portrait -> Core -> SessionTracker -> Store
    -> graph.json + the SSE bus the browser listens on

Nothing in it is stubbed. Only Telegram itself is replaced, by a local server
speaking the Bot API (tests/e2e/fake_telegram.py) — so no token and no network.
The one thing left unproven is the shape of Telegram's real answers.

No model is called here: the wall shows the person the moment the photo lands
(spec 6), long before extraction runs.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from PIL import Image

from kg.telegram_bot import TelegramSource
from tests.e2e.conftest import make_core, write_photo
from tests.e2e.fake_telegram import TOKEN, FakeTelegram

pytestmark = pytest.mark.e2e

CHAT_ID = 987654


class UnusedLLM:
    def parse(self, system, user, output_model):  # pragma: no cover - must not run
        raise AssertionError("the photo path must not call the model")


async def _pump(application, condition, timeout=15.0):
    """Let the poller run until `condition()` holds, then stop it."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        if asyncio.get_running_loop().time() > deadline:
            return False
        await asyncio.sleep(0.05)
    return True


async def test_a_telegram_photo_reaches_the_wall_as_a_person_node(station):
    cfg, store, bus, log = station
    core = make_core(cfg, store, bus, log, UnusedLLM())
    source_photo = write_photo(cfg.data_dir / "incoming" / "visitor.jpg")
    subscriber = bus.subscribe()

    with FakeTelegram() as telegram:
        telegram.queue_photo("PHOTO1", source_photo, chat_id=CHAT_ID, at=1_700_000_000)

        source = TelegramSource(
            token=TOKEN,
            chat_id=CHAT_ID,
            photo_dir=cfg.photo_dir,
            portrait_dir=cfg.portrait_dir,
            portrait_size=cfg.portrait_size,
            on_photo=core.on_photo,
            on_text=core.on_text,
            api_base_url=telegram.base_url,
            api_base_file_url=telegram.base_file_url,
        )
        application = source.build_application()
        await application.initialize()
        await application.updater.start_polling(poll_interval=0.05)
        await application.start()
        try:
            # The poller hands the update to dispatch(); dispatch downloads and
            # cuts the portrait, then queues onto the Core. Wait for the Core's
            # own queue to have something before draining it.
            arrived = await _pump(application, lambda: not core._queue.empty())
            assert arrived, "no update reached the Core within the timeout"
        finally:
            await application.updater.stop()
            await application.stop()
            await application.shutdown()

    await core.drain()

    # 1. The person exists in the store, open, with both files recorded.
    persons = store.list_persons()
    assert len(persons) == 1
    person = persons[0]
    assert person.started_at == 1_700_000_000
    assert person.stopped_at is None

    # 2. The bytes really travelled: the downloaded photo equals the source.
    photo_path = cfg.photo_dir / "1700000000_100.jpg"
    assert photo_path.read_bytes() == source_photo.read_bytes()

    # 3. The portrait is the normalised circle the wall expects (spec 10.2).
    portrait_path = cfg.portrait_dir / "1700000000_100.png"
    with Image.open(portrait_path) as portrait:
        assert portrait.size == (cfg.portrait_size, cfg.portrait_size)
        assert portrait.mode == "RGBA"
        assert portrait.getpixel((0, 0))[3] == 0  # corner cut away by the mask
        assert portrait.getpixel((32, 32))[3] == 255  # centre opaque

    # 4. graph.json — what the browser fetches — carries the node and the URL
    #    that the server's /media/portraits mount actually serves.
    graph = json.loads(cfg.graph_json_path.read_text(encoding="utf-8"))
    nodes = [n for n in graph["nodes"] if n["type"] == "person"]
    assert len(nodes) == 1
    assert nodes[0]["portrait"] == f"/media/portraits/{portrait_path.name}"
    assert nodes[0]["id"] == person.id

    # 5. A live browser is told without reloading: the graph event went out.
    events = []
    while not subscriber.empty():
        events.append(subscriber.get_nowait())
    graph_events = [e for e in events if e["type"] == "graph"]
    assert graph_events, "no graph event was broadcast to the browser"
    assert any(n["id"] == person.id for n in graph_events[-1]["graph"]["nodes"])

    # 6. The real API calls happened in the real order.
    assert telegram.calls[0] == "getMe"
    assert "getUpdates" in telegram.calls
    assert "getFile" in telegram.calls


async def test_a_text_message_closes_the_interview_the_photo_opened(station):
    """The second half of the Telegram contract: any text is the stop signal."""
    cfg, store, bus, log = station
    processed: list[tuple] = []

    def record_processor(store_, cfg_, llm, embedder, log_, person_id, started, stopped, **kw):
        processed.append((person_id, started, stopped, kw.get("cut_end")))

    core = make_core(cfg, store, bus, log, UnusedLLM(), processor=record_processor)
    source_photo = write_photo(cfg.data_dir / "incoming" / "visitor.jpg")

    with FakeTelegram() as telegram:
        telegram.queue_photo("PHOTO1", source_photo, chat_id=CHAT_ID, at=1_700_000_000)
        telegram.queue_text("fertig", chat_id=CHAT_ID, at=1_700_000_120)

        source = TelegramSource(
            token=TOKEN,
            chat_id=CHAT_ID,
            photo_dir=cfg.photo_dir,
            portrait_dir=cfg.portrait_dir,
            portrait_size=cfg.portrait_size,
            on_photo=core.on_photo,
            on_text=core.on_text,
            api_base_url=telegram.base_url,
            api_base_file_url=telegram.base_file_url,
        )
        application = source.build_application()
        await application.initialize()
        await application.updater.start_polling(poll_interval=0.05)
        await application.start()
        try:
            got_both = await _pump(application, lambda: core._queue.qsize() >= 2)
            assert got_both, "photo and text did not both reach the Core"
        finally:
            await application.updater.stop()
            await application.stop()
            await application.shutdown()

    # settle_cut_end waits for an in-flight final on the text path; there is no
    # STT here, so shorten the wait rather than sitting out the full 3 seconds.
    core.settle_timeout_s = 0.1
    await core.drain()

    person = store.list_persons()[0]
    assert person.stopped_at == 1_700_000_120
    assert person.stop_reason == "text"
    assert processed == [(person.id, 1_700_000_000, 1_700_000_120, 1_700_000_120)]
