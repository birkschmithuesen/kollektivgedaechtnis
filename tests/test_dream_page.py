"""Spec §6 — screen B. Driven through the harness, exactly as Tool 1 drives
its renderer: no server, no EventSource, just the view and a state object."""

from __future__ import annotations

import pytest


def state(current=None, history=(), **overrides):
    base = {
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


#: Was der Streifen als AUFLAGE vom Bild verdeckt: die Summe der
#: Miniatur-Flächen, nicht die Höhe eines reservierten Rasterbandes. Seit dem
#: Vollbild-Umbau gibt es kein Band mehr, dessen Höhe man messen könnte — die
#: verdeckte Fläche ist die Größe, die die Aussage „das Hauptbild dominiert"
#: noch trägt.
THUMB_AREA_SHARE = """
() => {
  const boxes = Array.from(document.querySelectorAll('#strip li'))
    .map((li) => li.getBoundingClientRect());
  return boxes.reduce((sum, box) => sum + box.width * box.height, 0) /
    (window.innerWidth * window.innerHeight);
}
"""


def box(page, selector):
    return page.locator(selector).bounding_box()


# -- the baseline layout ----------------------------------------------------


def test_the_image_the_sentence_and_the_strip_are_all_present(view):
    """Drei Elemente, nicht mehr vier: die Leitfrage ist am 2026-08-31
    ersatzlos entfallen (Birk: „Ja, ganz weg")."""
    apply(view, state(current=dream(3), history=[dream(1), dream(2)]))

    assert view.locator("#stage .frame.visible").count() == 1
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


def test_the_strip_covers_only_a_little_of_the_image(view):
    """Spec §6: asymmetric by design — the current dream is the subject.

    Umformuliert am 2026-08-30 (Vollbild-Umbau). Vorher verglich der Test die
    Höhe der Bühne mit der Höhe einer Miniatur. Seit das Bild formatfüllend
    liegt, ist die Bühne per Definition 1080 px hoch und jeder solche Vergleich
    trivial wahr — der Test hätte auch einen Streifen bestanden, der das halbe
    Bild zudeckt. Geprüft wird jetzt, was der Streifen als Auflage tatsächlich
    kostet: den Anteil der Bildfläche, den die Miniaturen verdecken.
    """
    apply(view, state(current=dream(3), history=[dream(i) for i in range(1, 6)]))

    share = view.evaluate(THUMB_AREA_SHARE)
    assert 0 < share < 0.06, f"die Auflage verdeckt {share:.1%} des Bildes"


def test_the_strip_stays_an_overlay_across_the_full_legal_range(view):
    """An operator control must not be able to express a layout that inverts
    the design (Finding 1). `strip_ratio`'s bounds in kg2/server.py were
    lowered from a measured sweep showing the stage-vs-thumbnail dominance
    that held at the default ratio broke down well inside the OLD legal
    range (inverted outright at 0.5). Walking min/middle/max here — instead
    of only the default, like the test above — is what makes a future change
    to either the CSS geometry or the bound fail loudly rather than silently
    re-opening that gap.

    Umformuliert am 2026-08-30 aus demselben Grund wie der Test darüber, und
    zusätzlich am HÄRTESTEN Fall gefahren: 40 Träume, nicht fünf. Der Regler
    ist seit dem Umbau die Miniaturhöhe der Auflage, also ist genau die
    Kombination „größter Regler + vollster Streifen" die, die das Bild
    zustellen könnte.
    """
    for ratio in (0.05, 0.15, 0.25):  # legal minimum, middle, legal maximum
        apply(
            view,
            state(
                current=dream(41),
                history=[dream(i) for i in range(1, 41)],
                strip_ratio=ratio,
            ),
        )
        share = view.evaluate(THUMB_AREA_SHARE)
        assert 0 < share < 0.08, f"Auflage {share:.1%} des Bildes bei strip_ratio={ratio}"
        strip = box(view, "#strip")
        assert strip["height"] <= 0.12 * 1080, f"Auflage zu hoch bei strip_ratio={ratio}"


def test_the_page_is_readable_with_no_dreams_at_all(view):
    """09:00, before the first interview. Empty, not broken."""
    apply(view, state())

    assert view.locator("#sentence").inner_text() == ""
    assert view.locator("#strip li").count() == 0


def test_a_full_strip_of_forty_dreams_still_fits_on_screen(view):
    """The end of the festival day is the hard case (spec §11's visual series).

    Gilt weiter, jetzt gegen die Auflage: der Streifen hängt an keiner
    Rasterzeile mehr, sondern liegt unten rechts auf dem Bild. Dazu kommt eine
    Aussage, die vorher keinen Sinn ergab — EINE Reihe. Der Streifen wächst
    nicht mehr nach oben ins Bild hinein (siehe dream.css: der Modus `wrap`
    ist mit dem Umbau entfallen).
    """
    apply(view, state(current=dream(41), history=[dream(i) for i in range(1, 41)]))

    assert view.locator("#strip li").count() == 40
    strip = box(view, "#strip")
    assert strip["y"] + strip["height"] <= 1081  # inside a 1080-high viewport
    assert strip["x"] >= -1 and strip["x"] + strip["width"] <= 1921

    tops = view.locator("#strip li").evaluate_all(
        "els => els.map(e => Math.round(e.getBoundingClientRect().top))"
    )
    assert len(set(tops)) == 1, f"die Auflage ist auf {len(set(tops))} Reihen umgebrochen"


def test_the_longest_seeded_sentence_stays_clear_of_the_strip_and_the_screen(view):
    """Review finding: the seeded corpus used to top out at 21 words, so this
    case — a genuine 36-40 word sentence in the two-line `#sentence` budget,
    WITH a full strip below it — was never actually rendered before being
    judged. Uses the real corpus, not a hand-picked long string, so a future
    edit that quietly shortens it back down would be caught here too.

    Umbenannt am 2026-08-30: „push the strip off screen" beschrieb den
    Rastermechanismus — ein wachsender Satz schob die Streifenzeile nach
    unten. Den gibt es nicht mehr, der Streifen ist absolut verankert. Die
    Gefahr hat die Seite gewechselt: jetzt wächst der Satz nach OBEN aus dem
    Verlauf heraus. Beides wird geprüft.
    """
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

    strip = box(view, "#strip")
    assert strip["y"] + strip["height"] <= 1081  # inside a 1080-high viewport
    sentence = box(view, "#sentence")
    assert sentence["y"] + sentence["height"] <= strip["y"]
    assert sentence["y"] >= 0  # nicht oben aus dem Bild heraus


# -- formatfüllendes Bild (Birk, 2026-08-30) ---------------------------------


def test_the_image_fills_the_whole_screen(view):
    """Birks Befund an der Station: „bei einem Vollbild 16:9 das Bild
    bildschirmfüllend komplett da". Gemessen wurde vorher 671 von 1080 px
    (62 % der Höhe, 39 % der Fläche) — der Rest ging an die drei anderen
    Rasterzeilen. Das Bild hängt jetzt an keiner Zeile mehr."""
    apply(view, state(current=dream(3), history=[dream(1), dream(2)]))

    frame = box(view, "#stage .frame.visible")
    assert frame["width"] == pytest.approx(1920, abs=2)
    assert frame["height"] == pytest.approx(1080, abs=2)
    assert frame["x"] == pytest.approx(0, abs=2)
    assert frame["y"] == pytest.approx(0, abs=2)

    # Beide gestapelten Rahmen, nicht nur der sichtbare: die Überblendung
    # blendet auf den anderen um, und ein `contain` dort wäre ein sichtbarer
    # Sprung mitten in der Blende (Randbedingung 1).
    fits = view.locator("#stage .frame").evaluate_all(
        "els => els.map(e => getComputedStyle(e).objectFit)"
    )
    assert fits == ["cover", "cover"]


def test_there_is_no_question_element_and_the_image_still_fills_the_screen(view):
    """Die Leitfrage ist am 2026-08-31 ersatzlos entfallen (Birk an der
    Station: „Ja, ganz weg") — sie erreichte seit dem 2026-08-28 kein Modell
    mehr und zeigte obendrein eine Frage, die den Gästen nie gestellt wurde.

    Dieser Test ersetzt `test_switching_the_question_off_does_not_change_the_
    image_area`: dessen Fehlerbild — die Frage-Zeile fiel aus dem alten
    Raster, die Bühne landete auf der `auto`-Zeile und war 0 px hoch — kann
    ohne Frage und ohne Raster nicht mehr auftreten, und der Schalter, den er
    umlegte, existiert nicht mehr. Geprüft bleibt die Randbedingung, die von
    der Entfernung berührt wird: Kein `#question` im Dokument, und der frei
    gewordene Platz oben bekommt kein Ersatzelement, sondern gehört dem Bild.
    """
    apply(view, state(current=dream(3), history=[dream(1), dream(2)]))

    assert view.locator("#question").count() == 0

    frame = box(view, "#stage .frame.visible")
    assert frame["width"] == pytest.approx(1920, abs=2)
    assert frame["height"] == pytest.approx(1080, abs=2)
    assert frame["x"] == pytest.approx(0, abs=2)
    assert frame["y"] == pytest.approx(0, abs=2)

    # Und oben liegt wirklich nichts mehr auf dem Bild: kein Element ragt in
    # die oberen 18 vh, die vorher der Frage und ihrem Verlauf gehörten.
    top_band = view.evaluate(
        """() => Array.from(document.querySelectorAll('#page > *'))
             .filter((el) => el.id !== 'stage')
             .filter((el) => { const b = el.getBoundingClientRect();
                               return b.height > 0 && b.top < 0.18 * window.innerHeight; })
             .map((el) => el.id)"""
    )
    assert top_band == []


def test_the_sentence_lies_over_the_image_on_a_scrim_and_clear_of_the_strip(view):
    """Variante A: der Satz liegt auf dem Bild, nicht darunter. Auf einem
    hellen Traumbild ist heller Text ohne Verlauf unlesbar — der Verlauf ist
    der Grund, dass der Satz überhaupt oben liegen darf, keine Dekoration.
    Deshalb wird hier beides geprüft: dass es ihn gibt, dass er den Satz
    wirklich unterlegt, und dass die Auflage ihn nicht überdeckt."""
    apply(view, state(current=dream(41), history=[dream(i) for i in range(1, 41)]))

    scrim, scrim_height = view.locator("#page").evaluate(
        "e => { const s = getComputedStyle(e, '::after');"
        "       return [s.backgroundImage, parseFloat(s.height)]; }"
    )
    assert "gradient" in scrim, "kein Verlauf unter dem Satz"

    frame = box(view, "#stage .frame.visible")
    sentence = box(view, "#sentence")
    strip = box(view, "#strip")

    # Über dem Bild — also innerhalb der Bildfläche, nicht darunter.
    assert sentence["y"] >= frame["y"]
    assert sentence["y"] + sentence["height"] <= frame["y"] + frame["height"]
    # Und innerhalb des Verlaufs, sonst trägt der Verlauf den Satz nicht.
    assert sentence["y"] >= 1080 - scrim_height
    # Die Auflage liegt darunter, nicht darauf.
    assert sentence["y"] + sentence["height"] <= strip["y"]

    # OBEN liegt seit dem 2026-08-31 kein Verlauf mehr: der obere war
    # ausschließlich für die Leitfrage da, die es nicht mehr gibt. Ein Verlauf
    # ohne Text darunter verdunkelt nur das Bild, dem dieser Platz gehört.
    top_scrim = view.locator("#page").evaluate(
        "e => getComputedStyle(e, '::before').backgroundImage"
    )
    assert "gradient" not in top_scrim


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


# Die drei Tests zur Leitfrage (`test_the_question_can_be_switched_off`,
# `test_the_question_auto_hides_after_the_configured_seconds`,
# `test_zero_seconds_means_permanent`) sind am 2026-08-31 entfallen: sie
# prüften das Verhalten eines Elements und zweier Schalter, die es nicht mehr
# gibt. Was von ihnen bleibt, ist die Abwesenheitsprüfung oben
# (`test_there_is_no_question_element_and_the_image_still_fills_the_screen`).


# -- the cross-fade (spec §6, Birk: not a morph) -----------------------------


def mid_fade_opacities(page):
    """Die Deckkraft beider Rahmen in dem Moment, in dem die Blende läuft.

    Gelesen in DERSELBEN Auswertung, die die Bedingung entscheidet — sonst
    wäre zwischen „ist mittendrin" und „lies ab" wieder ein Rennen. Kein
    festes Zeitfenster: dieselbe Lehre wie beim Schreibmaschinen-Test am
    2026-08-30 (dream.js, TYPE_MS) — ein Test, der von der Auslastung des
    Rechners abhängt, sagt nichts über den Code. Seit das Bild formatfüllend
    liegt, blendet Chromium zwei 1920×1080-Flächen ineinander; auf einem
    software-gerenderten Rechner kommt das erste Einzelbild der Blende
    messbar später als nach den vorher fest gewarteten 150 ms.
    """
    handle = page.wait_for_function(
        "() => { const values = Array.from(document.querySelectorAll('#stage .frame'))"
        "         .map((e) => Number(getComputedStyle(e).opacity));"
        "       return values.some((v) => v > 0 && v < 1) ? values : null; }",
        timeout=10000,
    )
    return handle.json_value()


def test_a_new_dream_cross_fades_rather_than_cutting(view):
    apply(view, state(current=dream(1)))

    view.evaluate("(s) => window.kgDream.applyState(s)", state(current=dream(2), history=[dream(1)]))

    opacities = mid_fade_opacities(view)
    # Both frames on screen at once is what makes it a fade and not a cut.
    # Gewartet wurde auf EINEN Rahmen dazwischen, geprüft werden BEIDE — sonst
    # wäre die Zusicherung nur die Wiederholung der Wartebedingung.
    assert all(0 < value < 1 for value in opacities), opacities
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
    session" separately from `currentId` is what makes this a fade again.

    Wartet seit dem Vollbild-Umbau auf die Bedingung statt auf die Uhr, siehe
    `mid_fade_opacities`. Der ausgeblendete Rahmen steht hier auf 0 (die Bühne
    war leer), es kann also nur EINER dazwischen liegen."""
    apply(view, state(current=dream(1)))
    apply(view, state(current=None, history=[]))

    view.evaluate("(s) => window.kgDream.applyState(s)", state(current=dream(2)))

    opacities = mid_fade_opacities(view)
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
    """Wortweise, nicht auf einen Schlag.

    Repariert am 2026-08-30: Der Test wartete feste 120 ms und griff dann den
    Zwischenstand ab. Bei 55 ms pro Wort (dream.js, TYPE_MS) und fünf Wörtern
    ist das ein Rennen — allein lief er grün, im vollen Lauf unter Last war
    der Satz nach 120 ms schon fertig und der Test rot. Ein Test, der von der
    Auslastung des Rechners abhängt, sagt nichts über den Code.

    Jetzt wird auf den ERSTEN Zwischenstand gewartet, statt auf die Uhr zu
    schauen: sobald überhaupt Text steht, muss er kürzer als der ganze Satz
    sein. Das prüft dieselbe Eigenschaft — es baut sich auf — und kann nicht
    mehr am Zeitverhalten der Maschine scheitern.
    """
    apply(view, state(current=dream(1), typewriter=True))

    ganzer_satz = "Der Beton träumt von Wald"
    view.evaluate(f"() => window.kgDream.showDreaming({ganzer_satz!r})")

    # Der erste Zustand, in dem überhaupt etwas steht — der muss unvollständig
    # sein. Kein Timeout-Fenster, sondern eine Bedingung.
    view.wait_for_function(
        "() => document.getElementById('typewriter').innerText.length > 0",
        timeout=10000,
    )
    partial = view.locator("#typewriter").inner_text()

    view.wait_for_function(
        "() => document.getElementById('typewriter').innerText.includes('Wald')", timeout=10000
    )

    assert partial != ganzer_satz
    assert ganzer_satz.startswith(partial), (
        f"der Zwischenstand muss ein Präfix des Satzes sein, war: {partial!r}"
    )
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
