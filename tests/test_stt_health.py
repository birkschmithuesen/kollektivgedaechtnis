"""Die Aufsicht über die Spracherkennung.

🔴 WAS HIER WIRKLICH GEPRÜFT WIRD (2026-09-02, am Gerät passiert):
Infomaniaks Whisper fiel aus. Der STT-Dienst lief weiter, `/status` sagte
„running", das Mikrofongate öffnete, ein Interview begann — und es kam kein
einziges Wort an. 26 Äußerungen, 0 Transkripte.

Der Grund, warum es so lange dauerte, das zu sehen: Das bloße ABSENDEN
lieferte zeitweise HTTP 200 (gemessen: 6 von 8), obwohl nie ein Ergebnis kam.
Eine Prüfung, die nach dem Absenden aufhört, meldet in genau diesem Fall
„alles gut". Deshalb ist `test_ein_erfolgreiches_absenden_allein_reicht_nicht`
der wichtigste Test dieser Datei.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kg import stt_health


# --- Hilfen, damit kein Test ins Netz geht -----------------------------------


def _absender(*antworten):
    """Gibt der Reihe nach die vorgegebenen Antworten zurück."""
    rest = list(antworten)

    def absenden(**_kwargs):
        return rest.pop(0) if rest else rest_letzte

    rest_letzte = antworten[-1] if antworten else {}
    return absenden


def _abholer(*antworten):
    rest = list(antworten)
    letzte = antworten[-1] if antworten else {}

    def abholen(**_kwargs):
        return rest.pop(0) if rest else letzte

    return abholen


def _uhr():
    """Eine Uhr, die bei jedem Blick eine Sekunde weiterläuft."""
    stand = {"t": 1000.0}

    def jetzt():
        stand["t"] += 1.0
        return stand["t"]

    return jetzt


# --- Die Probe ---------------------------------------------------------------


def test_die_ganze_kette_traegt():
    befund = stt_health.pruefe_infomaniak(
        api_key="k",
        absenden=_absender({"batch_id": "b1"}),
        abholen=_abholer({"data": {"status": "ok", "text": ""}}),
        schlafen=lambda _s: None,
        jetzt=_uhr(),
    )
    assert befund.gesund is True
    assert befund.meldung == "antwortet"


def test_ein_erfolgreiches_absenden_allein_reicht_nicht():
    """🔴 DER TEST, DER DEN AUSFALL VOM 2026-09-02 GEFUNDEN HÄTTE.

    Das Absenden gelingt und liefert eine `batch_id` — genau das Bild, das an
    diesem Morgen 6 von 8 Versuchen boten. Das Ergebnis kommt aber nie über
    `processing` hinaus. Eine Aufsicht, die hier `gesund` meldet, ist eine
    grüne Lampe über einem toten Dienst, und das ist schlimmer als gar keine
    Lampe: Sie lenkt die Suche eine Viertelstunde lang in die falsche Ecke.
    """
    befund = stt_health.pruefe_infomaniak(
        api_key="k",
        absenden=_absender({"batch_id": "b1"}),
        abholen=_abholer({"data": {"status": "processing"}}),
        versuche=3,
        warten_s=1.0,
        schlafen=lambda _s: None,
        jetzt=_uhr(),
    )
    assert befund.gesund is False
    assert "3 s" in befund.meldung


def test_eine_html_fehlerseite_wird_lesbar_gemeldet():
    """Infomaniak antwortete mit einer HTML-Seite statt mit JSON.

    Die Meldung landet unverkürzt im Bedienpult. Ohne den Rohtext stünde dort
    nur „keine batch_id" und niemand wüsste, ob der Schlüssel falsch war, der
    Dienst weg oder das Netz tot.
    """
    befund = stt_health.pruefe_infomaniak(
        api_key="k",
        absenden=_absender({"_roh": "<!DOCTYPE html> Infomaniak - service unavailable"}),
        abholen=_abholer({}),
        jetzt=_uhr(),
    )
    assert befund.gesund is False
    assert "service unavailable" in befund.meldung


def test_eine_netzstoerung_beim_absenden_reisst_nichts_mit():
    def absenden(**_kwargs):
        raise ConnectionError("peer closed connection")

    befund = stt_health.pruefe_infomaniak(
        api_key="k", absenden=absenden, abholen=_abholer({}), jetzt=_uhr()
    )
    assert befund.gesund is False
    assert "peer closed connection" in befund.meldung


def test_ohne_schluessel_meldet_sie_das_und_ruft_nicht_an():
    gerufen = []

    def absenden(**_kwargs):
        gerufen.append(1)
        return {}

    befund = stt_health.pruefe_infomaniak(
        api_key="", absenden=absenden, abholen=_abholer({}), jetzt=_uhr()
    )
    assert befund.gesund is False
    assert "Schlüssel" in befund.meldung
    assert gerufen == [], "ohne Schlüssel darf kein Aufruf hinausgehen"


def test_ungeprueft_ist_nicht_ungesund():
    """🔴 Drei Lagen, nicht zwei.

    Zwischen Programmstart und erster Probe weiß die Aufsicht nichts. `None`
    heißt „noch nicht geprüft"; wer das zu `False` verdichtet, hängt beim
    Aufschlagen der Seite eine rote Lampe hin, die nichts bedeutet — und rote
    Lampen, die immer leuchten, sieht nach einer Stunde niemand mehr.
    """
    assert stt_health.UNGEPRUEFT.gesund is None
    d = stt_health.UNGEPRUEFT.als_dict(jetzt=5.0)
    assert d["gesund"] is None
    assert d["geprueft_vor_s"] is None


def test_der_geprueft_pfad_ist_der_von_whisper_nicht_der_vom_llm():
    """🔴 `/1/…` für Sprache, `/2/…` für Text.

    Am 2026-09-02 lief das LLM unter `/2/` tadellos, während Whisper unter
    `/1/` tot war. Wer hier den LLM-Pfad einsetzt, misst dauerhaft den
    falschen Dienst und meldet „gesund", während niemand verstanden wird.
    """
    assert "/1/ai/" in stt_health.ABSENDEN
    assert "/2/" not in stt_health.ABSENDEN
    assert "audio/transcriptions" in stt_health.ABSENDEN


def test_die_probe_ist_eine_gueltige_wav_datei():
    roh = stt_health.probe_wav(sekunden=0.1)
    assert roh[:4] == b"RIFF" and roh[8:12] == b"WAVE"
    # Klein genug, dass ein Minutentakt nicht ins Gewicht fällt.
    assert len(roh) < 20_000


# --- Wer läuft gerade? -------------------------------------------------------


class _Lauf:
    """Ein Ersatz für `subprocess.run`, der vorgegebene Ausgaben liefert."""

    def __init__(self, **ausgaben):
        self.ausgaben = ausgaben
        self.aufrufe = []

    def __call__(self, argumente, **_kwargs):
        self.aufrufe.append(argumente)
        for schluessel, text in self.ausgaben.items():
            if schluessel in " ".join(argumente):
                return type("E", (), {"stdout": text, "returncode": 0})()
        return type("E", (), {"stdout": "", "returncode": 0})()


def test_der_laufende_anbieter_wird_nachgesehen_nicht_gemerkt():
    lauf = _Lauf(**{
        "lsof": "4711\n",
        "ps": "/…/venv/bin/python -m fundusapps.stt_server --language de "
              "elevenlabs-scribe --api-key-env ELEVENLABS_API_KEY --mic-gate\n",
    })
    assert stt_health.laufender_anbieter(lauf=lauf) == "elevenlabs"


def test_niemand_am_port_heisst_unbekannt_nicht_infomaniak():
    """`None` ist eine eigene Auskunft. Das Bedienpult sperrt darauf hin den
    Wechselknopf — ein Wechsel „weg von unbekannt" wäre ein Neustart auf
    Verdacht, womöglich mitten in einem laufenden Interview."""
    assert stt_health.laufender_anbieter(lauf=_Lauf()) is None


def test_ein_unbekanntes_backend_heisst_auch_unbekannt():
    lauf = _Lauf(**{"lsof": "4711\n", "ps": "python -m irgendwas --anders\n"})
    assert stt_health.laufender_anbieter(lauf=lauf) is None


# --- Der Wechsel -------------------------------------------------------------


class _Starter:
    def __init__(self):
        self.aufrufe = []

    def __call__(self, argumente, **kwargs):
        self.aufrufe.append((argumente, kwargs))
        return type("P", (), {"pid": 4242})()


def test_ein_fremder_name_erreicht_niemals_einen_prozess(tmp_path):
    """Der Wert kommt aus einer HTTP-Anfrage und entscheidet, was gestartet
    wird. Er wird gegen eine Liste geprüft, nicht bereinigt."""
    starter = _Starter()
    with pytest.raises(ValueError):
        stt_health.wechsle("; rm -rf /", repo=tmp_path, lauf=_Lauf(), starte=starter)
    assert starter.aufrufe == []


def test_der_wechsel_setzt_kg_stt_und_startet_das_bekannte_skript(tmp_path):
    (tmp_path / "scripts").mkdir()
    skript = tmp_path / stt_health.STARTSKRIPT
    skript.write_text("#!/bin/sh\n")
    starter = _Starter()
    ergebnis = stt_health.wechsle(
        "elevenlabs",
        repo=tmp_path,
        log_datei=tmp_path / "stt.log",
        lauf=_Lauf(**{"lsof": "999\n"}),
        starte=starter,
    )
    (argumente, kwargs), = starter.aufrufe
    assert argumente == [str(skript)], "der Pfad steht im Code, nicht in der Anfrage"
    assert kwargs["env"]["KG_STT"] == "elevenlabs"
    # Die Vorabprobe im Skript würde bis zu 20 s warten; der Kern weiß es
    # ohnehin besser, und ein Knopf, der eine halbe Minute hängt, wirkt kaputt.
    assert kwargs["env"]["KG_STT_PROBE"] == "0"
    assert ergebnis["beendet"] == [999], "der alte Dienst muss den Port hergeben"


def test_der_alte_dienst_wird_ueber_den_port_beendet_nicht_ueber_den_namen(tmp_path):
    """🔴 macOS nennt das Binary `Python` mit großem P und `uv run` schiebt
    einen weiteren Prozess davor. Ein `pkill -f "python -m …"` trifft den
    Mantel und lässt den Dienst am Leben — er hält dann Port oder Mikrofon
    besetzt, und der neue findet beides belegt (am 2026-09-01 real passiert,
    siehe `scripts/stop-station.sh`)."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / stt_health.STARTSKRIPT).write_text("#!/bin/sh\n")
    lauf = _Lauf(**{"lsof": "31337\n"})
    stt_health.wechsle(
        "infomaniak", repo=tmp_path, log_datei=tmp_path / "l.log",
        lauf=lauf, starte=_Starter(),
    )
    befehle = [" ".join(a) for a in lauf.aufrufe]
    assert any(b.startswith("lsof") and "5051" in b for b in befehle), befehle
    assert any(b == "kill 31337" for b in befehle), befehle
    assert not any("pkill" in b for b in befehle), befehle


