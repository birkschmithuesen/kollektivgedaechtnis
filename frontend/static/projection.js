import { newNodeIds, toCytoscape, visibleGraph } from './graph-model.js';
import { Camera } from './camera.js';

function cssVar(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function style() {
  return [
    {
      selector: 'node.person',
      style: {
        shape: 'ellipse',
        width: cssVar('--person-size', '96'),
        height: cssVar('--person-size', '96'),
        'background-color': cssVar('--person-fill', '#222'),
        'background-image': (ele) => ele.data('portrait') || 'none',
        'background-fit': 'cover',
        'border-width': cssVar('--ring-width', '5'),
        'border-color': cssVar('--ring-color', '#C9A227'),
        label: '',
      },
    },
    {
      selector: 'node.term',
      style: {
        shape: 'ellipse',
        width: cssVar('--term-dot', '14'),
        height: cssVar('--term-dot', '14'),
        'background-color': cssVar('--term-dot-color', '#EDE7D8'),
        label: 'data(label)',
        color: cssVar('--label-color', '#F5F1E6'),
        'font-family': cssVar('--label-font', 'Georgia, serif'),
        'font-size': cssVar('--label-size', '22'),
        'text-valign': 'bottom',
        // Both scale with the type: a wrap width and a gap tuned for 22px
        // labels turn 44px ones into a stack of short lines under the dot.
        'text-margin-y': cssVar('--label-margin-y', '6'),
        'text-wrap': 'wrap',
        'text-max-width': cssVar('--label-max-width', '220px'),
        'text-outline-width': cssVar('--label-outline-width', '3'),
        'text-outline-color': cssVar('--label-outline-color', '#101014'),
      },
    },
    {
      selector: 'edge.link',
      style: {
        width: cssVar('--edge-width', '2'),
        'line-color': cssVar('--edge-color', '#8A8578'),
        'curve-style': 'straight',
        opacity: cssVar('--edge-opacity', '0.75'),
      },
    },
  ];
}

export const LAYOUT = {
  name: 'cose',
  randomize: false,
  animate: true,
  animationDuration: 1200,
  fit: false,
  padding: 60,
  nodeRepulsion: 12000,
  idealEdgeLength: 160,
  nodeDimensionsIncludeLabels: true,
};

// Nodes are always visited in this order, never Cytoscape's own collection
// order (which is insertion order and so depends on network/API timing) —
// otherwise the same seed could settle differently between two runs.
function byId(a, b) {
  const idA = a.id();
  const idB = b.id();
  if (idA < idB) return -1;
  if (idA > idB) return 1;
  return 0;
}

function boxesOverlap(a, b) {
  return a.x1 < b.x2 && a.x2 > b.x1 && a.y1 < b.y2 && a.y2 > b.y1;
}

// The minimum-translation vector to move box `a` clear of box `b`, along
// whichever axis needs the smaller push. Ties (concentric boxes) resolve
// toward positive x/y, deterministically, rather than toward whatever
// floating-point noise happens to fall out of the centre comparison.
function overlapVector(a, b) {
  const ox = Math.min(a.x2, b.x2) - Math.max(a.x1, b.x1);
  const oy = Math.min(a.y2, b.y2) - Math.max(a.y1, b.y1);
  if (ox <= 0 || oy <= 0) return null;
  const ac = { x: (a.x1 + a.x2) / 2, y: (a.y1 + a.y2) / 2 };
  const bc = { x: (b.x1 + b.x2) / 2, y: (b.y1 + b.y2) / 2 };
  if (ox < oy) return { x: ac.x >= bc.x ? ox : -ox, y: 0 };
  return { x: 0, y: ac.y >= bc.y ? oy : -oy };
}

/** Count overlapping term-label boxes, and label-on-person collisions.
 *
 * `includeNodes: false` on a boundingBox call isolates the LABEL's own box
 * from its dot — Cytoscape's real measured text extent (font metrics, wrap
 * width), not a guess — so this is exactly what a viewer would see collide.
 * Exported so the pre-render CLI and the dev console can both ask "how bad
 * is it right now" without reaching into private state.
 */
export function countLabelOverlaps(cy) {
  const terms = cy.nodes('.term').sort(byId);
  const boxes = terms.map((node) => node.boundingBox({ includeLabels: true, includeNodes: false }));
  let labelPairs = 0;
  for (let i = 0; i < boxes.length; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      if (boxesOverlap(boxes[i], boxes[j])) labelPairs += 1;
    }
  }

  const personBoxes = cy.nodes('.person').map((node) => node.boundingBox({ includeNodes: true, includeLabels: false }));
  let labelsOnPersons = 0;
  boxes.forEach((box) => {
    personBoxes.forEach((personBox) => {
      if (boxesOverlap(box, personBox)) labelsOnPersons += 1;
    });
  });

  return { labelPairs, labelsOnPersons };
}

