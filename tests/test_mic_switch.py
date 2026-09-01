"""Der Schalter am Mikrofon als zweiter Weg, ein Interview zu beginnen und zu
beenden.

Der STT-Server (fundusbot, `--mic-gate`) meldet den physischen Schalter am
Mikrofon per POST an `/api/interview_switch`. Hier steht, was der Core daraus
macht: AUS beendet das offene Interview, AN eroeffnet eines ohne Portraet --
denn wer kein Foto von sich will, muss trotzdem teilnehmen koennen
(Birk, 2026-09-01).

Der heikelste Teil steht weiter unten und heisst
`test_a_photo_after_a_photo_stays_a_new_visitor`: Ein Foto auf ein per
Schalter eroeffnetes Interview reicht das Portraet NACH, ein Foto auf ein per
Foto eroeffnetes ist ein NEUER Besucher. Wuerden die beiden Faelle vermischt,
ueberschriebe der zweite Besucher still das Portraet des ersten.
"""
import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from kg.bus import EventBus
from kg.config import Config
from kg.core import Core
from kg.embeddings import HashEmbedder
from kg.export import build_graph
from kg.extraction import ExtractionResult
from kg.merging import MergeResult
from kg.pipeline import ProcessResult, process_interview
from kg.server import create_app
from kg.session import SessionTracker
from kg.store import Store
from kg.transcript import TranscriptionEvent, TranscriptLog


# --- SessionTracker, reine Logik --------------------------------------------

def test_switching_off_closes_the_interview_with_its_own_reason():
    tracker = SessionTracker(timeout_s=900, stop_phrases=["auf wiedersehen"])
    tracker.photo(at=100.0)

    transitions = tracker.mic_switch(on=False, at=200.0)

    assert [(t.kind, t.reason, t.at) for t in transitions] == [("closed", "mic_switch", 200.0)]
    assert tracker.open_since is None


def test_the_reason_stays_distinguishable_from_a_spoken_goodbye():
    """Im Nachhinein muss unterscheidbar bleiben, wie ein Interview endete."""
    tracker = SessionTracker(timeout_s=900, stop_phrases=["auf wiedersehen"])
    tracker.photo(at=100.0)
    spoken = tracker.transcript("also dann auf wiedersehen", at=150.0)
    tracker.photo(at=200.0)
    switched = tracker.mic_switch(on=False, at=250.0)

    assert spoken[0].reason == "spoken"
    assert switched[0].reason == "mic_switch"


def test_switching_on_opens_an_interview_with_its_own_reason():
    """Wer kein Foto von sich will, soll trotzdem teilnehmen koennen. Der
    Grund bleibt eigen, damit im Nachhinein unterscheidbar ist, ob ein
    Interview per Foto oder per Schalter begann."""
    tracker = SessionTracker(timeout_s=900, stop_phrases=[])

    transitions = tracker.mic_switch(on=True, at=100.0)

    assert [(t.kind, t.reason, t.at) for t in transitions] == [("opened", "mic_switch", 100.0)]
    assert tracker.open_since == 100.0


def test_switching_on_does_not_disturb_a_running_interview():
    """Kein zweites Interview daneben, keine Neueroeffnung: idempotent."""
    tracker = SessionTracker(timeout_s=900, stop_phrases=[])
    tracker.photo(at=100.0)
    assert tracker.mic_switch(on=True, at=150.0) == []
    assert tracker.open_since == 100.0


def test_switching_on_twice_opens_once():
    tracker = SessionTracker(timeout_s=900, stop_phrases=[])
    assert len(tracker.mic_switch(on=True, at=100.0)) == 1
    assert tracker.mic_switch(on=True, at=150.0) == []
    assert tracker.open_since == 100.0


def test_switching_off_ends_a_switch_opened_interview_like_any_other():
    tracker = SessionTracker(timeout_s=900, stop_phrases=[])
    tracker.mic_switch(on=True, at=100.0)

    transitions = tracker.mic_switch(on=False, at=200.0)

    assert [(t.kind, t.reason, t.at) for t in transitions] == [("closed", "mic_switch", 200.0)]
    assert tracker.open_since is None


