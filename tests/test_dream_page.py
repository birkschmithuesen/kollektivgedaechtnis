"""Spec §6 — screen B. Driven through the harness, exactly as Tool 1 drives
its renderer: no server, no EventSource, just the view and a state object."""

from __future__ import annotations

import pytest


def state(current=None, history=(), **overrides):
    base = {
        "question": "Wie leben und bauen wir in zehn Jahren?",
        "question_visible": True,
        "question_seconds": 0,
        "fade_ms": 1200,
        "strip_ratio": 0.22,
        "typewriter": False,
        "paused": False,
        "current": current,
        "history": list(history),
    }
    base.update(overrides)
    return base


def dream(index, sentence=None):
    return {
        "id": f"d{index}",
        "created_at": 1000.0 + index,
        "sentence": sentence or f"Traum {index}",
        # A 1x1 transparent GIF: a real, decodable image with no network.
        "image": "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7",
    }


@pytest.fixture()
def view(page, static_server):
    page.goto(f"{static_server}/frontend2/static/dream-harness.html")
    page.wait_for_function("window.kgDream !== undefined")
    return page


def apply(page, value):
    page.evaluate("(s) => window.kgDream.applyState(s)", value)
    page.wait_for_function("() => window.kgDream.fading === false", timeout=10000)


# -- the baseline layout ----------------------------------------------------


def test_the_question_the_image_the_sentence_and_the_strip_are_all_present(view):
    apply(view, state(current=dream(3), history=[dream(1), dream(2)]))

    assert view.locator("#question").inner_text() == "Wie leben und bauen wir in zehn Jahren?"
    assert view.locator("#sentence").inner_text() == "Traum 3"
    assert view.locator("#strip li").count() == 2


def test_the_strip_runs_oldest_to_newest(view):
    """Spec §6. The strip is a time axis, not a stack of most-recent-first."""
    apply(view, state(current=dream(3), history=[dream(1), dream(2)]))

    labels = view.locator("#strip li img").evaluate_all("els => els.map(e => e.alt)")
    assert labels == ["Traum 1", "Traum 2"]


def test_the_current_dream_is_not_repeated_in_the_strip(view):
    apply(view, state(current=dream(3), history=[dream(1), dream(2)]))

    assert view.locator("#strip li").count() == 2
    assert view.locator("#strip").inner_html().count("Traum 3") == 0


def test_the_current_image_dominates_the_strip(view):
    """Spec §6: asymmetric by design — the current dream is the subject."""
    apply(view, state(current=dream(3), history=[dream(i) for i in range(1, 6)]))

    stage = view.locator("#stage").bounding_box()
    thumb = view.locator("#strip li").first.bounding_box()
    assert stage["height"] > thumb["height"] * 3


def test_the_stage_dominates_the_strip_across_the_full_legal_range(view):
    """An operator control must not be able to express a layout that inverts
    the design (Finding 1). `strip_ratio`'s bounds in kg2/server.py were
    lowered from a measured sweep showing the stage-vs-thumbnail dominance
    that held at the default ratio broke down well inside the OLD legal
    range (inverted outright at 0.5). Walking min/middle/max here — instead
    of only the default, like the test above — is what makes a future change
    to either the CSS geometry or the bound fail loudly rather than silently
    re-opening that gap."""
    for ratio in (0.05, 0.15, 0.25):  # legal minimum, middle, legal maximum
        apply(
            view,
            state(current=dream(3), history=[dream(i) for i in range(1, 6)], strip_ratio=ratio),
        )
        stage = view.locator("#stage").bounding_box()
        thumb = view.locator("#strip li").first.bounding_box()
        assert stage["height"] > thumb["height"] * 2, f"dominance lost at strip_ratio={ratio}"


def test_the_page_is_readable_with_no_dreams_at_all(view):
    """09:00, before the first interview. Empty, not broken."""
    apply(view, state())

    assert view.locator("#sentence").inner_text() == ""
    assert view.locator("#strip li").count() == 0
    assert view.locator("#question").is_visible() is True


