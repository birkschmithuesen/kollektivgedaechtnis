// Spec §7. Display settings and flow control — and nothing that could change
// the guiding question, the visual register or the weighting at runtime.

// The last state the server actually CONFIRMED, not merely what we tried to
// send. post() reverts to this on failure, which is this exhibition's only
// feedback for a write the server never acknowledged: no toast, no banner,
// just the control snapping back to the truth. Copied from Tool 1's operator
// UI on purpose — same surface, same stakes.
let lastState = null;
let lastDreams = [];

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

  document.getElementById('the-question').firstElementChild.textContent = state.question;
  document.getElementById('question-visible').checked = Boolean(state.question_visible);
  document.getElementById('question-seconds').value = String(state.question_seconds ?? 0);
  document.getElementById('fade-ms').value = String(state.fade_ms);
  document.getElementById('strip-ratio').value = String(state.strip_ratio);
  document.getElementById('typewriter').checked = Boolean(state.typewriter);

  // One button that says what it will DO, not what the state IS — the operator
  // is reaching for it in a hurry.
  document.getElementById('pause').textContent = state.paused ? 'Weiter' : 'Pause';

  const discard = document.getElementById('discard-current');
  discard.disabled = !state.current;
  discard.dataset.dreamId = state.current ? state.current.id : '';
}

function renderDreams(dreams) {
  lastDreams = dreams;
  const list = document.getElementById('dreams');
  list.replaceChildren();
  // Newest first: the operator reaches for the dream that is on screen NOW.
  // (The WALL runs oldest-first — that is a time axis, this is a work list.)
  dreams
    .slice()
    .sort((a, b) => b.created_at - a.created_at)
    .forEach((dream) => list.appendChild(dreamRow(dream)));
}

function refreshDreams() {
  return fetch('/api/dreams')
    .then((response) => response.json())
    .then((payload) => renderDreams(payload.dreams || []))
    .catch((error) => console.warn('could not load the dream record', error));
}

document
  .getElementById('question-visible')
  .addEventListener('change', (event) => display({ question_visible: event.target.checked }));
document
  .getElementById('question-seconds')
  .addEventListener('change', (event) => display({ question_seconds: Number(event.target.value) }));
document
  .getElementById('fade-ms')
  .addEventListener('change', (event) => display({ fade_ms: Number(event.target.value) }));
document
  .getElementById('strip-ratio')
  .addEventListener('change', (event) => display({ strip_ratio: Number(event.target.value) }));
document
  .getElementById('typewriter')
  .addEventListener('change', (event) => display({ typewriter: event.target.checked }));

document.getElementById('dream-now').addEventListener('click', () => post('/api/dream_now'));
document
  .getElementById('pause')
  .addEventListener('click', () => post('/api/pause', { paused: !(lastState && lastState.paused) }));
document.getElementById('discard-current').addEventListener('click', (event) => {
  const id = event.currentTarget.dataset.dreamId;
  if (id) post('/api/discard', { dream_id: id, discarded: true });
});

window.kgDreamOperator = { render, renderDreams, refreshDreams };

const events = new EventSource('/events');
events.onmessage = (message) => {
  const payload = JSON.parse(message.data);
  if (payload.type === 'state') {
    render(payload.state);
    refreshDreams();
  }
};
