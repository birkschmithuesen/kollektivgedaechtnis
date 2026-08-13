// Pure display logic. The store keeps everything; the wall shows a view of it.
// The minimum-mention dial is a display filter: instant, reversible, lossless.

export function visibleGraph(graph, minMentions) {
  const threshold = Math.max(1, Number(minMentions) || 1);
  const nodes = graph.nodes.filter((node) => {
    if (node.hidden) return false;
    if (node.type === 'term') return (node.mentions || 0) >= threshold;
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
      },
      classes: node.type,
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
