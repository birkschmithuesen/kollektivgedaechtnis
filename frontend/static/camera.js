// The camera is its own component from the start, even if everything fits.
// Mode 'pan' IS the touch fallback: a non-interactive automatic animation.

const MODES = ['fit', 'manual', 'pan'];

// How the automatic mode moves. These are the aesthetic decisions, gathered in
// one place so they can be tuned without reading the traversal logic.
//
// The shape being avoided: a camera that slides left, hits the edge, and
// reverses in a single frame reads as a screensaver — the reversal is the
// moment the machine shows. So the automatic mode does not bounce off walls.
// It picks a term node, travels to it, rests, and picks another. Motion then
// carries meaning (it is going somewhere) and every direction change happens
// while the camera is standing still at a target, never mid-glide.
const ROAM = {
  // The FASTEST the tour ever goes (speed factor 1.0). Everything slower is
  // derived by dividing by the factor, so this pair stays the reference the
  // motion was tuned against and the operator only ever slows it down —
  // there is no setting that outruns what was judged on the wall.
  travelMs: 5200, // one leg, long enough to read as drifting rather than cutting
  dwellMs: 4200, // rest on the target — the beat that makes it feel deliberate
  // Zoom breathes around the calibrated level across a whole leg-plus-dwell.
  // Small on purpose: enough that the image is never frozen, not so much that
  // the visitor notices a zoom happening.
  breathAmplitude: 0.06,
  breathPeriodMs: 42000,
  // Prefer well-connected terms: the wall is about what people share, so the
  // traversal should dwell where sharing actually happened. Degree 1 nodes are
  // still reachable, just far less often.
  degreeBias: 2.0,
  // Handing the view back: how long the camera takes to travel from the
  // close-up a visitor left behind to the view the automatic mode wants.
  //
  // Deliberately shorter than a leg (5200 ms) and in the same breath longer
  // than a cut: this is not part of the journey, it is the wall taking over
  // after 30 s of nobody touching it, and the next person walking up should
  // find it already moving rather than still unwinding somebody else's pinch.
  //
  // NOT scaled by the operator's speed slider, unlike travel and dwell. The
  // slider sets the pace of the tour; a quarter-speed setting must not leave a
  // visitor's abandoned close-up on the wall for six seconds.
  handoverMs: 1500,
};

/** Ease in and out — no abrupt starts, no arrivals that slam to a halt.
 *
 * cosine rather than a cubic: its derivative is zero at BOTH ends, so a leg
 * begins and ends at literally zero speed. That is what removes the visible
 * "start" of each leg; with a cubic ease the residual velocity at t=0 is small
 * but perceptible on a 65" screen at close range. */
function easeInOut(t) {
  return 0.5 - 0.5 * Math.cos(Math.PI * Math.min(1, Math.max(0, t)));
}

/** Interpolate a magnification: equal steps in RATIO, not in difference.
 *
 * Zoom is a factor, and the eye reads factors. A linear ramp from 4x to 1x
 * spends its first half between 4x and 2.5x — a sixth of the way back in
 * perceived terms — and then rushes the rest, which looks like the camera
 * hesitating and then falling. Falls back to linear for unusable levels
 * rather than producing NaN: a wall must degrade, never stop rendering. */
function lerpZoom(from, to, t) {
  if (!(from > 0) || !(to > 0)) return from + (to - from) * t;
  return from * Math.pow(to / from, t);
}

/** Keep a speed inside [0.25, 1], treating anything unusable as full speed.
 *
 * `Number(x) || 1` is the obvious spelling and is WRONG here: 0 is falsy, so a
 * zero would fall through to 1 — full speed — when it plainly means "as slow
 * as possible". Only NaN deserves the fallback.
 */
function clampRoamSpeed(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 1;
  return Math.min(1, Math.max(0.25, n));
}

