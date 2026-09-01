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

    core.on_mic_switch(True, at=100.0)
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
    core.on_mic_switch(True, at=100.0)
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
    core.on_mic_switch(True, at=100.0)
    core.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await core.drain()

    core.on_final(TranscriptionEvent(type="final", text="okay, Interview beendet", timestamp=180.0))
    await core.drain()

    assert core.store.get_person("p1").stop_reason == "spoken"
    assert core.processed == [("p1", 100.0, 180.0, 180.0)]


async def test_the_timeout_closes_a_forgotten_interview(core):
    core.on_mic_switch(True, at=100.0)
    core.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await core.drain()

    core.on_tick(now=1100.0)
    await core.drain()

    assert core.store.get_person("p1").stop_reason == "timeout"
    assert core.processed[0][2] == 1100.0


async def test_ein_foto_ohne_interview_wird_geloescht_statt_liegen_zu_bleiben(core, tmp_path):
    """🔴 Der Weg, den `/api/photo` nicht abfangen kann.

    Die HTTP-Route weist ab, BEVOR sie schreibt. Telegram kann das nicht: Dort
    ist die Datei schon heruntergeladen und das Portraet gerechnet, wenn der
    Core sie sieht. Ohne Aufraeumen sammelten sich Gesichter auf der Platte,
    die zu keiner Person gehoeren -- niemand sieht sie, also raeumt sie
    niemand auf.

    Geprueft wird am Dateisystem, nicht an einem Aufrufzaehler: Ob die Datei
    weg ist, ist die Zusage; wer sie geloescht hat, ist gleichgueltig.
    """
    foto = tmp_path / "waise.jpg"
    portrait = tmp_path / "waise.png"
    foto.write_bytes(b"jpeg")
    portrait.write_bytes(b"png")

    core.on_photo(photo_path=str(foto), portrait_path=str(portrait), at=100.0)
    await core.drain()

    assert core.store.open_person() is None, "es wurde doch ein Interview eroeffnet"
    assert not foto.exists(), "das Foto blieb liegen"
    assert not portrait.exists(), "das Portraet blieb liegen"


async def test_ein_zweites_foto_ersetzt_das_bild_und_teilt_das_interview_nicht(core):
    """🔴 Die Umstellung vom 2026-09-01 auf der Ebene des Core.

    Vorher schloss das zweite Foto p1 und eroeffnete p2 -- ein Gespraech wurde
    in zwei Personen zerschnitten, nur weil jemand nachjustiert hat. Jetzt
    bleibt es EINE Person, die nur ihr Bild wechselt, und die Auswertung
    laeuft entsprechend nicht an."""
    core.on_mic_switch(True, at=100.0)
    core.on_photo(photo_path="a.jpg", portrait_path="a.png", at=100.0)
    await core.drain()
    core.on_photo(photo_path="b.jpg", portrait_path="b.png", at=400.0)
    await core.drain()

    person = core.store.open_person()
    assert person is not None, "das Interview wurde geschlossen"
    assert person.id == "p1", "es wurde eine zweite Person angelegt"
    assert person.portrait_path == "b.png", "das neue Bild kam nicht an"
    assert person.started_at == 100.0, "der Beginn ist mitgewandert"
    assert core.processed == [], "die Auswertung lief mitten im Gespraech an"


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
    core.on_mic_switch(True, at=100.0)
    core.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await core.drain()
    core.on_text("stop", at=200.0)
    await core.drain()

    # Die Zusage lautet: Nach einer abgestuerzten Auswertung nimmt die Station
    # den NAECHSTEN Besuch noch an. Belegt wird das ueber den Schalter, weil
    # seit 2026-09-01 nur er ein Interview eroeffnet -- ein zweites Foto
    # bewiese hier nichts mehr.
    core.on_mic_switch(True, at=300.0)
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
    core1.on_mic_switch(True, at=100.0)
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
    # Der neue Prozess muss das offene Interview WEITERFUEHREN. Belegt ueber
    # den Schalter: das Schliessen per Foto gibt es seit 2026-09-01 nicht mehr
    # (der Test hing vorher genau daran und haette den Wiederaufnahme-Fall
    # danach gar nicht mehr geprueft).
    core2.on_mic_switch(False, at=500.0)
    await core2.drain()

    persons = {p.id: p for p in core2.store.list_persons()}
    assert persons["p1"].stop_reason == "mic_switch"
    assert persons["p1"].stopped_at == 500.0
    assert core2.store.open_person() is None
    assert calls == [("p1", 100.0, 500.0, 500.0)]
    store2.close()


# -- settle behaviour on the Telegram-text stop path only -------------------


async def test_the_text_stop_captures_a_final_that_arrives_after_the_stop_marker(core):
    core.on_mic_switch(True, at=100.0)
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
    core.on_mic_switch(True, at=100.0)
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
    instance.on_mic_switch(True, at=100.0)
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
    instance.on_mic_switch(True, at=100.0)
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


# -- the LLM gate behind the wake word (2026-08-30) ----------------------------


class WakeLLM:
    """The cheap yes/no model, faked. Counts calls and can be made slow."""

    def __init__(self, is_stop=True, delay=0.0):
        self.is_stop = is_stop
        self.delay = delay
        self.calls = 0

    def parse(self, system, user, output_model):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if isinstance(self.is_stop, Exception):
            raise self.is_stop
        return output_model(is_stop_command=self.is_stop)


