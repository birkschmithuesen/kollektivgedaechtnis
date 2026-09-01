"""FastAPI app: three static pages, one SSE stream, the operator API."""

from __future__ import annotations

import asyncio
import json
import mimetypes
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from kg.export import build_graph, write_graph_json
from kg.photos import make_portrait

# Windows resolves MIME types from the registry, where HKCR\.js is routinely
# "text/plain". Starlette's StaticFiles asks `mimetypes` and therefore serves
# our ES modules as text/plain, and Chromium refuses them outright: "Expected a
# JavaScript module script but the server responded with a MIME type of
# text/plain". The page then loads, styles fine and stays EMPTY -- no error,
# no missing file, just no script. Observed on the exhibition machine
# 2026-08-29; harmless no-op on Linux, where the mapping is already correct.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

# Obergrenze fuer ein Foto aus der App (`/api/photo`). 12 MB fasst jedes Bild,
# das die App erzeugt (2048px lange Kante, JPEG Q85, typisch deutlich unter
# 1 MB) mit reichlich Luft, und schliesst zugleich aus, dass ein versehentlich
# geschicktes Panorama den Speicher der Station belegt, waehrend die Wand
# laeuft.
MAX_PHOTO_BYTES = 12 * 1024 * 1024


class MaxTerms(BaseModel):
    # Upper bound generous enough to mean "alle" on any exhibition-scale
    # graph without needing a separate sentinel value (spec §4).
    value: int = Field(ge=1, le=1000)


class HiddenFlag(BaseModel):
    node_id: str
    hidden: bool


class PersonName(BaseModel):
    person_id: str
    # Nach oben begrenzt, aus demselben Grund wie bei den Reglern: was hier
    # ankommt, landet unter einem Zitat auf einer 1920px-Wand. 120 Zeichen
    # fassen jeden wirklichen Namen und schließen ein versehentlich
    # hineinkopiertes Transkript aus. Leer ist ausdrücklich erlaubt — so
    # löscht der Operator einen verhörten Namen wieder (kg.store).
    name: str = Field(max_length=120)


class CameraMode(BaseModel):
    mode: Literal["fit", "manual", "pan"]


class CameraSpeed(BaseModel):
    # A fraction of the tuned traversal speed: 1.0 is as fast as the tour ever
    # goes (the pace the motion was judged at), 0.25 is a quarter of that —
    # four times as long per leg. Bounded on both sides: above 1.0 the wall
    # would outrun what was ever looked at, below 0.25 a leg takes most of a
    # minute and reads as a stuck screen.
    factor: float = Field(ge=0.25, le=1.0)


class CameraZoom(BaseModel):
    # >= 1 by construction: 1 = the whole net in frame, 2 = half its width
    # across the wall. The upper bound keeps a stray value from zooming the
    # wall into a single node at an unattended exhibition.
    factor: float = Field(ge=1.0, le=4.0)


class PortraitSize(BaseModel):
    # The largest a portrait may get on the wall, in RENDERED pixels, while
    # the camera is driving — an upper bound, not a size (Birk, 2026-08-30;
    # frontend/static/projection.js). Bounds from Birk's brief (2026-08-29):
    # below 40px a portrait is a dot on a 1920px wall, above 260px a handful of
    # faces crowd everything else off it. Bounded on both sides for the same
    # reason as the zoom next to it: whatever a stray value does, it must not
    # be able to leave an unattended wall unusable.
    pixels: float = Field(ge=40.0, le=260.0)


class InterviewSwitch(BaseModel):
    # Der Schalter am Mikrofon, gemeldet vom STT-Server (fundusbot,
    # `--mic-gate`). `source` ist bewusst frei und nur zur Nachvollziehbarkeit
    # in den Logs -- entschieden wird allein an `on`.
    on: bool
    source: str = Field(default="mic_switch", max_length=40)


class Point(BaseModel):
    x: float
    y: float


class Positions(BaseModel):
    positions: dict[str, Point]


