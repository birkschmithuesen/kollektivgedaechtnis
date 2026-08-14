import asyncio
import time

import pytest

from kg.config import Config
from kg.bus import EventBus
from kg.core import SETTLE_TIMEOUT_S, Core, settle_cut_end
from kg.embeddings import HashEmbedder
from kg.pipeline import ProcessResult
from kg.store import Store
from kg.transcript import TranscriptionEvent, TranscriptLog

# Short enough that the text-stop tests below don't each burn real seconds,
# but long enough to comfortably out-poll the ~0.05s "late final" tests.
TEST_SETTLE_TIMEOUT_S = 0.3
TEST_SETTLE_POLL_S = 0.02


def make_processor():
    calls = []

    def processor(store_, cfg_, llm_, embedder_, log_, person_id, started_at, stopped_at, cut_end):
        calls.append((person_id, started_at, stopped_at, cut_end))
        return ProcessResult(person_id, "done", [], "")

    return processor, calls


@pytest.fixture()
def core(tmp_path):
    cfg = Config(data_dir=tmp_path / "state", interview_timeout_s=900)
    store = Store.open(cfg.db_path)
    processor, calls = make_processor()

    instance = Core(
        cfg=cfg,
        store=store,
        bus=EventBus(),
        transcript_log=TranscriptLog(cfg.transcript_log_path),
        llm=object(),
        embedder=HashEmbedder(dim=16),
        processor=processor,
        settle_timeout_s=TEST_SETTLE_TIMEOUT_S,
        settle_poll_s=TEST_SETTLE_POLL_S,
    )
    instance.processed = calls
    yield instance
    store.close()


async def test_a_photo_creates_the_person_node_immediately(core):
    events = core.bus.subscribe()

    core.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await core.drain()

    person = core.store.open_person()
    assert person is not None
    assert person.portrait_path == "p.png"
    kinds = []
    while not events.empty():
        kinds.append(events.get_nowait()["type"])
    assert "graph" in kinds  # the wall learns about it at once
    assert core.processed == []  # nothing extracted yet


async def test_a_text_message_closes_the_interview_and_runs_the_pipeline(core):
    core.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await core.drain()

    core.on_text("fertig", at=200.0)
    await core.drain()

    assert core.store.open_person() is None
    # No final ever arrived after the stop marker, so the settle window ran
    # out and cut_end fell back to stopped_at.
    assert core.processed == [("p1", 100.0, 200.0, 200.0)]
    assert core.store.get_person("p1").stop_reason == "text"


async def test_a_spoken_command_in_a_final_closes_it(core):
    core.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await core.drain()

    core.on_final(TranscriptionEvent(type="final", text="okay, Interview beendet", timestamp=180.0))
    await core.drain()

    assert core.store.get_person("p1").stop_reason == "spoken"
    assert core.processed == [("p1", 100.0, 180.0, 180.0)]


async def test_the_timeout_closes_a_forgotten_interview(core):
    core.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await core.drain()

    core.on_tick(now=1100.0)
    await core.drain()

    assert core.store.get_person("p1").stop_reason == "timeout"
    assert core.processed[0][2] == 1100.0


async def test_a_new_photo_closes_the_previous_interview_and_opens_the_next(core):
    core.on_photo(photo_path="a.jpg", portrait_path="a.png", at=100.0)
    await core.drain()
    core.on_photo(photo_path="b.jpg", portrait_path="b.png", at=400.0)
    await core.drain()

    assert core.store.get_person("p1").stop_reason == "new_photo"
    assert core.store.open_person().id == "p2"
    assert core.processed == [("p1", 100.0, 400.0, 400.0)]


async def test_stop_signals_without_an_interview_do_nothing(core):
    core.on_text("hallo", at=10.0)
    core.on_tick(now=99999.0)
    await core.drain()

    assert core.store.list_persons() == []
    assert core.processed == []