// cose's own nodeDimensionsIncludeLabels sizes each node's repulsion off its
// OWN measured extent, but never learns that a neighbour's label is wide too
// — measured 2026-08-14 on the seeded 50-person / 75-term graph at theme b,
// cose alone settles at 43 overlapping label-box pairs and 30 labels sitting
// on person discs. This pass pushes the MEASURED dot+label boxes
// (Cytoscape's own boundingBox, not a guessed constant) apart directly, in
// node-position space, so the layout finally "knows" a term node is its dot
// plus its caption.
//
// It is a relaxation with a cap, NOT a solver: on that graph it does not
// reach a clean state within the cap, and raising the cap to 400 only takes
// one round's result from 25 pairs to 17 for ~5x the time. Getting to zero
// is the job of the rounds in settlePlacement() and the declutter pass
// afterwards, both of which are far cheaper per pair removed.
const SEPARATION_ITERATIONS = 60;
// Resolve half of every overlap per pass, not all of it: a node colliding
// with several neighbours at once would otherwise overshoot on each of them
// simultaneously.
const SEPARATION_STEP = 0.5;

function fullBox(node) {
  return node.boundingBox({ includeLabels: true });
}

export function separateOverlappingNodes(cy) {
  const nodes = cy.nodes().sort(byId);
  if (nodes.length < 2) return;
  for (let iteration = 0; iteration < SEPARATION_ITERATIONS; iteration += 1) {
    const boxes = nodes.map((node) => fullBox(node));
    const push = nodes.map(() => ({ x: 0, y: 0 }));
    let anyOverlap = false;
    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        const v = overlapVector(boxes[i], boxes[j]);
        if (!v) continue;
        anyOverlap = true;
        push[i].x += v.x * SEPARATION_STEP;
        push[i].y += v.y * SEPARATION_STEP;
        push[j].x -= v.x * SEPARATION_STEP;
        push[j].y -= v.y * SEPARATION_STEP;
      }
    }
    if (!anyOverlap) break;
    nodes.forEach((node, index) => {
      const at = node.position();
      node.position({ x: at.x + push[index].x, y: at.y + push[index].y });
    });
  }
}

// This is a relaxation, and on a crowded net it needs room to run: measured
// 2026-08-14 from the settled placement of the seeded 50-person / 75-term
// graph at theme b, a 30-iteration cap stalls at 18 overlapping label pairs
// while 300 clears the same state to zero (~1s). The cap is the binding
// constraint here, not the step size and not the displacement budget below —
// no label ever reaches that budget on this net.
const DECLUTTER_ITERATIONS = 300;
const DECLUTTER_STEP = 0.5;
// A label may wander further than this from its dot's default position
// before it stops reading as that dot's caption. Scaled off the label's
// OWN measured box height, not a constant, because the theme series ranges
// from 22px to 44px type — a fixed pixel cap tuned for one theme would be
// meaningless (too tight or too loose) on the others.
const MAX_LABEL_DISPLACEMENT_LINES = 2;
// How many label-on-label pairs one label-on-portrait collision is worth when
// scoring a candidate state (rule (c) over rule (b), see below).
const PERSON_COLLISION_WEIGHT = 3;

