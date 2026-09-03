// Spec §7. Display settings and flow control — and nothing that could change
// the visual register or the weighting at runtime. (Die Leitfrage stand hier
// bis zum 2026-08-31 unveränderbar zum Nachlesen; sie ist ersatzlos entfallen,
// weil sie nichts mehr steuerte und eine nie gestellte Frage zeigte.)

// The last state the server actually CONFIRMED, not merely what we tried to
// send. post() reverts to this on failure, which is this exhibition's only
// feedback for a write the server never acknowledged: no toast, no banner,
// just the control snapping back to the truth. Copied from Tool 1's operator
// UI on purpose — same surface, same stakes.
let lastState = null;

function post(url, body) {
  return fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body || {}),
  })
    .then((response) => {
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    })
    .catch((error) => {
      console.warn(`request to ${url} failed`, error);
      if (lastState) render(lastState);
    });
}

function display(patch) {
  return post('/api/display', patch);
}

function dreamRow(dream) {
  const item = document.createElement('li');
  item.id = `dream-${dream.id}`;
  item.className = [dream.discarded ? 'discarded' : '', dream.status].filter(Boolean).join(' ');

  const image = document.createElement('img');
  if (dream.image) image.src = dream.image;
  image.alt = '';
  item.appendChild(image);

  const body = document.createElement('div');
  const sentence = document.createElement('div');
  sentence.className = 'sentence';
  sentence.textContent = dream.sentence || '—';
  body.appendChild(sentence);

  const meta = document.createElement('div');
  meta.className = 'meta';
  const when = new Date(dream.created_at * 1000).toLocaleTimeString('de-DE');
  meta.textContent =
    `${when} · ${dream.person_count} Menschen, ${dream.term_count} Begriffe · ` +
    `${dream.contradiction ? 'mit Widerspruch' : 'ohne Widerspruch'}` +
    `${dream.discarded ? ' · verworfen' : ''}`;
  body.appendChild(meta);

  if (dream.error) {
    const error = document.createElement('div');
    error.className = 'error';
    error.textContent = dream.error;
    body.appendChild(error);
  }

  // The image prompt lives HERE and only here (spec §5.2): showing it on the
  // wall would put lighting instructions in front of visitors.
  if (dream.stage2_prompt) {
    const prompt = document.createElement('div');
    prompt.className = 'prompt';
    prompt.textContent = dream.stage2_prompt;
    body.appendChild(prompt);
  }
  item.appendChild(body);

  const button = document.createElement('button');
  button.className = 'discard';
  button.textContent = dream.discarded ? 'zurückholen' : 'verwerfen';
  button.addEventListener('click', () =>
    post('/api/discard', { dream_id: dream.id, discarded: !dream.discarded }),
  );
  item.appendChild(button);
  return item;
}

function render(state) {
  lastState = state;

  document.getElementById('fade-ms').value = String(state.fade_ms);
  document.getElementById('strip-ratio').value = String(state.strip_ratio);
  document.getElementById('strip-max').value = String(state.strip_max);
  document.getElementById('typewriter').checked = Boolean(state.typewriter);
  // Vorgabe an, nicht aus: Fehlt das Feld (aelterer Kern), soll der Haken
  // zeigen, was die Wand dann tut — und die blaettert.
  document.getElementById('slideshow').checked = state.slideshow !== false;

  // One button that says what it will DO, not what the state IS — the operator
  // is reaching for it in a hurry.
  document.getElementById('pause').textContent = state.paused ? 'Weiter' : 'Pause';

  const discard = document.getElementById('discard-current');
  discard.disabled = !state.current;
  discard.dataset.dreamId = state.current ? state.current.id : '';
}

function renderDreams(dreams) {
  const list = document.getElementById('dreams');
  list.replaceChildren();
  // Newest first: the operator reaches for the dream that is on screen NOW.
  // (The WALL runs oldest-first — that is a time axis, this is a work list.)
  dreams
    .slice()
    .sort((a, b) => b.created_at - a.created_at)
    .forEach((dream) => list.appendChild(dreamRow(dream)));
}

