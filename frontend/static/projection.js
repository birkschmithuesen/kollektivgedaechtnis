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
        'background-color': cssVar('--person-fill', '#242424'),
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
        'background-color': cssVar('--term-dot-color', '#FFFFFF'),
        label: 'data(label)',
        color: cssVar('--label-color', '#FFFFFF'),
        'font-family': cssVar('--label-font', 'Georgia, serif'),
        'font-size': cssVar('--label-size', '22'),
        'text-valign': 'bottom',
        // Both scale with the type: a wrap width and a gap tuned for 22px
        // labels turn 44px ones into a stack of short lines under the dot.
        'text-margin-y': cssVar('--label-margin-y', '6'),
        'text-wrap': 'wrap',
        'text-max-width': cssVar('--label-max-width', '220px'),
        'text-outline-width': cssVar('--label-outline-width', '3'),
        'text-outline-color': cssVar('--label-outline-color', '#000000'),
      },
    },
    {
      selector: 'edge.link',
      style: {
        width: cssVar('--edge-width', '2'),
        'line-color': cssVar('--edge-color', '#858585'),
        'curve-style': 'straight',
        opacity: cssVar('--edge-opacity', '0.75'),
      },
    },
  ];
}

// Everything below is sized in MODEL units, never rendered pixels — which is
// what makes spec 10.3's "always fills the screen" requirement free. Cytoscape
// scales node width/height AND font-size with the zoom, so a viewport fit is
// simultaneously the answer to "how big should a node be": three nodes fit at
// a high zoom and come out large, a hundred fit at a low zoom and come out
// small. There is no fixed on-screen scale to become unreadable or overcrowded.
const PADDING = 60;

/** The layout. fcose, from the library, not a hand-rolled force pass.
 *
 * Birk 2026-08-14 replaced the "nothing ever moves" rule with "everything
 * migrates slowly": when the graph changes, the whole net re-distributes to
 * fill the freed space. The anti-jump requirement is unchanged and is what
 * these options are chosen for — the enemy was ever only the JUMP, not the
 * movement (spec 11).
 *
 *   quality: 'proof'   — the only mode in which `randomize: false` is
 *                        supported at all, and the only one in which
 *                        `nodeDimensionsIncludeLabels` is honoured.
 *   randomize: false   — THE anti-jump guarantee, and it comes from the
 *                        library: the layout starts from the CURRENT node
 *                        positions and improves them. Never a re-roll.
 *   nodeDimensionsIncludeLabels — the layout knows a term node is its dot PLUS
 *                        its caption. Measured 2026-08-15 on the seeded
 *                        50-person / 75-term graph at theme b: without it 156
 *                        overlapping label pairs and 65 labels on portrait
 *                        discs, with it 42 and 26.
 *   packComponents     — early in the festival the net really is disconnected
 *                        (one component per interview, until two people share
 *                        a term). Polyomino packing keeps those components off
 *                        each other; needs cytoscape-layout-utilities, which
 *                        the pages load and `createGraphView` initialises.
 *
 * `animate` is false HERE on purpose: this is the computation, not the
 * migration. The glide is MIGRATION below, so that the passes that run between
 * the two (settlePlacement) cannot land as a snap after the animation.
 *
 * idealEdgeLength/nodeRepulsion are far above the cose defaults this file
 * carried before, because fcose measures a term node at its full label extent
 * (~340px wide at theme b) — an ideal edge shorter than that box guarantees
 * collisions. Swept 2026-08-15 over idealEdgeLength 160..640 x nodeRepulsion
 * 12k..120k on the seeded graph; 480 / 120000 is the cheapest pair the passes
 * below then clear to zero overlaps.
 */
export const LAYOUT = {
  name: 'fcose',
  quality: 'proof',
  randomize: false,
  animate: false,
  fit: false,
  padding: PADDING,
  nodeDimensionsIncludeLabels: true,
  packComponents: true,
  uniformNodeDimensions: false,
  nodeRepulsion: 120000,
  idealEdgeLength: 480,
  numIter: 2500,
};

// How long the net takes to migrate to its new arrangement. Slow on purpose:
// this is the transition a visitor watches when their own node joins the wall,
// and it must read as a glide, not as a cut. Exported so the pre-render can
// place its mid-flight frames inside it rather than guessing.
export const MIGRATION_DURATION_MS = 2500;