/** Nudge label OFFSETS (never node positions) until no two term-label boxes
 * overlap, and no term-label box overlaps a person disc.
 *
 * Idempotent: it starts from whatever text-margin-x/y a node already
 * carries (0 / the theme's --label-margin-y default if untouched, or a
 * previous call's result), so calling it again on an already-clear net
 * measures zero overlaps on the first iteration and changes nothing.
 * Person discs are fixed obstacles here — only the label moves.
 */
export function declutterLabels(cy) {
  const terms = cy.nodes('.term').sort(byId);
  if (terms.length === 0) return;
  const persons = cy.nodes('.person').toArray();
  const baseMarginY = Number(cssVar('--label-margin-y', '6'));

  const state = terms.map((node) => ({
    node,
    x: node.numericStyle('text-margin-x'),
    y: node.numericStyle('text-margin-y'),
    // A label's own box height barely changes with its margin (the margin
    // shifts it, the wrap width sizes it), so its displacement budget is
    // measured once, up front, from that near-constant height.
    cap: node.boundingBox({ includeLabels: true, includeNodes: false }).h * MAX_LABEL_DISPLACEMENT_LINES,
  }));

  const applyState = () => state.forEach(({ node, x, y }) => node.style({ 'text-margin-x': x, 'text-margin-y': y }));

  // Relaxation this simple is not monotone: a label pushed clear of a person
  // disc at full strength lands on two other labels, and on a crowded net a
  // late iteration can end up worse than an early one (measured 2026-08-14:
  // 48 pairs in, 70 pairs out, on the seeded graph before this guard). So
  // every iteration is scored and the best one is what gets applied at the
  // end — including iteration 0, the untouched input, which makes the pass
  // incapable of handing back something worse than it was given.
  let best = null;
  const remember = (score) => {
    if (best && score >= best.score) return;
    best = { score, offsets: state.map(({ x, y }) => ({ x, y })) };
  };

  for (let iteration = 0; iteration < DECLUTTER_ITERATIONS; iteration += 1) {
    applyState();
    const boxes = state.map(({ node }) => node.boundingBox({ includeLabels: true, includeNodes: false }));
    const personBoxes = persons.map((p) => p.boundingBox({ includeNodes: true, includeLabels: false }));

    const push = state.map(() => ({ x: 0, y: 0 }));
    let anyOverlap = false;
    let labelPairs = 0;
    let labelsOnPersons = 0;

    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        const v = overlapVector(boxes[i], boxes[j]);
        if (!v) continue;
        anyOverlap = true;
        labelPairs += 1;
        push[i].x += v.x * DECLUTTER_STEP;
        push[i].y += v.y * DECLUTTER_STEP;
        push[j].x -= v.x * DECLUTTER_STEP;
        push[j].y -= v.y * DECLUTTER_STEP;
      }
      // A person disc never moves, so a label overlapping one is resolved
      // at full strength rather than split — the hard "may not overlap"
      // rule (c) should win out over the softer label-label spacing (b).
      personBoxes.forEach((personBox) => {
        const v = overlapVector(boxes[i], personBox);
        if (!v) return;
        anyOverlap = true;
        labelsOnPersons += 1;
        push[i].x += v.x;
        push[i].y += v.y;
      });
    }

    // Rule (c) outranks rule (b): a label on a portrait disc is worse than a
    // label on a label, because the disc becomes a real photograph later. A
    // state that clears one person collision is therefore preferred even if
    // it costs a few label-on-label pairs.
    remember(labelPairs + PERSON_COLLISION_WEIGHT * labelsOnPersons);
    if (!anyOverlap) break;

    state.forEach((entry, index) => {
      entry.x += push[index].x;
      entry.y += push[index].y;
      const dx = entry.x;
      const dy = entry.y - baseMarginY;
      const dist = Math.hypot(dx, dy);
      if (dist > entry.cap && dist > 0) {
        const scale = entry.cap / dist;
        entry.x = dx * scale;
        entry.y = baseMarginY + dy * scale;
      }
    });
  }

  if (best) {
    state.forEach((entry, index) => {
      entry.x = best.offsets[index].x;
      entry.y = best.offsets[index].y;
    });
  }
  applyState();
}

