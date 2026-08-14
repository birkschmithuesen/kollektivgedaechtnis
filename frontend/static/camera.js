// The camera is its own component from the start, even if everything fits.
// Mode 'pan' IS the touch fallback: a non-interactive automatic animation.

const MODES = ['fit', 'manual', 'pan'];

export class Camera {
  constructor(cy, { panSpeed = 18, padding = 60, zoomFactor = 1 } = {}) {
    this.cy = cy;
    this.panSpeed = panSpeed;
    this.padding = padding;
    // 1 = the whole net in frame. >1 = that many times tighter, i.e. only
    // 1/factor of the net's width is on the wall. Fit-all is illegible at 50
    // persons (pre-render series, 2026-08-14), so the zoom level is a setting
    // of this component, not a second camera bolted on next to it.
    this._zoomFactor = 1;
    this._mode = 'fit';
    this._direction = -1;
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

  setMode(mode) {
    if (!MODES.includes(mode)) throw new Error(`unknown camera mode: ${mode}`);
    this._mode = mode;
    this._applyInteractivity(mode);
    if (mode === 'fit') this._frame();
  }

  setZoomFactor(factor) {
    if (!(factor >= 1)) throw new Error(`zoom factor must be >= 1: ${factor}`);
    const changed = factor !== this._zoomFactor;
    this._zoomFactor = factor;
    // Manual is the visitor's mode: re-framing under their hands would fight
    // them. Every other mode is driven, so it re-frames at the new level.
    if (changed && this._mode !== 'manual') this._frame();
  }

  /** Point the camera at a subset — one cluster instead of the whole net.
   *
   * This is the framing an automatic traversal dwells on, and what the
   * pre-render shoots for the close view. It deliberately does not change the
   * mode: the interaction rules stay whatever the operator set. */
  focus(eles, padding = this.padding) {
    this.cy.fit(eles, padding);
  }

  _frame() {
    this.cy.fit(this.padding);
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
    this.cy.autoungrabify(!interactive);
  }

  onGraphChanged() {
    if (this._mode === 'fit') this._frame();
  }

  step(dtSeconds) {
    if (this._mode !== 'pan') return;
    const extent = this.cy.extent();
    const graphWidth = extent.x2 - extent.x1;
    if (graphWidth <= 0) return;
    const pan = this.cy.pan();
    const dx = this._direction * this.panSpeed * dtSeconds;
    const next = pan.x + dx;
    const limit = Math.max(graphWidth, this.cy.width());
    if (next < -limit || next > limit) this._direction *= -1;
    this.cy.pan({ x: pan.x + this._direction * this.panSpeed * dtSeconds, y: pan.y });
  }
}
