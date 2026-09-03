import pytest

GRAPH = {
    "max_terms": 2,
    "nodes": [
        # Two persons: p1 the newer one and carrying a term, p2 older, hidden
        # and with nothing attached — the shape of the test portrait from the
        # morning's setup that Birk could not get off the wall (2026-08-30).
        {"id": "p1", "type": "person", "portrait": "/portraits/p1.jpg", "hidden": False,
         "created_at": 2, "name": "Frau Kirchner"},
        # Ohne Namen: niemand hat sich vorgestellt, oder der Operator hat den
        # verhörten Namen gelöscht. Die Zeile muss trotzdem identifizierbar bleiben.
        {"id": "p2", "type": "person", "portrait": "/portraits/p2.jpg", "hidden": True,
         "created_at": 1, "name": None},
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
    "camera_min_label": 52,
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
    from the morning's setup looks like.

    Die Uhrzeit-Kennung steht seit dem Namensfeld im `placeholder` statt im
    Text: Sie identifiziert weiterhin jede Zeile, die keinen Namen trägt.
    """
    import re

    assert re.fullmatch(
        r"Person \d{2}:\d{2}",
        ui.eval_on_selector("#entry-p2 .label", "el => el.placeholder"),
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


def test_the_min_label_slider_reflects_state_and_posts_on_release(ui):
    """21b: without this control an operator with no touchscreen reach cannot
    set the wall's framing at all — the camera is otherwise constructor-only.

    Continuous since 2026-08-26: the on-site question is "far enough in that
    the labels read on THIS wall", which does not land on a preset. Seit dem
    2026-09-02 stellt der Regler genau diese Frage direkt — als Größe in
    gezeichneten Pixeln statt als Vergrößerung.
    """
    assert ui.eval_on_selector("#camera-min-label", "el => el.value") == "52"
    assert (
        ui.eval_on_selector("#camera-min-label-value", "el => el.textContent")
        == "mindestens 52 px"
    )

    ui.evaluate(
        """() => {
             const el = document.getElementById('camera-min-label');
             el.value = '33';
             el.dispatchEvent(new Event('change', { bubbles: true }));
           }"""
    )
    assert ui.evaluate("window.kgFetches.at(-1)") == ["/api/camera_min_label", {"pixels": 33}]


def test_dragging_the_min_label_slider_updates_the_readout_without_posting(ui):
    """A POST per pixel would broadcast state to every SSE client mid-drag."""
    before = ui.evaluate("window.kgFetches.length")
    ui.evaluate(
        """() => {
             const el = document.getElementById('camera-min-label');
             el.value = '34';
             el.dispatchEvent(new Event('input', { bubbles: true }));
           }"""
    )
    assert (
        ui.eval_on_selector("#camera-min-label-value", "el => el.textContent")
        == "mindestens 34 px"
    )
    assert ui.evaluate("window.kgFetches.length") == before


def test_the_slider_cannot_post_a_value_the_server_would_reject(ui):
    """Range/step mirror CameraMinLabel's own bound (ge=8.0, le=120.0)."""
    bounds = ui.eval_on_selector("#camera-min-label", "el => [el.min, el.max, el.type]")
    assert bounds == ["8", "120", "range"]


def test_the_bottom_stop_warns_that_roaming_has_no_effect_there(ui):
    """Am unteren Anschlag steht das ganze Netz ohnehin lesbar im Bild.

    Dann fährt die Kamera nicht — sie hat nichts zu suchen, was nicht schon zu
    sehen wäre. Das ist seit dem 2026-09-02 gewollt, sieht aber aus wie eine
    kaputte Kamera, wenn niemand es sagt: genau die Rückmeldung vom
    2026-08-26 („die automatische Kamera startet nicht"). Der Regler sagt es
    deshalb selbst.
    """
    ui.evaluate(
        """() => {
             const el = document.getElementById('camera-min-label');
             el.value = '8';
             el.dispatchEvent(new Event('input', { bubbles: true }));
           }"""
    )
    text = ui.eval_on_selector("#camera-min-label-value", "el => el.textContent")
    assert text.startswith("mindestens 8 px")
    assert "ohne Fahrt" in text


def test_a_readable_value_carries_no_warning(ui):
    ui.evaluate(
        """() => {
             const el = document.getElementById('camera-min-label');
             el.value = '40';
             el.dispatchEvent(new Event('input', { bubbles: true }));
           }"""
    )
    assert (
        ui.eval_on_selector("#camera-min-label-value", "el => el.textContent")
        == "mindestens 40 px"
    )


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
    """Range mirrors PortraitSize's own bound (ge=40.0, le=700.0).

    🔴 Nachgezogen am 2026-09-01: Die Obergrenze ist an dem Tag von 260 auf 700
    angehoben worden (Server UND Markup, siehe `PortraitSize` in kg/server.py —
    die 260 waren an einer 1920 px breiten Wand beurteilt, die Foyerfläche ist
    inzwischen 3840 px breit). Dieser Test ist dabei stehen geblieben und war
    seither rot; er hat also genau die Drift beschrieben, gegen die er da ist,
    nur zeigte er in die falsche Richtung. Die gelebte Zahl ist 700.
    """
    assert ui.eval_on_selector("#portrait-size", "el => [el.min, el.max, el.type]") == [
        "40",
        "700",
        "range",
    ]


def test_the_portrait_size_is_independent_of_the_min_label_control(ui):
    """Two different things (Birk's brief): the min label size picks the
    section of the net on the wall, the portrait size how big the faces in it
    are drawn. A state push that changes one must leave the other's control
    alone."""
    ui.evaluate(
        "(args) => window.kgOperator.render(args[0], args[1])",
        [GRAPH, {**STATE, "camera_min_label": 64}],
    )

    assert ui.eval_on_selector("#camera-min-label", "el => el.value") == "64"
    assert ui.eval_on_selector("#portrait-size", "el => el.value") == "150"


def test_the_speed_slider_only_goes_down_from_the_tuned_pace(ui):
    """Right stop = the speed the motion was judged at; nothing runs faster.

    🔴 Nachgezogen am 2026-09-01, wie beim Regler darüber: Die Untergrenze ist
    an dem Tag zweimal gesenkt worden (0.25 → 0.1 → 0.05, `CameraSpeed` in
    kg/server.py), weil Birk vor Ort am Anschlag stand und meldete „der
    Tempo-Regler hat keinen Einfluss". Der Test blieb auf 0.25 stehen und war
    seither rot. Die Aussage, um die es ihm geht, bleibt unverändert: nach
    OBEN ist bei 1.0 Schluss.
    """
    assert ui.eval_on_selector("#camera-speed", "el => [el.min, el.max, el.type]") == [
        "0.05",
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


def _mit_namen(person_id, name):
    """Derselbe Graph, aber der Server meldet für eine Person einen anderen Namen."""
    return {
        **GRAPH,
        "nodes": [{**n, "name": name} if n["id"] == person_id else n for n in GRAPH["nodes"]],
    }


def test_a_person_row_carries_an_editable_name_field(ui):
    """Die Spracherkennung verhört Namen. Korrigiert wird dort, wo die Person
    ohnehin identifiziert wird: in ihrer Zeile, neben dem Porträt."""
    assert ui.eval_on_selector("#entry-p1 .label", "el => el.tagName") == "INPUT"
    assert ui.eval_on_selector("#entry-p1 .label", "el => el.value") == "Frau Kirchner"
    # Ohne Namen bleibt das Feld leer — kein Platzhaltertext im Wert, den der
    # Operator erst löschen müsste, bevor er den richtigen Namen tippen kann.
    assert ui.eval_on_selector("#entry-p2 .label", "el => el.value") == ""
    # Begriffe bleiben unverändert Text: nur Personen tragen einen Namen.
    assert ui.eval_on_selector("#entry-t1 .label", "el => el.tagName") == "SPAN"
    assert ui.eval_on_selector_all(".entry.person input.label", "els => els.length") == 2


def test_typing_a_name_posts_nothing_until_the_field_is_left(ui):
    """Wie bei den Reglern: `input` feuert pro Tastendruck, und jede
    Speicherung schickt eine Graph-Rundmeldung an jeden SSE-Client — die Wand
    bekäme pro Buchstabe einen vollständigen Graphen zugestellt."""
    before = ui.evaluate("window.kgFetches.length")
    ui.click("#entry-p2 .label")
    ui.keyboard.type("Anna Weber")
    assert ui.evaluate("window.kgFetches.length") == before

    ui.click("#transcript")  # Feld verlassen
    assert ui.evaluate("window.kgFetches.at(-1)") == [
        "/api/person_name",
        {"person_id": "p2", "name": "Anna Weber"},
    ]


def test_enter_saves_the_name_exactly_once(ui):
    """Enter heißt „fertig". Umgesetzt als Fokusabgabe, damit der Browser genau
    ein `change` feuert — selbst zu posten hieße bei anschließendem Verlassen
    des Feldes zweimal speichern."""
    ui.click("#entry-p2 .label")
    ui.keyboard.type("Anna Weber")
    before = ui.evaluate("window.kgFetches.length")

    ui.keyboard.press("Enter")

    assert ui.evaluate("window.kgFetches.length") == before + 1
    assert ui.evaluate("window.kgFetches.at(-1)") == [
        "/api/person_name",
        {"person_id": "p2", "name": "Anna Weber"},
    ]
    assert ui.evaluate("document.activeElement.dataset.nameFor") is None


def test_clearing_a_misheard_name_posts_the_empty_value(ui):
    """Das Feld zu leeren ist die Aussage „hier steht kein Name" — kein
    Nichtstun, sondern eine Speicherung, die der Server als NULL ablegt."""
    ui.click("#entry-p1 .label")
    # `ControlOrMeta` und nicht `Control`: Auf macOS ist Strg+A „an den
    # Zeilenanfang" (die alte Emacs-Belegung) und markiert gar nichts -- der
    # Test loeschte dort genau ein Zeichen und wurde rot, ohne dass an der
    # Oberflaeche etwas fehlte. Playwright waehlt mit `ControlOrMeta` je
    # Plattform Strg bzw. Cmd.
    ui.keyboard.press("ControlOrMeta+a")
    ui.keyboard.press("Delete")
    ui.keyboard.press("Enter")

    assert ui.evaluate("window.kgFetches.at(-1)") == [
        "/api/person_name",
        {"person_id": "p1", "name": ""},
    ]


def test_a_graph_push_while_typing_keeps_the_draft_and_the_cursor(ui):
    """Der Fallstrick dieser Liste: Sie wird bei JEDEM Push komplett neu gebaut.

    Am Bedienpult laufen Interviews im Minutentakt ein, und jedes davon löst
    einen Push aus. Ein halb getippter Name darf davon weder überschrieben noch
    aus dem Fokus geschoben werden — sonst tippt der Operator ins Leere weiter
    und merkt es erst am Ergebnis.
    """
    ui.click("#entry-p2 .label")
    ui.keyboard.type("Anna")

    # Der Server meldet währenddessen einen anderen Namen für genau diese Person.
    ui.evaluate(
        "(args) => window.kgOperator.render(args[0], args[1])",
        [_mit_namen("p2", "Frau Nau"), STATE],
    )

    assert ui.eval_on_selector("#entry-p2 .label", "el => el.value") == "Anna"
    assert ui.evaluate("document.activeElement.dataset.nameFor") == "p2"
    assert ui.evaluate("document.activeElement.selectionStart") == 4
    # Und das Tippen geht am Cursor weiter, nicht am Anfang.
    ui.keyboard.type("s")
    assert ui.eval_on_selector("#entry-p2 .label", "el => el.value") == "Annas"


def test_a_push_leaves_every_other_name_field_alone(ui):
    """Geschützt wird der Entwurf, nicht die Liste: Jede andere Zeile zeigt
    weiter das, was der Server sagt."""
    ui.click("#entry-p2 .label")
    ui.keyboard.type("Anna")

    ui.evaluate(
        "(args) => window.kgOperator.render(args[0], args[1])",
        [_mit_namen("p1", "Frau Kirchnauer"), STATE],
    )

    assert ui.eval_on_selector("#entry-p1 .label", "el => el.value") == "Frau Kirchnauer"
    assert ui.eval_on_selector("#entry-p2 .label", "el => el.value") == "Anna"


def test_once_the_field_is_left_the_server_text_wins_again(ui):
    """Nach dem Verlassen ist gespeichert — dann muss die Zeile wieder zeigen,
    was wirklich in der Datenbank steht, und nicht den letzten Entwurf."""
    ui.click("#entry-p1 .label")
    ui.click("#transcript")

    ui.evaluate(
        "(args) => window.kgOperator.render(args[0], args[1])",
        [_mit_namen("p1", "Frau Kirchnauer"), STATE],
    )

    assert ui.eval_on_selector("#entry-p1 .label", "el => el.value") == "Frau Kirchnauer"


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


# --- Der Interviewschalter am Bedienpult -----------------------------------
#
# Birk, 2026-09-01: „Als Backup sollte allerdings auch noch ein Button in einem
# Operator UI sein fuer Interview-Stop, falls die Interviewperson das vergisst."
# Birk, 2026-09-02: „Was mir noch fehlte, ist der Start-Stopp-Button im
# Operator-Panel, analog zur APK-App."
#
# Den Schalter am Mikrofon bedient eine eingewiesene Interviewperson, nicht der
# Gast. Er bleibt der verlaessliche Weg; dieses Paar ist das Netz darunter --
# und seit dem 2026-09-02 auch der Weg, ein Interview zu EROEFFNEN, wenn am
# Mikrofon niemand daran denkt.
#
# 🔴 ZWEI KNOEPFE UND KEIN UMSCHALTER. Der Knopf der App ist einer
# (`neuerZustand = !laeuft`), und seine Wirkung haengt damit an einem
# Anzeigestand, der schieflaufen kann. In der Nacht zum 2026-09-02 lief er
# schief: Um 01:14:51 schickte ein Druck auf „Start" in Wahrheit „Stopp", das
# offene Interview war zu, und das vierte Foto lief in ein 409.
#
# Hier sendet jeder Knopf einen FESTEN absoluten Wert. Der schlimmste Ausgang
# eines Drucks bei falschem Anzeigestand ist damit ein Nichts
# (`SessionTracker.mic_switch` ist idempotent) -- nie die Gegenaktion.

LAEUFT = {**STATE, "interview": {"person_id": "p1", "started_at": 100}}
# Ein Zustand, in dem der Server ueber das Interview noch NICHTS gesagt hat.
# Genau so sieht das Bedienpult in den Millisekunden zwischen Laden und erster
# SSE-Meldung aus -- und `interview: None` waere dafuer die falsche Auskunft:
# „kein Interview" ist eine Behauptung, „ich weiss es noch nicht" ist die
# Wahrheit.
UNBEKANNT = {schluessel: wert for schluessel, wert in STATE.items() if schluessel != "interview"}

FETCH_SCHEITERT = (
    "window.fetch = (url, opts) => { window.kgFetches.push([url, JSON.parse(opts.body)]);"
    " return Promise.resolve({ok: false, status: 503, statusText: 'Service Unavailable'}); }; void 0;"
)


def _gesperrt(ui, knopf):
    return ui.eval_on_selector(f"#interview-{knopf}", "el => el.disabled")


def test_jeder_interviewknopf_sendet_einen_festen_absoluten_wert(ui):
    """🔴 Der Kern der Absicherung gegen den Vorfall um 01:14:51.

    „Interview starten" sendet immer `on: true`, „Interview beenden" immer
    `on: false` -- unabhaengig davon, was das Bedienpult gerade zu wissen
    glaubt. Ein Umschalter kann bei falschem Anzeigestand das Gegenteil des
    Gewollten tun; diese beiden koennen hoechstens wirkungslos sein.
    """
    ui.click("#interview-start")  # STATE oben: kein Interview
    assert ui.evaluate("window.kgFetches.at(-1)") == ["/api/interview_switch", {"on": True}]

    ui.evaluate("(args) => window.kgOperator.render(args[0], args[1])", [GRAPH, LAEUFT])
    # Ohne Nachlauf, sonst pruefte dieser Test die Wartezeit statt den Wert.
    # Dass es den Nachlauf gibt, belegen die Tests weiter unten.
    ui.evaluate("() => { window.kgOperator.stopNachlaufMs = 0; }")
    ui.click("#interview-stop")
    assert ui.evaluate("window.kgFetches.at(-1)") == ["/api/interview_switch", {"on": False}]


def test_immer_nur_der_passende_interviewknopf_ist_bedienbar(ui):
    """Was gerade gilt, steht am Knopf selbst -- nicht nur im Text daneben.

    Gesperrt statt versteckt: Ein Knopf, der kommt und geht, laesst das
    Bedienpult im Leerlauf so aussehen, als gaebe es diesen Weg gar nicht --
    und genau den sucht jemand, der ihn eilig braucht. Der graue Knopf sagt
    stattdessen zugleich, dass es ihn gibt und dass er jetzt nicht dran ist.
    Ausprobieren kann man ihn trotzdem nicht, was der urspruengliche Grund
    fuers Verstecken war (2026-09-01).
    """
    assert ui.eval_on_selector("#interview", "el => el.textContent") == "kein Interview"
    assert _gesperrt(ui, "start") is False
    assert _gesperrt(ui, "stop") is True

    ui.evaluate("(args) => window.kgOperator.render(args[0], args[1])", [GRAPH, LAEUFT])
    assert ui.eval_on_selector("#interview", "el => el.textContent") == "Interview läuft"
    assert _gesperrt(ui, "start") is True
    assert _gesperrt(ui, "stop") is False


def test_solange_der_zustand_unbekannt_ist_sind_beide_knoepfe_gesperrt(ui):
    """Kein Raten, solange der Server nichts gesagt hat.

    „Kein Interview" anzunehmen waere die gefaehrliche Annahme: Sie stellt den
    Startknopf scharf, waehrend im Raum vielleicht laengst jemand spricht.
    """
    ui.evaluate("(args) => window.kgOperator.render(args[0], args[1])", [GRAPH, UNBEKANNT])
    assert ui.eval_on_selector("#interview", "el => el.textContent") == "Zustand unbekannt"
    assert _gesperrt(ui, "start") is True
    assert _gesperrt(ui, "stop") is True


def test_beim_laden_der_seite_ist_der_schalter_gesperrt(page, static_server):
    """Dieselbe Sperre schon im Markup, vor der ersten Zeile JavaScript.

    Zwischen Aufschlagen der Seite und der ersten SSE-Meldung liegt ein
    Moment, in dem noch kein `render()` gelaufen ist. Stuenden die Knoepfe
    dort offen, waere ausgerechnet der erste Griff der ungesicherte.
    """
    page.goto(f"{static_server}/frontend/operator.html")
    page.wait_for_function("window.kgOperator !== undefined")
    assert page.eval_on_selector("#interview-start", "el => el.disabled") is True
    assert page.eval_on_selector("#interview-stop", "el => el.disabled") is True
    assert page.eval_on_selector("#interview", "el => el.textContent") == "Zustand unbekannt"


def test_der_neue_zustand_gilt_sofort_nach_dem_druck(ui):
    """🔴 Die Lehre aus der App (`MainActivity.schalteInterview`).

    „Bis zu drei Sekunden Verzoegerung nach einem Druck fuehlen sich nach
    einem nicht angekommenen Knopf an, und dann drueckt man noch einmal."

    Hier ist die Verzoegerung eine andere und der Schluss derselbe: Der Server
    legt den Wechsel nur in die Warteschlange (`Core.on_mic_switch`), geoeffnet
    wird er im Worker, und erst dann kommt die Zustandsmeldung. Bis dahin
    zeigt das Bedienpult, was es gerade veranlasst hat -- ohne dass eine
    einzige weitere Meldung vom Server noetig waere.
    """
    ui.click("#interview-start")
    ui.wait_for_function("document.getElementById('interview-stop').disabled === false")
    assert ui.eval_on_selector("#interview", "el => el.textContent") == "Interview läuft"
    assert _gesperrt(ui, "start") is True


def test_erfolg_und_fehler_werden_gemeldet(ui):
    """Rueckmeldung wie in der App: ein Satz, der sagt, was passiert ist.

    Ohne sie ist ein Druck auf einen Knopf, dessen Wirkung im Nebenraum
    stattfindet, nicht von einem Druck ins Leere zu unterscheiden.
    """
    ui.click("#interview-start")
    ui.wait_for_function("document.getElementById('interview-meldung').textContent.length > 0")
    assert ui.eval_on_selector("#interview-meldung", "el => el.textContent") == "Interview gestartet"
    assert ui.eval_on_selector("#interview-meldung", "el => el.classList.contains('fehler')") is False

    ui.evaluate(FETCH_SCHEITERT)
    ui.evaluate("(args) => window.kgOperator.render(args[0], args[1])", [GRAPH, LAEUFT])
    ui.click("#interview-stop")
    ui.wait_for_function(
        "document.getElementById('interview-meldung').classList.contains('fehler')"
    )
    meldung = ui.eval_on_selector("#interview-meldung", "el => el.textContent")
    assert "503" in meldung or "nicht" in meldung.lower(), meldung


def test_ein_fehlschlag_uebernimmt_nichts_und_laesst_es_wieder_versuchen(ui):
    """Was nicht angekommen ist, darf am Bedienpult nicht als geschehen stehen.

    Der Anzeigestand faellt auf das zurueck, was zuletzt vom Server kam, und
    der Knopf wird wieder bedienbar -- sonst waere ein einziger Fehlschlag ein
    totes Bedienpult, und das ausgerechnet in dem Moment, in dem jemand es
    eilig braucht.
    """
    ui.evaluate(FETCH_SCHEITERT)
    ui.click("#interview-start")
    ui.wait_for_function(
        "document.getElementById('interview-meldung').classList.contains('fehler')"
    )
    assert ui.eval_on_selector("#interview", "el => el.textContent") == "kein Interview"
    assert _gesperrt(ui, "start") is False


def test_eine_widersprechende_meldung_kurz_nach_dem_druck_kippt_den_knopf_nicht(ui):
    """Der Grund, warum die Uebernahme nicht schon bei der naechsten Meldung faellt.

    Zwischen Druck und geoeffnetem Interview kann jede beliebige andere
    Zustandsmeldung liegen -- ein verschobener Regler etwa. Sie traegt noch
    `interview: null`, weil der Worker noch nicht so weit ist. Wuerde das
    Bedienpult ihr sofort folgen, spraenge der Knopf zurueck: genau das
    Flackern, das nach einem nicht angekommenen Druck aussieht.
    """
    ui.click("#interview-start")
    ui.wait_for_function("document.getElementById('interview-stop').disabled === false")
    ui.evaluate(
        "(args) => window.kgOperator.render(args[0], args[1])",
        [GRAPH, {**STATE, "camera_speed": 0.5}],  # kein Interview, aber eine andere Aenderung
    )
    assert ui.eval_on_selector("#interview", "el => el.textContent") == "Interview läuft"


def test_die_eigene_uebernahme_laeuft_nach_fuenf_sekunden_ab(page, static_server):
    """Die andere Haelfte von „zeigen, nicht besitzen".

    Die Uebernahme nach dem Druck haelt einer widersprechenden Servermeldung
    stand (siehe den Test darueber) -- aber nicht ewig. Sonst genuegte eine
    einzige verschluckte Bestaetigung, damit das Bedienpult bis zum Neuladen
    einen Zustand behauptet, den nur es selbst kennt.

    Die Uhr wird gestellt statt abgewartet: Fuenf Sekunden echte Wartezeit in
    einem Test, der heute vor der Oeffnung laufen muss, sind fuenf Sekunden zu
    viel.
    """
    page.clock.install()
    page.goto(f"{static_server}/frontend/operator.html")
    page.wait_for_function("window.kgOperator !== undefined")
    page.evaluate("window.kgFetches = []")
    page.evaluate(
        "window.fetch = (url, opts) => { window.kgFetches.push([url, JSON.parse(opts.body)]);"
        " return Promise.resolve({ok: true, json: () => Promise.resolve({})}); }; void 0;"
    )
    page.evaluate("(args) => window.kgOperator.render(args[0], args[1])", [GRAPH, STATE])

    page.click("#interview-start")
    # Kein `wait_for_function`: Die stehende Uhr laesst dessen Taktgeber
    # ruhen. Noetig ist es auch nicht -- der nachgebildete `fetch` ist schon
    # erfuellt, sein `then` laeuft als Microtask noch im selben Zug wie der
    # Klick, und dieser Aufruf hier wartet dessen Ende ohnehin ab.
    assert page.eval_on_selector("#interview", "el => el.textContent") == "Interview läuft"

    page.clock.fast_forward("00:06")
    page.evaluate("(args) => window.kgOperator.render(args[0], args[1])", [GRAPH, STATE])
    assert page.eval_on_selector("#interview", "el => el.textContent") == "kein Interview"


def test_der_schalter_am_mikrofon_gewinnt_wieder(ui):
    """🔴 Das Bedienpult ZEIGT den Zustand, es besitzt ihn nicht.

    Es gibt einen zweiten Steuerweg: den Schalter am Mikrofon, der an
    denselben Endpunkt meldet. Beendet er das Interview, das hier gestartet
    wurde, muss das Bedienpult folgen -- sonst stuenden zwei Wahrheiten im
    Raum, und die falsche waere die auf dem Bildschirm des Operators.
    """
    ui.click("#interview-start")
    ui.wait_for_function("document.getElementById('interview-stop').disabled === false")
    # Der Server bestaetigt: das Interview laeuft.
    ui.evaluate("(args) => window.kgOperator.render(args[0], args[1])", [GRAPH, LAEUFT])
    # Und jetzt legt jemand im Raum den Schalter um.
    ui.evaluate("(args) => window.kgOperator.render(args[0], args[1])", [GRAPH, STATE])
    assert ui.eval_on_selector("#interview", "el => el.textContent") == "kein Interview"
    assert _gesperrt(ui, "start") is False
    assert _gesperrt(ui, "stop") is True


def test_der_stop_knopf_beendet_nur_und_startet_nie(ui):
    """Er sendet ausschliesslich `on: false`.

    Nicht, weil ein Start vom Bedienpult verboten waere -- den gibt es seit
    dem 2026-09-02 als eigenen Knopf daneben -- sondern weil genau diese
    Trennung die Absicherung IST: Kein Knopf hier darf je etwas anderes
    senden als den einen Wert, der auf ihm steht.
    """
    ui.evaluate("(args) => window.kgOperator.render(args[0], args[1])", [GRAPH, LAEUFT])
    # Ohne Nachlauf: geprueft wird der gesendete WERT, nicht die Wartezeit.
    ui.evaluate("() => { window.kgOperator.stopNachlaufMs = 0; }")
    ui.click("#interview-stop")
    ui.wait_for_function("document.getElementById('interview-start').disabled === false")
    # Der Server bestaetigt das Ende, danach beginnt das naechste Interview.
    ui.evaluate("(args) => window.kgOperator.render(args[0], args[1])", [GRAPH, STATE])
    ui.evaluate(
        "(args) => window.kgOperator.render(args[0], args[1])",
        [GRAPH, {**STATE, "interview": {"person_id": "p2", "started_at": 200}}],
    )
    ui.click("#interview-stop")

    gesendet = ui.evaluate("window.kgFetches.filter(f => f[0] === '/api/interview_switch')")
    assert len(gesendet) == 2
    assert all(eintrag[1] == {"on": False} for eintrag in gesendet), (
        f"der Knopf hat etwas anderes als on:false gesendet: {gesendet}"
    )


# --- Der Nachlauf beim Beenden (Birk, 2026-09-02) ---------------------------


SCHALTBEFEHLE = "window.kgFetches.filter(f => f[0] === '/api/interview_switch')"


def test_beenden_laeuft_nach_und_sendet_nicht_sofort(ui):
    """🔴 Aus einem echten Schaden an der Wand (2026-09-02).

    p14 (Martin Kranz) wurde mitten in seiner Antwort auf die letzte Frage
    gestoppt. Er sprach zu Ende, das Transkript-Final kam Minuten spaeter, und
    weil `kg/transcript.py` allein nach dem Zeitstempel schneidet, landeten
    drei seiner Begriffe bei der NAECHSTEN Person.

    Birk will den Knopf trotzdem frueh druecken koennen („um dann mit den
    Menschen reden zu koennen") — also darf nicht der Mensch warten, sondern
    der Knopf.
    """
    ui.evaluate("(args) => window.kgOperator.render(args[0], args[1])", [GRAPH, LAEUFT])
    ui.evaluate("() => { window.kgFetches.length = 0; window.kgOperator.stopNachlaufMs = 400; }")

    ui.click("#interview-stop")
    # Sofort nach dem Druck ist kein SCHALTBEFEHL gesendet. Der Aufruf an
    # /api/stt/satzende geht dagegen genau jetzt raus — er ist der Grund, aus
    # dem der Nachlauf ueberhaupt etwas bringt.
    assert ui.evaluate(SCHALTBEFEHLE + ".length") == 0
    assert ui.evaluate("window.kgFetches.some(f => f[0] === '/api/stt/satzende')"), (
        "das Satzende wurde nicht ausgeloest — dann faengt der Nachlauf nur "
        "die Faelle mit Sprechpause"
    )
    # Und der Knopf sagt, was gerade passiert.
    beschriftung = ui.eval_on_selector("#interview-stop", "el => el.textContent")
    assert "Abbrechen" in beschriftung or "abbrechen" in beschriftung, beschriftung

    ui.wait_for_function(SCHALTBEFEHLE + ".length > 0")
    assert ui.evaluate(SCHALTBEFEHLE + ".at(-1)") == ["/api/interview_switch", {"on": False}]


def test_ein_zweiter_druck_bricht_den_nachlauf_ab(ui):
    """Der Weg zurueck. Ein versehentlicher Druck ist der haeufigere Fall, und
    der Abbruch ist die Richtung, in der nichts kaputtgeht — anders als bei
    „sofort beenden", wo ein Fehlgriff ein Interview kostet."""
    ui.evaluate("(args) => window.kgOperator.render(args[0], args[1])", [GRAPH, LAEUFT])
    ui.evaluate("() => { window.kgFetches.length = 0; window.kgOperator.stopNachlaufMs = 400; }")

    ui.click("#interview-stop")
    ui.click("#interview-stop")

    assert ui.evaluate(SCHALTBEFEHLE + ".length") == 0
    assert ui.eval_on_selector("#interview-stop", "el => el.textContent") == "Interview beenden"

    # 🔴 Und der Timer ist WIRKLICH weg, nicht nur die Beschriftung zurueck.
    # Diese Zeile fand eine Mutationsprobe: Mit einer falschen Timer-Referenz
    # (`stopNachlauf = 1`) sah der Abbruch im Moment des Klicks genauso aus,
    # das Interview endete aber Sekunden spaeter trotzdem.
    ui.wait_for_timeout(700)
    assert ui.evaluate(SCHALTBEFEHLE + ".length") == 0, (
        "der abgebrochene Nachlauf hat doch noch gesendet"
    )


def test_endet_das_interview_anderweitig_faellt_der_nachlauf_weg(ui):
    """🔴 Sonst beendet der Timer das NAECHSTE Interview.

    Der Schalter am Mikrofon kann waehrend des Nachlaufs beenden. Liefe der
    Timer weiter, schluege er Sekunden spaeter zu — und die naechste Person
    saesse vor einem Mikrofon, das gerade zugegangen ist. Das waere derselbe
    Schaden, gegen den der Nachlauf gebaut ist, nur eine Person weiter."""
    ui.evaluate("(args) => window.kgOperator.render(args[0], args[1])", [GRAPH, LAEUFT])
    ui.evaluate("() => { window.kgFetches.length = 0; window.kgOperator.stopNachlaufMs = 3000; }")
    ui.click("#interview-stop")

    # Der Server meldet: kein Interview mehr (der Schalter am Mikrofon).
    ui.evaluate("(args) => window.kgOperator.render(args[0], args[1])", [GRAPH, STATE])

    assert ui.eval_on_selector("#interview-stop", "el => el.textContent") == "Interview beenden"
    ui.wait_for_timeout(600)
    assert ui.evaluate(SCHALTBEFEHLE + ".length") == 0, "der Timer hat trotzdem gesendet"
