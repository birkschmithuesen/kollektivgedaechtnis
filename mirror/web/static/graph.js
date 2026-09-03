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
/** Ab welcher Fensterbreite die Laptop-Maße gelten.
 *
 * Dieselbe Schwelle, ab der auch das Blatt zur Seitenleiste wird (graph.css):
 * Wo eine Spalte von 380 px daneben passt, ist der Schirm kein Telefon mehr.
 * Eine Zahl an zwei Stellen wäre eine zu viel — sie steht hier, weil das CSS
 * sie nicht ausrechnen kann und JavaScript sie ohnehin braucht. */
const LAPTOP_AB = 820;

/** Die Maße der großen Fläche (Birk, 2026-09-03: „es sollte als mobile view
 *  und als laptop ansicht (so wie projektion) sein").
 *
 * Sie sind die der Wand (`frontend/static/theme-f.css`), auf den Spiegel
 * übertragen: 26er Schrift statt 13,5, Portraits von 235 statt 110. Am Laptop
 * sitzt niemand mit dem Gesicht 30 cm vor dem Schirm — dort gilt derselbe
 * Leseabstand wie im Raum, und dieselbe Bildsprache. */
const ZIEL_LAPTOP = {
  // 🔴 DIE BILDSPRACHE DER WAND, NICHT IHRE PIXEL (gemessen 2026-09-03):
  // Mit den Wandwerten (26 px Schrift, 235er Portraits) passte das Netz nicht
  // mehr ins Bild — man sah einen Ausschnitt, und die Knöpfe verschwanden
  // hinter Tafeln.
  //
  // Der Grund ist die Fläche: Die Wand hat 1920x1080 und wird aus drei Metern
  // gelesen, ein Laptop 1440x900 aus einem halben. Das sind 56 % der Fläche
  // bei einem Bruchteil des Abstands. Die Werte hier sind die der Wand mal
  // rund 0,72 — dieselben Verhältnisse untereinander, auf die kleinere Fläche
  // gebracht.
  schrift: 19,
  personModell: 170,
  personMin: 46,
  personMax: 190,
  ringAnteil: 0.045,
  // Polster 0,4 und Radius 0,7 der Schrifthöhe, wie an der Wand.
  tafelPolster: 8,
  tafelRadius: 13,
  tafelMaxBreite: 190,
};

