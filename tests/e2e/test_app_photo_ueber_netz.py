"""End-to-End: ein echtes HTTP-POST auf einen laufenden Server.

Der TestClient in `test_server_photo.py` umgeht den Netzweg -- er ruft die
App in-process auf. Diese Probe startet uvicorn wirklich, schickt echte Bytes
ueber einen Socket und prueft, was die App danach tatsaechlich getan hat.

Damit ist genau der Pfad belegt, den die Android-App geht, und nicht ein
bequemer Nachbar davon: Socket -> uvicorn -> FastAPI -> make_portrait ->
Core.on_photo.
"""

import io
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
from kg.server import create_app
from kg.store import Store


class CoreSpy:
    def __init__(self) -> None:
        self.aufrufe: list[tuple] = []

    def on_photo(self, photo_path, portrait_path, at: float) -> None:
        self.aufrufe.append((photo_path, portrait_path, at))


def freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def jpeg_bytes(groesse=(800, 600)) -> bytes:
    puffer = io.BytesIO()
    Image.new("RGB", groesse, (140, 100, 70)).save(puffer, format="JPEG")
    return puffer.getvalue()


@pytest.fixture()
def station(tmp_path):
    """Ein echter uvicorn auf einem echten Port, wie am Ausstellungstag."""
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    # Seit 2026-09-01 nimmt `/api/photo` nur an, was zu einem LAUFENDEN
    # Interview gehoert -- ein Foto eroeffnet keins mehr. Der Store bekommt
    # deshalb eine offene Person, so wie sie am Booth der Schalter anlegt.
    # Bewusst ueber den Store und nicht ueber den CoreSpy: die Route fragt den
    # Store, und eine Attrappe, die "ja" sagt, waere kein Beleg.
    store.create_person(started_at=100.0, photo_path=None, portrait_path=None)
    core = CoreSpy()
    port = freier_port()

    server = uvicorn.Server(
        uvicorn.Config(
            create_app(store, cfg, EventBus(), core=core),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    )
    faden = threading.Thread(target=server.run, daemon=True)
    faden.start()

    frist = time.time() + 20
    while not server.started and time.time() < frist:
        time.sleep(0.05)
    assert server.started, "uvicorn kam nicht hoch"

    try:
        yield f"http://127.0.0.1:{port}", core, cfg
    finally:
        server.should_exit = True
        faden.join(timeout=10)
        store.close()


def post(url: str, daten: bytes) -> int:
    anfrage = urllib.request.Request(
        url, data=daten, method="POST", headers={"Content-Type": "image/jpeg"}
    )
    try:
        with urllib.request.urlopen(anfrage, timeout=20) as antwort:
            return antwort.status
    except urllib.error.HTTPError as fehler:
        return fehler.code


def test_ein_foto_ueber_das_netz_erreicht_das_laufende_interview(station):
    basis, core, cfg = station

    assert post(f"{basis}/api/photo", jpeg_bytes()) == 200

    assert len(core.aufrufe) == 1
    _, portrait_path, _ = core.aufrufe[0]
    with Image.open(portrait_path) as bild:
        assert bild.size == (cfg.portrait_size, cfg.portrait_size)


def test_ohne_laufendes_interview_wird_das_foto_abgewiesen(tmp_path):
    """🔴 Der Kern der Umstellung vom 2026-09-01 (Birk: „ein foto duerfte
    eigentlich kein interview mehr eroeffnen").

    Zwei Zusagen in einem Test, und die zweite ist die wichtigere:

    1. Die Station sagt **409** statt "ok". Am Booth ist das der Unterschied
       zwischen "ich habe es gesehen" und "ich dachte, es sei angekommen".
    2. Es entsteht **keine Datei**. Ein Portraet, das zu keiner Person gehoert,
       waere ein Gesicht auf der Platte, das niemand mehr zuordnet und
       niemand aufraeumt -- bei einer Arbeit ueber Datensouveraenitaet nicht
       hinnehmbar. Deshalb prueft dieser Test die Verzeichnisse und nicht nur
       den Statuscode.

    Eigene Station ohne offene Person: die `station`-Fixture legt bewusst eine
    an, und ein Test, der die Abwesenheit prueft, darf sich die nicht
    wegdenken muessen.
    """
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    core = CoreSpy()
    port = freier_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(store, cfg, EventBus(), core=core),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    )
    faden = threading.Thread(target=server.run, daemon=True)
    faden.start()
    frist = time.time() + 20
    while not server.started and time.time() < frist:
        time.sleep(0.05)
    assert server.started, "uvicorn kam nicht hoch"

    try:
        assert post(f"http://127.0.0.1:{port}/api/photo", jpeg_bytes()) == 409
        assert core.aufrufe == [], "das Foto wurde trotzdem weitergereicht"
        for ordner in (cfg.photo_dir, cfg.portrait_dir):
            liegengeblieben = list(ordner.glob("*")) if ordner.exists() else []
            assert liegengeblieben == [], f"Waise in {ordner}: {liegengeblieben}"
    finally:
        server.should_exit = True
        faden.join(timeout=10)
        store.close()


def test_die_station_bleibt_nach_einer_abweisung_bedienbar(station):
    """Der Fall aus dem Flur: irgendetwas Falsches kommt an, und danach muss
    das naechste echte Foto trotzdem durchgehen."""
    basis, core, _ = station

    assert post(f"{basis}/api/photo", b"<html>kein bild</html>") == 415
    assert core.aufrufe == []

    assert post(f"{basis}/api/photo", jpeg_bytes()) == 200
    assert len(core.aufrufe) == 1


def test_zehn_fotos_hintereinander_gehen_alle_durch(station):
    """Am Booth kommen Fotos in Folge, nicht einzeln.

    Prueft zugleich, dass die Namensvergabe unter echtem Zeitverlauf
    kollisionsfrei bleibt -- der TestClient ist dafuer zu schnell, um
    aussagekraeftig zu sein.
    """
    basis, core, _ = station

    for _ in range(10):
        assert post(f"{basis}/api/photo", jpeg_bytes()) == 200

    assert len(core.aufrufe) == 10
    pfade = {aufruf[0] for aufruf in core.aufrufe}
    assert len(pfade) == 10, "Fotos haben einander ueberschrieben"
