// Der Graph am Telefon.
//
// Dieselben Daten wie an der Wand, ein anderes Bild. Drei Unterschiede, die
// alle aus demselben Grund folgen — die Wand ist 4 m breit und wird
// angeschaut, das Handy ist 39 cm² und wird BEDIENT:
//
// 1. Keine autonome Kamerafahrt. An der Wand führt sie, hier führt die
//    Besucherin: eine Fläche, die sich unter dem Finger von selbst wegdreht,
//    ist am Handy kein Erlebnis, sondern ein Fehler.
// 2. Weniger Begriffe gleichzeitig. Der Regler an der Wand kennt 45 Begriffe
//    auf 1920 px; hier passen etwa 17 auf 390 px, ohne dass die
//    Beschriftungen übereinanderliegen. Weniger ist hier richtig, nicht
//    ärmer.
// 3. Die Beschriftung behält ihre GRÖSSE AUF DEM SCHIRM, egal wie weit
//    hineingezoomt ist. Sonst wäre sie beim Herauszoomen unlesbar oder beim
//    Hineinzoomen plakatgross — und lesbar auf 390 px ist hier die Vorgabe.

/** Zielmasse. `schrift`, `tafelPolster`, `tafelRadius` und die beiden
 *  Portraitgrenzen in Bildschirm-Pixeln, `personModell` in Modelleinheiten.
 *
 *  Der Unterschied ist Absicht. Die Beschriftung muss immer lesbar sein, also
 *  hängt sie am Schirm. Die Portraits dagegen müssen die DICHTE des Netzes
 *  tragen: die Positionen kommen aus dem Layout der Wand, wo ein Gesicht
 *  `--person-size` Einheiten misst — hier dieselbe Zahl, also dasselbe
 *  Verhältnis von Gesicht zu Abstand. Am Schirm festgenagelt wären nach
 *  sechzig Interviews sechzig 44-px-Kreise auf 390 px Breite, also ein Fleck.
 *
 *  🔴 `personModell` war bis 2026-09-02 **56** — der Wert der Wand von
 *  2026-08-29. Die Wand steht seit theme-f („Schwarzplan") auf 110, und der
 *  Saal erbt das. Der Spiegel blieb zurück und zeichnete Gesichter halb so
 *  gross wie ueberall sonst. Gemessen an einem echten Stand der Station
 *  (drei Personen, 390×844, Zoom 0,345): **20,7 px**. Das ist genau Birks
 *  „die Porträts werden gar nicht angezeigt" — das Bild war da, geladen und
 *  gezeichnet, nur konnte man nichts darauf erkennen.
 *
 *  Boden und Deckel begrenzen die Extreme. 30 px ist die Untergrenze, ab der
 *  ein Bild als Bildinhalt und nicht als Markierung gelesen wird (zum
 *  Vergleich: `--tap` in mirror.css ist 44 px). 120 px ist derselbe Deckel,
 *  den die Wand fuehrt (PORTRAIT_MAX_PX in projection.js) — ein Gesicht darf
 *  bei zwei Personen im Netz nicht den halben Schirm fuellen. */
const ZIEL = {
  schrift: 13.5,
  personModell: 110,
  personMin: 30,
  personMax: 120,
  /* Der Ring um das Gesicht, als ANTEIL der Scheibe statt als feste Zahl:
     eine 2-Einheiten-Kontur ist an einem 110er Gesicht ein Haar und an einem
     30er ein Reifen. 0,045 ist das Verhaeltnis der Wand (--ring-width 5 auf
     --person-size 110). */
  ringAnteil: 0.045,
  /* Das Polster der Begriffstafel, in Bildschirm-Pixeln — dasselbe Mass, in
     dem die Schrift steht. Die Wand fuehrt --plate-pad 10 bei 26er Schrift,
     der Saal 12 bei 34er; beides rund 0,4 der Schrifthoehe. 6 px sind das
     bei 13,5. */
  tafelPolster: 6,
  /* Der Eckenradius der Tafel. Wand 18 bei 26er Schrift, Saal 24 bei 34er:
     rund 0,7 der Schrifthoehe. */
  tafelRadius: 9,
  /* Umbruchbreite der Beschriftung. Unveraendert aus dem Bestand — an ihr
     haengt LABEL_ABSTAND_PX unten, und der ist am echten Graphen eingestellt. */
  tafelMaxBreite: 150,
};

