"""Der Empfänger auf herkules: nimmt den Zustand der Station an, zeigt ihn öffentlich.

Die Sicherheitsgrenze dieses Aufbaus ist die Richtung. Es gibt bewusst keinen
Login — also darf von aussen NICHTS an der Station verändert werden können.
Deshalb:

* Aufnehmen (`/ingest/*`) geht nur mit `Authorization: Bearer <token>`, und das
  Token kommt ausschliesslich aus `KG_MIRROR_TOKEN` in der Prozessumgebung.
  Kein Standardwert, keine Beispieldatei, nichts im Repo.
* Alles Öffentliche ist ausschliesslich lesend. Es gibt hier keinen Endpunkt,
  der irgendetwas Richtung Ausstellungsrechner schickt — der Verkehr läuft nur
  in eine Richtung, weil der Uploader PUSHt (die Station steht hinter NAT in
  einem fremden WLAN und ist von hier aus gar nicht erreichbar).

Der Zustand liegt im Speicher UND auf Platte (`mirror-data/`). Ein Neustart des
Dienstes — und den macht systemd nach jedem Absturz — würde sonst die letzte
Ansicht verlieren, obwohl die Station längst weitergelaufen ist.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import mimetypes
import os
import re
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

WEB = Path(__file__).resolve().parent / "web"

#: Ab wann ein Stand nicht mehr als „live" durchgeht. Beide Seiten zeigen es
#: danach dezent an. Lieber ein ehrlicher alter Stand als eine Seite, die
#: Aktualität vortäuscht — bei 3 s Uploadintervall ist 90 s dreissig verpasste
#: Runden und damit sicher ein Ausfall und kein Schluckauf.
STALE_AFTER_S = 90.0

#: Was ein Dateiname sein darf. Alles andere ist ein Schreibversuch auf fremde
#: Dateien: hier kommt ein Name aus dem NETZ und wird zu einem Pfad.
NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")

#: Obergrenzen, damit ein defekter (oder fremder, das Token kann geraten
#: werden) Uploader die Platte des Servers nicht vollschreibt.
MAX_MEDIA_BYTES = 25 * 1024 * 1024
MAX_JSON_BYTES = 32 * 1024 * 1024

MEDIA_KINDS = ("portraits", "images")


def leerer_graph() -> dict:
    """Was `/api/graph` liefert, bevor je etwas eingegangen ist.

    Ein leerer, aber VOLLSTÄNDIGER Graph, kein 404 und kein 500: die Seite
    unterscheidet „noch nichts da" an `generated_at is null` und zeigt die
    Wartemeldung, statt an einem fehlenden `nodes` zu zerbrechen.
    """
    return {
        "version": 1,
        "generated_at": None,
        "max_terms": 1,
        "nodes": [],
        "edges": [],
        "quotes": [],
    }


def leerer_traum() -> dict:
    """Dasselbe für die Traumseite: die Felder, die `dream.js` liest, sind da."""
    return {"current": None, "history": [], "question": None, "question_visible": False}


class Spiegel:
    """Der letzte empfangene Stand — im Speicher, gespiegelt auf Platte."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.graph: dict = leerer_graph()
        self.dream: dict = leerer_traum()
        self.graph_at: float | None = None
        self.dream_at: float | None = None
        for unter in ("", *MEDIA_KINDS):
            (self.data_dir / unter).mkdir(parents=True, exist_ok=True)
        self._lade()

    # -- Platte ---------------------------------------------------------

    def _pfad(self, art: str) -> Path:
        return self.data_dir / f"{art}.json"

    def _lade(self) -> None:
        for art in ("graph", "dream"):
            pfad = self._pfad(art)
            try:
                gespeichert = json.loads(pfad.read_text(encoding="utf-8"))
            except FileNotFoundError:
                continue
            except Exception as fehler:  # noqa: BLE001
                # Ein abgeschnittenes JSON (Stromausfall mitten im Schreiben)
                # darf den Dienst nicht am Starten hindern — dann eben ohne
                # Vorstand, die nächste Aufnahme repariert das in Sekunden.
                print(f"[mirror] {pfad.name} unlesbar, ignoriert: {fehler}", flush=True)
                continue
            setattr(self, art, gespeichert.get("payload") or getattr(self, art))
            setattr(self, f"{art}_at", gespeichert.get("received_at"))

    def _schreibe(self, art: str, payload: dict, received_at: float) -> None:
        pfad = self._pfad(art)
        tmp = pfad.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps({"received_at": received_at, "payload": payload}, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp, pfad)

    # -- Aufnahme -------------------------------------------------------

    def setze_graph(self, payload: dict, jetzt: float) -> None:
        # Vollständiger Ersatz, kein Delta — `kg/export.py` schreibt den ganzen
        # Graphen bei jeder Änderung, es GIBT hier nichts zu mischen.
        self.graph = payload
        self.graph_at = jetzt
        self._schreibe("graph", payload, jetzt)

    def setze_traum(self, payload: dict, jetzt: float) -> None:
        self.dream = payload
        self.dream_at = jetzt
        self._schreibe("dream", payload, jetzt)

    def medienpfad(self, kind: str, name: str) -> Path:
        return self.data_dir / kind / name

    # -- Alter ----------------------------------------------------------

    def alter(self, art: str, jetzt: float | None = None) -> float | None:
        empfangen = getattr(self, f"{art}_at")
        if empfangen is None:
            return None
        return round(max(0.0, (jetzt or time.time()) - empfangen), 1)


