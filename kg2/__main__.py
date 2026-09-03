"""Entrypoint: one process, two concerns (the poll loop and the HTTP server)."""

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
from kg.llm import LLMClient
from kg2.config import load_dream_config
from kg2.server import create_dream_app, seed_display_settings
from kg2.store import DreamStore
from kg2.watcher import DreamWatcher


def resolved_host(host: str) -> str:
    """The address to PRINT. Never the address to bind.

    A deliberate DUPLICATE of `kg.__main__.resolved_host` (Finding 4), not an
    import from there: `kg.__main__` transitively imports `kg.store`,
    `kg.core`, `kg.server`, `kg.pipeline`, `kg.merging`, `kg.telegram_bot` and
    PIL — every one of them on the spec's list of modules Tool 2 must never
    import — even though this function opens no DB and starts no server. That
    cost nothing while both tools shared one install, but it made the "Tool 2
    never imports those three" guarantee weaker than it reads: if the dream
    machine's install is ever slimmed down, `python -m kg2` would die at 9
    a.m. on a missing Pillow, with a traceback that looks nothing like its
    real cause. `resolved_host` has no dependency on anything `kg`-specific,
    so copying its ~80 lines here is cheaper than the alternative — a module
    shared by both `__main__`s, which would recreate exactly the import
    coupling this duplication exists to prevent.

    Binding to `0.0.0.0` is correct and stays exactly as configured — that is
    what makes Tool 2's operator UI reachable from a second device on the
    exhibition LAN (spec §3.1). Printing it is a trap:
    `http://0.0.0.0:8810/operator` opens nothing from another box, and
    `docs/operations.md` tells the operator to open what this line prints. So
    the wildcard is resolved through up to three attempts, each one a
    fallback for the last one's blind spot, before honestly giving up to
    localhost.

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
    cfg = load_dream_config(Path(args.config) if args.config else None)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    store = DreamStore.open(cfg.db_path)
    seed_display_settings(store, cfg)
    bus = EventBus()
    # kg.llm is a pure client wrapper — no store, no core, no server (spec §3).
    # Anbieter und Schlüssel kommen aus der Konfiguration, nicht fest aus dem
    # Code: der Default bleibt Anthropic, `condense_api_mode =
    # "chat_completions"` schaltet auf einen OpenAI-kompatiblen Endpunkt
    # (Infomaniak). Bei Kimi K2.6 gehört `condense_reasoning_effort = "none"`
    # dazu — siehe die Messung in kg2/config.py.
    llm = LLMClient(
        model=cfg.condense_model,
        effort=cfg.condense_effort,
        max_tokens=cfg.condense_max_tokens,
        api_key=cfg.condense_api_key,
        api_mode=cfg.condense_api_mode,
        url=cfg.condense_url or None,
        reasoning_effort=cfg.condense_reasoning_effort or None,
        retry_budget_s=cfg.condense_retry_budget_s,
    )

    # 🔴 EIGENER CLIENT FUERS HAIKU (Birk, 2026-09-02). Nicht derselbe wie
    # oben: Kimi K2.6 braucht `reasoning_effort = "none"` und kann damit keine
    # Silben zaehlen — 3 von 32 Versuchen. Gemma kennt das Feld nicht, braucht
    # es nicht, und trifft mit der Silbenschleife 19–20 von 20.
    #
    # Gleiche URL, gleicher Schluessel, gleicher Anbieter: die Kette bleibt
    # EU-souveraen. `haiku_model` leer schaltet das Haiku ab.
    haiku_llm = None
    if cfg.haiku_model:
        haiku_llm = LLMClient(
            model=cfg.haiku_model,
            effort=cfg.condense_effort,
            max_tokens=cfg.condense_max_tokens,
            api_key=cfg.condense_api_key,
            api_mode=cfg.condense_api_mode,
            url=cfg.condense_url or None,
            reasoning_effort=cfg.haiku_reasoning_effort or None,
            retry_budget_s=cfg.condense_retry_budget_s,
        )

    app = create_dream_app(store, cfg, bus)
    server = uvicorn.Server(
        uvicorn.Config(app, host=cfg.server_host, port=cfg.server_port, log_level="info")
    )

    tasks = [asyncio.create_task(server.serve())]
    if not args.no_watch:
        watcher = DreamWatcher(cfg, store, bus, llm, haiku_llm=haiku_llm)
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
