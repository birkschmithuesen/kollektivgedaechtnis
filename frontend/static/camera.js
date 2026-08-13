// The camera is its own component from the start, even if everything fits.
// Mode 'pan' IS the touch fallback: a non-interactive automatic animation.

const MODES = ['fit', 'manual', 'pan'];

export class Camera {
  constructor(cy, { panSpeed = 18, padding = 60 } = {}) {
    this.cy = cy;
    this.panSpeed = panSpeed;
    this.padding = padding;
    this._mode = 'fit';
    this._direction = -1;
  }

  get mode() {
    return this._mode;
  }

  setMode(mode) {
    if (!MODES.includes(mode)) throw new Error(`unknown camera mode: ${mode}`);
    this._mode = mode;
    if (mode === 'fit') this.cy.fit(this.padding);
  }

  onGraphChanged() {
    if (this._mode === 'fit') this.cy.fit(this.padding);
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
