import pytest

GRAPH = {
    "min_mentions": 1,
    "nodes": [
        {"id": "p1", "type": "person", "portrait": "", "hidden": False, "created_at": 2},
        {"id": "t1", "type": "term", "label": "Holzbau", "mentions": 2, "hidden": False, "created_at": 3},
        {"id": "t2", "type": "term", "label": "Unfug", "mentions": 1, "hidden": True, "created_at": 4},
        # Below the dial and NOT hidden: the wall is filtering it out, so the
        # list must not offer a hide button that would change nothing on screen.
        {"id": "t3", "type": "term", "label": "Aussenwand", "mentions": 1, "hidden": False, "created_at": 5},
        # Above the dial, sorts before "Holzbau" only under alphabetical order —
        # newest-first would put it last, so this pins the sort direction.
        {"id": "t4", "type": "term", "label": "Ziegel", "mentions": 3, "hidden": False, "created_at": 6},
    ],
    "edges": [],
    "quotes": [{"id": "q1", "person_id": "p1", "text": "Wir bauen zu viel."}],
}
STATE = {
    "min_mentions": 2,
    "camera_mode": "pan",
    "camera_zoom": 2,
    "stt_connected": True,
    "interview": None,
}


@pytest.fixture()
def ui(page, static_server):
    page.goto(f"{static_server}/frontend/operator.html")
    page.wait_for_function("window.kgOperator !== undefined")
    page.evaluate("window.kgFetches = []")
    # The trailing `void 0;` is load-bearing, not stylistic: without it the
    # expression's completion value is the assigned function itself, and
    # Playwright's evaluate() calls that completion value with no arguments
    # while producing its own return value — a driver-level artifact
    # (reproduces on about:blank with any unrelated global name, nothing to
    # do with fetch or this app), which throws inside our mock on
    # `opts.body` before `render()` ever gets a chance to run.
    page.evaluate(
        "window.fetch = (url, opts) => { window.kgFetches.push([url, JSON.parse(opts.body)]);"
        " return Promise.resolve({ok: true, json: () => Promise.resolve({})}); }; void 0;"
    )
    page.evaluate("(args) => window.kgOperator.render(args[0], args[1])", [GRAPH, STATE])
    return page


def test_entries_are_listed_alphabetically_with_one_hide_button_each(ui):
    labels = ui.eval_on_selector_all(".entry .label", "els => els.map(e => e.textContent)")
    # "Aussenwand" (1 mention, visible) is below the dial at min_mentions=2 and
    # is therefore absent; the rest is A-Z, not newest-first.
    assert labels == ["Holzbau", "Unfug", "Ziegel"]
    assert ui.eval_on_selector_all(".entry button.hide", "els => els.length") == 3
    assert ui.eval_on_selector_all(".entry button", "els => els.length") == 3  # no approve/edit


def test_terms_below_the_dial_are_not_listed(ui):
    """The list offers an action only where the action is visible on the wall."""
    assert ui.eval_on_selector_all("#entry-t3", "els => els.length") == 0


def test_a_hidden_term_below_the_dial_still_offers_the_way_back(ui):
    """The exhibition's only undo must never disappear.

    `t2` is hidden AND sits below the dial (1 mention at min_mentions=2).
    Filtering it out the way the wall does would strand it: hidden forever,
    with no row left to click "einblenden" on.
    """
    assert ui.eval_on_selector("#entry-t2 button.hide", "el => el.textContent") == "einblenden"


def test_raising_the_dial_shortens_the_list(ui):
    ui.evaluate(
        "(args) => window.kgOperator.render(args[0], args[1])",
        [GRAPH, {**STATE, "min_mentions": 3}],
    )
    labels = ui.eval_on_selector_all(".entry .label", "els => els.map(e => e.textContent)")
    # Only "Ziegel" (3) clears the dial; "Unfug" stays because it is hidden.
    assert labels == ["Unfug", "Ziegel"]


def test_hidden_entries_are_marked_and_offer_unhide(ui):
    assert ui.eval_on_selector("#entry-t2", "el => el.classList.contains('hidden')") is True
    assert ui.eval_on_selector("#entry-t2 button.hide", "el => el.textContent") == "einblenden"


def test_clicking_hide_posts_the_flag(ui):
    ui.click("#entry-t1 button.hide")
    assert ui.evaluate("window.kgFetches[0]") == ["/api/hidden", {"node_id": "term:t1", "hidden": True}]


def test_the_density_dial_reflects_state_and_posts_changes(ui):
    assert ui.eval_on_selector("#min-mentions", "el => el.value") == "2"
    ui.select_option("#min-mentions", "3")
    assert ui.evaluate("window.kgFetches.at(-1)") == ["/api/min_mentions", {"value": 3}]


def _density_options(ui):
    return ui.eval_on_selector_all("#min-mentions option", "els => els.map(e => e.textContent)")


