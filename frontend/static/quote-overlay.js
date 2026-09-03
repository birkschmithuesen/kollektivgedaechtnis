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
    //: Die Karte aufbauen, aber nicht auf Tipps hoeren — siehe unten.
    stumm = false,
  } = {},
) {
  const panel = document.createElement('figure');
  panel.className = 'quote-overlay';
  panel.id = 'quote-overlay';
  panel.hidden = true;

  // The name goes ABOVE the quote and in its OWN element, never concatenated
  // into the blockquote's text: the quotation marks are drawn by CSS
  // (`.quote-text::before`/`::after` in base.css), so a name inside that text
  // would end up inside the quotation marks — as if the person had said their
  // own name. A <figcaption> because that is exactly what this figure needs:
  // the caption naming who is speaking.
  const name = document.createElement('figcaption');
  name.className = 'quote-name';
  name.hidden = true;
  panel.appendChild(name);

  const text = document.createElement('blockquote');
  text.className = 'quote-text';
  panel.appendChild(text);

  // 🔴 Der zweite Fall: ein Tipp auf einen BEGRIFF (Birk, 2026-09-02).
  //
  // „Wenn du pro Begriff eine kleine Erklärung machst, wie dieses Wort gemeint
  // ist … könnte beim Anklicken angezeigt werden, ähnlich wie die Zitate bei
  // Personen. Bei Begriffen, die von mehreren Menschen genannt wurden, der
  // jeweilige Kontext pro Person mit dem Namen."
  //
  // Eine EIGENE Liste und nicht dasselbe Blockquote: Ein Zitat ist EIN Satz
  // einer Person, eine Begriffserklärung sind mehrere Stellen mehrerer
  // Menschen. In ein Blockquote gepresst stünden die Anführungszeichen, die
  // `.quote-text::before/::after` zeichnet, einmal um alle zusammen — als
  // hätte eine Person das am Stück gesagt.
  const belegListe = document.createElement('ul');
  belegListe.className = 'quote-belege';
  belegListe.hidden = true;
  panel.appendChild(belegListe);

  container.appendChild(panel);

  // person_id -> quote text, at most one per person. Rebuilt on every graph
  // push: quotes arrive in the same payload as the nodes, so they can never
  // be staler than the wall.
  let byPerson = new Map();
  // person_id -> name, rebuilt from the person nodes on the same push and for
  // the same reason. Most persons have none: nobody introduced themselves, or
  // the operator cleared a misheard one. Then the entry is simply absent and
  // the panel shows the quote alone, exactly as it did before this existed.
  let namesByPerson = new Map();
  //: term_id -> [{ person_id, evidence }], aus den KANTEN. Je Person eine
  //: eigene Stelle: derselbe Begriff kann bei zwei Menschen zwei Dinge
  //: meinen, und genau das soll man sehen können.
  let belegeByTerm = new Map();
  let timer = null;
  let shownFor = null;

  function hide() {
    if (timer !== null) clearTimer(timer);
    timer = null;
    shownFor = null;
    panel.hidden = true;
    panel.classList.remove('visible');
    belegListe.hidden = true;
    belegListe.replaceChildren();
  }

  function showName(personId) {
    const person = namesByPerson.get(personId) || '';
    name.textContent = person;
    // Empty AND hidden, not just empty: an empty caption still occupies a line
    // box and would open a gap over the quote of every person who never said
    // their name — which is most of them.
    name.hidden = person === '';
  }

  function show(personId) {
    const quote = byPerson.get(personId);
    if (quote === undefined) {
      // A person whose extraction failed, or who said nothing quotable. Better
      // to do nothing than to open an empty panel that looks broken.
      hide();
      return false;
    }
    text.textContent = quote;
    showName(personId);
    shownFor = personId;
    panel.hidden = false;
    panel.classList.add('visible');
    if (timer !== null) clearTimer(timer);
    timer = setTimer(hide, visibleMs);
    return true;
  }

  /** Die Belegstellen eines Begriffs, eine Zeile je Person. */
  function showTerm(termId) {
    const eintraege = (belegeByTerm.get(termId) || []).filter((e) => e.evidence);
    if (!eintraege.length) {
      // Wie bei einer Person ohne Zitat: lieber nichts als eine Karte, die
      // kaputt aussieht. Kanten von vor dem 2026-09-02 haben keine Stelle.
      hide();
      return false;
    }
    text.textContent = '';
    name.hidden = true;
    belegListe.replaceChildren();
    for (const eintrag of eintraege) {
      const zeile = document.createElement('li');
      const wer = namesByPerson.get(eintrag.person_id);
      if (wer) {
        const marke = document.createElement('span');
        marke.className = 'quote-beleg-name';
        marke.textContent = wer;
        zeile.appendChild(marke);
      }
      const was = document.createElement('span');
      was.className = 'quote-beleg-text';
      was.textContent = eintrag.evidence;
      zeile.appendChild(was);
      belegListe.appendChild(zeile);
    }
    belegListe.hidden = false;
    shownFor = termId;
    panel.hidden = false;
    panel.classList.add('visible');
    if (timer !== null) clearTimer(timer);
    timer = setTimer(hide, visibleMs);
    return true;
  }

  // 🔴 NUR WENN NICHT STUMM — und diese Bedingung fehlte zuerst (gefunden am
  // gerenderten Bild, 2026-09-02): Die Option war deklariert und wurde von
  // projection.html auch gesetzt, aber nirgends gelesen. Die Karte hoerte also
  // weiter mit, und beim Antippen standen BEIDE da: die Tafel rechts und die
  // Karte quer ueber dem Netz, auf demselben hervorgehobenen Knoten. Genau der
  // Zustand, gegen den die Tafel gebaut wurde.
  //
  // Der Hintergrund-Tipp unten bleibt in jedem Fall gebunden: Blendet der
  // Zyklus von sich aus ein Zitat ein, muss man es auch wegtippen koennen.
  if (!stumm) {
    view.cy.on('tap', 'node.person', (event) => {
      belegListe.hidden = true;
      belegListe.replaceChildren();
      show(event.target.id());
    });
    view.cy.on('tap', 'node.term', (event) => showTerm(event.target.id()));
  }
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

  // 🔴 Die Karte nimmt seit 2026-09-02 Zeigereignisse an, damit man in ihr
  // ROLLEN kann (Birk: „ein klick auf den graphen dahinter bringt zurück, aber
  // ein scrollen in der karte scrollt eben"). Damit faengt sie aber auch
  // Tipps ab, die dem Graphen galten — genau das, was `pointer-events: none`
  // vorher verhindert hat.
  //
  // Deshalb hier die Unterscheidung, die das CSS nicht treffen kann: Ein
  // TIPP auf die Karte schliesst sie, als waere er hinter ihr gelandet. Ein
  // ZIEHEN laesst sie in Ruhe und rollt. Gemessen wird ueber die zurueckgelegte
  // Strecke, nicht ueber die Zeit — ein langsamer Tipp ist ein Tipp, ein
  // schnelles Wischen ist keiner.
  const TIPP_WEG_PX = 12;
  let start = null;
  panel.addEventListener('pointerdown', (e) => {
    start = { x: e.clientX, y: e.clientY };
  });
  panel.addEventListener('pointerup', (e) => {
    if (!start) return;
    const weg = Math.hypot(e.clientX - start.x, e.clientY - start.y);
    start = null;
    if (weg <= TIPP_WEG_PX) hide();
  });

  return {
    element: panel,
    /** Called with each graph push so the quote store tracks the wall. */
    setGraph(graph) {
      const next = new Map();
      for (const quote of graph.quotes || []) {
        // Exactly one quote per person now; kg/export.py already enforces
        // this, but an older graph.json snapshot could still carry more —
        // keep the first, the same compromise export.py makes for it.
        if (!next.has(quote.person_id)) next.set(quote.person_id, quote.text);
      }
      byPerson = next;

      const nextNames = new Map();
      for (const node of graph.nodes || []) {
        if (node.type !== 'person') continue;
        const person = (node.name || '').trim();
        if (person) nextNames.set(node.id, person);
      }
      namesByPerson = nextNames;

      // Die Belegstellen kommen an den KANTEN mit (kg/export.py) — nur dort
      // steht, WER einen Begriff wie gemeint hat.
      const nextBelege = new Map();
      for (const edge of graph.edges || []) {
        if (!edge || !edge.evidence) continue;
        const liste = nextBelege.get(edge.target) || [];
        liste.push({ person_id: edge.source, evidence: edge.evidence });
        nextBelege.set(edge.target, liste);
      }
      belegeByTerm = nextBelege;
      // A name corrected by the operator has to reach a quote that is on the
      // wall right now: the correction is usually made BECAUSE the wrong name
      // is being read off the screen.
      if (shownFor) showName(shownFor);

      // The person on screen may have just been hidden by the operator or
      // filtered away; a quote outliving its node would be a ghost.
      if (shownFor && !next.has(shownFor)) hide();
    },
    show,
    showTerm,
    hide,
    get visible() {
      return !panel.hidden;
    },
    get personId() {
      return shownFor;
    },
  };
}
