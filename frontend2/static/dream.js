// Screen B (spec §6). One layout, one optional animation, no dashboard.
//
// The page is a pure function of the state the server pushes: applyState()
// is idempotent, so the state event that arrives on every operator control
// change does not re-fade the image. That matters on a wall — a re-fade each
// time someone nudges the strip ratio would be visible from across the room.

const TYPE_MS = 55; // per word, the typewriter's own pace

export function createDreamView(root) {
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
  // 🔴 BLÄTTERN DURCH DIE REIHE (Birk, 2026-09-02: „da wo unten die kleinen
  // Reihen entsteht, da soll man das anklicken können").
  //
  // `blaetterId` ist der Traum, den jemand von Hand aus dem Streifen geholt
  // hat — null heisst „die Wand zeigt den laufenden Traum". `letzteLiveId`
  // merkt sich, welcher Traum zuletzt von selbst kam.
  //
  // Warum beides: `applyState` laeuft bei JEDER Zustandsmeldung, also auch
  // wenn der Operator nur die Streifenhoehe verstellt. Ohne die zweite
  // Variable wuerde jede solche Meldung das Blättern abbrechen. Und ohne die
  // erste bliebe die Wand auf einem alten Bild stehen, wenn jemand vergisst
  // zurueckzuklicken — deshalb holt ein NEUER Traum sie von selbst zurueck.
  let blaetterId = null;
  let letzteLiveId = null;
  let letzterLiveTraum = null;
  let visibleFrame = 0;
  let fading = false;
  let fadeTimer = null;
  let typeTimer = null;
  let typewriterEnabled = false;

  function setFade(ms) {
    root.style.setProperty('--fade-ms', `${ms}ms`);
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
      // Anklickbar, damit man einen frueheren Traum wieder gross sehen kann.
      // `button`-Rolle und Tastaturzugang, weil ein `li` fuer sich genommen
      // kein Bedienelement ist.
      item.classList.add('anklickbar');
      item.tabIndex = 0;
      item.setAttribute('role', 'button');
      item.dataset.traum = dream.id;
      const holen = () => zeigeAusReihe(dream);
      item.addEventListener('click', holen);
      item.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); holen(); }
      });
      if (dream.id === blaetterId) item.classList.add('gewaehlt');
      strip.appendChild(item);
    });
  }

  /** Einen Traum aus dem Streifen gross zeigen. Zweiter Klick auf denselben
   * geht zurueck auf den laufenden. */
  function zeigeAusReihe(dream) {
    if (!dream || !dream.image) return;
    if (blaetterId === dream.id) {
      blaetterId = null;
      if (letzterLiveTraum) {
        currentId = letzterLiveTraum.id;
        stopTypewriter();
        showImage(letzterLiveTraum.image, letzterLiveTraum.sentence, false);
        sentence.textContent = letzterLiveTraum.sentence || '';
      }
    } else {
      blaetterId = dream.id;
      currentId = dream.id;
      stopTypewriter();
      showImage(dream.image, dream.sentence, false);
      sentence.textContent = dream.sentence || '';
    }
    strip.querySelectorAll('li').forEach((li) => {
      li.classList.toggle('gewaehlt', li.dataset.traum === blaetterId);
    });
  }

  // ---------------------------------------------------------------------
  // Die Slideshow (Birk, 2026-09-02, am Abend des Ausstellungstags)
  // ---------------------------------------------------------------------
  // 🔴 „Die Träume sollten als Slideshow mit Überblendung durchlaufen."
  //
  // Der Anlass: Am Abend werden keine Interviews mehr geführt, es entsteht
  // also kein neuer Traum. Die Wand zeigte dann stundenlang EIN Bild. Die
  // Schleife macht aus dem Bestand des Tages wieder etwas, das läuft.
  //
  // Sie baut auf dem, was schon da ist: `showImage` blendet über zwei Frames
  // kreuz (--fade-ms, vom Operator einstellbar), und `blaetterId` sagt der
  // Wand ohnehin schon, dass gerade nicht der jüngste Traum zu sehen ist.
  // Die Slideshow ist damit nur ein automatisches Blättern — kein zweiter
  // Mechanismus neben dem, den eine Hand am Streifen bedient.
  const SLIDESHOW_MS = 8000;
  // Abschaltbar über `?slideshow=0`. Der Regelfall an einem Tag MIT Interviews
  // ist, dass ohnehin alle paar Minuten ein neuer Traum kommt und die Schleife
  // unterbricht — aber wer die Wand bewusst auf einem Bild stehen lassen will
  // (eine Aufnahme, eine Präsentation), soll das ohne Codeänderung können.
  // 🔴 ZWEI SCHALTER, und der Bedienpult-Schalter gewinnt (Birk, 2026-09-03:
  // „der traum operator braucht noch einen button um die automatische
  // slideshow an/aus zu setzen").
  //
  // `?slideshow=0` bleibt: Damit stellt man EINE Flaeche still, ohne den
  // anderen etwas wegzunehmen — etwa fuer eine Aufnahme. Der Schalter am
  // Bedienpult gilt fuer alle und ist der Weg, den eine Hand im Raum nimmt.
  // Aus bleibt aus, sobald einer von beiden es sagt.
  const slideshowUrlAn =
    new URLSearchParams(window.location.search).get('slideshow') !== '0';
  let slideshowStateAn = true;
  const slideshowAn = () => slideshowUrlAn && slideshowStateAn;
  let autoUhr = null;
  let autoReihe = [];
  let autoStelle = 0;

  function autoWeiter() {
    if (autoReihe.length < 2) return;
    autoStelle = (autoStelle + 1) % autoReihe.length;
    const traum = autoReihe[autoStelle];
    if (!traum || !traum.image) return;
    // Der letzte der Reihe IST der laufende Traum — dann ist das Blättern
    // vorbei und die Wand steht wieder auf dem Aktuellen.
    blaetterId = traum.id === letzteLiveId ? null : traum.id;
    currentId = traum.id;
    stopTypewriter();
    showImage(traum.image, traum.sentence, false);
    sentence.textContent = traum.sentence || '';
    strip.querySelectorAll('li').forEach((li) => {
      li.classList.toggle('gewaehlt', li.dataset.traum === blaetterId);
    });
  }

  function starteSlideshow() {
    if (autoUhr !== null) window.clearInterval(autoUhr);
    autoUhr = null;
    // Unter zwei Bildern gibt es nichts durchzublättern; die Wand bleibt
    // dann genau so stehen, wie sie es ohne die Slideshow täte.
    if (!slideshowAn() || autoReihe.length < 2) return;
    autoUhr = window.setInterval(autoWeiter, SLIDESHOW_MS);
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
    // Fehlt das Feld (aelterer Kern), bleibt es bei „an" — das ist, was die
    // Wand vor diesem Schalter tat.
    const vorher = slideshowStateAn;
    slideshowStateAn = state.slideshow !== false;
    if (slideshowStateAn !== vorher) {
      // 🔴 ABGESCHALTET HEISST ZURUECK ZUM JUENGSTEN TRAUM (Birk, 2026-09-03:
      // „wenn ich beim traum slideshow deaktiviere, soll es automatisch zum
      // letzten (aktuellsten) bild gehen").
      //
      // Zuerst hielt das Abschalten die Wand dort an, wo die Schleife gerade
      // stand — also auf einem beliebigen Traum von irgendwann am Tag. Wer den
      // Haken wegnimmt, will aber nicht IRGENDEIN Bild festhalten, sondern das
      // aktuelle: Es ist der Traum des zuletzt gefuehrten Gespraechs, und das
      // ist der Zustand, in dem die Wand steht, wenn niemand blaettert.
      //
      // `blaetterId = null` ist derselbe Griff, mit dem weiter unten ein
      // wirklich neuer Traum das Blaettern beendet — kein zweiter Mechanismus
      // daneben. Der Rest von `applyState` zeigt dann `state.current`.
      if (!slideshowStateAn && blaetterId !== null) {
        blaetterId = null;
        strip.querySelectorAll('li').forEach((li) => li.classList.remove('gewaehlt'));
      }
      // `starteSlideshow()` raeumt die laufende Uhr selbst ab.
      starteSlideshow();
    }
    if (wasTypewriterEnabled && !typewriterEnabled) {
      // Turning it off is a switch, not a rebuild (Finding 4, spec §6): a
      // build in progress must stop where it stands. Without this, a build
      // only stopped when the dream id also changed, so flipping the switch
      // mid-word let the animation run to completion on screen regardless.
      stopTypewriter();
    }
    renderStrip(state.history || []);

    // Der Vorrat für die Slideshow: die Historie in Entstehungsreihenfolge,
    // der laufende Traum zuletzt.
    //
    // 🔴 NUR, WENN ER NICHT SCHON DRIN IST (gefunden 2026-09-03): `history`
    // enthält den laufenden Traum bereits — `dream_state()` schneidet sie aus
    // derselben Tabelle. Angehängt stand er zweimal in der Reihe, und die Wand
    // blieb sechzehn statt acht Sekunden auf demselben Bild stehen. Bei einem
    // EINZIGEN Traum ergab das sogar eine Schleife von ihm auf sich selbst:
    // zwei Einträge, also lief die Uhr, und alle acht Sekunden wurde dasselbe
    // Bild neu eingeblendet — auf einer Wand ein Flackern ohne Sinn.
    const reihe = (state.history || []).filter((tr) => tr && tr.image);
    const laufend = state.current;
    if (laufend && laufend.image && !reihe.some((tr) => tr.id === laufend.id)) {
      reihe.push(laufend);
    }
    const schluessel = reihe.map((tr) => tr.id).join(',');
    if (schluessel !== autoReihe.map((tr) => tr.id).join(',')) {
      autoReihe = reihe;
      autoStelle = Math.max(0, autoReihe.length - 1);
      starteSlideshow();
    }

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
    // Ein WIRKLICH neuer Traum beendet das Blättern und holt die Wand zurueck.
    // Eine blosse Zustandsmeldung (Operator dreht an einem Regler) tut das
    // nicht — sonst waere Blättern nach dem ersten Reglerdruck vorbei.
    const istNeu = dream.id !== letzteLiveId;
    letzteLiveId = dream.id;
    letzterLiveTraum = dream;
    if (istNeu && blaetterId !== null) {
      blaetterId = null;
      strip.querySelectorAll('li').forEach((li) => li.classList.remove('gewaehlt'));
    }
    if (istNeu) {
      // Ein wirklich neuer Traum hat Vorrang: Die Wand zeigt ihn und blättert
      // von dort aus weiter. Sonst liefe die Schleife über ihn hinweg.
      autoStelle = Math.max(0, autoReihe.length - 1);
      starteSlideshow();
    }
    if (blaetterId !== null) {
      // Jemand sieht sich gerade einen frueheren Traum an: Bild und Satz
      // bleiben, wo sie sind.
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
    /** Ob die Wand gerade von selbst weiterblaettert.
     *
     * Pruefnaht wie `fading` daneben: Die Schleife laeuft im 8-Sekunden-Takt,
     * und ein Test, der auf einen Wechsel wartet, kostet acht Sekunden je
     * Behauptung. Gefragt wird deshalb, ob die Uhr laeuft — das ist genau die
     * Entscheidung, die der Schalter am Bedienpult trifft. */
    get slideshowLaeuft() {
      return autoUhr !== null;
    },
    /** Wie viele Stationen die Schleife hat. Pruefnaht neben der obigen: Ob
     * der laufende Traum doppelt in der Reihe steht, ist an der Wand erst nach
     * acht Sekunden Stillstand zu sehen — hier in einer Zahl. */
    get slideshowStationen() {
      return autoReihe.length;
    },
    /** Die Schleife auf eine bestimmte Station stellen.
     *
     * Pruefnaht: Von selbst braucht die Schleife acht Sekunden je Schritt, und
     * ein Test, der auf den zweiten Traum warten will, kostete sechzehn.
     * Gerufen wird genau das, was die Uhr sonst ruft. */
    blaettereFuerDenTest(stelle) {
      autoStelle = (stelle - 1 + autoReihe.length) % autoReihe.length;
      autoWeiter();
    },
  };
}
