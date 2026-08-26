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
  // Separate from currentId on purpose: currentId goes back to null whenever
  // the stage is cleared (a discard with nothing earlier to fall back to, or
  // the 09:00 empty state), but that is not the same event as "nothing has
  // ever been shown this session". Only the latter should skip the cross-fade
  // — conflating them turned a discard-then-new-dream into a cut (Finding 2).
  let everRevealed = false;
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

  function scheduleFadeDone() {
    // Shared by every transition that runs the CSS opacity fade (a new image
    // arriving, or the stage clearing to blank): `fading` and its timer exist
    // once so `applyState`'s idempotency check has one place to look, not one
    // per caller that could drift out of sync.
    fading = true;
    clearTimeout(fadeTimer);
    const ms = parseFloat(getComputedStyle(root).getPropertyValue('--fade-ms')) || 0;
    fadeTimer = setTimeout(() => {
      fading = false;
    }, ms + 40);
  }

  function showImage(url, alt, instant) {
    everRevealed = true;
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

    scheduleFadeDone();
  }

  function clearStage() {
    // A discard of the only dream, or the 09:00 state before anything has
    // happened, leaves nothing to cross-fade TO. Cutting the stale frame to
    // black would read as a fault; fading it out re-uses the same mechanism
    // as every other transition, so a blank stage is still a state change,
    // not a crash (Finding 2 — the spec's "replace with the previous dream"
    // rule bottoms out at "nothing" when there is no previous one).
    frames[visibleFrame].classList.remove('visible');
    scheduleFadeDone();
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
    const wasTypewriterEnabled = typewriterEnabled;
    typewriterEnabled = Boolean(state.typewriter);
    if (wasTypewriterEnabled && !typewriterEnabled) {
      // Turning it off is a switch, not a rebuild (Finding 4, spec §6): a
      // build in progress must stop where it stands. Without this, a build
      // only stopped when the dream id also changed, so flipping the switch
      // mid-word let the animation run to completion on screen regardless.
      stopTypewriter();
    }
    applyQuestion(state);
    renderStrip(state.history || []);

    const dream = state.current;
    if (!dream) {
      sentence.textContent = '';
      // Only fade if a frame is actually showing. At 09:00, before the first
      // interview, currentId is already null and there is nothing on the
      // stage to fade — clearStage() would spin up a --fade-ms cycle for an
      // image nobody ever saw.
      if (currentId !== null) {
        clearStage();
      }
      currentId = null;
      return;
    }
    // Idempotent: the same dream re-applied is a no-op for the image, so a
    // control change never re-fades the wall.
    if (dream.id !== currentId) {
      // A blank stage from a discard-to-empty is NOT the same as a session
      // that has shown nothing yet — everRevealed (not currentId) tracks
      // that, so the dream that follows a discard cross-fades in rather than
      // cutting onto a frame that only just faded out (Finding 2).
      const instant = !everRevealed;
      currentId = dream.id;
      stopTypewriter();
      showImage(dream.image, dream.sentence, instant);
    }
    sentence.textContent = dream.sentence || '';
  }

  function dreamFailed() {
    // Finding 1: stage 1's `dreaming` event may already have started the
    // typewriter build for a sentence whose dream then failed at stage 2.
    // `applyState`'s `dream.id !== currentId` guard cannot catch this — the
    // current dream is unchanged on a failure, so that idempotency check
    // never fires — which is exactly why the server publishes a distinct
    // `dream_failed` signal instead of folding this into a `state` push.
    // Only the overlay clears; the baseline sentence and image are left
    // exactly as they are (spec §8's "ride it out").
    stopTypewriter();
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
    dreamFailed,
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
