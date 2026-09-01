"""Der Foto-Endpunkt der Android-App (`POST /api/photo`).

Der zweite Einwurf neben Telegram: die App im Tailnet legt die Bytes direkt
auf der Station ab, statt sie durch ein fremdes Netz zu schicken. Geprueft
wird hier genau das, was die App und der Betrieb davon brauchen -- dass ein
echtes Foto ein Interview eroeffnet, und dass alles andere abgewiesen wird,
BEVOR es auf der Platte landet.
"""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from kg.bus import EventBus
from kg.config import Config
from kg.server import MAX_PHOTO_BYTES, create_app
from kg.store import Store


class CoreSpy:
    """Nimmt entgegen, was `Core.on_photo` entgegennehmen wuerde.

    Absichtlich kein echter Core: geprueft wird der Endpunkt, nicht die
    Pipeline dahinter. Dass der echte Core dieselbe Signatur hat, haelt
    `test_die_signatur_passt_zum_echten_core` fest -- sonst waere dieser Spion
    genau die Art Attrappe, die gruen bleibt, waehrend die Station steht.
    """

    def __init__(self) -> None:
        self.aufrufe: list[tuple] = []

    def on_photo(self, photo_path, portrait_path, at: float) -> None:
        self.aufrufe.append((photo_path, portrait_path, at))


def jpeg_bytes(groesse: tuple[int, int] = (640, 480)) -> bytes:
    puffer = io.BytesIO()
    Image.new("RGB", groesse, (120, 90, 60)).save(puffer, format="JPEG")
    return puffer.getvalue()


def png_bytes(groesse: tuple[int, int] = (640, 480)) -> bytes:
    puffer = io.BytesIO()
    Image.new("RGB", groesse, (30, 60, 120)).save(puffer, format="PNG")
    return puffer.getvalue()


@pytest.fixture()
def umgebung(tmp_path):
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    # Seit 2026-09-01 nimmt `/api/photo` nur an, was zu einem LAUFENDEN
    # Interview gehoert (Birk: „ein foto duerfte eigentlich kein interview
    # mehr eroeffnen"). Die Faelle hier pruefen den Bildweg -- Format,
    # Groesse, Namensvergabe -- und brauchen dafuer ein offenes Interview,
    # so wie es am Booth der Schalter anlegt.
    store.create_person(started_at=100.0, photo_path=None, portrait_path=None)
    core = CoreSpy()
    app = create_app(store, cfg, EventBus(), core=core)
    with TestClient(app) as client:
        client.cfg = cfg
        client.core = core
        yield client
    store.close()


def test_ein_foto_erreicht_das_laufende_interview(umgebung):
    antwort = umgebung.post(
        "/api/photo", content=jpeg_bytes(), headers={"Content-Type": "image/jpeg"}
    )

    assert antwort.status_code == 200
    assert antwort.json()["ok"] is True
    assert len(umgebung.core.aufrufe) == 1

    photo_path, portrait_path, at = umgebung.core.aufrufe[0]
    assert photo_path.exists() and portrait_path.exists()
    assert at > 0


def test_das_portrait_wird_wirklich_erzeugt(umgebung):
    """Nicht nur \"eine Datei liegt da\" -- es muss ein Portrait sein.

    `make_portrait` schneidet quadratisch, legt den Goldring auf und speichert
    als RGBA-PNG in `cfg.portrait_size`. Wer hier nur auf Existenz prueft,
    merkt nicht, wenn statt des Portraits die Rohdatei kopiert wurde.
    """
    umgebung.post("/api/photo", content=jpeg_bytes((1600, 900)))

    _, portrait_path, _ = umgebung.core.aufrufe[0]
    with Image.open(portrait_path) as bild:
        assert bild.size == (umgebung.cfg.portrait_size, umgebung.cfg.portrait_size)
        assert bild.mode == "RGBA"  # der weiche Rand braucht den Alphakanal


def test_png_wird_ebenso_angenommen(umgebung):
    assert umgebung.post("/api/photo", content=png_bytes()).status_code == 200
    assert len(umgebung.core.aufrufe) == 1


def test_die_antwort_nennt_das_portrait_damit_die_app_es_zeigen_kann(umgebung):
    """Die App zeigt nach dem Ausloesen, wie die Station zugeschnitten hat.

    Dafuer braucht sie den Dateinamen -- und das Bild muss unter genau
    diesem Namen abrufbar sein, sonst zeigt die Vorschau nichts und niemand
    weiss warum.
    """
    antwort = umgebung.post("/api/photo", content=jpeg_bytes())

    name = antwort.json()["portrait"]
    assert name.endswith(".png")

    _, portrait_path, _ = umgebung.core.aufrufe[0]
    assert portrait_path.name == name
    # Unter diesem Namen holt die App es ab (`/media/portraits` ist gemountet).
    assert (umgebung.cfg.portrait_dir / name).exists()