export class Camera {
  constructor(
    cy,
    {
      panSpeed = 18,
      padding = 60,
      zoomFactor = 1,
      roamSpeed = 1,
      random = Math.random,
      fitWith = (fit) => fit(),
      onModeChanged = () => {},
    } = {},
  ) {
    this.cy = cy;
    this.panSpeed = panSpeed;
    this.padding = padding;
    // Called after every setMode(). The projection re-sizes its portrait discs
    // there: since 2026-08-30 the portrait ceiling applies to the DRIVEN modes
    // only (see portraitCapBlend), so a mode change is a size change, and it
    // has to land in the same synchronous breath as the mode itself rather
    // than on the next animation frame.
    this._onModeChanged = onModeChanged;
    // Every viewport fit this camera performs goes through here. The
    // projection passes a wrapper that first puts the portrait discs back to
    // their placement size: since 2026-08-29 a disc's model size is derived
    // from the zoom (projection.js), and a fit that measured THOSE discs
    // would be computing the zoom from a size that is computed from the zoom
    // — with a single portrait on the wall that has no solution at all. The
    // default is the plain call, so a Camera used on its own is unchanged.
    this._fitWith = fitWith;
    // 1 = the whole net in frame. >1 = that many times tighter, i.e. only
    // 1/factor of the net's width is on the wall. Fit-all is illegible at 50
    // persons (pre-render series, 2026-08-14), so the zoom level is a setting
    // of this component, not a second camera bolted on next to it.
    this._zoomFactor = 1;
    this._mode = 'fit';
    this._direction = -1;
    // Injected so a test can drive the traversal deterministically; production
    // passes nothing and gets Math.random.
    this._random = random;
    this._roam = null;
    // The way back out of a visitor's hands, see _startHandover().
    this._handover = null;
    // 1 = the tuned speed (ROAM.travelMs/dwellMs), 0.25 = a quarter of it, i.e.
    // four times as long per leg. Clamped rather than validated-and-thrown: a
    // bad value must slow the wall down, never stop it rendering.
    this._roamSpeed = clampRoamSpeed(roamSpeed);
    // At an unattended exhibition a stray touch/mouse must never be able to
    // pan the viewport off-frame or drag a node off its persisted position.
    // `manual` is the only mode where a visitor is meant to move anything;
    // apply that for the initial mode too, not just from setMode onward.
    this._applyInteractivity(this._mode);
    this.setZoomFactor(zoomFactor);
  }

  get mode() {
    return this._mode;
  }

  get zoomFactor() {
    return this._zoomFactor;
  }

  get roamSpeed() {
    return this._roamSpeed;
  }

  /** How fast the automatic tour travels, as a fraction of the tuned speed.
   *
   * Applied to the DURATIONS, not to a velocity: a leg always covers the
   * whole distance to its target with the same cosine ease, it just takes
   * longer. Changing a velocity instead would leave the camera short of its
   * target when the phase ends, and the arrival — the moment the motion is
   * built around — would land somewhere arbitrary.
   *
   * Takes effect on the NEXT phase. Rescaling a leg already in flight would
   * make the camera visibly jump, which is the one thing the easing exists to
   * prevent. */
  setRoamSpeed(speed) {
    this._roamSpeed = clampRoamSpeed(speed);
  }

  /** This leg's duration at the current speed. */
  _travelDuration() {
    return ROAM.travelMs / this._roamSpeed;
  }

  /** This rest's duration at the current speed. */
  _dwellDuration() {
    return ROAM.dwellMs / this._roamSpeed;
  }

  /** What the automatic traversal is doing right now — for tests and the
   * pre-render, which need to place frames inside a leg rather than guess. */
  get roamState() {
    if (!this._roam) return null;
    return { phase: this._roam.phase, targetId: this._roam.targetId, elapsed: this._roam.elapsed };
  }

  setMode(mode) {
    if (!MODES.includes(mode)) throw new Error(`unknown camera mode: ${mode}`);
    const previous = this._mode;
    this._mode = mode;
    this._applyInteractivity(mode);
    // Entering pan starts a fresh traversal; leaving it drops the state so a
    // later return does not resume a leg whose target may no longer exist.
    this._roam = mode === 'pan' ? { phase: 'dwell', elapsed: 0, targetId: null, clock: 0 } : null;
    // Every mode change ends a handover in flight. The load-bearing case is a
    // visitor touching the wall while it is travelling back: `manual` has to
    // be theirs in that same frame, and a half-run handover still writing
    // pan/zoom would work against the hand that just grabbed it.
    this._handover = null;
    // Leaving manual is the one transition somebody is watching from a metre
    // away — it is their own view being taken back. Everywhere else the hard
    // framing stays: the operator's push, a graph change, and above all the
    // pre-render, which shoots a screenshot right after setting a view.
    if (previous === 'manual' && mode !== 'manual') this._startHandover();
    else if (mode === 'fit') this._frame();
    this._onModeChanged(mode);
  }

