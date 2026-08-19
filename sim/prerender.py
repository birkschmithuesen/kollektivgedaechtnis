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

Fifth iteration (Birk, 2026-08-15). Four stills cannot show a glide — played
back they look exactly like the jumping the migration exists to disprove. So
this module also renders FRAME SEQUENCES, dense enough to become video: 25 fps
across the wall's own 2.5s glide plus a settled tail, one directory per
transition, encoded to H.264 if an ffmpeg binary can be found. Three of them —
the dial going up, the dial coming back down (the hard direction, the one that
used to re-shuffle), and a new person joining a settled net, which is the
transition the audience actually sees most often.

Those frames are captured on a CONTROLLED CLOCK (`_FRAME_CLOCK` below), not by
screenshotting a running animation: a 1920x1080 screenshot costs a fifth of a
2.5s glide, so real-time sampling would bunch the frames at one end and would
not repeat between runs. Determinism is a requirement of every round of this
series, and it now covers motion as well as placement. It covers the MODEL:
the PNGs themselves are not byte-reproducible, because Cytoscape rasterises a
label into its texture cache at a sub-pixel phase that depends on how that
cache was packed. `motion.json`, written next to each sequence, is what carries
the claim.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import uvicorn

from kg.bus import EventBus
from kg.config import Config
from kg.export import write_graph_json
from kg.server import create_app
from kg.store import Store


@dataclass(frozen=True)
class Shot:
    """One delivered PNG: where it is, what it shows, and what it measures."""

    path: Path
    description: str
    coverage: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Served:
    """One app over one database, plus the handles to change it while it runs.

    `publish` hands an SSE event to the server's OWN event loop
    (`loop.call_soon_threadsafe`): the bus's queues are `asyncio.Queue`s
    belonging to that loop, and poking them from the renderer's thread is not
    thread-safe. `store` and `cfg` are safe to use directly — `kg.store.Store`
    serialises every call behind an RLock over a `check_same_thread=False`
    connection.
    """

    base_url: str
    store: Store
    cfg: Config
    publish: callable


# The one seed every round of this series has used. Same seed, same graph,
# same placement, and since the fifth round the same frames.
SEED = 20260814

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
    // fill-the-screen requirement is about. Both are reported: the seventh
    // brief asks for the model size AND the effective size, and since each
    // ladder variant is now laid out for itself the two no longer differ by a
    // shared factor.
    label_size_model: term ? Number(term.numericStyle('font-size')) : null,
    person_size_model: person ? Number(person.numericStyle('width')) : null,
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


