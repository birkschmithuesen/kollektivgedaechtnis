"""Headless 1920x1080 PNGs with the renderer that later runs live (spec 10.4).

Adapted from the plan's Task 20 Step 3. Per Birk's 2026-08-14 decision (see
the Task 20 brief), this does not depend on a simulation database (Tasks 18/19
don't exist yet): the CLI seeds each db directly through
`sim.seed_graph.seed_graph`. `render_series` itself stays a pure renderer over
existing dbs — it does not know or care how they were populated.

Fourth iteration (Birk's 2026-08-14 spec change, replacing spec 11's "existing
nodes stay put"): a graph change now makes the WHOLE net migrate slowly to a
better-distributed arrangement, and node/font size follow the viewport fit so
the picture always fills the wall. The layout is cytoscape-fcose, from the
library, not a hand-rolled pass. Three series answer that:

1. **Fill the screen** — the same seeded graph at 5 / 20 / 50 persons, each
   filling the canvas with type scaled to match. The evidence for "always
   readable, never overcrowded".
2. **The density dial**, again at min_mentions 1/2/3, but now with the
   re-layout: after hiding terms the survivors have SPREAD OUT into the freed
   space instead of sitting in their old holes. Canvas fill and overlap counts
   are reported per setting so the change against the third round is
   measurable.
3. **The migration itself** — a PNG cannot show motion, so one transition
   (the dial going 1 -> 2) is shot as a numbered sequence of frames taken at
   intervals through the animation. Nodes caught in mid-flight are the proof
   that it is a glide and not a cut.

The theme series (a/c), the camera series and the test pattern stay
regenerable behind flags; theme B is Birk's settled choice and the default.
"""

from __future__ import annotations

import argparse
import shutil
import socket
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import uvicorn

from kg.bus import EventBus
from kg.config import Config
from kg.server import create_app
from kg.store import Store


@dataclass(frozen=True)
class Shot:
    """One delivered PNG: where it is, what it shows, and what it measures."""

    path: Path
    description: str
    coverage: dict = field(default_factory=dict)


# The legibility ladder. Same graph, same palette — only type size and stroke
# weight change, which is the whole question that series asks.
SERIES = {
    "a": (
        "series-a-dark-base-label22",
        "A (reference): white on black, 22px labels, 5px rings, 2px edges — the concept rendering's weights.",
    ),
    "b": (
        "series-b-dark-larger-label32",
        "B: 32px labels (1.45x A), 7px rings, 20px term dots, 3px edges, 4px text outline — same ground, same palette.",
    ),
    "c": (
        "series-c-dark-largest-label44",
        "C: 44px labels (2x A), 10px rings, 28px term dots, 5px edges, 6px text outline — the upper end of the ladder.",
    ),
}

TESTPATTERN = (
    "series-d-testpattern-greyscale-and-font-ladder",
    "D: test pattern — greyscale wedge and font-size ladder, for the whiteboard's real black level on site.",
)

# Camera views over the identical graph. They call the live Camera component
# (window.kgView.camera), never cy.zoom/cy.pan directly: what is shot here is
# what the wall would actually do.
CAMERA_VIEWS = [
    (
        "camera-1-fit-all-reference",
        "Camera 1: fit mode, the whole net in frame — the reference view.",
        "() => { const c = window.kgView.camera; c.setZoomFactor(1); c.setMode('fit'); }",
    ),
    (
        "camera-2-zoom2x-half-the-net",
        "Camera 2: fit mode at zoom factor 2 — half the net's width across the wall, centred.",
        "() => { const c = window.kgView.camera; c.setMode('fit'); c.setZoomFactor(2); }",
    ),
    (
        "camera-3-cluster-closeup",
        "Camera 3: the camera on the tightest person-and-terms cluster in the net, plus whoever else falls in that frame — the view an automatic traversal dwells on.",
        # Deterministic pick: smallest cluster box by area, ties by person id.
        """() => {
             const cy = window.kgView.cy;
             let best = null;
             cy.nodes('.person').forEach((person) => {
               const cluster = person.union(person.neighborhood('node.term'));
               const box = cluster.boundingBox({ includeLabels: true });
               const area = box.w * box.h;
               if (!best || area < best.area || (area === best.area && person.id() < best.id)) {
                 best = { area, id: person.id(), cluster };
               }
             });
             window.kgView.camera.focus(best.cluster);
           }""",
    ),
]