  /** How much of the automatic portrait ceiling is in force right now, 0..1.
   *
   * The portrait size is an upper bound in the DRIVEN modes and no bound at
   * all in the visitor's (projection.js). The camera is the only component
   * that knows which of the two the wall is in — and, more to the point, that
   * there is a third state in between: the 1.5 s travel out of a close-up
   * somebody left behind. Switching the bound back on at either end of that
   * travel would be the snap the handover exists to remove, in the one element
   * that is ten times oversized at that moment, so it comes back on along the
   * handover's own cosine, together with the pan and the zoom.
   */
  get portraitCapBlend() {
    if (this._handover) return easeInOut(this._handover.elapsed / ROAM.handoverMs);
    return this._mode === 'manual' ? 0 : 1;
  }

  setZoomFactor(factor) {
    if (!(factor >= 1)) throw new Error(`zoom factor must be >= 1: ${factor}`);
    const changed = factor !== this._zoomFactor;
    this._zoomFactor = factor;
    // Manual is the visitor's mode: re-framing under their hands would fight
    // them. Every other mode is driven, so it re-frames at the new level.
    if (!changed || this._mode === 'manual') return;
    // A new level moves the destination. Steer the handover onto it instead of
    // framing hard underneath it — a hard frame mid-flight is the snap all
    // over again, and the next step() would drag the view back out of it.
    if (this._handover) this._handover.to = this._automaticView();
    else this._frame();
  }

  /** Point the camera at a subset — one cluster instead of the whole net.
   *
   * This is the framing an automatic traversal dwells on, and what the
   * pre-render shoots for the close view. It deliberately does not change the
   * mode: the interaction rules stay whatever the operator set. */
  focus(eles, padding = this.padding) {
    this._fitWith(() => this.cy.fit(eles, padding));
  }

  _frame() {
    this._fitWith(() => this.cy.fit(this.padding));
    if (this._zoomFactor === 1) return;
    // Zoom about the middle of the viewport, so the net stays centred on the
    // wall instead of drifting towards the model origin.
    this.cy.zoom({
      level: this.cy.zoom() * this._zoomFactor,
      renderedPosition: { x: this.cy.width() / 2, y: this.cy.height() / 2 },
    });
  }

  _applyInteractivity(mode) {
    const interactive = mode === 'manual';
    this.cy.userPanningEnabled(interactive);
    this.cy.userZoomingEnabled(interactive);
    // NOT gated on the mode, unlike the two above. Birk, 2026-08-30, live at
    // the station: in manual mode a visitor's hand pulled portraits and terms
    // out of the arrangement and left them there. Moving the VIEW is what
    // manual mode is for; the arrangement belongs to the layout, always.
    //
    // `autoungrabify` and not `autolock`, and not a `grabbable: false` in the
    // stylesheet, because it is the one of the three that draws the line
    // exactly where Birk drew it — between user input and everything else.
    // Cytoscape gates only its two input handlers on grabbability
    // (`nodeIsDraggable = !locked() && grabbable()`, checked by the mouse
    // handler and again by the separate touch handler, which is the one the
    // foyer's HID digitizer goes through). `locked()` is checked in two more
    // places: by `position()` itself (`canSet: (e) => !e.locked()`) and by the
    // preset layout the migration glide runs on — so `autolock` would take
    // sim/prerender.py, the crash-recovery path and every position-writing
    // test down with the visitor's hand. Both halves of that are measured in
    // tests/test_projection.py rather than left as a claim.
    this.cy.autoungrabify(true);
  }