def serve(store, cfg, bus=None) -> tuple[str, callable, callable]:
    """Start the real app on an ephemeral port in a background thread.

    Returns `(base_url, shutdown, publish)`. `publish` exists for the fifth
    round's `seq-new-person`, which has to make a person arrive on a graph
    that is already settled and on screen — the same SSE push the Core sends
    live, handed to the server's own event loop from this thread.
    """
    bus = EventBus() if bus is None else bus
    port = _free_port()
    loop_box: dict = {}

    class _CaptureLoop(uvicorn.Server):
        async def startup(self, sockets=None):
            loop_box["loop"] = asyncio.get_running_loop()
            await super().startup(sockets)

    server = _CaptureLoop(
        uvicorn.Config(create_app(store, cfg, bus), host="127.0.0.1", port=port, log_level="warning")
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

    def publish(event: dict) -> None:
        loop_box["loop"].call_soon_threadsafe(bus.publish, event)

    return f"http://127.0.0.1:{port}", shutdown, publish


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
    cfg = Config(data_dir=db_path.parent)
    base_url, shutdown, publish = serve(store, cfg)
    try:
        yield Served(base_url=base_url, store=store, cfg=cfg, publish=publish)
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
# The glide is slowed down for the four-frame STILL series only, and the
# filenames say so. At the wall's own 2.5s a screenshot round trip eats a
# fifth of the animation, and four frames would bunch at the end instead of
# spanning it. The frame SEQUENCES below do not need this — they run the glide
# at its real 2.5s on a controlled clock.
MIGRATION_SHOT_MS = 8000

# ---------------------------------------------------------------------------
# Frame sequences (Birk's fifth brief, 2026-08-15)
# ---------------------------------------------------------------------------

FPS = 25
FRAME_MS = 1000 / FPS
# How much settled picture follows the glide, so the sequence ends on the
# arrangement rather than on the last moving frame.
SEQUENCE_TAIL_MS = 500
# The person count seq-new-person joins. Birk asked for "a settled ~30-person
# graph"; the joiner is then person 31 of the same seed, which is exactly the
# 31st entry of `sim.seed_graph.person_specs`.
NEW_PERSON_BASE = 30

#: A frame clock the driver owns, so a sequence is a function of the seed and
#: nothing else.
#:
#: The problem it solves: a 1920x1080 screenshot costs 150-250ms, and the
#: glide being filmed is 2500ms long. Sampling a freely running animation at
#: 25 fps is therefore impossible — the frames would land wherever the round
#: trips allowed, differently on every run and differently on every machine.
#:
#: What it does: replaces `window.requestAnimationFrame` and
#: `performance.now()` with a queue and a counter the driver advances by
#: exactly 40ms per frame. The renderer is not patched and does not know:
#: Cytoscape resolves both dynamically off `window`/`performance` at call time
#: (verified against the vendored bundle — `function(e){u.requestAnimationFrame(e)}`
#: and `function(){return ye.now()}`), so installing these after the page has
#: loaded really does take over its animation loop. Every frame then lands on
#: the exact 40ms grid, and two runs agree on every node position in every
#: frame — see `_FRAME_STATE` for why that, and not the PNG bytes, is the
#: form the determinism claim takes.
#:
#: Rejected on measurement (2026-08-15): CDP `Emulation.setVirtualTimePolicy`
#: freezes `performance.now()` perfectly but suppresses requestAnimationFrame,
#: so the canvas stops being redrawn (3 distinct frames out of 20) and both
#: `Page.captureScreenshot` and `page.screenshot()` hang while it is paused.
#:
#: It is installed AFTER the page has settled and released afterwards, so the
#: load, the layout and the measurement all still happen on the real clock.
_FRAME_CLOCK = """
() => {
  if (window.__frameClock) return;
  const realRaf = window.requestAnimationFrame.bind(window);
  const realNow = performance.now.bind(performance);
  let controlled = false;
  let t = 0;
  let queue = [];
  window.requestAnimationFrame = (fn) => (controlled ? queue.push(fn) : realRaf(fn));
  window.cancelAnimationFrame = () => {};
  performance.now = () => (controlled ? t : realNow());
  window.__frameClock = {
    // Take over at the current real time, so nothing in the page sees the
    // clock jump — projection.js's camera loop keeps differencing timestamps
    // across the handover.
    take() { t = realNow(); controlled = true; },
    release() {
      controlled = false;
      const due = queue;
      queue = [];
      due.forEach((fn) => realRaf(fn));
    },
    tick(dt) {
      t += dt;
      const due = queue;
      queue = [];
      due.forEach((fn) => fn(t));
      return due.length;
    },
    now: () => (controlled ? t : realNow()),
  };
}
"""

# Watch for the moment the net actually starts MOVING. `layoutPending` covers
# the fcose run and the placement passes as well, and those are a freeze, not
# the animation being filmed. Re-registers unconditionally (unlike the still
# series' version, which could rely on the dial having been turned in the same
# evaluation) because a person arrives over SSE, some frames after the trigger.
_ARM_GLIDE = """
() => {
  window.__glide = null;
  const watch = () => {
    if (window.kgView.migrating) {
      window.__glide = performance.now();
      return;
    }
    requestAnimationFrame(watch);
  };
  requestAnimationFrame(watch);
}
"""

# One round trip instead of two while waiting for the glide to start.
_PUMP = "() => { window.__frameClock.tick(0); return window.__glide; }"
# A second pump at the SAME timestamp, after the one that advanced the clock.
# It costs nothing and removes an ordering question: Cytoscape steps its
# animations and redraws from the same callback list, and a frame that happened
# to draw before it stepped would show the previous position.
_TICK_HOLD = "() => window.__frameClock.tick(0)"

# What the frame SHOWS, in model terms: the elapsed time it stands for and the
# position of every node in it, keyed and sorted by id. Written next to the
# frames as `motion.json`, which is what makes "same seed, same sequence"
# checkable on the delivered files instead of only by re-rendering — and
# checkable at all, since the PNGs themselves are not byte-reproducible
# (Cytoscape rasterises a label into its texture cache at a sub-pixel phase
# that depends on cache packing; measured 2026-08-15, ~0.5% of pixels in a
# handful of captions, centroids within 0.2px, invisible).
_FRAME_STATE = """
(glideAt) => {
  const cy = window.kgView.cy;
  return {
    t: Math.round((performance.now() - glideAt) * 1000) / 1000,
    zoom: cy.zoom(),
    pan: cy.pan(),
    positions: cy
      .nodes()
      .map((n) => [n.id(), Math.round(n.position('x') * 1000) / 1000, Math.round(n.position('y') * 1000) / 1000])
      .sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0)),
  };
}
"""

# The pre-glide freeze can be long on the 50-person net (fcose at quality
# "proof" plus the placement rounds), and it is real CPU work, so the cap is
# generous. It exists only so a renderer that never migrates fails instead of
# hanging the run.
_GLIDE_PUMP_CAP = 20000


@dataclass(frozen=True)
class Sequence:
    """One rendered transition: a directory of frames, and what they mean."""

    directory: Path
    description: str
    frames: int
    fps: int
    glide_ms: int
    tail_ms: int
    compute_s: float
    mp4: Path | None = None
    coverage: dict = field(default_factory=dict)

    @property
    def duration_s(self) -> float:
        """Wall-clock the sequence represents, played at its own frame rate."""
        return self.frames / self.fps


def _capture_sequence(
    page,
    out_dir: Path,
    name: str,
    trigger,
    glide_ms: int = WALL_MIGRATION_MS,
    tail_ms: int = SEQUENCE_TAIL_MS,
    fps: int = FPS,
) -> Sequence:
    """Film one transition at `fps` and return where the frames landed.

    `trigger` is called once, with the frame clock already taken and the glide
    watcher armed; whatever it does — turn the dial, push a new person over
    SSE — must end in a graph change. The returned `Sequence` carries no
    description: only the caller knows what the transition was, and it only
    knows the numbers to say it with once the net has settled.
    """
    directory = out_dir / f"seq-{name}"
    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True)
    frame_ms = 1000 / fps

    page.evaluate(_FRAME_CLOCK)
    page.evaluate("() => window.__frameClock.take()")
    page.evaluate(_ARM_GLIDE)

    started = time.time()
    trigger()
    pumps = 0
    while page.evaluate(_PUMP) is None:
        pumps += 1
        if pumps > _GLIDE_PUMP_CAP:
            raise RuntimeError(f"{name}: the graph change never started a glide")
    # Real seconds, deliberately: this is the freeze a visitor sees between
    # the change and the movement, and it is CPU time on this machine — the
    # controlled clock says nothing about it.
    compute_s = time.time() - started
    glide_at = page.evaluate("window.__glide")

    frames = int(round((glide_ms + tail_ms) / frame_ms)) + 1
    motion = []
    for index in range(frames):
        if index:
            page.evaluate(f"() => window.__frameClock.tick({frame_ms})")
        page.evaluate(_TICK_HOLD)
        page.screenshot(path=str(directory / f"frame-{index + 1:04d}.png"))
        motion.append(page.evaluate(_FRAME_STATE, glide_at))

    # The grid is the claim this whole mechanism exists to make, so it is
    # measured rather than assumed.
    drift = motion[-1]["t"] - (frames - 1) * frame_ms
    if abs(drift) > 0.5:
        raise RuntimeError(f"{name}: frame clock drifted {drift:.2f}ms off the {fps} fps grid")

    page.evaluate("() => window.__frameClock.release()")
    page.wait_for_function("() => window.kgView.layoutPending === false", timeout=60000)
    page.wait_for_timeout(200)
    coverage = page.evaluate(MEASURE)

    (directory / "motion.json").write_text(
        json.dumps({"fps": fps, "glide_ms": glide_ms, "tail_ms": tail_ms, "frames": motion}),
        encoding="utf-8",
    )
    return Sequence(
        directory=directory,
        description="",
        frames=frames,
        fps=fps,
        glide_ms=glide_ms,
        tail_ms=tail_ms,
        compute_s=compute_s,
        coverage=coverage,
    )


