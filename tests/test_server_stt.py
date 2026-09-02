"""Die zwei Routen, an denen das Bedienpult die Spracherkennung sieht und schaltet.

🔴 Warum es sie gibt (2026-09-02): Bei einem Whisper-Ausfall bei Infomaniak sah
im Bedienpult alles gut aus — das STT-Abzeichen war grün, weil die Verbindung
zum Dienst auf 5051 tatsächlich stand. Nur verstand niemand ein Wort. Die
Antwort auf „steht der Draht" ist nicht die Antwort auf „kommt Text an".
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kg import stt_health
from kg.bus import EventBus
from kg.config import Config
from kg.server import create_app
from kg.store import Store


@pytest.fixture()
def bausatz(tmp_path):
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    yield store, cfg
    store.close()


def _klient(bausatz, aufsicht=None):
    store, cfg = bausatz
    return TestClient(create_app(store, cfg, EventBus(), stt_aufsicht=aufsicht))


class _Aufsicht:
    def __init__(self, gesund, anbieter="infomaniak", meldung="egal"):
        self.gesund, self.anbieter, self.meldung = gesund, anbieter, meldung

    def als_dict(self):
        return {
            "anbieter": self.anbieter,
            "anbieter_moeglich": list(stt_health.ANBIETER),
            "infomaniak": stt_health.Befund(self.gesund, self.meldung, 100.0).als_dict(),
        }


def test_ohne_aufsicht_sagt_die_route_das_und_behauptet_kein_ok(bausatz):
    """🔴 Keine Auskunft ist etwas anderes als eine gute Auskunft.

    Ohne API-Schlüssel läuft keine Aufsicht. Würde die Route dann `gesund:
    true` liefern, hinge im Bedienpult eine grüne Lampe, die nie etwas
    gemessen hat — genau die stille Falle, gegen die diese Anzeige gebaut ist.
    """
    antwort = _klient(bausatz).get("/api/stt").json()
    assert antwort["aufsicht"] is False
    assert antwort["infomaniak"]["gesund"] is None


def test_der_befund_kommt_unveraendert_durch(bausatz):
    antwort = _klient(bausatz, _Aufsicht(False, meldung="service unavailable")).get("/api/stt").json()
    assert antwort["aufsicht"] is True
    assert antwort["infomaniak"]["gesund"] is False
    assert "service unavailable" in antwort["infomaniak"]["meldung"]


def test_ein_fremder_anbietername_wird_abgewiesen(bausatz, monkeypatch):
    """Der Wert entscheidet, welcher Prozess startet. Er wird gegen die Liste
    geprüft, bevor irgendetwas passiert."""
    gerufen = []
    monkeypatch.setattr(stt_health, "wechsle", lambda *a, **k: gerufen.append(a))
    antwort = _klient(bausatz).post("/api/stt/anbieter", json={"anbieter": "boesewicht"})
    assert antwort.status_code == 400
    assert gerufen == []


def test_ein_gueltiger_wechsel_geht_durch(bausatz, monkeypatch):
    gerufen = {}

    def falscher_wechsel(anbieter, *, repo, **_k):
        gerufen["anbieter"] = anbieter
        gerufen["repo"] = repo
        return {"anbieter": anbieter, "beendet": [7], "pid": 42, "log": "/dev/null"}

    monkeypatch.setattr(stt_health, "wechsle", falscher_wechsel)
    antwort = _klient(bausatz).post("/api/stt/anbieter", json={"anbieter": "elevenlabs"})
    assert antwort.status_code == 200
    assert antwort.json()["ok"] is True
    assert gerufen["anbieter"] == "elevenlabs"
    # Der Pfad kommt aus dem Modul, nicht aus der Anfrage.
    assert (gerufen["repo"] / "scripts" / "start-stt-mac.sh").is_file()


def test_ein_gescheiterter_wechsel_wird_gemeldet_statt_verschluckt(bausatz, monkeypatch):
    """Ein Knopf, dessen Wirkung im Nebenraum stattfindet, ist ohne Rückmeldung
    nicht von einem Druck ins Leere zu unterscheiden."""
    def kaputt(*_a, **_k):
        raise FileNotFoundError("scripts/start-stt-mac.sh fehlt")

    monkeypatch.setattr(stt_health, "wechsle", kaputt)
    antwort = _klient(bausatz).post("/api/stt/anbieter", json={"anbieter": "infomaniak"})
    assert antwort.status_code == 500
    assert "start-stt-mac.sh" in antwort.json()["detail"]
