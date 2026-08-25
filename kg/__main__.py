"""Entrypoint: one process, four concerns (STT, Telegram, pipeline, HTTP)."""

from __future__ import annotations

import argparse
import asyncio
import logging
import socket
from pathlib import Path

import uvicorn

from kg.bus import EventBus
from kg.config import load_config
from kg.core import Core
from kg.embeddings import build_embedder
from kg.export import write_graph_json
from kg.llm import LLMClient
from kg.server import create_app
from kg.store import Store
from kg.stt_client import STTClient
from kg.telegram_bot import TelegramSource
from kg.transcript import TranscriptLog


def resolved_host(host: str) -> str:
    """The address to PRINT. Never the address to bind.

    Binding to `0.0.0.0` is correct and stays exactly as configured — that is
    what makes Tool 1 reachable from the dream machine (spec §3.1 of the
    Kollektivtraum spec). Printing it is a trap: `http://0.0.0.0:8800` opens
    nothing from another box, and `docs/operations.md` tells the operator to
    open what this line prints. So the wildcard is resolved to the interface
    the default route actually leaves through.

    No packet is sent: `connect()` on a UDP socket only selects a route, and
    192.0.2.1 is TEST-NET-1, reserved and guaranteed unroutable.

    That probe needs a default route (`0.0.0.0/0`), and the exhibition spec
    (§3.1) runs on an isolated one-day LAN — a direct cable between two boxes
    or a switch with static IPs and no configured gateway is entirely
    plausible there. Such a machine has a perfectly good LAN address but no
    default route, so the probe raises even though the box is reachable. "No
    default route" is not "no reachable address" — falling straight back to
    localhost in that case would silently reintroduce the exact bug this
    function exists to fix. So a second attempt asks the OS to resolve the
    machine's own hostname and takes the first non-loopback IPv4 address that
    comes back. Only if that also finds nothing is there truly no LAN address
    to offer, and 127.0.0.1 is printed — at that point honestly, not as a
    disguised failure.
    """
    if host not in ("0.0.0.0", "::"):
        return host
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 1))
        return sock.getsockname()[0]
    except OSError:
        pass
    finally:
        sock.close()
    return _first_non_loopback_ipv4() or "127.0.0.1"


def _first_non_loopback_ipv4() -> str | None:
    """Second-chance lookup for `resolved_host` when there is no default
    route to probe. Resolving the machine's own hostname still surfaces a
    statically-assigned LAN address on a gateway-less exhibition network.
    Never raises: any resolver failure just means there is nothing to offer.
    """
    try:
        _, _, addrs = socket.gethostbyname_ex(socket.gethostname())
    except OSError:
        return None
    for addr in addrs:
        if not addr.startswith("127."):
            return addr
    return None


async def main_async(args) -> None:
    cfg = load_config(Path(args.config) if args.config else None)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    store = Store.open(cfg.db_path)
    # Apply the calibrated start density on a fresh database. On a restart the
    # operator's live setting is already stored and must win (spec 7, 10.5).
    store.set_setting_default("min_mentions", str(cfg.default_min_mentions))
    bus = EventBus()
    transcript_log = TranscriptLog(cfg.transcript_log_path)
    llm = LLMClient(
        model=cfg.llm_model,
        effort=cfg.llm_effort,
        max_tokens=cfg.llm_max_tokens,
        api_key=cfg.anthropic_api_key,
    )
    # OpenRouter + persistent cache (spec 6.2). Nothing to warm up: no local
    # model, and repeated terms are served from the cache.
    embedder = build_embedder(cfg)

    core = Core(cfg, store, bus, transcript_log, llm, embedder)
    write_graph_json(store, cfg.graph_json_path)  # state is reconstructed from SQLite

    app = create_app(store, cfg, bus)
    server = uvicorn.Server(
        uvicorn.Config(app, host=cfg.server_host, port=cfg.server_port, log_level="info")
    )

    tasks = [
        asyncio.create_task(server.serve()),
        asyncio.create_task(core.run_worker()),
        asyncio.create_task(core.run_tick_loop()),
    ]

    if not args.no_stt:
        stt = STTClient(
            url=cfg.stt_url,
            log=transcript_log,
            on_final=core.on_final,
            on_partial=core.on_partial,
            on_state=core.on_stt_state,
        )
        tasks.append(asyncio.create_task(stt.run()))

    if not args.no_telegram and cfg.telegram_token:
        source = TelegramSource(
            token=cfg.telegram_token,
            chat_id=cfg.telegram_chat_id,
            photo_dir=cfg.photo_dir,
            portrait_dir=cfg.portrait_dir,
            portrait_size=cfg.portrait_size,
            on_photo=core.on_photo,
            on_text=core.on_text,
        )
        application = source.build_application()
        await application.initialize()
        await application.updater.start_polling()
        await application.start()

    shown = resolved_host(cfg.server_host)
    print(f"projection:  http://{shown}:{cfg.server_port}/projection")
    print(f"operator:    http://{shown}:{cfg.server_port}/operator")
    # Named explicitly: this is the one URL the dream machine needs, and the
    # cross-machine check in docs/operations.md is run against exactly it.
    print(f"graph.json:  http://{shown}:{cfg.server_port}/graph.json   (Tool 2 liest das)")
    await asyncio.gather(*tasks)


def main() -> None:
    parser = argparse.ArgumentParser(prog="kg")
    parser.add_argument("--config", default=None)
    parser.add_argument("--no-telegram", action="store_true")
    parser.add_argument("--no-stt", action="store_true")
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