def _set_dial(page, value: int) -> None:
    page.evaluate(f"() => window.kgView.setMinMentions({value})")
    page.wait_for_function("() => window.kgView.layoutPending === false", timeout=60000)


def _join_person(served: Served, spec) -> None:
    """Make one more person arrive on a graph that is already on the wall.

    Writes the interview through the Store exactly as `seed_graph` does, then
    pushes the complete graph over SSE — the same event the Core sends after
    every change (spec 11), on the server's own event loop.
    """
    from sim.seed_graph import write_person

    with served.store.transaction():
        write_person(served.store, served.cfg, spec)
    served.publish({"type": "graph", "graph": write_graph_json(served.store, served.cfg.graph_json_path)})


def _fill_shots(page, dbs: dict[int, Path], out_dir: Path, theme: str, scratch: Path) -> list[Shot]:
    """The same seeded graph at three sizes, each filling the canvas.

    `seed_graph` walks its rng once per person, so a 5-person seed is a strict
    prefix of the 50-person one: these really are the same graph at three
    points in its life, not three different graphs.
    """
    shots: list[Shot] = []
    for persons in sorted(dbs):
        with _served(dbs[persons], scratch / f"fill-{persons:02d}") as served:
            _open_projection(page, served.base_url, theme)
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


SEQUENCES = ("dial-1-to-2", "dial-2-to-1", "new-person")

