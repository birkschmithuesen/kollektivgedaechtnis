"""Headless 1920x1080 PNGs with the renderer that later runs live (spec 10.4).

Adapted from the plan's Task 20 Step 3. Per Birk's 2026-08-14 decision (see
the Task 20 brief), this no longer depends on a simulation database (Tasks
18/19 don't exist yet): the CLI seeds the db directly through
`sim.seed_graph.seed_graph` if it doesn't already exist. `render_series`
itself stays a pure renderer over an existing db — it does not know or care
how that db was populated.

Second iteration (Birk's 2026-08-14 pre-render review, binding):
- the inverted light-ground variant is dropped; all three graph variants are
  white on black and differ in type size and stroke weight only,
- the placement fills the 16:9 canvas (see `frameToAspect` in projection.js),
  and every shot reports how much of the canvas the node cloud covers,
- a camera series shows what zoomed operation looks like over the SAME graph,
  since fit-all at 50 persons is settled as illegible.

Third iteration (Birk's 2026-08-14 review of series 2, item 3 of that brief):
- theme B (32px labels) is Birk's settled choice and is now the default
  graph theme rendered; A and C stay regenerable behind `--themes` for the
  final call, which only a real projector on site can make,
- the minimum-mentions dial (Task 13's display filter — graph-model.js
  `visibleGraph`, driven here through `window.kgView.setMinMentions`, never
  a second filtering renderer) gets its own series: the SAME placement shot
  at min_mentions 1/2/3, so the dial's own effect on crowding is visible
  before any layout fix is judged,
- and because that dial's first step (min_mentions=1) hides nothing, it IS
  the theme-B full-graph shot — so the type-ladder series renders nothing by
  default. Delivering the identical picture twice under two filenames would
  read as two findings; `--themes a c` regenerates the other two rungs.
- one more shot repeats the min_mentions=1 picture with the label-declutter
  pass switched off, so that improvement is seen against the identical
  graph, not only reported as a pair count,
- the camera series and the test pattern stay regenerable but are off by
  default this round — the question this round is the dial, not the camera.
"""

from __future__ import annotations

import argparse
import shutil
import socket
import threading
import time
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


# The legibility ladder. Same graph, same positions, same palette — only type
# size and stroke weight change, which is the whole question this series asks.
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
        "Camera 1: fit mode, the whole net in frame — the reference, and the view that is settled as illegible at 50 persons.",
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