def test_each_density_step_says_how_many_terms_it_would_leave_on_the_wall(ui):
    """Moved here from the touchscreen on 2026-08-26, with the dial itself.

    The number exists because of a concrete incident: eight interviews in,
    somebody raised the density, got a blank wall and concluded the control
    was broken. It was not — nothing had been said by three people yet. The
    count turns a dead-looking step into an honest statement about the graph,
    and that has to survive the move to the operator laptop.

    Counted the way the wall counts: hidden terms are not on it, so `Unfug`
    (hidden, 1 mention) is in no step. `Aussenwand` (1), `Holzbau` (2) and
    `Ziegel` (3) are.
    """
    assert _density_options(ui) == ["1 — alles (3)", "2 — geteilt (2)", "3 — nur häufig (1)"]


def test_the_counts_follow_every_graph_push(ui):
    """A step that is empty now may have something behind it a minute later."""
    grown = {
        **GRAPH,
        "nodes": GRAPH["nodes"]
        + [{"id": "t5", "type": "term", "label": "Dämmung", "mentions": 3, "hidden": False, "created_at": 7}],
    }
    ui.evaluate("(args) => window.kgOperator.render(args[0], args[1])", [grown, STATE])
    assert _density_options(ui) == ["1 — alles (4)", "2 — geteilt (3)", "3 — nur häufig (2)"]


def test_a_step_that_would_empty_the_wall_says_so_before_it_is_chosen(ui):
    """The blank-wall case itself: the step stays selectable — the graph may
    grow into it — but it no longer lies about what is behind it."""
    early = {**GRAPH, "nodes": [n for n in GRAPH["nodes"] if n["id"] != "t4"]}
    ui.evaluate("(args) => window.kgOperator.render(args[0], args[1])", [early, STATE])
    assert _density_options(ui) == ["1 — alles (2)", "2 — geteilt (1)", "3 — nur häufig (0)"]
    assert ui.eval_on_selector_all("#min-mentions option[disabled]", "els => els.length") == 0


def test_the_camera_switch_reflects_state_and_posts_changes(ui):
    assert ui.eval_on_selector("#camera", "el => el.value") == "pan"
    ui.select_option("#camera", "fit")
    assert ui.evaluate("window.kgFetches.at(-1)") == ["/api/camera", {"mode": "fit"}]


def test_the_zoom_slider_reflects_state_and_posts_on_release(ui):
    """21b: without this control an operator with no touchscreen reach cannot
    zoom at all — Camera.setZoomFactor is otherwise constructor-only.

    Continuous since 2026-08-26: the on-site question is "far enough in that
    the labels read on THIS wall", which does not land on a preset.
    """
    assert ui.eval_on_selector("#camera-zoom", "el => el.value") == "2"
    assert ui.eval_on_selector("#camera-zoom-value", "el => el.textContent") == "2,00×"

    # A value strictly between the old presets — the whole point of the change.
    ui.evaluate(
        """() => {
             const el = document.getElementById('camera-zoom');
             el.value = '1.65';
             el.dispatchEvent(new Event('change', { bubbles: true }));
           }"""
    )
    assert ui.evaluate("window.kgFetches.at(-1)") == ["/api/camera_zoom", {"factor": 1.65}]


def test_dragging_the_zoom_slider_updates_the_readout_without_posting(ui):
    """A POST per pixel would broadcast state to every SSE client mid-drag."""
    before = ui.evaluate("window.kgFetches.length")
    ui.evaluate(
        """() => {
             const el = document.getElementById('camera-zoom');
             el.value = '3.4';
             el.dispatchEvent(new Event('input', { bubbles: true }));
           }"""
    )
    assert ui.eval_on_selector("#camera-zoom-value", "el => el.textContent") == "3,40×"
    assert ui.evaluate("window.kgFetches.length") == before


def test_the_slider_cannot_post_a_value_the_server_would_reject(ui):
    """Range/step mirror CameraZoom's own bound (ge=1.0, le=4.0)."""
    bounds = ui.eval_on_selector(
        "#camera-zoom", "el => [el.min, el.max, el.type]"
    )
    assert bounds == ["1", "4", "range"]


def test_the_bottom_stop_warns_that_roaming_has_no_effect_there(ui):
    """1,00× frames the whole net, so the tour has nowhere to travel.

    Reported 2026-08-26 as "the automatic camera doesn't start" — it did, but
    with every node already on screen nothing appeared to move. The control
    has to say so; the operator cannot be expected to derive it.
    """
    ui.evaluate(
        """() => {
             const el = document.getElementById('camera-zoom');
             el.value = '1';
             el.dispatchEvent(new Event('input', { bubbles: true }));
           }"""
    )
    text = ui.eval_on_selector("#camera-zoom-value", "el => el.textContent")
    assert text.startswith("1,00×")
    assert "ohne Wirkung" in text


def test_a_zoomed_in_value_carries_no_warning(ui):
    ui.evaluate(
        """() => {
             const el = document.getElementById('camera-zoom');
             el.value = '1.6';
             el.dispatchEvent(new Event('input', { bubbles: true }));
           }"""
    )
    assert ui.eval_on_selector("#camera-zoom-value", "el => el.textContent") == "1,60×"


