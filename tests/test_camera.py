import pytest

CY_STUB = """
window.cyStub = {
  calls: [],
  _pan: {x: 0, y: 0},
  _zoom: 1,
  fit(padding) { this.calls.push(['fit', padding]); },
  pan(p) { if (p === undefined) return this._pan; this._pan = p; this.calls.push(['pan', p]); },
  zoom(z) { if (z === undefined) return this._zoom; this._zoom = z; },
  extent() { return {x1: 0, y1: 0, x2: 4000, y2: 1000, w: 4000, h: 1000}; },
  width() { return 1920; },
  height() { return 1080; },
  elements() { return {length: 4}; },
};
"""


@pytest.fixture()
def camera(page, static_server):
    page.goto(f"{static_server}/frontend/static/test-harness.html")
    page.evaluate(CY_STUB)
    page.evaluate(
        """async () => {
             const { Camera } = await import('./camera.js');
             window.cam = new Camera(window.cyStub, { panSpeed: 100 });
           }"""
    )
    return page


def test_default_mode_is_fit_and_fits_on_graph_change(camera):
    assert camera.evaluate("window.cam.mode") == "fit"
    camera.evaluate("window.cam.onGraphChanged()")
    assert camera.evaluate("window.cyStub.calls.filter(c => c[0] === 'fit').length") == 1


def test_manual_mode_never_moves_the_viewport_by_itself(camera):
    camera.evaluate("window.cam.setMode('manual')")
    camera.evaluate("window.cam.onGraphChanged()")
    camera.evaluate("window.cam.step(1.0)")
    assert camera.evaluate("window.cyStub.calls.length") == 0


def test_pan_mode_moves_the_viewport_over_time(camera):
    camera.evaluate("window.cam.setMode('pan')")
    camera.evaluate("window.cam.step(1.0)")
    first = camera.evaluate("window.cyStub._pan.x")
    camera.evaluate("window.cam.step(1.0)")
    second = camera.evaluate("window.cyStub._pan.x")
    assert first != 0
    assert second != first


def test_pan_reverses_at_the_edge_instead_of_running_away(camera):
    camera.evaluate("window.cam.setMode('pan')")
    camera.evaluate("for (let i = 0; i < 400; i++) window.cam.step(1.0)")
    positions = camera.evaluate(
        "window.cyStub.calls.filter(c => c[0] === 'pan').map(c => c[1].x)"
    )
    assert min(positions) > -100000 and max(positions) < 100000
    assert any(a > b for a, b in zip(positions, positions[1:]))  # direction reversed


def test_an_unknown_mode_is_rejected(camera):
    assert camera.evaluate("(() => { try { window.cam.setMode('warp'); return 'no'; } catch (e) { return 'raised'; } })()") == "raised"
