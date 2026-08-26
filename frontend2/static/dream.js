// Screen B (spec §6). One layout, one optional animation, no dashboard.
//
// The page is a pure function of the state the server pushes: applyState()
// is idempotent, so the state event that arrives on every operator control
// change does not re-fade the image. That matters on a wall — a re-fade each
// time someone nudges the strip ratio would be visible from across the room.

const TYPE_MS = 55; // per word, the typewriter's own pace

export function createDreamView(root) {
  const question = root.querySelector('#question');
  const stage = root.querySelector('#stage');
  const sentence = root.querySelector('#sentence');
  const typewriter = root.querySelector('#typewriter');
  const strip = root.querySelector('#strip');
  const frames = [stage.querySelector('#frame-a'), stage.querySelector('#frame-b')];

  let currentId = null;
  let visibleFrame = 0;
  let fading = false;
  let fadeTimer = null;
  let questionTimer = null;
  let typeTimer = null;
  let typewriterEnabled = false;

  function setFade(ms) {
    root.style.setProperty('--fade-ms', `${ms}ms`);
  }

  function applyQuestion(state) {
    question.textContent = state.question || '';
    clearTimeout(questionTimer);
    if (!state.question_visible) {
      question.hidden = true;
      return;
    }
    question.hidden = false;
    // 0 means permanent (spec §7). Anything else hides it after N seconds —
    // Birk's explicit request, so the question can introduce the piece in the
    // morning and then get out of the image's way.
    if (state.question_seconds > 0) {
      questionTimer = setTimeout(() => {
        question.hidden = true;
      }, state.question_seconds * 1000);
    }
  }

  function showImage(url, alt, instant) {
    const next = 1 - visibleFrame;
    const incoming = frames[next];
    incoming.alt = alt || '';
    incoming.src = url;
    // Force a style flush so the browser has the new src laid out before the
    // opacity flip; without it the first fade of a session is a cut.
    void incoming.offsetWidth;

    if (instant) {
      // The very first image of a session has nothing to cross-fade FROM —
      // it is a reveal, not a transition between two dreams — so it applies
      // with no animation and never sets `fading`, instead of running the
      // full --fade-ms cycle for an image nobody was looking at yet.
      incoming.classList.add('instant', 'visible');
      void incoming.offsetWidth;
      incoming.classList.remove('instant');
      frames[visibleFrame].classList.remove('visible');
      visibleFrame = next;
      return;
    }

    incoming.classList.add('visible');
    frames[visibleFrame].classList.remove('visible');
    visibleFrame = next;

    fading = true;
    clearTimeout(fadeTimer);
    const ms = parseFloat(getComputedStyle(root).getPropertyValue('--fade-ms')) || 0;
    fadeTimer = setTimeout(() => {
      fading = false;
    }, ms + 40);
  }

  function renderStrip(history) {
    strip.replaceChildren();
    // Oldest to newest (spec §6): the strip is a time axis. It is also the
    // evidence that there was never ONE vision of the future, which only
    // reads if it runs in the direction the day ran.
    history.forEach((dream) => {
      const item = document.createElement('li');
      const image = document.createElement('img');
      image.src = dream.image;
      image.alt = dream.sentence || '';
      item.appendChild(image);
      strip.appendChild(item);
    });
  }

  function stopTypewriter() {
    clearInterval(typeTimer);
    typewriter.hidden = true;
    typewriter.textContent = '';
  }

  function applyState(state) {
    setFade(state.fade_ms);
    root.style.setProperty('--strip-ratio', String(state.strip_ratio));
    typewriterEnabled = Boolean(state.typewriter);
    applyQuestion(state);
    renderStrip(state.history || []);

    const dream = state.current;
    if (!dream) {
      sentence.textContent = '';
      currentId = null;
      return;
    }
    // Idempotent: the same dream re-applied is a no-op for the image, so a
    // control change never re-fades the wall.
    if (dream.id !== currentId) {
      const isFirstReveal = currentId === null;
      currentId = dream.id;
      stopTypewriter();
      showImage(dream.image, dream.sentence, isFirstReveal);
    }
    sentence.textContent = dream.sentence || '';
  }

  function showDreaming(text) {
    // Stage 1 has returned and stage 2 is running. The BASELINE carries this
    // moment either way — the previous image and sentence stay exactly where
    // they are (spec §6, brainstorm §3), so a 60 s generation shows nothing
    // unusual. The typewriter is the optional layer on top.
    if (!typewriterEnabled) return;
    const words = String(text).split(/\s+/).filter(Boolean);
    let index = 0;
    typewriter.hidden = false;
    typewriter.textContent = '';
    clearInterval(typeTimer);
    typeTimer = setInterval(() => {
      if (index >= words.length) {
        clearInterval(typeTimer);
        return;
      }
      typewriter.textContent = words.slice(0, ++index).join(' ');
    }, TYPE_MS);
  }

  return {
    applyState,
    showDreaming,
    get current() {
      return currentId;
    },
    get historyLength() {
      return strip.children.length;
    },
    get fading() {
      return fading;
    },
  };
}
