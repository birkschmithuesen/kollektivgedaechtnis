// One action per entry: hide. No approving, no editing, no queue (spec 8).

function post(url, body) {
  return fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
}

function entryRow(node) {
  const item = document.createElement('li');
  item.className = `entry ${node.hidden ? 'hidden' : ''}`.trim();
  item.id = `entry-${node.id}`;

  const label = document.createElement('span');
  label.className = 'label';
  label.textContent = node.type === 'term' ? node.label : node.id;
  item.appendChild(label);

  const meta = document.createElement('span');
  meta.className = 'meta';
  meta.textContent = node.type === 'term' ? `${node.mentions}×` : 'Person';
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
