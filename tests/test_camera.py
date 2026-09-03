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
    // A real fit re-centres, i.e. it moves the pan as well. Recorded here as
    // a plain assignment (not via pan(), which would add a call) so that the
    // tests asserting exact call sequences keep reading the same.
    this._pan = {x: 0, y: 0};
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


def in_die_fahrt(camera):
    """In den Modus `pan` UND ueber die Einfahrt hinweg.

    Seit dem 2026-09-02 ist auch der Eintritt in `pan` eine Uebergabefahrt
    (5 s, ROAM.handoverMs) statt eines Sprungs: `fit` zeigt seither woertlich
    das ganze Netz, die Fahrt laeuft auf der Mindestschrift, und zwischen
    beiden liegt damit ein Weg, den es vorher nicht gab (beide lagen auf
    `fitLevel x zoomFactor`).

    Die Tests unten wollen die FAHRT messen, nicht die Einfahrt. Ohne dieses
    Ausfahren wuerden sie nicht etwa scheitern, sondern Schlimmeres: Sie saessen
    danach in der Standzeit, in der sich per Definition nichts bewegt, und
    meldeten Erfolg, ohne irgendetwas geprueft zu haben.
    """
    camera.evaluate("window.cam.setMode('pan')")
    camera.evaluate("window.cam.step(5.0)")


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
    in_die_fahrt(camera)
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
    in_die_fahrt(camera)
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
    in_die_fahrt(camera)
    camera.evaluate("window.cam.step(5.0)")  # into travel
    camera.evaluate("window.cam.step(6.0)")  # past the end of the leg
    assert camera.evaluate("window.cam.roamState.phase") == "dwell"


def test_direction_never_changes_mid_flight(camera):
    """No bounce: within one leg the pan advances monotonically.

    The old camera reversed against an invisible wall, which is the exact
    moment a viewer sees the machine. Every direction change now happens at a
    standstill, between legs.
    """
    in_die_fahrt(camera)
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
    in_die_fahrt(camera)
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
    in_die_fahrt(camera)
    camera.evaluate("window.cam.step(5.0)")  # into travel at full speed
    before = camera.evaluate("window.cyStub._pan.x")
    camera.evaluate("window.cam.setRoamSpeed(0.25)")
    camera.evaluate("window.cam.step(0.1)")
    after = camera.evaluate("window.cyStub._pan.x")
    # One 0.1s slice of an eased leg moves a little; a rescale would teleport.
    assert abs(after - before) < 200, f"jumped {abs(after - before):.0f}px on a speed change"


def test_the_speed_is_clamped_rather_than_rejected(camera):
    """A bad value must slow the wall down, never stop it rendering.

    Auf die ABSICHT geprueft und nicht mehr auf die Untergrenze selbst: der
    Wert stand auf 0,25, wurde am 2026-09-01 auf Birks Rueckmeldung hin auf
    0,05 geoeffnet („mach mal nach unten noch mehr headroom") — und dieser
    Test blieb auf 0,25 stehen und war seitdem rot. Eine Zahl, die als
    Einstellung gedacht ist, gehoert nicht als Konstante in einen Test
    gespiegelt.
    """
    camera.evaluate("window.cam.setRoamSpeed(9)")
    assert camera.evaluate("window.cam.roamSpeed") == 1, "zu schnell wird nicht gedeckelt"

    camera.evaluate("window.cam.setRoamSpeed(0)")
    langsam = camera.evaluate("window.cam.roamSpeed")
    assert 0 < langsam < 1, f"0 muss zu einem langsamen, aber laufenden Tempo werden: {langsam}"

    camera.evaluate("window.cam.setRoamSpeed(NaN)")
    assert camera.evaluate("window.cam.roamSpeed") == 1, "NaN faellt auf volles Tempo zurueck"


def test_fit_zeigt_das_ganze_netz_und_rechnet_nichts_darauf(camera):
    """„Alles zeigen" heisst alles.

    Bis zum 2026-09-02 rechnete `fit` den Zoomfaktor des Operators auf den
    Rahmen und zeigte damit 1,55x enger als alles -- der Modus widersprach
    seinem eigenen Namen. Die Naehe entscheidet jetzt allein die
    Mindestschrift, und die wirkt in `pan`.
    """
    camera.evaluate("window.cam.onGraphChanged()")
    assert camera.evaluate("window.cyStub.calls.filter(c => c[0] === 'zoom').length") == 0
    assert camera.evaluate("window.cyStub._zoom") == 1


