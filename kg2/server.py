"""Tool 2's own web server: two pages, one SSE stream, its own operator API.

Tool 1's operator UI keeps its deliberate sparseness („the one live control",
T1§7) and is NOT extended — Tool 2 gets its own interface (spec §7).

Flow control („pause", „dream now") goes through the STORE, not through a
controller object handed to this app. One mechanism instead of two: it survives
a restart for free (spec §8), and this server needs no reference to the watcher
at all, so a wedged watcher cannot take the operator UI down with it.

`kg.bus.EventBus` is imported rather than copied — spec §3 permits pure helpers
from `kg`, and EventBus is pure asyncio with no store, core or server
dependency. Each process instantiates its own.
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Same Windows trap Tool 1 hit on the exhibition machine (2026-08-29): Windows
# resolves MIME types through the registry, where HKCR\.js is routinely
# "text/plain", and Starlette's StaticFiles takes `mimetypes` at its word.
# Chromium then refuses every ES module -- "Expected a JavaScript module script
# but the server responded with a MIME type of text/plain" -- and the page comes
# up styled but EMPTY, with no failing request and no traceback to follow.
# Registered here too because kg2 serves its own frontend from its own process;
# a no-op on Linux, where the mapping is already right.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")

FRONTEND = Path(__file__).resolve().parent.parent / "frontend2"


class DisplaySettings(BaseModel):
    """Spec §7's display settings. Every field optional — the operator UI sends
    one control at a time, and a partial update must not reset its neighbours."""

    # Never 0: a 0 ms "cross-fade" is a cut, and Birk ruled out anything but a
    # fade (spec §6). The upper bound keeps a stray value from leaving the wall
    # mid-dissolve for half a minute.
    fade_ms: int | None = Field(default=None, ge=100, le=10000)
    # Never 0 (the strip is the evidence and may not vanish) and never so large
    # that the strip swallows the dream it is evidence for (spec §6: asymmetric
    # by design). The ceiling is not a round number picked by eye — it is
    # measured against dream.css's actual geometry at 1920x1080: the stage
    # stays more than 2.6x the thumbnail height up to 0.25, crosses under 2x
    # by ~0.29, falls to a 1.18x sliver at 0.4, and at the old ceiling of 0.5
    # the thumbnail is taller than the stage — a complete inversion of "the
    # strip may never rival the dream it is evidence for". 0.25 is the value
    # below which dominance holds with comfortable margin across the whole
    # range, not just at the default.
    strip_ratio: float | None = Field(default=None, ge=0.05, le=0.25)
    # Never 0 (the strip is the evidence and this control only trims it —
    # discarding a single dream already exists for removing one). The upper
    # bound is the largest count the wall design has ever been judged at
    # (sim.dream_prerender's four-point series stops at 40; spec §6, Birk
    # 2026-08-26 on the rendered comparisons).
    strip_max: int | None = Field(default=None, ge=1, le=40)
    typewriter: bool | None = None
    slideshow: bool | None = None


class PauseFlag(BaseModel):
    paused: bool


class DiscardFlag(BaseModel):
    dream_id: str
    discarded: bool = True


_DEFAULTS = {
    "fade_ms": ("default_fade_ms", int),
    "strip_ratio": ("default_strip_ratio", float),
    "strip_max": ("default_strip_max", int),
    "typewriter": ("default_typewriter", bool),
    "slideshow": ("default_slideshow", bool),
}


def seed_display_settings(store, cfg) -> None:
    """Apply config's start values on a fresh database only.

    On a restart the operator's live setting is already stored and must win —
    the same rule Tool 1 holds for `min_mentions` (T1§7, §10.5).
    """
    for key, (attribute, kind) in _DEFAULTS.items():
        value = getattr(cfg, attribute)
        store.set_setting_default(key, "1" if kind is bool and value else
                                  "0" if kind is bool else str(value))
    store.set_setting_default("paused", "0")
    store.set_setting_default("dream_requested", "0")


def dream_payload(dream) -> dict | None:
    """What screen B needs, and nothing more.

    Deliberately WITHOUT the prompts: showing stage 2's prompt would put
    lighting instructions on the wall (spec §5.2). The operator UI reads the
    full record from /api/dreams instead.
    """
    if dream is None:
        return None
    return {
        "id": dream.id,
        "created_at": dream.created_at,
        "sentence": dream.sentence,
        "image": f"/media/images/{dream.image_path}" if dream.image_path else None,
    }


def dream_state(store, cfg) -> dict:
    strip_max = int(store.get_setting("strip_max", str(cfg.default_strip_max)))
    # Keine Frage mehr im Zustand (2026-08-31): die Überschrift war die letzte
    # Verwendung der Leitfrage, und sie zeigte eine Frage, die niemand im Raum
    # gestellt bekommen hat. Der Platz oben gehört jetzt dem Bild.
    return {
        "fade_ms": int(store.get_setting("fade_ms", str(cfg.default_fade_ms))),
        "strip_ratio": float(store.get_setting("strip_ratio", str(cfg.default_strip_ratio))),
        # Display only: the strip's newest `strip_max` entries. Nothing is
        # deleted from the store — history() already returns everything
        # oldest-first, this only slices what goes out over the wire.
        "strip_max": strip_max,
        "typewriter": store.get_setting("typewriter", "0") == "1",
        # Vorgabe "1": Die Slideshow ist an, solange niemand sie abschaltet —
        # anders als die Schreibmaschine, die aus ist, bis jemand sie will.
        "slideshow": store.get_setting("slideshow", "1") == "1",
        "paused": store.get_setting("paused", "0") == "1",
        "current": dream_payload(store.current_dream()),
        "history": [dream_payload(dream) for dream in store.history()[-strip_max:]],
    }


def broadcast_dream_state(store, cfg, bus) -> None:
    bus.publish({"type": "state", "state": dream_state(store, cfg)})


def create_dream_app(store, cfg, bus) -> FastAPI:
    app = FastAPI(title="Kollektivtraum")
    app.mount("/static", StaticFiles(directory=FRONTEND / "static"), name="static")
    app.mount("/media/images", StaticFiles(directory=cfg.image_dir), name="images")

    @app.get("/")
    def index() -> RedirectResponse:
        return RedirectResponse("/dream")

    @app.get("/dream")
    def dream_page() -> FileResponse:
        return FileResponse(FRONTEND / "dream.html")

    @app.get("/operator")
    def operator_page() -> FileResponse:
        return FileResponse(FRONTEND / "operator.html")

    @app.get("/api/state")
    def api_state() -> dict:
        return dream_state(store, cfg)

    @app.get("/api/dreams")
    def api_dreams() -> JSONResponse:
        """The full record, for the operator UI only (spec §5.3, §7).

        Includes failed and discarded rows: the display filters, the record
        does not.
        """
        return JSONResponse(
            {
                "dreams": [
                    {
                        "id": d.id,
                        "created_at": d.created_at,
                        "sentence": d.sentence,
                        "image": f"/media/images/{d.image_path}" if d.image_path else None,
                        "status": d.status,
                        "discarded": d.discarded,
                        "error": d.error,
                        "person_count": d.person_count,
                        "term_count": d.term_count,
                        "edge_count": d.edge_count,
                        "contradiction": d.contradiction,
                        "stage1_prompt": d.stage1_prompt,
                        "stage2_prompt": d.stage2_prompt,
                        # Fuer den Werkstatt-Tab (Birk, 2026-08-30): dieselbe
                        # Ansicht wie sim/probes/durchklick.py, aber ueber die
                        # echten Traeume statt ueber eine Sonde. Das sind die
                        # Felder, aus denen das Bild entstanden ist - ohne sie
                        # zeigt der Tab nur das Ergebnis und nicht den Weg.
                        "sentence_en": d.sentence_en,
                        "image_description": d.image_description,
                        "tension_source": d.tension_source,
                        "mood": d.mood,
                        "tension": d.tension,
                        "condense_model": d.condense_model,
                        "image_model": d.image_model,
                    }
                    for d in store.all_dreams()
                ]
            }
        )

    @app.post("/api/display")
    def api_display(payload: DisplaySettings) -> dict:
        for key, value in payload.model_dump(exclude_none=True).items():
            store.set_setting(key, "1" if value is True else "0" if value is False else str(value))
        broadcast_dream_state(store, cfg, bus)
        return {"ok": True}

    @app.post("/api/dream_now")
    def api_dream_now() -> dict:
        """Spec §7. A flag, not a call: the watcher owns the cycle, and this
        server must stay usable even when the watcher is wedged."""
        store.set_setting("dream_requested", "1")
        return {"ok": True}

    @app.post("/api/pause")
    def api_pause(payload: PauseFlag) -> dict:
        store.set_setting("paused", "1" if payload.paused else "0")
        broadcast_dream_state(store, cfg, bus)
        return {"ok": True}

    @app.post("/api/discard")
    def api_discard(payload: DiscardFlag) -> dict:
        """Spec §7: removes the dream from the large screen AND from the strip
        in one step. The row is kept — the record stays honest."""
        if store.get_dream(payload.dream_id) is None:
            raise HTTPException(status_code=400, detail=f"no dream {payload.dream_id}")
        store.set_discarded(payload.dream_id, payload.discarded)
        broadcast_dream_state(store, cfg, bus)
        return {"ok": True}

    @app.get("/events")
    async def events() -> StreamingResponse:
        queue = bus.subscribe()

        async def stream():
            try:
                yield _sse({"type": "state", "state": dream_state(store, cfg)})
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
