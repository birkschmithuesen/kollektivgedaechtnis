// Pure display logic. The store keeps everything; the wall shows a view of it.
// The term-count dial is a display filter: instant, reversible, lossless.

// The selection rule (spec 2026-08-29, shared with kg2/weighting.py's gliding
// budget): shared terms first, filled with the newest single mentions. If the
// shared terms alone exceed the cap, they are capped too — most-mentioned
// first. One ranking covers both cases: sort by mentions, then recency, and
// cut at the cap.
function rankTerms(terms) {
  return [...terms].sort((a, b) => {
    const byMentions = (b.mentions || 0) - (a.mentions || 0);
    if (byMentions !== 0) return byMentions;
    const byRecency = (b.created_at || 0) - (a.created_at || 0);
    if (byRecency !== 0) return byRecency;
    return a.label < b.label ? -1 : a.label > b.label ? 1 : 0;
  });
}

/** The term ids the cap alone would show, PLUS whatever `keepIds` (the
 * caller's hysteresis grace list, projection.js's job to decide) still
 * exists as a non-hidden term.
 *
 * Deliberately additive, not a swap: the alternative -- a grace id displacing
 * whoever it would naturally lose a slot to -- can only "protect" a stale
 * entry by blocking a BRAND NEW one, and the newest single mention is
 * supposed to appear the moment it is said (spec 2026-08-29 §3, "damit die
 * gerade interviewte Person ihren Begriff auf der Wand findet"). So a grace
 * hold can push the visible count slightly past the nominal cap. That
 * overflow is bounded, not runaway: it can only ever be as large as (typical
 * exits per graph update) x (the grace window), and it decays back to the
 * cap on its own once each grace period lapses. Measured 2026-08-29
 * (`sim.dream_calibrate.prefix_graph`, spec §7): roughly 2-3 exits per
 * interview at these caps, so a 3-update grace window overshoots by single
 * digits at worst -- close enough to the next cap tier up that the spec's own
 * legibility table (§2) already covers it. A grace id that no longer exists
 * or is hidden is simply skipped, never resurrected. */
export function selectVisibleTermIds(terms, maxTerms, keepIds = new Set()) {
  const cap = Math.max(1, Number(maxTerms) || 1);
  const candidates = terms.filter((term) => !term.hidden);
  const ranked = rankTerms(candidates);
  const ids = new Set(ranked.slice(0, cap).map((term) => term.id));
  const eligible = new Set(candidates.map((term) => term.id));
  for (const id of keepIds) {
    if (eligible.has(id)) ids.add(id);
  }
  return ids;
}

export function visibleGraph(graph, maxTerms, keepTermIds = new Set()) {
  const terms = graph.nodes.filter((node) => node.type === 'term');
  const visibleTermIds = selectVisibleTermIds(terms, maxTerms, keepTermIds);
  const nodes = graph.nodes.filter((node) => {
    if (node.hidden) return false;
    if (node.type === 'term') return visibleTermIds.has(node.id);
    return true;
  });
  const visibleIds = new Set(nodes.map((node) => node.id));
  const edges = graph.edges.filter(
    (edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target),
  );
  return { nodes, edges };
}

export function toCytoscape(view) {
  const elements = [];
  for (const node of view.nodes) {
    const element = {
      data: {
        id: node.id,
        type: node.type,
        label: node.type === 'term' ? node.label : '',
        portrait: node.portrait || '',
        mentions: node.mentions || 0,
        // Ob dieser Begriff gerade ins Bild geht (kg/export.py rechnet das
        // aus, Birk 2026-08-30). Als data-Feld UND als Klasse: die Klasse
        // stylt, das Feld überlebt einen Klassenwechsel und lässt sich
        // abfragen, ohne den Stil zu lesen.
        in_dream: node.in_dream === true,
      },
      classes: node.in_dream === true ? `${node.type} in-dream` : node.type,
    };
    if (node.x !== null && node.x !== undefined && node.y !== null && node.y !== undefined) {
      element.position = { x: node.x, y: node.y };
    }
    elements.push(element);
  }
  for (const edge of view.edges) {
    elements.push({
      data: { id: edge.id, source: edge.source, target: edge.target },
      classes: 'link',
    });
  }
  return elements;
}

export function newNodeIds(previousIds, view) {
  const known = new Set(previousIds);
  return view.nodes.map((node) => node.id).filter((id) => !known.has(id));
}
