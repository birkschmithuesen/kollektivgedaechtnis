"""The page at 1 / 5 / 20 / 40 dreams (spec §11's visual series).

Tool 1's Task 20 rule, held here: **the strip is judged FULL, not empty.** One
dream tells you nothing about forty, and forty is what the wall looks like at
17:00 — the state that actually has to be approved.

Build order, decided 2026-08-25: the cheap path FIRST. `--pool` seeds from a
handful of images so the harness can be made correct offline and for free; only
then is `--generate` run, so forty real images are spent on a page that already
works rather than on debugging a screenshot loop.
"""

from __future__ import annotations

import argparse
import shutil
import socket
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import uvicorn

from kg.bus import EventBus
from kg2.config import DreamConfig
from kg2.server import create_dream_app, seed_display_settings
from kg2.store import DreamStore

SIZES = (1, 5, 20, 40)


@dataclass(frozen=True)
class Shot:
    path: Path
    description: str
    coverage: dict = field(default_factory=dict)


# What the layout is judged by. Measured in the page, not guessed from the CSS.
MEASURE = """
() => {
  const strip = document.getElementById('strip');
  const stage = document.getElementById('stage');
  const sentence = document.getElementById('sentence');
  const thumbs = Array.from(strip.children);
  const box = (el) => el.getBoundingClientRect();
  return {
    strip_items: thumbs.length,
    strip_height_fraction: box(strip).height / window.innerHeight,
    stage_height_fraction: box(stage).height / window.innerHeight,
    // Asymmetric by design (spec §6): the current dream is the subject.
    stage_to_thumb: thumbs.length ? box(stage).height / box(thumbs[0]).height : null,
    thumb_width_px: thumbs.length ? box(thumbs[0]).width : null,
    sentence_px: parseFloat(getComputedStyle(sentence).fontSize),
    sentence_lines: Math.round(box(sentence).height /
      parseFloat(getComputedStyle(sentence).lineHeight)),
    // Everything must be inside the viewport, at every size.
    overflows: box(strip).bottom > window.innerHeight + 1,
  };
}
"""


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _serve(store, cfg):
    """The REAL app on an ephemeral port — same pattern as sim/prerender.py."""
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_dream_app(store, cfg, EventBus()),
                       host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        raise RuntimeError("dream prerender server did not start")

    def shutdown():
        server.should_exit = True
        thread.join(timeout=10)

    return f"http://127.0.0.1:{port}", shutdown


def _launch_chromium(playwright):
    # Same fallback as tests/conftest.py and sim/prerender.py: this host cannot
    # `playwright install` the pinned revision, but a compatible build is
    # cached. Reused rather than reinvented, or this breaks on this machine.
    try:
        return playwright.chromium.launch()
    except Exception:
        candidates = sorted(
            Path.home().glob(".cache/ms-playwright/chromium-*/chrome-linux64/chrome")
        )
        if not candidates:
            raise
        return playwright.chromium.launch(executable_path=str(candidates[-1]))


def render_series(dbs: dict[int, Path], out_dir, sizes=SIZES) -> list[Shot]:
    """One screenshot per size, through the real page and the real server."""
    from playwright.sync_api import sync_playwright

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    shots: list[Shot] = []

    with tempfile.TemporaryDirectory(prefix="dream-prerender-") as tmp, sync_playwright() as pw:
        scratch = Path(tmp)
        browser = _launch_chromium(pw)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        for size in sizes:
            # A throwaway copy per size, for the same reason Tool 1's series
            # takes one: a series must be reproducible from its seed alone.
            copy = scratch / f"size-{size:02d}"
            shutil.copytree(dbs[size].parent, copy)
            cfg = DreamConfig(data_dir=copy)
            store = DreamStore.open(cfg.db_path)
            seed_display_settings(store, cfg)
            base_url, shutdown = _serve(store, cfg)
            try:
                page.goto(f"{base_url}/dream")
                page.wait_for_function("window.kgDreamReady === true", timeout=30000)
                page.wait_for_function(
                    "() => window.kgDream.fading === false", timeout=30000
                )
                # Let every thumbnail decode before the shot, or a cold cache
                # produces a strip of empty boxes — Tool 1 hit exactly this
                # with portraits.
                page.evaluate(
                    "() => Promise.all(Array.from(document.images)"
                    ".filter((i) => !i.complete)"
                    ".map((i) => new Promise((r) => { i.onload = r; i.onerror = r; })))"
                )
                page.wait_for_timeout(400)
                coverage = page.evaluate(MEASURE)
                target = out_dir / f"dream-{size:02d}-dreams.png"
                page.screenshot(path=str(target))
                shots.append(
                    Shot(
                        target,
                        f"Der Traum-Schirm bei {size} Träumen: "
                        f"{coverage['strip_items']} im Streifen, Streifen "
                        f"{coverage['strip_height_fraction']:.0%} der Bildhöhe, "
                        f"aktuelles Bild {coverage['stage_height_fraction']:.0%}. "
                        f"Der Satz steht in {coverage['sentence_lines']} Zeile(n) "
                        f"bei {coverage['sentence_px']:.0f}px.",
                        coverage,
                    )
                )
            finally:
                shutdown()
                store.close()
        browser.close()
    return shots


