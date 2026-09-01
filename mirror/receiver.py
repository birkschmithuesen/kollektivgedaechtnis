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
import uuid
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


class Posteingang:
    """Fotos, die auf ihre Abholung durch die Station warten.

    Der Spiegel ist die einzige Stelle, die BEIDE erreichen: das Handy von
    aussen (HTTPS, öffentlich) und die Station von innen (sie holt ab, wie sie
    heute schon hochlädt). Die Station sitzt hinter Venue-NAT und ist von
    aussen nicht erreichbar — deshalb liegt das Foto hier zwischen, statt
    direkt zugestellt zu werden.

    Bewusst ein Verzeichnis und keine Datenbank: es ist eine Warteschlange von
    Dateien, und `os.replace` gibt die Atomarität, die es braucht. Ein halb
    geschriebenes Foto darf die Station nie sehen.

    Der Eingang ist FLÜCHTIG. Abgeholte Fotos werden gelöscht, alte verfallen
    (`MAX_ALTER_S`). Das ist kein Sparen an Platz, sondern Absicht: der
    Spiegel ist ein öffentlicher Server, und Portraits fremder Menschen sollen
    dort nicht liegenbleiben. Der Ort, an dem sie dauerhaft leben, ist die
    Station.
    """

    #: Ein Foto, das so lange niemand abgeholt hat, gehört zu einem Interview,
    #: das längst vorbei ist. Es später einzuspielen hiesse, das falsche
    #: Portrait an das falsche Gespräch zu hängen.
    MAX_ALTER_S = 900.0

    #: Damit ein Dauerdruck auf den Auslöser die Platte nicht vollschreibt.
    MAX_WARTEND = 50

    def __init__(self, verzeichnis: Path) -> None:
        self.verzeichnis = Path(verzeichnis)
        self.verzeichnis.mkdir(parents=True, exist_ok=True)

    def _verfallen(self, jetzt: float) -> None:
        for pfad in self.verzeichnis.glob("*.jpg"):
            try:
                if jetzt - pfad.stat().st_mtime > self.MAX_ALTER_S:
                    pfad.unlink()
            except FileNotFoundError:
                continue  # ein Nebenläufer war schneller, das ist in Ordnung

    def wartend(self) -> list[Path]:
        """Älteste zuerst — die Reihenfolge am Booth ist die Reihenfolge."""
        return sorted(self.verzeichnis.glob("*.jpg"), key=lambda p: p.name)

    def lege_ab(self, roh: bytes, jetzt: float) -> str:
        self._verfallen(jetzt)
        if len(self.wartend()) >= self.MAX_WARTEND:
            raise HTTPException(status_code=429, detail="Eingang voll")

        # Millisekunden im Namen, damit zwei Fotos derselben Sekunde nicht
        # kollidieren, und `uuid4` dahinter, weil zwei Handys unabhängig
        # voneinander drücken können und dieselbe Millisekunde treffen dürfen.
        name = f"{jetzt:.3f}_{uuid.uuid4().hex[:8]}.jpg"
        ziel = self.verzeichnis / name
        tmp = ziel.with_suffix(".jpg.tmp")
        tmp.write_bytes(roh)
        # Atomar: die Station darf nie ein halb geschriebenes Foto sehen.
        os.replace(tmp, ziel)
        return name

    def hole(self, name: str) -> bytes:
        pfad = self.verzeichnis / _pruefe_namen(name)
        try:
            return pfad.read_bytes()
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="nicht vorhanden") from None

    def quittiere(self, name: str) -> bool:
        """Löschen NACH erfolgreicher Abholung, nicht währenddessen.

        Getrennt vom Lesen, damit ein Abbruch auf dem Weg zur Station das Foto
        nicht verliert: erst wenn sie es sicher hat, quittiert sie.
        """
        pfad = self.verzeichnis / _pruefe_namen(name)
        try:
            pfad.unlink()
            return True
        except FileNotFoundError:
            return False


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


