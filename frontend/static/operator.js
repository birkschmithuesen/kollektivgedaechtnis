// One action per entry: hide. No approving, no editing, no queue (spec 8).

import { selectVisibleTermIds } from './graph-model.js';

// The last graph/state a render() call actually received — from the server,
// via /events, not merely attempted. post() reverts to these on failure, so
// this is the exhibition's only feedback for a control the server never
// confirmed (see the catch below): no toast/banner, just the control
// snapping back to the truth.
let lastGraph = { nodes: [], edges: [], quotes: [] };
let lastState = {
  max_terms: 32,
  camera_mode: 'fit',
  camera_zoom: 1,
  camera_speed: 1,
  portrait_size: 120,
  stt_connected: false,
  interview: null,
};

function post(url, body) {
  return fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
    .then((response) => {
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    })
    .catch((error) => {
      // This is the sole human control surface for the exhibition: a write
      // that the server never confirmed must not leave the operator staring
      // at a control showing a change that did not happen.
      console.warn(`request to ${url} failed`, error);
      render(lastGraph, lastState);
    });
}

/** How a person reads in the list. They carry no label — only a portrait and
 * the moment the photo was taken (`created_at`, the interview's start).
 *
 * The portrait is the identification; the time is what tells two portraits of
 * the same room apart, and it is the one thing an operator standing at the
 * station can match against their own clock ("the one from just before three").
 * Hours and minutes, nothing finer: seconds are noise at this resolution. */
function personLabel(node) {
  const seconds = Number(node.created_at);
  if (!Number.isFinite(seconds) || seconds <= 0) return 'Person';
  const time = new Date(seconds * 1000).toLocaleTimeString('de-DE', {
    hour: '2-digit',
    minute: '2-digit',
  });
  return `Person ${time}`;
}

/** The second identifying mark: how many terms hang off this person.
 *
 * "keine Begriffe" is exactly what a test portrait from the morning's setup
 * looks like (nobody spoke to it) — the case Birk could not get off the wall
 * on 2026-08-30. It is also the honest answer while an interview is still
 * being condensed, so it must not read as an error. */
function termCountText(count) {
  if (count === 0) return 'keine Begriffe';
  return count === 1 ? '1 Begriff' : `${count} Begriffe`;
}

/** Die Personenzeile trägt statt eines Labels ein Namensfeld.
 *
 * Der Name kommt aus dem Transkript — die Person stellt sich zu Beginn des
 * Interviews vor — und die Spracherkennung verhört Namen zuverlässiger als
 * alles andere. Korrigiert wird deshalb genau dort, wo die Person in dieser
 * Liste ohnehin identifiziert wird: neben ihrem Porträt.
 *
 * Ohne Namen bleibt das Feld leer und der `placeholder` zeigt weiter die
 * Uhrzeit-Kennung von `personLabel()`. Eine namenlose Zeile bleibt damit
 * genauso wiederzufinden wie vor dieser Änderung („die von kurz vor drei"),
 * und der leere Kasten sagt zugleich, dass hier etwas fehlt, das man
 * hinschreiben darf.
 */
function nameField(node, draft) {
  const field = document.createElement('input');
  field.type = 'text';
  // Behält die Label-Klasse: Das Feld steht an der Stelle des Labels, nimmt
  // dessen Breite in der Zeile ein und wird beim Ausblenden mit durchgestrichen.
  field.className = 'label name';
  field.dataset.nameFor = node.id;
  field.placeholder = personLabel(node);
  field.maxLength = 120; // dieselbe Grenze wie PersonName.name im Server
  // Ein laufender Entwurf schlägt den Servertext: siehe editingDraft() unten.
  field.value = draft && draft.personId === node.id ? draft.value : node.name || '';

  // Gespeichert wird beim Verlassen des Feldes, nicht beim Tippen. `input`
  // würde pro Tastendruck feuern und damit pro Buchstabe eine Graph-Rundmeldung
  // an jeden SSE-Client schicken — dieselbe Überlegung wie bei den Reglern
  // (frontend/operator.html) und mit derselben Antwort: `change`.
  field.addEventListener('change', () =>
    post('/api/person_name', { person_id: node.id, name: field.value.trim() }),
  );
  // Enter heißt „fertig" und wird deshalb genau darauf abgebildet: Das Feld
  // gibt den Fokus ab, der Browser feuert daraufhin `change` — einmal, und nur
  // wenn sich wirklich etwas geändert hat. Hier selbst zu posten würde bei
  // geändertem Wert zweimal speichern, und der Fokus bliebe im Feld: Eine
  // fehlgeschlagene Speicherung ließe den falschen Text dann stehen, statt ihn
  // wie jeden anderen Bedienschritt auf den Serverstand zurückspringen zu
  // lassen (siehe post()).
  field.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') field.blur();
  });
  return field;
}

