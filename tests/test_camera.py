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
  // The roaming camera picks term nodes to travel to, so the stub has to
  // provide a small graph. Positions are spread far apart on purpose: a leg
  // between them produces a pan delta big enough to assert on.
  _terms: [
    {id: 't1', degree: 5, x: 500, y: 300},
    {id: 't2', degree: 1, x: 3000, y: 800},
    {id: 't3', degree: 3, x: 1500, y: 100},
  ],
  nodes(selector) {
    const stub = this;
    const list = selector === '.term' ? this._terms : this._terms;
    const wrap = (items) => {
      const collection = items.map((t) => ({
        id: () => t.id,
        degree: () => t.degree,
        position: () => ({x: t.x, y: t.y}),
      }));
      collection.empty = () => collection.length === 0;
      collection.filter = (fn) => wrap(items.filter((t, i) => fn(collection[i])));
      collection.map = (fn) => items.map((t, i) => fn(collection[i]));
      return collection;
    };
    void stub;
    return wrap(list);
  },
  getElementById(id) {
    const found = this._terms.some((t) => t.id === id);
    return {empty: () => !found};
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


def test_pan_mode_travels_towards_a_term_instead_of_sliding_sideways(camera):
    """The automatic mode goes somewhere; it does not drift across the field."""
    camera.evaluate("window.cam.setMode('pan')")
    # Sit out the opening dwell, then take a step into the first leg.
    camera.evaluate("window.cam.step(5.0)")
    assert camera.evaluate("window.cam.roamState.phase") == "travel"
    target = camera.evaluate("window.cam.roamState.targetId")
    assert target in ("t1", "t2", "t3")

    before = camera.evaluate("window.cyStub._pan.x")
    camera.evaluate("window.cam.step(1.0)")
    assert camera.evaluate("window.cyStub._pan.x") != before


def test_a_leg_starts_and_ends_at_zero_speed(camera):
    """Cosine easing: no visible kick at the start, no slam at the arrival.

    Asserted as a relation, not a constant — the first slice of a leg must
    move less than the middle slice, and so must the last.
    """
    camera.evaluate("window.cam.setMode('pan')")
    camera.evaluate("window.cam.step(5.0)")  # into travel
    samples = camera.evaluate(
        """(() => {
             const xs = [window.cyStub._pan.x];
             for (let i = 0; i < 10; i++) { window.cam.step(0.52); xs.push(window.cyStub._pan.x); }
             return xs;
           })()"""
    )
    deltas = [abs(b - a) for a, b in zip(samples, samples[1:])]
    middle = max(deltas)
    assert deltas[0] < middle
    assert deltas[-1] < middle


def test_the_camera_rests_after_arriving_before_choosing_again(camera):
    """The dwell is the beat that makes the motion read as deliberate."""
    camera.evaluate("window.cam.setMode('pan')")
    camera.evaluate("window.cam.step(5.0)")  # into travel
    camera.evaluate("window.cam.step(6.0)")  # past the end of the leg
    assert camera.evaluate("window.cam.roamState.phase") == "dwell"


def test_direction_never_changes_mid_flight(camera):
    """No bounce: within one leg the pan advances monotonically.

    The old camera reversed against an invisible wall, which is the exact
    moment a viewer sees the machine. Every direction change now happens at a
    standstill, between legs.
    """
    camera.evaluate("window.cam.setMode('pan')")
    camera.evaluate("window.cam.step(5.0)")
    xs = camera.evaluate(
        """(() => {
             const xs = [window.cyStub._pan.x];
             for (let i = 0; i < 8; i++) { window.cam.step(0.5); xs.push(window.cyStub._pan.x); }
             return xs;
           })()"""
    )
    deltas = [b - a for a, b in zip(xs, xs[1:])]
    signs = {d > 0 for d in deltas if abs(d) > 1e-9}
    assert len(signs) <= 1, f"direction flipped mid-leg: {deltas}"


def test_a_target_that_leaves_the_graph_does_not_strand_the_camera(camera):
    """Density raised or term hidden mid-leg: restart, never point at nothing."""
    camera.evaluate("window.cam.setMode('pan')")
    camera.evaluate("window.cam.step(5.0)")
    camera.evaluate("window.cyStub._terms = []")
    camera.evaluate("window.cam.onGraphChanged()")
    assert camera.evaluate("window.cam.roamState.targetId") is None
    camera.evaluate("window.cam.step(5.0)")  # must not throw on an empty wall


def test_the_tour_runs_at_full_speed_by_default(camera):
    assert camera.evaluate("window.cam.roamSpeed") == 1


def test_a_quarter_speed_leg_takes_four_times_as_long(camera):
    """The slider scales DURATIONS, so a leg still arrives — it just lingers.

    Asserted as a relation between two runs rather than against a millisecond
    constant: the tuned pace may be retuned, the 4x ratio is the contract.
    """

    def leg_seconds(speed):
        camera.evaluate("(s) => { window.cam.setRoamSpeed(s); window.cam.setMode('pan'); }", speed)
        # Step out of the opening dwell in small slices until travel starts.
        for _ in range(400):
            camera.evaluate("window.cam.step(0.1)")
            if camera.evaluate("window.cam.roamState.phase") == "travel":
                break
        seconds = 0.0
        for _ in range(1000):
            camera.evaluate("window.cam.step(0.1)")
            seconds += 0.1
            if camera.evaluate("window.cam.roamState.phase") == "dwell":
                break
        return seconds

    full = leg_seconds(1)
    quarter = leg_seconds(0.25)
    assert 3.5 < quarter / full < 4.5, f"full={full}s quarter={quarter}s"


def test_changing_speed_mid_leg_does_not_jerk_the_camera(camera):
    """The duration is frozen when a leg starts.

    Reading the live speed every frame would rescale a glide already in
    flight, and the eased position would jump the moment the operator touched
    the slider — the one thing the easing exists to prevent.
    """
    camera.evaluate("window.cam.setMode('pan')")
    camera.evaluate("window.cam.step(5.0)")  # into travel at full speed
    before = camera.evaluate("window.cyStub._pan.x")
    camera.evaluate("window.cam.setRoamSpeed(0.25)")
    camera.evaluate("window.cam.step(0.1)")
    after = camera.evaluate("window.cyStub._pan.x")
    # One 0.1s slice of an eased leg moves a little; a rescale would teleport.
    assert abs(after - before) < 200, f"jumped {abs(after - before):.0f}px on a speed change"


def test_the_speed_is_clamped_rather_than_rejected(camera):
    """A bad value must slow the wall down, never stop it rendering."""
    camera.evaluate("window.cam.setRoamSpeed(9)")
    assert camera.evaluate("window.cam.roamSpeed") == 1
    camera.evaluate("window.cam.setRoamSpeed(0)")
    assert camera.evaluate("window.cam.roamSpeed") == 0.25


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
