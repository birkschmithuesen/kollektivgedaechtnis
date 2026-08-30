import pytest

GRAPH = {
    "max_terms": 2,
    "nodes": [
        # Two persons: p1 the newer one and carrying a term, p2 older, hidden
        # and with nothing attached — the shape of the test portrait from the
        # morning's setup that Birk could not get off the wall (2026-08-30).
        {"id": "p1", "type": "person", "portrait": "/portraits/p1.jpg", "hidden": False, "created_at": 2},
        {"id": "p2", "type": "person", "portrait": "/portraits/p2.jpg", "hidden": True, "created_at": 1},
        {"id": "t1", "type": "term", "label": "Holzbau", "mentions": 2, "hidden": False, "created_at": 3},
        {"id": "t2", "type": "term", "label": "Unfug", "mentions": 1, "hidden": True, "created_at": 4},
        # Below the cap and NOT hidden: the wall is filtering it out, so the
        # list must not offer a hide button that would change nothing on screen.
        {"id": "t3", "type": "term", "label": "Aussenwand", "mentions": 1, "hidden": False, "created_at": 5},
        # Above the cap: the most-mentioned term, so it always wins a slot.
        {"id": "t4", "type": "term", "label": "Ziegel", "mentions": 3, "hidden": False, "created_at": 6},
    ],
    "edges": [{"id": "e1", "source": "p1", "target": "t1"}],
    "quotes": [{"id": "q1", "person_id": "p1", "text": "Wir bauen zu viel."}],
}
# max_terms=2: ranked by mentions then recency, only Ziegel (3) and Holzbau (2)
# make the cut. Aussenwand (1 mention) is below it; Unfug is hidden regardless.
STATE = {
    "max_terms": 2,
    "camera_mode": "pan",
    "camera_zoom": 2,
    "portrait_size": 150,
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
    labels = ui.eval_on_selector_all(".entry.term .label", "els => els.map(e => e.textContent)")
    # "Aussenwand" (1 mention, visible) is below the cap at max_terms=2 and is
    # therefore absent; the rest is A-Z, not newest-first.
    assert labels == ["Holzbau", "Unfug", "Ziegel"]
    # One button per row and nothing else on it — no approve, no edit.
    entries = ui.eval_on_selector_all(".entry", "els => els.length")
    assert ui.eval_on_selector_all(".entry button.hide", "els => els.length") == entries
    assert ui.eval_on_selector_all(".entry button", "els => els.length") == entries


def test_terms_below_the_cap_are_not_listed(ui):
    """The list offers an action only where the action is visible on the wall."""
    assert ui.eval_on_selector_all("#entry-t3", "els => els.length") == 0


def test_a_hidden_term_below_the_cap_still_offers_the_way_back(ui):
    """The exhibition's only undo must never disappear.

    `t2` is hidden AND sits below the cap (1 mention at max_terms=2).
    Filtering it out the way the wall does would strand it: hidden forever,
    with no row left to click "einblenden" on.
    """
    assert ui.eval_on_selector("#entry-t2 button.hide", "el => el.textContent") == "einblenden"


def test_lowering_the_cap_shortens_the_list(ui):
    ui.evaluate(
        "(args) => window.kgOperator.render(args[0], args[1])",
        [GRAPH, {**STATE, "max_terms": 1}],
    )
    labels = ui.eval_on_selector_all(".entry.term .label", "els => els.map(e => e.textContent)")
    # Only "Ziegel" (3 mentions) clears a cap of 1; "Unfug" stays because it is hidden.
    assert labels == ["Unfug", "Ziegel"]


def test_hidden_entries_are_marked_and_offer_unhide(ui):
    assert ui.eval_on_selector("#entry-t2", "el => el.classList.contains('hidden')") is True
    assert ui.eval_on_selector("#entry-t2 button.hide", "el => el.textContent") == "einblenden"


def test_persons_are_listed_and_show_their_portrait(ui):
    """Birk, 2026-08-30: a test portrait stayed on the wall with no way to get
    it off. The server took `person:<id>` all along; only the control was
    missing. A person carries no label, so the portrait IS the identification.
    """
    assert ui.eval_on_selector_all(".entry.person", "els => els.length") == 2
    assert (
        ui.eval_on_selector("#entry-p1 img.portrait", "el => el.getAttribute('src')")
        == "/portraits/p1.jpg"
    )
    assert ui.eval_on_selector("#entry-p1 button.hide", "el => el.textContent") == "ausblenden"


def test_a_person_row_says_when_it_was_recorded_and_what_it_carries(ui):
    """Two portraits of the same room look alike; the recording time and the
    number of terms behind them do not. "keine Begriffe" is what a portrait
    from the morning's setup looks like."""
    import re

    assert re.fullmatch(
        r"Person \d{2}:\d{2}", ui.eval_on_selector("#entry-p1 .label", "el => el.textContent")
    )
    assert ui.eval_on_selector("#entry-p1 .meta", "el => el.textContent") == "1 Begriff"
    assert ui.eval_on_selector("#entry-p2 .meta", "el => el.textContent") == "keine Begriffe"


def test_persons_come_first_newest_first(ui):
    """Persons head the list: they are few (one per interview), the term cap
    never touches them, and the reason to reach for this list is nearly always
    the portrait that just appeared."""
    order = ui.eval_on_selector_all(".entry", "els => els.map(e => e.id)")
    assert order[:2] == ["entry-p1", "entry-p2"]  # p1 recorded after p2
    assert all(entry.startswith("entry-t") for entry in order[2:])


def test_the_term_cap_never_hides_a_person_from_the_list(ui):
    """`max_terms` caps terms. Every person is on the wall always, so every
    person must stay reachable here — at any setting of the dial."""
    ui.evaluate(
        "(args) => window.kgOperator.render(args[0], args[1])",
        [GRAPH, {**STATE, "max_terms": 1}],
    )
    assert ui.eval_on_selector_all(".entry.person", "els => els.length") == 2


def test_a_hidden_person_stays_in_the_list_and_offers_the_way_back(ui):
    """Same reason as for a hidden term: the row IS the undo. Dropping it would
    make "ausblenden" a one-way door for a person."""
    assert ui.eval_on_selector("#entry-p2", "el => el.classList.contains('hidden')") is True
    assert ui.eval_on_selector("#entry-p2 button.hide", "el => el.textContent") == "einblenden"


def test_clicking_a_persons_button_posts_the_person_id(ui):
    ui.click("#entry-p1 button.hide")
    assert ui.evaluate("window.kgFetches[0]") == [
        "/api/hidden",
        {"node_id": "person:p1", "hidden": True},
    ]

    ui.click("#entry-p2 button.hide")
    assert ui.evaluate("window.kgFetches.at(-1)") == [
        "/api/hidden",
        {"node_id": "person:p2", "hidden": False},
    ]


def test_clicking_hide_posts_the_flag(ui):
    ui.click("#entry-t1 button.hide")
    assert ui.evaluate("window.kgFetches[0]") == ["/api/hidden", {"node_id": "term:t1", "hidden": True}]


def test_the_density_dial_reflects_state_and_posts_changes(ui):
    # A real option value this time (the markup's own steps),
    # independent of the small GRAPH fixture's own content above.
    ui.evaluate("(args) => window.kgOperator.render(args[0], args[1])", [GRAPH, {**STATE, "max_terms": 32}])
    assert ui.eval_on_selector("#max-terms", "el => el.value") == "32"
    ui.select_option("#max-terms", "45")
    assert ui.evaluate("window.kgFetches.at(-1)") == ["/api/max_terms", {"value": 45}]


def test_the_density_dial_reaches_past_45_without_jumping_to_all(ui):
    """Birk at the real graph, 2026-08-30: „45 reicht mir nicht, aber immer
    alle geht auch nicht."

    The steps are a proposal that gets set on site (operator.html's own
    comment), and the gap between 45 and „alle" was the whole upper half of a
    full day: a 60-person graph carries 131 terms, so anyone wanting more than
    45 had to jump straight to everything. Guarded as a PROPERTY — that
    intermediate steps exist above 45 and below „alle" — rather than as a list
    of numbers, so tuning them on site does not break the test.
    """
    steps = ui.eval_on_selector_all(
        "#max-terms option", "els => els.map(el => Number(el.value))"
    )
    dazwischen = [s for s in steps if 45 < s < 999]
    assert len(dazwischen) >= 3, f"keine Zwischenstufen über 45: {steps}"
    assert max(dazwischen) >= 110, "die Obergrenze bleibt unter einem vollen Tag"

    ui.evaluate("(args) => window.kgOperator.render(args[0], args[1])", [GRAPH, STATE])
    ui.select_option("#max-terms", str(dazwischen[0]))
    assert ui.evaluate("window.kgFetches.at(-1)") == [
        "/api/max_terms",
        {"value": dazwischen[0]},
    ]


def _term_node(i, created_at, mentions=1, hidden=False):
    return {
        "id": f"c{i}",
        "type": "term",
        "label": f"Begriff {i:03d}",
        "mentions": mentions,
        "hidden": hidden,
        "created_at": created_at,
    }


def _counts_graph(term_count):
    return {
        "max_terms": 32,
        "nodes": [_term_node(i, created_at=i) for i in range(term_count)],
        "edges": [],
        "quotes": [],
    }


def _density_options(ui):
    return ui.eval_on_selector_all("#max-terms option", "els => els.map(e => e.textContent)")


def test_each_density_step_says_how_many_terms_it_would_leave_on_the_wall(ui):
    """Moved here from the touchscreen on 2026-08-26, with the dial itself.

    The number exists because of a concrete incident: eight interviews in,
    somebody raised the density, got a blank wall and concluded the control
    was broken. It was not — nothing had been said by three people yet. The
    count turns a dead-looking step into an honest statement about the graph,
    and that has to survive the move to the operator laptop.

    25 unhidden terms: below every step but "20", so "20" alone differs from
    the rest — the case worth pinning is that a cap the graph has not grown
    into yet reports the graph's REAL size, not the cap number itself.
    """
    ui.evaluate(
        "(args) => window.kgOperator.render(args[0], args[1])", [_counts_graph(25), {**STATE, "max_terms": 32}]
    )
    assert _density_options(ui) == [
        "20 (20)", "32 (25)", "45 (25)", "60 (25)", "80 (25)",
        "110 (25)", "150 (25)", "alle (25)",
    ]


def test_the_counts_follow_every_graph_push(ui):
    """A step that reads the same as a smaller one now may differ a minute later."""
    ui.evaluate(
        "(args) => window.kgOperator.render(args[0], args[1])", [_counts_graph(25), {**STATE, "max_terms": 32}]
    )
    ui.evaluate(
        "(args) => window.kgOperator.render(args[0], args[1])", [_counts_graph(26), {**STATE, "max_terms": 32}]
    )
    assert _density_options(ui) == [
        "20 (20)", "32 (26)", "45 (26)", "60 (26)", "80 (26)",
        "110 (26)", "150 (26)", "alle (26)",
    ]


def test_early_steps_honestly_report_the_graph_the_wall_has_not_grown_into_yet(ui):
    """The step stays selectable — the graph may grow into it — but it never
    lies about what is behind it. Every step reading the same small number
    is correct, not broken, and none of them may be disabled for it."""
    ui.evaluate(
        "(args) => window.kgOperator.render(args[0], args[1])", [_counts_graph(5), {**STATE, "max_terms": 32}]
    )
    assert _density_options(ui) == [
        "20 (5)", "32 (5)", "45 (5)", "60 (5)", "80 (5)",
        "110 (5)", "150 (5)", "alle (5)",
    ]
    assert ui.eval_on_selector_all("#max-terms option[disabled]", "els => els.length") == 0


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


def test_the_portrait_slider_reflects_state_and_posts_on_release(ui):
    """The control for Birk's 2026-08-29 finding: with one person on the wall
    the portrait filled the screen. Since 2026-08-30 it sets an UPPER BOUND in
    rendered pixels for the automatic modes, which the read-out has to say —
    an operator who reads it as "so groß sind die Porträts" would go looking
    for a fault on the busy wall where it does nothing."""
    assert ui.eval_on_selector("#portrait-size", "el => el.value") == "150"
    assert (
        ui.eval_on_selector("#portrait-size-value", "el => el.textContent")
        == "höchstens 150 px"
    )

    before = ui.evaluate("window.kgFetches.length")
    ui.evaluate(
        """() => {
             const el = document.getElementById('portrait-size');
             el.value = '90';
             el.dispatchEvent(new Event('input', { bubbles: true }));
           }"""
    )
    # Dragging only moves the read-out: a POST per pixel would push a state
    # broadcast to every SSE client dozens of times per second.
    assert (
        ui.eval_on_selector("#portrait-size-value", "el => el.textContent")
        == "höchstens 90 px"
    )
    assert ui.evaluate("window.kgFetches.length") == before

    ui.evaluate(
        """() => {
             document
               .getElementById('portrait-size')
               .dispatchEvent(new Event('change', { bubbles: true }));
           }"""
    )
    assert ui.evaluate("window.kgFetches.at(-1)") == ["/api/portrait_size", {"pixels": 90}]


def test_the_portrait_slider_cannot_post_a_value_the_server_would_reject(ui):
    """Range mirrors PortraitSize's own bound (ge=40.0, le=260.0)."""
    assert ui.eval_on_selector("#portrait-size", "el => [el.min, el.max, el.type]") == [
        "40",
        "260",
        "range",
    ]


def test_the_portrait_size_is_independent_of_the_zoom_control(ui):
    """Two different things (Birk's brief): the zoom picks the section of the
    net on the wall, the portrait size how big the faces in it are drawn. A
    state push that changes one must leave the other's control alone."""
    ui.evaluate(
        "(args) => window.kgOperator.render(args[0], args[1])",
        [GRAPH, {**STATE, "camera_zoom": 3.5}],
    )

    assert ui.eval_on_selector("#camera-zoom", "el => el.value") == "3.5"
    assert ui.eval_on_selector("#portrait-size", "el => el.value") == "150"


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
    ui.evaluate("(args) => window.kgOperator.render(args[0], args[1])", [GRAPH, {**STATE, "max_terms": 32}])
    warnings = []
    ui.on("console", lambda msg: warnings.append(msg.text) if msg.type == "warning" else None)
    ui.evaluate("window.fetch = () => Promise.reject(new Error('network down')); void 0;")

    ui.select_option("#max-terms", "45")
    assert ui.eval_on_selector("#max-terms", "el => el.value") == "32"

    ui.select_option("#camera", "fit")
    assert ui.eval_on_selector("#camera", "el => el.value") == "pan"

    assert any("api/max_terms" in w for w in warnings)
    assert any("api/camera" in w for w in warnings)

    # The page keeps working afterwards: a subsequent request still fires normally.
    ui.evaluate(
        "window.fetch = (url, opts) => { window.kgFetches.push([url, JSON.parse(opts.body)]);"
        " return Promise.resolve({ok: true, json: () => Promise.resolve({})}); }; void 0;"
    )
    ui.click("#entry-t1 button.hide")
    assert ui.evaluate("window.kgFetches[0]") == ["/api/hidden", {"node_id": "term:t1", "hidden": True}]


def test_a_non_ok_response_reverts_the_dial_and_camera_and_the_page_keeps_working(ui):
    ui.evaluate("(args) => window.kgOperator.render(args[0], args[1])", [GRAPH, {**STATE, "max_terms": 32}])
    warnings = []
    ui.on("console", lambda msg: warnings.append(msg.text) if msg.type == "warning" else None)
    ui.evaluate(
        "window.fetch = () => Promise.resolve({ok: false, status: 400, statusText: 'Bad Request',"
        " json: () => Promise.resolve({})}); void 0;"
    )

    ui.select_option("#max-terms", "45")
    assert ui.eval_on_selector("#max-terms", "el => el.value") == "32"

    ui.select_option("#camera", "fit")
    assert ui.eval_on_selector("#camera", "el => el.value") == "pan"

    assert any("api/max_terms" in w for w in warnings)
    assert any("api/camera" in w for w in warnings)

    # The page keeps working afterwards: the hide list still re-renders and a
    # subsequent request still fires normally. All four terms qualify at
    # max_terms=32 -- this test rendered with that cap so the select's value
    # would match a real option (see the render() call at the top).
    assert ui.eval_on_selector_all(".entry.term .label", "els => els.map(e => e.textContent)") == [
        "Aussenwand",
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
