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

/** Zielmasse. `schrift` und `punkt` in Bildschirm-Pixeln, `personModell` in
 *  Modelleinheiten.
 *
 *  Der Unterschied ist Absicht. Die Beschriftung muss immer lesbar sein, also
 *  hängt sie am Schirm. Die Portraits dagegen müssen die DICHTE des Netzes
 *  tragen: die Positionen kommen aus dem Layout der Wand, wo ein Gesicht 56
 *  Einheiten misst — hier dieselbe Zahl, also dasselbe Verhältnis von Gesicht
 *  zu Abstand. Am Schirm festgenagelt wären nach sechzig Interviews sechzig
 *  44-px-Kreise auf 390 px Breite, also ein Fleck. Boden und Deckel begrenzen
 *  nur die Extreme: ein Punkt unter 10 px ist kein Gesicht mehr, über 52 px
 *  füllt eines ein Siebtel der Breite eines Telefons. */
const ZIEL = { schrift: 13.5, punkt: 7, personModell: 56, personMin: 10, personMax: 52 };

/** Wie viel Platz eine Beschriftung auf dem Schirm braucht, damit die nächste
 *  daneben und nicht darauf liegt. Aus `text-max-width: 150px` in STIL heraus
 *  gerechnet: eine typische Beschriftung bricht auf zwei Zeilen und misst dann
 *  gut 110 px; 100 px ist der Abstand, bei dem sich zwei davon höchstens
 *  streifen — gemessen am realen Graphen (Replay 19c, 18 Begriffe auf 390 px):
 *  darüber sieht man vier Begriffe und zu wenig Netz, darunter liegen die
 *  Beschriftungen wieder ineinander. */
const LABEL_ABSTAND_PX = 100;

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

function elemente(sicht) {
  const liste = [];
  for (const n of sicht.nodes) {
    const element = {
      data: {
        id: n.id,
        label: n.type === 'term' ? n.label || '' : '',
        portrait: n.portrait || '',
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
    liste.push({ data: { id: e.id, source: e.source, target: e.target }, classes: 'link' });
  }
  return liste;
}

const STIL = [
  {
    selector: 'node.person',
    style: {
      shape: 'ellipse',
      'background-color': '#242424',
      'border-width': 2,
      'border-color': '#d62828',
      label: '',
      'z-index': 10,
    },
  },
  {
    selector: 'node.person.mit-bild',
    style: { 'background-image': 'data(portrait)', 'background-fit': 'cover' },
  },
  {
    selector: 'node.term',
    style: {
      shape: 'ellipse',
      'background-color': 'rgba(242, 239, 233, 0.55)',
      label: 'data(label)',
      color: '#f2efe9',
      'text-valign': 'center',
      'text-halign': 'center',
      'font-family': 'Inter, "Helvetica Neue", system-ui, sans-serif',
      // Die Beschriftung ist am Handy die Hauptsache und muss auch dann lesbar
      // bleiben, wenn ein Portrait dahinterliegt: eigener dunkler Grund statt
      // eines Schattens.
      'text-background-color': '#0d0e10',
      'text-background-opacity': 0.82,
      'text-background-shape': 'roundrectangle',
      'text-max-width': '150px',
      'text-wrap': 'wrap',
      'z-index': 5,
    },
  },
  { selector: 'node.dream-anchor', style: { color: '#d62828' } },
  { selector: 'node.dream-neighbour', style: { color: '#4a7fd8' } },
  { selector: 'node.dream-recent', style: { color: '#f4c300' } },
  {
    selector: 'edge.link',
    style: {
      'curve-style': 'straight',
      'line-color': 'rgba(242, 239, 233, 0.18)',
      'target-arrow-shape': 'none',
      'z-index': 1,
    },
  },
];

export function createMobileGraph(container, { aufPerson = () => {} } = {}) {
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
    // gleich gross bleibt.
    const z = cy.zoom() || 1;
    const person =
      Math.min(ZIEL.personMax, Math.max(ZIEL.personMin, ZIEL.personModell * z)) / z;
    cy.batch(() => {
      cy.nodes('.person').style({ width: person, height: person });
      cy.nodes('.term').style({
        width: ZIEL.punkt / z,
        height: ZIEL.punkt / z,
        'font-size': ZIEL.schrift / z,
        'text-background-padding': `${3 / z}px`,
      });
      cy.edges().style({ width: Math.max(0.6, 1 / z) });
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

  function einpassen() {
    cy.fit(undefined, 36);
    skaliere();
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

      if (ersteZeichnung && cy.nodes().length) {
        ersteZeichnung = false;
        ersteAnsicht();
      } else {
        skaliere();
      }
    },
  };
}