  onGraphChanged() {
    // Same reason as in setZoomFactor: an interview arriving during the 1.5 s
    // handover moves the destination, so the handover is redirected rather
    // than overwritten.
    if (this._handover) this._handover.to = this._automaticView();
    else if (this._mode === 'fit') this._frame();
    // A target that just left the graph (density raised, term hidden) must not
    // strand the traversal mid-leg pointing at nothing.
    if (this._roam && this._roam.targetId && this.cy.getElementById(this._roam.targetId).empty()) {
      this._roam = { phase: 'dwell', elapsed: 0, targetId: null, clock: this._roam.clock };
    }
  }

  /** The level the roaming camera travels at: the operator's calibrated zoom,
   * breathing gently so the image is never completely static. */
  _breathingZoom(baseLevel, clockMs) {
    const wave = Math.sin((2 * Math.PI * clockMs) / ROAM.breathPeriodMs);
    return baseLevel * (1 + ROAM.breathAmplitude * wave);
  }

  /** Pick the next term to travel to.
   *
   * Weighted by degree so the traversal favours shared concepts, and never
   * returns the node it is already sitting on — revisiting immediately would
   * look like the camera got stuck. */
  _pickTarget() {
    const candidates = this.cy.nodes('.term').filter((n) => n.id() !== this._roam?.targetId);
    if (candidates.empty()) return null;
    const weights = candidates.map((n) => Math.pow(n.degree(false) || 1, ROAM.degreeBias));
    const total = weights.reduce((a, b) => a + b, 0);
    let roll = this._random() * total;
    for (let i = 0; i < weights.length; i += 1) {
      roll -= weights[i];
      if (roll <= 0) return candidates[i];
    }
    return candidates[candidates.length - 1];
  }

  /** The view a handover is travelling to, or null when none is in flight. */
  get handoverTarget() {
    return this._handover ? { ...this._handover.to } : null;
  }

  /** Begin the travel from the view the visitor left to the automatic one. */
  _startHandover() {
    const from = { x: this.cy.pan().x, y: this.cy.pan().y, zoom: this.cy.zoom() };
    // In flight BEFORE the target is measured, and provisionally aimed at the
    // view it starts from. _automaticView() performs the hard framing and so
    // writes the zoom three times before putting it back, and the projection
    // sizes its portrait discs off portraitCapBlend on every one of those
    // writes. With the handover not yet in flight the blend would read 1 —
    // the mode has already flipped — and those writes would size the discs as
    // if the ceiling were fully back on, i.e. exactly the snap this travel
    // exists to remove, one frame before it starts.
    this._handover = { elapsed: 0, from, to: { ...from } };
    this._handover.to = this._automaticView();
  }

  /** Where the automatic mode wants the viewport — measured, not derived.
   *
   * It performs the HARD framing this mode does, reads the result off the
   * viewport and puts the visitor's view straight back. Computing the numbers
   * a second time instead would be a second implementation of _frame() and of
   * the traversal's opening zoom, free to drift away from the ones the wall
   * actually uses; this way the handover can only ever land where the old
   * jump landed. */
  _automaticView() {
    const before = { pan: { ...this.cy.pan() }, zoom: this.cy.zoom() };
    if (this._mode === 'fit') {
      this._frame();
    } else {
      // Pan mode does not re-frame: its opening dwell holds the pan where it
      // is and puts the zoom on the calibrated travel level, about the
      // viewport centre — which carries the pan with it. Reproduced by simply
      // doing it, at clock 0, where the breathing wave is exactly zero and the
      // first step() will therefore continue from the same level.
      this._applyZoom(this._breathingZoom(this._travelLevel(), 0));
    }
    const to = { x: this.cy.pan().x, y: this.cy.pan().y, zoom: this.cy.zoom() };
    this.cy.zoom(before.zoom);
    this.cy.pan(before.pan);
    return to;
  }

