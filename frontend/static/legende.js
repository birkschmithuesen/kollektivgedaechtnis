/** Die Legende zu den drei Farben der Traumauswahl (Birk, 2026-09-01).
 *
 * Wörtlich gewünscht:
 *   rot   → „oft genannt"
 *   blau  → „nachbarn"
 *   gelb  → „vor kurzem gesagt"
 *
 * 🔴 „oft genannt" stimmte am 2026-09-01, als der Anker der meistgenannte
 * Begriff des ganzen Tages war (`haeufigste[0]`). Seit dem 2026-09-02 ist er
 * der meistgenannte Begriff DER ZULETZT BEFRAGTEN PERSON — das Bild ist an
 * das letzte Gespräch gebunden. Das Wort bleibt trotzdem stehen: Es ist
 * Birks eigene Formulierung, und für den Besucher vor der Wand bedeutet Rot
 * weiterhin „das ist hier das Wichtige". Wer es genau wissen will, liest
 * `select_required`.
 *
 * Die Häufigkeit hat seit dem 2026-09-02 einen EIGENEN Kanal: die GRÖSSE des
 * Punktes (`mapData(mentions …)` in projection.js). Deshalb steht sie unten
 * als vierter Eintrag — ohne ihn erklärte die Legende drei von vier
 * Bedeutungen, die auf der Wand zu sehen sind. Die
 * Farben stehen in `theme-f.css` als `--dream-anchor-color` (Bauhaus-Rot),
 * `--dream-neighbour-color` (Blau) und `--dream-recent-color` (Gelb).
 *
 * ## Warum das dem Konzept nicht widerspricht
 *
 * `konzept-live-interview-graph.md` sagt „bewusst reduziert, kein Dashboard:
 * keine Legende, kein Filter". Der Satz zielt auf ein Bedienfeld — etwas, das
 * Zustände anzeigt und zum Klicken einlädt. Diese Legende ist das Gegenteil:
 * drei Punkte mit je einem Wort, unbeweglich, nicht anklickbar, ohne Rahmen,
 * ohne Überschrift, ohne Kasten. Sie erklärt einen Code, der sonst
 * ungedeutet bleibt — sie zeigt keinen Zustand.
 *
 * Die Farben werden aus dem GELADENEN Stylesheet gelesen, nicht hier
 * wiederholt: Ein zweiter Satz Farbwerte im Code liefe auseinander, sobald
 * jemand die Palette anfasst — und dann erklärte die Legende Farben, die an
 * der Wand nicht mehr vorkommen. Das wäre schlimmer als keine Legende.
 *
 * Deshalb erscheint sie auch NUR in Themes, die die Farbcodierung wirklich
 * tragen (e und f). Ein Theme ohne `--dream-anchor-color` bekommt keine
 * Legende statt einer mit leeren Punkten.
 */

/** Die drei Achsen, in der Reihenfolge, in der die Auswahl sie bildet:
 *  erst der Anker, dann seine Nachbarschaft, dann das Jüngste. */
const ACHSEN = [
  { variable: '--dream-anchor-color', wort: 'oft genannt' },
  { variable: '--dream-neighbour-color', wort: 'Nachbarn' },
  { variable: '--dream-recent-color', wort: 'vor Kurzem gesagt' },
];

/** Der vierte Eintrag: kein Farbpunkt, sondern zwei verschieden grosse.
 *  Er erklaert den Kanal, den die drei Farben NICHT tragen. */
const GROESSE = { wort: 'öfter gesagt' };

function cssWert(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Hängt die Legende an `ziel` (Vorgabe: document.body).
 *
 * Gibt ein Handle mit `element` und `entfernen()` zurück — Letzteres braucht
 * `sim/prerender.py`, das definierte statt erzählende Aufnahmen schießt und
 * die Legende dabei nicht im Bild haben will.
 *
 * Liefert `null`, wenn das aktive Theme die Farben nicht kennt. Der Aufrufer
 * muss das nicht prüfen; er bekommt dann schlicht keine Legende.
 */
export function attachLegende(ziel = document.body) {
  const farben = ACHSEN.map((achse) => ({ ...achse, farbe: cssWert(achse.variable) }));
  // Alle drei oder keine: eine Legende, in der ein Punkt unsichtbar bleibt,
  // erklärt weniger als gar keine und sieht nach einem Fehler aus.
  if (farben.some((f) => !f.farbe)) return null;

  const box = document.createElement('aside');
  box.className = 'dream-legende';
  // Für Vorlesewerkzeuge unsichtbar: Die Wand ist eine Projektion ohne
  // Bedienung, und der Inhalt steht bereits im Graphen selbst.
  box.setAttribute('aria-hidden', 'true');

  for (const { farbe, wort } of farben) {
    const zeile = document.createElement('span');
    zeile.className = 'dream-legende-eintrag';

    const punkt = document.createElement('span');
    punkt.className = 'dream-legende-punkt';
    // Inline gesetzt, weil der Wert aus dem Theme kommt und nicht aus dem
    // Stylesheet dieser Datei stammen kann.
    punkt.style.background = farbe;
    zeile.appendChild(punkt);

    const text = document.createElement('span');
    text.textContent = wort;
    zeile.appendChild(text);

    box.appendChild(zeile);
  }

  ziel.appendChild(box);
  return {
    element: box,
    entfernen() {
      box.remove();
    },
  };
}
