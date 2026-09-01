// Bedienfeld für die Plenarfläche (Birk, 2026-09-01: „Eigenes Operator-Panel
// mit großen Slidern. Getrennt vom bestehenden, damit die Foyer-Einstellungen
// unberührt bleiben.").
//
// ## Warum eine eigene Seite und nicht ein zweiter Block in /operator
//
// Die Trennung IST die Anforderung. Zwei Sätze Regler auf einer Seite wären
// genau der Griff, den Birk ausgeschlossen haben will: Wer im Saal am Zoom
// dreht, darf den Zoom im Foyer nicht erwischen — und das Foyer ist heute
// mühsam kalibriert worden. Getrennte Seiten machen den Fehler unmöglich
// statt unwahrscheinlich.
//
// ## Warum die Seite sich selbst baut
//
// Die Regler stehen nicht im HTML, sondern kommen aus `GET /api/plenum/regler`
// — derselben Tabelle, gegen die der Server prüft (`PLENUM_REGLER` in
// kg/server.py). Damit gibt es keine zweite Stelle mit Bereichen und
// Schrittweiten, die auseinanderlaufen kann. Genau das ist hier schon
// passiert: `portrait_size` stand am 2026-09-01 mit max 260 im Markup,
// während der Server längst 700 erlaubte, und Birk stand vor Ort am Anschlag
// und meldete „der Regler hat keinen Einfluss".
//
// Geteilt wird mit `operator.js` bewusst NICHTS außer dem Stylesheet: Diese
// Seite anzufassen darf die Foyer-Bedienung nie berühren. Die einzige
// Dopplung ist die `post()`-Hülle unten (zwölf Zeilen) — ein gemeinsames
// Modul dafür hieße, `operator.js` umzubauen, und das ist der Preis nicht
// wert, solange die Ausstellung morgen ist.

/** Die zuletzt vom Server bestätigten Saalwerte. Ein fehlgeschlagener Post
 * springt hierhin zurück — dieselbe Rückmeldung wie im Foyer-Bedienfeld: kein
 * Banner, sondern ein Regler, der auf die Wahrheit zurückschnappt. */
let stand = {};
/** Die Reglertabelle vom Server, in Anzeigereihenfolge. */
let tabelle = [];

function post(key, value) {
  return fetch('/api/plenum', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ key, value }),
  })
    .then((antwort) => {
      if (!antwort.ok) throw new Error(`${antwort.status} ${antwort.statusText}`);
    })
    .catch((fehler) => {
      console.warn(`Regler ${key} konnte nicht gesetzt werden`, fehler);
      anzeigen(stand);
    });
}

/** Wie viele Nachkommastellen ein Regler zeigt — abgeleitet aus seiner
 * Schrittweite, nicht pro Regler gepflegt. Ein Schritt von 0,05 braucht zwei
 * Stellen, ein Schritt von 5 keine. */
function stellen(regler) {
  const schritt = Number(regler.schritt);
  if (!(schritt > 0) || schritt >= 1) return 0;
  return String(schritt).split('.')[1]?.length || 2;
}

/** Der Wert, wie ihn jemand im Saal liest: deutsches Komma, feste Stellenzahl,
 * Einheit dahinter. „1,80×" statt „1.8000000000000003×". */
function wertText(regler, wert) {
  if (regler.typ === 'auswahl') {
    const i = regler.auswahl.indexOf(wert);
    return i >= 0 ? regler.beschriftungen[i] : String(wert);
  }
  const zahl = Number(wert);
  if (!Number.isFinite(zahl)) return '—';
  const n = stellen(regler);
  const text = zahl.toFixed(n).replace('.', ',');
  return regler.einheit ? `${text} ${regler.einheit}`.replace(' ×', '×') : text;
}