def test_ohne_startskript_bricht_er_ab_statt_ins_leere_zu_greifen(tmp_path):
    with pytest.raises(FileNotFoundError):
        stt_health.wechsle("infomaniak", repo=tmp_path, lauf=_Lauf(), starte=_Starter())


# --- Die Aufsicht als Ganzes -------------------------------------------------


def test_eine_werfende_probe_reisst_die_aufsicht_nicht_um():
    """Sie läuft eine Ausstellung lang. Eine Ausnahme, die den Task beendet,
    hinterlässt eine Anzeige, die für immer den letzten Stand zeigt."""
    import asyncio

    def kaputt():
        raise RuntimeError("Netz weg")

    aufsicht = stt_health.Aufsicht(api_key="k", repo=Path("."), takt_s=0.0, probe=kaputt)

    async def eine_runde():
        aufgabe = asyncio.create_task(aufsicht.lauf())
        await asyncio.sleep(0.05)
        aufgabe.cancel()

    asyncio.run(eine_runde())
    assert aufsicht.befund.gesund is False
    assert "Netz weg" in aufsicht.befund.meldung


def test_eine_unerwartete_antwortform_bringt_die_aufsicht_nicht_um():
    """🔴 Real passiert, 2026-09-02 09:20: Unter `data` kam ein STRING zurueck.

    `daten.get(...)` warf `'str' object has no attribute 'get'`, die Ausnahme
    verliess `pruefe_infomaniak`, und im Bedienpult stand daraufhin ein Fehler,
    der nicht der des Anbieters war — die Aufsicht meldete ihre eigene Panne
    als dessen Ausfall. Genau dann, wenn der Anbieter sich seltsam verhaelt,
    darf die Messung nicht mitgehen.
    """
    for kaputt in ({"data": "processing"}, "einfach ein String", None, {"data": None}, []):
        befund = stt_health.pruefe_infomaniak(
            api_key="k",
            absenden=_absender({"batch_id": "b1"}),
            abholen=_abholer(kaputt),
            versuche=1, warten_s=0.0,
            schlafen=lambda _s: None, jetzt=_uhr(),
        )
        assert befund.gesund is False, kaputt
        assert "object has no attribute" not in befund.meldung, kaputt


def test_auch_eine_html_antwort_beim_absenden_wirft_nicht():
    """Kein `batch_id`, weil die Antwort gar kein Objekt ist."""
    befund = stt_health.pruefe_infomaniak(
        api_key="k", absenden=_absender("<!DOCTYPE html>"), abholen=_abholer({}), jetzt=_uhr()
    )
    assert befund.gesund is False
    assert "DOCTYPE" in befund.meldung