def wake_core(tmp_path, wake_llm, **cfg_kwargs):
    cfg = Config(data_dir=tmp_path / "state", interview_timeout_s=900, **cfg_kwargs)
    store = Store.open(cfg.db_path)
    processor, calls = make_processor()
    core = Core(
        cfg=cfg,
        store=store,
        bus=EventBus(),
        transcript_log=TranscriptLog(cfg.transcript_log_path),
        llm=object(),
        embedder=HashEmbedder(dim=16),
        processor=processor,
        wake_llm=wake_llm,
        settle_timeout_s=TEST_SETTLE_TIMEOUT_S,
        settle_poll_s=TEST_SETTLE_POLL_S,
    )
    core.processed = calls
    return core


async def test_a_freely_worded_stop_behind_the_name_closes_the_interview(tmp_path):
    llm = WakeLLM(is_stop=True)
    core = wake_core(tmp_path, llm)
    core.on_mic_switch(True, at=100.0)
    core.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await core.drain()

    core.on_final(
        TranscriptionEvent(
            type="final", text="Utopia, hiermit beende ich das Interview", timestamp=180.0
        )
    )
    await core.drain()

    # A reason of its own, so store and logs say which of the two ways fired.
    assert core.store.get_person("p1").stop_reason == "spoken_llm"
    assert core.processed == [("p1", 100.0, 180.0, 180.0)]
    assert llm.calls == 1
    core.store.close()


async def test_a_no_from_the_llm_keeps_the_recording_running(tmp_path):
    llm = WakeLLM(is_stop=False)
    core = wake_core(tmp_path, llm)
    core.on_mic_switch(True, at=100.0)
    core.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await core.drain()

    core.on_final(
        TranscriptionEvent(type="final", text="Utopia hat mir gestern geholfen", timestamp=180.0)
    )
    await core.drain()

    assert core.store.open_person().id == "p1"
    assert llm.calls == 1
    core.store.close()


async def test_a_dead_proxy_leaves_the_mechanical_way_untouched(tmp_path):
    """2026-08-30: an expired subscription token answered every call with
    auth_error. The station has to keep working through that."""
    llm = WakeLLM(is_stop=RuntimeError("auth_error"))
    core = wake_core(tmp_path, llm)
    core.on_mic_switch(True, at=100.0)
    core.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await core.drain()

    core.on_final(
        TranscriptionEvent(
            type="final", text="Utopia, hiermit beende ich das Interview", timestamp=180.0
        )
    )
    await core.drain()
    assert core.store.open_person().id == "p1"  # still recording

    core.on_final(TranscriptionEvent(type="final", text="Interview beendet", timestamp=200.0))
    await core.drain()
    assert core.store.get_person("p1").stop_reason == "spoken"
    core.store.close()


async def test_switched_off_nothing_is_ever_asked(tmp_path):
    llm = WakeLLM(is_stop=True)
    core = wake_core(tmp_path, llm, wake_word_llm=False)
    core.on_mic_switch(True, at=100.0)
    core.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await core.drain()

    core.on_final(
        TranscriptionEvent(
            type="final", text="Utopia, hiermit beende ich das Interview", timestamp=180.0
        )
    )
    await core.drain()

    assert core.store.open_person().id == "p1"
    assert llm.calls == 0
    core.store.close()


async def test_ordinary_finals_never_reach_the_model(tmp_path):
    """The cost guarantee, measured where the money is actually spent."""
    llm = WakeLLM(is_stop=True)
    core = wake_core(tmp_path, llm)
    core.on_mic_switch(True, at=100.0)
    core.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await core.drain()

    for at, text in enumerate(
        ["wir brauchen mehr Holzbau", "die Bodenpreise sind das Problem"], start=110
    ):
        core.on_final(TranscriptionEvent(type="final", text=text, timestamp=float(at)))
    # And a mechanical hit does not pay for a second opinion either.
    core.on_final(TranscriptionEvent(type="final", text="Interview beendet", timestamp=180.0))
    await core.drain()

    assert core.store.get_person("p1").stop_reason == "spoken"
    assert llm.calls == 0
    core.store.close()


async def test_a_slow_answer_neither_blocks_the_loop_nor_the_next_utterance(tmp_path):
    """The call sits on the hot path of a running recording: it runs off the
    event loop and gives up after a hard, short budget."""
    llm = WakeLLM(is_stop=True, delay=30.0)
    core = wake_core(tmp_path, llm, wake_word_llm_timeout_s=0.1)
    core.on_mic_switch(True, at=100.0)
    core.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await core.drain()

    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.005)

    beat = asyncio.create_task(ticker())
    began = time.monotonic()
    core.on_final(
        TranscriptionEvent(
            type="final", text="Utopia, hiermit beende ich das Interview", timestamp=180.0
        )
    )
    core.on_final(
        TranscriptionEvent(type="final", text="und noch ein Satz danach", timestamp=181.0)
    )
    await core.drain()
    elapsed = time.monotonic() - began
    beat.cancel()

    assert elapsed < 5.0  # the 30 s answer was abandoned, not waited for
    assert ticks > 3  # …and the rest of the station kept running meanwhile
    assert core.store.open_person().id == "p1"  # a lost answer never closes
    core.store.close()
