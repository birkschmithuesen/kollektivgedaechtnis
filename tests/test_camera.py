import pytest

CY_STUB = """
window.cyStub = {
  calls: [],
  // Interactivity toggles are recorded separately from `calls` so that
  // existing assertions on `calls` (e.g. "manual mode produces zero calls")
  // are unaffected by the interactivity gating the camera also does now.
  interactivity: [],
  _pan: {x: 0, y: 0},
  _zoom: 1,
  _panningEnabled: true,
  _zoomingEnabled: true,
  _autoungrabify: false,
  // cy.fit() takes either a padding or (collection, padding) — the camera
  // uses both, so the stub records which elements it was pointed at.
  fit(a, b) {
    // The real cy.fit() *sets* the zoom to the fit-all level; 1 stands in for
    // that here, so a zoom factor is always applied to a fresh fit and never
    // compounds with the level a previous call left behind.
    this._zoom = 1;
    if (b === undefined) this.calls.push(['fit', a]);
    else this.calls.push(['fit', a.stubName, b]);
  },
  pan(p) { if (p === undefined) return this._pan; this._pan = p; this.calls.push(['pan', p]); },
  // cy.zoom() takes a level or {level, renderedPosition}; the camera zooms
  // about the viewport centre, so the object form has to be understood.
  zoom(z) {
    if (z === undefined) return this._zoom;
    this._zoom = typeof z === 'object' ? z.level : z;
    this.calls.push(['zoom', this._zoom]);
  },
  extent() { return {x1: 0, y1: 0, x2: 4000, y2: 1000, w: 4000, h: 1000}; },
  width() { return 1920; },
  height() { return 1080; },
  elements() { return {length: 4}; },
  userPanningEnabled(v) {
    if (v === undefined) return this._panningEnabled;
    this._panningEnabled = v;
    this.interactivity.push(['userPanningEnabled', v]);
  },
  userZoomingEnabled(v) {
    if (v === undefined) return this._zoomingEnabled;
    this._zoomingEnabled = v;
    this.interactivity.push(['userZoomingEnabled', v]);
  },
  autoungrabify(v) {
    if (v === undefined) return this._autoungrabify;
    this._autoungrabify = v;
    this.interactivity.push(['autoungrabify', v]);
  },
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


def test_the_default_zoom_factor_fits_the_whole_net(camera):
    assert camera.evaluate("window.cam.zoomFactor") == 1
    camera.evaluate("window.cam.onGraphChanged()")
    # Fit-all must stay exactly a fit: no zoom call on top of it.
    assert camera.evaluate("window.cyStub.calls.filter(c => c[0] === 'zoom').length") == 0


def test_a_zoom_factor_sits_that_many_times_tighter_than_fit_all(camera):
    camera.evaluate("window.cam.setZoomFactor(2)")
    assert camera.evaluate("window.cam.zoomFactor") == 2
    # fit() first (the stub leaves zoom at 1 = the fit-all level), then 2x it.
    assert camera.evaluate("window.cyStub._zoom") == 2
    assert camera.evaluate("window.cyStub.calls.filter(c => c[0] === 'fit').length") == 1


def test_the_zoom_factor_is_reapplied_when_the_graph_changes(camera):
    camera.evaluate("window.cam.setZoomFactor(3)")
    camera.evaluate("window.cyStub.calls.length = 0")
    camera.evaluate("window.cam.onGraphChanged()")
    assert camera.evaluate("window.cyStub.calls") == [["fit", 60], ["zoom", 3]]


def test_a_zoom_factor_below_one_is_rejected(camera):
    # Below 1 would frame emptiness around the net on an unattended wall.
    assert (
        camera.evaluate(
            "(() => { try { window.cam.setZoomFactor(0.5); return 'no'; } catch (e) { return 'raised'; } })()"
        )
        == "raised"
    )


def test_manual_mode_is_never_reframed_by_a_zoom_factor_change(camera):
    camera.evaluate("window.cam.setMode('manual')")
    camera.evaluate("window.cyStub.calls.length = 0")
    camera.evaluate("window.cam.setZoomFactor(4)")
    assert camera.evaluate("window.cyStub.calls.length") == 0


def test_focus_frames_only_the_given_elements(camera):
    camera.evaluate("window.cam.focus({stubName: 'cluster'}, 40)")
    assert camera.evaluate("window.cyStub.calls") == [["fit", "cluster", 40]]


def test_an_unknown_mode_is_rejected(camera):
    assert camera.evaluate("(() => { try { window.cam.setMode('warp'); return 'no'; } catch (e) { return 'raised'; } })()") == "raised"


def test_initial_fit_mode_disables_panning_zooming_and_grabbing(camera):
    # A stray touch/mouse must not be able to pan the wall or drag a node off
    # its persisted position from the moment the camera is constructed, not
    # only from the first setMode() call onward.
    assert camera.evaluate("window.cyStub._panningEnabled") is False
    assert camera.evaluate("window.cyStub._zoomingEnabled") is False
    assert camera.evaluate("window.cyStub._autoungrabify") is True


def test_manual_mode_enables_panning_zooming_and_grabbing(camera):
    camera.evaluate("window.cyStub.interactivity.length = 0")
    camera.evaluate("window.cam.setMode('manual')")
    calls = camera.evaluate("window.cyStub.interactivity")
    assert ["userPanningEnabled", True] in calls
    assert ["userZoomingEnabled", True] in calls
    assert ["autoungrabify", False] in calls
    assert camera.evaluate("window.cyStub._panningEnabled") is True
    assert camera.evaluate("window.cyStub._zoomingEnabled") is True
    assert camera.evaluate("window.cyStub._autoungrabify") is False


def test_fit_and_pan_modes_disable_panning_zooming_and_grabbing(camera):
    for mode in ("fit", "pan"):
        camera.evaluate("window.cyStub.interactivity.length = 0")
        camera.evaluate(f"window.cam.setMode('{mode}')")
        calls = camera.evaluate("window.cyStub.interactivity")
        assert ["userPanningEnabled", False] in calls, mode
        assert ["userZoomingEnabled", False] in calls, mode
        assert ["autoungrabify", True] in calls, mode
        assert camera.evaluate("window.cyStub._panningEnabled") is False, mode
        assert camera.evaluate("window.cyStub._zoomingEnabled") is False, mode
        assert camera.evaluate("window.cyStub._autoungrabify") is True, mode