def test_the_speed_slider_only_goes_down_from_the_tuned_pace(ui):
    """Right stop = the speed the motion was judged at; nothing runs faster."""
    assert ui.eval_on_selector("#camera-speed", "el => [el.min, el.max, el.type]") == [
        "0.25",
        "1",
        "range",
    ]


def test_the_speed_reads_as_a_fraction_not_a_decimal(ui):
    """"Half as fast" is the decision; 0.5 makes the operator do arithmetic."""
    for value, shown in (("1", "1/1"), ("0.5", "1/2"), ("0.25", "1/4")):
        ui.evaluate(
            """(v) => {
                 const el = document.getElementById('camera-speed');
                 el.value = v;
                 el.dispatchEvent(new Event('input', { bubbles: true }));
               }""",
            value,
        )
        assert ui.eval_on_selector("#camera-speed-value", "el => el.textContent") == shown


def test_dragging_the_speed_slider_posts_only_on_release(ui):
    before = ui.evaluate("window.kgFetches.length")
    ui.evaluate(
        """() => {
             const el = document.getElementById('camera-speed');
             el.value = '0.4';
             el.dispatchEvent(new Event('input', { bubbles: true }));
           }"""
    )
    assert ui.evaluate("window.kgFetches.length") == before
    ui.evaluate(
        """() => {
             const el = document.getElementById('camera-speed');
             el.dispatchEvent(new Event('change', { bubbles: true }));
           }"""
    )
    assert ui.evaluate("window.kgFetches.at(-1)") == ["/api/camera_speed", {"factor": 0.4}]


def test_the_transcript_area_shows_partials(ui):
    ui.evaluate("window.kgOperator.showTranscript('wir bauen zu viel neu')")
    assert ui.eval_on_selector("#transcript", "el => el.textContent") == "wir bauen zu viel neu"


def test_stt_connection_state_is_visible(ui):
    assert ui.eval_on_selector("#stt", "el => el.classList.contains('ok')") is True
    ui.evaluate(
        "(args) => window.kgOperator.render(args[0], args[1])",
        [GRAPH, {**STATE, "stt_connected": False}],
    )
    assert ui.eval_on_selector("#stt", "el => el.classList.contains('ok')") is False


def test_a_rejected_fetch_reverts_the_dial_and_camera_and_the_page_keeps_working(ui):
    warnings = []
    ui.on("console", lambda msg: warnings.append(msg.text) if msg.type == "warning" else None)
    ui.evaluate("window.fetch = () => Promise.reject(new Error('network down')); void 0;")

    ui.select_option("#min-mentions", "3")
    assert ui.eval_on_selector("#min-mentions", "el => el.value") == "2"

    ui.select_option("#camera", "fit")
    assert ui.eval_on_selector("#camera", "el => el.value") == "pan"

    assert any("api/min_mentions" in w for w in warnings)
    assert any("api/camera" in w for w in warnings)

    # The page keeps working afterwards: a subsequent request still fires normally.
    ui.evaluate(
        "window.fetch = (url, opts) => { window.kgFetches.push([url, JSON.parse(opts.body)]);"
        " return Promise.resolve({ok: true, json: () => Promise.resolve({})}); }; void 0;"
    )
    ui.click("#entry-t1 button.hide")
    assert ui.evaluate("window.kgFetches[0]") == ["/api/hidden", {"node_id": "term:t1", "hidden": True}]


def test_a_non_ok_response_reverts_the_dial_and_camera_and_the_page_keeps_working(ui):
    warnings = []
    ui.on("console", lambda msg: warnings.append(msg.text) if msg.type == "warning" else None)
    ui.evaluate(
        "window.fetch = () => Promise.resolve({ok: false, status: 400, statusText: 'Bad Request',"
        " json: () => Promise.resolve({})}); void 0;"
    )

    ui.select_option("#min-mentions", "3")
    assert ui.eval_on_selector("#min-mentions", "el => el.value") == "2"

    ui.select_option("#camera", "fit")
    assert ui.eval_on_selector("#camera", "el => el.value") == "pan"

    assert any("api/min_mentions" in w for w in warnings)
    assert any("api/camera" in w for w in warnings)

    # The page keeps working afterwards: the hide list still re-renders and a
    # subsequent request still fires normally.
    assert ui.eval_on_selector_all(".entry .label", "els => els.map(e => e.textContent)") == [
        "Holzbau",
        "Unfug",
        "Ziegel",
    ]
    ui.evaluate(
        "window.fetch = (url, opts) => { window.kgFetches.push([url, JSON.parse(opts.body)]);"
        " return Promise.resolve({ok: true, json: () => Promise.resolve({})}); }; void 0;"
    )
    ui.click("#entry-t1 button.hide")
    assert ui.evaluate("window.kgFetches[0]") == ["/api/hidden", {"node_id": "term:t1", "hidden": True}]