# What the layout is judged by: the rendered box of all nodes as a fraction of
# the 1920x1080 canvas, plus how much of the net is in frame and how big the
# type reaches the wall.
MEASURE = """
() => {
  const cy = window.kgView.cy;
  const nodes = cy.nodes();
  const bare = nodes.renderedBoundingBox({ includeLabels: false });
  const withLabels = nodes.renderedBoundingBox({ includeLabels: true });
  const extent = cy.extent();
  // Keyed by node id, not summed: the density dial changes which nodes are
  // even present (term nodes below the threshold drop out), so a sum over a
  // shorter node set would drift even when every surviving node sits exactly
  // where it did. Sorted by id so two evaluations are comparable regardless
  // of cy's own iteration order.
  const placement = nodes
    .map((n) => [n.id(), Math.round(n.position('x') * 1000) / 1000, Math.round(n.position('y') * 1000) / 1000])
    .sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
  const inFrame = nodes.filter((n) => {
    const p = n.position();
    return p.x >= extent.x1 && p.x <= extent.x2 && p.y >= extent.y1 && p.y <= extent.y2;
  }).length;
  const term = cy.nodes('.term')[0];
  const person = cy.nodes('.person')[0];
  return {
    nodes: nodes.length,
    // What is actually on the wall at this shot — the density dial's whole
    // point, so it is reported per shot, not just derived from a filename.
    term_nodes: cy.nodes('.term').length,
    person_nodes: cy.nodes('.person').length,
    edges: cy.edges('.link').length,
    zoom: cy.zoom(),
    // Fingerprint of the placement, so a shared one can be asserted.
    placement,
    width_fraction: bare.w / cy.width(),
    height_fraction: bare.h / cy.height(),
    width_fraction_with_labels: withLabels.w / cy.width(),
    height_fraction_with_labels: withLabels.h / cy.height(),
    // The single "canvas fill" number Birk asked for in the fourth brief.
    area_fraction_with_labels: (withLabels.w * withLabels.h) / (cy.width() * cy.height()),
    nodes_in_frame: inFrame / nodes.length,
    // Model-unit type and disc sizes are constants of the theme; what reaches
    // the wall is that constant times the zoom, and THAT is the number the
    // fill-the-screen requirement is about.
    label_px_on_wall: term ? Number(term.numericStyle('font-size')) * cy.zoom() : null,
    person_px_on_wall: person ? Number(person.numericStyle('width')) * cy.zoom() : null,
    // The front end's own overlap count, not a second one computed here —
    // this file renders, it does not re-implement label-collision judgement.
    label_overlaps: window.kgView.labelOverlaps(),
    label_overlap_stats: window.kgView.labelOverlapStats,
  };
}
"""

# Positions are persisted by the renderer itself (POST /api/positions) and the
# next page load reads them back, which is also the crash-recovery path
# (spec 10.5): a restored graph is the one case that must NOT migrate.
POSITIONS_PERSISTED = """
async () => {
  const graph = await (await fetch('/graph.json')).json();
  return graph.nodes.every((n) => n.x !== null && n.x !== undefined);
}
"""

# Portraits are background-images: Cytoscape paints the ring first and fills
# it in whenever each file arrives. Without waiting for them a cold-cache run
# shoots half-drawn person nodes — which is exactly what a first run is.
PORTRAITS_LOADED = """
() =>
  Promise.all(
    window.kgView.cy
      .nodes('.person')
      .map((node) => node.data('portrait'))
      .filter(Boolean)
      .map(
        (url) =>
          new Promise((resolve) => {
            const image = new Image();
            image.onload = resolve;
            image.onerror = resolve;
            image.src = url;
          }),
      ),
  ).then(() => {
    // Cytoscape redraws by itself as each image lands, but say so explicitly
    // — and return a plain value, never the cy instance: serialising that
    // back to the driver crashes the page.
    window.kgView.cy.forceRender();
    return true;
  })
"""