  /** One frame of the handover, on the same clock as the tour.
   *
   * Cytoscape's cy.animate() was the obvious alternative and is the wrong tool
   * here: it drives itself from its own requestAnimationFrame, so it would be
   * a second writer on this viewport next to the step() loop that is already
   * running — and the traversal's breathing zoom writes every single frame.
   * Two writers per frame is the kind of bug that surfaces later as jitter.
   * Sharing step()'s dt also means a test can drive the handover, and that a
   * visitor's touch cancels it by dropping one object. */
  _advanceHandover(dtMs) {
    const handover = this._handover;
    handover.elapsed += dtMs;
    const t = Math.min(1, handover.elapsed / ROAM.handoverMs);
    // The same cosine as a leg of the tour, so the handover and the travel it
    // hands over to feel like one movement.
    const eased = easeInOut(t);
    const { from, to } = handover;
    this.cy.zoom(t >= 1 ? to.zoom : lerpZoom(from.zoom, to.zoom, eased));
    this.cy.pan(
      t >= 1
        ? { x: to.x, y: to.y }
        : { x: from.x + (to.x - from.x) * eased, y: from.y + (to.y - from.y) * eased },
    );
    if (t >= 1) this._handover = null;
  }

  step(dtSeconds) {
    const dtMs = dtSeconds * 1000;
    // The handover owns the viewport until it lands: letting the traversal
    // write pan and zoom in the same frame is exactly the two-writer problem
    // the handover avoids by not being a cy.animate().
    if (this._handover) {
      this._advanceHandover(dtMs);
      return;
    }
    if (this._mode !== 'pan') return;
    if (!this._roam) this._roam = { phase: 'dwell', elapsed: 0, targetId: null, clock: 0 };
    const roam = this._roam;
    roam.clock += dtMs;
    roam.elapsed += dtMs;

    if (roam.phase === 'dwell') {
      // Hold still (bar the breathing) until the beat is over, then choose.
      this._applyZoom(this._breathingZoom(this._travelLevel(), roam.clock));
      if (roam.elapsed < (roam.duration ?? this._dwellDuration())) return;
      const target = this._pickTarget();
      if (!target) return; // empty wall: keep waiting rather than throwing
      roam.phase = 'travel';
      roam.elapsed = 0;
      // Frozen for the whole leg: reading the live speed every frame would
      // rescale a glide already in progress, and the eased position would
      // jump the moment the operator touched the slider.
      roam.duration = this._travelDuration();
      roam.targetId = target.id();
      roam.from = { ...this.cy.pan() };
      roam.to = this._panForCentering(target);
      return;
    }

    // travel
    const t = Math.min(1, roam.elapsed / (roam.duration ?? this._travelDuration()));
    const eased = easeInOut(t);
    this._applyZoom(this._breathingZoom(this._travelLevel(), roam.clock));
    this.cy.pan({
      x: roam.from.x + (roam.to.x - roam.from.x) * eased,
      y: roam.from.y + (roam.to.y - roam.from.y) * eased,
    });
    if (t >= 1) {
      roam.phase = 'dwell';
      roam.elapsed = 0;
      roam.duration = this._dwellDuration();
    }
  }

  /** The zoom level the traversal travels at, derived from the calibrated
   * factor the same way `_frame` derives it — so "1.8×" means the same thing
   * whether the operator is in fit or in pan. */
  _travelLevel() {
    if (this._roamBaseLevel === undefined || this._roamBaseFactor !== this._zoomFactor) {
      const before = { pan: { ...this.cy.pan() }, zoom: this.cy.zoom() };
      this._fitWith(() => this.cy.fit(this.padding));
      this._roamBaseLevel = this.cy.zoom() * this._zoomFactor;
      this._roamBaseFactor = this._zoomFactor;
      this.cy.zoom(before.zoom);
      this.cy.pan(before.pan);
    }
    return this._roamBaseLevel;
  }

  _applyZoom(level) {
    // Around the viewport centre, so breathing does not also drift the frame.
    this.cy.zoom({
      level,
      renderedPosition: { x: this.cy.width() / 2, y: this.cy.height() / 2 },
    });
  }

  /** The pan that puts `node` in the middle of the viewport at current zoom. */
  _panForCentering(node) {
    const zoom = this.cy.zoom();
    const pos = node.position();
    return {
      x: this.cy.width() / 2 - pos.x * zoom,
      y: this.cy.height() / 2 - pos.y * zoom,
    };
  }
}
