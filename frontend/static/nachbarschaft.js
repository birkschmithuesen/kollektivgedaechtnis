// Hervorheben, was zusammenhängt (Birk, 2026-09-02).
//
// 🔴 „Wenn wir einen Node anklicken, sei es Porträt oder sei es Begriff, dann
// sollen die damit verknüpften Nodes auch gehighlighted hervortreten und die
// anderen im Hintergrund treten." Vorbild ist Obsidians Graph View, wo ein
// Hover genau das tut.
//
// Warum eine eigene Datei und nicht ein paar Zeilen in projection.js: Das
// Hervorheben ist eine ANSICHTSSACHE und darf am Graphmodell nichts ändern.
// Es setzt nur Klassen und nimmt sie wieder weg — kein Layoutlauf, keine
// Positionen, keine Daten. Damit kann es nie die Anordnung stören, an der die
// Traumauswahl inzwischen mitrechnet (kg2/weighting.py misst echte Abstände).
//
// Aussteigen über einen Tipp ins Leere, genau wie beim Zitat (Birk: „rauskommen
// über klicken in freien bereich, wie es bisher bei der anzeige von zitaten
// auch schon ist"). Deshalb hängt es sich an dieselbe Mechanik: die
// ungefilterte Bindung mit explizitem Zielvergleich. Cytoscapes 'core'-Selektor
// feuert auf dem GEGENTEIL dessen, was sein Name nahelegt — siehe die Messung
// in quote-overlay.js.

/** Klassen: `.nachbar` für das Angetippte und seine direkten Verbindungen,
 * `.abseits` für alles andere. Beide Namen liegen im Theme, nicht hier. */
export function attachNachbarschaft(view) {
  const cy = view.cy;

  function loesen() {
    cy.elements().removeClass('nachbar abseits');
  }

  function hervorheben(node) {
    // `closedNeighborhood` ist die Nachbarschaft EINSCHLIESSLICH des Knotens
    // selbst und einschliesslich der Kanten dazwischen — ohne die Kanten
    // bliebe die Verbindung unsichtbar, und genau sie ist die Aussage.
    const nah = node.closedNeighborhood();
    cy.elements().addClass('abseits');
    nah.removeClass('abseits').addClass('nachbar');
  }

  cy.on('tap', 'node', (event) => hervorheben(event.target));
  cy.on('tap', (event) => {
    if (event.target === cy) loesen();
  });

  return { loesen, hervorheben };
}
