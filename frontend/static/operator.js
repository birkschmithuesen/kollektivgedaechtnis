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

function entryRow(node) {
  const item = document.createElement('li');
  item.className = `entry ${node.hidden ? 'hidden' : ''}`.trim();
  item.id = `entry-${node.id}`;

  // render() only ever passes term nodes here (see the filter below), so
  // this has no person branch to fall into — kept simple on purpose rather
  // than handling a case that can't occur.
  const label = document.createElement('span');
  label.className = 'label';
  label.textContent = node.label;
  item.appendChild(label);

  const meta = document.createElement('span');
  meta.className = 'meta';
  meta.textContent = `${node.mentions}×`;
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
  document.getElementById('stt').classList.toggle('ok', Boolean(state.stt_connected));
  document.getElementById('interview').textContent = state.interview
    ? 'Interview läuft'
    : 'kein Interview';

  const list = document.getElementById('entries');
  list.replaceChildren();
  // Same cap the wall applies, so the list offers an action only where that
  // action has a visible effect. Deliberately NOT visibleGraph(): that one
  // also drops hidden nodes, which is right for the wall and fatal here — the
  // hidden entry IS the way back, and a list that dropped it would make
  // "ausblenden" a one-way door with no matching "einblenden". Also
  // deliberately without the wall's own hysteresis grace list: this list
  // answers "what would the cap alone show", not "what does the wall happen
  // to still be holding onto right now".
  const terms = graph.nodes.filter((node) => node.type === 'term');
  const visibleTermIds = selectVisibleTermIds(terms, state.max_terms);
  terms
    .filter((node) => node.hidden || visibleTermIds.has(node.id))
    .sort((a, b) => a.label.localeCompare(b.label, 'de'))
    .forEach((node) => list.appendChild(entryRow(node)));
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
