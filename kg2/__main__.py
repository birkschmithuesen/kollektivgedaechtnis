"""Entrypoint: one process, two concerns (the poll loop and the HTTP server)."""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

import uvicorn

from kg.__main__ import resolved_host
from kg.bus import EventBus
from kg.llm import LLMClient
from kg2.config import load_dream_config
from kg2.server import create_dream_app, seed_display_settings
from kg2.store import DreamStore
from kg2.watcher import DreamWatcher


async def main_async(args) -> None:
    cfg = load_dream_config(Path(args.config) if args.config else None)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    store = DreamStore.open(cfg.db_path)
    seed_display_settings(store, cfg)
    bus = EventBus()
    # kg.llm is a pure client wrapper — no store, no core, no server (spec §3).
    llm = LLMClient(
        model=cfg.condense_model,
        effort=cfg.condense_effort,
        max_tokens=cfg.condense_max_tokens,
        api_key=cfg.anthropic_api_key,
    )

    app = create_dream_app(store, cfg, bus)
    server = uvicorn.Server(
        uvicorn.Config(app, host=cfg.server_host, port=cfg.server_port, log_level="info")
    )

    tasks = [asyncio.create_task(server.serve())]
    if not args.no_watch:
        watcher = DreamWatcher(cfg, store, bus, llm)
        tasks.append(asyncio.create_task(watcher.run()))

    shown = resolved_host(cfg.server_host)
    print(f"dream:     http://{shown}:{cfg.server_port}/dream")
    print(f"operator:  http://{shown}:{cfg.server_port}/operator")
    print(f"tool 1:    {cfg.graph_url}")
    await asyncio.gather(*tasks)


def main() -> None:
    parser = argparse.ArgumentParser(prog="kg2")
    parser.add_argument("--config", default=None)
    parser.add_argument(
        "--no-watch",
        action="store_true",
        help="serve the pages without polling Tool 1 — for a smoke test with "
        "no exhibition machine and no credentials",
    )
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