def current_state(store) -> dict:
    person = store.open_person()
    return {
        "max_terms": int(store.get_setting("max_terms", "1")),
        "camera_mode": store.get_setting("camera_mode", "fit"),
        # D4 (Birk, 2026-08-19): the wall opens on the whole net; zoom is set
        # on site. The Camera component has always supported a zoom factor,
        # but until 21b it was reachable only through its constructor — so an
        # operator with no touchscreen access could not zoom at all.
        "camera_zoom": float(store.get_setting("camera_zoom", "1")),
        # 1.0 = the traversal's tuned pace, 0.25 = a quarter of it. Slowing the
        # tour down is a room-and-audience judgement, like the zoom next to it,
        # so it belongs to the operator rather than to a constant.
        "camera_speed": float(store.get_setting("camera_speed", "1")),
        # How large a portrait may get on the wall in the automatic modes, in
        # rendered pixels (Birk, 2026-08-29 and 2026-08-30). The default
        # matches projection.js's DEFAULT_PORTRAIT_SIZE, so a station that has
        # never been touched shows the same wall whether or not this setting
        # exists yet.
        "portrait_size": float(store.get_setting("portrait_size", "120")),
        "stt_connected": store.get_setting("stt_connected", "0") == "1",
        # Der physische Schalter am Mikrofon, getrennt von `stt_connected`
        # (siehe Core.on_mic_switch). Default "1": eine Station ohne
        # Schalter-Meldung hat ein dauerhaft offenes Mikrofon, und "aus"
        # anzuzeigen waere dort schlicht falsch.
        "mic_on": store.get_setting("mic_on", "1") == "1",
        "interview": None
        if person is None
        else {"person_id": person.id, "started_at": person.started_at},
    }


def broadcast_graph(store, cfg, bus) -> None:
    bus.publish({"type": "graph", "graph": write_graph_json(store, cfg.graph_json_path)})


def broadcast_state(store, bus) -> None:
    bus.publish({"type": "state", "state": current_state(store)})


