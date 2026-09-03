"""Das ausgeloeste Satzende (`kg.vad_satzende`).

🔴 WARUM DIESE TESTS SCHARF SEIN MUESSEN: Der benutzte Endpunkt des fremden
Dienstes schreibt die VAD-Schwelle IN SEINE SETTINGS-DATEI. Bleibt das
Zuruecksetzen aus, ist das Mikrofon dauerhaft taub — ueber Neustarts hinweg,
und ohne dass irgendein Bildschirm es zeigt: Der Pegel schlaegt weiter aus,
das STT-Abzeichen bleibt gruen, und es kommt kein Wort an. Das ist exakt der
Ausfall vom Morgen des 2026-09-02, nur selbstgemacht.

Jeder Test hier fragt deshalb dieselbe Frage: Steht die Schwelle danach wieder
unten?
"""

from __future__ import annotations

import httpx
import pytest

from kg.vad_satzende import (
    RUECKFALL_SCHWELLE,
    STILLE_SCHWELLE,
    VERDACHT_AB,
    pruefe_und_repariere,
    satzende_ausloesen,
)

BASIS = "http://stt.test"


class Dienst:
    """Ein STT-Dienst als Attrappe. `stoere_ab` laesst den n-ten POST scheitern."""

    def __init__(self, schwelle=0.0066, stoere_ab=None):
        self.schwelle = schwelle
        self.verlauf: list[float] = []
        self.stoere_ab = stoere_ab
        self.posts = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/levels":
            return httpx.Response(200, json={"vad_energy_threshold": self.schwelle})
        if request.url.path == "/vad_threshold":
            self.posts += 1
            if self.stoere_ab is not None and self.posts >= self.stoere_ab:
                raise httpx.ConnectError("Verbindung weg", request=request)
            import json as _json

            wert = _json.loads(request.content)["value"]
            self.schwelle = wert
            self.verlauf.append(wert)
            return httpx.Response(200, json={"value": wert})
        return httpx.Response(404)


@pytest.fixture
def dienst(monkeypatch):
    def bauen(schwelle=0.0066, stoere_ab=None):
        d = Dienst(schwelle, stoere_ab)
        echt = httpx.AsyncClient

        def gefaelscht(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(d.handler)
            return echt(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", gefaelscht)
        return d

    return bauen


async def test_die_schwelle_geht_hoch_und_wieder_zurueck(dienst):
    """Der ganze Zweck in einem Test: kurz taub, dann wieder wie vorher."""
    d = dienst(schwelle=0.0066)

    assert await satzende_ausloesen(BASIS) is True

    assert d.verlauf == [STILLE_SCHWELLE, 0.0066], d.verlauf
    assert d.schwelle == 0.0066, "die alte Schwelle wurde nicht wiederhergestellt"


async def test_die_schwelle_kommt_auch_zurueck_wenn_das_warten_kracht(dienst):
    """🔴 Der Fall, der das Mikrofon taub zuruecklaesst.

    Zwischen Anheben und Zuruecksetzen liegt eine Wartezeit. Wird der Kern
    genau dort abgeraeumt oder wirft irgendetwas, MUSS das `finally` greifen."""
    d = dienst(schwelle=0.0066)

    async def krachendes_schlafen(_s):
        raise RuntimeError("abgeraeumt")

    # Kein `pytest.raises`: Die Funktion faengt bewusst alles ab (ein Absturz
    # im Kern kostet den Abend). Geprueft wird das, worauf es ankommt — dass
    # das `finally` VOR dem Fangen gelaufen ist.
    assert await satzende_ausloesen(BASIS, schlafen=krachendes_schlafen) is False

    assert d.schwelle == 0.0066, (
        f"die Schwelle blieb bei {d.schwelle} stehen — das Mikrofon waere taub"
    )


async def test_eine_steckengebliebene_schwelle_wird_nicht_noch_hoeher_gedreht(dienst):
    """Stand sie schon oben, hat ein frueherer Lauf sie stehen lassen. Dann
    wird sie zurueckgesetzt statt erneut angehoben — sonst schriebe jeder
    weitere Versuch den kaputten Zustand fest."""
    d = dienst(schwelle=STILLE_SCHWELLE)

    assert await satzende_ausloesen(BASIS) is False
    assert d.schwelle == RUECKFALL_SCHWELLE, d.schwelle
    assert STILLE_SCHWELLE not in d.verlauf, "sie wurde noch einmal angehoben"


async def test_ein_toter_dienst_bringt_den_kern_nicht_um(dienst):
    """Ein misslungenes Satzende kostet den letzten Satz. Ein Absturz im Kern
    kostet den Abend."""
    d = dienst(schwelle=0.0066, stoere_ab=1)

    assert await satzende_ausloesen(BASIS) is False
    assert d.schwelle == 0.0066


async def test_der_start_repariert_eine_stehengebliebene_schwelle(dienst):
    """Ein Tag, der mit tauben Mikrofon beginnt, sieht auf jedem Bildschirm
    gesund aus. Deshalb wird beim Start nachgesehen."""
    d = dienst(schwelle=STILLE_SCHWELLE)

    assert await pruefe_und_repariere(BASIS) is True
    assert d.schwelle == RUECKFALL_SCHWELLE


async def test_der_start_fasst_eine_gesunde_schwelle_nicht_an(dienst):
    """Die Gegenprobe. Ein Startcheck, der immer schreibt, ueberschriebe jede
    Einstellung, die jemand am Bedienpult des STT-Dienstes gemacht hat."""
    d = dienst(schwelle=0.0066)

    assert await pruefe_und_repariere(BASIS) is False
    assert d.verlauf == [], "beim Start wurde ungefragt geschrieben"
    assert 0.0066 < VERDACHT_AB
