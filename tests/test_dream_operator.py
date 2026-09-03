"""Spec §7 — Tool 2's own operator interface, and its deliberate limits."""

from __future__ import annotations

import json

import pytest


def state(**overrides):
    base = {
        "fade_ms": 1200,
        "strip_ratio": 0.22,
        "typewriter": False,
        "slideshow": True,
        "paused": False,
        "current": None,
        "history": [],
    }
    base.update(overrides)
    return base


def record(index, status="done", discarded=False):
    return {
        "id": f"d{index}",
        "created_at": 1000.0 + index,
        "sentence": f"Traum {index}",
        "image": "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7",
        "status": status,
        "discarded": discarded,
        "error": None if status != "failed" else "read timeout",
        "person_count": 6,
        "term_count": 5,
        "edge_count": 9,
        "contradiction": True,
        "stage1_prompt": f"S1 für d{index}",
        "stage2_prompt": f"S2 für d{index}",
        "condense_model": "claude-opus-5",
        "image_model": "google/gemini-3-pro-image",
        # Seit 2026-08-30 fuer den Werkstatt-Tab: das, WORAUS das Bild
        # entstanden ist, nicht nur das Ergebnis.
        "sentence_en": f"Dream {index} in English",
        "image_description": f"A wide courtyard, dream {index}",
        "tension_source": f"widerspruch {index}",
        "mood": 3,
        "tension": 4,
    }


@pytest.fixture()
def ui(page, static_server):
    """The real page, with fetch stubbed so nothing needs a server."""
    page.goto(f"{static_server}/frontend2/operator.html")
    page.evaluate(
        """() => {
             window.__posts = [];
             window.__failNext = false;
             window.fetch = (url, options) => {
               if (!options || options.method !== 'POST') {
                 return Promise.resolve({ ok: true, json: () => Promise.resolve({ dreams: [] }) });
               }
               window.__posts.push([url, JSON.parse(options.body || '{}')]);
               const ok = !window.__failNext;
               window.__failNext = false;
               return Promise.resolve({ ok, status: ok ? 200 : 500, statusText: 'x' });
             };
           }"""
    )
    page.wait_for_function("window.kgDreamOperator !== undefined")
    return page


def render(page, value, dreams=()):
    page.evaluate("(a) => window.kgDreamOperator.render(a[0])", [value])
    page.evaluate("(a) => window.kgDreamOperator.renderDreams(a[0])", [list(dreams)])


def posts(page):
    return page.evaluate("() => window.__posts")


# -- display settings (spec §7) --------------------------------------------


def test_every_display_control_is_present(ui):
    render(ui, state())

    for control in ("#fade-ms", "#strip-ratio", "#typewriter", "#slideshow"):
        assert ui.locator(control).count() == 1


def test_the_controls_show_the_servers_values(ui):
    render(ui, state(fade_ms=800, strip_ratio=0.3, typewriter=True))

    assert ui.locator("#fade-ms").input_value() == "800"
    assert ui.locator("#strip-ratio").input_value() == "0.3"
    assert ui.locator("#typewriter").is_checked() is True


def test_changing_the_fade_posts_it(ui):
    render(ui, state())

    ui.locator("#fade-ms").fill("600")
    ui.locator("#fade-ms").dispatch_event("change")

    assert posts(ui)[-1] == ["/api/display", {"fade_ms": 600}]


def test_toggling_the_typewriter_posts_it(ui):
    render(ui, state())

    ui.locator("#typewriter").click()

    assert posts(ui)[-1] == ["/api/display", {"typewriter": True}]


def test_die_slideshow_laesst_sich_am_pult_abschalten(ui):
    """🔴 BIRK, 2026-09-03: „der traum operator braucht noch einen button um die
    automatische slideshow an/aus zu setzen."

    Bis dahin ging das nur ueber `?slideshow=0` an jeder Flaeche einzeln — also
    nicht waehrend die Ausstellung laeuft, und nicht fuer alle zugleich.
    """
    render(ui, state())
    assert ui.locator("#slideshow").is_checked() is True

    ui.locator("#slideshow").click()

    assert posts(ui)[-1] == ["/api/display", {"slideshow": False}]


def test_der_haken_zeigt_was_der_server_sagt(ui):
    """Ein Schalter, der etwas anderes anzeigt als das, was gilt, ist schlimmer
    als keiner — dieselbe Regel wie beim Zoomregler an der Wand."""
    render(ui, state(slideshow=False))
    assert ui.locator("#slideshow").is_checked() is False

    render(ui, state(slideshow=True))
    assert ui.locator("#slideshow").is_checked() is True


def test_ohne_das_feld_steht_der_haken_auf_an(ui):
    """Ein aelterer Kern schickt `slideshow` nicht mit. Dann soll der Haken
    zeigen, was die Wand in diesem Fall TUT — und die blaettert."""
    ohne = state()
    del ohne["slideshow"]
    render(ui, ohne)

    assert ui.locator("#slideshow").is_checked() is True


