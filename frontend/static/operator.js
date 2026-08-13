// One action per entry: hide. No approving, no editing, no queue (spec 8).

// The last graph/state a render() call actually received — from the server,
// via /events, not merely attempted. post() reverts to these on failure, so
// this is the exhibition's only feedback for a control the server never
// confirmed (see the catch below): no toast/banner, just the control
// snapping back to the truth.
let lastGraph = { nodes: [], edges: [], quotes: [] };
let lastState = { min_mentions: 1, camera_mode: 'fit', stt_connected: false, interview: null };

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

function render(graph, state) {
  lastGraph = graph;
  lastState = state;

  document.getElementById('min-mentions').value = String(state.min_mentions);
  document.getElementById('camera').value = state.camera_mode;
  document.getElementById('stt').classList.toggle('ok', Boolean(state.stt_connected));
  document.getElementById('interview').textContent = state.interview
    ? 'Interview läuft'
    : 'kein Interview';

  const list = document.getElementById('entries');
  list.replaceChildren();
  graph.nodes
    .filter((node) => node.type === 'term')
    .slice()
    .sort((a, b) => (b.created_at || 0) - (a.created_at || 0))
    .forEach((node) => list.appendChild(entryRow(node)));
}

function showTranscript(text) {
  document.getElementById('transcript').textContent = text;
}

document.getElementById('min-mentions').addEventListener('change', (event) =>
  post('/api/min_mentions', { value: Number(event.target.value) }),
);
document.getElementById('camera').addEventListener('change', (event) =>
  post('/api/camera', { mode: event.target.value }),
);

window.kgOperator = { render, showTranscript };

let graph = { nodes: [], edges: [], quotes: [] };
let state = { min_mentions: 1, camera_mode: 'fit', stt_connected: false, interview: null };
const events = new EventSource('/events');
events.onmessage = (message) => {
  const payload = JSON.parse(message.data);
  if (payload.type === 'graph') graph = payload.graph;
  else if (payload.type === 'state') state = payload.state;
  else if (payload.type === 'transcript') return showTranscript(payload.text);
  render(graph, state);
};