function entryRow(node, termCounts, draft) {
  const item = document.createElement('li');
  item.className = `entry ${node.type} ${node.hidden ? 'hidden' : ''}`.trim();
  item.id = `entry-${node.id}`;

  if (node.type === 'person' && node.portrait) {
    const portrait = document.createElement('img');
    portrait.className = 'portrait';
    portrait.src = node.portrait;
    // Decorative in this row: the text next to it already names the person and
    // the time, and no screen reader is at the station anyway.
    portrait.alt = '';
    item.appendChild(portrait);
  }

  if (node.type === 'person') {
    item.appendChild(nameField(node, draft));
  } else {
    const label = document.createElement('span');
    label.className = 'label';
    label.textContent = node.label;
    item.appendChild(label);
  }

  const meta = document.createElement('span');
  meta.className = 'meta';
  meta.textContent =
    node.type === 'person' ? termCountText(termCounts.get(node.id) || 0) : `${node.mentions}×`;
  item.appendChild(meta);

  const button = document.createElement('button');
  button.className = 'hide';
  button.textContent = node.hidden ? 'einblenden' : 'ausblenden';
  button.addEventListener('click', () =>
    post('/api/hidden', { node_id: `${node.type}:${node.id}`, hidden: !node.hidden }),
  );
  item.appendChild(button);
  return item;
}

/** Append to each cap step how many terms it would actually leave on the wall.
 *
 * The count used to sit on the touchscreen's own density buttons; it followed
 * the dial here when the visitor controls lost it (2026-08-26), because the
 * knowledge behind it must not be lost with them: a step with nothing behind
 * it empties the wall and reads as a broken control unless it says so first.
 * Also catches the case a plain cap number cannot show on its own: "alle"
 * (999) on a graph with only 14 terms still says "alle (14)", not "alle
 * (999)".
 *
 * Counted the way the wall counts — hidden terms are not on it, so they are in
 * no step. Deliberately not the operator list's own rule below, which keeps
 * hidden entries so "einblenden" stays reachable; that is a different question
 * from "what would the room see". Same selection rule the wall itself applies
 * (`graph-model.js`), so the number is never a different count than what a
 * visitor would actually see at that step. */
function showDensityCounts(graph) {
  const terms = (graph.nodes || []).filter((node) => node.type === 'term');
  for (const option of document.getElementById('max-terms').options) {
    // The markup's text is the base label. Cached on first pass so a second
    // render appends to the label, not to the label plus its last count.
    if (option.dataset.label === undefined) option.dataset.label = option.textContent;
    const cap = Number(option.value);
    const count = selectVisibleTermIds(terms, cap).size;
    option.textContent = `${option.dataset.label} (${count})`;
  }
}

/** Was gerade in ein Namensfeld getippt wird — oder `null`, wenn keines den
 * Fokus hat.
 *
 * Die Liste wird bei JEDEM Push komplett neu gebaut (`replaceChildren()`
 * unten). Für einen Knopf ist das folgenlos, für ein Textfeld nicht: Ein Push
 * mitten im Tippen — ein beendetes Interview, ein anderer Bedienschritt, die
 * eigene Speicherung — ersetzte sonst das halbfertige Wort durch den
 * Servertext und schöbe den Cursor in eine Zeile, die es nicht mehr gibt.
 * Genau das ist am Bedienpult nicht theoretisch: Interviews landen im Minutentakt.
 *
 * Also merkt sich render() vor dem Neubau dieses eine Feld mit Inhalt und
 * Cursorposition und stellt es danach wieder her. Der Servertext gewinnt
 * wieder, sobald das Feld den Fokus abgibt — dann ist gespeichert und beide
 * sagen ohnehin dasselbe. Der Entwurf wird bewusst NICHT global gehalten,
 * sondern pro Neubau frisch aus dem Dokument gelesen: So kann er nicht länger
 * leben als der Fokus, den er beschreibt. */