/** Wie viel Platz eine Beschriftung auf dem Schirm braucht, damit die nächste
 *  daneben und nicht darauf liegt. Aus `tafelMaxBreite` heraus
 *  gerechnet: eine typische Beschriftung bricht auf zwei Zeilen und misst dann
 *  gut 110 px; 100 px ist der Abstand, bei dem sich zwei davon höchstens
 *  streifen — gemessen am realen Graphen (Replay 19c, 18 Begriffe auf 390 px):
 *  darüber sieht man vier Begriffe und zu wenig Netz, darunter liegen die
 *  Beschriftungen wieder ineinander. */
const LABEL_ABSTAND_PX = 100;

/** Zeilenhöhe der Tafelbeschriftung. Muss zu `line-height` im STIL passen:
 *  zwei getrennte Zahlen machen die Tafel frueher oder spaeter kleiner als die
 *  Schrift darin. Derselbe Wert wie an der Wand (term-plate.js). */
const ZEILENHOEHE = 1.12;

/** Die Schriftfamilie der Tafeln. Steht hier UND im STIL, weil die Messung
 *  unten dieselbe Schrift braucht, mit der spaeter gezeichnet wird. */
const SCHRIFTFAMILIE = 'Inter, "Helvetica Neue", system-ui, sans-serif';

/** Wie weit die erste Ansicht höchstens hineinzoomt. Darüber sieht man drei
 *  Begriffe und hat kein Netz mehr vor sich, sondern eine Nahaufnahme. */
const MAX_START_ZOOM = 2.5;

/** Untergrenze der Begriffszahl: unter zehn ist es kein Netz mehr. */
const MIN_BEGRIFFE = 10;
/** Obergrenze: darüber liegen die Beschriftungen auch auf einem Tablet
 *  übereinander. */
const MAX_BEGRIFFE = 40;

/** Wie viele Begriffe auf diesen Schirm passen. Aus der KURZEN Seite
 *  gerechnet, damit das Querformat nicht plötzlich doppelt so voll wird —
 *  gedreht wird das Gerät, nicht die Lesbarkeit. */
export function begriffsZahl(breite, hoehe) {
  const kurz = Math.min(breite || 0, hoehe || 0);
  return Math.max(MIN_BEGRIFFE, Math.min(MAX_BEGRIFFE, Math.round(kurz / 22)));
}

/** Die Rangfolge der Wand, hier noch einmal: geteilte Begriffe zuerst,
 *  aufgefüllt mit den jüngsten Einzelnennungen. Bewusst nachgebaut statt aus
 *  frontend/static/graph-model.js importiert — die Wand wird gerade
 *  weiterentwickelt, und eine geteilte Datei würde beide Baustellen
 *  aneinanderbinden (Auftrag 2026-08-31). */
export function sichtbareBegriffe(begriffe, obergrenze) {
  const kandidaten = begriffe.filter((b) => !b.hidden);
  const sortiert = [...kandidaten].sort((a, b) => {
    const nachNennungen = (b.mentions || 0) - (a.mentions || 0);
    if (nachNennungen !== 0) return nachNennungen;
    const nachNeuheit = (b.created_at || 0) - (a.created_at || 0);
    if (nachNeuheit !== 0) return nachNeuheit;
    return a.label < b.label ? -1 : a.label > b.label ? 1 : 0;
  });
  const ids = new Set(sortiert.slice(0, Math.max(1, obergrenze)).map((b) => b.id));
  // Was gerade ins Traumbild geht, steht IMMER da — dieselbe Regel wie an der
  // Wand (Birk, 2026-08-30). Ohne sie wäre die Farbe, die „gerade eben
  // gesagt" bedeutet, am Handy strukturell unsichtbar: solche Begriffe haben
  // genau eine Nennung und stehen damit am Ende jeder Rangliste.
  for (const b of kandidaten) if (b.in_dream) ids.add(b.id);
  return ids;
}

