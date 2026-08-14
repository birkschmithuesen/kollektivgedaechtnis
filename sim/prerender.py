"""Headless 1920x1080 PNGs with the renderer that later runs live (spec 10.4).

Adapted from the plan's Task 20 Step 3. Per Birk's 2026-08-14 decision (see
the Task 20 brief), this no longer depends on a simulation database (Tasks
18/19 don't exist yet): the CLI seeds the db directly through
`sim.seed_graph.seed_graph` if it doesn't already exist. `render_series`
itself stays a pure renderer over an existing db — it does not know or care
how that db was populated.
"""

from __future__ import annotations

import argparse
import socket
import threading
import time
from pathlib import Path

import uvicorn

from kg.bus import EventBus
from kg.config import Config
from kg.server import create_app
from kg.store import Store


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def serve(store, cfg) -> tuple[str, callable]:
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(store, cfg, EventBus()), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        raise RuntimeError("prerender server did not start")

    def shutdown() -> None:
        server.should_exit = True
        thread.join(timeout=10)

    return f"http://127.0.0.1:{port}", shutdown


def _launch_chromium(playwright):
    # This Debian 11 host cannot `playwright install` the pinned chromium
    # revision (no network access, OS predates what it needs), but a
    # compatible build is already cached. Same fallback as tests/conftest.py
    # — reused here, not reinvented, or this breaks on this exact machine.
    try:
        return playwright.chromium.launch()
    except Exception:
        candidates = sorted(Path.home().glob(".cache/ms-playwright/chromium-*/chrome-linux64/chrome"))
        if not candidates:
            raise
        return playwright.chromium.launch(executable_path=str(candidates[-1]))


def render_series(
    db_path: Path,
    out_dir: Path,
    themes: tuple[str, ...] = ("a", "b", "c"),
    include_testpattern: bool = True,
) -> list[Path]:
    from playwright.sync_api import sync_playwright

    db_path = Path(db_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = Config(data_dir=db_path.parent)
    store = Store.open(db_path)
    base_url, shutdown = serve(store, cfg)
    written: list[Path] = []
    try:
        with sync_playwright() as playwright:
            browser = _launch_chromium(playwright)
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            for theme in themes:
                page.goto(f"{base_url}/projection?theme={theme}")
                # The 50-person / ~70-term graph and its animated cose layout
                # take real wall-clock time — 60s (not the toy-graph 20s the
                # plan used) is the budget, not a guess to shrink.
                page.wait_for_function("window.kgReady === true", timeout=60000)
                # Wait for the real signal, not a guessed duration: the cose
                # layout is animated and nodes are still moving until layoutstop.
                page.wait_for_function(
                    "() => window.kgView && window.kgView.layoutPending === false",
                    timeout=60000,
                )
                page.wait_for_timeout(200)  # let the final frame paint
                target = out_dir / f"{theme}.png"
                page.screenshot(path=str(target))
                written.append(target)
            if include_testpattern:
                page.goto(f"{base_url}/testpattern")
                page.wait_for_selector(".wedge")
                target = out_dir / "d.png"
                page.screenshot(path=str(target))
                written.append(target)
            browser.close()
    finally:
        shutdown()
        store.close()
    return written


def main() -> None:
    from sim.seed_graph import seed_graph

    parser = argparse.ArgumentParser(prog="sim.prerender")
    parser.add_argument("--db", default="out/prerender-state/kg.db")
    parser.add_argument("--out", default="out/prerender")
    parser.add_argument("--persons", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260814)
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        seed_graph(db_path.parent, persons=args.persons, seed=args.seed)

    for path in render_series(db_path, Path(args.out)):
        print(path)


if __name__ == "__main__":
    main()