def test_die_mindestschrift_ist_der_zoom_bei_dem_die_schrift_sie_erreicht(camera):
    """`labelSize x zoom` ist die Schrift auf der Wand -- das ist die Rechnung.

    Der Stub laesst nach einem fit() den Zoom auf 1 stehen (= Vollansicht), die
    Schrift steht dort also auf `labelSize`. Bei einer Mindestschrift von 52 px
    und einer Schriftgroesse von 26 Modelleinheiten muss die Fahrt auf 2,0
    laufen -- und keinen Schritt enger.
    """
    camera.evaluate("window.cam.setLabelSize(26)")
    camera.evaluate("window.cam.setMinLabel(52)")
    in_die_fahrt(camera)
    assert camera.evaluate("window.cyStub._zoom") == pytest.approx(2.0, rel=1e-3)


def test_ein_theme_mit_groesserer_schrift_braucht_weniger_zoom(camera):
    """Dieselbe Mindestschrift, doppelte Schriftgroesse, halber Zoom.

    Der Grund, warum die Schriftgroesse ueberhaupt hereingereicht wird: Die
    Themes setzen `--label-size` zwischen 22 (theme-a) und 44 (theme-c). Eine
    Mindestgroesse in Pixeln waere ohne diesen Bezug eine Aussage ueber
    Modelleinheiten und damit je Theme etwas anderes.
    """
    camera.evaluate("window.cam.setMinLabel(52)")
    camera.evaluate("window.cam.setLabelSize(52)")
    in_die_fahrt(camera)
    assert camera.evaluate("window.cyStub._zoom") == pytest.approx(1.0, rel=1e-3)


def test_ein_unbrauchbarer_wert_haelt_die_wand_nicht_an(camera):
    """Der Wert kommt ueber /events herein; eine kaputte Zahl darf nichts kosten.

    Der Vorgaenger `setZoomFactor` warf unter 1, und projection.html musste den
    Wurf abfangen. Eine unbeaufsichtigte Wand muss langsamer werden oder stehen
    bleiben, nie aufhoeren zu zeichnen -- dieselbe Regel wie bei
    `clampRoamSpeed`.
    """
    camera.evaluate("window.cam.setMinLabel(40)")
    for kaputt in ("0", "-5", "NaN", "'weit'", "undefined"):
        camera.evaluate(f"window.cam.setMinLabel({kaputt})")
        assert camera.evaluate("window.cam.minLabelPx") == 40, kaputt


def test_manual_mode_is_never_reframed_by_a_min_label_change(camera):
    camera.evaluate("window.cam.setMode('manual')")
    camera.evaluate("window.cyStub.calls.length = 0")
    camera.evaluate("window.cam.setMinLabel(80)")
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


def test_manual_mode_enables_panning_and_zooming_but_never_grabbing(camera):
    # Birk, 2026-08-30, live at the station: in manual mode a visitor's hand
    # pulled portraits and terms out of the arrangement. Panning and zooming
    # are what manual mode is FOR and stay; the arrangement belongs to the
    # layout, in every mode.
    camera.evaluate("window.cyStub.interactivity.length = 0")
    camera.evaluate("window.cam.setMode('manual')")
    calls = camera.evaluate("window.cyStub.interactivity")
    assert ["userPanningEnabled", True] in calls
    assert ["userZoomingEnabled", True] in calls
    assert ["autoungrabify", False] not in calls
    assert camera.evaluate("window.cyStub._panningEnabled") is True
    assert camera.evaluate("window.cyStub._zoomingEnabled") is True
    assert camera.evaluate("window.cyStub._autoungrabify") is True


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


def test_no_sequence_of_modes_ever_makes_a_node_grabbable(camera):
    # The guarantee stated as a sweep rather than per mode: whatever the
    # operator, the idle timeout and a visitor's hand do to the mode, in what
    # order, `autoungrabify` is never once switched off.
    camera.evaluate("window.cyStub.interactivity.length = 0")
    for mode in ("manual", "fit", "manual", "pan", "manual", "pan", "fit"):
        camera.evaluate(f"window.cam.setMode('{mode}')")
        assert camera.evaluate("window.cyStub._autoungrabify") is True, mode
    off = [call for call in camera.evaluate("window.cyStub.interactivity") if call == ["autoungrabify", False]]
    assert off == []


# --- Handing the view back from the visitor to the automatic mode ------------
#
# Birk at the station, 2026-08-29: after the 30 s idle timeout the touchscreen
# SNAPPED into the automatic view. The camera has to travel there instead — the
# visitor's abandoned close-up and the automatic view are two ends of one move.