const ZIEL_MOBIL = {
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

/** Die Maße, die gerade gelten.
 *
 * 🔴 EINE FUNKTION und keine Konstante: Die Wahl hängt an der Fensterbreite,
 * und die ändert sich beim Drehen eines Tablets ebenso wie beim Ziehen eines
 * Browserfensters. Ein einmal gelesener Wert wäre danach falsch — und zwar
 * still, weil das Bild einfach weiter mit den alten Maßen rechnet.
 *
 * Der Zugriff kostet nichts Messbares: `innerWidth` ist ein Feld, kein Layout. */
function ziel() {
  const breit = typeof window !== 'undefined' && window.innerWidth >= LAPTOP_AB;
  return breit ? ZIEL_LAPTOP : ZIEL_MOBIL;
}

// Für die Stellen, die weiterhin einen festen Bezug brauchen (Vorgabewerte in
// Signaturen). Sie lesen die mobilen Maße; wer die geltenden will, ruft `ziel()`.
const ZIEL = ZIEL_MOBIL;

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
// Der Deckel, der uebrig bleibt: An der Station laufen selten mehr als
// hundert Begriffe zusammen, und eine Zahl im Code verhindert, dass ein
// fehlerhafter Push die Seite mit Tausenden lahmlegt.
const MAX_BEGRIFFE = 200;

/** Wie viele Begriffe der Spiegel zeigt.
 *
 * 🔴 SEIT DEM 2026-09-03 ALLE, auch am Telefon (Birk: „zeige im handy auch 66
 * positionen an und nimm dafür den traum weg").
 *
 * Vorher wurde aus der kurzen Bildschirmseite gerechnet — auf 390 px ergab das
 * `round(390/22) = 18` Begriffe, also gut ein Viertel des Bestands. Die
 * Begrenzung war als Lesbarkeitsschutz gedacht und stammt aus einer Zeit, in
 * der sich die Tafeln am Telefon noch überlagerten. Beides ist seither
 * anders: Die Überdeckungen werden aufgelöst (`loeseUeberdeckungen`), und wer
 * etwas genauer sehen will, zoomt.
 *
 * Der Zuschnitt bleibt trotzdem an EINER Stelle stehen und wird nicht
 * herausgerissen: Der Regler an der Station (`max_terms`) begrenzt weiterhin,
 * und wer die Grenze zurückholen will, ändert diese Zeile.
 *
 * `breite`/`hoehe` bleiben in der Signatur — die Seite ruft mit ihnen, und ein
 * geänderter Aufruf wäre eine zweite Stelle, die man beim nächsten Umbau
 * vergisst. */
export function begriffsZahl(breite, hoehe) {
  void breite;
  void hoehe;
  return MAX_BEGRIFFE;
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
/** Ab wie vielen Nennungen die Schrift waechst — dieselben Schwellen wie an
 *  der Wand (frontend/static/projection.js). Drei: Zwei Menschen sind eine
 *  Uebereinstimmung, drei sind ein Thema. */
const OFT_AB = 3;

/** Die Schriftgroesse eines Begriffs in Zielpixeln.
 *
 * 🔴 MITSKALIEREND (Birk, 2026-09-03: „mach mitskalieren"): Der Wert geht
 * durch denselben `/ z`-Teiler wie `ZIEL.schrift`, wird also beim Zoomen
 * genauso festgenagelt wie alles andere. Damit bleibt das Verhaeltnis
 * „oft gesagt = groesser" bei jedem Zoom gleich sichtbar, statt sich beim
 * Herauszoomen einzuebnen.
 *
 * Grundgroesse bis zum Doppelten, Deckel bei sechs Nennungen — ein einzelner
 * Spitzenreiter soll die Skala nicht fuer sich nehmen. Die Skala setzt bei
 * 1,3 an, damit ein Begriff, der eben erst zum Thema geworden ist, nicht
 * aussieht wie eine Einmal-Nennung. */
export function haeufigSchrift(mentions) {
  const n = Number(mentions) || 1;
  const Z = ziel();
  if (n < OFT_AB) return Z.schrift;
  const gedeckelt = Math.min(6, n);
  return Z.schrift * (1.3 + ((gedeckelt - OFT_AB) / (6 - OFT_AB)) * 0.7);
}

export function tafelMass(text, schriftPx, maxBreite) {
  const Z = ziel();
  schriftPx = schriftPx || Z.schrift;
  maxBreite = maxBreite || Z.tafelMaxBreite;
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
    w: Math.ceil(breiteste) + 2 * ziel().tafelPolster,
    h: Math.ceil(Math.max(1, zeilen.length) * schriftPx * ZEILENHOEHE) + 2 * ziel().tafelPolster,
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
    // Die Tafel wird mit der Schrift gemessen, die sie tragen wird — sonst
    // stuende der groessere Text in der alten Kiste (derselbe Fehler wie an
    // der Wand, 2026-09-03).
    const mass =
      n.type === 'term' ? tafelMass(n.label || '', haeufigSchrift(n.mentions)) : null;
    const element = {
      data: {
        id: n.id,
        label: n.type === 'term' ? n.label || '' : '',
        portrait: n.portrait || '',
        boxW: mass ? mass.w : undefined,
        boxH: mass ? mass.h : undefined,
        // 🔴 BEIDE Lagen mitfuehren (Birk, 2026-09-03: „der spiegel soll auch
        // die beiden verschiedenen organisationsarten (menschen / bedeutung)
        // zulassen"). `x/y` ist die Lage aus den Gespraechen — wer mit wem
        // etwas gesagt hat. `sx/sy` ist die Lage aus der Bedeutung: was
        // inhaltlich nebeneinander gehoert, auch wenn es niemand zusammen
        // gesagt hat. Der Kern rechnet beide und liefert beide.
        gx: n.x, gy: n.y,
        sx: n.sx, sy: n.sy,
        // Wie viele Menschen den Begriff gesagt haben — traegt seit dem
        // 2026-09-03 die Schriftgroesse (`haeufigSchrift`).
        mentions: n.mentions || 0,
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
  /* 🔴 DIE DREI TRAUMROLLEN FAERBEN NICHTS MEHR (Birk, 2026-09-03, zuerst an
     der Wand: „die farbige markierung (rot/blau/gelb) soll jetzt weg … bzw. du
     kannst das color coding jetzt nutzen um häufig genannte begriffe zu
     highlighten"). Am Spiegel trugen alle drei ohnehin dieselbe Farbe, seit
     die Legende hier verborgen ist — sie unterschieden also nichts mehr.
     Die Klassen bleiben am Knoten: Sie sind Daten und werden vom Empfaenger
     geprueft, nur gemalt wird nichts mehr daraus.
     Die Haeufigkeit steht seither in der SCHRIFTGROESSE (`haeufigSchrift`). */
  // --- Nachbarschaft: was zum Angetippten gehoert, und was zuruecktritt ----
  //
  // 🔴 IM CYTOSCAPE-STYLESHEET und nicht in graph.css: Knoten und Kanten
  // werden auf ein <canvas> gezeichnet, es gibt fuer sie keine CSS-Regel, die
  // greifen koennte. Eine Klasse im Stylesheet ist der einzige Weg.
  //
  // Zurueckgetreten heisst blass, nicht weg: Das Netz soll als Ganzes stehen
  // bleiben — man soll sehen, WOVOR die Auswahl haengt. 0,12 ist der Wert, bei
  // dem die Umrisse gerade noch erkennbar sind.
  { selector: '.abseits', style: { opacity: 0.12 } },
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
    // Die geltenden Zielmaße — am Laptop die der Wand, am Telefon die kleinen.
    const Z = ziel();
    const person =
      Math.min(Z.personMax, Math.max(Z.personMin, Z.personModell * z)) / z;
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
        const mass = tafelMass(
          knoten.data('label') || '',
          haeufigSchrift(knoten.data('mentions')),
        );
        knoten.data({ boxW: mass.w / z, boxH: mass.h / z });
      }
      cy.nodes('.term').style({
        'font-size': (ele) => haeufigSchrift(ele.data('mentions')) / z,
        'corner-radius': Z.tafelRadius / z,
        'border-width': (ele) => (ele.hasClass('in-dream') ? 2.5 : 1.5) / z,
        'text-max-width': `${Z.tafelMaxBreite / z}px`,
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
    // 🔴 HIER STAND EIN VERSUCH, AM LAPTOP IMMER DAS GANZE NETZ ZU ZEIGEN
    // (Birk, 2026-09-03: „als laptop ansicht (so wie projektion)") — und er
    // ist ZURUECKGENOMMEN, weil die Messung ihn widerlegt hat:
    //
    //     ohne den Zweig unten, 1440x900:  730 Ueberdeckungen, Zoom 0,062
    //     mit ihm:                           0 Ueberdeckungen, lesbarer Ausschnitt
    //
    // Der Grund ist derselbe wie ueberall hier: Schrift und Portraits haengen
    // an einer festen BILDSCHIRMgroesse. Zoomt man heraus, ruecken sie
    // zusammen, ohne kleiner zu werden — bei 92 Knoten liegt am Ende alles
    // uebereinander. `loeseUeberdeckungen` kann das nicht auffangen, weil
    // jedes Auseinanderschieben das Netz wieder groesser macht und der
    // naechste Fit es erneut zusammenzieht.
    //
    // Der Zweig unten ist also kein Notbehelf, sondern die Antwort auf genau
    // diese Frage: Lieber ein lesbarer Ausschnitt als ein vollstaendiges Bild,
    // in dem nichts zu entziffern ist. Wer das Ganze sehen will, zoomt heraus
    // — dann ist es seine Entscheidung.
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
    hervorheben(null);
    aufPerson(null);
    // Zurueck aufs Ganze — sonst bliebe die Ansicht auf dem letzten
    // Angetippten stehen, obwohl nichts mehr ausgewaehlt ist.
    window.setTimeout(einpassen, 260);
  });
  // Der unfilterte Tipp plus Zielprüfung oben ist die Form, die Hintergrund und
  // Knoten wirklich unterscheidet — Cytoscapes 'core'-Selektor tut in diesem
  // Bundle das Gegenteil seines Namens (gemessen 2026-08-26,
  // frontend/static/quote-overlay.js).
  /** Fassen, sobald das Blatt wirklich steht.
   *
   * 🔴 SO OFT, BIS DAS FELD RUHT — und nicht einmal nach einer geschaetzten
   * Frist (gemessen 2026-09-03 auf 390x844): Nach 260 ms war das Blatt noch
   * 501 px hoch, nach 650 ms 400. `fasseAuf` lief also, rechnete mit einem
   * Feld, das es gleich nicht mehr gab, und p1 stand danach 76 px unter der
   * Kante. Ein Zaehler im Rumpf bewies dabei, dass die Funktion lief — der
   * Fehler lag nicht am Aufruf, sondern an dem, was sie mass.
   *
   * Warum die Frist nicht zu erraten ist: Die Hoehe des Blattes kommt aus
   * seinem INHALT (`max-height: 72%`), und der steht erst, wenn die Abschnitte
   * gebaut sind — mal drei Zeilen, mal dreissig. Gewartet wird deshalb auf das
   * Ergebnis, nicht auf die Uhr.
   *
   * Die Collection wird ERST HIER geholt und nicht beim Tippen: Ein Push
   * dazwischen kann Elemente ersetzt haben, und eine gehaltene Collection
   * zeigte dann auf Knoten, die nicht mehr im Netz stehen. */
  function nachFassen(knoten, versuche = 10) {
    const id = knoten.id();
    let letzte = null;
    const schritt = () => {
      const jetzt = cy.getElementById(id);
      if (!jetzt.length) return;
      const feld = freiesFeld();
      fasseAuf(jetzt.closedNeighborhood());
      // Ruht das Feld, ist die Rechnung endgueltig — sonst noch einmal.
      const ruht =
        letzte !== null && Math.abs(feld.w - letzte.w) < 1 && Math.abs(feld.h - letzte.h) < 1;
      letzte = feld;
      if (!ruht && --versuche > 0) window.setTimeout(schritt, 80);
    };
    window.setTimeout(schritt, 80);
  }

  /** Der Teil der Zeichenflaeche, den das Blatt NICHT verdeckt.
   *
   *  🔴 WOZU (gemessen 2026-09-03 auf 390x844): Das Blatt nimmt am Telefon bis
   *  zu 72 % der Hoehe. Das Netz lag bei y=248..562, das geoeffnete Blatt ab
   *  y=236 — die hervorgehobene Nachbarschaft war vollstaendig verdeckt, und
   *  das Blatt erklaerte etwas, das niemand sehen konnte. Dasselbe Problem hat
   *  die grosse Flaeche mit ihrer Tafel, und dieselbe Antwort: Das Netz weicht
   *  aus, statt ueberdeckt zu werden.
   *
   *  Gemessen am wirklich gerenderten Blatt und nicht an der Regel im
   *  Stylesheet: Ob es unten liegt oder seit dem Umbruch bei 900 px rechts,
   *  entscheidet das CSS — hier zaehlt nur, welches Rechteck uebrig bleibt. */
  function freiesFeld() {
    const flaeche = container.getBoundingClientRect();
    const blatt = document.getElementById('blatt');
    const feld = { x: 0, y: 0, w: flaeche.width, h: flaeche.height };
    if (!blatt || !blatt.classList.contains('offen')) return feld;
    const b = blatt.getBoundingClientRect();
    if (b.width === 0 || b.height === 0) return feld;
    // Waagerecht oder senkrecht daneben — je nachdem, welche Kante es teilt.
    const seitlich = b.width < flaeche.width * 0.9;
    if (seitlich) feld.w = Math.max(80, b.left - flaeche.left);
    else feld.h = Math.max(80, b.top - flaeche.top);
    return feld;
  }

  /** Auf eine Auswahl fassen — in das Feld, das das Blatt uebrig laesst.
   *
   *  Cytoscape kann kein ungleiches Polster, deshalb in drei Schritten: erst
   *  fassen wie gewohnt, dann den Zoom um das Verhaeltnis der Felder kuerzen,
   *  zuletzt den Mittelpunkt der Auswahl in die Mitte des freien Feldes
   *  schieben. */
  function fasseAuf(eles) {
    if (!eles || !eles.length) return;
    // 🔴 IN RUNDEN, aus demselben Grund wie `einpassen()`: `skaliere()` haelt
    // Portraits und Tafeln gegen den Zoom lesbar — sie werden also GROESSER,
    // wenn herausgezoomt wird. Eine einzelne Rechnung passt deshalb auf
    // Groessen, die es danach nicht mehr gibt (gemessen 2026-09-03: 2 von 3
    // hervorgehobenen Knoten lagen anschliessend doch unter dem Blatt).
    let vorher = 0;
    for (let runde = 0; runde < EINPASS_RUNDEN; runde++) {
      const feld = freiesFeld();
      cy.fit(eles, 24);
      skaliere();
      // 🔴 IN BILDSCHIRMPIXELN messen und nicht im Modell (gemessen
      // 2026-09-03: p1 lag 76 px unter der Feldkante). `skaliere()` haelt
      // Portraits und Tafeln auf einer festen Pixelgroesse — ihr Mass IM
      // MODELL waechst also beim Herauszoomen, und eine Modellbox sagt danach
      // nichts mehr darueber, wie viel Platz sie auf dem Schirm brauchen.
      let rb = eles.renderedBoundingBox({ includeLabels: true });
      const eng = Math.min(feld.w / rb.w, feld.h / rb.h, 1);
      if (eng < 0.999) {
        cy.zoom(cy.zoom() * eng);
        skaliere();
      }
      // Erst jetzt schieben — nach dem letzten `skaliere()`, sonst waere die
      // Mitte wieder die von vorher.
      rb = eles.renderedBoundingBox({ includeLabels: true });
      cy.panBy({
        x: feld.x + feld.w / 2 - (rb.x1 + rb.x2) / 2,
        y: feld.y + feld.h / 2 - (rb.y1 + rb.y2) / 2,
      });
      const jetzt = cy.zoom();
      if (vorher && Math.abs(jetzt - vorher) / vorher < EINPASS_GENAUIGKEIT) break;
      vorher = jetzt;
    }
  }

  /** Wie viele Knotenpaare sich ueberdecken, Beschriftungen eingerechnet. */
  function ueberdeckungen() {
    const boxen = cy.nodes().map((n) => n.boundingBox({ includeLabels: true }));
    let zahl = 0;
    for (let i = 0; i < boxen.length; i++) {
      for (let j = i + 1; j < boxen.length; j++) {
        const a = boxen[i];
        const b = boxen[j];
        if (
          Math.min(a.x2, b.x2) - Math.max(a.x1, b.x1) > 2 &&
          Math.min(a.y2, b.y2) - Math.max(a.y1, b.y1) > 2
        ) {
          zahl += 1;
        }
      }
    }
    return zahl;
  }

  /** Ueberdeckungen aufloesen — trennen und ein wenig spreizen im Wechsel.
   *
   * 🔴 BEIDES, weil keines allein genuegt (an der Wand gemessen, 2026-09-03):
   * Lokales Trennen haelt die Form, steckt aber fest, sobald es eng wird —
   * jeder Schub drueckt einen Nachbarn in einen dritten. Ein wenig Luft loest
   * die Klemme, und danach kommt das Trennen wieder voran. Spreizen allein
   * blaeht dagegen die ganze Wolke auf.
   *
   * Am Telefon wiegt das schwerer als an der Wand: Die Flaeche ist klein, und
   * seit die Schrift die Haeufigkeit traegt, sind die Tafeln unterschiedlich
   * gross geworden. */
  function loeseUeberdeckungen({ schritt = 1.08, runden = 8 } = {}) {
    trenneUeberlappende();
    for (let i = 0; i < runden; i += 1) {
      if (ueberdeckungen() === 0) return;
      const bb = cy.nodes().boundingBox();
      const mx = (bb.x1 + bb.x2) / 2;
      const my = (bb.y1 + bb.y2) / 2;
      cy.batch(() => {
        cy.nodes().forEach((n) => {
          const at = n.position();
          n.position({ x: mx + (at.x - mx) * schritt, y: my + (at.y - my) * schritt });
        });
      });
      trenneUeberlappende();
    }
  }

  /** Kollidierende Knoten auseinanderschieben, je Durchgang die halbe
   *  Ueberdeckung — wer mit mehreren zugleich kollidiert, schoesse sonst auf
   *  jedem einzeln ueber das Ziel hinaus. */
  function trenneUeberlappende(durchgaenge = 60) {
    const ns = cy.nodes();
    if (ns.length < 2) return;
    for (let d = 0; d < durchgaenge; d += 1) {
      const boxen = ns.map((n) => n.boundingBox({ includeLabels: true }));
      const schub = ns.map(() => ({ x: 0, y: 0 }));
      let etwas = false;
      for (let i = 0; i < boxen.length; i += 1) {
        for (let j = i + 1; j < boxen.length; j += 1) {
          const a = boxen[i];
          const b = boxen[j];
          const w = Math.min(a.x2, b.x2) - Math.max(a.x1, b.x1);
          const h = Math.min(a.y2, b.y2) - Math.max(a.y1, b.y1);
          if (w <= 0 || h <= 0) continue;
          etwas = true;
          // Auf der kuerzeren Achse trennen: der kuerzeste Weg aus der
          // Ueberdeckung heraus.
          const ax = (a.x1 + a.x2) / 2;
          const ay = (a.y1 + a.y2) / 2;
          const bx = (b.x1 + b.x2) / 2;
          const by = (b.y1 + b.y2) / 2;
          let vx = 0;
          let vy = 0;
          if (w < h) vx = (ax <= bx ? -w : w) * 0.25;
          else vy = (ay <= by ? -h : h) * 0.25;
          schub[i].x += vx;
          schub[i].y += vy;
          schub[j].x -= vx;
          schub[j].y -= vy;
        }
      }
      if (!etwas) return;
      cy.batch(() => {
        ns.forEach((n, i) => {
          const at = n.position();
          n.position({ x: at.x + schub[i].x, y: at.y + schub[i].y });
        });
      });
    }
  }

  /** Das Angetippte und seine direkten Verbindungen bleiben hell, der Rest
   *  tritt zurueck.
   *
   *  `closedNeighborhood()` ist genau die richtige Menge: der Knoten selbst,
   *  seine Kanten und was daran haengt. Bei einer Person sind das ihre
   *  Begriffe, bei einem Begriff alle, die ihn gesagt haben — also in beiden
   *  Faellen das, was das Blatt daneben aufzaehlt. Beide zeigen dasselbe. */
  let hervorgehoben = null;
  // 🔴 BEDEUTUNG IST DIE VORGABE (Birk, 2026-09-03: „der default soll bedeutung
  // sein"). Am Telefon sieht man einen Ausschnitt und selten das Ganze — dann
  // traegt die inhaltliche Nachbarschaft mehr als die soziale: Wer nebeneinander
  // steht, sagt Verwandtes, und das erklaert sich von selbst. Die Wand hat den
  // Platz fuer das andere Bild.
  let semantisch = true;

  /** Die Knoten auf die gewaehlte Anordnung setzen.
   *
   * EINE Stelle fuer beide Wege — sie wird beim Aufbau, bei jedem Push und beim
   * Umschalten gerufen. Sonst setzte `update()` die Positionen aus `x/y` zurueck
   * und die Bedeutungslage waere nach drei Sekunden wieder weg (derselbe
   * Fallstrick wie bei den Klassen, siehe `hervorhebungErneuern`).
   *
   * Ein Knoten ohne die gewaehlte Lage bleibt, wo er ist: Frueh am Tag gibt es
   * noch keine semantische Rechnung, und ein Sprung auf (0,0) waere schlimmer
   * als die alte Lage. */
  function anordnen({ sanft = false } = {}) {
    cy.batch(() => {
      cy.nodes().forEach((n) => {
        const x = semantisch ? n.data('sx') : n.data('gx');
        const y = semantisch ? n.data('sy') : n.data('gy');
        if (x === null || x === undefined || y === null || y === undefined) return;
        if (sanft) n.animate({ position: { x, y } }, { duration: 450, easing: 'ease-in-out' });
        else n.position({ x, y });
      });
    });
  }

  /** Ob es ueberhaupt etwas umzuschalten gibt. Frueh am Tag rechnet der Kern
   * noch keine Bedeutungslage — dann waere ein Knopf, der nichts tut,
   * schlimmer als keiner. */
  function hatBeideLagen() {
    return cy.nodes().some((n) => n.data('sx') !== null && n.data('sx') !== undefined);
  }

  function hervorheben(knoten) {
    // 🔴 DIE ID MERKEN, nicht die Collection: Ein Push kann Elemente ersetzen,
    // und eine gehaltene Collection zeigte danach auf Knoten, die es nicht
    // mehr gibt.
    hervorgehoben = knoten && knoten.length ? knoten.id() : null;
    cy.elements().removeClass('abseits');
    if (!hervorgehoben) return;
    const nah = knoten.closedNeighborhood();
    cy.elements().difference(nah).addClass('abseits');
  }

  /** Die Hervorhebung nach einem Push wiederherstellen.
   *
   * 🔴 GEMESSEN 2026-09-03: `update()` setzt die Klassen jedes vorhandenen
   * Elements neu (`vorhanden.classes(...)`) — und warf `.abseits` damit weg.
   * Der Spiegel holt alle drei Sekunden; die Hervorhebung ueberlebte also
   * keine drei Sekunden, waehrend das Blatt daneben stehen blieb. Beim ersten
   * Messen sah es richtig aus, weil der Screenshot vor dem naechsten Push fiel.
   *
   * Ist der Knoten inzwischen weg (zusammengelegt, weggefiltert), faellt die
   * Hervorhebung ganz — dasselbe wie ein Tipp ins Leere. */
  function hervorhebungErneuern() {
    if (!hervorgehoben) return;
    const knoten = cy.getElementById(hervorgehoben);
    if (!knoten.length) {
      hervorgehoben = null;
      cy.elements().removeClass('abseits');
      return;
    }
    hervorheben(knoten);
  }

  cy.on('tap', 'node.person', (ereignis) => {
    const knoten = ereignis.target;
    hervorheben(knoten);
    aufPerson(knoten.id());
    // 🔴 NACH `aufPerson`: Erst dann steht das Blatt offen, und erst dann
    // weiss `freiesFeld()`, wie viel Platz bleibt. Davor gefasst, rahmte es
    // auf die ganze Flaeche — also genau auf den Bereich, der gleich verdeckt
    // ist. Die 260 ms sind die Uebergangszeit des Blattes (graph.css) plus
    // ein Frame Luft.
    nachFassen(knoten);
  });
  // 🔴 Und auf einen BEGRIFF (Birk, 2026-09-02). Gemessen am echten Stand auf
  // 390x844: Ein Fingertipp auf ein Portrait landete auf einem BEGRIFF — vier
  // Knoten lagen an derselben Stelle uebereinander. Begriffe waren nicht
  // anklickbar, also passierte gar nichts, und die Seite wirkte tot.
  cy.on('tap', 'node.term', (ereignis) => {
    const knoten = ereignis.target;
    hervorheben(knoten);
    aufBegriff(knoten.id());
    nachFassen(knoten);
  });

  return {
    cy,
    einpassen,
    ersteAnsicht,
    hervorheben,
    hatBeideLagen,
    /** Alles neu messen, weil sich die Zielmaße geaendert haben.
     *
     * Die Tafelmasse stecken in den Knotendaten (`boxW`/`boxH`) und werden
     * beim Aufbau einmal gerechnet — nach einem Wechsel zwischen mobilen und
     * Laptop-Massen sind sie falsch. Danach neu anordnen, aufraeumen und
     * einpassen, in dieser Reihenfolge. */
    neuVermessen() {
      cy.batch(() => {
        cy.nodes('.term').forEach((n) => {
          const mass = tafelMass(n.data('label') || '', haeufigSchrift(n.data('mentions')));
          n.data({ boxW: mass.w, boxH: mass.h });
        });
      });
      anordnen();
      skaliere();
      if (ueberdeckungen() > 0) loeseUeberdeckungen();
      einpassen();
    },
    get semantisch() {
      return semantisch;
    },
    /** Umschalten zwischen den beiden Anordnungen. Sanft, weil ein Sprung von
     * siebzig Knoten auf einmal nicht zu lesen ist — man soll sehen, WOHIN
     * etwas wandert. */
    setzeAnordnung(nachBedeutung) {
      if (semantisch === nachBedeutung) return;
      semantisch = nachBedeutung;
      anordnen({ sanft: true });
      // Erst wenn die Bewegung steht — sonst raeumte es Positionen auf, die
      // sich gerade noch veraendern (die Animation laeuft 450 ms).
      window.setTimeout(() => {
        if (ueberdeckungen() > 0) loeseUeberdeckungen();
        einpassen();
      }, 500);
    },
    fasseAuf,
    freiesFeld,
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
      // Erst die Lage, dann die Masse: `skaliere()` und `ersteAnsicht()`
      // rechnen beide mit den Positionen.
      anordnen();
      skaliere();
      // 🔴 NACH `skaliere()`: Die Tafelmasse haengen an der Schriftgroesse und
      // die an der Haeufigkeit — vorher gemessen waeren es die Masse von
      // gestern. Und nur, wenn es etwas zu tun gibt: Der Vergleich kostet
      // nichts, das Verschieben schon.
      if (ueberdeckungen() > 0) loeseUeberdeckungen();
      // 🔴 EIN EIGENES EREIGNIS, weil `add`/`remove` hier nicht genuegt
      // (gefunden 2026-09-03): Kommt derselbe Knoten mit ANDEREN Daten wieder —
      // etwa ohne Bedeutungslage, weil der Kern sie frueh am Tag noch nicht
      // rechnet —, aendert sich am Bestand der Elemente nichts, und die Seite
      // erfuehre nie davon. Wer auf den Stand des Netzes reagieren will, hoert
      // hierauf und nicht auf einen bestimmten Datenweg.
      cy.emit('kg-aktualisiert');
      // Und die Hervorhebung zurueckholen, die `classes(...)` oben mitgenommen
      // hat — sonst steht das Blatt offen vor einem Netz, in dem nichts mehr
      // hervorgehoben ist (gemessen 2026-09-03).
      hervorhebungErneuern();
      if (ersteZeichnung && cy.nodes().length) {
        ersteZeichnung = false;
        ersteAnsicht();
      }
    },
  };
}