# A working ffmpeg on this host, named by Birk in the fifth brief. It is the
# LAST candidate `find_ffmpeg` tries, after $KG_FFMPEG, $PATH and the
# imageio-ffmpeg package that ships it — an absolute path into one user's home
# directory is a fallback, never the interface.
FFMPEG_FALLBACK = Path(
    "/home/birk/.local/lib/python3.9/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2"
)


def find_ffmpeg(explicit: str | Path | None = None) -> Path | None:
    """The first usable encoder, or None — frames are the deliverable either way."""
    candidates = [explicit, os.environ.get("KG_FFMPEG"), shutil.which("ffmpeg")]
    try:
        import imageio_ffmpeg

        candidates.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass
    candidates.append(FFMPEG_FALLBACK)
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return Path(candidate)
    return None


def encode_sequence(sequence: Sequence, ffmpeg: Path) -> Path:
    """H.264 / yuv420p at the sequence's own frame rate, so it plays inline.

    yuv420p and `+faststart` are not decoration: they are what makes the file
    play in Telegram and in QuickTime rather than only in VLC.
    """
    target = sequence.directory.with_suffix(".mp4")
    subprocess.run(
        [
            str(ffmpeg),
            "-y",
            "-loglevel", "error",
            "-framerate", str(sequence.fps),
            "-i", str(sequence.directory / "frame-%04d.png"),
            "-c:v", "libx264",
            "-preset", "slow",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(target),
        ],
        check=True,
    )
    return target


def _dial_sequence(page, served, out_dir, theme, frm, to, fps, glide_ms, tail_ms) -> Sequence:
    from dataclasses import replace

    _open_projection(page, served.base_url, theme, migration_ms=glide_ms)
    if frm != 1:
        # Getting TO the starting state is setup, not the transition being
        # filmed, so it runs before the clock is taken and is not captured.
        _set_dial(page, frm)
    before = page.evaluate(MEASURE)
    sequence = _capture_sequence(
        page,
        out_dir,
        f"dial-{frm}-to-{to}",
        trigger=lambda: page.evaluate(f"() => window.kgView.setMinMentions({to})"),
        fps=fps,
        glide_ms=glide_ms,
        tail_ms=tail_ms,
    )
    after = sequence.coverage
    moved = abs(before["term_nodes"] - after["term_nodes"])
    verb = "vanish and the survivors migrate outward into the freed space" if to > frm else (
        "come back, and everyone already on the wall makes room for them"
    )
    return replace(
        sequence,
        description=(
            f"The density dial moving min_mentions {frm} -> {to} on the seeded "
            f"{before['person_nodes']}-person net: {before['term_nodes']} term nodes before, "
            f"{after['term_nodes']} after — {moved} {verb}. Every node moves, none jumps."
        ),
    )