def _visitor_leaves_a_close_up(camera, mode):
    """Somebody pans and zooms by hand, then lets go and the timeout fires."""
    camera.evaluate("window.cam.setMode('manual')")
    camera.evaluate("window.cyStub._zoom = 4; window.cyStub._pan = {x: 700, y: 400};")
    camera.evaluate(f"window.cam.setMode('{mode}')")


def _view_samples(camera, count, dt=0.1):
    return camera.evaluate(
        """([count, dt]) => {
             const seen = [];
             for (let i = 0; i < count; i++) {
                 window.cam.step(dt);
                 seen.push({x: window.cyStub._pan.x, y: window.cyStub._pan.y,
                            zoom: window.cyStub._zoom});
             }
             return seen;
           }""",
        [count, dt],
    )


@pytest.mark.parametrize("mode", ["fit", "pan"])
def test_leaving_manual_does_not_move_the_view_in_the_same_frame(camera, mode):
    """The mode flips at once; the picture has not gone anywhere yet.

    Both ways back matter: the operator may have the wall on 'fit' or on 'pan'
    when a visitor's 30 s run out, and the fallback lands on whichever it is.
    """
    _visitor_leaves_a_close_up(camera, mode)
    assert camera.evaluate("window.cam.mode") == mode
    assert camera.evaluate("window.cyStub._zoom") == 4
    assert camera.evaluate("window.cyStub._pan") == {"x": 700, "y": 400}


@pytest.mark.parametrize("mode", ["fit", "pan"])
def test_pan_and_zoom_both_approach_the_automatic_view_step_by_step(camera, mode):
    """Not one frame, not zoom-only: the whole view travels.

    A visitor who pinched in deep is the normal case, so animating the pan and
    letting the zoom jump would still read as a snap.
    """
    _visitor_leaves_a_close_up(camera, mode)
    target = camera.evaluate("({...window.cam.handoverTarget})")
    samples = _view_samples(camera, 10)  # 1 s, still inside the handover

    zooms = [4.0] + [s["zoom"] for s in samples]
    xs = [700.0] + [s["x"] for s in samples]
    moved = 0
    # No frame may carry the bulk of the distance — that IS the snap. Asserted
    # per axis so an animated pan with a jumping zoom does not pass either.
    for axis, start, goal in ((zooms, 4.0, target["zoom"]), (xs, 700.0, target["x"])):
        span = abs(goal - start)
        if span == 0:
            # In 'pan' mode the traversal keeps the visitor's pan and only
            # changes the zoom; the pan target then differs from where the
            # visitor left it solely through the zoom's anchor at the viewport
            # centre, which the cy stub does not model. Nothing to assert here.
            continue
        moved += 1
        biggest = max(abs(b - a) for a, b in zip(axis, axis[1:]))
        assert biggest < 0.3 * span, f"one frame moved {biggest} of {span}: {axis}"
        # And one-way: a handover must not overshoot and come back.
        signs = {b > a for a, b in zip(axis, axis[1:]) if abs(b - a) > 1e-9}
        assert len(signs) <= 1, axis
    # Guard against the assertions above quietly emptying out: on the way back
    # to 'fit' the frame re-centres, so both axes have a distance to travel.
    assert moved == (2 if mode == "fit" else 1)


def _run_the_handover_to_the_end(camera):
    """Step until it lands, and report how long it took."""
    return camera.evaluate(
        """() => {
             let frames = 0;
             while (window.cam.handoverTarget && frames < 2000) {
                 window.cam.step(0.02);
                 frames += 1;
             }
             return frames * 0.02;
           }"""
    )


@pytest.mark.parametrize("mode", ["fit", "pan"])
def test_the_handover_lands_exactly_on_the_automatic_view(camera, mode):
    """It is a handover, not a drift: it ends where the hard jump used to."""
    _visitor_leaves_a_close_up(camera, mode)
    target = camera.evaluate("({...window.cam.handoverTarget})")
    seconds = _run_the_handover_to_the_end(camera)
    assert camera.evaluate("window.cyStub._zoom") == pytest.approx(target["zoom"])
    assert camera.evaluate("window.cyStub._pan.x") == pytest.approx(target["x"])
    assert camera.evaluate("window.cyStub._pan.y") == pytest.approx(target["y"])
    # A full leg of the tour (~5 s), on Birk's call after watching it on the
    # wall (2026-08-30). It read as a lurch at 1.5 s; the point is that the
    # takeover should look like the tour simply carrying on. The window stays
    # wide on purpose -- it pins the order of magnitude, not the constant,
    # which lives in ROAM.handoverMs.
    assert 3.0 < seconds < 8.0, seconds


