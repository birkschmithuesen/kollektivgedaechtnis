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
        'text-margin-y': 6,
        'text-wrap': 'wrap',
        'text-max-width': '220px',
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

const LAYOUT = {
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

export function createGraphView(container, { onPositions = () => {} } = {}) {
  const cy = cytoscape({ container, style: style(), wheelSensitivity: 0.2 });
  const camera = new Camera(cy);
  let lastGraph = { nodes: [], edges: [], min_mentions: 1 };
  let minMentions = 1;
  // True while an animated layout is running. Tests and the pre-render wait on
  // this instead of guessing a timeout; positions land only at `layoutstop`.
  let layoutPending = false;

  function render() {
    const view = visibleGraph(lastGraph, minMentions);
    const wanted = new Set(view.nodes.map((n) => n.id).concat(view.edges.map((e) => e.id)));
    const present = cy.elements().map((el) => el.id());

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
    const fresh = newNodeIds(present, view).filter((id) => !placed.has(id));
    const toAdd = toCytoscape(view).filter((el) => cy.$id(el.data.id).length === 0);
    if (toAdd.length) cy.add(toAdd);

    if (fresh.length) {
      // Seed each new node next to a neighbour it already has, so the layout
      // starts from a sensible place instead of the origin. The offset is
      // derived from the index (golden angle), not random: two pre-render runs
      // over the same graph must produce the same picture.
      fresh.forEach((id, index) => {
        const node = cy.$id(id);
        if (node.position('x') || node.position('y')) return;
        const anchor = node.neighborhood('node').filter((n) => !fresh.includes(n.id()))[0];
        const base = anchor ? anchor.position() : { x: 0, y: 0 };
        const angle = index * 2.39996;
        node.position({ x: base.x + Math.cos(angle) * 140, y: base.y + Math.sin(angle) * 140 });
      });
      // Existing nodes are locked: the net must never re-shuffle (spec 11).
      const existing = cy.nodes().filter((n) => !fresh.includes(n.id()));
      existing.lock();
      const layout = cy.layout(LAYOUT);
      layoutPending = true;
      layout.one('layoutstop', () => {
        existing.unlock();
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
  };
}