// -- Werkstatt-Tab (Birk, 2026-08-30) --------------------------------------
// Zeigt neben dem Bild, WORAUS es entstanden ist: Satz, Bildbeschreibung,
// benannter Widerspruch, mood/tension und die beiden vollstaendigen Prompts.
// Dieselbe Frage, die sim/probes/durchklick.py fuer Testlaeufe beantwortet,
// hier aber ueber die echten Traeume — die Sonde bleibt fuer Renderreihen
// ausserhalb der Installation, dieser Tab ist fuer den Ausstellungstag.
//
// Verworfene und fehlgeschlagene Traeume bleiben drin: Gerade der Traum, der
// schiefging, ist der, dessen Prompt man sehen will.
let werkTraeume = [];
let werkIndex = 0;

/** Die Begriffe, die in ein Bild sollten — aus dem gespeicherten Stufe-1-Prompt.
 *
 * 🔴 GELESEN, NICHT GESPEICHERT (Birk, 2026-09-02: „die Werkstatt sollte auch
 * die Begriffe anzeigen, die in das Bild sollten"). Eine eigene Spalte waere
 * sauberer, aber `kg2/store.py` hat keine Nachruestung fuer neue Spalten —
 * eine Schemaaenderung am Ausstellungstag ist das falsche Risiko. Der Prompt
 * ist ohnehin wortwoertlich aufbewahrt (Spec §5.3, „ein Satz ohne den Prompt,
 * der ihn erzeugt hat, laesst sich hinterher nicht erklaeren"), und die
 * Listen darin tragen feste Ueberschriften.
 *
 * Scheitert das Lesen, wird NICHTS angezeigt statt etwas Falschem: Das ist
 * eine Anzeige, kein Verhalten — ein leeres Feld kostet nichts, eine
 * erfundene Begriffsliste waere eine Lüge ueber das Bild daneben.
 */
function werkBegriffe(prompt) {
  if (typeof prompt !== 'string') return null;
  const listeNach = (ueberschrift) => {
    const i = prompt.indexOf(ueberschrift);
    if (i < 0) return [];
    // Die Liste beginnt hinter dem Doppelpunkt der Ueberschrift und endet an
    // der ersten Leerzeile.
    const ab = prompt.indexOf(':\n', i);
    if (ab < 0) return [];
    const block = prompt.slice(ab + 2).split('\n\n')[0];
    return block
      .split('\n')
      .map((z) => z.trim())
      .filter((z) => z)
      // „Lehmhaus (1× genannt)" -> „Lehmhaus"
      .map((z) => z.replace(/\s*\(\d+×[^)]*\)\s*$/, ''));
  };
  const pflicht = listeNach('DIESE BEGRIFFE MÜSSEN INS BILD');
  const rand = listeNach('Randnotizen');
  if (!pflicht.length && !rand.length) return null;
  return { pflicht, rand };
}

function werkZeige(index) {
  const inhalt = document.getElementById('werk-inhalt');
  const leer = document.getElementById('werk-leer');
  if (!werkTraeume.length) {
    if (inhalt) inhalt.hidden = true;
    if (leer) leer.hidden = false;
    const pos = document.getElementById('werk-position');
    if (pos) pos.textContent = '';
    return;
  }
  werkIndex = Math.max(0, Math.min(index, werkTraeume.length - 1));
  const traum = werkTraeume[werkIndex];
  if (leer) leer.hidden = true;
  if (inhalt) inhalt.hidden = false;

  const setze = (id, text) => {
    const el = document.getElementById(id);
    if (el) el.textContent = text || '—';
  };
  const bild = document.getElementById('werk-bild');
  if (bild) {
    bild.src = traum.image || '';
    bild.hidden = !traum.image;
  }
  setze('werk-satz', traum.sentence);
  const zeit = new Date(traum.created_at * 1000).toLocaleTimeString('de-DE');
  setze(
    'werk-meta',
    `${zeit} · ${traum.person_count} Personen · ${traum.term_count} Begriffe` +
      (traum.status !== 'ok' ? ` · ${traum.status}` : '') +
      (traum.discarded ? ' · verworfen' : ''),
  );
  const begriffe = werkBegriffe(traum.stage1_prompt);
  const feld = document.getElementById('werk-begriffe');
  if (feld) {
    feld.replaceChildren();
    if (begriffe) {
      const zeile = (titel, liste) => {
        if (!liste.length) return;
        const d = document.createElement('div');
        const b = document.createElement('strong');
        b.textContent = `${titel} `;
        d.appendChild(b);
        d.appendChild(document.createTextNode(liste.join(' · ')));
        feld.appendChild(d);
      };
      zeile('Pflicht:', begriffe.pflicht);
      zeile('Rand:', begriffe.rand);
    } else {
      feld.textContent = '—';
    }
  }
  setze('werk-motiv', traum.image_description || traum.sentence_en);
  setze('werk-widerspruch', traum.tension_source);
  setze(
    'werk-werte',
    `mood ${traum.mood ?? '—'} · tension ${traum.tension ?? '—'}` +
      (traum.condense_model ? ` · ${traum.condense_model} → ${traum.image_model || '—'}` : ''),
  );
  setze('werk-prompt1', traum.stage1_prompt);
  setze('werk-prompt2', traum.stage2_prompt);
  setze('werk-position', `${werkIndex + 1} von ${werkTraeume.length}`);
}