def test_a_full_strip_of_forty_dreams_still_fits_on_screen(view):
    """The end of the festival day is the hard case (spec §11's visual series)."""
    apply(view, state(current=dream(41), history=[dream(i) for i in range(1, 41)]))

    assert view.locator("#strip li").count() == 40
    strip = view.locator("#strip").bounding_box()
    assert strip["y"] + strip["height"] <= 1081  # inside a 1080-high viewport


def test_the_longest_seeded_sentence_does_not_push_the_strip_off_screen(view):
    """Review finding: the seeded corpus used to top out at 21 words, so this
    case — a genuine 36-40 word sentence in the two-line `#sentence` budget,
    WITH a full strip below it — was never actually rendered before being
    judged. Uses the real corpus, not a hand-picked long string, so a future
    edit that quietly shortens it back down would be caught here too."""
    from sim.seed_dreams import SENTENCES

    longest = max(SENTENCES, key=lambda sentence: len(sentence.split()))
    assert len(longest.split()) >= 36  # otherwise this isn't the hard case

    apply(
        view,
        state(
            current=dream(41, sentence=longest),
            history=[dream(i) for i in range(1, 41)],
        ),
    )

    strip = view.locator("#strip").bounding_box()
    assert strip["y"] + strip["height"] <= 1081  # inside a 1080-high viewport
    sentence_box = view.locator("#sentence").bounding_box()
    assert sentence_box["y"] + sentence_box["height"] <= strip["y"]


# -- sizing (spec §6 / T1§11) ------------------------------------------------


def test_every_size_is_viewport_relative(view):
    """Tool 1's rule: model units scaled to the viewport, so a different screen
    changes nothing. Measured by resizing rather than by reading the CSS."""
    apply(view, state(current=dream(1), history=[dream(0)]))
    small = view.locator("#strip li").first.bounding_box()["height"]

    view.set_viewport_size({"width": 3840, "height": 2160})
    view.wait_for_timeout(200)
    large = view.locator("#strip li").first.bounding_box()["height"]

    assert large == pytest.approx(small * 2, rel=0.05)


def test_the_strip_ratio_control_changes_the_thumbnail_height(view):
    apply(view, state(current=dream(1), history=[dream(0)], strip_ratio=0.15))
    thin = view.locator("#strip li").first.bounding_box()["height"]

    apply(view, state(current=dream(1), history=[dream(0)], strip_ratio=0.35))
    thick = view.locator("#strip li").first.bounding_box()["height"]

    assert thick > thin * 1.8


# -- the guiding question (spec §7) ------------------------------------------


def test_the_question_can_be_switched_off(view):
    apply(view, state(current=dream(1), question_visible=False))

    assert view.locator("#question").is_visible() is False


def test_the_question_auto_hides_after_the_configured_seconds(view):
    apply(view, state(current=dream(1), question_visible=True, question_seconds=1))

    assert view.locator("#question").is_visible() is True
    view.wait_for_function(
        "() => !document.getElementById('question').checkVisibility()", timeout=5000
    )


def test_zero_seconds_means_permanent(view):
    apply(view, state(current=dream(1), question_visible=True, question_seconds=0))
    view.wait_for_timeout(1500)

    assert view.locator("#question").is_visible() is True


# -- the cross-fade (spec §6, Birk: not a morph) -----------------------------


def test_a_new_dream_cross_fades_rather_than_cutting(view):
    apply(view, state(current=dream(1)))

    view.evaluate("(s) => window.kgDream.applyState(s)", state(current=dream(2), history=[dream(1)]))
    view.wait_for_timeout(150)  # mid-fade

    opacities = view.locator("#stage .frame").evaluate_all(
        "els => els.map(e => Number(getComputedStyle(e).opacity))"
    )
    # Both frames on screen at once is what makes it a fade and not a cut.
    assert sum(1 for value in opacities if 0 < value < 1) >= 1
    view.wait_for_function("() => window.kgDream.fading === false", timeout=10000)


