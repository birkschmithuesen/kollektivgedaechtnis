"""The page at 1 / 5 / 20 / 40 dreams (spec §11's visual series).

Tool 1's Task 20 rule, held here: **the strip is judged FULL, not empty.** One
dream tells you nothing about forty, and forty is what the wall looks like at
17:00 — the state that actually has to be approved.

Build order, decided 2026-08-25: the cheap path FIRST. `--pool` seeds from a
handful of images so the harness can be made correct offline and for free; only
then is `--generate` run, so forty real images are spent on a page that already
works rather than on debugging a screenshot loop.

Review finding (2026-08-26): the strip's crop-vs-shrink trade-off at realistic
counts is an artistic call, not this module's — `--strip-mode` renders the page
against whichever of `cover` / `aspect` / `wrap` frontend2/static/dream.css
defines (see that file), so Birk compares real screenshots instead of the
implementer choosing for him. And a pool of SOLID-COLOUR placeholders proved
nothing about cropping — a crop of a flat colour is still that flat colour —
so `--placeholder-pool` builds a content-bearing one instead (shapes across the
full frame, not a colour swatch).
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
    // Both dimensions, not just width: --strip-mode=aspect/wrap change the
    // per-thumbnail HEIGHT too (cover's is fixed; the other two are not),
    // and that is exactly what the comparison is judged on.
    thumb_width_px: thumbs.length ? box(thumbs[0]).width : null,
    thumb_height_px: thumbs.length ? box(thumbs[0]).height : null,
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


def render_series(
    dbs: dict[int, Path], out_dir, sizes=SIZES, strip_mode: str = "cover"
) -> list[Shot]:
    """One screenshot per size, through the real page and the real server.

    `strip_mode` is passed as a URL query param (`?strip_mode=...`), read once
    by dream.html/dream-harness.html's inline script — no server-side change
    needed, since the mode only ever affects dream.css's rendering. The
    filename carries the mode too (Finding 1): Birk must be able to tell the
    files apart without opening them, and a directory of same-named
    screenshots overwritten three times over would tell him nothing.
    """
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
                page.goto(f"{base_url}/dream?strip_mode={strip_mode}")
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
                target = out_dir / f"dream-{size:02d}-dreams-{strip_mode}.png"
                page.screenshot(path=str(target))
                # thumb_*_px is None at size 1 (no history yet, nothing in the
                # strip to measure) — the f-string must not crash on that.
                thumb_size = (
                    f"{coverage['thumb_width_px']:.0f}×{coverage['thumb_height_px']:.0f}px"
                    if coverage["thumb_width_px"] is not None
                    else "n/a (leerer Streifen)"
                )
                shots.append(
                    Shot(
                        target,
                        f"Der Traum-Schirm bei {size} Träumen, Streifen-Modus "
                        f"'{strip_mode}': {coverage['strip_items']} im Streifen, "
                        f"Streifen {coverage['strip_height_fraction']:.0%} der "
                        f"Bildhöhe, aktuelles Bild {coverage['stage_height_fraction']:.0%}, "
                        f"Thumbnail {thumb_size}. "
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


def _check_generate_credentials(cfg, count: int) -> None:
    """Same bar `_pool_images` already sets: a clean `SystemExit` with what to
    do, never a raw traceback through `_generate_images -> render_image ->
    ImageError`. Checked here, before `_generate_images` is even entered — no
    money is wasted either way (`render_image` checks before the network
    call too), but a traceback is not an actionable message, and the operator
    running this by hand on festival morning needs one line telling them what
    to export and what it will cost, not a stack trace to read past.
    """
    if not cfg.openrouter_api_key:
        raise SystemExit(
            "OPENROUTER_API_KEY is not set. Export it before running --generate "
            f"— this run would cost {count} calls to {cfg.image_model} "
            "(one real image per dream)."
        )


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


#: Distinct per index so the pool images differ from each other, not just
#: from a plain colour. The left/centre/right shapes stay the SAME type in
#: every image (rectangle / circle / triangle) — what changes with the crop
#: is not "which shape" but "how much of it is still there", which is the
#: thing being measured. Alphabetical-free; there is no ranking to imply.
_PLACEHOLDER_BACKGROUNDS = [
    (30, 33, 38), (52, 30, 58), (24, 48, 42), (58, 46, 22),
    (26, 26, 52), (46, 24, 24), (22, 46, 50), (48, 48, 20),
]
_PLACEHOLDER_LEFT = (214, 92, 64)     # rectangle, left third
_PLACEHOLDER_CENTRE = (72, 150, 224)  # circle, centre third
_PLACEHOLDER_RIGHT = (104, 196, 132)  # triangle, right third
_PLACEHOLDER_SIZE = (1600, 900)


def make_placeholder_pool(out_dir: Path, count: int) -> list[Path]:
    """`count` distinct 1600x900 PNGs with content across the FULL frame.

    Finding 1's root cause: the earlier placeholder pool was solid colours,
    and a CROP of a solid colour is still that solid colour — so the pool
    could not show whether cropping had destroyed anything. A shape at each
    third plus a large index number means a crop that keeps only the centre
    is visibly different from the whole frame, which is the honest version of
    the same test.
    """
    from PIL import Image, ImageDraw, ImageFont

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    width, height = _PLACEHOLDER_SIZE
    try:
        font = ImageFont.load_default(size=height // 2)
    except TypeError:  # Pillow < 10.1 has no `size` kwarg on load_default
        font = ImageFont.load_default()

    paths = []
    for index in range(count):
        image = Image.new("RGB", (width, height), _PLACEHOLDER_BACKGROUNDS[
            index % len(_PLACEHOLDER_BACKGROUNDS)
        ])
        draw = ImageDraw.Draw(image)
        third = width // 3
        margin = height // 6
        draw.rectangle(
            [margin, margin, third - margin, height - margin], fill=_PLACEHOLDER_LEFT
        )
        draw.ellipse(
            [third + margin, margin, 2 * third - margin, height - margin],
            fill=_PLACEHOLDER_CENTRE,
        )
        draw.polygon(
            [
                (2 * third + margin, height - margin),
                ((2 * third + width) // 2, margin),
                (width - margin, height - margin),
            ],
            fill=_PLACEHOLDER_RIGHT,
        )
        draw.text(
            (width / 2, height / 2), str(index),
            fill="white", anchor="mm", font=font, stroke_width=6, stroke_fill="black",
        )
        path = out_dir / f"placeholder-{index:02d}.png"
        image.save(path)
        paths.append(path)
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
    parser.add_argument(
        "--strip-mode",
        choices=["aspect", "cover", "wrap"],
        default="cover",
        help="which history-strip layout dream.css renders (Finding 1: an "
        "artistic call left open, not picked here). 'cover' is today's "
        "behaviour and stays the default so nothing changes unless asked; "
        "listed alphabetically, which implies no preference.",
    )
    parser.add_argument(
        "--placeholder-pool",
        type=int,
        default=None,
        metavar="N",
        help="write N distinct content-bearing 1600x900 placeholder PNGs to "
        "--placeholder-pool-out and exit, instead of rendering anything. A "
        "solid-colour pool crops to the same solid colour at any width and "
        "proves nothing about the strip; point --pool at the output "
        "afterwards to render the comparison against it.",
    )
    parser.add_argument(
        "--placeholder-pool-out",
        default="out/dream-placeholder-pool",
        help="output directory for --placeholder-pool",
    )
    args = parser.parse_args()

    if args.placeholder_pool is not None:
        paths = make_placeholder_pool(Path(args.placeholder_pool_out), args.placeholder_pool)
        print(f"{len(paths)} placeholder PNGs written to {Path(args.placeholder_pool_out).resolve()}")
        for path in paths:
            print(f"  {path.name}")
        return

    cfg = load_dream_config(Path(args.config) if args.config else None)
    largest = max(args.sizes)

    if args.generate:
        _check_generate_credentials(cfg, largest)
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

    for shot in render_series(dbs, Path(args.out), tuple(sorted(args.sizes)), args.strip_mode):
        print(shot.path.resolve())
        print(f"    {shot.description}")
        if shot.coverage.get("overflows"):
            print("    WARNUNG: der Streifen läuft unten aus dem Bild.")


if __name__ == "__main__":
    main()