/** Der Ausschnitt des Graphen, den dieses Gerät zeigt. */
export function ansicht(graph, obergrenze) {
  const knoten = graph.nodes || [];
  const begriffe = knoten.filter((n) => n.type === 'term');
  const sichtbar = sichtbareBegriffe(begriffe, obergrenze);
  const nodes = knoten.filter((n) => {
    if (n.hidden) return false;
    return n.type === 'term' ? sichtbar.has(n.id) : true;
  });
  const ids = new Set(nodes.map((n) => n.id));
  const edges = (graph.edges || []).filter((e) => ids.has(e.source) && ids.has(e.target));
  return { nodes, edges };
}

/* --- Kantenbögen ----------------------------------------------------------
   Birk, 2026-09-02: „Die Ansicht soll im Prinzip dieselbe sein wie der
   Plenarsaal — mit geschwungenen Kanten."

   Nachgebaut aus `frontend/static/term-plate.js::edgeCurve`, nicht importiert:
   der Spiegel wird ohne `frontend/` ausgeliefert (er läuft auf herkules), ein
   Import von dort wäre am Ausstellungstag ein 404 statt eines Netzes. Die
   Zahlen sind absichtlich WÖRTLICH dieselben — die Positionen kommen aus dem
   Layout der Wand, also gilt hier dasselbe Modellmass.

   Der Bogen hängt an der Kanten-ID und nicht am Zufall: der Spiegel bekommt
   alle drei Sekunden einen Push, und ein Bogen pro Frame würde das ganze Netz
   zappeln lassen. */

function hash32(text) {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h >>> 0;
}

/** {cpd, cpw} für eine Kante — zwei Kontrollpunkte mit gegenläufigem
 *  Vorzeichen, also die flache S-Kurve der Wand und nicht ein einzelner Bauch. */
export function kantenBogen(kantenId) {
  const h = hash32(String(kantenId));
  const vorzeichen = h & 1 ? 1 : -1;
  const amp1 = 18 + ((h >>> 1) % 22); // 18..39 Modelleinheiten
  const amp2 = 10 + ((h >>> 6) % 16); // 10..25, Gegenschwung
  return { cpd: `${vorzeichen * amp1} ${-vorzeichen * amp2}`, cpw: '0.35 0.72' };
}

/* --- Tafelmasse -----------------------------------------------------------
   Cytoscape kann einen Knoten NICHT auf seine Beschriftung wachsen lassen
   (kein `width: label`), also wird der Text vorher gemessen. Ein 2D-Kontext
   ohne DOM, gecacht — dieselbe Lösung wie an der Wand.

   Der Unterschied zur Wand: dort steht die Schrift in MODELLeinheiten und die
   Tafel damit auch, hier hängt die Schrift am SCHIRM (sie soll bei jedem Zoom
   lesbar bleiben). Gemessen wird deshalb einmal in Bildschirm-Pixeln, und
   `skaliere()` teilt das Ergebnis je Frame durch den Zoom. */

const _messFlaeche = document.createElement('canvas').getContext('2d');
const _messCache = new Map();

/** Die Tafelgrösse einer Beschriftung in BILDSCHIRM-Pixeln, inkl. Polster. */
export function tafelMass(text, schriftPx = ZIEL.schrift, maxBreite = ZIEL.tafelMaxBreite) {
  const schluessel = `${text}|${schriftPx}|${maxBreite}`;
  const treffer = _messCache.get(schluessel);
  if (treffer) return treffer;

  _messFlaeche.font = `${schriftPx}px ${SCHRIFTFAMILIE}`;
  // Dieselbe Umbruchregel wie Cytoscapes `text-wrap: wrap`.
  const zeilen = [];
  let laufend = '';
  for (const wort of String(text || '').split(/\s+/)) {
    const probe = laufend ? `${laufend} ${wort}` : wort;
    if (_messFlaeche.measureText(probe).width <= maxBreite || !laufend) {
      laufend = probe;
    } else {
      zeilen.push(laufend);
      laufend = wort;
    }
  }
  if (laufend) zeilen.push(laufend);

  let breiteste = 0;
  for (const zeile of zeilen) {
    breiteste = Math.max(breiteste, _messFlaeche.measureText(zeile).width);
  }
  const mass = {
    w: Math.ceil(breiteste) + 2 * ZIEL.tafelPolster,
    h: Math.ceil(Math.max(1, zeilen.length) * schriftPx * ZEILENHOEHE) + 2 * ZIEL.tafelPolster,
  };
  _messCache.set(schluessel, mass);
  return mass;
}