function zeile(regler) {
  const reihe = document.createElement('div');
  reihe.className = 'regler-zeile';
  reihe.dataset.key = regler.key;

  const name = document.createElement('label');
  name.className = 'regler-name';
  name.htmlFor = `regler-${regler.key}`;
  name.textContent = regler.label;
  const hinweis = document.createElement('span');
  hinweis.className = 'regler-hinweis';
  hinweis.textContent = regler.hinweis || '';
  name.appendChild(hinweis);
  reihe.appendChild(name);

  let feld;
  if (regler.typ === 'auswahl') {
    feld = document.createElement('select');
    regler.auswahl.forEach((wert, i) => {
      const option = document.createElement('option');
      option.value = wert;
      option.textContent = regler.beschriftungen[i] || wert;
      feld.appendChild(option);
    });
  } else {
    feld = document.createElement('input');
    feld.type = 'range';
    feld.min = regler.min;
    feld.max = regler.max;
    feld.step = regler.schritt;
  }
  feld.id = `regler-${regler.key}`;
  feld.dataset.key = regler.key;
  reihe.appendChild(feld);

  const wert = document.createElement('output');
  wert.className = 'regler-wert';
  wert.dataset.wertFuer = regler.key;
  // Bei einer Auswahlliste steht der Wert schon IN der Liste. Ihn daneben zu
  // wiederholen sagt nichts und liest sich wie zwei verschiedene Angaben.
  if (regler.typ === 'auswahl') wert.hidden = true;
  reihe.appendChild(wert);

  // Zwei Zuhörer, wie im Foyer-Bedienfeld und aus demselben Grund: `input`
  // feuert bei jedem Pixel des Ziehens und aktualisiert nur die Zahl daneben,
  // damit sie der Hand folgt. Gepostet wird erst beim Loslassen (`change`) —
  // ein Post pro Pixel schickte an jede angeschlossene Fläche eine
  // Zustandsmeldung, dutzendfach pro Sekunde.
  feld.addEventListener('input', () => {
    wert.textContent = wertText(regler, feld.value);
  });
  feld.addEventListener('change', () => post(regler.key, feld.value));
  return reihe;
}

/** Die Regler auf einen Zustand stellen. */
function anzeigen(werte) {
  for (const regler of tabelle) {
    const feld = document.getElementById(`regler-${regler.key}`);
    const wert = document.querySelector(`[data-wert-fuer="${regler.key}"]`);
    if (!feld || !wert) continue;
    // Einen Regler, der gerade unter der Hand liegt, nicht wegziehen. Eine
    // Zustandsmeldung kommt auch dann, wenn jemand anders etwas verstellt hat
    // — der Daumen dürfte darüber nicht springen.
    if (feld === document.activeElement) continue;
    const aktuell = werte[regler.key];
    if (aktuell === undefined) continue;
    feld.value = String(aktuell);
    wert.textContent = wertText(regler, aktuell);
  }
}

function bauen(regler) {
  tabelle = regler;
  const ziel = document.getElementById('regler');
  ziel.replaceChildren();
  for (const eintrag of regler) ziel.appendChild(zeile(eintrag));
  anzeigen(stand);
}

// Erst die Tabelle, dann der Zustand. Käme es andersherum, stünde der erste
// Push vor leeren Reglern und würde verworfen — `anzeigen()` läuft deshalb
// auch am Ende von `bauen()`.
fetch('/api/plenum/regler')
  .then((antwort) => antwort.json())
  .then((daten) => bauen(daten.regler))
  .catch((fehler) => {
    console.warn('Reglertabelle nicht erreichbar', fehler);
    document.querySelector('.laedt').textContent =
      'Die Reglertabelle ist nicht erreichbar — läuft die Station?';
  });

const events = new EventSource('/events');
events.onmessage = (meldung) => {
  const inhalt = JSON.parse(meldung.data);
  if (inhalt.type !== 'state') return;
  // Nur der Saal-Block. Alles andere im Zustand gehört dem Foyer-Bedienfeld,
  // und diese Seite fasst es nicht an — auch nicht lesend, damit gar nicht
  // erst der Eindruck entsteht, sie zeige es.
  stand = inhalt.state.plenum || {};
  anzeigen(stand);
};

window.kgOperatorPlenum = { anzeigen, bauen, wertText, get tabelle() { return tabelle; } };