def _pool_images(source: Path) -> list[Path]:
    images = sorted(Path(source).glob("*.png"))
    if not images:
        raise SystemExit(
            f"no PNGs in {source}. Run `python -m sim.dream_register --out {source}` "
            "first, or point --pool at a directory that has some."
        )
    return images


def _generate_images(count: int, out: Path, cfg) -> list[Path]:
    """The expensive path: `count` real images in the configured register.

    COST: one image-model call per image. At 40 that is 40 calls. Run this ONLY
    once the series is known to render correctly from --pool.
    """
    from kg2.imagegen import build_image_prompt, render_image, save_image
    from sim.seed_dreams import SENTENCES

    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for index in range(count):
        target = out / f"generated-{index:02d}.png"
        if target.exists():
            paths.append(target)
            continue
        prompt = build_image_prompt(
            SENTENCES[index], cfg.visual_register, cfg.image_aspect_ratio
        )
        data = render_image(
            prompt, model=cfg.image_model, api_key=cfg.openrouter_api_key,
            url=cfg.image_url, timeout=cfg.image_timeout_s,
        )
        save_image(data, target)
        print(f"  {index + 1}/{count} {target.name}")
        paths.append(target)
    return paths


def main() -> None:
    from kg2.config import load_dream_config
    from sim.seed_dreams import seed_dreams

    parser = argparse.ArgumentParser(prog="sim.dream_prerender")
    parser.add_argument("--out", default="out/dream-prerender1")
    parser.add_argument("--state", default="out/dream-prerender1-state")
    parser.add_argument("--config", default=None)
    parser.add_argument("--sizes", type=int, nargs="+", default=list(SIZES))
    parser.add_argument(
        "--pool",
        default="out/register1",
        help="directory of PNGs to cycle through (the cheap path, and the "
        "default: the harness must be correct before real images are spent)",
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="render one REAL image per dream in the configured register. "
        "COSTS one image-model call per dream — 40 calls for the full series. "
        "Run this only once --pool has proved the page renders correctly.",
    )
    args = parser.parse_args()

    cfg = load_dream_config(Path(args.config) if args.config else None)
    largest = max(args.sizes)

    if args.generate:
        print(f"Generating {largest} real images — {largest} calls to {cfg.image_model}.")
        images = _generate_images(largest, Path(args.state) / "generated", cfg)
    else:
        images = _pool_images(Path(args.pool))
        print(
            f"Pool path: {len(images)} images cycled across up to {largest} dreams. "
            "The variety in the strip is FAKE — use --generate before judging it."
        )

    dbs = {}
    for size in sorted(args.sizes):
        state = Path(args.state) / f"dreams-{size:02d}"
        shutil.rmtree(state, ignore_errors=True)
        dbs[size] = seed_dreams(state, count=size, images=images)

    for shot in render_series(dbs, Path(args.out), tuple(sorted(args.sizes))):
        print(shot.path.resolve())
        print(f"    {shot.description}")
        if shot.coverage.get("overflows"):
            print("    WARNUNG: der Streifen läuft unten aus dem Bild.")


if __name__ == "__main__":
    main()