function elemente(sicht) {
  const liste = [];
  for (const n of sicht.nodes) {
    // Die Tafelmasse kommen schon HIER mit, nicht erst aus `skaliere()`:
    // `cy.fit()` in der ersten Ansicht rechnet mit der Knotengroesse, und ein
    // undefiniertes `data(boxW)` waere zu diesem Zeitpunkt ein Knoten ohne
    // Ausdehnung — der Ausschnitt saesse dann daneben. Der Wert gilt fuer
    // Zoom 1; `skaliere()` rechnet ihn jeden Frame auf den echten Zoom um.
    const mass = n.type === 'term' ? tafelMass(n.label || '') : null;
    const element = {
      data: {
        id: n.id,
        label: n.type === 'term' ? n.label || '' : '',
        portrait: n.portrait || '',
        boxW: mass ? mass.w : undefined,
        boxH: mass ? mass.h : undefined,
      },
      classes:
        n.type === 'person'
          ? // `mit-bild` nur, wenn es wirklich eins gibt: ein leeres
            // `background-image` lässt Cytoscape eine Bildwarnung je Knoten
            // und Frame protokollieren, und eine Person ohne Portrait (Foto
            // abgelehnt, Zuschnitt noch nicht fertig) ist der Normalfall.
            `person${n.portrait ? ' mit-bild' : ''}`
          : `term${n.in_dream ? ` in-dream dream-${n.dream_role || 'anchor'}` : ''}`,
    };
    if (n.x !== null && n.x !== undefined && n.y !== null && n.y !== undefined) {
      element.position = { x: n.x, y: n.y };
    }
    liste.push(element);
  }
  for (const e of sicht.edges) {
    // 🔴 KEINE eigene Klasse fuer Kanten an Traumbegriffen. Der erste Entwurf
    // hatte eine (rot, kraeftiger) und begruendete sie mit „wie an der Wand".
    // Nachgesehen statt geglaubt: `frontend/static/graph-model.js` gibt JEDER
    // Kante `classes: 'link'` und sonst nichts — die Regel `edge.link.in-dream`
    // in projection.js wird nie zugewiesen. An 390 px war der Unterschied auch
    // nicht dekorativ, sondern falsch: das Handy zeigt 20 statt 45 Begriffen,
    // die fuenf Traumbegriffe stehen dabei IMMER (`sichtbareBegriffe`), und
    // damit war ein Viertel des Netzes rot. Am Bild gemessen: 73 von 302
    // Kanten des Replays 19c beruehren einen Traumbegriff.
    liste.push({
      data: { id: e.id, source: e.source, target: e.target, ...kantenBogen(e.id) },
      classes: 'link',
    });
  }
  return liste;
}

/* --- Der Stil ------------------------------------------------------------
   Die Bildsprache des Saals, auf 390 px uebersetzt (Birk, 2026-09-02: „Die
   Ansicht soll im Prinzip dieselbe sein wie der Plenarsaal"). Kopiert, nicht
   geteilt: der Spiegel laeuft ohne `frontend/`, und eine geteilte Datei wuerde
   jede Aenderung an der Wand im selben Moment auf die Handys der Besucherinnen
   schieben.

   Was uebernommen ist:
     * Gesichter tragen einen Ring und ein leises Echo daneben (Zirkelgeometrie
       aus theme-f), und wer kein Bild hat, bekommt eine eigene ruhige Flaeche
       statt eines Platzhalters.
     * Begriffe SIND Tafeln. Der Punkt daneben ist ersatzlos weg — er war
       Kanten- und Labelanker und kostete den Blick einen Sprung.
     * Kanten sind Boegen.

   Was NICHT uebernommen ist: der Saal wirft die drei Achsenfarben weg, weil
   dort keine Legende steht. Am Handy steht eine (`#legende` in graph.html),
   also bleiben sie — sonst waere die Erklaerung unten ohne Gegenstand. */