# `test_switching_the_question_off_posts_it` und
# `test_the_auto_hide_duration_posts_seconds` sind am 2026-08-31 entfallen:
# beide Regler gibt es nicht mehr. Die Abwesenheit prueft
# `test_the_operator_shows_no_guiding_question_at_all` weiter unten.


def test_the_strip_ratio_posts_a_fraction(ui):
    render(ui, state())

    ui.locator("#strip-ratio").fill("0.35")
    ui.locator("#strip-ratio").dispatch_event("change")

    assert posts(ui)[-1] == ["/api/display", {"strip_ratio": 0.35}]


# -- flow control (spec §7) -------------------------------------------------


def test_dream_now_posts(ui):
    render(ui, state())

    ui.locator("#dream-now").click()

    assert posts(ui)[-1][0] == "/api/dream_now"


def test_pause_and_resume_are_one_button_that_says_what_it_will_do(ui):
    render(ui, state(paused=False))
    assert "Pause" in ui.locator("#pause").inner_text()

    ui.locator("#pause").click()
    assert posts(ui)[-1] == ["/api/pause", {"paused": True}]

    render(ui, state(paused=True))
    assert "Weiter" in ui.locator("#pause").inner_text()


def test_discarding_the_current_dream_posts_its_id(ui):
    render(ui, state(current=record(2)), dreams=[record(1), record(2)])

    ui.locator("#discard-current").click()

    assert posts(ui)[-1] == ["/api/discard", {"dream_id": "d2", "discarded": True}]


def test_the_discard_button_is_disabled_when_there_is_nothing_to_discard(ui):
    render(ui, state(current=None))

    assert ui.locator("#discard-current").is_disabled() is True


def test_each_dream_in_the_list_can_be_discarded_and_restored(ui):
    render(ui, state(current=record(2)), dreams=[record(1), record(2, discarded=True)])

    ui.locator("#dream-d1 button.discard").click()
    assert posts(ui)[-1] == ["/api/discard", {"dream_id": "d1", "discarded": True}]

    ui.locator("#dream-d2 button.discard").click()
    assert posts(ui)[-1] == ["/api/discard", {"dream_id": "d2", "discarded": False}]


def test_the_restore_button_says_restore(ui):
    """Same as Tool 1's hide flag: „Wieder einblenden ist derselbe Knopf"."""
    render(ui, state(), dreams=[record(1, discarded=True)])

    assert "zurückholen" in ui.locator("#dream-d1 button.discard").inner_text()


# -- the record (spec §5.3) -------------------------------------------------


def test_the_operator_sees_the_image_prompt(ui):
    """Spec §5.2: stored for reproducibility and shown ONLY here — never on the
    wall, where it would put lighting instructions in front of visitors."""
    render(ui, state(), dreams=[record(1)])

    assert "S2 für d1" in ui.locator("#dream-d1").inner_text()


def test_failed_dreams_appear_with_their_error(ui):
    render(ui, state(), dreams=[record(1, status="failed")])

    text = ui.locator("#dream-d1").inner_text()
    assert "read timeout" in text


def test_a_discarded_dream_is_marked_but_still_listed(ui):
    """The record stays honest (spec §7); only the DISPLAY filters."""
    render(ui, state(), dreams=[record(1, discarded=True)])

    assert ui.locator("#dream-d1").count() == 1
    assert "verworfen" in ui.locator("#dream-d1").inner_text()


# -- the deliberate limits (spec §7) ---------------------------------------


def test_the_operator_shows_no_guiding_question_at_all(ui):
    """Bis zum 2026-08-31 stand die Leitfrage hier unveraenderbar zum
    Nachlesen. Sie ist ersatzlos entfallen — sie steuerte nichts mehr und war
    zudem keine der Fragen, die den Gaesten gestellt werden. Der Nachfolger
    des alten Tests prueft deshalb die Abwesenheit: weder Anzeige noch
    Regler, und auch keine Beschriftung, die noch eine verspricht."""
    render(ui, state())

    assert ui.locator("#the-question").count() == 0
    assert "leitfrage" not in ui.locator("body").inner_text().lower()


def test_there_is_no_control_for_the_register_or_the_weighting(ui):
    render(ui, state(), dreams=[record(1)])

    html = ui.locator("body").inner_html().lower()
    for forbidden in ("register", "bildsprache", "gewichtung", "min_mentions"):
        # Substring, not prefix: an id like "visualRegister" or
        # "dream-register-toggle" would slip past a `id="register` check while
        # breaking the constraint outright.
        assert forbidden not in html
    # And no writable control of any kind beyond the display settings and the
    # three flow buttons — a new <input> here is how a morning-only setting
    # quietly becomes a runtime one. This list is maintained by hand on
    # purpose: a new control must be added here explicitly, or the test fails
    # — that friction is the point of the guard.
    writable = ui.locator("input, textarea, select").evaluate_all(
        "els => els.map((e) => e.id).sort()"
    )
    assert writable == sorted(
        [
            "fade-ms",
            # Das automatische Blaettern durch die Traeume des Tages (Birk,
            # 2026-09-03). Ein ANZEIGE-Regler wie die anderen hier: Er
            # entscheidet, was die Wand ZEIGT, nicht was sie erzeugt — und
            # genau darin liegt die Grenze, die dieser Test bewacht.
            "slideshow",
            "strip-max",
            "strip-ratio",
            "typewriter",
        ]
    )