# Start the transition AND the clock in one evaluation, so nothing between the
# two can be mistaken for animation time. `__glide` is stamped the moment the
# glide itself begins — the fcose computation and the placement passes run
# first and are not part of the animation being shot.
START_MIGRATION = """
(value) => {
  window.__glide = null;
  const watch = () => {
    if (window.kgView.migrating) {
      window.__glide = performance.now();
      return;
    }
    if (window.kgView.layoutPending) requestAnimationFrame(watch);
  };
  window.kgView.setMinMentions(value);
  requestAnimationFrame(watch);
}
"""


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


@contextmanager
def _served(db_path: Path, scratch: Path | None = None):
    """One app over one db — by default over a THROWAWAY COPY of it.

    The renderer persists the placement it settles on back into the database
    it is reading (POST /api/positions), and the next page load over that
    database deliberately restores it rather than laying the net out again
    (spec 10.5). That is correct for the wall and poison for a comparison
    series: whichever series ran first would silently pin the placement of
    every series after it, and re-running one series alone would not
    reproduce what the full run delivered. Found the hard way on 2026-08-15,
    when the camera series inherited the density series' arrangement and
    reported a close-up that was wider than the view it was zoomed into.

    So every series gets its own copy of the seeded state, and the seed is the
    only thing any of them depends on.
    """
    if scratch is not None:
        shutil.copytree(db_path.parent, scratch)
        db_path = scratch / db_path.name
    store = Store.open(db_path)
    base_url, shutdown = serve(store, Config(data_dir=db_path.parent))
    try:
        yield base_url
    finally:
        shutdown()
        store.close()


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


def _open_projection(page, base_url: str, theme: str, migration_ms: int | None = None) -> None:
    query = f"theme={theme}"
    if migration_ms:
        query += f"&migration={migration_ms}"
    page.goto(f"{base_url}/projection?{query}")
    # The 50-person / ~75-term graph, its fcose layout, the placement passes
    # and a 2.5s glide take real wall-clock time — 60s is the budget, not a
    # guess to shrink.
    page.wait_for_function("window.kgReady === true", timeout=60000)
    # Wait for the real signal, not a guessed duration: positions are final
    # only once the migration's computation AND its animation have finished.
    page.wait_for_function(
        "() => window.kgView && window.kgView.layoutPending === false",
        timeout=60000,
    )
    # The renderer POSTs the settled positions back; a later page load over
    # the same db must read them rather than lay the net out again.
    page.wait_for_function(POSITIONS_PERSISTED, timeout=60000)
    page.evaluate(PORTRAITS_LOADED)
    page.wait_for_timeout(500)  # let the final frame paint


THEME = "b"  # Birk's settled choice (third pre-render review)
FILL_SIZES = (5, 20, 50)
DENSITY_MIN_MENTIONS = (1, 2, 3)
# The dial step shot as a migration. 1 -> 2 removes the most terms of the
# three steps, so it is the transition with the most visible motion.
MIGRATION_FROM, MIGRATION_TO = 1, 2
# Fractions of the animation at which the frames are taken. The last one is
# not a fraction at all — it waits for the real end-of-migration signal, so
# the closing frame is the settled picture and not a near-miss.
MIGRATION_FRACTIONS = (0.0, 0.35, 0.7, 1.0)
# The wall's own glide length. The single source of truth is
# MIGRATION_DURATION_MS in frontend/static/projection.js; this copy exists so
# the printed report can say what the default is, and tests/test_prerender.py
# asserts the two agree rather than trusting a comment.
WALL_MIGRATION_MS = 2500
# The glide is slowed down for the frame sequence only, and the filenames say
# so. At the wall's own 2.5s a screenshot round trip eats a fifth of the
# animation, and four frames would bunch at the end instead of spanning it.
MIGRATION_SHOT_MS = 8000