const STIL = [
  {
    selector: 'node.person',
    style: {
      shape: 'ellipse',
      // 🔴 WIE IM PLENARSAAL, nicht wie im Schwarzplan (Birk, 2026-09-02:
      // „der rote Ring um die Porträts soll vom Design her so sein wie im
      // Plenarsaal"). Der Saal erbt `theme-f.css`, und dort steht die
      // Begruendung im Wortlaut:
      //
      //   `--person-fill: transparent` — „Schwarz und Nichts sehen auf
      //   Schwarz gleich aus. Der Unterschied zeigt sich nur dort, wo etwas
      //   dahinter ist, und dort ist er der Punkt." Ein dunkler Grund hinter
      //   dem Portrait deckt zu, was hinter ihm liegt.
      //
      //   `--ring-width: 0` — „Die goldenen Kreise um die Porträts sind viel
      //   zu viel" (2026-08-30). Der weiche Rand kommt aus dem PNG selbst
      //   (`kg/photos.py`, `soft_disc_mask` und `ring_glow`); ein harter Ring
      //   drumherum schneidet genau den Feather ab, den er umgibt.
      //
      // OHNE Portrait traegt die Fuellung die Scheibe allein. `#6e6656` ist
      // `--person-blank`: keine neue Farbe, sondern die der ruhenden
      // Begriffsraender. Eine Flaeche, keine Vertretung — kein Avatar, kein
      // Fragezeichen. Wer sich gegen ein Bild entscheidet, ist kein fehlendes
      // Bild.
      'background-color': (ele) => (ele.data('portrait') ? 'transparent' : '#6e6656'),
      'background-opacity': (ele) => (ele.data('portrait') ? 0 : 1),
      // Ring und Ringecho aus. Die Farbe bleibt als warmes Gold stehen (nicht
      // Rot), damit ein spaeteres Wiedereinschalten nicht versehentlich die
      // Signalfarbe zurueckholt.
      'border-color': '#c9a227',
      'border-opacity': 0,
      'outline-color': '#c9a227',
      'outline-opacity': 0,
      label: '',
      'z-index': 20,
    },
  },
  {
    // `mit-bild` nur, wenn es wirklich eins gibt: ein leeres
    // `background-image` laesst Cytoscape eine Bildwarnung je Knoten und
    // Frame protokollieren.
    selector: 'node.person.mit-bild',
    style: {
      'background-image': 'data(portrait)',
      'background-fit': 'cover',
      'background-clip': 'node',
    },
  },
  {
    selector: 'node.term',
    style: {
      // Die Tafel IST der Knoten. Damit enden die Kanten an der Tafelkante
      // statt unter der Schrift, und die Trefferflaeche fuer den Finger ist
      // die Flaeche, die man auch sieht.
      shape: 'round-rectangle',
      width: 'data(boxW)',
      height: 'data(boxH)',
      'background-color': '#0d0e10',
      'background-opacity': 0.55,
      'border-color': '#6e6656',
      'border-opacity': 0.85,
      label: 'data(label)',
      color: '#f2efe9',
      'text-valign': 'center',
      'text-halign': 'center',
      'text-justification': 'center',
      'font-family': SCHRIFTFAMILIE,
      'line-height': ZEILENHOEHE,
      'text-wrap': 'wrap',
      'z-index': 10,
    },
  },
  {
    // Im Bild: die Tafel wird massiv. Muss NACH `node.term` stehen —
    // Cytoscape gewichtet gleich spezifische Selektoren nach Reihenfolge.
    selector: 'node.term.in-dream',
    style: { 'background-opacity': 0.8 },
  },
  // 🔴 KEIN FARBCODE (Birk, 2026-09-02: „bei dem Spiegelview soll das Color
  // Coding weg"). Dieselbe Entscheidung wie im Plenarsaal, wo `plenum.css`
  // alle drei Rollenfarben auf `--licht` legt und die Legende damit gegenstands-
  // los wird.
  //
  // Die Rollen bleiben als KLASSEN erhalten und werden nur gleich gemalt: Sie
  // steuern weiterhin, WAS im Traum liegt (`node.term.in-dream` hebt die Tafel
  // an), nur nicht mehr, in welcher Farbe. Wer sie spaeter wieder auseinander-
  // ziehen will, aendert drei Werte statt der Datenstruktur.
  //
  // `#BEB497` ist `--licht` aus theme-f.css, dieselbe Farbe wie im Saal.
  { selector: 'node.dream-anchor', style: { color: '#BEB497', 'border-color': '#BEB497' } },
  { selector: 'node.dream-neighbour', style: { color: '#BEB497', 'border-color': '#BEB497' } },
  { selector: 'node.dream-recent', style: { color: '#BEB497', 'border-color': '#BEB497' } },
  {
    selector: 'edge.link',
    style: {
      // Der Bogen. `edge-distances: intersection` laesst ihn an der Tafel- bzw.
      // Scheibenkante ansetzen und nicht in deren Mittelpunkt.
      'curve-style': 'unbundled-bezier',
      'control-point-distances': 'data(cpd)',
      'control-point-weights': 'data(cpw)',
      'edge-distances': 'intersection',
      'line-cap': 'round',
      'line-color': '#7a6a4a',
      'line-opacity': 0.55,
      'target-arrow-shape': 'none',
      'z-index': 1,
    },
  },
];