/** Clear every per-node label offset back to the theme default, undoing
 * declutterLabels(). Removing the style bypass (rather than setting it to
 * a computed default) means a later theme swap still takes effect through
 * the normal stylesheet cascade.
 */
export function resetLabelOffsets(cy) {
  cy.nodes('.term').forEach((node) => node.removeStyle('text-margin-x text-margin-y'));
}

// The projection surface is 16:9. A force layout is isotropic, so its settled
// cloud is round: on 1920x1080 that leaves the sides empty (measured
// 2026-08-14: 30% of the canvas width) and the camera cannot recover it —
// zooming in further only clips the top and bottom.
const CANVAS_ASPECT = 16 / 9;
// A label keeps its own width when the nodes around it move apart, so one
// correction always undershoots the target. Iterate to it instead.
const FRAME_STEPS = 6;
const FRAME_TOLERANCE = 0.01;
// The stretch is the part of the framing that does distort, so it is bounded:
// beyond this the net is a smear, and something about the layout is wrong.
const MAX_STRETCH = 3;

/** Shape a from-scratch placement like the canvas it is projected onto.
 *
 * Deterministic: a pure function of the settled positions, so the same seed
 * still yields the same picture. Exported so it can be exercised on its own.
 */
export function frameToAspect(cy, target = CANVAS_ASPECT, { rotate = true } = {}) {
  const nodes = cy.nodes();
  if (nodes.length < 2) return;
  let box = nodes.boundingBox({ includeLabels: true });
  if (!(box.w > 0) || !(box.h > 0)) return;

  // Cytoscape's cose measures repulsion with each node's width and height
  // swapped, so a net of wide labels settles PORTRAIT — exactly the wrong way
  // round for this wall. A quarter turn costs no distortion at all and does
  // most of the work; only what remains is stretched.
  if (rotate && (box.w < box.h) === (target > 1)) {
    const centre = { x: (box.x1 + box.x2) / 2, y: (box.y1 + box.y2) / 2 };
    nodes.positions((node) => {
      const at = node.position();
      return { x: centre.x + (at.y - centre.y), y: centre.y - (at.x - centre.x) };
    });
    box = nodes.boundingBox({ includeLabels: true });
  }

  let stretched = 1;
  for (let step = 0; step < FRAME_STEPS; step += 1) {
    const aspect = box.w / box.h;
    // Only ever pull the short axis out to the target. Squeezing the long one
    // would push labels together, which is what this whole series is about.
    const scale = aspect < target ? { x: target / aspect, y: 1 } : { x: 1, y: aspect / target };
    if (Math.max(scale.x, scale.y) < 1 + FRAME_TOLERANCE) return;
    const capped = Math.min(Math.max(scale.x, scale.y), MAX_STRETCH / stretched);
    if (capped <= 1) return;
    stretched *= capped;
    const factor = { x: scale.x > 1 ? capped : 1, y: scale.y > 1 ? capped : 1 };
    const centre = { x: (box.x1 + box.x2) / 2, y: (box.y1 + box.y2) / 2 };
    nodes.positions((node) => {
      const at = node.position();
      return {
        x: centre.x + (at.x - centre.x) * factor.x,
        y: centre.y + (at.y - centre.y) * factor.y,
      };
    });
    box = nodes.boundingBox({ includeLabels: true });
  }
}

// Separation and framing pull against each other, so one round of each
// undershoots: separating pushes boxes apart along whichever axis is
// cheapest, which pulls the cloud back towards square, and re-stretching it
// to 16:9 opens gaps that let the next separation round resolve collisions
// it previously had no room for. It takes several rounds to break through —
// measured 2026-08-14 on the live projection page at theme b with the seeded
// 50-person / 75-term graph, overlapping label pairs by round: 24, 24, 24,
// 24, 5, 4, 2, then flat. Stopping at four (which looked like plenty on the
// offline runs) leaves 18 pairs on the wall; running on to convergence
// leaves 2.
//
// So this is a cap, not a target: the loop below stops as soon as the rounds
// stop paying, and each round costs real time (~1-3s on that graph, all of
// it inside boundingBox). It runs once, on a from-scratch placement only.
const PLACEMENT_ROUNDS = 16;
// Rounds that buy nothing before giving up. One flat round is not enough
// evidence — the measurement above sat at 24 for four rounds before it broke
// through to 5.
const PLACEMENT_PATIENCE = 5;