def test_discarding_the_only_dream_leaves_no_stale_image_on_the_stage(view):
    """Finding 2: applyState({current: None}) — the only dream was discarded,
    or the store genuinely has nothing left — must not leave the previous
    frame frozen on screen with no sentence under it. Going blank is correct
    here; a stale frame is not."""
    apply(view, state(current=dream(1)))

    apply(view, state(current=None, history=[]))

    assert view.locator("#sentence").inner_text() == ""
    opacities = view.locator("#stage .frame").evaluate_all(
        "els => els.map(e => Number(getComputedStyle(e).opacity))"
    )
    assert all(value == 0 for value in opacities)


def test_a_dream_after_a_discard_to_empty_cross_fades_rather_than_cutting(view):
    """Finding 2: the instant-reveal decision used to key off `currentId ===
    null`, which is also true right after a discard-to-empty — so the next
    dream took the no-animation reveal path from a stage that was still
    showing the old frame a moment before. Tracking "ever revealed this
    session" separately from `currentId` is what makes this a fade again."""
    apply(view, state(current=dream(1)))
    apply(view, state(current=None, history=[]))

    view.evaluate("(s) => window.kgDream.applyState(s)", state(current=dream(2)))
    view.wait_for_timeout(150)  # mid-fade

    opacities = view.locator("#stage .frame").evaluate_all(
        "els => els.map(e => Number(getComputedStyle(e).opacity))"
    )
    assert sum(1 for value in opacities if 0 < value < 1) >= 1
    view.wait_for_function("() => window.kgDream.fading === false", timeout=10000)


def test_the_fade_duration_follows_the_operator_setting(view):
    apply(view, state(current=dream(1), fade_ms=400))

    duration = view.locator("#stage .frame").first.evaluate(
        "e => getComputedStyle(e).transitionDuration"
    )

    assert duration.startswith("0.4")


def test_the_transition_is_opacity_only_never_a_transform(view):
    """Birk ruled out morphs explicitly (spec §6, brainstorm §2). A transform
    in the transition list is how a morph sneaks back in."""
    apply(view, state(current=dream(1)))

    properties = view.locator("#stage .frame").first.evaluate(
        "e => getComputedStyle(e).transitionProperty"
    )

    assert "opacity" in properties
    assert "transform" not in properties


def test_re_applying_the_same_state_does_not_re_fade(view):
    """The state push arrives on every control change too. Re-fading the image
    each time an operator nudges the strip ratio would be visible on the wall.

    Finding 3: the earlier version of this test asserted `current == first`
    (trivially true — nothing here changes the id) and `fading is False`
    (guaranteed by the `apply()` helper, which polls for exactly that before
    returning). It passed even with the `dream.id !== currentId` guard
    deleted. This version asserts on what a re-fade would actually do: swap
    which of the two stacked frames carries `visible`, and write a src onto
    the frame that a real re-fade would target. Confirmed to fail without the
    guard, then the guard was restored — see the fix report."""
    apply(view, state(current=dream(1)))
    visible_id_before = view.locator("#stage .frame.visible").get_attribute("id")
    other_src_before = view.locator("#stage .frame:not(.visible)").get_attribute("src")

    apply(view, state(current=dream(1), strip_ratio=0.2))

    assert view.locator("#stage .frame.visible").get_attribute("id") == visible_id_before
    assert view.locator("#stage .frame:not(.visible)").get_attribute("src") == other_src_before


# -- the typewriter (spec §6) ------------------------------------------------


def test_the_typewriter_builds_the_sentence_up_while_stage_2_runs(view):
    apply(view, state(current=dream(1), typewriter=True))

    view.evaluate("() => window.kgDream.showDreaming('Der Beton träumt von Wald')")
    view.wait_for_timeout(120)
    partial = view.locator("#typewriter").inner_text()
    view.wait_for_function(
        "() => document.getElementById('typewriter').innerText.includes('Wald')", timeout=10000
    )

    assert partial != "Der Beton träumt von Wald"
    assert view.locator("#typewriter").is_visible() is True


def test_the_typewriter_settles_into_the_baseline_line_when_the_image_arrives(view):
    """Spec §6: one layout with an optional animation, not a second layout."""
    apply(view, state(current=dream(1), typewriter=True))
    view.evaluate("() => window.kgDream.showDreaming('Der Beton träumt von Wald')")
    view.wait_for_timeout(300)

    apply(view, state(current=dream(2, "Der Beton träumt von Wald"), history=[dream(1)],
                      typewriter=True))

    assert view.locator("#typewriter").is_visible() is False
    assert view.locator("#sentence").inner_text() == "Der Beton träumt von Wald"


