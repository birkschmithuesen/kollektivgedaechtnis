"""Der ganze Ablauf gegen einen ECHTEN Server, so wie die App ihn geht.

Anlass (Birk, 2026-09-01): Interview-Start/Stopp am Handy, und ein Foto
eroeffnet kein Interview mehr. Beides greift ineinander -- der Knopf ist nur
brauchbar, wenn `/api/state` danach wirklich den neuen Stand meldet, und das
Foto ist nur dann nicht verloren, wenn die Station vorher "nein" sagt.

Die Unit-Tests pruefen die Teile. Diese Probe faehrt die Reihenfolge, die am
Booth passiert, ueber echte Sockets:

    kein Interview -> Foto abgewiesen (409, keine Datei)
    Knopf "starten" -> /api/state meldet interview
    Foto -> angenommen, Portraet kommt an
    zweites Foto -> ersetzt, KEINE zweite Person
    Knopf "beenden" -> /api/state meldet kein Interview mehr
    Foto -> wieder abgewiesen

Absichtlich mit dem echten `Core` und nicht mit einer Attrappe: Die Frage,
ob ein Foto eine Person anlegt, entscheidet der SessionTracker im Worker --
ein CoreSpy wuerde genau die Entscheidung wegabstrahieren, um die es geht.
"""

import asyncio
import io
import json
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest
import uvicorn
from PIL import Image

from kg.bus import EventBus
from kg.config import Config
from kg.core import Core
from kg.embeddings import HashEmbedder
from kg.server import create_app
from kg.store import Store
from kg.transcript import TranscriptLog


def freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def jpeg_bytes(farbe=(140, 100, 70)) -> bytes:
    puffer = io.BytesIO()
    Image.new("RGB", (800, 600), farbe).save(puffer, format="JPEG")
    return puffer.getvalue()


def post(url: str, daten: bytes, typ: str) -> int:
    anfrage = urllib.request.Request(
        url, data=daten, method="POST", headers={"Content-Type": typ}
    )
    try:
        with urllib.request.urlopen(anfrage, timeout=20) as antwort:
            return antwort.status
    except urllib.error.HTTPError as fehler:
        return fehler.code


def hole(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=20) as antwort:
        return json.loads(antwort.read())


@pytest.fixture()
def station(tmp_path):
    """Echter uvicorn, echter Core, echter Worker -- wie am Ausstellungstag."""
    cfg = Config(data_dir=tmp_path / "state", interview_timeout_s=900)
    store = Store.open(cfg.db_path)
    core = Core(
        cfg=cfg,
        store=store,
        bus=EventBus(),
        transcript_log=TranscriptLog(cfg.transcript_log_path),
        llm=object(),
        embedder=HashEmbedder(dim=16),
        # Die Auswertung nach dem Schliessen ist hier nicht das Thema und
        # braucht ein Sprachmodell -- sie wird durch eine Leerfunktion
        # ersetzt, damit das Beenden nicht am fehlenden Netz haengt.
        processor=lambda *a, **k: None,
    )
    port = freier_port()

    server = uvicorn.Server(
        uvicorn.Config(
            create_app(store, cfg, core.bus, core=core),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    )

    # Der Worker MUSS laufen: Er verarbeitet die Warteschlange, in die
    # `on_mic_switch` und `on_photo` nur einlegen. Ohne ihn passierte gar
    # nichts, und der Test bewiese lediglich, dass HTTP antwortet.
    schleife = asyncio.new_event_loop()

    def fahre() -> None:
        asyncio.set_event_loop(schleife)
        schleife.create_task(core.run_worker())
        schleife.run_until_complete(server.serve())

    faden = threading.Thread(target=fahre, daemon=True)
    faden.start()

    frist = time.time() + 20
    while not server.started and time.time() < frist:
        time.sleep(0.05)
    assert server.started, "uvicorn kam nicht hoch"

    try:
        yield f"http://127.0.0.1:{port}", store, cfg
    finally:
        server.should_exit = True
        faden.join(timeout=10)
        store.close()


def warte_auf(bedingung, was: str, frist_s: float = 5.0) -> None:
    """Wartet, bis der Worker die Warteschlange abgearbeitet hat.

    Die Endpunkte kehren absichtlich sofort zurueck (der STT-Server darf nie
    auf eine Pipeline warten), der Zustand steht also einen Wimpernschlag
    spaeter. Warten statt schlafen: eine feste Pause waere auf einer
    beschaeftigten Maschine zu kurz und im Normalfall zu lang.
    """
    ende = time.time() + frist_s
    while time.time() < ende:
        if bedingung():
            return
        time.sleep(0.02)
    raise AssertionError(f"kam nicht: {was}")


def test_der_ganze_ablauf_vom_handy_aus(station):
    basis, store, cfg = station

    # 1. Kein Interview: Das Foto wird abgewiesen und hinterlaesst nichts.
    assert post(f"{basis}/api/photo", jpeg_bytes(), "image/jpeg") == 409
    assert hole(f"{basis}/api/state")["interview"] is None
    for ordner in (cfg.photo_dir, cfg.portrait_dir):
        if ordner.exists():
            assert list(ordner.glob("*")) == [], f"Waise in {ordner}"

    # 2. Der Knopf "Interview starten" -- derselbe Weg wie der Mikrofonschalter.
    assert post(
        f"{basis}/api/interview_switch",
        b'{"on":true,"source":"handy"}',
        "application/json",
    ) == 200
    warte_auf(lambda: store.open_person() is not None, "Interview geoeffnet")

    zustand = hole(f"{basis}/api/state")
    assert zustand["interview"] is not None, "die App saehe den Start nicht"
    person_id = store.open_person().id

    # 3. Jetzt geht das Foto durch.
    assert post(f"{basis}/api/photo", jpeg_bytes(), "image/jpeg") == 200
    warte_auf(
        lambda: store.open_person().portrait_path is not None, "Portraet gesetzt"
    )
    erstes = store.open_person().portrait_path

    # 4. Ein zweites Foto ersetzt das Bild -- und teilt das Interview NICHT.
    assert post(f"{basis}/api/photo", jpeg_bytes((30, 60, 90)), "image/jpeg") == 200
    warte_auf(
        lambda: store.open_person().portrait_path != erstes, "Portraet ersetzt"
    )
    offen = store.open_person()
    assert offen.id == person_id, "es wurde eine zweite Person angelegt"
    assert len(store.list_persons()) == 1, "das Interview wurde zerschnitten"

    # 5. Der Knopf "Interview beenden".
    assert post(
        f"{basis}/api/interview_switch",
        b'{"on":false,"source":"handy"}',
        "application/json",
    ) == 200
    warte_auf(lambda: store.open_person() is None, "Interview geschlossen")
    assert hole(f"{basis}/api/state")["interview"] is None

    # 6. Und danach wird wieder abgewiesen -- der Kreis schliesst sich.
    assert post(f"{basis}/api/photo", jpeg_bytes(), "image/jpeg") == 409
    assert len(store.list_persons()) == 1, "die Abweisung legte doch etwas an"