/** Shape a from-scratch placement for this wall: 16:9, and with the layout
 * finally knowing that a term node is its dot PLUS its label box.
 *
 * ORDER MATTERS, and it is the opposite of the obvious one. `frameToAspect`
 * may turn the whole net a quarter turn, and a rotation moves the dots while
 * every label stays horizontal — so a net separated first and rotated after
 * comes out overlapping again (measured on the same graph: separation took
 * 43 pairs down to 20, and the rotation put it back to 48). Rotate FIRST, in
 * the orientation the wall will actually show, and only then separate.
 */
export function settlePlacement(cy) {
  frameToAspect(cy);
  const nodes = cy.nodes().sort(byId);
  const snapshot = () => nodes.map((node) => ({ ...node.position() }));
  let best = { score: Infinity, positions: null };
  let flatRounds = 0;

  for (let round = 0; round < PLACEMENT_ROUNDS; round += 1) {
    separateOverlappingNodes(cy);
    // No rotation from here on: the orientation is settled above, and a
    // separation round that happens to leave the cloud taller than wide must
    // not be allowed to spin the whole picture a quarter turn.
    frameToAspect(cy, CANVAS_ASPECT, { rotate: false });
    const { labelPairs, labelsOnPersons } = countLabelOverlaps(cy);
    const score = labelPairs + PERSON_COLLISION_WEIGHT * labelsOnPersons;
    if (score < best.score) {
      best = { score, positions: snapshot() };
      flatRounds = 0;
    } else if ((flatRounds += 1) >= PLACEMENT_PATIENCE) {
      break;
    }
    if (labelPairs === 0 && labelsOnPersons === 0) break;
  }

  // Pushing node A clear of B can push it into C, so the rounds do not
  // descend cleanly — measured 2026-08-14 on the seeded graph they wander
  // (41, 32, 32, 28, 30, 33, 26, 27, ...). Ending on whatever the last round
  // happened to produce would throw away a better picture the loop had
  // already found and paid for, so the best one is what gets kept.
  if (best.positions) {
    nodes.forEach((node, index) => node.position({ ...best.positions[index] }));
  }
}

// Reset then declutter, and measure both sides of it. `before` is the
// layout's own settled state (positions final, labels still at the theme
// default); `after` is what a viewer actually sees. Run on every render —
// including a min_mentions change, which adds no new nodes and so runs no
// layout — because raising the dial only ever removes labels and the pass
// should take that free win immediately, not carry over stale offsets
// sized for a denser picture.
function settleLabels(cy) {
  resetLabelOffsets(cy);
  const before = countLabelOverlaps(cy);
  declutterLabels(cy);
  const after = countLabelOverlaps(cy);
  return { before, after };
}