def test_after_the_handover_a_fit_wall_stands_still_again(camera):
    """'fit' is a still picture; only the handover was ever allowed to move."""
    _visitor_leaves_a_close_up(camera, "fit")
    _run_the_handover_to_the_end(camera)
    landed = camera.evaluate("({x: window.cyStub._pan.x, zoom: window.cyStub._zoom})")
    _view_samples(camera, 20)
    assert camera.evaluate("window.cyStub._pan.x") == landed["x"]
    assert camera.evaluate("window.cyStub._zoom") == landed["zoom"]


def test_the_handover_eases_instead_of_running_at_a_constant_speed(camera):
    """Same feel as a leg of the tour: cosine in, cosine out."""
    _visitor_leaves_a_close_up(camera, "fit")
    # Sample past the end of the handover (ROAM.handoverMs = 5000): the ease
    # is only visible over the WHOLE travel. Sampling a fixed 1.5 s window --
    # what this test did while the handover lasted exactly that long -- now
    # catches just the accelerating first third and would fail on a perfectly
    # good ease.
    xs = [700.0] + [s["x"] for s in _view_samples(camera, 60)]
    deltas = [abs(b - a) for a, b in zip(xs, xs[1:])]
    moving = [d for d in deltas if d > 1e-9]
    assert moving[0] < max(moving)
    assert moving[-1] < max(moving)


def test_a_visitor_touching_mid_handover_gets_the_view_back_immediately(camera):
    """The case that happens all day in an exhibition.

    A half-run handover that keeps running would work against the hand that
    just grabbed the wall, so `manual` has to drop it on the spot.
    """
    _visitor_leaves_a_close_up(camera, "pan")
    _view_samples(camera, 4)  # mid-flight
    camera.evaluate("window.cam.setMode('manual')")
    assert camera.evaluate("window.cam.handoverTarget") is None
    held = camera.evaluate("({x: window.cyStub._pan.x, zoom: window.cyStub._zoom})")
    _view_samples(camera, 10)
    assert camera.evaluate("window.cyStub._pan.x") == held["x"]
    assert camera.evaluate("window.cyStub._zoom") == held["zoom"]


def test_the_automatic_tour_only_starts_once_the_handover_has_landed(camera):
    """One writer on the viewport at a time — no traversal under the handover."""
    _visitor_leaves_a_close_up(camera, "pan")
    _view_samples(camera, 4)
    assert camera.evaluate("window.cam.roamState.phase") == "dwell"
    assert camera.evaluate("window.cam.roamState.elapsed") == 0


def test_an_operator_fit_still_frames_in_a_single_frame(camera):
    """The pre-render's contract: `setMode('fit')` places the frame at once.

    sim/prerender.py shoots a screenshot right after setting a camera view, so
    the hard framing has to stay the behaviour everywhere but the way out of a
    visitor's hands.
    """
    camera.evaluate("window.cam.setMode('pan')")
    camera.evaluate("window.cyStub._zoom = 4; window.cyStub._pan = {x: 700, y: 400};")
    camera.evaluate("window.cam.setMode('fit')")
    assert camera.evaluate("window.cyStub._zoom") == 1
    assert camera.evaluate("window.cam.handoverTarget") is None


# --- How much of the portrait ceiling is in force (Birk, 2026-08-30) --------
#
# The portrait size became an upper bound for the DRIVEN modes only
# (projection.js). The camera is the only component that knows which of the
# three regimes the wall is in — driven, in a visitor's hands, or travelling
# between the two — so it publishes that as one number and the projection sizes
# its discs off it. Interpolating on the handover's own clock is what keeps the
# discs from snapping back to the ceiling at the end of the handover travel.


def test_the_driven_modes_apply_the_portrait_ceiling_in_full(camera):
    for mode in ("fit", "pan"):
        camera.evaluate(f"window.cam.setMode('{mode}')")
        assert camera.evaluate("window.cam.portraitCapBlend") == 1, mode


def test_the_visitors_mode_lifts_the_portrait_ceiling_entirely(camera):
    camera.evaluate("window.cam.setMode('manual')")
    assert camera.evaluate("window.cam.portraitCapBlend") == 0