// Cytoscape's own `preset` layout does the gliding — positions in, animated
// interpolation out, viewport fit animated along with it. Nothing hand-built.
const MIGRATION = {
  name: 'preset',
  animate: true,
  animationDuration: MIGRATION_DURATION_MS,
  animationEasing: 'ease-in-out-cubic',
  padding: PADDING,
};

// How far a fresh node starts from a neighbour it already has, so the
// incremental layout begins from somewhere sensible instead of the origin.
// Deliberately much SHORTER than idealEdgeLength: `randomize: false` makes
// fcose sensitive to its starting state, and a compact start settles
// measurably better than a pre-spread one. Measured 2026-08-15 on the seeded
// 50-person graph across five density targets, from-scratch: starting at 140
// clears every target to zero overlapping label pairs, starting at 480 (one
// ideal edge) leaves 7-8 pairs and up to 4 labels on portrait discs.
const SEED_RADIUS = 140;

// cytoscape-layout-utilities also offers `placeNewNodes()` for exactly this,
// and it is the better heuristic (least-crowded quadrant around the existing
// neighbour). It is NOT used: it picks that quadrant with Math.random()
// (src/core/layout-utilities.js:256) and jitters the final spot with another
// (:313), so two pre-render runs over the same seed would not produce the same
// picture. Determinism outranks the better seed here; the golden angle below
// is a pure function of the node's index.
const GOLDEN_ANGLE = 2.39996;

function runLayout(cy, options) {
  return new Promise((resolve) => {
    const layout = cy.layout(options);
    layout.one('layoutstop', resolve);
    layout.run();
  });
}

/** Hand the browser two clear frames.
 *
 * Cytoscape times its animations off the animation loop's frame clock, and the
 * frame that arrives right after a long synchronous block carries a timestamp
 * from before it. Measured 2026-08-15 on the 50-person / 75-term net: with the
 * glide started immediately after settlePlacement returned, a 2500ms animation
 * ran out in 116ms of real time — the wall froze and then cut, which is
 * precisely the jump spec 11 forbids. Waiting for a second, genuinely fresh
 * frame resets that clock, and it also lets the browser paint the arrangement
 * the migration is about to start from.
 */
function nextFrame() {
  return new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
}

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

/** Count overlapping term-label boxes, label-on-person collisions, and person
 * discs sitting on each other.
 *
 * `includeNodes: false` on a boundingBox call isolates the LABEL's own box
 * from its dot — Cytoscape's real measured text extent (font metrics, wrap
 * width), not a guess — so this is exactly what a viewer would see collide.
 * Exported so the pre-render CLI and the dev console can both ask "how bad
 * is it right now" without reaching into private state.
 *
 * `personPairs` is Birk's seventh brief (2026-08-15): the legibility ladder
 * came back with portrait discs overlapping each other, and nothing here had
 * ever measured that. It is the only one of the three the declutter pass
 * cannot touch — a disc moves only when the placement moves it — so it is
 * scored in settlePlacement instead.
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

  const personBoxes = cy
    .nodes('.person')
    .sort(byId)
    .map((node) => node.boundingBox({ includeNodes: true, includeLabels: false }));
  let labelsOnPersons = 0;
  boxes.forEach((box) => {
    personBoxes.forEach((personBox) => {
      if (boxesOverlap(box, personBox)) labelsOnPersons += 1;
    });
  });

  let personPairs = 0;
  for (let i = 0; i < personBoxes.length; i += 1) {
    for (let j = i + 1; j < personBoxes.length; j += 1) {
      if (boxesOverlap(personBoxes[i], personBoxes[j])) personPairs += 1;
    }
  }

  return { labelPairs, labelsOnPersons, personPairs };
}

// fcose's nodeDimensionsIncludeLabels sizes each node's repulsion off its OWN
// measured extent, but a force layout is a compromise between forces, not an
// overlap solver — it never promises a collision-free result and does not
// deliver one here. Measured 2026-08-15 on the seeded 50-person / 75-term
// graph at theme b, fcose with every option above settles at 42 overlapping
// label-box pairs and 26 labels sitting on person discs. This pass pushes the
// MEASURED dot+label boxes (Cytoscape's own boundingBox, not a guessed
// constant) apart directly, in node-position space.
//
// It is a relaxation with a cap, NOT a solver: on that graph it does not reach
// a clean state within the cap. Getting to zero is the job of the rounds in
// settlePlacement() and the declutter pass afterwards, both of which are far
// cheaper per pair removed.
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
// And what one portrait disc lying on another is worth. The heaviest of the
// three: two discs on each other hide a face behind a face, and no later pass
// can undo it — the declutter pass moves labels only. Birk's seventh brief,
// 2026-08-15, after the sixth round's ladder came back with discs on discs.
const DISC_COLLISION_WEIGHT = 5;

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
// cloud is round: fcose's own output on the seeded graph is 1.18:1, which a
// viewport fit can only show at 59% of the canvas width (measured 2026-08-15).
// The camera cannot recover that — zooming in further only clips top and
// bottom — so the PLACEMENT is shaped like the surface instead.
const CANVAS_ASPECT = 16 / 9;
// A label keeps its own width when the nodes around it move apart, so one
// correction always undershoots the target. Iterate to it instead.
const FRAME_STEPS = 6;
const FRAME_TOLERANCE = 0.01;
// The stretch is the part of the framing that does distort, so it is bounded:
// beyond this the net is a smear, and something about the layout is wrong.
const MAX_STRETCH = 3;

/** Shape a placement like the canvas it is projected onto.
 *
 * Deterministic: a pure function of the settled positions, so the same seed
 * still yields the same picture. Exported so it can be exercised on its own.
 *
 * This used to begin with a quarter turn, because cose measured repulsion with
 * each node's width and height swapped and so settled a net of wide labels
 * PORTRAIT. fcose does not have that bug — its raw output on the seeded graph
 * comes out at 1.18:1, already landscape (measured 2026-08-15), so the
 * rotation never fired and is gone. Only the stretch remains.
 */
