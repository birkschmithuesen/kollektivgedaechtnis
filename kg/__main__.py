"""Entrypoint: one process, four concerns (STT, Telegram, pipeline, HTTP)."""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import socket
import subprocess
from pathlib import Path

import uvicorn

from kg.bus import EventBus
from kg.config import load_config
from kg.core import Core
from kg.embeddings import build_embedder
from kg.export import write_graph_json
from kg.llm import build_llm
from kg.server import create_app
from kg.stop_intent import build_stop_intent_llm
from kg.store import Store
from kg.stt_client import STTClient
from kg.telegram_bot import TelegramSource
from kg.transcript import TranscriptLog


def resolved_host(host: str) -> str:
    """The address to PRINT. Never the address to bind.

    Duplicated verbatim (with its two helpers below) as `kg2.__main__`'s own
    copy, on purpose (Finding 4 of Tool 2's review): `kg2/__main__.py` used to
    import this function directly, which transitively pulled `kg.store`,
    `kg.core`, `kg.server` and PIL into Tool 2's process even though this
    function itself needs none of them. Do not "fix" the duplication by
    reintroducing that import, or by factoring this out into a module shared
    by both `__main__`s — a shared module would recreate exactly the import
    coupling between the two tools that keeping two small copies avoids.

    Binding to `0.0.0.0` is correct and stays exactly as configured — that is
    what makes Tool 1 reachable from the dream machine (spec §3.1 of the
    Kollektivtraum spec). Printing it is a trap: `http://0.0.0.0:8800` opens
    nothing from another box, and `docs/operations.md` tells the operator to
    open what this line prints. So the wildcard is resolved through up to
    three attempts, each one a fallback for the last one's blind spot, before
    honestly giving up to localhost.

    (1) Route probe: connect a UDP socket to 192.0.2.1 (TEST-NET-1, reserved
    and guaranteed unroutable) and read back the interface address the
    kernel picked. No packet is sent — `connect()` on a UDP socket only
    selects a route. This needs a default route (`0.0.0.0/0`), and the
    exhibition spec (§3.1) runs on an isolated one-day LAN — a direct cable
    between two boxes or a switch with static IPs and no configured gateway
    is entirely plausible there. Such a machine has a perfectly good LAN
    address but no default route, so the probe raises even though the box is
    reachable. "No default route" is not "no reachable address."

    (2) `ip -4 -o addr show scope global`: the same command
    `docs/operations.md` already tells the operator to run by hand, now run
    for them. `scope global` excludes loopback and link-local at the source,
    which is what makes a simple parse safe. This is the step that actually
    covers the gateway-less-LAN case from (1) on any Linux box, which is
    every machine this ships on. The subprocess gets a 2-second timeout: this
    runs on the startup path of an unattended exhibition process, and a
    wedged or missing `ip` binary must not be able to stall it.

    (3) `socket.gethostbyname_ex(socket.gethostname())`, first non-loopback
    IPv4 address returned: a non-Linux fallback for when (2) can't run at
    all. On the Debian-family hosts this project actually deploys to, expect
    this step to find nothing: `/etc/hosts` ships a stock
    `127.0.1.1 <hostname>` line, assigning a static LAN IP does not update
    it, and that loopback address is correctly rejected here — leaving (2)
    as the step actually doing the work on this deployment.

    Only when all three find nothing is there truly no LAN address to offer,
    and 127.0.0.1 is printed — at that point honestly, not as a disguised
    failure.
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
    return (
        _first_global_ipv4_via_ip_command()
        or _first_non_loopback_ipv4()
        or "127.0.0.1"
    )


def _first_global_ipv4_via_ip_command() -> str | None:
    """Second-chance lookup for `resolved_host` when there is no default
    route to probe. Runs the same `ip -4 addr show scope global` the
    operator runbook (docs/operations.md) already tells a human to run by
    hand when the printed address looks wrong — the exhibition LAN's static
    address is exactly what `scope global` reports. The 2-second timeout
    exists because this runs unattended at process startup: a wedged or
    absent `ip` binary must fall through to the next attempt, not hang it.
    Never raises: any failure here just means there is nothing to offer.
    """
    try:
        result = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", "scope", "global"],
            capture_output=True,
            text=True,
            errors="replace",  # Strict UTF-8 decoding (default) crashes on non-UTF-8 bytes
                                # from locale-specific interface names. Replacement of bad
                                # bytes as U+FFFD is safe: a mangled char cannot occur in
                                # ASCII dotted quads.
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for match in re.finditer(r"inet (\d+\.\d+\.\d+\.\d+)/", result.stdout):
        addr = match.group(1)
        # `scope global` already excludes loopback and link-local at the
        # source; this re-checks rather than trusting output parsing alone.
        if not addr.startswith("127.") and not addr.startswith("169.254."):
            return addr
    return None


def _first_non_loopback_ipv4() -> str | None:
    """Third-chance lookup for `resolved_host`, after the route probe and the
    `ip` command both found nothing. `gethostbyname_ex` is a non-Linux
    fallback in practice: on the Debian-family hosts this project deploys to,
    `/etc/hosts` ships a stock `127.0.1.1 <hostname>` line that a statically
    assigned LAN IP does not update, so this call typically resolves to
    loopback only and this loop correctly finds nothing — the `ip` command
    above is what actually carries that case. Never raises: any resolver
    failure just means there is nothing to offer.
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
    # Apply the calibrated start cap on a fresh database. On a restart the
    # operator's live setting is already stored and must win (spec 7, 10.5).
    # A distinct setting key from the retired `min_mentions` on purpose: an
    # existing database that still carries `min_mentions` must never have that
    # value read as `max_terms` (spec 2026-08-29 §4).
    store.set_setting_default("max_terms", str(cfg.default_max_terms))
    # Same contract for the camera: a fresh station opens roaming (2026-08-26),
    # a restarted one comes back exactly as the operator left it.
    store.set_setting_default("camera_mode", cfg.default_camera_mode)
    bus = EventBus()
    transcript_log = TranscriptLog(cfg.transcript_log_path)
    # Anthropic oder ein OpenAI-kompatibler Endpunkt — entschieden allein von
    # der config.toml, Default unverändert Anthropic (kg/llm.py).
    llm = build_llm(cfg)
    # OpenRouter + persistent cache (spec 6.2). Nothing to warm up: no local
    # model, and repeated terms are served from the cache.
    embedder = build_embedder(cfg)

    # Second, small client for the one yes/no question behind the wake word
    # (spec 5, 2026-08-30). None when the way is switched off in the config.
    wake_llm = build_stop_intent_llm(cfg)

    core = Core(cfg, store, bus, transcript_log, llm, embedder, wake_llm=wake_llm)
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
