// Quote on touch (design spec §10.2 + parked nice-to-have, now built).
//
// The spec deliberately keeps quotes OFF the default display: "a quote would
// only make the graph more chaotic" (Birk, 2026-08-12). Person nodes carry a
// face, term nodes carry text, and that is the whole vocabulary of the wall.
//
// This does not change that. The wall stays quiet until somebody asks: tap a
// portrait, the quote fades in; tap anywhere else, or wait, and it is gone
// again. So the resting state is exactly the one the spec approved, and the
// quote is a reward for curiosity rather than permanent furniture.
//
// Auto-hide matters more than it looks: a visitor who taps a face and walks
// away must not leave that person's quote burnt onto an exhibition screen for
// the next twenty minutes.

const VISIBLE_MS = 12000;

export function attachQuoteOverlay(
  view,
  {
    container = document.body,
    visibleMs = VISIBLE_MS,
    setTimer = (fn, ms) => window.setTimeout(fn, ms),
    clearTimer = (id) => window.clearTimeout(id),
  } = {},
) {
  const panel = document.createElement('figure');
  panel.className = 'quote-overlay';
  panel.id = 'quote-overlay';
  panel.hidden = true;

  const text = document.createElement('blockquote');
  text.className = 'quote-text';
  panel.appendChild(text);
  container.appendChild(panel);

  // person_id -> [quote, ...]. Rebuilt on every graph push: quotes arrive in
  // the same payload as the nodes, so they can never be staler than the wall.
  let byPerson = new Map();
  let timer = null;
  let shownFor = null;

  function hide() {
    if (timer !== null) clearTimer(timer);
    timer = null;
    shownFor = null;
    panel.hidden = true;
    panel.classList.remove('visible');
  }

  function show(personId) {
    const quotes = byPerson.get(personId);
    if (!quotes || quotes.length === 0) {
      // A person whose extraction failed, or who said nothing quotable. Better
      // to do nothing than to open an empty panel that looks broken.
      hide();
      return false;
    }
    // Several quotes: pick one per tap rather than showing a wall of text.
    // Tapping the same face again cycles to the next — the only "more" gesture
    // on a surface with no scrollbars.
    const index = shownFor === personId ? (panel.dataset.index | 0) + 1 : 0;
    panel.dataset.index = String(index % quotes.length);
    text.textContent = quotes[index % quotes.length];
    shownFor = personId;
    panel.hidden = false;
    panel.classList.add('visible');
    if (timer !== null) clearTimer(timer);
    timer = setTimer(hide, visibleMs);
    return true;
  }

  view.cy.on('tap', 'node.person', (event) => show(event.target.id()));
  // Background tap = "done reading".
  //
  // Do NOT rewrite this as `cy.on('tap', 'core', …)`. Cytoscape's 'core'
  // selector fires on the exact OPPOSITE of what its name suggests — measured
  // 2026-08-26 on this vendored build by logging both bindings:
  //   node click       -> ['node.person', 'core', 'any:node']
  //   background click -> ['any:core']
  // so a 'core'-bound listener runs on every NODE tap and never on a
  // background tap. Bound that way, this hide() ran immediately after the
  // show() above and the quote never appeared. The unfiltered binding plus an
  // explicit target check is the form that actually distinguishes the two.
  view.cy.on('tap', (event) => {
    if (event.target === view.cy) hide();
  });

  return {
    element: panel,
    /** Called with each graph push so the quote store tracks the wall. */
    setGraph(graph) {
      const next = new Map();
      for (const quote of graph.quotes || []) {
        if (!next.has(quote.person_id)) next.set(quote.person_id, []);
        next.get(quote.person_id).push(quote.text);
      }
      byPerson = next;
      // The person on screen may have just been hidden by the operator or
      // filtered away; a quote outliving its node would be a ghost.
      if (shownFor && !next.has(shownFor)) hide();
    },
    show,
    hide,
    get visible() {
      return !panel.hidden;
    },
    get personId() {
      return shownFor;
    },
  };
}