def _fill_shots(page, dbs: dict[int, Path], out_dir: Path, theme: str, scratch: Path) -> list[Shot]:
    """The same seeded graph at three sizes, each filling the canvas.

    `seed_graph` walks its rng once per person, so a 5-person seed is a strict
    prefix of the 50-person one: these really are the same graph at three
    points in its life, not three different graphs.
    """
    shots: list[Shot] = []
    for persons in sorted(dbs):
        with _served(dbs[persons], scratch / f"fill-{persons:02d}") as base_url:
            _open_projection(page, base_url, theme)
            data = page.evaluate(MEASURE)
            stem = f"theme-{theme}-fill-{persons:02d}-persons-{data['term_nodes']}-terms"
            target = out_dir / f"{stem}.png"
            page.screenshot(path=str(target))
            shots.append(
                Shot(
                    target,
                    f"Fill the screen at {persons} persons / {data['term_nodes']} terms: "
                    f"labels reach the wall at {data['label_px_on_wall']:.0f}px and person discs "
                    f"at {data['person_px_on_wall']:.0f}px. Nothing in the theme changed between "
                    "these three shots — the viewport fit scales model-unit type and node sizes "
                    "with it, so a smaller net simply comes out larger.",
                    data,
                )
            )
    return shots


def _density_shots(page, base_url: str, out_dir: Path, theme: str, min_mentions_values) -> list[Shot]:
    """The dial's own series, through the real display-filter path
    (window.kgView.setMinMentions -> render() -> graph-model.js visibleGraph),
    never a second, special-case renderer that filters the graph data itself.

    Unlike the third round, each step now re-lays the net out: hiding terms
    frees space and the survivors migrate into it."""
    shots: list[Shot] = []
    _open_projection(page, base_url, theme)
    first = min_mentions_values[0]
    for value in min_mentions_values:
        page.evaluate(f"() => window.kgView.setMinMentions({value})")
        # Every dial step is a graph change now, so it runs a full migration.
        # Wait for the real end-of-migration signal, never a fixed timeout.
        page.wait_for_function("() => window.kgView.layoutPending === false", timeout=60000)
        page.wait_for_timeout(300)  # let the settled frame paint
        data = page.evaluate(MEASURE)
        # The filename carries the REAL remaining count, not the threshold
        # alone — a filename must tell Birk what he is looking at without
        # opening the file.
        qualifier = "all-" if value == first else ""
        stem = f"theme-{theme}-min-mentions-{value}-{qualifier}{data['term_nodes']}-terms"
        description = (
            f"Density dial at min_mentions={value}: {data['term_nodes']} term nodes, "
            f"{data['person_nodes']} persons, {data['edges']} edges on the wall — and the "
            "net re-distributed into the space the hidden terms freed, rather than "
            "keeping its old holes."
        )
        target = out_dir / f"{stem}.png"
        page.screenshot(path=str(target))
        shots.append(Shot(target, description, data))
    return shots


def _migration_shots(page, base_url: str, out_dir: Path, theme: str, duration_ms: int) -> list[Shot]:
    """One transition, several frames — the only way a PNG can show motion.

    The frames are timed off the glide's own start (`window.kgView.migrating`),
    not off the moment the dial was turned: the fcose run and the placement
    passes happen first and are not part of the animation being shown. Each
    frame's real elapsed time is measured and goes into its filename, so the
    sequence can be read without trusting the intended fraction.
    """
    shots: list[Shot] = []
    _open_projection(page, base_url, theme, migration_ms=duration_ms)
    page.evaluate(f"() => window.kgView.setMinMentions({MIGRATION_FROM})")
    page.wait_for_function("() => window.kgView.layoutPending === false", timeout=60000)

    page.evaluate(START_MIGRATION, MIGRATION_TO)
    page.wait_for_function("() => window.__glide !== null", timeout=60000)

    total = len(MIGRATION_FRACTIONS)
    for index, fraction in enumerate(MIGRATION_FRACTIONS, start=1):
        if fraction >= 1.0:
            page.wait_for_function("() => window.kgView.layoutPending === false", timeout=60000)
            page.wait_for_timeout(300)
        else:
            page.wait_for_function(
                f"() => performance.now() - window.__glide >= {fraction * duration_ms}",
                timeout=60000,
            )
        elapsed = page.evaluate("() => performance.now() - window.__glide")
        stem = (
            f"theme-{theme}-migration-dial-{MIGRATION_FROM}-to-{MIGRATION_TO}"
            f"-frame-{index}-of-{total}-t{elapsed / 1000:.1f}s"
        )
        target = out_dir / f"{stem}.png"
        page.screenshot(path=str(target))
        settled = fraction >= 1.0
        # Measuring costs O(n^2) bounding boxes and would eat animation time,
        # so only the settled frame carries the full coverage numbers. The
        # in-flight frames are pictures, and that is all they need to be.
        coverage = page.evaluate(MEASURE) if settled else {}
        state = (
            "the settled arrangement — every node has landed"
            if settled
            else f"{elapsed / duration_ms:.0%} through the glide, nodes in mid-flight"
        )
        shots.append(
            Shot(
                target,
                f"Migration frame {index}/{total} at t={elapsed / 1000:.1f}s of a "
                f"{duration_ms / 1000:.1f}s glide (the wall's own default is "
                f"{WALL_MIGRATION_MS / 1000:.1f}s; slowed here only so four frames "
                f"span the motion): {state}. "
                f"Trigger: the density dial moving {MIGRATION_FROM} -> {MIGRATION_TO}.",
                coverage,
            )
        )
    return shots