# --- Foto nachreichen, ohne den Fotoweg zu verbiegen -------------------------

def test_a_photo_after_a_switch_opening_hands_in_the_portrait():
    """Wer sich mitten im Gespraech doch fotografieren laesst, ist derselbe
    Mensch -- das Interview laeuft weiter, nur das Portraet kommt dazu."""
    tracker = SessionTracker(timeout_s=900, stop_phrases=[])
    tracker.mic_switch(on=True, at=100.0)

    transitions = tracker.photo(at=150.0)

    assert [(t.kind, t.reason, t.at) for t in transitions] == [("portrait", "late_photo", 150.0)]
    assert tracker.open_since == 100.0


def test_a_photo_after_a_photo_stays_a_new_visitor():
    """Die Absicherung gegen das Vermischen: Ein Foto auf ein per FOTO
    eroeffnetes Interview bleibt ein neuer Besucher. Sonst schriebe der
    zweite Besucher still das Portraet des ersten um."""
    tracker = SessionTracker(timeout_s=900, stop_phrases=[])
    tracker.photo(at=100.0)

    transitions = tracker.photo(at=200.0)

    assert [(t.kind, t.reason) for t in transitions] == [("closed", "new_photo"), ("opened", "photo")]
    assert tracker.open_since == 200.0


def test_only_the_first_photo_is_handed_in():
    """Nach dem nachgereichten Portraet ist das Interview eines wie jedes
    andere: Das naechste Foto ist wieder ein neuer Besucher."""
    tracker = SessionTracker(timeout_s=900, stop_phrases=[])
    tracker.mic_switch(on=True, at=100.0)
    tracker.photo(at=150.0)

    transitions = tracker.photo(at=200.0)

    assert [(t.kind, t.reason) for t in transitions] == [("closed", "new_photo"), ("opened", "photo")]
    assert tracker.open_since == 200.0


def test_a_resumed_interview_without_a_portrait_still_takes_one():
    """Nach einem Neustart weiss der Tracker aus der Datenbank, dass die
    offene Person kein Portraet hat (kg.core liest sie beim Bau)."""
    tracker = SessionTracker(
        timeout_s=900, stop_phrases=[], open_since=100.0, open_without_portrait=True
    )

    assert [(t.kind, t.reason) for t in tracker.photo(at=150.0)] == [("portrait", "late_photo")]
    assert tracker.open_since == 100.0


def test_switching_off_twice_closes_once():
    tracker = SessionTracker(timeout_s=900, stop_phrases=[])
    tracker.photo(at=100.0)
    assert len(tracker.mic_switch(on=False, at=200.0)) == 1
    assert tracker.mic_switch(on=False, at=201.0) == []


def test_switching_off_without_an_open_interview_is_harmless():
    tracker = SessionTracker(timeout_s=900, stop_phrases=[])
    assert tracker.mic_switch(on=False, at=100.0) == []


# --- Core -------------------------------------------------------------------

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
    )
    instance.processed = calls
    yield instance
    store.close()


async def test_the_switch_closes_the_person_and_starts_the_pipeline(core):
    core.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await core.drain()
    person_id = core.store.open_person().id

    core.on_mic_switch(on=False, at=200.0)
    await core.drain()

    assert core.store.open_person() is None
    closed = core.store.get_person(person_id)
    assert closed.stopped_at == 200.0
    assert closed.stop_reason == "mic_switch"
    assert [c[0] for c in core.processed] == [person_id]


async def test_the_switch_state_is_its_own_setting(core):
    """Nicht `stt_connected` mitbenutzen: das eine ist das Netz, das andere
    die Hand des Besuchers, und auf der Bedienseite muss man sie am selben
    Moment auseinanderhalten koennen."""
    core.on_stt_state(connected=True)
    core.on_mic_switch(on=False, at=100.0)
    await core.drain()

    assert core.store.get_setting("mic_on", "1") == "0"
    assert core.store.get_setting("stt_connected", "0") == "1"

    core.on_mic_switch(on=True, at=110.0)
    await core.drain()
    assert core.store.get_setting("mic_on", "0") == "1"


