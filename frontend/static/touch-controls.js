// The two controls a VISITOR may touch on surface A. Deliberately not the
// operator UI: no hiding, no camera modes, no zoom slider — two things, both
// forgiving, both undoable by pressing them again.
//
// Why these two: after a minute of pinching around, a visitor is lost, and the
// next visitor inherits a random close-up of one node. "Übersicht" is the way
// out of that with one press. The density menu is the only control that changes
// what the wall MEANS rather than where it points, and Birk wants it reachable
// at the screen (2026-08-26) rather than only on the operator laptop.
//
// Density DOES post to the server — unlike the camera mode. That is intentional
// and is the difference between the two controls: density is a statement about
// the exhibit ("show what at least N people share") and should hold everywhere,
// including surface C in the plenary room. Where the camera points is a local
// concern; what the wall shows is not.

const DENSITY_LABELS = [
  { value: 1, label: 'alle Begriffe' },
  { value: 2, label: 'geteilt (ab 2)' },
  { value: 3, label: 'häufig (ab 3)' },
];

export function createTouchControls(
  container,
  { onOverview, onDensity, initialDensity = 1, labels = DENSITY_LABELS } = {},
) {
  const bar = document.createElement('div');
  bar.className = 'touch-controls';
  bar.id = 'touch-controls';

  const overview = document.createElement('button');
  overview.id = 'touch-overview';
  overview.className = 'touch-button';
  // Not "Zoom 1x": the visitor is not thinking in zoom factors, they are
  // thinking "show me everything again".
  overview.textContent = 'Übersicht';
  overview.addEventListener('click', () => onOverview && onOverview());
  bar.appendChild(overview);

  const group = document.createElement('div');
  group.className = 'touch-density';
  group.id = 'touch-density';

  const buttons = labels.map((entry) => {
    const button = document.createElement('button');
    button.className = 'touch-button density';
    button.dataset.value = String(entry.value);

    const caption = document.createElement('span');
    caption.className = 'density-label';
    caption.textContent = entry.label;
    button.appendChild(caption);

    // How many terms this step would actually show. Without it a visitor
    // pressing "häufig" early in the day gets a blank wall and concludes the
    // button is broken — which is exactly what happened on 2026-08-26 with
    // eight interviews in and nothing yet shared by three people. The count
    // turns a dead-looking control into an honest statement about the graph.
    const badge = document.createElement('span');
    badge.className = 'density-count';
    badge.textContent = '';
    button.appendChild(badge);

    button.addEventListener('click', () => {
      setActive(entry.value);
      if (onDensity) onDensity(entry.value);
    });
    group.appendChild(button);
    return button;
  });

  function setActive(value) {
    buttons.forEach((b) => b.classList.toggle('active', Number(b.dataset.value) === Number(value)));
  }

  function setCounts(graph) {
    const terms = (graph.nodes || []).filter((n) => n.type === 'term' && !n.hidden);
    buttons.forEach((b) => {
      const threshold = Number(b.dataset.value);
      const count = terms.filter((t) => (t.mentions || 0) >= threshold).length;
      b.querySelector('.density-count').textContent = String(count);
      // A step with nothing behind it stays pressable — the wall may grow into
      // it a minute later — but says so rather than pretending.
      b.classList.toggle('empty', count === 0);
    });
  }

  setActive(initialDensity);
  bar.appendChild(group);
  container.appendChild(bar);

  return {
    element: bar,
    /** Reflect a density that arrived from the server (operator changed it). */
    setDensity(value) {
      setActive(value);
    },
    /** Refresh the per-step term counts from a graph push. */
    setGraph(graph) {
      setCounts(graph);
    },
  };
}