def render_series(
    dbs: dict[int, Path],
    out_dir: Path,
    theme: str = THEME,
    themes: tuple[str, ...] = (),
    include_fill_series: bool = True,
    include_density_series: bool = True,
    include_migration_series: bool = True,
    include_testpattern: bool = False,
    include_camera_views: bool = False,
    camera_theme: str = THEME,
    min_mentions_values: tuple[int, ...] = DENSITY_MIN_MENTIONS,
    migration_ms: int = MIGRATION_SHOT_MS,
) -> list[Shot]:
    """Render every requested series into `out_dir`.

    `dbs` maps a person count to a seeded database. Every series but the fill
    one runs against the largest — which is the wall at the end of the
    festival, and so the hard case.
    """
    from playwright.sync_api import sync_playwright

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    full = dbs[max(dbs)]

    shots: list[Shot] = []
    with tempfile.TemporaryDirectory(prefix="prerender-") as tmp, sync_playwright() as playwright:
        scratch = Path(tmp)
        browser = _launch_chromium(playwright)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        if include_fill_series:
            shots.extend(_fill_shots(page, dbs, out_dir, theme, scratch))
        if include_density_series:
            with _served(full, scratch / "density") as base_url:
                shots.extend(_density_shots(page, base_url, out_dir, theme, min_mentions_values))
        if include_migration_series:
            with _served(full, scratch / "migration") as base_url:
                shots.extend(_migration_shots(page, base_url, out_dir, theme, migration_ms))
        if themes:
            # One served copy for the whole ladder on purpose: the first theme
            # lays the net out and persists it, the rest restore it. Without
            # that shared placement, bigger type would spread the layout and
            # the camera's fit would zoom back out by the same factor —
            # the labels would reach the wall at the same size and the
            # comparison would compare nothing.
            with _served(full, scratch / "themes") as base_url:
                for extra in themes:
                    stem, description = SERIES[extra]
                    _open_projection(page, base_url, extra)
                    target = out_dir / f"{stem}.png"
                    page.screenshot(path=str(target))
                    shots.append(Shot(target, description, page.evaluate(MEASURE)))
        if include_camera_views:
            with _served(full, scratch / "camera") as base_url:
                _open_projection(page, base_url, camera_theme)
                for stem, description, setup in CAMERA_VIEWS:
                    page.evaluate(setup)
                    page.wait_for_timeout(200)
                    target = out_dir / f"{stem}.png"
                    page.screenshot(path=str(target))
                    shots.append(
                        Shot(target, f"{description} [theme {camera_theme}]", page.evaluate(MEASURE))
                    )
        if include_testpattern:
            with _served(full, scratch / "testpattern") as base_url:
                stem, description = TESTPATTERN
                page.goto(f"{base_url}/testpattern")
                page.wait_for_selector(".wedge")
                target = out_dir / f"{stem}.png"
                page.screenshot(path=str(target))
                shots.append(Shot(target, description))
        browser.close()
    return shots