async def test_partials_are_pushed_to_the_operator_but_not_stored(core):
    events = core.bus.subscribe()

    core.on_partial(TranscriptionEvent(type="partial", text="wir bau", timestamp=5.0))

    payload = events.get_nowait()
    assert payload == {"type": "transcript", "text": "wir bau"}
    assert not core.cfg.transcript_log_path.exists()


async def test_stt_connection_state_is_recorded_and_broadcast(core):
    events = core.bus.subscribe()

    core.on_stt_state(True)
    assert core.store.get_setting("stt_connected", "0") == "1"
    assert events.get_nowait()["type"] == "state"

    core.on_stt_state(False)
    assert core.store.get_setting("stt_connected", "0") == "0"


async def test_a_failing_pipeline_does_not_stop_the_core(tmp_path):
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)

    def exploding(*args, **kwargs):
        raise RuntimeError("boom")

    core = Core(
        cfg=cfg,
        store=store,
        bus=EventBus(),
        transcript_log=TranscriptLog(cfg.transcript_log_path),
        llm=object(),
        embedder=HashEmbedder(dim=16),
        processor=exploding,
        settle_timeout_s=TEST_SETTLE_TIMEOUT_S,
        settle_poll_s=TEST_SETTLE_POLL_S,
    )
    core.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await core.drain()
    core.on_text("stop", at=200.0)
    await core.drain()

    core.on_photo(photo_path="q.jpg", portrait_path="q.png", at=300.0)
    await core.drain()
    assert core.store.open_person().id == "p2"
    store.close()


async def test_a_restart_resumes_an_interview_left_open_by_a_crash(tmp_path):
    cfg = Config(data_dir=tmp_path / "state", interview_timeout_s=900)
    processor, calls = make_processor()

    # Session 1: open an interview, then "crash" (no close_person call).
    store1 = Store.open(cfg.db_path)
    core1 = Core(
        cfg=cfg,
        store=store1,
        bus=EventBus(),
        transcript_log=TranscriptLog(cfg.transcript_log_path),
        llm=object(),
        embedder=HashEmbedder(dim=16),
        processor=processor,
    )
    core1.on_photo(photo_path="a.jpg", portrait_path="a.png", at=100.0)
    await core1.drain()
    store1.close()

    # Session 2: a fresh process against the same database must resume the
    # still-open interview, not lose track of it and open a second one.
    store2 = Store.open(cfg.db_path)
    core2 = Core(
        cfg=cfg,
        store=store2,
        bus=EventBus(),
        transcript_log=TranscriptLog(cfg.transcript_log_path),
        llm=object(),
        embedder=HashEmbedder(dim=16),
        processor=processor,
    )
    core2.on_photo(photo_path="b.jpg", portrait_path="b.png", at=500.0)
    await core2.drain()

    persons = {p.id: p for p in core2.store.list_persons()}
    assert persons["p1"].stop_reason == "new_photo"
    assert persons["p1"].stopped_at == 500.0
    assert core2.store.open_person().id == "p2"
    assert calls == [("p1", 100.0, 500.0, 500.0)]
    store2.close()


# -- settle behaviour on the Telegram-text stop path only -------------------


async def test_the_text_stop_captures_a_final_that_arrives_after_the_stop_marker(core):
    core.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await core.drain()

    async def append_late_final():
        await asyncio.sleep(0.05)
        core.transcript_log.append(
            TranscriptionEvent(type="final", text="...noch was hinterher", timestamp=200.6)
        )

    late_task = asyncio.create_task(append_late_final())
    core.on_text("fertig", at=200.0)
    start = time.monotonic()
    await core.drain()
    elapsed = time.monotonic() - start
    await late_task

    assert core.processed == [("p1", 100.0, 200.0, 200.6)]
    # Returned as soon as the final landed, well short of sleeping out the
    # whole (short, test-only) settle window.
    assert elapsed < TEST_SETTLE_TIMEOUT_S * 0.7