def _new_person_sequence(page, served, out_dir, theme, spec, fps, glide_ms, tail_ms) -> Sequence:
    from dataclasses import replace

    _open_projection(page, served.base_url, theme, migration_ms=glide_ms)
    before = page.evaluate(MEASURE)
    sequence = _capture_sequence(
        page,
        out_dir,
        "new-person",
        trigger=lambda: _join_person(served, spec),
        fps=fps,
        glide_ms=glide_ms,
        tail_ms=tail_ms,
    )
    after = sequence.coverage
    return replace(
        sequence,
        description=(
            f"One new person joining a settled {before['person_nodes']}-person net, with the "
            f"{len(spec.terms)} terms of their interview: {before['nodes']} nodes before, "
            f"{after['nodes']} after. The graph arrives over SSE exactly as it does live, and "
            "the whole net re-distributes to take them in. This is the transition the audience "
            "sees most often."
        ),
    )


def render_sequences(
    dbs: dict[int, Path],
    out_dir: Path,
    theme: str = THEME,
    names: tuple[str, ...] = SEQUENCES,
    fps: int = FPS,
    ffmpeg: str | Path | None = None,
    encode: bool = True,
    glide_ms: int = WALL_MIGRATION_MS,
    tail_ms: int = SEQUENCE_TAIL_MS,
    seed: int = SEED,
    new_person_base: int = NEW_PERSON_BASE,
) -> list[Sequence]:
    """Film each requested transition at `fps` into its own subdirectory.

    Every sequence runs the wall's OWN glide length — the point of the round is
    for Birk to judge the real speed — and gets a throwaway copy of its
    database, for the same reason the still series does: a series must be
    reproducible from the seed alone.
    """
    from playwright.sync_api import sync_playwright

    from sim.seed_graph import person_specs

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    full = dbs[max(dbs)]
    encoder = find_ffmpeg(ffmpeg) if encode else None

    sequences: list[Sequence] = []
    with tempfile.TemporaryDirectory(prefix="prerender-seq-") as tmp, sync_playwright() as playwright:
        scratch = Path(tmp)
        browser = _launch_chromium(playwright)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        for name in names:
            if name == "new-person":
                base = dbs.get(new_person_base)
                if base is None:
                    raise KeyError(
                        f"seq-new-person needs a {new_person_base}-person seeded db in `dbs`"
                    )
                # The joiner is the NEXT person of the same seed, so the net it
                # joins and the interview that joins it come from one graph.
                spec = person_specs(new_person_base + 1, seed)[new_person_base]
                with _served(base, scratch / name) as served:
                    sequences.append(
                        _new_person_sequence(page, served, out_dir, theme, spec, fps, glide_ms, tail_ms)
                    )
            else:
                frm, to = (int(part) for part in name.replace("dial-", "").split("-to-"))
                with _served(full, scratch / name) as served:
                    sequences.append(
                        _dial_sequence(page, served, out_dir, theme, frm, to, fps, glide_ms, tail_ms)
                    )
        browser.close()

    if encoder is None:
        return sequences

    from dataclasses import replace

    return [replace(s, mp4=encode_sequence(s, encoder)) for s in sequences]


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
            with _served(full, scratch / "density") as served:
                shots.extend(_density_shots(page, served.base_url, out_dir, theme, min_mentions_values))
        if include_migration_series:
            with _served(full, scratch / "migration") as served:
                shots.extend(_migration_shots(page, served.base_url, out_dir, theme, migration_ms))
        if themes:
            # ONE COPY PER VARIANT, so each one lays the net out for ITSELF.
            #
            # Up to the sixth round the whole ladder shared a single served
            # copy: the first theme laid the net out, persisted it, and the
            # rest restored that placement — "same placement, only the type
            # size differs". Birk's seventh brief retracts that instruction as
            # self-contradictory, and the sixth round's own output is the
            # proof: at 32px and 44px the labels overlapped each other AND the
            # 63px person discs overlapped, because the arrangement they were
            # dropped into had been computed for 22px labels on 30px discs.
            #
            # A variant's type and disc sizes are theme CSS variables, and both
            # the layout (fcose's nodeDimensionsIncludeLabels) and the
            # placement passes measure nodes through them — so a fresh copy is
            # all it takes for each variant to be laid out at its own extents.
            # The price is the one the old comment named: a bigger net is
            # fitted from further away, so the type does NOT reach the wall
            # proportionally larger. That is the real trade and it is what the
            # per-variant numbers in the report now show.
            for extra in themes:
                stem, description = SERIES[extra]
                with _served(full, scratch / f"theme-{extra}") as served:
                    _open_projection(page, served.base_url, extra)
                    target = out_dir / f"{stem}.png"
                    page.screenshot(path=str(target))
                    shots.append(Shot(target, description, page.evaluate(MEASURE)))
        if include_camera_views:
            with _served(full, scratch / "camera") as served:
                _open_projection(page, served.base_url, camera_theme)
                for stem, description, setup in CAMERA_VIEWS:
                    page.evaluate(setup)
                    page.wait_for_timeout(200)
                    target = out_dir / f"{stem}.png"
                    page.screenshot(path=str(target))
                    shots.append(
                        Shot(target, f"{description} [theme {camera_theme}]", page.evaluate(MEASURE))
                    )
        if include_testpattern:
            with _served(full, scratch / "testpattern") as served:
                stem, description = TESTPATTERN
                page.goto(f"{served.base_url}/testpattern")
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