def create_app(store, cfg, bus, core=None) -> FastAPI:
    app = FastAPI(title="Kollektivgedächtnis")
    app.mount("/static", StaticFiles(directory=FRONTEND / "static"), name="static")
    app.mount("/media/portraits", StaticFiles(directory=cfg.portrait_dir), name="portraits")

    @app.get("/")
    def index() -> RedirectResponse:
        return RedirectResponse("/projection")

    @app.get("/projection")
    def projection() -> FileResponse:
        return FileResponse(FRONTEND / "projection.html")

    @app.get("/operator")
    def operator() -> FileResponse:
        return FileResponse(FRONTEND / "operator.html")

    @app.get("/testpattern")
    def testpattern() -> FileResponse:
        return FileResponse(FRONTEND / "testpattern.html")

    @app.get("/graph.json")
    def graph_json() -> JSONResponse:
        return JSONResponse(build_graph(store))

    @app.get("/api/state")
    def api_state() -> dict:
        return current_state(store)

    @app.post("/api/max_terms")
    def api_max_terms(payload: MaxTerms) -> dict:
        store.set_setting("max_terms", str(payload.value))
        broadcast_state(store, bus)
        broadcast_graph(store, cfg, bus)
        return {"ok": True}

    @app.post("/api/hidden")
    def api_hidden(payload: HiddenFlag) -> dict:
        try:
            store.set_hidden(payload.node_id, payload.hidden)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        broadcast_graph(store, cfg, bus)
        return {"ok": True}

    @app.post("/api/person_name")
    def api_person_name(payload: PersonName) -> dict:
        # Die Spracherkennung verhört Namen zuverlässig, also muss der Operator
        # sie richtigstellen können — das ist die einzige Korrektur, die er an
        # einem fertigen Interview vornimmt.
        #
        # Nur `broadcast_graph`, kein `broadcast_state`: genau wie /api/hidden
        # darüber, und aus demselben Grund — der Name reist im Graphen mit
        # (kg.export), `current_state` kennt ihn nicht, und eine zweite
        # Rundmeldung mit unverändertem Inhalt würde die Bedienliste nur ein
        # weiteres Mal neu bauen.
        store.set_person_name(payload.person_id, payload.name)
        broadcast_graph(store, cfg, bus)
        return {"ok": True}

    @app.post("/api/camera")
    def api_camera(payload: CameraMode) -> dict:
        store.set_setting("camera_mode", payload.mode)
        broadcast_state(store, bus)
        return {"ok": True}

    @app.post("/api/camera_zoom")
    def api_camera_zoom(payload: CameraZoom) -> dict:
        # A display-only control, like the camera mode next to it. Spec §7's
        # "exactly one runtime dial" governs controls that change EXTRACTION
        # or MERGING; this changes neither.
        store.set_setting("camera_zoom", str(payload.factor))
        broadcast_state(store, bus)
        return {"ok": True}

    @app.post("/api/camera_speed")
    def api_camera_speed(payload: CameraSpeed) -> dict:
        # Display-only, exactly like camera_zoom: it changes how long the tour
        # dwells and travels, never what is extracted or merged.
        store.set_setting("camera_speed", str(payload.factor))
        broadcast_state(store, bus)
        return {"ok": True}

    @app.post("/api/portrait_size")
    def api_portrait_size(payload: PortraitSize) -> dict:
        # Display-only, like the two camera controls above: it bounds how big
        # a face is drawn, never what is extracted, merged or shown.
        # Deliberately independent of camera_zoom — that one chooses the
        # SECTION of the net on the wall, this one bounds the portraits inside
        # it, and turning either must leave the other alone.
        store.set_setting("portrait_size", str(payload.pixels))
        broadcast_state(store, bus)
        return {"ok": True}

    if core is not None:
        # Nur mit Core registriert. Ein Prozess ohne Core (die reine
        # Anzeige-Konfiguration, u.a. in den Tests) hat den Endpunkt dann gar
        # nicht -- besser ein 404 als eine 200, die nichts tut.
        @app.post("/api/photo")
        async def api_photo(request: Request) -> dict:
            """Ein Foto aus der Android-App eroeffnet ein Interview.

            Derselbe Weg, den bisher nur Telegram ging (`TelegramSource.
            _handle_photo` -> `Core.on_photo`), nur ohne den Umweg ueber ein
            fremdes Netz: die App im Tailnet legt die Bytes direkt hier ab.
            Telegram bleibt unveraendert daneben bestehen -- ein zweiter
            Einwurf, kein Ersatz, damit ein Ausfall des einen Wegs die Station
            nicht stillegt.

            **Rohe Bytes im Rumpf, kein multipart.** Das spart die
            Abhaengigkeit `python-multipart` und macht die Android-Seite zu
            einem einzigen `outputStream.write(jpegBytes)` -- kein
            Boundary-Bau, keine Bibliothek. Der Dateiname wird HIER vergeben,
            nie vom Client uebernommen: ein Client-Name waere ein
            Pfad-Injektions-Vektor, und gebraucht wird er fuer nichts.

            Die Groessengrenze ist kein Schikane-Limit, sondern der Schutz
            gegen ein Handy, das versehentlich ein 50-MB-Panorama schickt und
            damit den Speicher der Station belegt, waehrend die Wand laeuft.
            """
            raw = await request.body()
            if not raw:
                raise HTTPException(status_code=400, detail="leerer Rumpf")
            if len(raw) > MAX_PHOTO_BYTES:
                raise HTTPException(
                    status_code=413, detail=f"Bild groesser als {MAX_PHOTO_BYTES} Bytes"
                )
            # Aus den Magic Bytes, nicht aus dem Content-Type-Kopf: der Kopf ist
            # eine Behauptung des Clients, die ersten Bytes sind das Bild. Ein
            # HTML-Fehlerdokument darf hier nie als .jpg auf der Platte landen.
            if not (raw[:3] == b"\xff\xd8\xff" or raw[:8] == b"\x89PNG\r\n\x1a\n"):
                raise HTTPException(status_code=415, detail="kein JPEG/PNG")

            at = time.time()
            stem = f"{int(at)}_app{int(at * 1000) % 1000:03d}"
            photo_path = cfg.photo_dir / f"{stem}.jpg"
            portrait_path = cfg.portrait_dir / f"{stem}.png"
            try:
                await asyncio.to_thread(photo_path.write_bytes, raw)
                await asyncio.to_thread(
                    make_portrait, photo_path, portrait_path, cfg.portrait_size
                )
            except Exception as exc:  # ein kaputtes Bild darf die Station nie anhalten
                raise HTTPException(status_code=422, detail=f"Bild unlesbar: {exc}") from exc

            core.on_photo(photo_path, portrait_path, at)
            # Der Name des Portraits, damit die App es sich ansehen kann
            # (`GET /media/portraits/<name>`, schon gemountet). Absichtlich
            # der Name und nicht das Bild selbst: die App soll es sich HOLEN,
            # wenn sie es zeigen will, statt es jedem Einwurf aufzuzwingen —
            # ein Portrait ist ~100 kB, und am Booth zählt, dass der Auslöser
            # schnell wieder frei ist.
            return {"ok": True, "portrait": portrait_path.name}

        @app.post("/api/interview_switch")
        async def api_interview_switch(payload: InterviewSwitch) -> dict:
            """Der Schalter am Mikrofon, gemeldet vom STT-Server.

            Der zweite Weg, ein Interview zu beenden, neben der gesprochenen
            Schlussphrase -- und seit 2026-09-01 auch der zweite, eins zu
            beginnen: `on: true` eroeffnet ein Interview ohne Portraet, weil
            wer kein Foto von sich moechte, trotzdem teilnehmen koennen muss
            (`SessionTracker.mic_switch`). Geschlossen wird bei `on: false`,
            mit eigenem Grund "mic_switch", damit im Nachhinein unterscheidbar
            bleibt, ob ein Interview per Schlusssatz oder per Schalter endete
            -- und geoeffnet mit demselben Grund, damit dasselbe fuer den
            Anfang gilt.

            Kehrt sofort zurueck: `Core.on_mic_switch` legt den Wechsel nur in
            die Warteschlange, geoeffnet und geschlossen wird im Worker. Der
            STT-Server ruft aus einem Wegwerf-Thread heraus auf und darf nicht
            auf eine Pipeline warten.

            `async def`, und das ist hier nicht Geschmack: eine gewoehnliche
            `def`-Route laesst FastAPI im Threadpool laufen, und
            `Core.on_mic_switch` legt von dort aus mit `put_nowait` in eine
            `asyncio.Queue`. Das ist nicht threadsicher -- das Wecken des
            wartenden Workers geht ueber ein Future der Ereignisschleife.
            Verloren ginge dabei nicht die Antwort, sondern das Schliessen des
            Interviews, und zwar still. Alle anderen Einspeiser dieser
            Warteschlange (Telegram, STT-Client, tick-Schleife) sitzen ohnehin
            auf der Schleife; dieser hier muss es auch.

            Kein Test faengt das ab, und das ist ausdruecklich vermerkt statt
            verschwiegen: `put_nowait` aus einem fremden Thread geht in CPython
            meistens gut, weil die Schleife ohnehin gleich wieder pollt. Es ist
            ein Rennen, kein Fehler mit Ansage -- und genau deshalb steht das
            `async` hier und nicht das Vertrauen darauf, dass es schon
            auffiele.
            """
            core.on_mic_switch(payload.on, time.time())
            return {"ok": True, "on": payload.on}

    @app.post("/api/positions")
    def api_positions(payload: Positions) -> dict:
        # No broadcast: positions come FROM the renderer; echoing them would loop.
        store.save_positions({k: (p.x, p.y) for k, p in payload.positions.items()})
        return {"ok": True}

    @app.get("/events")
    async def events() -> StreamingResponse:
        queue = bus.subscribe()

        async def stream():
            try:
                yield _sse({"type": "graph", "graph": build_graph(store)})
                yield _sse({"type": "state", "state": current_state(store)})
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    except TimeoutError:
                        yield ": keep-alive\n\n"
                        continue
                    yield _sse(event)
            finally:
                bus.unsubscribe(queue)

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
