import pytest

GRAPH = {
    "min_mentions": 1,
    "nodes": [
        {"id": "p1", "type": "person", "portrait": "", "hidden": False, "created_at": 2},
        {"id": "t1", "type": "term", "label": "Holzbau", "mentions": 2, "hidden": False, "created_at": 3},
        {"id": "t2", "type": "term", "label": "Unfug", "mentions": 1, "hidden": True, "created_at": 4},
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


def test_entries_are_listed_newest_first_with_one_hide_button_each(ui):
    labels = ui.eval_on_selector_all(".entry .label", "els => els.map(e => e.textContent)")
    assert labels == ["Unfug", "Holzbau"]
    assert ui.eval_on_selector_all(".entry button.hide", "els => els.length") == 2
    assert ui.eval_on_selector_all(".entry button", "els => els.length") == 2  # no approve/edit


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


def test_the_camera_switch_reflects_state_and_posts_changes(ui):
    assert ui.eval_on_selector("#camera", "el => el.value") == "pan"
    ui.select_option("#camera", "fit")
    assert ui.evaluate("window.kgFetches.at(-1)") == ["/api/camera", {"mode": "fit"}]


def test_the_zoom_select_reflects_state_and_posts_changes(ui):
    """21b: without this control an operator with no touchscreen reach cannot
    zoom at all — Camera.setZoomFactor is otherwise constructor-only."""
    assert ui.eval_on_selector("#camera-zoom", "el => el.value") == "2"
    ui.select_option("#camera-zoom", "1.5")
    assert ui.evaluate("window.kgFetches.at(-1)") == ["/api/camera_zoom", {"factor": 1.5}]


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
        "Unfug",
        "Holzbau",
    ]
    ui.evaluate(
        "window.fetch = (url, opts) => { window.kgFetches.push([url, JSON.parse(opts.body)]);"
        " return Promise.resolve({ok: true, json: () => Promise.resolve({})}); }; void 0;"
    )
    ui.click("#entry-t1 button.hide")
    assert ui.evaluate("window.kgFetches[0]") == ["/api/hidden", {"node_id": "term:t1", "hidden": True}]
