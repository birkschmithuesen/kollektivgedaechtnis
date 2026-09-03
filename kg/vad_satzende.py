"""Ein Satzende beim Spracherkenner ausloesen, ohne auf eine Sprechpause zu warten.

🔴 WARUM ES DIESE DATEI GIBT (Birk, 2026-09-02, am Ausstellungstag):

    „Fuer die STT hat das mit den 8 sec Wartezeit nicht gereicht. Das Problem
     ist der VAD. Wenn keine Stille kommt, weil weiter geredet wird, wird das
     Letztgesagte trotzdem nicht genommen. Sobald der Stop-Button gedrueckt
     wird, muss also der Eingangspegel runter, oder besser automatisch ein
     Satzende-Signal (was VAD macht) gesendet werden."

Der Befund stimmt und ist im fremden Dienst nachlesbar: Der VAD schliesst
einen Turn erst ab, wenn die Stille laenger als `vad_min_silence_ms` dauert —
bei Infomaniak 700 ms (`fundusapps/stt_server/args.py:199`). Wird durchgeredet,
kommt dieser Moment nie, und der Chunk bleibt im Puffer. Blosses Warten hilft
dagegen nichts; deshalb reichten die 8 Sekunden Nachlauf im Bedienpult nicht.

## Warum nicht `/pause`

`sr.py:499` setzt nur `_mute` auf den Erkenner-Threads. Der laufende Chunk
wird damit VERWORFEN, nicht abgeschlossen — das haette den letzten Satz sicher
zerstoert statt ihn zu retten. Genau das Gegenteil des Gewollten.

## Der Weg: die VAD-Schwelle kurz anheben

`POST /vad_threshold` wirkt laut fremder Doku „on the running chunkers
immediately". Steht die Schwelle kurz ueber jedem real vorkommenden Pegel,
sieht der VAD Stille, loest nach `vad_min_silence_ms` sein `speech_end` aus und
schickt den Chunk zur Transkription. Das ist Birks „automatisch ein
Satzende-Signal senden", gebaut aus dem, was der fremde Dienst schon anbietet —
ohne eine Zeile in `fundusbot` zu aendern (Projektregel: kein Fork).

## 🔴 Die Gefahr, und warum das hier und nicht im Browser steht

Derselbe Endpunkt schreibt den Wert IN DIE SETTINGS-DATEI des fremden Dienstes
(„is written to the settings file (so a restart keeps it)"). Bleibt das
Zuruecksetzen aus, ist das Mikrofon DAUERHAFT taub — auch ueber einen Neustart
hinweg. Das ist das teuerste Fehlerbild dieser Station: alles sieht gut aus,
der Pegel schlaegt aus, und es kommt kein Wort an. Genau der Ausfall vom
Morgen des 2026-09-02.

Deshalb drei Vorkehrungen:

1. Das Zuruecksetzen steht in einem `finally` und laeuft auch, wenn das Warten
   oder der Aufruf dazwischen scheitert.
2. Der alte Wert wird VORHER gelesen und nur ein plausibler Wert wieder
   gesetzt; wurde er nie gelesen, gilt `RUECKFALL_SCHWELLE`.
3. `pruefe_und_repariere()` gehoert beim Start des Kerns aufgerufen: Steht die
   Schwelle absurd hoch, hat ein frueherer Lauf sie stehen lassen — dann wird
   sie zurueckgesetzt, statt den Tag mit einem tauben Mikrofon zu beginnen.

Ein Browser koennte Punkt 1 nicht zusagen: Wer das Bedienpult in der falschen
Sekunde schliesst, liesse den Dienst taub zurueck.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

log = logging.getLogger(__name__)

#: Weit ueber jedem Pegel, den ein Mikrofon im Raum liefert (gemessen am
#: 2026-09-02: Sprache 0,001–0,01, Schwelle 0,0066). 1.0 ist der Vollausschlag
#: eines normalisierten Signals — darueber gibt es nichts.
STILLE_SCHWELLE = 1.0

#: Falls die alte Schwelle nicht gelesen werden konnte. Der Vorgabewert des
#: fremden Dienstes fuer Infomaniak-Whisper; lieber ein etwas falscher Wert als
#: ein taubes Mikrofon.
RUECKFALL_SCHWELLE = 0.0023

#: Ab hier gilt eine Schwelle als „steckengeblieben". Deutlich ueber jedem
#: sinnvollen Betriebswert und deutlich unter `STILLE_SCHWELLE`.
VERDACHT_AB = 0.5

#: Wie lange die Schwelle oben bleibt. `vad_min_silence_ms` ist 700 ms
#: (Infomaniak) bzw. 500 ms (lokales Whisper); 900 ms geben dem langsameren
#: Fall Luft, ohne den Menschen vor dem Schirm warten zu lassen.
STILLE_DAUER_S = 0.9

_ZEIT = httpx.Timeout(3.0)


async def _schwelle_lesen(client: httpx.AsyncClient, basis: str) -> float | None:
    antwort = await client.get(f"{basis}/levels")
    antwort.raise_for_status()
    wert = antwort.json().get("vad_energy_threshold")
    return float(wert) if isinstance(wert, (int, float)) else None


async def _schwelle_setzen(client: httpx.AsyncClient, basis: str, wert: float) -> None:
    antwort = await client.post(f"{basis}/vad_threshold", json={"value": wert})
    antwort.raise_for_status()


async def satzende_ausloesen(basis_url: str, *, schlafen=asyncio.sleep) -> bool:
    """Den laufenden Chunk abschliessen lassen. Gibt zurueck, ob es geklappt hat.

    Wirft nie: Ein misslungenes Satzende kostet den letzten Satz, ein Absturz
    im Kern kostet den Abend. Der Fehler steht im Log, der Betrieb laeuft
    weiter — dieselbe Regel wie bei `_verwirf_foto`.
    """
    alte: float | None = None
    try:
        async with httpx.AsyncClient(timeout=_ZEIT) as client:
            alte = await _schwelle_lesen(client, basis_url)
            if alte is not None and alte >= VERDACHT_AB:
                # Schon oben — dann hat ein frueherer Lauf sie stehen lassen.
                # Nicht noch einmal anheben, sondern nur zuruecksetzen.
                log.warning(
                    "VAD-Schwelle stand bei %.4f — wird zurueckgesetzt, nicht angehoben",
                    alte,
                )
                await _schwelle_setzen(client, basis_url, RUECKFALL_SCHWELLE)
                return False
            await _schwelle_setzen(client, basis_url, STILLE_SCHWELLE)
            try:
                await schlafen(STILLE_DAUER_S)
            finally:
                # 🔴 Der Rueckweg. Ohne ihn bleibt das Mikrofon taub, und zwar
                # ueber Neustarts hinweg — der fremde Dienst schreibt die
                # Schwelle in seine Settings-Datei.
                await _schwelle_setzen(
                    client, basis_url, alte if alte is not None else RUECKFALL_SCHWELLE
                )
            return True
    except Exception as fehler:  # noqa: BLE001 — siehe Docstring
        log.warning("Satzende konnte nicht ausgeloest werden: %s", fehler)
        if alte is not None:
            # Zweiter Versuch mit eigener Verbindung: Die erste kann genau
            # beim Zuruecksetzen gestorben sein.
            try:
                async with httpx.AsyncClient(timeout=_ZEIT) as client:
                    await _schwelle_setzen(client, basis_url, alte)
                log.info("VAD-Schwelle im zweiten Anlauf zurueckgesetzt")
            except Exception as zweiter:  # noqa: BLE001
                log.error(
                    "🔴 VAD-Schwelle konnte NICHT zurueckgesetzt werden (%s) — "
                    "das Mikrofon ist womoeglich taub. Von Hand: "
                    "curl -X POST %s/vad_threshold -d '{\"value\": %s}' "
                    "-H 'Content-Type: application/json'",
                    zweiter,
                    basis_url,
                    alte,
                )
        return False


async def pruefe_und_repariere(basis_url: str) -> bool:
    """Beim Start: Steht die Schwelle steckengeblieben oben, zuruecksetzen.

    Gibt zurueck, ob repariert wurde. Ein Tag, der mit einem tauben Mikrofon
    beginnt, sieht auf jedem Bildschirm gesund aus — deshalb wird hier
    nachgesehen und nicht darauf vertraut, dass der letzte Lauf sauber endete.
    """
    try:
        async with httpx.AsyncClient(timeout=_ZEIT) as client:
            alte = await _schwelle_lesen(client, basis_url)
            if alte is None or alte < VERDACHT_AB:
                return False
            log.error(
                "🔴 VAD-Schwelle stand beim Start auf %.4f — ein frueherer Lauf "
                "hat sie nicht zurueckgesetzt. Wird auf %.4f gesetzt.",
                alte,
                RUECKFALL_SCHWELLE,
            )
            await _schwelle_setzen(client, basis_url, RUECKFALL_SCHWELLE)
            return True
    except Exception as fehler:  # noqa: BLE001
        log.warning("VAD-Schwelle beim Start nicht pruefbar: %s", fehler)
        return False