def _print_shot(shot: Shot) -> None:
    print(shot.path.resolve())
    print(f"    {shot.description}")
    if not shot.coverage:
        return
    print(
        "    node cloud: {width_fraction:.0%} of canvas width, "
        "{height_fraction:.0%} of height (with labels "
        "{width_fraction_with_labels:.0%} x {height_fraction_with_labels:.0%}, "
        "{area_fraction_with_labels:.0%} of the canvas area); "
        "zoom {zoom:.3f}; {nodes_in_frame:.0%} of {nodes} nodes in frame".format(**shot.coverage)
    )
    print(
        "    on the wall: {term_nodes} term nodes, {person_nodes} persons, "
        "{edges} edges; labels {label_px_on_wall:.0f}px ({label_size_model:.0f}px model type), "
        "discs {person_px_on_wall:.0f}px ({person_size_model:.0f}px model)".format(**shot.coverage)
    )
    stats = shot.coverage.get("label_overlap_stats")
    if stats:
        before, after = stats["before"], stats["after"]
        # All three counts, before and after the declutter pass (Birk's
        # seventh brief). The disc-on-disc pair count cannot move across that
        # pass — declutter only ever changes label offsets — so it is printed
        # once, as the placement's own number.
        print(
            f"    labels: {before['labelPairs']} overlapping pairs before -> "
            f"{after['labelPairs']} after the declutter pass; "
            f"{before['labelsOnPersons']} on person discs before -> "
            f"{after['labelsOnPersons']} after; "
            f"{after['personPairs']} discs on discs (placement only, declutter cannot move a disc)"
        )