# What the layout fix is judged by: the rendered box of all nodes as a
# fraction of the 1920x1080 canvas, plus how much of the net is in frame.
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
    nodes_in_frame: inFrame / nodes.length,
    // The front end's own overlap count, not a second one computed here —
    // this file renders, it does not re-implement label-collision judgement.
    label_overlaps: window.kgView.labelOverlaps(),
    label_overlap_stats: window.kgView.labelOverlapStats,
  };
}
"""

# Positions are persisted by the renderer itself (POST /api/positions) and the
# next variant loads them, so every variant shares one placement — without
# that, a bigger label size would spread the layout out and the camera's fit
# would zoom back out by the same factor, leaving the type visually identical
# and the whole comparison meaningless.
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


def _open_projection(page, base_url: str, theme: str) -> None:
    page.goto(f"{base_url}/projection?theme={theme}")
    # The 50-person / ~75-term graph and its animated cose layout take real
    # wall-clock time — 60s (not the toy-graph 20s the plan used) is the
    # budget, not a guess to shrink.
    page.wait_for_function("window.kgReady === true", timeout=60000)
    # Wait for the real signal, not a guessed duration: the cose layout is
    # animated and nodes are still moving until layoutstop.
    page.wait_for_function(
        "() => window.kgView && window.kgView.layoutPending === false",
        timeout=60000,
    )
    # The renderer POSTs the settled positions back; the next page load must
    # read them, not lay the net out a second time.
    page.wait_for_function(POSITIONS_PERSISTED, timeout=60000)
    page.evaluate(PORTRAITS_LOADED)
    page.wait_for_timeout(500)  # let the final frame paint


# The dial's own series (Task 3 of the third brief). Same graph, same
# placement, only the threshold moves — through the real display-filter path
# (window.kgView.setMinMentions -> render() -> graph-model.js visibleGraph),
# never a second, special-case renderer that filters the graph data itself.
DENSITY_MIN_MENTIONS = (1, 2, 3)
DENSITY_THEME = "b"  # Birk's settled choice this round (see module docstring)


def _density_shots(page, base_url: str, out_dir: Path, theme: str, min_mentions_values) -> list[Shot]:
    shots: list[Shot] = []
    _open_projection(page, base_url, theme)
    first = min_mentions_values[0]
    for value in min_mentions_values:
        page.evaluate(f"() => window.kgView.setMinMentions({value})")
        # No new nodes arrive when the dial only hides existing ones, so
        # render() never starts a layout — layoutPending stays false and this
        # is purely the declutter pass (over fewer, now-visible labels)
        # settling, not a layout wait.
        page.wait_for_timeout(200)
        data = page.evaluate(MEASURE)
        # The filename carries the REAL remaining count, not the threshold
        # alone — a filename must tell Birk what he is looking at without
        # opening the file.
        qualifier = "all-" if value == first else ""
        stem = f"theme-{theme}-min-mentions-{value}-{qualifier}{data['term_nodes']}-terms"
        description = (
            f"Density dial at min_mentions={value}: {data['term_nodes']} term nodes, "
            f"{data['person_nodes']} persons, {data['edges']} edges on the wall — same "
            "placement as the other two steps, only the dial moved."
        )
        target = out_dir / f"{stem}.png"
        page.screenshot(path=str(target))
        shots.append(Shot(target, description, data))

    # BEFORE/AFTER declutter comparison on the exact picture the min_mentions
    # equal to `first` shot above already is — so the improvement is seen
    # against the identical graph, not only reported as a pair count.
    page.evaluate(f"() => window.kgView.setMinMentions({first})")
    page.wait_for_timeout(200)
    page.evaluate("() => window.kgView.resetLabelOffsets()")
    page.wait_for_timeout(200)
    before_data = page.evaluate(MEASURE)
    before_target = out_dir / f"theme-{theme}-min-mentions-{first}-labels-BEFORE-declutter.png"
    page.screenshot(path=str(before_target))
    page.evaluate("() => window.kgView.declutterLabels()")
    page.wait_for_timeout(200)
    after_overlaps = page.evaluate("() => window.kgView.labelOverlaps()")
    # Override the generic auto-recorded stats: those describe the LAST
    # render's own pass, not this manual reset/redeclutter demonstration.
    before_data["label_overlap_stats"] = {"before": before_data["label_overlaps"], "after": after_overlaps}
    shots.append(
        Shot(
            before_target,
            f"Same picture as min_mentions={first} above, label declutter pass switched OFF: "
            f"{before_data['label_overlaps']['labelPairs']} overlapping label pairs "
            f"(vs {after_overlaps['labelPairs']} once the pass runs).",
            before_data,
        )
    )
    return shots


def render_series(
    db_path: Path,
    out_dir: Path,
    themes: tuple[str, ...] = (),
    include_testpattern: bool = False,
    include_camera_views: bool = False,
    camera_theme: str = "a",
    include_density_series: bool = True,
    density_theme: str = DENSITY_THEME,
    min_mentions_values: tuple[int, ...] = DENSITY_MIN_MENTIONS,
) -> list[Shot]:
    from playwright.sync_api import sync_playwright

    db_path = Path(db_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = Config(data_dir=db_path.parent)
    store = Store.open(db_path)
    base_url, shutdown = serve(store, cfg)
    shots: list[Shot] = []
    try:
        with sync_playwright() as playwright:
            browser = _launch_chromium(playwright)
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            for theme in themes:
                stem, description = SERIES[theme]
                _open_projection(page, base_url, theme)
                target = out_dir / f"{stem}.png"
                page.screenshot(path=str(target))
                shots.append(Shot(target, description, page.evaluate(MEASURE)))
            if include_density_series:
                shots.extend(_density_shots(page, base_url, out_dir, density_theme, min_mentions_values))
            if include_camera_views:
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
                stem, description = TESTPATTERN
                page.goto(f"{base_url}/testpattern")
                page.wait_for_selector(".wedge")
                target = out_dir / f"{stem}.png"
                page.screenshot(path=str(target))
                shots.append(Shot(target, description))
            browser.close()
    finally:
        shutdown()
        store.close()
    return shots


def main() -> None:
    from sim.seed_graph import seed_graph

    parser = argparse.ArgumentParser(prog="sim.prerender")
    parser.add_argument("--db", default="out/prerender3-state/kg.db")
    parser.add_argument("--out", default="out/prerender3")
    parser.add_argument("--persons", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260814)
    parser.add_argument(
        "--reseed",
        action="store_true",
        help="delete the seeded state first. The renderer persists node positions "
        "into it, so an existing db pins the placement — required after any "
        "change to the layout.",
    )
    parser.add_argument(
        "--themes",
        nargs="+",
        default=[],
        choices=sorted(SERIES),
        help="which type-size variants to render as their own full-graph shot "
        "(default: none — theme b, Birk's settled choice this round, is already "
        "the density series' min_mentions=1 shot; pass a and/or c to regenerate "
        "the other rungs for the on-site projector call)",
    )
    parser.add_argument(
        "--camera-theme",
        default="a",
        choices=sorted(SERIES),
        help="theme for the camera series (default a, so it compares directly with series A)",
    )
    parser.add_argument(
        "--camera-views", action="store_true", help="also render the camera series (off by default this round)"
    )
    parser.add_argument(
        "--testpattern",
        action="store_true",
        help="also render the greyscale/font-ladder test pattern (off by default this round)",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if args.reseed and db_path.parent.exists():
        shutil.rmtree(db_path.parent)
    if not db_path.exists():
        seed_graph(db_path.parent, persons=args.persons, seed=args.seed)

    shots = render_series(
        db_path,
        Path(args.out),
        themes=tuple(args.themes),
        include_testpattern=args.testpattern,
        include_camera_views=args.camera_views,
        camera_theme=args.camera_theme,
    )
    for shot in shots:
        print(shot.path.resolve())
        print(f"    {shot.description}")
        if shot.coverage:
            print(
                "    node cloud: {width_fraction:.0%} of canvas width, "
                "{height_fraction:.0%} of height (with labels "
                "{width_fraction_with_labels:.0%} x {height_fraction_with_labels:.0%}); "
                "zoom {zoom:.3f}; {nodes_in_frame:.0%} of {nodes} nodes in frame".format(
                    **shot.coverage
                )
            )
            if "term_nodes" in shot.coverage:
                print(
                    "    on the wall: {term_nodes} term nodes, {person_nodes} persons, "
                    "{edges} edges".format(**shot.coverage)
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