function editingDraft(list) {
  const active = document.activeElement;
  if (!active || active.dataset?.nameFor === undefined || !list.contains(active)) return null;
  return {
    personId: active.dataset.nameFor,
    value: active.value,
    start: active.selectionStart,
    end: active.selectionEnd,
  };
}

function restoreDraft(list, draft) {
  if (!draft) return;
  const field = list.querySelector(`input[data-name-for="${draft.personId}"]`);
  // Die Person kann inzwischen aus der Liste verschwunden sein. Dann gibt es
  // nichts wiederherzustellen — und nichts, was der Operator dort noch tippen
  // könnte.
  if (!field) return;
  field.focus();
  field.setSelectionRange(draft.start, draft.end);
}

function render(graph, state) {
  lastGraph = graph;
  lastState = state;

  document.getElementById('max-terms').value = String(state.max_terms);
  showDensityCounts(graph);
  document.getElementById('camera').value = state.camera_mode;
  document.getElementById('camera-zoom').value = String(state.camera_zoom ?? 1);
  showZoomValue(state.camera_zoom ?? 1);
  document.getElementById('camera-speed').value = String(state.camera_speed ?? 1);
  showSpeedValue(state.camera_speed ?? 1);
  document.getElementById('portrait-size').value = String(state.portrait_size ?? 120);
  showPortraitSizeValue(state.portrait_size ?? 120);
  document.getElementById('stt').classList.toggle('ok', Boolean(state.stt_connected));
  document.getElementById('interview').textContent = state.interview
    ? 'Interview läuft'
    : 'kein Interview';

  const list = document.getElementById('entries');
  const draft = editingDraft(list);
  list.replaceChildren();

  // How many terms each person carries, for their row's meta text. One pass
  // over the edges; every edge in this graph runs person -> term.
  const termCounts = new Map();
  for (const edge of graph.edges || []) {
    termCounts.set(edge.source, (termCounts.get(edge.source) || 0) + 1);
  }

  // Persons first, newest recording first. Two reasons for the order, both
  // about reaching a row without hunting for it: the cap below never applies
  // to persons (every person is on the wall, always — so filtering them by
  // `max_terms` would hide a row for a node that is demonstrably visible), and
  // the reason to open this list is nearly always the portrait that just
  // appeared. A day's persons are one per interview, so the block stays short
  // enough that the setup's test portrait is still findable at its foot.
  // Terms keep their own A-Z order below, unchanged.
  const persons = graph.nodes
    .filter((node) => node.type === 'person')
    .sort((a, b) => (b.created_at || 0) - (a.created_at || 0));

  // Same cap the wall applies, so the list offers an action only where that
  // action has a visible effect. Deliberately NOT visibleGraph(): that one
  // also drops hidden nodes, which is right for the wall and fatal here — the
  // hidden entry IS the way back, and a list that dropped it would make
  // "ausblenden" a one-way door with no matching "einblenden". That holds for
  // a hidden person just as much as for a hidden term. Also deliberately
  // without the wall's own hysteresis grace list: this list answers "what
  // would the cap alone show", not "what does the wall happen to still be
  // holding onto right now".
  const terms = graph.nodes.filter((node) => node.type === 'term');
  const visibleTermIds = selectVisibleTermIds(terms, state.max_terms);
  const visibleTerms = terms
    .filter((node) => node.hidden || visibleTermIds.has(node.id))
    .sort((a, b) => a.label.localeCompare(b.label, 'de'));

  for (const node of [...persons, ...visibleTerms]) {
    list.appendChild(entryRow(node, termCounts, draft));
  }
  restoreDraft(list, draft);
}

function showTranscript(text) {
  document.getElementById('transcript').textContent = text;
}