async def test_switching_on_creates_a_person_without_a_portrait(core):
    """Die Datenbank kann eine Person ohne Foto -- `photo_path` und
    `portrait_path` sind seit jeher `str | None`."""
    events = core.bus.subscribe()

    core.on_mic_switch(on=True, at=100.0)
    await core.drain()

    person = core.store.open_person()
    assert person is not None
    assert person.started_at == 100.0
    assert person.photo_path is None
    assert person.portrait_path is None
    assert core.processed == []  # verdichtet wird erst nach dem Schluss
    kinds = []
    while not events.empty():
        kinds.append(events.get_nowait()["type"])
    assert "graph" in kinds  # der Knoten steht sofort auf der Wand


async def test_switching_on_twice_does_not_open_a_second_interview(core):
    core.on_mic_switch(on=True, at=100.0)
    core.on_mic_switch(on=True, at=150.0)
    await core.drain()

    assert [p.id for p in core.store.list_persons()] == ["p1"]
    assert core.store.open_person().started_at == 100.0


async def test_switching_on_does_not_disturb_a_photo_interview(core):
    core.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    core.on_mic_switch(on=True, at=150.0)
    await core.drain()

    assert [p.id for p in core.store.list_persons()] == ["p1"]
    assert core.store.get_person("p1").portrait_path == "p.png"


async def test_switching_off_closes_a_switch_opened_interview(core):
    core.on_mic_switch(on=True, at=100.0)
    await core.drain()
    core.on_mic_switch(on=False, at=200.0)
    await core.drain()

    assert core.store.open_person() is None
    closed = core.store.get_person("p1")
    assert closed.stopped_at == 200.0
    assert closed.stop_reason == "mic_switch"
    assert [c[0] for c in core.processed] == ["p1"]


async def test_a_late_photo_fills_in_the_portrait_instead_of_starting_over(core):
    """Das Foto darf das laufende Interview nicht schliessen und ein neues
    eroeffnen -- es ist dieselbe Person, die sich anders entschieden hat."""
    core.on_mic_switch(on=True, at=100.0)
    await core.drain()

    core.on_photo(photo_path="spaet.jpg", portrait_path="spaet.png", at=150.0)
    await core.drain()

    assert [p.id for p in core.store.list_persons()] == ["p1"]
    person = core.store.get_person("p1")
    assert person.started_at == 100.0
    assert person.stopped_at is None
    assert (person.photo_path, person.portrait_path) == ("spaet.jpg", "spaet.png")
    assert core.processed == []  # nichts wurde geschlossen, nichts verdichtet


async def test_a_photo_after_a_photo_stays_a_new_visitor_in_the_core(core):
    """Punkt 5 der Aufgabe, die Absicherung gegen das Vermischen: Der zweite
    Besucher bekommt eine eigene Person, statt das Portraet des ersten
    still zu ueberschreiben."""
    core.on_photo(photo_path="a.jpg", portrait_path="a.png", at=100.0)
    await core.drain()
    core.on_photo(photo_path="b.jpg", portrait_path="b.png", at=400.0)
    await core.drain()

    assert core.store.get_person("p1").stop_reason == "new_photo"
    assert core.store.get_person("p1").portrait_path == "a.png"
    assert core.store.open_person().id == "p2"
    assert core.store.get_person("p2").portrait_path == "b.png"


async def test_a_second_photo_after_a_late_photo_is_a_new_visitor(core):
    """Sobald das Portraet nachgereicht ist, gilt wieder die Fotoregel."""
    core.on_mic_switch(on=True, at=100.0)
    core.on_photo(photo_path="spaet.jpg", portrait_path="spaet.png", at=150.0)
    await core.drain()

    core.on_photo(photo_path="b.jpg", portrait_path="b.png", at=400.0)
    await core.drain()

    assert core.store.get_person("p1").stop_reason == "new_photo"
    assert core.store.get_person("p1").portrait_path == "spaet.png"
    assert core.store.open_person().id == "p2"