function werkSetze(dreams) {
  // Aeltester zuerst: der Werkstatt-Tab ist eine Zeitachse durch den Tag,
  // keine Arbeitsliste. Beim ersten Laden steht der neueste Traum vorn, weil
  // das der ist, der gerade an der Wand haengt.
  const vorher = werkTraeume.length;
  werkTraeume = dreams.slice().sort((a, b) => a.created_at - b.created_at);
  werkZeige(vorher === 0 ? werkTraeume.length - 1 : werkIndex);
}

function refreshDreams() {
  return fetch('/api/dreams')
    .then((response) => response.json())
    .then((payload) => {
      const dreams = payload.dreams || [];
      renderDreams(dreams);
      werkSetze(dreams);
    })
    .catch((error) => console.warn('could not load the dream record', error));
}

document
  .getElementById('fade-ms')
  .addEventListener('change', (event) => display({ fade_ms: Number(event.target.value) }));
document
  .getElementById('strip-ratio')
  .addEventListener('change', (event) => display({ strip_ratio: Number(event.target.value) }));
document
  .getElementById('strip-max')
  .addEventListener('change', (event) => display({ strip_max: Number(event.target.value) }));
document
  .getElementById('typewriter')
  .addEventListener('change', (event) => display({ typewriter: event.target.checked }));
document
  .getElementById('slideshow')
  .addEventListener('change', (event) => display({ slideshow: event.target.checked }));

document.getElementById('dream-now').addEventListener('click', () => post('/api/dream_now'));
document
  .getElementById('pause')
  .addEventListener('click', () => post('/api/pause', { paused: !(lastState && lastState.paused) }));
document.getElementById('discard-current').addEventListener('click', (event) => {
  const id = event.currentTarget.dataset.dreamId;
  if (id) post('/api/discard', { dream_id: id, discarded: true });
});

document.querySelectorAll('.tab').forEach((knopf) => {
  knopf.addEventListener('click', () => {
    const ziel = knopf.dataset.tab;
    document.querySelectorAll('.tab').forEach((k) => k.classList.toggle('on', k === knopf));
    document.getElementById('tab-steuerung').hidden = ziel !== 'steuerung';
    document.getElementById('tab-werkstatt').hidden = ziel !== 'werkstatt';
  });
});
document.getElementById('werk-prev').addEventListener('click', () => werkZeige(werkIndex - 1));
document.getElementById('werk-next').addEventListener('click', () => werkZeige(werkIndex + 1));
// Die Pfeiltasten nur, wenn die Werkstatt sichtbar ist: im Steuerungs-Tab
// stehen Zahlenfelder, und dort verstellen Pfeiltasten Werte.
addEventListener('keydown', (event) => {
  if (document.getElementById('tab-werkstatt').hidden) return;
  if (event.target && /^(INPUT|TEXTAREA)$/.test(event.target.tagName)) return;
  if (event.key === 'ArrowLeft') werkZeige(werkIndex - 1);
  if (event.key === 'ArrowRight') werkZeige(werkIndex + 1);
});

window.kgDreamOperator = { render, renderDreams, refreshDreams, werkSetze, werkZeige };

const events = new EventSource('/events');
events.onmessage = (message) => {
  const payload = JSON.parse(message.data);
  if (payload.type === 'state') {
    render(payload.state);
    refreshDreams();
  }
};