export function frameToAspect(cy, target = CANVAS_ASPECT) {
  const nodes = cy.nodes();
  if (nodes.length < 2) return;
  let box = nodes.boundingBox({ includeLabels: true });
  if (!(box.w > 0) || !(box.h > 0)) return;

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

// How much of its own bounding box a settled net fills with ink — the summed
// area of every node's dot/disc plus its label box, over the area of the cloud
// they sit in. This is the "fills the screen without overcrowding" number of
// Birk's fourth brief, and it is a CONSTANT on purpose: hold it fixed and the
// viewport fit does the rest, because three nodes then claim a small cloud and
// come out large while a hundred claim a large one and come out small.
//
// Without it the picture does not scale at all. A force layout's cloud size is
// set by its gravity and its ideal edge length, not by how much is in it:
// measured 2026-08-15 across seeded graphs of 3 / 6 / 20 / 50 persons, fcose's
// own output put labels on the wall at 17.3 / 20.8 / 14.5 / 15.1 px — flat and
// non-monotone, which is exactly the "fixed scale that eventually becomes
// unreadable" the brief rules out.
//
// It is an AMBITION, not a promise: settlePlacement() below loosens it step by
// step until the picture is actually clean, so the delivered density is "as
// tight as these labels allow" rather than a number tuned against one graph.
// That matters — the value has a cliff and the cliff moves with the theme.
// Measured 2026-08-15 on the seeded 5 / 20 / 50-person graphs at theme B,
// labels on the wall and overlapping pairs at 50 persons, with no loosening:
//   0.55 -> 30.2 / 20.0 / 15.7 px, 17 pairs and 15 labels on discs
//   0.45 -> 28.8 / 18.2 / 14.3 px,  8 pairs and 4 on discs
//   0.40 -> 28.0 / 17.2 / 13.5 px,  0 and 0
//   0.35 -> 26.5 / 16.2 / 12.6 px,  0 and 0
// 0.35 is the value theme B needs no loosening at all for, which keeps the
// common case fast; theme A (22px type on bigger discs) does need it.
const TARGET_INK_FRACTION = 0.35;

/** Spread or gather a placement uniformly about its own centre.
 *
 * Uniform, so it distorts nothing and — this is what the loop in
 * settlePlacement() relies on — a factor above 1 can only ever REDUCE
 * overlaps: every gap grows while every box keeps its size.
 */
function scaleAbout(cy, factor) {
  const nodes = cy.nodes();
  if (nodes.length < 2 || !(factor > 0) || Math.abs(factor - 1) < 0.001) return;
  const box = nodes.boundingBox({ includeLabels: true });
  const centre = { x: (box.x1 + box.x2) / 2, y: (box.y1 + box.y2) / 2 };
  nodes.positions((node) => {
    const at = node.position();
    return { x: centre.x + (at.x - centre.x) * factor, y: centre.y + (at.y - centre.y) * factor };
  });
}

/** Scale a settled placement until the net claims `target` of its own
 * bounding box in ink. Deterministic, and a no-op on a net already there.
 */
export function normaliseDensity(cy, target = TARGET_INK_FRACTION) {
  const nodes = cy.nodes();
  if (nodes.length < 2) return;
  const box = nodes.boundingBox({ includeLabels: true });
  const area = box.w * box.h;
  if (!(area > 0)) return;
  const ink = nodes.reduce((sum, node) => {
    const own = node.boundingBox({ includeLabels: true });
    return sum + own.w * own.h;
  }, 0);
  if (!(ink > 0)) return;
  scaleAbout(cy, Math.sqrt(ink / target / area));
}

// Separation and framing pull against each other, so one round of each
// undershoots: separating pushes boxes apart along whichever axis is
// cheapest, which pulls the cloud back towards square, and re-stretching it
// to 16:9 opens gaps that let the next separation round resolve collisions
// it previously had no room for.
//
// So this is a cap, not a target: the loop below stops as soon as the rounds
// stop paying, and each round costs real time (~0.2s per round on the seeded
// 50-person graph, all of it inside boundingBox).
const PLACEMENT_ROUNDS = 16;
// Rounds that buy nothing before giving up. One flat round is not enough
// evidence — an earlier measurement sat at 24 pairs for four rounds before it
// broke through to 5.
const PLACEMENT_PATIENCE = 5;
// If neither the rounds nor the declutter pass can clear the picture, the net
// is simply packed too tightly for these labels: give it more room and run
// them again. A uniform spread cannot create an overlap, so this always
// converges downward — the only question is how many steps it costs, and every
// step costs a full set of rounds.
const LOOSEN_STEP = 1.12;
const LOOSEN_ATTEMPTS = 8;

/** Shape a placement for this wall: 16:9, as tight as the labels allow, and
 * with the layout finally knowing that a term node is its dot PLUS its label
 * box.
 *
 * This is the hand-built geometry the fcose migration did NOT delete, and it
 * was kept on the numbers Birk's brief asked for (2026-08-15, seeded 50-person
 * / 75-term graph, theme b, identical starting state):
 *
 *   fcose alone                            42 pairs / 26 on discs / 59% width
 *   fcose, nodeDimensionsIncludeLabels off 156 / 65 / 43%
 *   fcose + declutterLabels only           43 / 14 / 59%
 *   fcose + this (declutter included)       0 /  0 / 89%
 *
 * The width number is the part fcose has no option for at all: no fcose or
 * layout-utilities option shapes a single connected component to an aspect
 * ratio (`desiredAspectRatio` applies to randomized component PACKING only).
 */
export function settlePlacement(cy, { inkFraction = TARGET_INK_FRACTION } = {}) {
  normaliseDensity(cy, inkFraction);
  frameToAspect(cy);
  const nodes = cy.nodes().sort(byId);
  const snapshot = () => nodes.map((node) => ({ ...node.position() }));
  // All three collision kinds, because this is the only pass that can move a
  // person disc. Scoring the labels alone let the loop declare a picture clear
  // — and stop loosening — while two portraits still lay on each other:
  // measured 2026-08-15 on 20 persons around 3 short terms (0 label pairs, 0
  // labels on discs, 7 disc pairs) and on the seeded 50-person net at theme c
  // (0 / 0 / 2).
  const score = () => {
    const { labelPairs, labelsOnPersons, personPairs } = countLabelOverlaps(cy);
    return (
      labelPairs + PERSON_COLLISION_WEIGHT * labelsOnPersons + DISC_COLLISION_WEIGHT * personPairs
    );
  };
  let best = { score: Infinity, positions: null };

  for (let attempt = 0; attempt < LOOSEN_ATTEMPTS; attempt += 1) {
    let flatRounds = 0;
    let clear = false;
    for (let round = 0; round < PLACEMENT_ROUNDS; round += 1) {
      separateOverlappingNodes(cy);
      frameToAspect(cy);
      const current = score();
      if (current < best.score) {
        best = { score: current, positions: snapshot() };
        flatRounds = 0;
      } else if ((flatRounds += 1) >= PLACEMENT_PATIENCE) {
        break;
      }
      if (current === 0) {
        clear = true;
        break;
      }
    }
    if (clear) break;

    // The two levers are not equal. Moving a label is free; spreading the net
    // costs type size, because the camera then has more to fit onto the same
    // wall. So ask the free one first, and only loosen if it is not enough.
    // The offsets are thrown away again either way — settleLabels() re-derives
    // them from the final positions — this is purely about whether the net has
    // to grow. Measured 2026-08-15 on the seeded graph: asking here keeps the
    // net one loosening step tighter, which is 12.7px of type on the wall
    // instead of 11.4px, at zero overlaps either way.
    resetLabelOffsets(cy);
    declutterLabels(cy);
    const assisted = score();
    resetLabelOffsets(cy);
    if (assisted === 0) {
      best = { score: 0, positions: snapshot() };
      break;
    }

    scaleAbout(cy, LOOSEN_STEP);
    frameToAspect(cy);
  }

  // Pushing node A clear of B can push it into C, so the rounds do not
  // descend cleanly — they wander. Ending on whatever the last round happened
  // to produce would throw away a better picture the loop had already found
  // and paid for, so the best one is what gets kept.
  if (best.positions) {
    nodes.forEach((node, index) => node.position({ ...best.positions[index] }));
  }
}

// Reset then declutter, and measure both sides of it. `before` is the
// layout's own settled state (positions final, labels still at the theme
// default); `after` is what a viewer actually sees.
function settleLabels(cy) {
  resetLabelOffsets(cy);
  const before = countLabelOverlaps(cy);
  declutterLabels(cy);
  const after = countLabelOverlaps(cy);
  return { before, after };
}

/** Compute the net's new arrangement, then GLIDE the whole net into it.
 *
 * The order is the point. The arrangement is computed with the animation off
 * (fcose, then settlePlacement over its result), the nodes are put back where
 * they started, and only then does Cytoscape's own `preset` layout animate
 * every node from its old place to its new one. Computing first and animating
 * once means the passes after the layout cannot land as a snap at the end of
 * an animation — what a visitor sees is one continuous migration, from the
 * arrangement that was on the wall to the arrangement that fills it.
 */
async function migrate(cy, { fit, duration, onGlideStart = () => {} }) {
  const nodes = cy.nodes().sort(byId);
  const from = nodes.map((node) => ({ ...node.position() }));

  // Label offsets are geometry too, and stale ones (sized for the old, denser
  // arrangement) would measurably mislead the separation pass.
  resetLabelOffsets(cy);
  await runLayout(cy, LAYOUT);
  settlePlacement(cy);

  const to = new Map(nodes.map((node) => [node.id(), { ...node.position() }]));
  nodes.forEach((node, index) => node.position(from[index]));
  await nextFrame();
  onGlideStart();
  await runLayout(cy, {
    ...MIGRATION,
    animationDuration: duration,
    fit,
    positions: (node) => to.get(node.id()),
  });
}

export function createGraphView(
  container,
  { onPositions = () => {}, migrationDuration = MIGRATION_DURATION_MS } = {},
) {
  const cy = cytoscape({ container, style: style(), wheelSensitivity: 0.2 });
  // fcose only packs disconnected components when this extension is
  // initialised on the instance (it calls cy.layoutUtilities('get') and falls
  // back to constructing one). Doing it here, once, is also the only place the
  // packing options can be set.
  if (cy.layoutUtilities) cy.layoutUtilities({ desiredAspectRatio: CANVAS_ASPECT, componentSpacing: 80 });
  const camera = new Camera(cy);
  let lastGraph = { nodes: [], edges: [], min_mentions: 1 };
  let minMentions = 1;
  // True while a migration is running (computation AND glide). Tests and the
  // pre-render wait on this instead of guessing a timeout.
  let layoutPending = false;
  // True only while the net is actually in flight — layoutPending covers the
  // computation before it too. Separate flags because they answer different
  // questions: "are the positions final yet" and "is a viewer watching motion
  // right now". The pre-render needs the second one to place its frames
  // inside the glide rather than inside the compute.
  let gliding = false;
  // One migration at a time. The operator can spin the density dial faster
  // than a 2.5s glide, and two overlapping layouts over one cy instance would
  // interleave their position writes.
  let migration = null;
  let rerenderQueued = false;
  const emptyStats = { labelPairs: 0, labelsOnPersons: 0 };
  let labelOverlapStats = { before: emptyStats, after: emptyStats };
  // Where each node was last seen, by id. The dial hides term nodes by
  // REMOVING them from cy, so turning it back down re-adds them — and until
  // the server has round-tripped this session's positions back into
  // `lastGraph`, those nodes carry x/y null and would read as brand new.
  // Starting them from the origin would make the migration a jump for exactly
  // the half of the net that returned. They start where they left instead,
  // and migrate from there like everyone else.
  const lastSeen = new Map();

  function persist() {
    const positions = {};
    cy.nodes().forEach((n) => {
      positions[n.id()] = { x: n.position('x'), y: n.position('y') };
    });
    onPositions(positions);
  }

  function render() {
    if (migration) {
      rerenderQueued = true;
      return;
    }
    const view = visibleGraph(lastGraph, minMentions);
    const wanted = new Set(view.nodes.map((n) => n.id).concat(view.edges.map((e) => e.id)));
    const present = cy.elements().map((el) => el.id());

    cy.nodes().forEach((n) => lastSeen.set(n.id(), { ...n.position() }));

    const dropped = cy.elements().filter((el) => !wanted.has(el.id()));
    const removedCount = dropped.length;
    dropped.remove();

    const placed = new Set(
      view.nodes
        .filter((n) => n.x !== null && n.x !== undefined && n.y !== null && n.y !== undefined)
        .map((n) => n.id),
    );
    const arriving = newNodeIds(present, view);
    const returning = arriving.filter((id) => !placed.has(id) && lastSeen.has(id));
    const fresh = arriving.filter((id) => !placed.has(id) && !lastSeen.has(id));
    const toAdd = toCytoscape(view).filter((el) => cy.$id(el.data.id).length === 0);
    if (toAdd.length) cy.add(toAdd);
    returning.forEach((id) => cy.$id(id).position({ ...lastSeen.get(id) }));

    fresh.forEach((id, index) => {
      const node = cy.$id(id);
      // `fresh` already excludes every id in `placed` (an explicit x/y
      // null-check against the graph data, not a truthy check on the rendered
      // position), so every node reached here is genuinely unseeded and must
      // always be positioned. A `position('x') || position('y')` guard here
      // would be confused by a node legitimately seeded to exactly (0, 0).
      const anchor = node.neighborhood('node').filter((n) => !fresh.includes(n.id()))[0];
      const base = anchor ? anchor.position() : { x: 0, y: 0 };
      const angle = index * GOLDEN_ANGLE;
      node.position({ x: base.x + Math.cos(angle) * SEED_RADIUS, y: base.y + Math.sin(angle) * SEED_RADIUS });
    });

    // Crash recovery (spec 10.5) is the one case that must NOT migrate: the
    // first paint of a session whose every node already carries a persisted
    // position has to reproduce the wall exactly as it stood, not re-arrange
    // it while nobody is looking. Every other change — a person joining, the
    // dial hiding or revealing terms — re-distributes the whole net.
    const restoring = present.length === 0 && view.nodes.length > 0 && placed.size === view.nodes.length;
    const changed = toAdd.length > 0 || removedCount > 0;

    const settle = () => {
      labelOverlapStats = settleLabels(cy);
      camera.onGraphChanged();
    };

    if (!changed || restoring) {
      settle();
      layoutPending = false;
      return;
    }

    layoutPending = true;
    migration = migrate(cy, {
      fit: camera.mode === 'fit',
      duration: migrationDuration,
      onGlideStart: () => {
        gliding = true;
      },
    })
      .catch((error) => console.warn('layout migration failed', error))
      .then(() => {
        migration = null;
        gliding = false;
        settle();
        persist();
        if (rerenderQueued) {
          rerenderQueued = false;
          render();
        } else {
          layoutPending = false;
        }
      });
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
    get migrating() {
      return gliding;
    },
    get migrationDuration() {
      return migrationDuration;
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