def _print_sequence(sequence: Sequence) -> None:
    print(sequence.directory.resolve())
    print(f"    {sequence.description}")
    print(
        f"    {sequence.frames} frames at {sequence.fps} fps = "
        f"{sequence.duration_s:.2f}s of wall-clock: a {sequence.glide_ms / 1000:.1f}s glide "
        f"(the wall's own default, not slowed) plus a {sequence.tail_ms / 1000:.1f}s settled tail. "
        f"frame-0001.png is the first moving frame."
    )
    print(
        f"    the fcose run and the placement passes freeze the picture for "
        f"{sequence.compute_s:.1f}s before the glide starts; that freeze is NOT in the frames."
    )
    if sequence.mp4:
        print(f"    {sequence.mp4.resolve()}  (H.264 / yuv420p / {sequence.fps} fps)")
    else:
        print("    no encoder found — frames only")
    print(f"    {(sequence.directory / 'motion.json').resolve()}  (per frame: t, zoom, pan, every node position)")
    if sequence.coverage:
        _print_shot(Shot(sequence.directory / f"frame-{sequence.frames:04d}.png", "the settled arrangement it lands on:", sequence.coverage))


def main() -> None:
    parser = argparse.ArgumentParser(prog="sim.prerender")
    parser.add_argument("--state", default="out/prerender7-state")
    parser.add_argument("--out", default="out/prerender7")
    parser.add_argument("--seed", type=int, default=SEED)
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
    parser.add_argument(
        "--sequences",
        nargs="+",
        default=list(SEQUENCES),
        choices=sorted(SEQUENCES),
        help="which transitions to film into seq-<name>/ at --fps, over the "
        "wall's own 2.5s glide (default: all three)",
    )
    parser.add_argument("--no-sequences", action="store_true", help="skip the frame sequences")
    parser.add_argument("--fps", type=int, default=FPS, help=f"sequence frame rate (default {FPS})")
    parser.add_argument(
        "--glide-ms",
        type=int,
        default=WALL_MIGRATION_MS,
        help=f"glide length to film (default {WALL_MIGRATION_MS}, the wall's own). "
        "A sequence is captured on a controlled clock, so this does not need "
        "slowing down to be sampled — change it only to judge a different speed.",
    )
    parser.add_argument("--stills", action="store_true", help="also render the fourth round's PNG series")
    parser.add_argument(
        "--no-migration-stills",
        action="store_true",
        help="skip the four-frame slowed migration series inside --stills. The "
        "frame sequences replaced it as the evidence for motion (fifth round), "
        "so a stills-only round like the sixth does not need it.",
    )
    parser.add_argument(
        "--no-fill-stills",
        action="store_true",
        help="skip the fill-the-screen series inside --stills",
    )
    parser.add_argument(
        "--no-density-stills",
        action="store_true",
        help="skip the density-dial series inside --stills. With "
        "--no-fill-stills and --no-migration-stills this leaves the --themes "
        "ladder alone, which is the seventh round's whole delivery.",
    )
    parser.add_argument("--ffmpeg", default=None, help="encoder to use; default: $KG_FFMPEG, PATH, imageio-ffmpeg")
    parser.add_argument("--no-mp4", action="store_true", help="deliver frames only, do not encode")
    args = parser.parse_args()

    sequences_wanted = () if args.no_sequences else tuple(args.sequences)
    sizes = set(args.sizes)
    if sequences_wanted:
        # seq-new-person joins a settled NEW_PERSON_BASE-person net; the dial
        # sequences run against the largest, which is the hard case.
        sizes |= {NEW_PERSON_BASE}
    dbs = seed_sizes(Path(args.state), tuple(sorted(sizes)), args.seed, reseed=args.reseed)

    if args.stills:
        for shot in render_series(
            {size: dbs[size] for size in sorted(args.sizes)},
            Path(args.out),
            themes=tuple(args.themes),
            include_testpattern=args.testpattern,
            include_camera_views=args.camera_views,
            include_fill_series=not args.no_fill_stills,
            include_density_series=not args.no_density_stills,
            include_migration_series=not args.no_migration_stills,
            migration_ms=args.migration_ms,
        ):
            _print_shot(shot)

    if sequences_wanted:
        for sequence in render_sequences(
            dbs,
            Path(args.out),
            names=sequences_wanted,
            fps=args.fps,
            glide_ms=args.glide_ms,
            ffmpeg=args.ffmpeg,
            encode=not args.no_mp4,
            seed=args.seed,
        ):
            _print_sequence(sequence)


if __name__ == "__main__":
    main()