def seed_sizes(state_dir: Path, sizes, seed: int, reseed: bool = False) -> dict[int, Path]:
    """One seeded db per size, all from the same seed.

    `seed_graph` walks its rng once per person, so the smaller ones are strict
    prefixes of the largest — the same graph earlier in its life. These are
    read-only masters: `render_series` copies each one before serving it, so
    nothing here accumulates a placement between runs.
    """
    from sim.seed_graph import seed_graph

    state_dir = Path(state_dir)
    if reseed and state_dir.exists():
        shutil.rmtree(state_dir)

    dbs: dict[int, Path] = {}
    for persons in sizes:
        data_dir = state_dir / f"fill-{persons:02d}"
        if data_dir.exists():
            dbs[persons] = Config(data_dir=data_dir).db_path
        else:
            dbs[persons] = seed_graph(data_dir, persons=persons, seed=seed)
    return dbs


def main() -> None:
    parser = argparse.ArgumentParser(prog="sim.prerender")
    parser.add_argument("--state", default="out/prerender4-state")
    parser.add_argument("--out", default="out/prerender4")
    parser.add_argument("--seed", type=int, default=20260814)
    parser.add_argument(
        "--sizes",
        type=int,
        nargs="+",
        default=list(FILL_SIZES),
        help="person counts for the fill-the-screen series. Same seed for all "
        "of them, so the smaller ones are prefixes of the largest.",
    )
    parser.add_argument(
        "--reseed",
        action="store_true",
        help="delete the seeded state first. The renderer persists node positions "
        "into it, so an existing state pins the placement — required after any "
        "change to the layout.",
    )
    parser.add_argument(
        "--themes",
        nargs="+",
        default=[],
        choices=sorted(SERIES),
        help="which type-size variants to render as their own full-graph shot "
        "(default: none — theme b, Birk's settled choice, is what every series "
        "below already uses)",
    )
    parser.add_argument(
        "--migration-ms",
        type=int,
        default=MIGRATION_SHOT_MS,
        help="glide length for the migration frame sequence only (default "
        f"{MIGRATION_SHOT_MS}; the wall's own default is 2500)",
    )
    parser.add_argument("--camera-views", action="store_true", help="also render the camera series")
    parser.add_argument("--testpattern", action="store_true", help="also render the greyscale/font-ladder test pattern")
    args = parser.parse_args()

    dbs = seed_sizes(Path(args.state), tuple(args.sizes), args.seed, reseed=args.reseed)

    shots = render_series(
        dbs,
        Path(args.out),
        themes=tuple(args.themes),
        include_testpattern=args.testpattern,
        include_camera_views=args.camera_views,
        migration_ms=args.migration_ms,
    )
    for shot in shots:
        print(shot.path.resolve())
        print(f"    {shot.description}")
        if shot.coverage:
            print(
                "    node cloud: {width_fraction:.0%} of canvas width, "
                "{height_fraction:.0%} of height (with labels "
                "{width_fraction_with_labels:.0%} x {height_fraction_with_labels:.0%}, "
                "{area_fraction_with_labels:.0%} of the canvas area); "
                "zoom {zoom:.3f}; {nodes_in_frame:.0%} of {nodes} nodes in frame".format(
                    **shot.coverage
                )
            )
            print(
                "    on the wall: {term_nodes} term nodes, {person_nodes} persons, "
                "{edges} edges; labels {label_px_on_wall:.0f}px, discs "
                "{person_px_on_wall:.0f}px".format(**shot.coverage)
            )
            stats = shot.coverage.get("label_overlap_stats")
            if stats:
                before, after = stats["before"], stats["after"]
                print(
                    f"    labels: {before['labelPairs']} overlapping pairs before -> "
                    f"{after['labelPairs']} after the declutter pass; "
                    f"{before['labelsOnPersons']} on person discs before -> "
                    f"{after['labelsOnPersons']} after"
                )


if __name__ == "__main__":
    main()
