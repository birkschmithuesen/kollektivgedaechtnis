"""Der Uploader auf dem Ausstellungsrechner: schiebt den Stand nach herkules.

PUSH, nicht PULL. Der Server kann diesen Rechner nicht erreichen — Venue-WLAN,
NAT, keine eingehende Verbindung. Also läuft die Schleife HIER und schiebt
hoch.

Die eigentliche Anforderung ist nicht das Hochladen, sondern das Durchhalten:
das Ding läuft einen Tag lang unbeaufsichtigt in einem fremden WLAN, und
niemand sitzt daneben, um es neu zu starten. Deshalb gilt hier durchgehend:

* Keine Netz-Operation darf das Skript beenden. Jede sitzt in `try/except`,
  der Fehler geht auf stderr, die Schleife läuft weiter.
* Tool 1 und Tool 2 fallen unabhängig voneinander aus (Spec §9). Der Uploader
  darf diese Unabhängigkeit nicht aufheben: ist eins weg, geht das andere
  trotzdem weiter hoch.
* Timeouts überall. Ein halboffenes WLAN antwortet nicht und schliesst auch
  nicht — ohne Read-Timeout steht die Schleife dann für immer.
* Rückwärts-Abstand nach wiederholten Fehlern. Ein toter Server soll nicht
  dauerhaft die Bandbreite fressen, die die Station selbst braucht.

Das Token steht in `KG_MIRROR_TOKEN` und wird NIE ausgegeben — nicht beim
Start, nicht in einer Fehlermeldung. Die Logdatei eines Ausstellungsrechners
liest am Ende irgendwer.

Läuft auf Windows: nur stdlib + httpx, keine Signale, keine Forks, keine Pfade
mit fest verdrahtetem Schrägstrich.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import httpx

#: Neben dem Skript, nicht im Datenverzeichnis: der Uploader soll ohne
#: Kenntnis der Ablage der beiden Werkzeuge laufen können.
GEDAECHTNIS = Path(__file__).resolve().parent / "mirror-uploaded.json"

#: connect 5 s / read 20 s aus dem Auftrag. Der Lese-Wert ist der grosszügige:
#: ein 4-MB-Portrait über ein Konferenz-WLAN hochzuschieben dauert.
TIMEOUT = httpx.Timeout(connect=5.0, read=20.0, write=20.0, pool=5.0)

#: Obergrenze des Rückwärts-Abstands. 60 s ist der Punkt, an dem ein Ausfall
#: nichts mehr kostet und ein zurückkehrender Server trotzdem binnen einer
#: Minute wieder bedient wird.
MAX_BACKOFF_S = 60.0

MEDIA_PREFIX = {"portraits": "/media/portraits/", "images": "/media/images/"}


def stabiler_hash(payload: object) -> str:
    """Ein Fingerabdruck, der nur vom INHALT abhängt.

    `sort_keys` ist der springende Punkt: Python garantiert die Reihenfolge
    eines Dicts über die Zeit zwar, aber der Graph kommt frisch aus einem
    JSON-Parser, und schon eine umsortierte Antwort würde sonst als „geändert"
    gelten. Dann liefe der Uploader alle drei Sekunden mit dem gleichen Inhalt
    los, den ganzen Tag.
    """
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


class Aenderungswache:
    """Merkt sich je Schlüssel den zuletzt hochgeladenen Inhalt.

    Bewusst eine eigene, netzfreie Klasse: die Änderungserkennung ist die eine
    Stelle, an der ein Fehler unsichtbar teuer wird (jede Runde alles neu
    schicken), und so lässt sie sich ohne Server prüfen.
    """

    def __init__(self) -> None:
        self._hashes: dict[str, str] = {}

    def geaendert(self, schluessel: str, payload: object) -> bool:
        """True, wenn `payload` sich seit dem letzten `bestaetige` unterscheidet."""
        return self._hashes.get(schluessel) != stabiler_hash(payload)

    def bestaetige(self, schluessel: str, payload: object) -> None:
        """Nach dem ERFOLGREICHEN Upload. Vorher wäre falsch: ein Upload, der
        mit 500 endet, muss beim nächsten Durchlauf wiederholt werden."""
        self._hashes[schluessel] = stabiler_hash(payload)

    def vergiss(self, schluessel: str) -> None:
        self._hashes.pop(schluessel, None)


def bildnamen(payload: object, prefix: str) -> list[str]:
    """Alle Dateinamen, die unter `prefix` in einem Dokument referenziert sind.

    Rekursiv über die ganze Struktur statt gezielt über `portrait` bzw.
    `current.image`/`history[].image`: die beiden Werkzeuge werden parallel
    weiterentwickelt, und ein neues Feld mit einem Bildpfad darf nicht dazu
    führen, dass am Handy ein Platzhalter statt eines Bildes steht. Was kein
    Bildpfad ist, matcht schlicht nicht.
    """
    gefunden: list[str] = []

    def geh(knoten: object) -> None:
        if isinstance(knoten, str):
            if knoten.startswith(prefix):
                name = knoten[len(prefix):]
                if name and "/" not in name and name not in gefunden:
                    gefunden.append(name)
        elif isinstance(knoten, dict):
            for wert in knoten.values():
                geh(wert)
        elif isinstance(knoten, list):
            for wert in knoten:
                geh(wert)

    geh(payload)
    return gefunden


def lade_gedaechtnis(pfad: Path) -> set[str]:
    """Was schon oben liegt, aus dem letzten Lauf.

    Ein unlesbares Gedächtnis ist kein Grund aufzugeben: dann werden die Bilder
    eben noch einmal geschickt. Teuer, aber richtig — anders herum (aufgeben)
    fehlten am Handy Gesichter.
    """
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
        return set(daten.get("uploaded", []))
    except FileNotFoundError:
        return set()
    except Exception as fehler:  # noqa: BLE001
        print(f"[uploader] {pfad.name} unlesbar, fange von vorn an: {fehler}", file=sys.stderr)
        return set()


def schreibe_gedaechtnis(pfad: Path, hochgeladen: set[str]) -> None:
    try:
        tmp = pfad.with_name(pfad.name + ".tmp")
        tmp.write_text(
            json.dumps({"uploaded": sorted(hochgeladen)}, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(tmp, pfad)
    except Exception as fehler:  # noqa: BLE001
        # Eine volle oder schreibgeschützte Platte darf den Upload nicht
        # beenden — sie kostet nur die Ersparnis über einen Neustart hinweg.
        print(f"[uploader] konnte {pfad.name} nicht schreiben: {fehler}", file=sys.stderr)


class Uploader:
    def __init__(
        self,
        ziel_url: str,
        token: str,
        tool1_url: str = "http://127.0.0.1:8800",
        tool2_url: str = "http://127.0.0.1:8810",
        client: httpx.Client | None = None,
        gedaechtnis: Path = GEDAECHTNIS,
    ) -> None:
        self.ziel = ziel_url.rstrip("/")
        self.tool1 = tool1_url.rstrip("/")
        self.tool2 = tool2_url.rstrip("/")
        self._kopf = {"Authorization": f"Bearer {token}"}
        self.client = client or httpx.Client(timeout=TIMEOUT, follow_redirects=False)
        self.gedaechtnis_pfad = Path(gedaechtnis)
        self.hochgeladen = lade_gedaechtnis(self.gedaechtnis_pfad)
        self.wache = Aenderungswache()
        self.fehler_in_folge = 0

    # -- Bausteine ------------------------------------------------------

    def _hole(self, url: str) -> object | None:
        antwort = self.client.get(url)
        antwort.raise_for_status()
        return antwort.json()

    def _schicke_json(self, weg: str, payload: object) -> None:
        antwort = self.client.post(
            f"{self.ziel}{weg}",
            content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={**self._kopf, "content-type": "application/json"},
        )
        antwort.raise_for_status()

    def _schicke_datei(self, kind: str, name: str, roh: bytes) -> None:
        antwort = self.client.post(
            f"{self.ziel}/ingest/media/{kind}/{name}",
            content=roh,
            headers={**self._kopf, "content-type": "application/octet-stream"},
        )
        antwort.raise_for_status()

    # -- Die drei Schritte einer Runde ----------------------------------

    def uebertrage_dokument(self, schluessel: str, quelle: str, weg: str) -> object | None:
        """Holen, vergleichen, notfalls hochladen. Gibt das Dokument zurück
        (auch das unveränderte — die Medienliste braucht es jede Runde)."""
        payload = self._hole(quelle)
        if payload is None:
            return None
        if self.wache.geaendert(schluessel, payload):
            self._schicke_json(weg, payload)
            self.wache.bestaetige(schluessel, payload)
        return payload

    def uebertrage_medien(self, payload: object, kind: str, basis: str) -> None:
        for name in bildnamen(payload, MEDIA_PREFIX[kind]):
            marke = f"{kind}/{name}"
            if marke in self.hochgeladen:
                continue
            try:
                antwort = self.client.get(f"{basis}{MEDIA_PREFIX[kind]}{name}")
                antwort.raise_for_status()
                self._schicke_datei(kind, name, antwort.content)
            except Exception as fehler:  # noqa: BLE001
                # Ein einzelnes fehlendes Bild darf die übrigen nicht mitnehmen:
                # ein Portrait, das die Station gerade erst zuschneidet, ist
                # kurz 404 und in der nächsten Runde da.
                print(f"[uploader] {marke}: {kurz(fehler)}", file=sys.stderr)
                continue
            self.hochgeladen.add(marke)
            schreibe_gedaechtnis(self.gedaechtnis_pfad, self.hochgeladen)

    def runde(self) -> bool:
        """Eine Runde. True, wenn beide Werkzeuge erreichbar waren.

        Die beiden Blöcke sind getrennt und fangen jeder für sich: Tool 1 und
        Tool 2 fallen unabhängig aus, und der Uploader darf aus zwei getrennten
        Ausfällen nicht einen gemeinsamen machen.
        """
        vollstaendig = True

        try:
            graph = self.uebertrage_dokument("graph", f"{self.tool1}/graph.json", "/ingest/graph")
            if graph is not None:
                self.uebertrage_medien(graph, "portraits", self.tool1)
        except Exception as fehler:  # noqa: BLE001
            vollstaendig = False
            # Der Hash bleibt ungültig, damit der nächste Versuch wirklich
            # hochlädt und nicht denkt, der Stand liege schon oben.
            self.wache.vergiss("graph")
            print(f"[uploader] Tool 1: {kurz(fehler)}", file=sys.stderr)

        try:
            traum = self.uebertrage_dokument("dream", f"{self.tool2}/api/state", "/ingest/dream")
            if traum is not None:
                self.uebertrage_medien(traum, "images", self.tool2)
        except Exception as fehler:  # noqa: BLE001
            vollstaendig = False
            self.wache.vergiss("dream")
            print(f"[uploader] Tool 2: {kurz(fehler)}", file=sys.stderr)

        return vollstaendig

    def schlafdauer(self, intervall: float) -> float:
        """Das Intervall, nach Fehlern verdoppelt, gedeckelt bei 60 s."""
        if self.fehler_in_folge == 0:
            return intervall
        return min(MAX_BACKOFF_S, intervall * (2 ** min(self.fehler_in_folge, 10)))

    def laufe(self, intervall: float = 3.0, runden: int | None = None) -> None:
        """Die Schleife. `runden` begrenzt sie — für Tests, nicht für den Betrieb."""
        durchlauf = 0
        while runden is None or durchlauf < runden:
            durchlauf += 1
            try:
                ok = self.runde()
            except Exception as fehler:  # noqa: BLE001
                # Doppelt genäht: `runde` fängt schon alles, aber ein Fehler
                # ausserhalb der beiden Blöcke (kaputtes Gedächtnis, MemoryError
                # beim Serialisieren) darf den Dienst genauso wenig beenden.
                ok = False
                print(f"[uploader] Runde gescheitert: {kurz(fehler)}", file=sys.stderr)
            self.fehler_in_folge = 0 if ok else self.fehler_in_folge + 1
            if runden is not None and durchlauf >= runden:
                break
            time.sleep(self.schlafdauer(intervall))


def kurz(fehler: BaseException) -> str:
    """Eine Fehlerzeile ohne Token.

    httpx setzt bei einem 401 die ANGEFRAGTE URL in die Meldung, und das Token
    steht im Kopf, nicht in der URL — trotzdem wird hier geputzt, statt sich
    darauf zu verlassen: diese Ausgabe läuft in eine Datei, die am Ende des
    Tages irgendwer liest.
    """
    text = f"{type(fehler).__name__}: {fehler}"
    token = os.environ.get("KG_MIRROR_TOKEN")
    if token:
        text = text.replace(token, "***")
    return text


def main() -> int:
    ziel = os.environ.get("KG_MIRROR_URL")
    token = os.environ.get("KG_MIRROR_TOKEN")
    if not ziel or not token:
        print(
            "KG_MIRROR_URL und KG_MIRROR_TOKEN müssen gesetzt sein "
            "(siehe mirror/README.md).",
            file=sys.stderr,
        )
        return 2

    tool1 = os.environ.get("KG_TOOL1_URL", "http://127.0.0.1:8800")
    tool2 = os.environ.get("KG_TOOL2_URL", "http://127.0.0.1:8810")
    try:
        intervall = float(os.environ.get("KG_MIRROR_INTERVAL", "3.0"))
    except ValueError:
        intervall = 3.0
    intervall = max(0.5, intervall)

    # Was läuft, aber NIE womit: kein Token, auch nicht abgekürzt.
    print(f"[uploader] Ziel     {ziel}", flush=True)
    print(f"[uploader] Tool 1   {tool1}/graph.json", flush=True)
    print(f"[uploader] Tool 2   {tool2}/api/state", flush=True)
    print(f"[uploader] Intervall {intervall:.1f} s", flush=True)
    print(f"[uploader] Gedächtnis {GEDAECHTNIS}", flush=True)

    uploader = Uploader(ziel, token, tool1_url=tool1, tool2_url=tool2)
    try:
        uploader.laufe(intervall)
    except KeyboardInterrupt:
        print("[uploader] beendet", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