def create_app(
    data_dir: Path | str | None = None,
    token: str | None = None,
    foto_token: str | None = None,
) -> FastAPI:
    """Die App. `token=None` heisst: aus der Umgebung, und ohne Umgebung zu.

    Ohne konfiguriertes Token beantwortet jede Aufnahme 401 („fail closed").
    Der Dienst läuft dann trotzdem und zeigt weiter den Stand von der Platte —
    ein vergessenes `EnvironmentFile` darf die öffentliche Seite nicht mit in
    den Abgrund reissen, nur das Nachfüllen verhindern.

    **`foto_token` ist bewusst ein ZWEITES, getrenntes Geheimnis** (Birk,
    2026-09-01). Es steckt in jeder ausgelieferten APK und ist damit kein
    Geheimnis mehr, sobald das Handy aus der Hand gegeben wird — ein APK ist
    ein ZIP, das Token liest jeder heraus. Deshalb darf es ausschliesslich
    Fotos EINWERFEN (`POST /ingest/photo`) und sonst nichts: nicht den Graphen
    ersetzen, nicht den Traum überschreiben, keine Portraits an der Wand
    austauschen. Wer es hat, kann Fotos in die Warteschlange legen — mehr
    nicht, und das ist genau die Befugnis, die die App braucht.

    Das Uploader-Token (`token`) bleibt davon unberührt und darf weiterhin
    alles. Es verlässt die Station nie.
    """
    if data_dir is None:
        data_dir = os.environ.get("KG_MIRROR_DATA", "mirror-data")
    if token is None:
        token = os.environ.get("KG_MIRROR_TOKEN")
    if foto_token is None:
        foto_token = os.environ.get("KG_FOTO_TOKEN")

    spiegel = Spiegel(Path(data_dir))
    posteingang = Posteingang(Path(data_dir) / "eingang")
    bus = _Verteiler()

    app = FastAPI(title="Kollektivgedächtnis — mobiler Spiegel", docs_url=None, redoc_url=None)
    app.state.spiegel = spiegel
    app.state.posteingang = posteingang
    app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")

    def pruefe_token(request: Request) -> None:
        kopf = request.headers.get("authorization", "")
        vorgelegt = kopf[7:] if kopf.lower().startswith("bearer ") else ""
        # `compare_digest` statt `==`: der Vergleich soll nicht verraten, wie
        # viele Zeichen schon stimmen. Kein Token konfiguriert -> nie gleich.
        if not token or not hmac.compare_digest(vorgelegt, token):
            raise HTTPException(status_code=401, detail="kein gültiges Token")

    def pruefe_foto_token(request: Request) -> None:
        """Das schwächere Geheimnis, nur für den Foto-Einwurf.

        Eigene Funktion und NICHT ein zweiter Vergleich in `pruefe_token`:
        die beiden Befugnisse dürfen nie zusammenfallen. Wer hier durchkommt,
        darf ausschliesslich einwerfen — dass das so bleibt, hält
        `test_foto_token_darf_sonst_nichts` fest.

        Das Uploader-Token wird hier ABSICHTLICH NICHT auch akzeptiert. Es
        wäre bequem („das stärkere darf ja alles"), aber dann liesse sich am
        Testaufbau nicht mehr unterscheiden, welches der beiden gerade wirkt,
        und ein Fehler in der Abgrenzung fiele nicht auf.
        """
        kopf = request.headers.get("authorization", "")
        vorgelegt = kopf[7:] if kopf.lower().startswith("bearer ") else ""
        if not foto_token or not hmac.compare_digest(vorgelegt, foto_token):
            raise HTTPException(status_code=401, detail="kein gültiges Foto-Token")

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

    # Die Wurzel ist der Wegweiser, nicht die Ansicht: wer den Link im Haus
    # abtippt, landet zuerst bei der Erklärung und entscheidet dann selbst.
    # Start- und Transparenzseite sind rein statisch — sie funktionieren auch,
    # wenn nie eine Aufnahme eingegangen ist, und hängen an keinem Zustand.

    # ---- Foto-Einwurf von aussen (SCHWACHES Foto-Token) ---------------
    #
    # Der Weg für ein Handy OHNE Tailnet-Zugang (Birk, 2026-09-01): das
    # Handy wirft hier ein, die Station holt unten ab. Bewusst getrennt von
    # `/ingest/media/...` darüber — das schreibt Portraits, die SOFORT an der
    # Wand erscheinen, und darf niemals mit einem Token aus einer APK
    # erreichbar sein.

    @app.post("/ingest/photo")
    async def ingest_photo(request: Request) -> dict:
        pruefe_foto_token(request)
        roh = await request.body()
        if not roh:
            raise HTTPException(status_code=400, detail="leerer Rumpf")
        if len(roh) > MAX_MEDIA_BYTES:
            raise HTTPException(status_code=413, detail="Bild zu gross")
        # Magic Bytes, nicht der Content-Type-Kopf: der Kopf ist eine
        # Behauptung des Clients. Auf einem öffentlichen Server ist das keine
        # Förmlichkeit — ohne diese Prüfung liesse sich hier Beliebiges
        # ablegen und über die Abholroute wieder herausholen.
        if not (roh[:3] == b"\xff\xd8\xff" or roh[:8] == b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(status_code=415, detail="kein JPEG/PNG")

        name = posteingang.lege_ab(roh, time.time())
        print(f"[mirror] Foto eingeworfen: {len(roh)} Bytes -> {name}", flush=True)
        return {"ok": True, "name": name}

    # ---- Abholung durch die Station (STARKES Uploader-Token) ----------

    @app.get("/eingang")
    def eingang_liste(request: Request) -> dict:
        pruefe_token(request)
        return {"wartend": [p.name for p in posteingang.wartend()]}

    @app.get("/eingang/{name:path}")
    def eingang_hole(name: str, request: Request) -> Response:
        pruefe_token(request)
        return Response(content=posteingang.hole(name), media_type="image/jpeg")

    @app.delete("/eingang/{name:path}")
    def eingang_quittiere(name: str, request: Request) -> dict:
        pruefe_token(request)
        return {"ok": posteingang.quittiere(name)}

    @app.get("/")
    def seite_start() -> FileResponse:
        return FileResponse(WEB / "start.html")

    @app.get("/graph")
    def seite_graph() -> FileResponse:
        return FileResponse(WEB / "graph.html")

    @app.get("/traum")
    def seite_traum() -> FileResponse:
        return FileResponse(WEB / "traum.html")

    @app.get("/transparenz")
    def seite_transparenz() -> FileResponse:
        return FileResponse(WEB / "transparenz.html")

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
