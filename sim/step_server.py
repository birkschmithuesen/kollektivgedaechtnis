"""Serve an empty wall and grow it one interview at a time, on command.

Run this instead of `python -m kg` when the point is to FOLLOW the graph's
construction: the wall starts empty, and each step adds exactly one interview
and pushes the new graph to every open browser over the same SSE channel the
live Core uses. So the wall you watch here is the real wall, not a preview of
one.

Steps are triggered over HTTP (`POST /step`) rather than from stdin, because
the thing driving them sits in another process — an agent session, a second
terminal, a phone on the same tailnet. `GET /progress` answers where we are.

Two deliberate non-goals: no LLM runs here (the extraction already happened,
see sim/stepper.py), and stepping is one-way. To go back, restart — the
database is a throwaway, rebuilt from the recorded run in seconds.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import uvicorn
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from kg.bus import EventBus
from kg.config import Config
from kg.export import write_graph_json
from kg.server import create_app, current_state
from kg.store import Store
from sim.stepper import InterviewStepper, apply_interview


def build(source_db: Path, data_dir: Path, portraits: list[str] | None = None):
    """Wire an empty live store to a finished run, plus the step endpoints."""
    cfg = Config(data_dir=data_dir)
    store = Store.open(cfg.db_path)
    # Same start-up contract as the real Core (kg/__main__.py): a fresh wall
    # opens roaming, so walking through the interviews shows what the station
    # actually does on the day rather than a motionless net.
    store.set_setting_default("camera_mode", cfg.default_camera_mode)
    bus = EventBus()
    stepper = InterviewStepper(source_db)
    app = create_app(store, cfg, bus)
    # Mutable so /step can advance it; a dict keeps it reachable from the
    # closures below without a module-level global.
    cursor = {"done": 0}

    # The server serves faces from `portrait_dir` and the export writes only a
    # BASENAME into graph.json (kg/export.py:_portrait_url), so a portrait that
    # merely exists somewhere on disk would render as a broken image. Copy the
    # set in once, here, and hand out basenames from then on.
    faces: list[str] = []
    for source in portraits or []:
        origin = Path(source)
        if not origin.is_file():
            continue
        target = cfg.portrait_dir / origin.name
        if not target.exists():
            shutil.copyfile(origin, target)
        faces.append(target.name)

    def _broadcast() -> None:
        """Push the whole graph, exactly as the Core does after an interview."""
        bus.publish({"type": "graph", "graph": write_graph_json(store, cfg.graph_json_path)})
        bus.publish({"type": "state", "state": current_state(store)})

    @app.get("/progress")
    def progress() -> JSONResponse:
        return JSONResponse(
            {
                "done": cursor["done"],
                "total": stepper.total,
                "persons": len(store.list_persons()),
                "terms": len(store.list_terms()),
            }
        )

    @app.post("/step")
    def step() -> JSONResponse:
        if cursor["done"] >= stepper.total:
            raise HTTPException(status_code=409, detail="alle Interviews eingelesen")
        index = cursor["done"] + 1
        interview = stepper.interview(index)
        portrait = None
        if faces:
            # Cycle: 16 faces over 60 people still gives everyone a face rather
            # than leaving later nodes blank. Repeats are obvious to a human and
            # entirely fine — this set exists to judge the LOOK, not to pretend
            # to be sixty distinct visitors.
            portrait = faces[(index - 1) % len(faces)]
        report = apply_interview(store, interview, portrait_path=portrait)
        cursor["done"] = index
        _broadcast()
        report["total"] = stepper.total
        report["terms_total"] = len(store.list_terms())
        report["persons_total"] = len(store.list_persons())
        return JSONResponse(report)

    @app.post("/reset")
    def reset() -> JSONResponse:
        """Back to an empty wall without restarting the process.

        Deletes rows rather than the file: the Store holds an open connection
        that every other endpoint shares, so swapping the database out from
        under it would leave those handles pointing at a file nobody else can
        see. Order follows the foreign keys — edges and quotes reference the
        people and terms they connect.
        """
        with store.transaction():
            for table in ("edge", "quote", "position", "term_alias", "term", "person",
                          "merge_decision", "counters"):
                store.conn.execute(f"DELETE FROM {table}")
        cursor["done"] = 0
        _broadcast()
        return JSONResponse({"done": 0, "total": stepper.total})

    return app, cfg, store


def main() -> None:
    parser = argparse.ArgumentParser(prog="sim.step_server")
    parser.add_argument("--source-db", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8802)
    parser.add_argument(
        "--portraits",
        default="",
        help="glob or comma-separated portrait paths, cycled over the people "
             "(e.g. 'sim/data/portraits/*.jpg')",
    )
    args = parser.parse_args()

    portraits: list[str] = []
    for chunk in args.portraits.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        # Sorted so the face-to-person mapping is reproducible between runs;
        # a shell that already expanded the glob passes plain paths and those
        # fall through unchanged.
        matches = sorted(str(p) for p in Path().glob(chunk)) if any(c in chunk for c in "*?[") else [chunk]
        portraits.extend(matches)
    app, cfg, _ = build(args.source_db, args.data_dir, portraits)
    print(f"projection:  http://{args.host}:{args.port}/projection")
    print(f"operator:    http://{args.host}:{args.port}/operator")
    print(f"step:        curl -XPOST http://{args.host}:{args.port}/step")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