class _Verteiler:
    """Winziger Pub/Sub für den Ereignisstrom.

    Bewusst hier und nicht `kg.bus.EventBus` importiert: der Empfänger läuft auf
    einer anderen Maschine als die Station und soll ohne `kg`/`kg2` im Pfad
    starten können. Zwölf Zeilen sind der günstigere Preis als eine Kopplung an
    ein Paket, das hier sonst nirgends gebraucht wird.

    Wie dort gilt: ein langsamer Handy-Tab darf die Aufnahme nicht bremsen, also
    fliegt sein Ereignis weg statt zu blockieren. Die Ereignisse tragen den
    VOLLEN Zustand, ein verlorenes kostet deshalb nichts.
    """

    def __init__(self, max_queue: int = 50) -> None:
        self.max_queue = max_queue
        self._abonnenten: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self.max_queue)
        self._abonnenten.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        if queue in self._abonnenten:
            self._abonnenten.remove(queue)

    def publish(self, event: dict) -> None:
        for queue in list(self._abonnenten):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass


def _pruefe_namen(name: str) -> str:
    """Der einzige Ort, an dem ein Name aus dem Netz zu einem Pfad wird.

    `..`, `/`, `\\`, ein leerer Name, ein Name mit Doppelpunkt (NTFS-Datenstrom
    auf einer Windows-Kopie): alles 400. Die Route ist absichtlich als
    `{name:path}` deklariert, damit ein Ausbruchsversuch HIER ankommt und
    beantwortet wird, statt vorher als 404 durchs Routing zu fallen.
    """
    if not NAME_RE.match(name or "") or name in (".", ".."):
        raise HTTPException(status_code=400, detail="ungültiger Dateiname")
    return name


def _pruefe_art(kind: str) -> str:
    if kind not in MEDIA_KINDS:
        raise HTTPException(status_code=400, detail="unbekannte Medienart")
    return kind