async def test_the_text_stop_gives_up_after_the_settle_window_with_nothing_arriving(core):
    core.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await core.drain()

    core.on_text("fertig", at=200.0)
    start = time.monotonic()
    await core.drain()
    elapsed = time.monotonic() - start

    assert core.processed == [("p1", 100.0, 200.0, 200.0)]
    assert elapsed >= TEST_SETTLE_TIMEOUT_S


async def test_the_spoken_stop_does_not_wait_even_with_a_large_settle_window(tmp_path):
    cfg = Config(data_dir=tmp_path / "state", interview_timeout_s=900)
    store = Store.open(cfg.db_path)
    processor, calls = make_processor()
    instance = Core(
        cfg=cfg,
        store=store,
        bus=EventBus(),
        transcript_log=TranscriptLog(cfg.transcript_log_path),
        llm=object(),
        embedder=HashEmbedder(dim=16),
        processor=processor,
        settle_timeout_s=5.0,  # any wait at all would be unmissable here
        settle_poll_s=0.1,
    )
    instance.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await instance.drain()

    start = time.monotonic()
    instance.on_final(TranscriptionEvent(type="final", text="okay, Interview beendet", timestamp=180.0))
    await instance.drain()
    elapsed = time.monotonic() - start

    assert calls == [("p1", 100.0, 180.0, 180.0)]
    assert elapsed < 1.0
    store.close()


async def test_the_timeout_stop_does_not_wait_even_with_a_large_settle_window(tmp_path):
    cfg = Config(data_dir=tmp_path / "state", interview_timeout_s=900)
    store = Store.open(cfg.db_path)
    processor, calls = make_processor()
    instance = Core(
        cfg=cfg,
        store=store,
        bus=EventBus(),
        transcript_log=TranscriptLog(cfg.transcript_log_path),
        llm=object(),
        embedder=HashEmbedder(dim=16),
        processor=processor,
        settle_timeout_s=5.0,  # any wait at all would be unmissable here
        settle_poll_s=0.1,
    )
    instance.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await instance.drain()

    start = time.monotonic()
    instance.on_tick(now=1100.0)
    await instance.drain()
    elapsed = time.monotonic() - start

    assert calls == [("p1", 100.0, 1100.0, 1100.0)]
    assert elapsed < 1.0
    store.close()


def test_the_shipped_default_settle_window_is_three_seconds(tmp_path):
    assert SETTLE_TIMEOUT_S == 3.0
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    instance = Core(
        cfg=cfg,
        store=store,
        bus=EventBus(),
        transcript_log=TranscriptLog(cfg.transcript_log_path),
        llm=object(),
        embedder=HashEmbedder(dim=16),
    )

    assert instance.settle_timeout_s == SETTLE_TIMEOUT_S
    store.close()


# -- settle_cut_end helper, directly -----------------------------------------


async def test_settle_cut_end_returns_as_soon_as_a_late_final_lands(tmp_path):
    log = TranscriptLog(tmp_path / "t.jsonl")
    log.append(TranscriptionEvent(type="final", text="early", timestamp=50.0))

    async def append_late_final():
        await asyncio.sleep(0.05)
        log.append(TranscriptionEvent(type="final", text="late", timestamp=100.4))

    task = asyncio.create_task(append_late_final())
    start = time.monotonic()
    result = await settle_cut_end(log, stopped_at=100.0, timeout=0.3, poll_interval=0.02)
    elapsed = time.monotonic() - start
    await task

    assert result == 100.4
    assert elapsed < 0.2


async def test_settle_cut_end_gives_up_and_returns_stopped_at_unchanged(tmp_path):
    log = TranscriptLog(tmp_path / "t.jsonl")

    start = time.monotonic()
    result = await settle_cut_end(log, stopped_at=100.0, timeout=0.2, poll_interval=0.02)
    elapsed = time.monotonic() - start

    assert result == 100.0
    assert elapsed >= 0.2