# -- failure feedback -------------------------------------------------------


def test_a_failed_write_snaps_the_control_back_to_the_servers_value(ui):
    """Tool 1's rule, copied deliberately: this is the exhibition's only human
    control surface, and a control showing a change that did not happen is
    worse than no feedback at all."""
    render(ui, state(fade_ms=1200))
    ui.evaluate("() => { window.__failNext = true; }")

    ui.locator("#fade-ms").fill("600")
    ui.locator("#fade-ms").dispatch_event("change")
    ui.wait_for_function("() => document.getElementById('fade-ms').value === '1200'", timeout=5000)

    assert ui.locator("#fade-ms").input_value() == "1200"


# -- Werkstatt-Tab (Birk, 2026-08-30) ----------------------------------------


def werkstatt(page, dreams):
    """Traeume laden und in den Werkstatt-Tab wechseln."""
    page.evaluate("(a) => window.kgDreamOperator.werkSetze(a[0])", [list(dreams)])
    page.click('.tab[data-tab="werkstatt"]')
    return page


def test_der_werkstatt_tab_zeigt_woraus_das_bild_entstanden_ist(ui):
    """Birk, 2026-08-30: die Durchklick-Ansicht als fester Teil der
    Installation. Der Punkt ist nicht das Bild — das haengt an der Wand —
    sondern der Weg dorthin: Satz, Motiv, Widerspruch, Werte, beide Prompts."""
    werkstatt(ui, [record(1), record(2)])

    assert ui.eval_on_selector("#tab-werkstatt", "el => !el.hidden")
    assert ui.eval_on_selector("#tab-steuerung", "el => el.hidden")
    # Zuletzt entstandener Traum steht vorn: der haengt gerade an der Wand.
    assert ui.eval_on_selector("#werk-satz", "el => el.textContent") == "Traum 2"
    assert "courtyard, dream 2" in ui.eval_on_selector("#werk-motiv", "el => el.textContent")
    assert "widerspruch 2" in ui.eval_on_selector("#werk-widerspruch", "el => el.textContent")
    assert "mood 3" in ui.eval_on_selector("#werk-werte", "el => el.textContent")
    assert "S1 für d2" in ui.eval_on_selector("#werk-prompt1", "el => el.textContent")
    assert "S2 für d2" in ui.eval_on_selector("#werk-prompt2", "el => el.textContent")


def test_man_kann_durch_die_traeume_des_tages_blaettern(ui):
    werkstatt(ui, [record(1), record(2), record(3)])

    assert ui.eval_on_selector("#werk-position", "el => el.textContent") == "3 von 3"
    ui.click("#werk-prev")
    assert ui.eval_on_selector("#werk-satz", "el => el.textContent") == "Traum 2"
    ui.click("#werk-prev")
    assert ui.eval_on_selector("#werk-satz", "el => el.textContent") == "Traum 1"
    # Am Anfang bleibt es stehen, statt in einen leeren Zustand zu laufen.
    ui.click("#werk-prev")
    assert ui.eval_on_selector("#werk-satz", "el => el.textContent") == "Traum 1"
    ui.click("#werk-next")
    assert ui.eval_on_selector("#werk-satz", "el => el.textContent") == "Traum 2"


def test_die_pfeiltasten_blaettern_nur_im_werkstatt_tab(ui):
    """Der Steuerungs-Tab ist voller Zahlenfelder — dort wuerden Pfeiltasten
    Werte verstellen, waehrend der Operator glaubt zu blaettern."""
    werkstatt(ui, [record(1), record(2)])
    ui.keyboard.press("ArrowLeft")
    assert ui.eval_on_selector("#werk-satz", "el => el.textContent") == "Traum 1"

    ui.click('.tab[data-tab="steuerung"]')
    ui.keyboard.press("ArrowRight")
    # Unveraendert: im anderen Tab darf die Taste nichts tun.
    assert ui.eval_on_selector("#werk-satz", "el => el.textContent") == "Traum 1"


def test_ein_gescheiterter_traum_bleibt_in_der_werkstatt_sichtbar(ui):
    """Gerade der Traum, der schiefging, ist der, dessen Prompt man sehen
    will. Die Werkstatt filtert deshalb nicht, anders als die Wand."""
    werkstatt(ui, [record(1), record(2, status="failed")])

    assert ui.eval_on_selector("#werk-position", "el => el.textContent") == "2 von 2"
    assert "failed" in ui.eval_on_selector("#werk-meta", "el => el.textContent")


def test_vor_dem_ersten_traum_steht_ein_hinweis_statt_einer_leeren_flaeche(ui):
    werkstatt(ui, [])

    assert ui.eval_on_selector("#werk-leer", "el => !el.hidden")
    assert ui.eval_on_selector("#werk-inhalt", "el => el.hidden")