/** Print the slider's value the way an operator reads it, not the way JS
 * stringifies a float: "1,45×", never "1.4500000000000002×".
 *
 * At 1,00× the whole net is in frame by definition, so the automatic tour has
 * nowhere to travel to: it still runs, but every target is already on screen
 * and the wall looks motionless. That reads as a broken camera (Birk,
 * 2026-08-26 — reported as "no automatic movement" with the slider at the
 * bottom stop), so the control says it rather than leaving it to be
 * rediscovered on the exhibition floor. */
function showZoomValue(factor) {
  const value = Number(factor);
  const hint = value < 1.05 ? ' — ganzes Netz, Fahrt ohne Wirkung' : '';
  document.getElementById('camera-zoom-value').textContent =
    `${value.toFixed(2).replace('.', ',')}×${hint}`;
}

document.getElementById('max-terms').addEventListener('change', (event) =>
  post('/api/max_terms', { value: Number(event.target.value) }),
);
document.getElementById('camera').addEventListener('change', (event) =>
  post('/api/camera', { mode: event.target.value }),
);
// Two listeners, deliberately: `input` fires continuously while the operator
// drags and only updates the local read-out, so the number under the thumb
// tracks the hand. `change` fires once on release and is the only one that
// posts — a POST per pixel would push a state broadcast to every SSE client
// (wall, plenary mirror) dozens of times per second.
document.getElementById('camera-zoom').addEventListener('input', (event) =>
  showZoomValue(event.target.value),
);
document.getElementById('camera-zoom').addEventListener('change', (event) =>
  post('/api/camera_zoom', { factor: Number(event.target.value) }),
);

/** The largest a portrait may get on the wall, in the unit the operator is
 * choosing in: pixels of the projected image, whole ones.
 *
 * No fraction and no multiplier, because this control is not relative to
 * anything — unlike the zoom, which multiplies a fit, this is a size in
 * pixels. "höchstens" and not a bare number because it is a CEILING since
 * 2026-08-30: on a busy wall the portraits stay under it by themselves and
 * the slider does nothing at all, and in manual mode it does not apply. An
 * operator who reads it as "so groß sind die Porträts" would go looking for a
 * fault when nothing moves. */
function showPortraitSizeValue(pixels) {
  const value = Math.round(Number(pixels) || 120);
  document.getElementById('portrait-size-value').textContent = `höchstens ${value} px`;
}

document.getElementById('portrait-size').addEventListener('input', (event) =>
  showPortraitSizeValue(event.target.value),
);
document.getElementById('portrait-size').addEventListener('change', (event) =>
  post('/api/portrait_size', { pixels: Number(event.target.value) }),
);

/** The tour's pace as a plain fraction — "1/1", "1/2", "1/4".
 *
 * Not a percentage and not seconds: the operator is choosing "half as fast",
 * and 0.5 or "50 %" or "10,4 s pro Etappe" all take a moment of arithmetic to
 * turn back into that. The slider is continuous, so anything between the neat
 * fractions is shown as a decimal divisor ("1/1,4"). */
function showSpeedValue(factor) {
  const value = Math.min(1, Math.max(0.25, Number(factor) || 1));
  const divisor = 1 / value;
  const rounded = Math.round(divisor * 10) / 10;
  const text = Number.isInteger(rounded) ? String(rounded) : String(rounded).replace('.', ',');
  document.getElementById('camera-speed-value').textContent = `1/${text}`;
}

document.getElementById('camera-speed').addEventListener('input', (event) =>
  showSpeedValue(event.target.value),
);
document.getElementById('camera-speed').addEventListener('change', (event) =>
  post('/api/camera_speed', { factor: Number(event.target.value) }),
);

window.kgOperator = { render, showTranscript };

let graph = { nodes: [], edges: [], quotes: [] };
let state = {
  max_terms: 32,
  camera_mode: 'fit',
  camera_zoom: 1,
  camera_speed: 1,
  portrait_size: 120,
  stt_connected: false,
  interview: null,
};
const events = new EventSource('/events');
events.onmessage = (message) => {
  const payload = JSON.parse(message.data);
  if (payload.type === 'graph') graph = payload.graph;
  else if (payload.type === 'state') state = payload.state;
  else if (payload.type === 'transcript') return showTranscript(payload.text);
  render(graph, state);
};