export function createMobileGraph(container, { aufPerson = () => {}, aufBegriff = () => {} } = {}) {
  const cy = cytoscape({
    container,
    style: STIL,
    elements: [],
    layout: { name: 'preset' },
    minZoom: 0.05,
    maxZoom: 6,
    // Wischen und Zwei-Finger-Zoom: ja. Knoten verschieben: nein — am Handy
    // ist ein gehaltener Finger ein Wischversuch, kein Umbauwunsch.
    autoungrabify: true,
    autounselectify: true,
    boxSelectionEnabled: false,
  });

  let bekannt = new Set();
  let ersteZeichnung = true;

  function skaliere() {
    // Bildschirmmasse in Modelleinheiten umrechnen, damit alles beim Zoomen
    // gleich gross bleibt. Alles, was hier durch `z` geteilt wird, ist am
    // Schirm festgenagelt; was nicht geteilt wird, folgt der Dichte des Netzes.
    const z = cy.zoom() || 1;
    const person =
      Math.min(ZIEL.personMax, Math.max(ZIEL.personMin, ZIEL.personModell * z)) / z;
    // 🔴 Ring und Echo auf 0 — wie `--ring-width` und `--ring-echo-width` im
    // Theme, das der Plenarsaal erbt. Die Breite wird trotzdem HIER gesetzt
    // und nicht nur oben im Stilblatt weggelassen: Cytoscape behaelt sonst,
    // was ein frueherer Frame gesetzt hat, und der Ring kaeme beim ersten
    // Zoomen zurueck.
    cy.batch(() => {
      cy.nodes('.person').style({
        width: person,
        height: person,
        'border-width': 0,
        'outline-width': 0,
      });
      // Die Tafeln. Gemessen wird in Bildschirm-Pixeln (einmal je Beschriftung,
      // gecacht), geteilt wird je Frame — so bleibt die Tafel exakt so gross
      // wie ihre Schrift, bei jedem Zoom.
      for (const knoten of cy.nodes('.term')) {
        const mass = tafelMass(knoten.data('label') || '');
        knoten.data({ boxW: mass.w / z, boxH: mass.h / z });
      }
      cy.nodes('.term').style({
        'font-size': ZIEL.schrift / z,
        'corner-radius': ZIEL.tafelRadius / z,
        'border-width': (ele) => (ele.hasClass('in-dream') ? 2.5 : 1.5) / z,
        'text-max-width': `${ZIEL.tafelMaxBreite / z}px`,
      });
      cy.edges().style({ width: 1.2 / z });
    });
  }

  let geplant = false;
  function skalierePlanen() {
    if (geplant) return;
    geplant = true;
    window.requestAnimationFrame(() => {
      geplant = false;
      skaliere();
    });
  }
  cy.on('zoom', skalierePlanen);

  /** Wie oft `einpassen()` hoechstens nachrechnet. Vier reichen mit weitem
   *  Abstand: gemessen konvergiert es nach zweien. */
  const EINPASS_RUNDEN = 4;
  /** Ab welcher Aenderung es sich gelohnt hat weiterzurechnen. */
  const EINPASS_GENAUIGKEIT = 0.01;

  /** Alles ins Bild — als FIXPUNKT, nicht in einem Durchgang.
   *
   *  🔴 Die Tafelgroesse und der Ausschnitt haengen VONEINANDER ab: eine Tafel
   *  misst `Mass / Zoom` Modelleinheiten (die Schrift soll am Schirm gleich
   *  gross bleiben), und `cy.fit()` bestimmt den Zoom aus eben diesen
   *  Modelleinheiten. Ein einzelnes `fit()` beantwortet also eine Frage, die
   *  sich durch die Antwort aendert.
   *
   *  Am 2026-09-02 gemessen, echter Stand der Station auf 390×844: nach dem
   *  ersten `fit()` stand Zoom 0,345, und die damit neu gerechneten Tafeln
   *  reichten von x = −98 bis x = 388 — links aus dem Bild heraus. Ein
   *  zweiter Durchgang kam auf 0,226 und passte.
   *
   *  Die Wand hat dieses Problem nicht: dort steht die Schrift in
   *  Modelleinheiten und waechst mit dem Zoom mit. Der Preis fuer die
   *  Lesbarkeit am Telefon ist diese Schleife. */
  function einpassen() {
    let vorher = 0;
    for (let runde = 0; runde < EINPASS_RUNDEN; runde++) {
      cy.fit(undefined, 36);
      skaliere();
      const jetzt = cy.zoom();
      // Relativ vergleichen, nicht absolut: der Zoom bewegt sich je nach
      // Netzgroesse zwischen 0,05 und 6, und eine feste Schranke waere am
      // einen Ende blind und am anderen nie erreicht.
      if (vorher && Math.abs(jetzt - vorher) / vorher < EINPASS_GENAUIGKEIT) break;
      vorher = jetzt;
    }
  }

  /** Der Zoom, ab dem zwei benachbarte Beschriftungen nebeneinanderpassen.
   *
   *  Gerechnet, nicht geraten: gemessen wird der typische (mittlere) Abstand
   *  zweier benachbarter Begriffe im Modell, und daraus folgt der Zoom, bei dem
   *  dieser Abstand auf dem Schirm mindestens eine Beschriftungsbreite ergibt.
   *  Gibt `null` zurück, wenn zu wenige Begriffe für eine Aussage da sind. */
  function lesbarerZoom() {
    const begriffe = cy.nodes('.term');
    if (begriffe.length < 3) return null;
    const punkte = begriffe.map((n) => n.position());
    const naechste = punkte.map((a) => {
      let kleinster = Infinity;
      for (const b of punkte) {
        if (a === b) continue;
        const d = Math.hypot(a.x - b.x, a.y - b.y);
        if (d < kleinster) kleinster = d;
      }
      return kleinster;
    });
    naechste.sort((a, b) => a - b);
    const mitte = naechste[Math.floor(naechste.length / 2)];
    if (!Number.isFinite(mitte) || mitte <= 0) return null;
    return LABEL_ABSTAND_PX / mitte;
  }

  /** Die erste Ansicht: NICHT stumpf alles einpassen.
   *
   *  Die Positionen kommen aus dem Layout der Wand, das für 1920 px gerechnet
   *  ist. Auf 390 px gepresst liegen die Beschriftungen übereinander — auf
   *  einer Wand ist der ganze Graph auf einmal lesbar, am Telefon ist er es
   *  nicht, und das lässt sich nicht durch kleinere Schrift lösen (dann ist
   *  gar nichts mehr lesbar).
   *
   *  Also öffnet die Seite auf einem AUSSCHNITT, so weit hineingezoomt, dass
   *  die Begriffe auseinandertreten, und dort, wo gerade etwas passiert: bei
   *  den Begriffen, aus denen das Traumbild entsteht. Von da führt die
   *  Besucherin selbst — wischen, aufziehen, Doppeltipp für das Ganze. Das ist
   *  keine Kamerafahrt: es bewegt sich nichts von allein, es ist nur die
   *  Stelle, an der die Seite aufschlägt. */
  function ersteAnsicht() {
    einpassen();
    const noetig = lesbarerZoom();
    if (noetig === null || cy.zoom() >= noetig) return;
    const ziel = Math.min(noetig, MAX_START_ZOOM);
    cy.zoom({ level: ziel, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
    const fokus = brennpunkt();
    if (fokus && fokus.length) cy.center(fokus);
    skaliere();
  }

  /** Wo die Seite aufschlägt.
   *
   *  Erste Wahl sind die Begriffe, aus denen gerade das Traumbild entsteht —
   *  dort passiert etwas, und die Farben der Wand bekommen am Handy nur einen
   *  Sinn, wenn man sie auch sieht. Sonst der Begriff mit den meisten Kanten:
   *  die Mitte des Feldes ist nicht dessen geometrischer Mittelpunkt (der kann
   *  im Leeren liegen), sondern die dichteste Stelle. */
  function brennpunkt() {
    const imBild = cy.nodes('.in-dream');
    if (imBild.length) return imBild;
    const begriffe = cy.nodes('.term');
    if (!begriffe.length) return null;
    return begriffe.max((n) => n.degree(false)).ele;
  }

  // Doppeltipp = alles einpassen. Nur auf dem Hintergrund: ein Doppeltipp auf
  // ein Gesicht ist zweimal „zeig mir diese Person", nicht „geh raus".
  let letzterHintergrundTipp = 0;
  cy.on('tap', (ereignis) => {
    if (ereignis.target !== cy) return;
    const jetzt = Date.now();
    if (jetzt - letzterHintergrundTipp < 320) einpassen();
    letzterHintergrundTipp = jetzt;
    aufPerson(null);
  });
  // Der unfilterte Tipp plus Zielprüfung oben ist die Form, die Hintergrund und
  // Knoten wirklich unterscheidet — Cytoscapes 'core'-Selektor tut in diesem
  // Bundle das Gegenteil seines Namens (gemessen 2026-08-26,
  // frontend/static/quote-overlay.js).
  cy.on('tap', 'node.person', (ereignis) => aufPerson(ereignis.target.id()));
  // 🔴 Und auf einen BEGRIFF (Birk, 2026-09-02). Gemessen am echten Stand auf
  // 390x844: Ein Fingertipp auf ein Portrait landete auf einem BEGRIFF — vier
  // Knoten lagen an derselben Stelle uebereinander. Begriffe waren nicht
  // anklickbar, also passierte gar nichts, und die Seite wirkte tot.
  cy.on('tap', 'node.term', (ereignis) => aufBegriff(ereignis.target.id()));

  return {
    cy,
    einpassen,
    ersteAnsicht,
    /** Ein vollständiger Graph, wie er vom Spiegel kommt. */
    update(graph, obergrenze) {
      const sicht = ansicht(graph, obergrenze);
      const neu = elemente(sicht);
      const neueIds = new Set(neu.map((e) => e.data.id));

      cy.batch(() => {
        // Nur die Differenz anfassen: ein kompletter Neuaufbau würde bei jedem
        // Push die Ansicht zurücksetzen, die die Besucherin sich gerade
        // zurechtgeschoben hat.
        for (const id of bekannt) {
          if (!neueIds.has(id)) cy.getElementById(id).remove();
        }
        for (const element of neu) {
          const vorhanden = cy.getElementById(element.data.id);
          if (vorhanden.length) {
            vorhanden.data(element.data);
            vorhanden.classes(element.classes);
            if (element.position && vorhanden.isNode()) vorhanden.position(element.position);
          } else {
            cy.add(element);
          }
        }
      });
      bekannt = neueIds;

      // Ohne gespeicherte Positionen (eine Station, deren Wand noch nie
      // gerendert hat) legt Cytoscapes eingebautes cose ein Netz. Die
      // Erweiterungen der Wand werden dafür NICHT mitgeschleppt: 710 KB über
      // ein Konferenz-WLAN für einen Randfall.
      const ohnePosition = cy.nodes().filter((n) => {
        const p = n.position();
        return !p || (p.x === 0 && p.y === 0);
      });
      if (cy.nodes().length && ohnePosition.length === cy.nodes().length) {
        cy.layout({ name: 'cose', animate: false, fit: false }).run();
      }

      // Erst die Masse, dann der Ausschnitt: `ersteAnsicht()` misst die
      // Abstaende der Tafeln, und die haengen an ihrer Groesse.
      skaliere();
      if (ersteZeichnung && cy.nodes().length) {
        ersteZeichnung = false;
        ersteAnsicht();
      }
    },
  };
}