async def test_a_restart_keeps_the_portrait_open(core, tmp_path):
    """Der Neustart nach einem Absturz liest die offene Person aus der
    Datenbank -- samt der Tatsache, dass sie noch kein Portraet hat."""
    core.on_mic_switch(on=True, at=100.0)
    await core.drain()

    wieder = Core(
        cfg=core.cfg,
        store=core.store,
        bus=EventBus(),
        transcript_log=core.transcript_log,
        llm=object(),
        embedder=HashEmbedder(dim=16),
        processor=core.processor,
    )
    assert wieder.tracker.open_since == 100.0
    wieder.on_photo(photo_path="spaet.jpg", portrait_path="spaet.png", at=150.0)
    await wieder.drain()

    assert [p.id for p in core.store.list_persons()] == ["p1"]
    assert core.store.get_person("p1").portrait_path == "spaet.png"


async def test_the_graph_export_carries_a_person_without_a_portrait(core):
    """`_portrait_url` gibt bei leerem Pfad `None` zurueck -- der Export muss
    das aushalten, sonst nimmt eine einzige Person ohne Foto die ganze Wand
    mit."""
    core.on_mic_switch(on=True, at=100.0)
    await core.drain()

    graph = build_graph(core.store)

    person = next(n for n in graph["nodes"] if n["type"] == "person")
    assert person["id"] == "p1"
    assert person["portrait"] is None


class ScriptedLLM:
    """Wie in tests/test_pipeline.py: gibt je Aufruf ein vorbereitetes
    Ergebnis zurueck, damit die echte Verdichtung ohne Netz laeuft."""

    def __init__(self, results):
        self.results = list(results)

    def parse(self, system, user, output_model):
        return self.results.pop(0)


async def test_a_switch_opened_interview_condenses_like_any_other(tmp_path):
    """Vom Schalter bis zum Begriff auf der Wand, mit der echten Pipeline."""
    cfg = Config(data_dir=tmp_path / "state", interview_timeout_s=900)
    store = Store.open(cfg.db_path)
    transcript_log = TranscriptLog(cfg.transcript_log_path)
    transcript_log.append(
        TranscriptionEvent(type="final", text="Wir sollten Genossenschaften staerken.", timestamp=120.0)
    )
    instance = Core(
        cfg=cfg,
        store=store,
        bus=EventBus(),
        transcript_log=transcript_log,
        llm=ScriptedLLM(
            [
                ExtractionResult(
                    interview_end_index=10_000,
                    terms=[{"label": "Genossenschaftliches Wohnen", "evidence": "Genossenschaften"}],
                    quotes=[{"text": "Wir sollten Genossenschaften staerken."}],
                ),
                MergeResult(groups=[]),
            ]
        ),
        embedder=HashEmbedder(dim=16),
        processor=process_interview,
    )

    instance.on_mic_switch(on=True, at=100.0)
    await instance.drain()
    instance.on_mic_switch(on=False, at=200.0)
    await instance.drain()

    assert [t.label for t in store.list_terms()] == ["Genossenschaftliches Wohnen"]
    assert [(e.person_id, e.term_id) for e in store.list_edges()] == [("p1", "t1")]
    assert store.get_person("p1").status == "done"
    assert store.get_person("p1").portrait_path is None
    store.close()


async def test_the_switch_reaches_the_wall_immediately(core):
    events = core.bus.subscribe()
    core.on_mic_switch(on=False, at=100.0)
    await core.drain()

    states = []
    while not events.empty():
        event = events.get_nowait()
        if event["type"] == "state":
            states.append(event["state"])
    assert states and states[-1]["mic_on"] is False


# --- HTTP -------------------------------------------------------------------

class FakeCore:
    def __init__(self):
        self.calls = []

    def on_mic_switch(self, on, at):
        self.calls.append((on, at))


@pytest.fixture()
def client(tmp_path):
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    fake = FakeCore()
    app = create_app(store, cfg, EventBus(), core=fake)
    with TestClient(app) as test_client:
        test_client.store = store
        test_client.core = fake
        yield test_client
    store.close()