def test_the_typewriter_switch_off_leaves_the_baseline_intact(view):
    """Turning it off is a switch, not a rebuild (spec §6)."""
    apply(view, state(current=dream(1), typewriter=False))

    view.evaluate("() => window.kgDream.showDreaming('sollte nichts tun')")
    view.wait_for_timeout(300)

    assert view.locator("#typewriter").is_visible() is False
    assert view.locator("#sentence").inner_text() == "Traum 1"


def test_turning_the_typewriter_off_mid_animation_stops_it(view):
    """Finding 4: `applyState` used to call `stopTypewriter()` only when the
    dream id changed, so flipping `typewriter: true -> false` while a
    word-by-word build was ticking let it run to completion on screen.
    Turning it off is a switch, not a rebuild — it must stop where it
    stands, not at the end of the sentence."""
    apply(view, state(current=dream(1), typewriter=True))
    view.evaluate("() => window.kgDream.showDreaming('Der Beton träumt von einem Wald voller Vögel')")
    view.wait_for_timeout(120)
    partial = view.locator("#typewriter").inner_text()
    assert partial != "" and "Vögel" not in partial  # confirms it was still mid-build

    apply(view, state(current=dream(1), typewriter=False))

    assert view.locator("#typewriter").is_visible() is False
    assert view.locator("#typewriter").inner_text() == ""
    # Long enough for the old interval to have reached the last word if it
    # had kept ticking — proves it was actually cleared, not just hidden.
    view.wait_for_timeout(400)
    assert view.locator("#typewriter").inner_text() == ""


def test_the_baseline_carries_the_sixty_second_risk_either_way(view):
    """Spec §6 / brainstorm §3: while a dream is generating, the PREVIOUS image
    and sentence stay up. Nothing blanks, with or without the typewriter."""
    for typewriter in (False, True):
        apply(view, state(current=dream(1), typewriter=typewriter))
        view.evaluate("() => window.kgDream.showDreaming('unterwegs')")
        view.wait_for_timeout(200)

        assert view.locator("#sentence").inner_text() == "Traum 1"
        assert view.locator("#stage .frame.visible").count() == 1


# -- a failed dream (Finding 1) ----------------------------------------------


def test_dream_failed_clears_the_typewriter_but_leaves_the_baseline_untouched(view):
    """Finding 1: stage 2 failed after stage 1 already announced a sentence
    and the typewriter started building it. `dreamFailed()` — the signal the
    watcher publishes on this path instead of a `state` push — must clear the
    overlay without touching the previous dream's sentence or image (spec
    §8's "ride it out": a failure needs nothing undone because nothing about
    the current dream changed)."""
    apply(view, state(current=dream(1), typewriter=True))
    view.evaluate("() => window.kgDream.showDreaming('Der Beton träumt von Wald')")
    view.wait_for_timeout(120)
    partial = view.locator("#typewriter").inner_text()
    assert partial != ""  # confirms the typewriter really was mid-build

    view.evaluate("() => window.kgDream.dreamFailed()")

    assert view.locator("#typewriter").is_visible() is False
    assert view.locator("#typewriter").inner_text() == ""
    # The baseline — sentence AND image — is exactly what it was before the
    # failed attempt started, not blanked and not advanced.
    assert view.locator("#sentence").inner_text() == "Traum 1"
    assert view.locator("#stage .frame.visible").count() == 1
    assert view.locator("#stage .frame.visible").get_attribute("src") == dream(1)["image"]


# -- no dashboard (spec §6) --------------------------------------------------


def test_there_is_no_counter_no_progress_bar_and_no_spinner(view):
    apply(view, state(current=dream(3), history=[dream(1), dream(2)]))

    html = view.locator("body").inner_html()
    for forbidden in ("progress", "spinner", "loading", "generiert", "Traum 3 von"):
        assert forbidden not in html.lower()
    assert view.locator("progress").count() == 0
