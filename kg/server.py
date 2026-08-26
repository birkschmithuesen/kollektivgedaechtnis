"""FastAPI app: three static pages, one SSE stream, the operator API."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from kg.export import build_graph, write_graph_json

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


class MinMentions(BaseModel):
    value: int = Field(ge=1, le=10)


class HiddenFlag(BaseModel):
    node_id: str
    hidden: bool


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


class Point(BaseModel):
    x: float
    y: float


class Positions(BaseModel):
    positions: dict[str, Point]


def current_state(store) -> dict:
    person = store.open_person()
    return {
        "min_mentions": int(store.get_setting("min_mentions", "1")),
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
        "stt_connected": store.get_setting("stt_connected", "0") == "1",
        "interview": None
        if person is None
        else {"person_id": person.id, "started_at": person.started_at},
    }


def broadcast_graph(store, cfg, bus) -> None:
    bus.publish({"type": "graph", "graph": write_graph_json(store, cfg.graph_json_path)})


def broadcast_state(store, bus) -> None:
    bus.publish({"type": "state", "state": current_state(store)})


def create_app(store, cfg, bus) -> FastAPI:
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

    @app.post("/api/min_mentions")
    def api_min_mentions(payload: MinMentions) -> dict:
        store.set_setting("min_mentions", str(payload.value))
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
