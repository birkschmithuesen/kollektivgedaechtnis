"""Abholer: holt beim Spiegel eingeworfene Fotos und gibt sie der Station.

Das Gegenstueck zu `POST /ingest/photo` (mirror/receiver.py). Ein Handy ohne
Tailnet-Zugang kann die Station nicht erreichen -- sie sitzt hinter
Venue-NAT. Der Spiegel ist die einzige Stelle, die beide sehen, also liegt
das Foto dort zwischen, und die Station HOLT es ab. Dieselbe Richtung wie
beim Uploader daneben: die Station spricht nach draussen, nie umgekehrt.

Aufruf (auf dem Ausstellungsrechner, neben den anderen Diensten):

    KG_MIRROR_URL=https://kollektivgedaechtnis.flashclash.de \\
    KG_MIRROR_TOKEN=… \\
    python -m mirror.abholer

Er braucht das STARKE Uploader-Token, nicht das Foto-Token: abholen und
quittieren darf nur die Station.
"""

from __future__ import annotations

import logging
import os
import sys
import time

import httpx

log = logging.getLogger("abholer")

#: Wie oft beim Spiegel nachgefragt wird. 3 s ist derselbe Takt wie beim
#: Uploader: schnell genug, dass ein Portrait im Gespraech erscheint, und
#: langsam genug, dass es keine Last ist.
INTERVALL_S = 3.0

#: Nach einem Fehlschlag warten, aber gedeckelt -- ein zurueckkehrender
#: Spiegel soll binnen einer Minute wieder bedient werden.
MAX_BACKOFF_S = 60.0


class Abholer:
    def __init__(
        self,
        spiegel: str,
        token: str,
        station: str = "http://127.0.0.1:8800",
        client: httpx.Client | None = None,
    ) -> None:
        self.spiegel = spiegel.rstrip("/")
        self.station = station.rstrip("/")
        self._kopf = {"authorization": f"Bearer {token}"}
        self.client = client or httpx.Client(timeout=30.0)

    def _wartend(self) -> list[str]:
        antwort = self.client.get(f"{self.spiegel}/eingang", headers=self._kopf)
        antwort.raise_for_status()
        return list(antwort.json().get("wartend") or [])

    def _hole(self, name: str) -> bytes:
        antwort = self.client.get(f"{self.spiegel}/eingang/{name}", headers=self._kopf)
        antwort.raise_for_status()
        return antwort.content

    def _quittiere(self, name: str) -> None:
        self.client.delete(f"{self.spiegel}/eingang/{name}", headers=self._kopf)

    def _an_station(self, roh: bytes) -> None:
        antwort = self.client.post(
            f"{self.station}/api/photo",
            content=roh,
            headers={"content-type": "image/jpeg"},
        )
        antwort.raise_for_status()

    def einmal(self) -> int:
        """Eine Runde. Gibt zurueck, wie viele Fotos zugestellt wurden."""
        zugestellt = 0
        for name in self._wartend():
            try:
                roh = self._hole(name)
            except Exception as fehler:  # noqa: BLE001
                log.warning("konnte %s nicht holen: %s", name, fehler)
                continue

            try:
                self._an_station(roh)
            except Exception as fehler:  # noqa: BLE001
                # NICHT quittieren: das Foto bleibt liegen und wird beim
                # naechsten Durchlauf erneut versucht. Eine Station, die
                # gerade neu startet, darf kein Portrait kosten.
                log.warning("Station nahm %s nicht an: %s", name, fehler)
                continue

            # Erst JETZT quittieren -- die Station hat es sicher.
            try:
                self._quittiere(name)
            except Exception as fehler:  # noqa: BLE001
                # Zugestellt ist zugestellt. Bleibt die Quittung aus, kommt
                # das Foto ein zweites Mal -- doppeltes Portrait ist
                # aergerlich, ein verlorenes waere schlimmer.
                log.warning("Quittung fuer %s fehlgeschlagen: %s", name, fehler)
            zugestellt += 1
            log.info("Foto zugestellt: %s (%d Bytes)", name, len(roh))
        return zugestellt

    def laufe(self, intervall: float = INTERVALL_S) -> None:
        backoff = intervall
        while True:
            try:
                self.einmal()
                backoff = intervall  # Erfolg setzt die Wartezeit zurueck
            except Exception as fehler:  # noqa: BLE001
                # Der Spiegel ist weg (Netz, Neustart, TLS). Kein Abbruch:
                # der Dienst laeuft am Ausstellungstag unbeaufsichtigt.
                log.warning("Spiegel nicht erreichbar: %s", fehler)
                backoff = min(backoff * 2, MAX_BACKOFF_S)
            time.sleep(backoff)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="[abholer] %(message)s")

    spiegel = os.environ.get("KG_MIRROR_URL")
    token = os.environ.get("KG_MIRROR_TOKEN")
    station = os.environ.get("KG_STATION_URL", "http://127.0.0.1:8800")

    if not spiegel or not token:
        print(
            "KG_MIRROR_URL und KG_MIRROR_TOKEN muessen gesetzt sein.\n"
            "Das Token ist das STARKE Uploader-Token, nicht das Foto-Token.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    log.info("Spiegel: %s -> Station: %s", spiegel, station)
    Abholer(spiegel, token, station).laufe()


if __name__ == "__main__":
    main()