def test_the_endpoint_forwards_the_switch(client):
    before = time.time()
    response = client.post("/api/interview_switch", json={"on": False, "source": "mic_switch"})
    assert response.status_code == 200
    assert response.json() == {"ok": True, "on": False}

    assert len(client.core.calls) == 1
    on, at = client.core.calls[0]
    assert on is False
    assert before <= at <= time.time()


def test_source_is_optional(client):
    assert client.post("/api/interview_switch", json={"on": True}).status_code == 200
    assert client.core.calls == [(True, pytest.approx(time.time(), abs=5))]


@pytest.mark.parametrize("body", [{}, {"on": "vielleicht"}, {"on": None}])
def test_nonsense_is_rejected(client, body):
    assert client.post("/api/interview_switch", json=body).status_code == 422
    assert client.core.calls == []


def test_state_reports_the_microphone(client):
    assert client.get("/api/state").json()["mic_on"] is True   # Default: offen
    client.store.set_setting("mic_on", "0")
    assert client.get("/api/state").json()["mic_on"] is False


def test_the_whole_way_from_http_to_a_closed_interview(tmp_path):
    """Vom POST bis zur geschlossenen Person, mit laufendem Worker.

    Die Tests darueber pruefen die Teile einzeln (Tracker, Core, Route mit
    Attrappe). Dieser prueft, dass sie zusammen auch wirklich etwas bewegen:
    ein POST, und die Person in der Datenbank ist geschlossen, mit dem
    richtigen Grund.

    Was er NICHT zeigt: dass die Route `async def` sein muss. Der Grund dafuer
    (put_nowait in eine asyncio.Queue aus dem FastAPI-Threadpool) ist ein
    Rennen, das in CPython meistens gut geht -- mit `def` statt `async def`
    laeuft dieser Test genauso gruen durch. Nachgemessen, nicht vermutet. Die
    Begruendung steht deshalb als Kommentar an der Route und nicht als
    Zusicherung hier.
    """
    cfg = Config(data_dir=tmp_path / "state", interview_timeout_s=900)
    store = Store.open(cfg.db_path)
    # Das offene Interview kommt aus der Datenbank, nicht aus `on_photo`: der
    # Core liest beim Bau ein offenes Person-Objekt und setzt den Tracker
    # darauf (Neustart nach Absturz). Der Test faedelt damit NUR den Weg ein,
    # um den es geht -- HTTP -> Warteschlange -> Worker -- statt selbst aus dem
    # Testthread in eine asyncio.Queue zu legen, also genau das zu tun, wovor
    # dieser Test schuetzen soll.
    person_id = store.create_person(
        started_at=100.0, photo_path="p.jpg", portrait_path="p.png"
    ).id
    processor, calls = make_processor()
    core_instance = Core(
        cfg=cfg,
        store=store,
        bus=EventBus(),
        transcript_log=TranscriptLog(cfg.transcript_log_path),
        llm=object(),
        embedder=HashEmbedder(dim=16),
        processor=processor,
    )
    assert core_instance.tracker.open_since == 100.0
    app = create_app(store, cfg, core_instance.bus, core=core_instance)

    worker: list[asyncio.Task] = []

    @app.on_event("startup")
    async def _start_worker():
        worker.append(asyncio.create_task(core_instance.run_worker()))

    with TestClient(app) as http:
        assert http.post("/api/interview_switch", json={"on": False}).status_code == 200

        for _ in range(200):
            if store.open_person() is None:
                break
            time.sleep(0.01)
        assert store.open_person() is None, "der Schalter hat das Interview nicht beendet"
        assert store.get_person(person_id).stop_reason == "mic_switch"
        assert http.get("/api/state").json()["mic_on"] is False

    store.close()


def test_without_a_core_the_endpoint_does_not_exist(tmp_path):
    """Lieber ein 404 als eine 200, die nichts tut."""
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    app = create_app(store, cfg, EventBus())
    with TestClient(app) as display_only:
        assert display_only.post("/api/interview_switch", json={"on": False}).status_code == 404
        assert display_only.get("/api/state").status_code == 200
    store.close()