def test_das_portrait_ist_ueber_media_abrufbar(umgebung):
    """Der Weg, den die Vorschau geht -- nicht nur der Name, sondern das Bild."""
    name = umgebung.post("/api/photo", content=jpeg_bytes()).json()["portrait"]

    geholt = umgebung.get(f"/media/portraits/{name}")

    assert geholt.status_code == 200
    assert geholt.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_ein_leerer_rumpf_wird_abgewiesen(umgebung):
    assert umgebung.post("/api/photo", content=b"").status_code == 400
    assert umgebung.core.aufrufe == []


def test_wer_kein_bild_schickt_bekommt_415_und_nichts_landet_auf_der_platte(umgebung):
    """Der Content-Type-Kopf ist eine Behauptung, die Magic Bytes sind das Bild.

    Genau der Fall aus dem Betrieb: ein Portal antwortet mit einer
    HTML-Fehlerseite, und die darf nie als `.jpg` im Fotoordner liegen.
    """
    antwort = umgebung.post(
        "/api/photo",
        content=b"<html>Anmeldung erforderlich</html>",
        headers={"Content-Type": "image/jpeg"},  # luegt bewusst
    )

    assert antwort.status_code == 415
    assert umgebung.core.aufrufe == []
    assert list(umgebung.cfg.photo_dir.iterdir()) == []


def test_ein_zu_grosses_bild_wird_abgewiesen_bevor_es_geschrieben_wird(umgebung):
    antwort = umgebung.post("/api/photo", content=b"\xff\xd8\xff" + b"\x00" * MAX_PHOTO_BYTES)

    assert antwort.status_code == 413
    assert umgebung.core.aufrufe == []
    assert list(umgebung.cfg.photo_dir.iterdir()) == []


def test_ein_kaputtes_jpeg_haelt_die_station_nicht_an(umgebung):
    """Richtige Magic Bytes, danach Muell -- Pillow scheitert beim Oeffnen.

    Die Station muss weiterlaufen und einen sprechenden Fehler zurueckgeben,
    statt den Prozess mit einem 500er zu quittieren.
    """
    antwort = umgebung.post("/api/photo", content=b"\xff\xd8\xff" + b"nicht wirklich ein bild")

    assert antwort.status_code == 422
    assert umgebung.core.aufrufe == []
    # Die Station antwortet weiterhin -- kein toter Prozess.
    assert umgebung.get("/api/state").status_code == 200


def test_zwei_fotos_ueberschreiben_einander_nicht(umgebung):
    """Der Dateiname wird hier vergeben, und zwei Fotos in derselben Sekunde
    sind am Booth der Normalfall, nicht der Sonderfall."""
    umgebung.post("/api/photo", content=jpeg_bytes())
    umgebung.post("/api/photo", content=jpeg_bytes())

    pfade = {aufruf[0] for aufruf in umgebung.core.aufrufe}
    assert len(umgebung.core.aufrufe) == 2
    assert len(pfade) == 2, "beide Fotos muessen als eigene Datei existieren"
    assert all(p.exists() for p in pfade)


def test_der_client_bestimmt_den_dateinamen_nicht(umgebung):
    """Ein Client-Name waere ein Pfad-Injektions-Vektor.

    Die App schickt rohe Bytes, aber ein spaeterer Client koennte einen Namen
    mitzuschicken versuchen. Er darf nirgends einwirken -- weder als Pfad noch
    als Namensteil.
    """
    umgebung.post(
        "/api/photo",
        content=jpeg_bytes(),
        headers={
            "Content-Type": "image/jpeg",
            "Content-Disposition": 'attachment; filename="../../../../tmp/uebernommen.jpg"',
            "X-Filename": "../../uebernommen.jpg",
        },
    )

    photo_path, _, _ = umgebung.core.aufrufe[0]
    assert photo_path.parent == umgebung.cfg.photo_dir
    assert "uebernommen" not in photo_path.name
    assert ".." not in photo_path.name


def test_ohne_core_gibt_es_den_endpunkt_gar_nicht(tmp_path):
    """Die reine Anzeige-Konfiguration hat keinen Einwurf -- besser ein 404
    als eine 200, die nichts tut."""
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    app = create_app(store, cfg, EventBus())  # ohne core

    with TestClient(app) as client:
        assert client.post("/api/photo", content=jpeg_bytes()).status_code == 404
    store.close()


def test_die_signatur_passt_zum_echten_core():
    """Der Spion oben darf nicht von der echten Schnittstelle abweichen.

    Ohne diese Pruefung bliebe die ganze Datei gruen, waehrend `Core.on_photo`
    laengst eine andere Signatur hat und die Station beim ersten Foto steht.
    """
    import inspect

    from kg.core import Core

    echt = inspect.signature(Core.on_photo)
    spion = inspect.signature(CoreSpy.on_photo)
    assert list(echt.parameters) == list(spion.parameters)
