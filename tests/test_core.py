import pytest

from kg.config import Config
from kg.bus import EventBus
from kg.core import Core
from kg.embeddings import HashEmbedder
from kg.pipeline import ProcessResult
from kg.store import Store
from kg.transcript import TranscriptionEvent, TranscriptLog


@pytest.fixture()
def core(tmp_path):
    cfg = Config(data_dir=tmp_path / "state", interview_timeout_s=900)
    store = Store.open(cfg.db_path)
    calls = []

    def processor(store_, cfg_, llm_, embedder_, log_, person_id, started_at, stopped_at):
        calls.append((person_id, started_at, stopped_at))
        return ProcessResult(person_id, "done", [], "")

    instance = Core(
        cfg=cfg,
        store=store,
        bus=EventBus(),
        transcript_log=TranscriptLog(cfg.transcript_log_path),
        llm=object(),
        embedder=HashEmbedder(dim=16),
        processor=processor,
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
    assert core.processed == [("p1", 100.0, 200.0)]
    assert core.store.get_person("p1").stop_reason == "text"


async def test_a_spoken_command_in_a_final_closes_it(core):
    core.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await core.drain()

    core.on_final(TranscriptionEvent(type="final", text="okay, Interview beendet", timestamp=180.0))
    await core.drain()

    assert core.store.get_person("p1").stop_reason == "spoken"
    assert core.processed == [("p1", 100.0, 180.0)]


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
    assert core.processed == [("p1", 100.0, 400.0)]


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
    calls = []

    def processor(store_, cfg_, llm_, embedder_, log_, person_id, started_at, stopped_at):
        calls.append((person_id, started_at, stopped_at))
        return ProcessResult(person_id, "done", [], "")

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
    assert calls == [("p1", 100.0, 500.0)]
    store2.close()