def create_app(data_dir: Path | str | None = None, token: str | None = None) -> FastAPI:
    """Die App. `token=None` heisst: aus der Umgebung, und ohne Umgebung zu.

    Ohne konfiguriertes Token beantwortet jede Aufnahme 401 („fail closed").
    Der Dienst läuft dann trotzdem und zeigt weiter den Stand von der Platte —
    ein vergessenes `EnvironmentFile` darf die öffentliche Seite nicht mit in
    den Abgrund reissen, nur das Nachfüllen verhindern.
    """
    if data_dir is None:
        data_dir = os.environ.get("KG_MIRROR_DATA", "mirror-data")
    if token is None:
        token = os.environ.get("KG_MIRROR_TOKEN")

    spiegel = Spiegel(Path(data_dir))
    bus = _Verteiler()

    app = FastAPI(title="Kollektivgedächtnis — mobiler Spiegel", docs_url=None, redoc_url=None)
    app.state.spiegel = spiegel
    app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")

    def pruefe_token(request: Request) -> None:
        kopf = request.headers.get("authorization", "")
        vorgelegt = kopf[7:] if kopf.lower().startswith("bearer ") else ""
        # `compare_digest` statt `==`: der Vergleich soll nicht verraten, wie
        # viele Zeichen schon stimmen. Kein Token konfiguriert -> nie gleich.
        if not token or not hmac.compare_digest(vorgelegt, token):
            raise HTTPException(status_code=401, detail="kein gültiges Token")

    async def json_body(request: Request) -> dict:
        roh = await request.body()
        if len(roh) > MAX_JSON_BYTES:
            raise HTTPException(status_code=413, detail="Körper zu gross")
        try:
            daten = json.loads(roh.decode("utf-8"))
        except Exception as fehler:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="kein gültiges JSON") from fehler
        if not isinstance(daten, dict):
            raise HTTPException(status_code=400, detail="Objekt erwartet")
        return daten

    # ---- Aufnahme (Token) --------------------------------------------

    @app.post("/ingest/graph")
    async def ingest_graph(request: Request) -> dict:
        pruefe_token(request)
        daten = await json_body(request)
        jetzt = time.time()
        spiegel.setze_graph(daten, jetzt)
        bus.publish({"type": "graph", "graph": daten, "age_s": 0.0})
        return {"ok": True}

    @app.post("/ingest/dream")
    async def ingest_dream(request: Request) -> dict:
        pruefe_token(request)
        daten = await json_body(request)
        jetzt = time.time()
        spiegel.setze_traum(daten, jetzt)
        bus.publish({"type": "dream", "dream": daten, "age_s": 0.0})
        return {"ok": True}

    @app.post("/ingest/media/{kind}/{name:path}")
    async def ingest_media(kind: str, name: str, request: Request) -> dict:
        pruefe_token(request)
        _pruefe_art(kind)
        _pruefe_namen(name)
        roh = await request.body()
        if len(roh) > MAX_MEDIA_BYTES:
            raise HTTPException(status_code=413, detail="Datei zu gross")
        if not roh:
            raise HTTPException(status_code=400, detail="leere Datei")
        ziel = spiegel.medienpfad(kind, name)
        # Das Verzeichnis wird beim Start angelegt; hier noch einmal, weil ein
        # Aufräumskript auf dem Server es unter dem laufenden Dienst wegnehmen
        # kann und der Spiegel danach von selbst weiterlaufen soll.
        ziel.parent.mkdir(parents=True, exist_ok=True)
        tmp = ziel.with_name(ziel.name + ".tmp")
        tmp.write_bytes(roh)
        # Umbenennen statt direkt schreiben: sonst kann eine halb übertragene
        # Datei schon ausgeliefert werden, und ein abgebrochenes Bild bleibt
        # als Bruchstück liegen, das nie wieder nachgeladen wird.
        os.replace(tmp, ziel)
        return {"ok": True, "bytes": len(roh)}

    # ---- Öffentlich, nur lesend --------------------------------------

    @app.get("/")
    def seite_graph() -> FileResponse:
        return FileResponse(WEB / "graph.html")

    @app.get("/traum")
    def seite_traum() -> FileResponse:
        return FileResponse(WEB / "traum.html")

    @app.get("/favicon.ico")
    def favicon() -> Response:
        # Kein Symbol, aber auch kein 404 je Seitenaufruf: die Unit läuft mit
        # LogLevelMax=notice, und ein Rauschen pro Besucherin ist keins wert.
        return Response(status_code=204)

    @app.get("/api/graph")
    def api_graph() -> JSONResponse:
        return JSONResponse(spiegel.graph)

    @app.get("/api/dream")
    def api_dream() -> JSONResponse:
        return JSONResponse(spiegel.dream)

    @app.get("/media/{kind}/{name:path}")
    def media(kind: str, name: str) -> FileResponse:
        # Dieselbe Prüfung wie beim Schreiben, aus demselben Grund: hier wird
        # ein Name aus dem Netz zu einem Pfad, diesmal zum Lesen.
        _pruefe_art(kind)
        _pruefe_namen(name)
        pfad = spiegel.medienpfad(kind, name)
        if not pfad.is_file():
            raise HTTPException(status_code=404, detail="nicht da")
        typ, _ = mimetypes.guess_type(pfad.name)
        return FileResponse(
            pfad,
            media_type=typ or "application/octet-stream",
            # Der Name eines Bildes ist an der Station eindeutig und wird nie
            # unter demselben Namen neu belegt — also darf das Handy es behalten
            # statt es im Konferenz-WLAN alle paar Minuten neu zu holen.
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @app.get("/healthz")
    def healthz() -> dict:
        jetzt = time.time()
        return {
            "ok": True,
            "graph_age_s": spiegel.alter("graph", jetzt),
            "dream_age_s": spiegel.alter("dream", jetzt),
            "stale_after_s": STALE_AFTER_S,
        }

    @app.get("/events")
    async def events() -> StreamingResponse:
        queue = bus.subscribe()

        async def stream():
            try:
                jetzt = time.time()
                yield _sse({"type": "graph", "graph": spiegel.graph, "age_s": spiegel.alter("graph", jetzt)})
                yield _sse({"type": "dream", "dream": spiegel.dream, "age_s": spiegel.alter("dream", jetzt)})
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    except TimeoutError:
                        # Muster wie kg/server.py: alle 15 s ein Kommentar, damit
                        # nginx und die Mobilfunk-NAT die Leitung offen lassen.
                        yield ": keep-alive\n\n"
                        continue
                    yield _sse(event)
            finally:
                bus.unsubscribe(queue)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            # Gegen puffernde Zwischenstationen; nginx braucht zusätzlich
            # `proxy_buffering off` (mirror/nginx-kg-mirror.conf).
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def main() -> None:
    import uvicorn

    if not os.environ.get("KG_MIRROR_TOKEN"):
        raise SystemExit(
            "KG_MIRROR_TOKEN fehlt. Ohne Token nimmt der Spiegel nichts an; "
            "das Token gehört in die Umgebung (~/.config/kg-mirror.env), "
            "niemals in eine Datei im Repo."
        )
    host = os.environ.get("KG_MIRROR_HOST", "127.0.0.1")
    port = int(os.environ.get("KG_MIRROR_PORT", "8820"))
    daten = os.environ.get("KG_MIRROR_DATA", "mirror-data")
    print(f"[mirror] Empfänger auf {host}:{port}, Daten in {Path(daten).resolve()}", flush=True)
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
