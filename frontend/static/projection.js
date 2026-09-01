import { newNodeIds, toCytoscape, visibleGraph } from './graph-model.js';
import { LINE_HEIGHT } from './term-plate.js';
import { Camera } from './camera.js';

// Matches kg/config.py's Config.default_max_terms -- only relevant before the
// first real state push ever arrives.
const DEFAULT_MAX_TERMS = 32;
// See the hysteresis comment in createGraphView() for what this guards.
const MIN_STAND_REVISIONS = 3;

function cssVar(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

/* theme-f „Schwarzplan" (Entwurf 2026-08-30, an Cytoscape 3.30.2 headless
   geprueft). Eigene Funktion statt Aenderungen an style(): theme-e bleibt
   damit als Rueckfallebene woertlich erhalten, und beide sind ueber
   ?theme= vergleichbar — Birk urteilt am Bild, nicht an der Beschreibung.

   Die drei Aenderungen gegenueber theme-e:
   1. Der Punkt am Begriff faellt weg; der Begriff IST die beschriftete
      Flaeche. Kanten enden dadurch an der Tafelkante statt unter der Schrift.
   2. Die Achsenfarbe wandert von der Schrift in die Flaeche. Farbige Schrift
      auf Schwarz ist der schwaechste Traeger, den eine Farbe haben kann.
   3. Statt Schlagschatten ein helles Halo: auf additiver Projektion ist ein
      dunkler Schatten auf Schwarz buchstaeblich unsichtbar.

   GEMESSEN, nicht gewaehlt: Weiss auf Gelb hat 1.66:1 und ist unlesbar —
   gelbe Tafeln tragen deshalb SCHWARZE Schrift (12.65:1). */
function styleSchwarzplan() {
  const FF = cssVar('--label-font', 'Georgia, serif');
  const FS = cssVar('--label-size', '26');
  const PERSON_FILL = cssVar('--person-fill', '#242424');
  const PERSON_BLANK = cssVar('--person-blank', '#6E6656');

  return [
    /* ---- PERSONEN: Portrait mit Tiefe ------------------------------------
       Drei Schichten statt der einen flachen Scheibe:
         underlay-*  ein weiches, HELLES Halo. Auf additiver Projektion ist
                     nur Licht sichtbar — ein dunkler Schlagschatten auf
                     Schwarz wäre an der Wand exakt nichts. Das Halo dreht
                     den Effekt um: der Schatten ist Licht.
         background-fill: radial-gradient  füllt den Rest der Scheibe dort,
                     wo das Portrait durchscheinend ausläuft.
         outline-*   ein zweiter, schwacher Ring in Abstand — das
                     konzentrische Echo, Bauhaus-Zirkelgeometrie.
       Der weiche Rand selbst kommt NICHT von hier, sondern aus dem PNG:
       kg/photos.py muss die harte Ellipsenmaske gegen einen Alpha-Verlauf
       tauschen (siehe make_portrait-Patch). Cytoscape respektiert das
       Alpha — headless nachgemessen. */
    {
      selector: 'node.person',
      style: {
        shape: 'ellipse',
        width: cssVar('--person-size', '110'),
        height: cssVar('--person-size', '110'),
        /* Zwei Fuellungen, nach Datenlage (Birk, 2026-09-01: „Es kann ja
           sein, dass irgendwer nicht will, dass ein Foto von ihm oder ihr
           gemacht wird"). Hinter einem Portrait bleibt der Grund schwarz --
           er ist es, der die harte Knotenkante unter dem auslaufenden
           PNG-Alpha verschwinden laesst. OHNE Portrait waere derselbe Grund
           auf --bg #000000 buchstaeblich nichts: am Bild gemessen 247 von
           28392 Pixeln nicht schwarz, und die kamen von der Kante zum
           Begriff. In theme-f traegt weder Ring noch Lichthof (beide auf 0),
           also muss die Fuellung selbst die Scheibe tragen.

           Eine Farbe, keine Vertretung: kein Platzhalter-Avatar, kein
           Fragezeichen, kein Icon. Wer sich gegen ein Bild entscheidet, ist
           kein fehlendes Bild. */
        'background-color': (ele) => (ele.data('portrait') ? PERSON_FILL : PERSON_BLANK),
        // KEIN radial-gradient hinter dem Portrait mehr. Er stammte aus dem
        // ersten Entwurf und sollte „die Scheibe dort fuellen, wo das Portrait
        // durchscheinend auslaeuft" — genau diese Aufgabe hat seit 2026-08-30
        // der Goldring im PNG (kg/photos.py, ring_glow). Der dunkle Verlauf
        // (#1a1a1a -> #000000) lag praezise ueber der Uebergangszone und hat
        // den Ring verschluckt: Am Bild gemessen war er im PNG da
        // ((195,168,84) bei Alpha 254), auf der Wand aber unsichtbar.
        'background-image': (ele) => ele.data('portrait') || 'none',
        'background-fit': 'cover',
        'background-clip': 'node',
        'border-width': cssVar('--ring-width', '5'),
        'border-color': cssVar('--ring-color', '#D62828'),
        'border-opacity': 1,
        'outline-width': cssVar('--ring-echo-width', '1'),
        'outline-color': cssVar('--ring-color', '#D62828'),
        'outline-offset': cssVar('--ring-echo-offset', '7'),
        'outline-opacity': cssVar('--ring-echo-opacity', '0.35'),
        'underlay-color': cssVar('--halo-color', '#FFFFFF'),
        'underlay-opacity': cssVar('--halo-opacity', '0.10'),
        'underlay-padding': cssVar('--halo-padding', '14'),
        'underlay-shape': 'ellipse',
        label: '',
        'z-index': 20,
      },
    },

    /* ---- BEGRIFFE: die Tafel IST der Knoten ------------------------------
       Der Punkt ist ersatzlos weg. Er hat nie etwas bedeutet: er war ein
       Anfasser für die Kante und ein Anker fürs Label, und er kostete den
       Blick einen Sprung (Punkt finden -> Text daneben lesen -> zuordnen).
       Jetzt zielen die Kanten auf die Schriftfläche selbst.

       background-opacity: 0 — der Knotenkörper ist unsichtbar, er ist nur
       noch die Trefferfläche und das Kantenziel. Sichtbar ist allein die
       text-background-* Tafel. Damit stimmen Tafel und Knotengeometrie
       überein, und das fcose-Layout rechnet mit der wahren Fläche. */
    {
      selector: 'node.term',
      style: {
        shape: 'round-rectangle',
        'corner-radius': cssVar('--plate-radius', '2'),
        width: 'data(boxW)',
        height: 'data(boxH)',
        // NICHT gefuellt, nur umrandet — das echte Rendering zeigt Konturen,
        // durch die der Grund durchscheint, keine massiven Kaestchen.
        'background-color': '#000000',
        'background-opacity': cssVar('--term-plate-idle-opacity', '0.35'),
        'border-width': cssVar('--term-ring-width', '1.5'),
        'border-color': cssVar('--term-ring-idle', '#6E6656'),
        'border-opacity': 0.85,
        label: 'data(label)',
        color: cssVar('--label-color', '#FFFFFF'),
        'font-family': FF,
        'font-size': FS,
        'text-valign': 'center',
        'text-halign': 'center',
        'text-wrap': 'wrap',
        'text-max-width': cssVar('--label-max-width', '220px'),
        'text-justification': 'center',
        'line-height': LINE_HEIGHT,
        // Ruhende Begriffe: Kontur, keine Tafel. Sie sollen zurücktreten.
        'text-outline-width': cssVar('--label-outline-width', '4'),
        'text-outline-color': cssVar('--label-outline-color', '#000000'),
        'z-index': 10,
      },
    },

    /* Im Bild: die Tafel wird massiv. Der Umschlag von "Kontur auf Schwarz"
       zu "Schrift auf Farbfläche" ist der stärkste Sprung, den die Wand
       hergibt — ganz ohne Größenänderung, die Birk zu Recht verworfen hat.
       text-outline-width: 0, weil eine schwarze Kontur auf einer Farbtafel
       die Schrift nur verschmutzt. */
    {
      selector: 'node.term.in-dream',
      style: {
        'border-width': cssVar('--term-ring-dream-width', '3'),
        'background-opacity': cssVar('--term-plate-dream-opacity', '0.55'),
        // Der Lichthof, der im Rendering jedes Element traegt. Auf additiver
        // Projektion die einzige Richtung, die wirkt: Licht addiert sich,
        // ein Schatten auf Schwarz waere unsichtbar.
        'underlay-color': cssVar('--halo-color', '#C9A227'),
        'underlay-opacity': 0.16,
        'underlay-padding': 10,
        'underlay-shape': 'round-rectangle',
        // Ohne diesen Radius zeichnet Cytoscape den Lichthof mit SCHARFEN
        // Ecken, obwohl die Form 'round-rectangle' heisst — der Radius wird
        // NICHT vom Knoten geerbt (Birk, 2026-08-30: „Der Glow um die
        // markierten Kaestchen ist quadratisch"). Im Bundle 3.30.2 vorhanden,
        // nachgeprueft. Etwas groesser als der Knotenradius, weil der Hof
        // 10 Einheiten weiter aussen liegt und sonst enger wirkt als das
        // Kaestchen, das er umgibt.
        'underlay-corner-radius': cssVar('--plate-radius-glow', '28'),
        'z-index': 15,
      },
    },

    /* Die drei Achsen. Die Schriftfarbe ist NICHT frei wählbar, sondern
       folgt dem Kontrast auf der jeweiligen Fläche (gemessen, WCAG):
         auf Rot  #D62828 : Weiß  5.01:1   ok
         auf Blau #1D4E9C : Weiß  8.01:1   ok
         auto Gelb #F4C300: Weiß  1.66:1   UNLESBAR -> Schwarz 12.65:1
       Deshalb trägt Gelb schwarze Schrift. Das ist keine Stilfrage. */
    {
      selector: 'node.term.dream-anchor',
      style: {
        'border-color': cssVar('--dream-anchor-color', '#D62828'),
        'underlay-color': cssVar('--dream-anchor-color', '#D62828'),
      },
    },
    {
      selector: 'node.term.dream-neighbour',
      style: {
        'border-color': cssVar('--dream-neighbour-color', '#1D4E9C'),
        'underlay-color': cssVar('--dream-neighbour-color', '#1D4E9C'),
      },
    },
    {
      selector: 'node.term.dream-recent',
      style: {
        'border-color': cssVar('--dream-recent-color', '#F4C300'),
        'underlay-color': cssVar('--dream-recent-color', '#F4C300'),
      },
    },

    /* ---- KANTEN: Bögen statt Schnüre -------------------------------------
       unbundled-bezier mit zwei Kontrollpunkten aus edgeCurve(). Weil die
       Begriffs-Knoten jetzt die volle Tafelfläche haben, endet die Kante
       automatisch an der Tafelkante statt unter der Schrift — das
       "Ausweichen um Beschriftungen" fällt als Nebenwirkung ab und muss
       nicht gerechnet werden. */
    {
      selector: 'edge.link',
      style: {
        width: cssVar('--edge-width', '2'),
        'line-color': cssVar('--edge-color', '#858585'),
        'curve-style': 'unbundled-bezier',
        'control-point-distances': 'data(cpd)',
        'control-point-weights': 'data(cpw)',
        'edge-distances': 'intersection',
        'line-cap': 'round',
        'line-opacity': cssVar('--edge-opacity', '0.75'),
        'z-index': 1,
      },
    },

    /* Kanten ins Bild hinein: leicht kräftiger und in der Ankerfarbe. So
       zeigt das Netz, WOHER der gezeigte Ausschnitt gespeist wird. */
    {
      selector: 'edge.link.in-dream',
      style: {
        width: cssVar('--edge-width-dream', '3'),
        'line-color': cssVar('--dream-anchor-color', '#D62828'),
        'line-opacity': cssVar('--edge-opacity-dream', '0.9'),
        'z-index': 5,
      },
    },
  ];
}


function style() {
  const PERSON_FILL = cssVar('--person-fill', '#242424');
  const PERSON_BLANK = cssVar('--person-blank', '#6E6656');

  return [
    {
      selector: 'node.person',
      style: {
        shape: 'ellipse',
        width: cssVar('--person-size', '96'),
        height: cssVar('--person-size', '96'),
        // Wie in styleSchwarzplan(): ohne Portrait eine eigene, ruhige
        // Fuellung. Hier traegt der Ring die Scheibe zwar ohnehin, aber eine
        // Person ohne Bild soll in allen Themes dasselbe sein und nicht in
        // dreien eine leere und in einem eine gefuellte Scheibe.
        'background-color': (ele) => (ele.data('portrait') ? PERSON_FILL : PERSON_BLANK),
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
      // Die Begriffe, aus denen gerade das Bild entsteht (Birk, 2026-08-30).
      // KEINE Größenänderung — der erste Entwurf machte sie größer, Birk hat
      // das verworfen: Die Schriftgröße ist über die Themen a/b/c gegen die
      // Lesbarkeit auf 1080 Zeilen kalibriert, und zwei Größen nebeneinander
      // machen die kleinere zur zweiten Klasse. Die Vorgaben unten sind
      // deshalb gleich den Normalwerten; ein Theme darf sie ändern, das
      // Bauhaus-Theme (theme-e.css) tut es bewusst nicht.
      // Muss NACH `node.term` stehen: Cytoscape gewichtet gleich spezifische
      // Selektoren nach Reihenfolge, und diese Regel soll gewinnen.
      selector: 'node.term.in-dream',
      style: {
        width: cssVar('--term-dot-dream', '14'),
        height: cssVar('--term-dot-dream', '14'),
        'border-width': cssVar('--term-dream-ring', '0'),
        'border-color': cssVar('--dream-anchor-color', '#D62828'),
        'font-size': cssVar('--label-size-dream', '22'),
        'text-outline-width': cssVar('--label-outline-width-dream', '3'),
        'z-index': 10,
      },
    },
    {
      // Die drei Bauhaus-Grundfarben tragen die drei Auswahlachsen aus
      // `kg2.weighting.select_required`, damit an der Wand ablesbar ist,
      // WARUM ein Begriff im Bild ist. Rot = Anker (das Zentrum des
      // Ausschnitts), Blau = seine Nachbarschaft, Gelb = das gerade erst
      // Gesagte. Punkt UND Schrift nehmen die Farbe an: Der Punkt allein
      // verschwindet, sobald ein Portrait davor liegt.
      selector: 'node.term.dream-anchor',
      style: {
        'background-color': cssVar('--dream-anchor-color', '#D62828'),
        color: cssVar('--dream-anchor-color', '#D62828'),
      },
    },
    {
      selector: 'node.term.dream-neighbour',
      style: {
        'background-color': cssVar('--dream-neighbour-color', '#1D4E9C'),
        color: cssVar('--dream-neighbour-color', '#1D4E9C'),
      },
    },
    {
      selector: 'node.term.dream-recent',
      style: {
        'background-color': cssVar('--dream-recent-color', '#F4C300'),
        color: cssVar('--dream-recent-color', '#F4C300'),
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
//
// The PORTRAIT DISCS carry one deliberate qualification since 2026-08-29: an
// upper bound in rendered pixels, so a wall with a single person on it does
// not show one face and nothing else. See the portrait-size block in
// createGraphView() for how that is kept from feeding back into everything
// else.
const PADDING = 60;

// The largest a portrait may get on the wall, in RENDERED pixels, until the
// operator says otherwise. Birk, live at the station 2026-08-29: with a single
// person on the wall the model-unit sizing filled the whole screen with one
// face. Measured on the unchanged renderer at 1920x1080, one person and one
// term: 367px at theme a, 450px at theme b — against 29px at fifty persons.
//
// A CEILING, not a size (Birk again, 2026-08-30, correcting b803745). He
// wanted that one case gone, not the sizing: on the touchscreen, pinching into
// a portrait until it fills the format is how a visitor looks at a face.
//
// 120px is a tenth of the wall's height: plainly a portrait rather than a
// backdrop when one person stands alone. It sits in the lower half of the
// operator's 40-260px range on purpose — the placement does not know about
// this size (see below), so a generous ceiling would let a busy wall crowd
// itself before anyone had touched a control. The exact value is an on-site
// judgement like the zoom next to it.
const DEFAULT_PORTRAIT_SIZE = 120;

// Re-size the discs only when the target size has moved by more than this
// fraction.
//
// A style write per zoom frame is NOT free, which is why this threshold
// exists. Measured 2026-08-29 in Chromium on the seeded 50-person net: one
// batched width/height/border-width write across 50 person nodes costs 2.8ms
// (mean over 200 writes; themes a and b within 0.2ms of each other) — a sixth
// of a 16.7ms frame, spent on nothing else but resizing discs. And the
// automatic tour changes the zoom on EVERY frame (camera.js's breathing, ±6%
// over 42s), so an unthrottled version would pay it continuously, all day,
// for a size change of about 0.015% per frame that no one can see.
//
// At 1% a disc is off its target size by at most a pixel in a hundred, and a
// whole breathing cycle costs ~24 writes instead of ~2500. Operator changes
// and camera fits bypass the threshold entirely (`force`), so the one case
// where the size really does jump is never throttled. It also bounds the 1.5s
// handover, where the ceiling eases back on: ~1% per write there too, which is
// a step no eye resolves on a face travelling from 1200px to 120px.
const PORTRAIT_ZOOM_TOLERANCE = 0.01;

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

/** Run a layout to completion.
 *
 * `around` wraps the START of the run, not the whole run: a layout with
 * `fit: true` resolves its target viewport synchronously inside run()
 * (cytoscape's animate() calls getFitViewport there and then), so that is
 * where the portrait discs have to be back at their placement size — see
 * createGraphView(). The default is the plain call.
 */
function runLayout(cy, options, around = (run) => run()) {
  return new Promise((resolve) => {
    const layout = cy.layout(options);
    layout.one('layoutstop', resolve);
    around(() => layout.run());
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

  // In theme-f („Schwarzplan") steht die Schrift MITTIG IM Knoten, nicht als
  // Beschriftung darunter. Ein text-margin verschiebt dort zwar den Text,
  // aber nicht die Tafel, auf der er liegt — die Schrift liefe aus ihrer
  // eigenen Fläche heraus, und die Überlappung mit den Portraits bliebe
  // bestehen. Gemessen am realen Graphen: 113 Überschneidungen, und
  // before == after, das Verfahren lief vollständig ins Leere (Birk sah
  // genau das: „die Portraits liegen wieder über den Begriffen").
  //
  // Dort ist die Fläche selbst der Knoten, also muss der KNOTEN ausweichen,
  // nicht seine Beschriftung — und das gehoert ins Layout, nicht hierher.
  // theme-f: Die Schrift steht MITTIG im Knoten, ein text-margin verschiebt
  // dort den Text aus seinem eigenen Ring heraus statt die Ueberlappung zu
  // loesen. Also gar nicht erst versuchen.
  //
  // Ein eigenes Verfahren, das die KNOTEN schiebt, stand hier und ist wieder
  // raus: gemessen brachte es NICHTS (before == after) und kostete 78
  // Sekunden bis zum ersten Bild — 300 Runden ueber 110 Tafeln gegen 60
  // Portraits. Der richtige Hebel sitzt im Layout (fcose kennt die
  // Tafelgroesse ueber data(boxW/boxH) bereits), nicht in einer
  // Nachbearbeitung.
  if (terms.length > 0 && terms[0].style('text-valign') === 'center') return;

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
// theme-f: Dieselbe Groesse, aber als Flaeche statt als Punkt mit Text — das
// Netz braucht mehr Luft, damit die Kaestchen sich nicht beruehren. Kleiner
// heisst weiter auseinander.
const PLATE_INK_FRACTION = 0.18;

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
export function settlePlacement(cy, { inkFraction = null } = {}) {
  // Die Zieldichte ist THEMENABHAENGIG — der Kommentar an TARGET_INK_FRACTION
  // sagt es selbst: „der Kliff bewegt sich mit dem Theme". Der Wert 0.35 ist
  // gegen Punkt-plus-Beschriftung kalibriert; in theme-f ist ein Begriff ein
  // Kaestchen von 185x75 statt eines Punktes mit Text daneben, und dieselbe
  // Dichte presst es wieder zusammen, sobald das Aufweiten gewirkt hat.
  // Gemessen: 30 ueberlappende Paare bei 110 Begriffen, unabhaengig davon wie
  // oft die Schleife lockerte (Birk, 2026-08-30: „die Kaestchen ueberlappen
  // sich").
  if (inkFraction === null) {
    const kaestchen =
      cy.nodes('.term').length > 0 && cy.nodes('.term')[0].style('text-valign') === 'center';
    inkFraction = kaestchen ? PLATE_INK_FRACTION : TARGET_INK_FRACTION;
  }
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
    const current0 = score();

    // The two levers are not equal. Moving a label is free; spreading the net
    // costs type size, because the camera then has more to fit onto the same
    // wall. So ask the free one first, and only loosen if it is not enough.
    // The offsets are thrown away again either way — settleLabels() re-derives
    // them from the final positions — this is purely about whether the net has
    // to grow. Measured 2026-08-15 on the seeded graph: asking here keeps the
    // net one loosening step tighter, which is 12.7px of type on the wall
    // instead of 11.4px, at zero overlaps either way.
    // In theme-f steht die Schrift IM Knoten: declutterLabels kann dort nichts
    // verschieben (siehe dort), also ist das Aufweiten der EINZIGE Hebel und
    // muss ohne diesen Zwischenschritt weiterlaufen. Ohne die Fallunter-
    // scheidung endete die Schleife hier mit „das Label hat nicht geholfen",
    // obwohl sie es nie versucht hatte — gemessen 30 ueberlappende Paare bei
    // 110 Begriffen (Birk, 2026-08-30: „die Kaestchen ueberlappen sich").
    const schriftImKnoten =
      cy.nodes('.term').length > 0 && cy.nodes('.term')[0].style('text-valign') === 'center';
    let assisted = current0;
    if (!schriftImKnoten) {
      resetLabelOffsets(cy);
      declutterLabels(cy);
      assisted = score();
      resetLabelOffsets(cy);
    }
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
async function migrate(
  cy,
  { fit, duration, onUmbauStart = () => {}, onGlideStart = () => {}, atPlacementSize, atPlacementSizeAsync },
) {
  const nodes = cy.nodes().sort(byId);
  const from = nodes.map((node) => ({ ...node.position() }));

  // 🔴 Die KAMERA erfährt hier, dass die Knoten sich bewegen — nicht erst kurz
  // vor dem Gleiten (Birk, 2026-08-31, Punkt 7).
  //
  // Gemessen 2026-09-01: Der Sprung lag NICHT im Gleiten, sondern davor. Das
  // `fcose` unten rechnet die neue Anordnung und schreibt sie den Knoten
  // direkt ein; `settlePlacement` schiebt sie weiter, und danach setzt
  // `nodes.forEach(...position(from[index]))` alles in einem Schlag zurück.
  // In jedem dieser Frames misst die Kamera eine andere Wolke und zieht mit.
  //
  // Getrennt von `onGlideStart`, weil der Prerender eine ANDERE Frage stellt:
  // Er filmt die sichtbare Überblendung und darf die Rechenphase nicht
  // mitfilmen (sonst steht sein erster Frame still) — siehe den Kommentar bei
  // `umbauend` in createGraphView().
  onUmbauStart();

  // Label offsets are geometry too, and stale ones (sized for the old, denser
  // arrangement) would measurably mislead the separation pass.
  resetLabelOffsets(cy);
  // The whole computation runs at the placement size. It is also the only
  // stretch of this function where that is invisible: fcose's `proof` quality
  // blocks the main thread outright (see nextFrame() above), so the browser
  // never paints a frame with the discs at anything but their wall size.
  await atPlacementSizeAsync(async () => {
    await runLayout(cy, LAYOUT);
    settlePlacement(cy);
  });

  const to = new Map(nodes.map((node) => [node.id(), { ...node.position() }]));
  nodes.forEach((node, index) => node.position(from[index]));
  await nextFrame();
  onGlideStart();
  await runLayout(
    cy,
    { ...MIGRATION, animationDuration: duration, fit, positions: (node) => to.get(node.id()) },
    // Only the start: this fit's target must come from the placement, but the
    // glide itself is 2.5 painted seconds during which the discs hold their
    // size on the wall like everywhere else.
    (run) => atPlacementSize(run),
  );
}

export function createGraphView(
  container,
  { onPositions = () => {}, migrationDuration = MIGRATION_DURATION_MS } = {},
) {
  // Welcher Stil gilt, entscheidet das Theme — und zwar an einer CSS-Variablen,
  // die nur theme-f setzt. Nicht am ?theme=-Parameter: der steht im HTML, und
  // eine zweite Stelle, die dieselbe Wahl trifft, laeuft irgendwann auseinander.
  // Das Stylesheet ist beim Aufruf bereits geladen (projection.html wartet auf
  // das `load`-Event, bevor createGraphView laeuft).
  const schwarzplan = cssVar('--schwarzplan', '') === 'an';
  // --- Zeichenleistung bei bewegter Kamera (Birk, 2026-09-01 vor Ort) ------
  //
  // Der Touchscreen ruckelte beim Kameraschwenk und bei der Interaktion,
  // sobald viele Begriffe im Bild sind. GEMESSEN an derselben Szene (Stufe 60,
  // 138 Knoten, beide Bildschirme):
  //
  //                     GPU 3D    CPU brave
  //   Stillstand (fit)   10,6 %      49,4 %
  //   Kamerafahrt (pan)  61,4 %     144,4 %      -> 5,8x GPU, 2,9x CPU
  //
  // Die Dienste sind NICHT die Ursache: alle Python-Prozesse zusammen bleiben
  // bei ~12 %, unabhaengig davon, was die Anzeige tut. Das Zeichnen ist es.
  //
  // Cytoscape zeichnet bei jeder Kamerabewegung jeden Knoten und jede Kante
  // neu, mit voller Beschriftung. Die drei Schalter unten waren genau dafuer
  // gedacht; sie stehen in der Bibliothek alle auf `false` bzw. `undefined`
  // (im Bundle nachgesehen, nicht aus dem Gedaechtnis).
  //
  // Wie weit sie wirklich reichen, steht bei jedem einzelnen — und es ist in
  // `tests/test_projection_zeichenleistung.py` an der laufenden Wand
  // NACHGEMESSEN, nicht abgeleitet: waehrend einer Wischgeste fuellt sich
  // `textureCache` und die Kanten verschwinden, waehrend der automatischen
  // Fahrt bleibt der Cache leer und die Kanten bleiben stehen.
  //
  //   textureOnViewport    🔴 WIRKT BEI DER AUTOMATISCHEN FAHRT NICHT. Im
  //                        Bibliothekscode nachgelesen (nicht vermutet): die
  //                        Textur greift nur bei
  //                        `pinching || hoverData.dragging || swipePanning ||
  //                        data.wheelZooming` — also ausschliesslich bei
  //                        BENUTZERGESTEN. Die Fahrt setzt `cy.pan()` und
  //                        `cy.zoom()` direkt und loest keine dieser Flaggen
  //                        aus. Bleibt drin, weil sie beim Wischen und
  //                        Pinchen auf dem Touchscreen sehr wohl greift —
  //                        aber sie ist NICHT die Antwort auf das Ruckeln
  //                        der Kamerafahrt.
  //   hideEdgesOnViewport  Gleiche Einschraenkung, plus `cy.animated()`.
  //                        Auch das trifft hier nicht zu: camera.js faehrt
  //                        bewusst frame-fuer-frame OHNE `cy.animate()`
  //                        (siehe den Kommentar dort). Ebenfalls nur fuer
  //                        Gesten wirksam.
  //   pixelRatio           🔴 ENTFERNT am 2026-09-01, wenige Minuten nach dem
  //                        Einbau. Ich hatte ihn zweimal falsch beurteilt:
  //                        erst als grossen Hebel („auf HiDPI die vierfache
  //                        Pixelmenge"), dann nach einem Blick in die
  //                        Registry als wirkungslos, weil die
  //                        Windows-Skalierung auf 100 % steht.
  //
  //                        Beides falsch, und Birk hat es am BILD gesehen:
  //                        „die ganzen Graphen sehen sehr schlecht
  //                        aufgeloest aus, das sieht so aus wie Full HD, die
  //                        festen Texte sehen gut aus."
  //
  //                        Das ist die Signatur von `pixelRatio: 1`: der
  //                        HTML-Text daneben wird weiter in voller
  //                        Aufloesung gesetzt, nur Cytoscapes Zeichenflaeche
  //                        faellt auf ein Viertel der Pixel.
  //                        `devicePixelRatio` ist eben NICHT die
  //                        Desktop-Skalierung, und der Registry-Schluessel
  //                        sagt darueber nichts aus.
  //
  // 🔴 EHRLICHE BILANZ dieses Blocks: von drei Schaltern wirkte bei der
  // automatischen Fahrt genau EINER — und das war der, der das Bild kaputt
  // gemacht hat. Die gemessenen 61,4 % GPU im Dauerbetrieb `pan` ruehren
  // die beiden verbliebenen nicht an. Wer die senken will, braucht etwas
  // anderes, und das ist eine Entscheidung fuers Bild (weniger Knoten,
  // ruhigere Fahrt, andere Kantenform), kein Schalter.
  //
  // LEHRE: eine Bildwirkung ist am BILD zu pruefen, nicht an einem
  // Registry-Wert; und ob ein Schalter im eigenen Anwendungsfall ueberhaupt
  // greift, steht im Bibliothekscode — nachlesen kostet zehn Minuten, das
  // Zurueckrudern am Vorabend der Ausstellung kostet mehr.
  //
  // 🔴 Der 4K-Schirm ist die ANZEIGEFLAECHE (Birk, 2026-09-01: „das ist schon
  // der Screen, den alle sehen"). 3840x2160 sind gesetzt und nicht
  // verhandelbar — FullHD sieht sichtbar schlechter aus.
  //
  // 🔴 Abschaltbar per `?schnell=0`, damit am Ausstellungstag ohne neuen Build
  // zurueckgeschaltet werden kann, falls die Textur sichtbar unscharf wirkt.
  // Das Urteil faellt am Bild, nicht an der Zahl (Birk).
  const params = new URLSearchParams(window.location.search);
  const schnell = params.get('schnell') !== '0';
  const cy = cytoscape({
    container,
    style: schwarzplan ? styleSchwarzplan() : style(),
    wheelSensitivity: 0.2,
    textureOnViewport: schnell,
    hideEdgesOnViewport: schnell,
  });
  // fcose only packs disconnected components when this extension is
  // initialised on the instance (it calls cy.layoutUtilities('get') and falls
  // back to constructing one). Doing it here, once, is also the only place the
  // packing options can be set.
  if (cy.layoutUtilities) cy.layoutUtilities({ desiredAspectRatio: CANVAS_ASPECT, componentSpacing: 80 });

  // --- Portrait size on the wall (Birk, 2026-08-29 / 2026-08-30) ----------
  //
  // A single portrait must not fill the wall. That was the whole of the
  // complaint, and b803745 over-answered it by pinning the disc to a constant
  // size in rendered pixels — which also killed the gesture the touchscreen is
  // there for, a visitor pinching into a face until it fills the format.
  //
  // So `portraitSize` is a CEILING, and it applies only while the camera is
  // DRIVING (modes 'fit' and 'pan'):
  //
  //   driven:  width = min(placement size × S/120, S / zoom)
  //   manual:  width = whatever it was when the visitor took over
  //
  // (S = `portraitSize`. Der Maßstab S/120 kam am 2026-09-01 dazu — der Grund
  // steht ausführlich in `portraitWidth()`, hier nur die Formel.)
  //
  // Below the ceiling — anything but a nearly empty wall — the min() picks the
  // theme's own model size and the disc scales with the zoom exactly as it did
  // before b803745, so a crowded wall behaves as it always did. In 'manual'
  // the disc holds its MODEL width, which means the visitor's pinch magnifies
  // the picture they were looking at instead of re-proportioning it: at ten
  // times the zoom the face is ten times as big, on past the ceiling, up to
  // the full 1080px format.
  //
  // Freezing rather than releasing to the theme size is what makes entering
  // manual continuous. Leaving it is the camera's 1.5 s handover (384b928),
  // and the ceiling eases back on along that same cosine — see
  // camera.portraitCapBlend.
  //
  // The part that needs care is that this could easily become circular. The
  // camera sizes the zoom by fitting the net, and the fit measures the very
  // discs whose size then follows from that zoom. Left alone, that loop does
  // not converge: with a single portrait on the wall each fit multiplies the
  // zoom by roughly (canvas height - padding) / portraitSize — a factor of 8
  // at the default — and a handful of graph updates would blow the viewport
  // away entirely. It is not a stability problem to be damped, either: a lone
  // disc of bounded screen size can NEVER satisfy "fill the viewport", so
  // there is no fit for the fit to find.
  //
  // So the ceiling is strictly a DISPLAY property, applied on top of a
  // placement that knows nothing about it: every pass that computes or scores
  // geometry (fcose, settlePlacement, declutterLabels, countLabelOverlaps)
  // and every viewport fit runs at the theme's own --person-size, in model
  // units, exactly as before. A fit is therefore still a pure function of the
  // node positions, and every measurement this repo has ever taken of the
  // placement still means what it meant.
  //
  // The price b803745 carried is gone with the fixed size: at the 120px
  // default the ceiling only ever makes a disc SMALLER than the placement
  // assumed, so it cannot push portraits onto each other. (b803745's own
  // measurement, for the record: 108 touching portrait pairs of 1225 at the
  // 120px default on the seeded 50-person net, against 0 before it and 0
  // again now.)
  //
  // 🔴 Diese Zusage gilt seit dem 2026-09-01 nur noch BIS 120. Darüber
  // streckt der Regler die Modellgröße (S/120), und dann kann eine Scheibe
  // größer werden, als die Platzierung angenommen hat. Das ist kein
  // Versehen, sondern die Anforderung selbst — „der Regler muss nach oben
  // wirken" heißt „größer als das Layout annimmt". Beurteilt wird das am
  // Bild, vor Ort; die Zahl steht deshalb an einem Regler und nicht im Code.
  const placementPersonSize = Number(cssVar('--person-size', '96'));
  // The ring is not a constant but a RATIO of the disc: the themes tune the
  // two together (theme a 5 on 56, theme c 10 on 100), so a resized portrait
  // has to keep the proportion or it gets a frame from another drawing.
  const ringRatio = Number(cssVar('--ring-width', '5')) / placementPersonSize;
  let portraitSize = DEFAULT_PORTRAIT_SIZE;
  // The disc's model width as last written, and the width it holds while the
  // ceiling is off. `null` means "the visitor does not have it".
  let appliedWidth = 0;
  let freeWidth = null;
  // Re-entrant on purpose: settle() holds the placement size across a call
  // that fits the camera, which holds it again.
  let placementDepth = 0;

  /** The disc's model width at this zoom, under the current regime. */
  function portraitWidth(zoom) {
    // 🔴 DER REGLER IST DECKEL **UND** MASSSTAB (Birk, 2026-09-01 vor Ort:
    // „Der Portraitgrößen-Regler hat keinen Einfluss", bei Stellung 199 px —
    // also NICHT am Anschlag).
    //
    // Die reine Deckelung, die bis dahin hier stand:
    //
    //     Modellbreite = min(--person-size, S / zoom)
    //     gezeichnet   = min(--person-size × zoom, S)
    //
    // macht den Regler überall dort wirkungslos, wo die Grenze nicht bindet —
    // und das ist der NORMALFALL, nicht der Randfall. Gemessen an Birks Wand
    // (theme-f, --person-size 56, Zoom 1,55): gezeichnet 56 × 1,55 = 86,8 px,
    // und 199, 260, 400 und 700 ergaben alle dieselben 86,8 px. Die Grenze
    // anzuheben ändert daran nichts — das war mein erster, falscher Reflex.
    //
    // Sie ersatzlos zu streichen (mein zweiter, 7e6307c) aber auch nicht:
    // `S / zoom` hält die GEZEICHNETE Größe fest, die Scheibe wächst dann
    // beim Hineinzoomen überhaupt nicht mehr mit. Gemessen an dem Test, der
    // es aufdeckte (theme-a-Harness, 20 Personen): bei dreifachem Zoom stand
    // die Scheibe unverändert auf 120 px, statt von 47,9 px auf die 120er
    // Grenze zu STEIGEN. Vier Tests haben das gehalten, mit ihren Messwerten
    // vom 2026-08-30.
    //
    // Der Regler wirkt jetzt an BEIDEN Stellen derselben Formel:
    //
    //     gezeichnet = min(--person-size × zoom × S/120, S)
    //
    // Als Maßstab (S/120) streckt er die Modellgröße, die mit dem Zoom
    // mitwächst; als Deckel (S) begrenzt er weiterhin das Gezeichnete. Drei
    // Eigenschaften, und zusammen sind sie genau die Anforderung:
    //
    //   * Bei S = 120 ist die Formel ZAHLENGLEICH mit der alten. Alles, was
    //     am 2026-08-29/30 an der Wand gemessen wurde, gilt unverändert.
    //   * `gezeichnet ≤ S` gilt immer — „höchstens N px" bleibt wörtlich wahr,
    //     die Beschriftung am Regler stimmt weiter.
    //   * `gezeichnet` ist streng monoton in S, auf JEDER Wand und bei jedem
    //     Zoom. Genau das fehlte. NACHGEMESSEN auf der theme-a-Harness mit 20
    //     Personen, wo die Grenze nicht bindet (natürliche Scheibe 47,9 px):
    //     120 → 47,9 px, 199 → 79,5, 240 → 95,9, 260 → 103,8, 400 → 159,8,
    //     700 → 279,6. Mit reiner Deckelung: sechsmal 47,9 — der Regler
    //     bewegte dort nichts, und das war Birks ganzer Befund.
    //
    // Der Bezugspunkt 120 ist DEFAULT_PORTRAIT_SIZE und keine zweite Zahl:
    // „Reglerstellung = Vorgabe" heißt „Wand wie entworfen", und der Weg nach
    // beiden Seiten ist ein reiner Faktor darauf.
    const massstab = portraitSize / DEFAULT_PORTRAIT_SIZE;
    const gedeckelt = Math.min(placementPersonSize * massstab, portraitSize / zoom);
    // `camera` is assigned below this function and the very first call comes
    // from inside its constructor (a fit changes the zoom), so the fallback is
    // load-bearing, not defensive: until the camera exists the wall is in its
    // initial driven mode.
    const blend = camera ? camera.portraitCapBlend : 1;
    if (blend >= 1) {
      freeWidth = null;
      return gedeckelt;
    }
    if (freeWidth === null) freeWidth = appliedWidth > 0 ? appliedWidth : gedeckelt;
    if (blend <= 0) return freeWidth;
    // Geometric, like camera.js's lerpZoom and for the same reason: this is a
    // magnification travelling by a factor of ten, and the eye reads factors.
    //
    // 🔴 VIER STELLEN, EIN BEZEICHNER — wer ihn umbenennt, muss alle vier
    // mitnehmen. Hier stand bis 2026-09-01 `capped`, während der Commit
    // „Beide Regler wirken wieder" (7e6307c) die drei Stellen darüber schon
    // umbenannt hatte. Der Zweig wird NUR bei laufendem Handover betreten
    // (sonst kehrt `blend` bei 0 oder 1 vorher um), weshalb es keine
    // Testabdeckung gab, die es sofort gezeigt hätte.
    //
    // Der ReferenceError flog von hier durch `cy.zoom()` bis in `tick()`
    // hinauf — die Bildschleife der Wand starb dann 300 ms nach dem Beginn
    // JEDER Übergabefahrt. Also kein Ruckeln, sondern Stillstand.
    // Gemessen und abgesichert in `tests/test_camera_wand_haelt_durch.py`;
    // fünf Tests in `test_projection.py` und zwei in
    // `test_projection_schwarzplan.py` standen seither rot.
    return freeWidth * Math.pow(gedeckelt / freeWidth, blend);
  }

  function applyPortraitSize(force = false) {
    if (placementDepth > 0) return;
    const zoom = cy.zoom();
    if (!(zoom > 0)) return;
    const width = portraitWidth(zoom);
    if (!(width > 0)) return;
    if (!force && Math.abs(width - appliedWidth) < appliedWidth * PORTRAIT_ZOOM_TOLERANCE) return;
    appliedWidth = width;
    cy.batch(() => {
      const persons = cy.nodes('.person');
      // Entfernt statt geschrieben wird der Stil nur, wenn die gewollte Breite
      // GENAU die Modellbreite des Themas ist — dann tut die Kaskade dasselbe
      // umsonst, ein volles Netz zahlt gar keine Stilschreibvorgänge, und ein
      // späterer Themenwechsel greift normal durch (gleicher Grund wie bei
      // resetLabelOffsets).
      //
      // 🔴 Hier stand `width >= placementPersonSize`. Das war gleichbedeutend,
      // SOLANGE die Breite nach oben durch die Themengröße begrenzt war. Seit
      // der Regler auch nach oben wirkt, ist es das nicht mehr — und dann ist
      // es die zweite Hälfte von Birks Befund: bei Stellung 199 und theme-f
      // will die Scheibe 56 × 199/120 = 92,9 Modellpixel, das ist ≥ 56, der
      // Stil wäre entfernt worden und die Scheibe stünde wieder auf 56. Der
      // Regler wäre also selbst mit richtig gerechneter Breite stumm
      // geblieben.
      if (width === placementPersonSize) persons.removeStyle('width height border-width');
      else persons.style({ width, height: width, 'border-width': width * ringRatio });
    });
  }

  function enterPlacementSize() {
    // Removing the bypass (rather than writing the theme's number back) keeps
    // a later theme swap working through the normal cascade — same reason
    // resetLabelOffsets() removes rather than sets.
    if (placementDepth === 0) cy.nodes('.person').removeStyle('width height border-width');
    placementDepth += 1;
  }

  function leavePlacementSize() {
    placementDepth -= 1;
    if (placementDepth === 0) applyPortraitSize(true);
  }

  /** Run `fn` with the discs back at the placement's model size.
   *
   * Safe by construction for the synchronous callers, which is all of them
   * bar the migration: nothing awaits between removing the style bypass and
   * restoring it, so the browser never gets a frame in which to paint the
   * intermediate state.
   */
  function atPlacementSize(fn) {
    enterPlacementSize();
    try {
      return fn();
    } finally {
      leavePlacementSize();
    }
  }

  /** The same, for the one caller that has to await inside it. */
  async function atPlacementSizeAsync(fn) {
    enterPlacementSize();
    try {
      return await fn();
    } finally {
      leavePlacementSize();
    }
  }

  cy.on('zoom', () => applyPortraitSize());

  // `let`, not `const`, and read through a guard in portraitWidth(): the
  // Camera's constructor fits the viewport, which fires the zoom handler
  // above, which would otherwise reach a binding still in its temporal dead
  // zone and take the whole wall down on load.
  let camera = null;
  camera = new Camera(cy, {
    // Die Schriftgröße des Themes, in Modelleinheiten. Die Kamera braucht sie,
    // weil ihr ganzer Regler eine Aussage über GEZEICHNETE Pixel ist und
    // Cytoscape `font-size` mit dem Zoom skaliert: `labelSize × zoom` ist die
    // Schrift auf der Wand. Von HIER gereicht und nicht dort gelesen — diese
    // Datei liest `--label-size` ohnehin schon für den Stylesheet-Aufbau, und
    // ein zweiter Leseweg wäre eine zweite Stelle, an der ein Theme-Wechsel
    // hängenbleibt (theme-a hat 22, theme-c hat 44).
    labelSize: Number(cssVar('--label-size', '26')),
    fitWith: (fit) => atPlacementSize(fit),
    // A mode change IS a size change now (the ceiling applies to the driven
    // modes only), and it has to land in the same synchronous breath as the
    // mode rather than on the next animation frame — the pre-render and the
    // tests both read the wall straight after setMode().
    onModeChanged: () => applyPortraitSize(true),
  });
  let lastGraph = { nodes: [], edges: [], max_terms: DEFAULT_MAX_TERMS };
  // Ob die Kamera dem Traum folgt (Birk, 2026-08-31). Auf der Wand immer; in
  // einer Aufnahme, die eine definierte Bewegung zeigen soll, nicht — siehe
  // `aimCameraAtDream()` weiter unten, dort steht der Grund.
  //
  // HIER deklariert und nicht neben der Funktion, die es liest: `settle()`
  // ruft `aimCameraAtDream()` und ist selbst schon vor dieser Stelle definiert.
  // Ein `let` weiter unten läge für den ersten `render()`-Durchlauf in seiner
  // temporalen Todeszone — genau die Falle, die in dieser Datei bereits die
  // ganze Wand lahmgelegt hat (siehe `let camera = null` und der Kommentar
  // dort).
  let dreamCameraEnabled = true;
  let maxTerms = DEFAULT_MAX_TERMS;
  // Hysteresis (spec §7: measured 2026-08-29 -- raw churn is far above "less
  // than one change per interview", but the specific case the spec worries
  // about, a term vanishing and reappearing on the VERY NEXT interview, is
  // narrower and is what this targets). A term that made it onto the wall
  // stays for at least MIN_STAND_REVISIONS more graph updates, regardless of
  // rank, so a visitor's own just-said term does not get yanked away before
  // they have stepped back from the wall. `graphRevision` only advances on a
  // genuinely new graph (`update()`), never on a dial change alone -- an
  // operator lowering the cap is a deliberate override and must act at once,
  // not wait out another term's grace period.
  let graphRevision = 0;
  const standSince = new Map();
  // True while a migration is running (computation AND glide). Tests and the
  // pre-render wait on this instead of guessing a timeout.
  let layoutPending = false;
  // True only while the net is actually in flight — layoutPending covers the
  // computation before it too. Separate flags because they answer different
  // questions: "are the positions final yet" and "is a viewer watching motion
  // right now". The pre-render needs the second one to place its frames
  // inside the glide rather than inside the compute.
  // Zwei verschiedene Fragen, deshalb zwei Merker (2026-09-01).
  //
  // `umbauend` heißt „die Knoten bewegen sich, aus welchem Grund auch immer" —
  // das beginnt schon beim Rechnen (fcose schreibt Positionen, settlePlacement
  // schiebt nach, dann setzt ein forEach alles zurück) und ist die Frage, die
  // die KAMERA stellt: Sie darf in keinem dieser Frames die Wolke vermessen.
  //
  // `gliding` heißt eng „die sichtbare 2,5-Sekunden-Überblendung läuft" und
  // ist die Frage, die der PRERENDER stellt: Er hängt seine Aufnahme daran und
  // erwartet, dass ab diesem Moment jeder Frame ein anderes Bild ist.
  //
  // 🔴 Beides in EINEN Merker zu legen war ein Fehler und ist von
  // `test_a_sequence_covers_the_whole_glide_and_settles` gefangen worden: Mit
  // dem früheren Startpunkt filmte der Prerender die Rechenphase mit, in der
  // sich nichts bewegt — 10 verschiedene Bilder statt 11, also ein Standbild
  // am Anfang. Der Test hält fest „jeder Frame der Überblendung ist ein
  // anderes Bild, sonst ist ein Schnitt drin"; diese Aussage bleibt richtig,
  // nur mein Merker war der falsche.
  let umbauend = false;
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
    const keepTermIds = new Set(
      [...standSince.keys()].filter((id) => graphRevision - standSince.get(id) < MIN_STAND_REVISIONS),
    );
    const view = visibleGraph(lastGraph, maxTerms, keepTermIds);
    const wanted = new Set(view.nodes.map((n) => n.id).concat(view.edges.map((e) => e.id)));
    const present = cy.elements().map((el) => el.id());

    // Bookkeeping for the grace list above: a term newly on the wall starts
    // its clock, one that dropped off (cap, hide, or deletion -- `view`
    // already excludes all three) loses its place in it.
    const visibleTermIds = new Set(view.nodes.filter((n) => n.type === 'term').map((n) => n.id));
    for (const id of visibleTermIds) if (!standSince.has(id)) standSince.set(id, graphRevision);
    for (const id of [...standSince.keys()]) if (!visibleTermIds.has(id)) standSince.delete(id);

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

    // Die Hervorhebung der Traumbegriffe muss auch an Knoten nachgezogen
    // werden, die schon da sind (Birk, 2026-08-30). `toCytoscape` setzt die
    // Klasse nur beim Anlegen — ohne diese Schleife bliebe die Auswahl des
    // ERSTEN Traums den ganzen Tag stehen, während die Bilder längst aus
    // anderen Begriffen entstehen. Genau das wäre schlimmer als keine
    // Hervorhebung: eine Anzeige, die etwas Falsches behauptet.
    for (const node of view.nodes) {
      if (node.type !== 'term') continue;
      const element = cy.$id(node.id);
      if (element.length === 0) continue;
      const soll = node.in_dream === true;
      const rolle = soll ? `dream-${node.dream_role || 'anchor'}` : '';
      if (soll !== element.hasClass('in-dream') || (soll && !element.hasClass(rolle))) {
        element.toggleClass('in-dream', soll);
        // Die alte Rollenklasse muss WEG, nicht nur die neue dazu: Ein
        // Begriff, der vom Anker zum Nachbarn wird, trüge sonst beide und
        // Cytoscape entschiede nach Regelreihenfolge — die Wand zeigte eine
        // Farbe, die nichts mehr bedeutet.
        for (const r of ['dream-anchor', 'dream-neighbour', 'dream-recent']) {
          element.toggleClass(r, r === rolle);
        }
        element.data('in_dream', soll);
        element.data('dream_role', node.dream_role || '');
      }
    }

    // Aus demselben Grund muss ein NACHGEREICHTES Portrait nachgezogen werden
    // (seit 2026-09-01, kg.core `_portrait`): Wer per Mikrofonschalter ohne
    // Foto begonnen hat und sich mitten im Gespräch doch fotografieren lässt,
    // steht als leere Scheibe längst auf der Wand. `toCytoscape` setzt
    // `portrait` nur beim ANLEGEN — ohne diese Schleife bliebe die Scheibe
    // leer bis zum nächsten Neuladen der Seite, mit dem Bild in der Datenbank
    // und nicht im Bild.
    for (const node of view.nodes) {
      if (node.type !== 'person') continue;
      const element = cy.$id(node.id);
      if (element.length === 0) continue;
      const portrait = node.portrait || '';
      if (element.data('portrait') !== portrait) element.data('portrait', portrait);
    }

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

    // Both halves are placement work: settleLabels() measures label boxes
    // against person discs, and onGraphChanged() may fit the camera.
    const settle = () =>
      atPlacementSize(() => {
        labelOverlapStats = settleLabels(cy);
        aimCameraAtDream();
        camera.onGraphChanged();
      });

    if (!changed || restoring) {
      settle();
      layoutPending = false;
      return;
    }

    layoutPending = true;
    migration = migrate(cy, {
      fit: camera.mode === 'fit',
      duration: migrationDuration,
      onUmbauStart: () => {
        umbauend = true;
      },
      onGlideStart: () => {
        gliding = true;
      },
      atPlacementSize,
      atPlacementSizeAsync,
    })
      .catch((error) => console.warn('layout migration failed', error))
      .then(() => {
        migration = null;
        umbauend = false;
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

  /** Die Knoten, aus denen das Bild gerade entsteht — Ausschnitt für die
   * Kamera (Birk, 2026-08-31).
   *
   * Die fünf Begriffe mit `.in-dream` PLUS die Personen, die sie genannt
   * haben. Gemessen am Replay-Stand: die fünf allein ergäben Zoom 1.45 (1,6x
   * enger als die kalibrierte Wand), mit ihren 18 Personen 1.07 — und die
   * Portraits sind die andere Hälfte der Aussage, weil sie zeigen, WER das
   * Material geliefert hat.
   *
   * `.neighborhood()` und nicht `.closedNeighborhood()`: beide existieren im
   * vendorierten Bundle 3.30.2 (geprüft), aber das Ergebnis wird ohnehin mit
   * den Traumknoten vereinigt, und `neighborhood()` macht sichtbar, dass hier
   * die PERSONEN dazukommen und nicht versehentlich weitere Begriffe. */
  function dreamNodes() {
    const dream = cy.nodes('.in-dream');
    if (dream.empty()) return null;
    return dream.union(dream.neighborhood().nodes('.person'));
  }

  /** Der Kamera sagen, wo das aktuelle Bild herkommt. Ein No-op, solange kein
   * Traum markiert ist — dann verhält sich die Wand wie vorher.
   *
   * Abschaltbar über `setDreamCamera(false)`, und das ist keine Bequemlichkeit
   * für Tests: `sim/prerender.py` filmt EINE Bewegung und braucht danach ein
   * Standbild. Diese Funktion läuft aber in `settle()`, also bei JEDER
   * Migration — auch bei einer rein mechanischen wie einem Dial-Wechsel, den
   * der Prerender selbst auslöst. Ein `clearDream()` vor der Aufnahme reicht
   * deshalb nicht: die Migration, die gefilmt wird, setzt die Kopplung mitten
   * im Film neu (gemessen 2026-08-31 — nach der Migration stand `dream: 23,
   * handover: läuft`, obwohl unmittelbar davor beides gelöscht war).
   *
   * Ein Schalter und nicht ein wiederholtes Löschen, weil „diese Aufnahme
   * erzählt nicht, sie zeigt" eine Aussage über den ganzen Lauf ist und nicht
   * über einen Zeitpunkt. Die Wand schaltet ihn nie. */
  function aimCameraAtDream() {
    if (!dreamCameraEnabled) return;
    const nodes = dreamNodes();
    if (!nodes || nodes.empty()) return;
    camera.focusDream(nodes);
  }

  let last = performance.now();
  function tick(now) {
    // Während die Knoten umziehen, fährt die Kamera nicht.
    //
    // 🔴 Gemessen 2026-09-01 (Birk, Punkt 7): `migrate()` setzt alle Knoten in
    // EINEM Schritt auf ihre alten Plätze zurück, bevor es sie 2,5 s lang an
    // die neuen gleiten lässt (`nodes.forEach(node.position(from[index]))`).
    // Die Kamera weiß davon nichts, misst in genau diesem Frame die Wolke neu
    // und zieht mit — gemessen als Pan-Sprung von über 250 Modellpixeln in
    // einem Frame, gegen einen Median unter 1 px.
    //
    // Sie steht dabei nicht still: Der Handover behält Vorrang (er IST eine
    // gewollte Bewegung und läuft nur 1,5 s), und die Standzeit läuft weiter,
    // damit die Fahrt nach dem Umzug nicht sofort losfährt. Ausgesetzt wird
    // allein das Vermessen und Fahren — das Bild bleibt stehen, während sich
    // der Graph sortiert, und nimmt die Fahrt danach weich wieder auf.
    if (umbauend && !camera.handoverActive) {
      last = now;
      applyPortraitSize();
      requestAnimationFrame(tick);
      return;
    }
    camera.step((now - last) / 1000);
    last = now;
    // After the camera, because the handover moves the ceiling as well as the
    // viewport and the discs have to follow it frame by frame. Cheap when
    // nothing is travelling: the target width is unchanged and the tolerance
    // above turns the call into a zoom read and a comparison.
    applyPortraitSize();
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
    /** The largest a portrait may get on the wall in the driven camera modes,
     * in rendered pixels. Not the size it IS: below the ceiling a disc is the
     * theme's model size times the zoom times S/120 — it still grows with the
     * zoom like everything else — and in 'manual' the ceiling does not apply
     * at all. Der Faktor S/120 ist der Teil, mit dem der Regler auch dort
     * wirkt, wo die Grenze nicht bindet (2026-09-01, siehe portraitWidth). */
    get portraitSize() {
      return portraitSize;
    },
    /** The model size the PLACEMENT reasons in — the theme's --person-size.
     * Reported by the pre-render alongside the size that reaches the wall,
     * which is this number times the zoom unless the ceiling cuts it short. */
    get placementPersonSize() {
      return placementPersonSize;
    },
    update(graph, value) {
      graphRevision += 1;
      lastGraph = graph;
      if (value !== undefined) maxTerms = value;
      else if (graph.max_terms) maxTerms = graph.max_terms;
      render();
    },
    /** Ob die Kamera dem Traum folgt. Die Wand lässt das an; abgeschaltet wird
     * es nur von Werkzeugen, die eine definierte statt einer erzählenden
     * Aufnahme brauchen (`sim/prerender.py`) — der Grund steht bei
     * `aimCameraAtDream()`. Schaltet man es ab, wird auch das gemerkte Gebiet
     * samt laufender Fahrt verworfen: sonst bliebe die Kopplung, die gerade
     * gilt, bis zum Ende der Aufnahme in Kraft. */
    setDreamCamera(enabled) {
      dreamCameraEnabled = enabled !== false;
      if (!dreamCameraEnabled) camera.clearDream();
    },
    setMaxTerms(value) {
      maxTerms = value;
      // The operator's dial is a deliberate, immediate override -- it must
      // not wait out another term's grace period (see the hysteresis comment
      // above `graphRevision`).
      standSince.clear();
      render();
    },
    /** How large a portrait may get on the wall in the driven modes, in
     * rendered pixels. Takes effect at once, like the operator's other dials.
     * A value that is not a usable size is ignored rather than thrown on:
     * this runs an unattended wall, and a bad state push must never stop it
     * rendering. */
    setPortraitSize(pixels) {
      const size = Number(pixels);
      if (!(size > 0)) return;
      portraitSize = size;
      applyPortraitSize(true);
    },
    // Both of these weigh label boxes against the person discs, so they run at
    // the placement's model size rather than at what the discs are drawn at
    // (see the portrait-size block above). resetLabelOffsets() below does not:
    // it touches nothing but the labels' own margins.
    declutterLabels() {
      atPlacementSize(() => declutterLabels(cy));
    },
    resetLabelOffsets() {
      resetLabelOffsets(cy);
    },
    labelOverlaps() {
      return atPlacementSize(() => countLabelOverlaps(cy));
    },
  };
}