@pytest.mark.parametrize("mode", ["fit", "pan"])
def test_the_ceiling_comes_back_on_over_the_handover_not_at_its_end(camera, mode):
    _visitor_leaves_a_close_up(camera, mode)
    # Not already back on the instant the mode flips — that is the snap.
    assert camera.evaluate("window.cam.portraitCapBlend") == 0

    blends = camera.evaluate(
        """() => {
             const seen = [];
             while (window.cam.handoverTarget && seen.length < 2000) {
                 window.cam.step(0.02);
                 seen.push(window.cam.portraitCapBlend);
             }
             return seen;
           }"""
    )

    # It rises the whole way, monotonically, and no single frame carries more
    # than a fraction of it.
    assert blends[-1] == 1
    assert all(a <= b + 1e-12 for a, b in zip(blends, blends[1:]))
    assert max(b - a for a, b in zip([0.0] + blends, blends)) < 0.2


def test_a_hand_back_on_the_wall_lifts_the_ceiling_again_at_once(camera):
    # Same rule as the pan and the zoom: a half-run handover must not keep
    # shrinking a face under the hand that just grabbed the wall.
    _visitor_leaves_a_close_up(camera, "pan")
    _view_samples(camera, 4)
    assert 0 < camera.evaluate("window.cam.portraitCapBlend") < 1

    camera.evaluate("window.cam.setMode('manual')")

    assert camera.evaluate("window.cam.portraitCapBlend") == 0


def test_die_fahrt_bevorzugt_die_meistgenannten_begriffe(page, static_server):
    """🔴 BIRK, 2026-09-03: „bei der automatischen kamerafahrt sollten die
    meist genannten begriffe angefahren werden."

    Die Gewichtung gab es schon (`ROAM.degreeBias`), sie war mit 2,0 aber zu
    schwach: Am Bestand des Tages gerechnet — 66 Begriffe — kamen die sechs
    haeufigsten zusammen auf 58 % der Fahrten. Mit 3,0 sind es 76 %.

    Nicht hoeher: Bei 4,0 kaeme in einer Stunde praktisch keine Einmal-Nennung
    mehr vor, und die Wand zeigte nur noch ihre eigene Spitze. Genau das
    prueft die zweite Behauptung unten.

    Gemessen wird ueber viele Ziehungen mit festem Zufall, nicht an einer
    einzelnen: Die Auswahl IST zufaellig, nur eben gewichtet.
    """
    page.goto(f"{static_server}/frontend/projection.html?theme=f&deterministisch=1")
    page.wait_for_function("window.kgView !== undefined", timeout=30000)

    graph = {
        "version": 1, "generated_at": 1000.0, "max_terms": 99,
        "nodes": [
            {"id": "p1", "type": "person", "name": "A", "portrait": None,
             "created_at": 1.0, "hidden": False, "x": 0, "y": 0},
            {"id": "oft", "type": "term", "label": "Oft gesagt", "mentions": 9,
             "created_at": 2.0, "hidden": False, "x": 400, "y": 0},
            {"id": "mittel", "type": "term", "label": "Mittel", "mentions": 3,
             "created_at": 2.0, "hidden": False, "x": 0, "y": 400},
            {"id": "selten", "type": "term", "label": "Selten", "mentions": 1,
             "created_at": 2.0, "hidden": False, "x": -400, "y": 0},
        ],
        "edges": [{"id": "e1", "source": "p1", "target": "oft", "evidence": "x"}],
        "quotes": [],
    }
    page.evaluate("(g) => window.kgView.update(g, 99)", graph)
    page.wait_for_function("() => window.kgView.layoutPending === false", timeout=60000)

    verteilung = page.evaluate("""() => {
      const c = window.kgView.camera;
      const zaehler = {};
      for (let i = 0; i < 600; i++) {
        const ziel = c._pickTarget();
        if (!ziel) continue;
        const id = ziel.id();
        zaehler[id] = (zaehler[id] || 0) + 1;
      }
      return zaehler;
    }""")

    oft = verteilung.get("oft", 0)
    mittel = verteilung.get("mittel", 0)
    selten = verteilung.get("selten", 0)
    gesamt = oft + mittel + selten
    assert gesamt > 400, f"zu wenige Ziehungen ausgewertet: {verteilung}"

    # Neunmal gesagt schlaegt dreimal, dreimal schlaegt einmal.
    assert oft > mittel > selten, f"die Haeufigkeit schlaegt sich nicht durch: {verteilung}"
    # Deutlich, nicht knapp: 9^3 zu 1^3 sind 729 zu 1.
    assert oft > 3 * mittel, f"der Vorrang ist zu schwach: {verteilung}"
    # Aber der seltene kommt vor. Eine Wand, die nur noch ihre Spitze zeigt,
    # waere das andere Extrem.
    assert selten > 0, (
        "die Einmal-Nennung kommt in 600 Fahrten kein einziges Mal dran — "
        "der Vorrang ist zu hart"
    )
