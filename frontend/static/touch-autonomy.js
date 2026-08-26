// Touch autonomy for surface A (the 65" touchscreen).
//
// The problem this solves: `camera_mode` is GLOBAL state. It lives in the
// Store's settings table and `broadcast_state` pushes it to every SSE
// subscriber (see docs/decisions/cr1-second-screen-player.md). So a visitor
// touching the screen in the foyer must NOT be allowed to POST a mode change —
// that would drag surface C in the plenary room into manual mode as well, with
// nobody there to touch anything and no operator to notice.
//
// Therefore the switch is purely local: this module overrides the camera's mode
// on THIS page only, and never talks to the server. The operator's setting stays
// the truth everywhere; the touchscreen just borrows manual mode for as long as
// somebody is actually using it.
//
// Back to automatic after IDLE_MS of no contact, because an exhibition screen
// left mid-zoom by a visitor who walked away is a dead screen for the next
// person. 30 s is Birk's call (2026-08-26): long enough that a pause to read
// does not yank the view away, short enough that the wall recovers on its own.

const IDLE_MS = 30000;

export function attachTouchAutonomy(
  view,
  {
    idleMs = IDLE_MS,
    target = document,
    // Injected for tests; production uses the real timers.
    now = () => Date.now(),
    setTimer = (fn, ms) => window.setTimeout(fn, ms),
    clearTimer = (id) => window.clearTimeout(id),
  } = {},
) {
  // The mode the operator last pushed. Manual touching does not change it —
  // it is what we fall BACK to, so it has to survive the whole interaction.
  let operatorMode = view.camera.mode;
  let touching = false;
  let timer = null;
  let lastTouch = 0;

  function toAutomatic() {
    timer = null;
    if (!touching) return;
    touching = false;
    // Return to whatever the operator has set — not hardcoded 'pan'. If the
    // operator switched the wall to 'fit' while a visitor was panning, the
    // idle timeout must land on 'fit'.
    view.camera.setMode(operatorMode);
  }

  function poke() {
    lastTouch = now();
    if (!touching) {
      touching = true;
      view.camera.setMode('manual');
    }
    if (timer !== null) clearTimer(timer);
    timer = setTimer(toAutomatic, idleMs);
  }

  // pointerdown covers touch, pen and mouse in one event — the iiyama reports
  // as a USB-HID digitizer, so its contacts arrive as pointer events with
  // pointerType 'touch'.
  //
  // Pressing one of the visitor controls must NOT count as "the visitor is
  // steering the view": tapping "Übersicht" would otherwise flip the camera
  // into manual in the same breath as the handler puts it back into fit, and
  // the button would appear dead (found 2026-08-26 — the control worked, the
  // autonomy immediately overrode it). The controls do their own thing; only
  // contact with the GRAPH means someone is navigating.
  const onPointer = (event) => {
    if (event.target instanceof Element && event.target.closest('.touch-controls')) return;
    poke();
  };
  target.addEventListener('pointerdown', onPointer, { passive: true });
  // Wheel/trackpad for testing on a desktop without a touchscreen.
  target.addEventListener('wheel', onPointer, { passive: true });

  return {
    /** The operator's push. Kept separate from the local override so a state
     * broadcast that arrives WHILE a visitor is touching does not yank the
     * view out from under their hand — it is recorded and applied at idle. */
    setOperatorMode(mode) {
      operatorMode = mode;
      if (!touching) view.camera.setMode(mode);
    },
    /** Force the way back — the "Übersicht" button on the touchscreen. */
    releaseNow() {
      if (timer !== null) clearTimer(timer);
      timer = null;
      touching = false;
      view.camera.setMode(operatorMode);
    },
    get manual() {
      return touching;
    },
    get idleSince() {
      return lastTouch;
    },
    detach() {
      target.removeEventListener('pointerdown', onPointer);
      target.removeEventListener('wheel', onPointer);
      if (timer !== null) clearTimer(timer);
    },
  };
}
