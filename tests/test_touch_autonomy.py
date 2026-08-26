"""Surface A's local touch behaviour (Birk, 2026-08-26).

The load-bearing property under test is an isolation one: touching the
touchscreen must NOT change what surface C in the plenary room is doing.
`camera_mode` is global state pushed over SSE, so the only safe design is a
LOCAL override that never posts — and that is exactly what can silently
regress into "just POST the mode" during a later refactor.
"""

import pytest

HARNESS = """
window.calls = [];
window.timers = [];
window.fakeCamera = {
  _mode: 'pan',
  _zoom: 1,
  get mode() { return this._mode; },
  setMode(m) { this._mode = m; window.calls.push(['setMode', m]); },
  setZoomFactor(z) { this._zoom = z; window.calls.push(['setZoomFactor', z]); },
};
window.fakeView = { camera: window.fakeCamera };
window.fetchCalls = [];
window.fetch = (url, opts) => {
  window.fetchCalls.push([url, opts ? JSON.parse(opts.body) : null]);
  return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
};
// Controllable clock: the idle timeout is 30s and no test may sleep for it.
window.pendingTimer = null;
window.fakeSetTimer = (fn, ms) => { window.pendingTimer = { fn, ms }; return 1; };
window.fakeClearTimer = () => { window.pendingTimer = null; };
window.fireIdle = () => { const t = window.pendingTimer; window.pendingTimer = null; if (t) t.fn(); };
"""


@pytest.fixture()
def touch(page, static_server):
    page.goto(f"{static_server}/frontend/static/test-harness.html")
    page.evaluate(HARNESS)
    page.evaluate(
        """async () => {
             const { attachTouchAutonomy } = await import('./touch-autonomy.js');
             window.autonomy = attachTouchAutonomy(window.fakeView, {
               setTimer: window.fakeSetTimer,
               clearTimer: window.fakeClearTimer,
             });
           }"""
    )
    return page


def _touch_screen(page):
    page.evaluate("document.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}))")


def test_a_touch_switches_this_screen_to_manual(touch):
    assert touch.evaluate("window.fakeCamera.mode") == "pan"
    _touch_screen(touch)
    assert touch.evaluate("window.fakeCamera.mode") == "manual"
    assert touch.evaluate("window.autonomy.manual") is True


def test_a_touch_never_posts_to_the_server(touch):
    """The isolation property: surface C must not follow surface A into manual.

    camera_mode is global (docs/decisions/cr1-second-screen-player.md), so any
    POST here would change the mode in the plenary room too.
    """
    _touch_screen(touch)
    touch.evaluate("window.fireIdle()")
    assert touch.evaluate("window.fetchCalls") == []


def test_thirty_seconds_without_contact_returns_to_automatic(touch):
    _touch_screen(touch)
    assert touch.evaluate("window.pendingTimer.ms") == 30000
    touch.evaluate("window.fireIdle()")
    assert touch.evaluate("window.fakeCamera.mode") == "pan"
    assert touch.evaluate("window.autonomy.manual") is False


def test_each_new_touch_restarts_the_countdown(touch):
    """A visitor reading between gestures must not be interrupted."""
    _touch_screen(touch)
    first = touch.evaluate("window.pendingTimer")
    _touch_screen(touch)
    assert touch.evaluate("window.pendingTimer") is not None
    assert touch.evaluate("window.fakeCamera.mode") == "manual"
    assert first is not None


def test_the_operator_mode_is_restored_not_a_hardcoded_pan(touch):
    """If the operator moved the wall to 'fit', idle must land on 'fit'."""
    touch.evaluate("window.autonomy.setOperatorMode('fit')")
    _touch_screen(touch)
    assert touch.evaluate("window.fakeCamera.mode") == "manual"
    touch.evaluate("window.fireIdle()")
    assert touch.evaluate("window.fakeCamera.mode") == "fit"


def test_an_operator_push_during_a_gesture_does_not_yank_the_view(touch):
    """State broadcasts keep arriving while a visitor is panning."""
    _touch_screen(touch)
    touch.evaluate("window.autonomy.setOperatorMode('fit')")
    # Still under the visitor's hand.
    assert touch.evaluate("window.fakeCamera.mode") == "manual"
    touch.evaluate("window.fireIdle()")
    assert touch.evaluate("window.fakeCamera.mode") == "fit"


def test_release_now_is_the_way_back_for_the_overview_button(touch):
    _touch_screen(touch)
    touch.evaluate("window.autonomy.releaseNow()")
    assert touch.evaluate("window.fakeCamera.mode") == "pan"
    assert touch.evaluate("window.autonomy.manual") is False
    assert touch.evaluate("window.pendingTimer") is None


def test_pressing_a_visitor_control_is_not_treated_as_navigating(touch):
    """The bug of 2026-08-26: the buttons looked dead.

    They were not — "Übersicht" set the camera back to fit, and the very same
    pointerdown flipped it into manual again a moment later, so nothing on
    screen ever changed. A control press must leave the camera alone; only
    contact with the GRAPH means somebody is steering.
    """
    touch.evaluate(
        """() => {
             const bar = document.createElement('div');
             bar.className = 'touch-controls';
             const button = document.createElement('button');
             button.id = 'probe';
             bar.appendChild(button);
             document.body.appendChild(bar);
           }"""
    )
    touch.click("#probe")
    assert touch.evaluate("window.fakeCamera.mode") == "pan"
    assert touch.evaluate("window.autonomy.manual") is False


def test_touching_the_graph_still_counts_as_navigating(touch):
    """The counterpart — the exemption must not swallow real gestures."""
    _touch_screen(touch)
    assert touch.evaluate("window.fakeCamera.mode") == "manual"