export function createGraphView(container, { onPositions = () => {} } = {}) {
  const cy = cytoscape({ container, style: style(), wheelSensitivity: 0.2 });
  const camera = new Camera(cy);
  let lastGraph = { nodes: [], edges: [], min_mentions: 1 };
  let minMentions = 1;
  // True while an animated layout is running. Tests and the pre-render wait on
  // this instead of guessing a timeout; positions land only at `layoutstop`.
  let layoutPending = false;
  const emptyStats = { labelPairs: 0, labelsOnPersons: 0 };
  let labelOverlapStats = { before: emptyStats, after: emptyStats };
  // Where each node was last seen, by id. The dial hides term nodes by
  // REMOVING them from cy, so turning it back down re-adds them — and until
  // the server has round-tripped this session's positions back into
  // `lastGraph`, those nodes carry x/y null and would read as brand new. Left
  // to that, lowering the dial would re-run a layout and visibly reshuffle
  // the returning half of the net (spec 11). They go back exactly where they
  // were instead.
  const lastSeen = new Map();

  function render() {
    const view = visibleGraph(lastGraph, minMentions);
    const wanted = new Set(view.nodes.map((n) => n.id).concat(view.edges.map((e) => e.id)));
    const present = cy.elements().map((el) => el.id());

    cy.nodes().forEach((n) => lastSeen.set(n.id(), { ...n.position() }));

    // Remove what dropped out of the view. Positions of the rest are untouched.
    cy.elements()
      .filter((el) => !wanted.has(el.id()))
      .remove();

    // A node that arrives with a persisted position is NOT "fresh": it is
    // already placed and must be locked like any long-standing node (spec 11).
    const placed = new Set(
      view.nodes
        .filter((n) => n.x !== null && n.x !== undefined && n.y !== null && n.y !== undefined)
        .map((n) => n.id),
    );
    const returning = newNodeIds(present, view).filter((id) => !placed.has(id) && lastSeen.has(id));
    const fresh = newNodeIds(present, view).filter((id) => !placed.has(id) && !lastSeen.has(id));
    const toAdd = toCytoscape(view).filter((el) => cy.$id(el.data.id).length === 0);
    if (toAdd.length) cy.add(toAdd);
    returning.forEach((id) => cy.$id(id).position({ ...lastSeen.get(id) }));

    if (fresh.length) {
      // Seed each new node next to a neighbour it already has, so the layout
      // starts from a sensible place instead of the origin. The offset is
      // derived from the index (golden angle), not random: two pre-render runs
      // over the same graph must produce the same picture.
      fresh.forEach((id, index) => {
        const node = cy.$id(id);
        // `fresh` already excludes every id in `placed` (an explicit x/y
        // null-check against the graph data, not a truthy check on the
        // rendered position), so every node reached here is genuinely
        // unseeded and must always be positioned. A `position('x') ||
        // position('y')` guard here would be confused by a node legitimately
        // seeded to exactly (0, 0) and skip it.
        const anchor = node.neighborhood('node').filter((n) => !fresh.includes(n.id()))[0];
        const base = anchor ? anchor.position() : { x: 0, y: 0 };
        const angle = index * 2.39996;
        node.position({ x: base.x + Math.cos(angle) * 140, y: base.y + Math.sin(angle) * 140 });
      });
      // Existing nodes are locked: the net must never re-shuffle (spec 11).
      const existing = cy.nodes().filter((n) => !fresh.includes(n.id()));
      existing.lock();
      // Nothing is placed yet, so this layout owns the whole picture and may
      // shape it to the canvas. Every later layout only adds to a net that is
      // already on the wall, and must leave that net exactly where it is.
      const fromScratch = existing.length === 0;
      const layout = cy.layout(LAYOUT);
      layoutPending = true;
      layout.one('layoutstop', () => {
        existing.unlock();
        // The layout only ever separated dots; this shapes the placement to
        // the wall and teaches it about the label boxes it settled without.
        if (fromScratch) settlePlacement(cy);
        labelOverlapStats = settleLabels(cy);
        const positions = {};
        cy.nodes().forEach((n) => {
          positions[n.id()] = { x: n.position('x'), y: n.position('y') };
        });
        onPositions(positions);
        camera.onGraphChanged();
        layoutPending = false;
      });
      layout.run();
    } else {
      labelOverlapStats = settleLabels(cy);
      camera.onGraphChanged();
    }
  }

  let last = performance.now();
  function tick(now) {
    camera.step((now - last) / 1000);
    last = now;
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);

  return {
    cy,
    camera,
    get layoutPending() {
      return layoutPending;
    },
    get labelOverlapStats() {
      return labelOverlapStats;
    },
    update(graph, value) {
      lastGraph = graph;
      if (value !== undefined) minMentions = value;
      else if (graph.min_mentions) minMentions = graph.min_mentions;
      render();
    },
    setMinMentions(value) {
      minMentions = value;
      render();
    },
    declutterLabels() {
      declutterLabels(cy);
    },
    resetLabelOffsets() {
      resetLabelOffsets(cy);
    },
    labelOverlaps() {
      return countLabelOverlaps(cy);
    },
  };
}
