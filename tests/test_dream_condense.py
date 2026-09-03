"""Spec §5.1 — the sentence. What the prompt must say, and what it must not."""

from __future__ import annotations

import pytest

from kg2.condense import (
    CondenseResult,
    DreamSentence,
    SENTENCE_MAX_WORDS,
    build_condense_prompt,
    build_condense_system,
    condense,
)
from kg2.weighting import build_material


class FakeLLM:
    """Records what it was asked, answers what it was told to."""

    def __init__(
        self,
        sentence="Der Beton träumt vom Wald.",
        sentence_en="The concrete dreams of the forest.",
        image_description=(
            "A slab of raw grey concrete stands in a clearing of thin birch "
            "trunks. Its formwork seams are still visible and moss has taken "
            "the lower edge. A printed invoice lies face up on the wet ground "
            "beside it, swollen and curling at the corners."
        ),
        tension_source="restoring an existing façade while billing it as new construction",
        mood=3,
        tension=3,
    ):
        self.sentence = sentence
        self.sentence_en = sentence_en
        self.image_description = image_description
        self.tension_source = tension_source
        self.mood = mood
        self.tension = tension
        self.calls: list[tuple[str, str]] = []

    def parse(self, system, user, output_model):
        self.calls.append((system, user))
        return output_model(
            sentence=self.sentence,
            sentence_en=self.sentence_en,
            image_description=self.image_description,
            tension_source=self.tension_source,
            mood=self.mood,
            tension=self.tension,
        )


class AngryLLM:
    def parse(self, system, user, output_model):
        raise RuntimeError("llm call failed after 2 attempts")


def material(persons=8, quotes=("Wir bauen zu viel Neues.",)):
    nodes = [
        {"id": f"p{i}", "type": "person", "portrait": None, "created_at": 1.0,
         "hidden": False, "x": None, "y": None}
        for i in range(persons)
    ] + [
        {"id": "t1", "type": "term", "label": "Weiterbauen im Bestand", "mentions": persons,
         "created_at": 2.0, "hidden": False, "x": None, "y": None},
        {"id": "t2", "type": "term", "label": "Sickerfähige Beläge", "mentions": 1,
         "created_at": 2.0, "hidden": False, "x": None, "y": None},
    ]
    edges = [{"id": f"e{i}", "source": f"p{i}", "target": "t1"} for i in range(persons)]
    edges.append({"id": "ex", "source": "p0", "target": "t2"})
    return build_material(
        {
            "version": 1, "generated_at": 1000.0, "min_mentions": 1,
            "nodes": nodes, "edges": edges,
            "quotes": [{"id": f"q{i}", "person_id": "p0", "text": t}
                       for i, t in enumerate(quotes, 1)],
        }
    )


# -- the stance -------------------------------------------------------------


def test_the_system_prompt_asks_for_a_dream_not_an_illustration():
    """Spec §1: not a plausible architectural vision. The friction is the
    subject matter, and no model does this without being told."""
    system = build_condense_system()

    assert "Traum" in system
    assert "Verdichtung" in system
    assert "unmöglich" in system
    # The failure mode named by name, so a later edit cannot lose it silently.
    assert "Zusammenfassung" in system
    # „ILLUSTRIEREN", the verb, as the prompt's own heading has it. The prompt
    # text is the artwork and is not edited to suit an assertion.
    assert "ILLUSTRIEREN" in system


def test_the_prompt_forbids_naming_anyone():
    """Spec §12: the dream is collective; quotes feed it, attribution does not.
    Also the quieter answer to „where do my statements end up"."""
    system = build_condense_system()

    assert "keine Namen" in system.lower() or "nenne keine namen" in system.lower()


def test_the_system_prompt_no_longer_carries_a_guiding_question():
    """Decided 2026-08-28: a sixth question nobody was asked forces a reading
    direction the material may not contain. Seit dem 2026-08-31 gibt es gar
    keine Leitfrage mehr — auch nicht als Überschrift auf dem Schirm."""
    system = build_condense_system()

    assert "LEITFRAGE" not in system


def test_the_prompt_requires_evidence_in_the_material():
    """Replaces the removed contradiction clause: everything in the sentence
    must be traceable to the delivered terms, nothing invented."""
    system = build_condense_system()

    assert "erfinden" in system.lower()


def test_the_prompt_carries_the_neutral_condensing_instruction():
    """Spec-decided wording (2026-08-28): condense the terms into one
    statement; a contradiction may appear if the material has one, but must
    not be invented."""
    system = build_condense_system()

    assert "Verdichte" in system


def test_the_prompt_asks_for_one_short_main_clause():
    """Spec §5.1 (revised 2026-08-28): one main clause, at most 16 words, no
    comma, no subordinate clause, no dash — measured against the real
    frontend (docs/operations.md): 36 words made 4 lines / ~11s to read."""
    system = build_condense_system()

    assert "Hauptsatz" in system
    assert str(SENTENCE_MAX_WORDS) in system
    assert "Komma" in system
    assert "Deutsch" in system


def test_the_prompt_asks_for_a_literal_english_translation():
    """The English sentence is the honest counterpart of what stands on the
    wall and is kept with it (spec §5.3). It must be a translation, not a
    rewrite — since 2026-08-29 it is no longer the image motif on its own,
    which is exactly why it may stay literal."""
    system = build_condense_system()

    assert "Englisch" in system
    assert "wörtlich" in system.lower()


def test_the_prompt_asks_for_a_longer_image_description():
    """Befund B (Birk, 2026-08-29): the 16-word wall sentence gave the image
    model almost nothing, while Google's guidance for this exact model asks
    for a scene described narratively. The prompt must ask for length, and
    for what makes a scene visible."""
    system = build_condense_system()

    assert "BILDBESCHREIBUNG" in system
    # Length, named as a number so nobody can read „ausführlich" as one line.
    # Raised from 50-80 to 130-180 on 2026-08-30 (Birk, at the material): the
    # day's graph carries dozens of terms, and at 80 words stage 1 has to drop
    # nearly all of them — measured, the model was already overrunning the old
    # ceiling on its own (88 words average against a stated 50-80).
    assert "130" in system and "180" in system
    # The concrete things the description is supposed to carry. NOT „Licht":
    # naming light is now explicitly forbidden here, because it collides with
    # the mood channel that owns it (same session, measured).
    for asked_for in ("Materialien", "Oberflächen", "Zustand"):
        assert asked_for in system


def test_the_prompt_says_the_wall_sentence_and_the_image_are_the_same_scene():
    """The one way this could go wrong in the room: two different pictures,
    one on the wall in German and another on the screen. They are one scene
    described at two lengths, and the prompt has to say so outright."""
    system = build_condense_system()

    assert "DERSELBEN Szene" in system


def test_the_prompt_keeps_mood_and_camera_instructions_out_of_the_description():
    """Stage 2 fixes the light (MOOD_LIGHT) and the register itself; a second
    source for either would fight it and make the five mood stages
    indistinguishable (kg2/imagegen.py's module docstring)."""
    system = build_condense_system()

    assert "Lichtstimmung" in system
    assert "Kamera" in system


def test_the_prompt_asks_which_two_things_contradict_each_other():
    """Befund A (Birk, 2026-08-29): TENSION_COHERENCE names no content, so
    the image model invented a contradiction of its own. Stage 1 has the
    material and must name the real one."""
    system = build_condense_system()

    assert "WIDERSPRUCH" in system
    assert "Widerspruch aus dem Material" in system


def test_the_prompt_demands_a_VISIBLE_contradiction_not_an_abstract_one():
    """Befund A2 (Birk, 2026-08-29, am dritten Bild des neuen Aufbaus).

    Die erste Fassung verlangte „welche zwei konkreten Dinge einander
    widersprechen" und gab als Beispiel „restoring an existing façade while
    billing it as new construction". Das Modell hat gehorcht — und lieferte
    „gathering opinions while decisions are made from above". Beides sind
    VORGÄNGE, keine Anblicke: „von oben entschieden" hat kein Aussehen, und im
    Bild war davon folgerichtig nichts zu sehen.

    Der Fehler saß im Beispiel, nicht im Modell: ein abstraktes Vorbild
    erzeugt abstrakte Antworten. Ein Bildmodell kann nur Dinge im Raum zeigen,
    also muss Stufe 1 den Widerspruch übersetzen, bevor Stufe 2 ihn bekommt —
    „vier Menschen am runden Tisch unterschreiben den fertigen Plan" statt
    „von oben entschieden".

    Geprüft wird die Eigenschaft, nicht der Wortlaut: dass der Prompt
    Sichtbarkeit verlangt und den Grund dafür nennt.

    **Korrigiert am 2026-08-30.** Bis dahin verlangte dieser Test zusätzlich
    ein POSITIVBEISPIEL, mit der Begründung „ein abstraktes Gegenbeispiel
    allein genügt nicht — das Modell ahmt das Positivbeispiel nach". Der
    zweite Halbsatz stimmt, die Schlussfolgerung war falsch herum: Das Modell
    ahmt das Positivbeispiel WÖRTLICH nach. Gemessen über je fünf Bilder
    stiegen die aus meinem Beispiel übernommenen Wendungen von 9 auf 30, und
    jede einzelne Formulierung daraus tauchte in den Bildern wieder auf
    („thin room outlines" 4/5, „round table signing" 3/5). Alle
    Positivbeispiele sind deshalb aus dem Prompt entfernt; an ihrer Stelle
    steht eine Prüffrage. Negativbeispiele bleiben — die werden nicht
    nachgeahmt.
    """
    system = build_condense_system()

    # Die Anweisung selbst.
    assert "SICHTBARES" in system or "sichtbar" in system.lower()
    # Die Begründung, warum: ein Bildmodell zeigt keine Vorgänge.
    assert "Vorgang" in system
    # Ein Negativbeispiel, das den Fehler benennt, und eine Prüffrage an ihrer
    # Stelle statt eines Musters (siehe Docstring).
    assert "Gut (sichtbar)" not in system  # 2026-08-30, siehe Docstring
    assert "Schlecht (unsichtbar)" in system
    assert "Fotograf" in system  # die Prüffrage, die an die Stelle trat
    # Das konkrete Gegenbeispiel aus Birks Befund muss als schlecht markiert
    # sein — es stand vorher als Vorbild da.
    schlecht = system[system.index("Schlecht (unsichtbar)"):]
    assert "decisions are made from above" in schlecht


def test_the_prompt_demands_both_poles_of_the_material_in_the_picture():
    """Birks Vorgabe (2026-08-29), nachdem ihm das dritte Bild zu düster war:
    Stufe 1 soll „falls möglich das stärkste positive und negative aus dem
    Graphen rausholen und beides zusammen darstellen".

    Die Diagnose davor: Der düstere Ton kam NICHT aus dem mood-Baustein (der
    macht nur das Licht kühl), sondern aus dem Motiv — bröckelnder Putz,
    kellerlose Platte, zugebauter Freiraum. Das Material trägt beides, aber
    die Bildbeschreibung hatte keinen Grund, die zuversichtliche Seite
    mitzunehmen, und der Widerspruch war nur „irgendein Gegensatzpaar".

    Zwei Stellen müssen es tragen, deshalb zwei Prüfungen: die
    Bildbeschreibung (beide Seiten gleich groß im Bild) und der Widerspruch
    (die beiden ÄUSSEREN Enden, nicht ein beliebiges Paar).

    Die Ehrlichkeitsklausel ist Teil der Regel und wird mitgeprüft: Fehlt eine
    Seite im Material, wird sie nicht erfunden — sonst wäre aus „das Material
    ehrlich abbilden" ein „das Bild schönen" geworden, also derselbe Fehler
    mit umgekehrtem Vorzeichen.
    """
    system = build_condense_system()

    # 1. Die Bildbeschreibung muss beide Seiten tragen.
    assert "BEIDE SEITEN INS BILD" in system
    beschreibung = system[system.index("BEIDE SEITEN INS BILD"):]
    assert "gleich groß" in beschreibung
    # Der Zustand der Dinge ist die Stellschraube, nicht die Lichtstimmung.
    assert "intakt" in beschreibung

    # 2. Der Widerspruch spannt die äußeren Enden auf, nicht irgendein Paar.
    assert "WELCHE ZWEI HÄLFTEN" in system
    haelften = system[system.index("WELCHE ZWEI HÄLFTEN"):]
    assert "STÄRKSTE ZUVERSICHTLICHE" in haelften
    assert "STÄRKSTE BEUNRUHIGTE" in haelften

    # 3. Nichts erfinden, wenn eine Seite fehlt.
    assert "erfinden" in haelften


def test_the_prompt_forbids_splitting_the_frame_into_two_pictures():
    """Spec §5.2: ein Ort, eine Aufnahme — nicht zwei Haelften nebeneinander.

    🔴 Die Wache prueft die REGEL, nicht mehr ihre zweifache Nennung
    (konsolidiert 2026-09-02). Vorher verlangte sie zusaetzlich die
    Ueberschrift „AUCH HIER EIN ORT" — das war die WIEDERHOLUNG derselben
    Regel im Widerspruch-Abschnitt. „Ein Ort, eine Aufnahme" stand an fuenf
    Stellen im Prompt; das ist kein Nachdruck, sondern Streuung, und sie
    entstand nur, weil der Prompt nach Themen statt nach Ausgabefeldern
    geordnet war. Jetzt steht die Regel einmal ausfuehrlich bei der
    Bildbeschreibung und wird beim Widerspruch mit einem Halbsatz in Bezug
    genommen („ueber den Raum, nicht ueber eine Trennlinie").

    Die Aussage bleibt: Was der Prompt verbietet, muss er weiter verbieten —
    in BEIDEN Feldern.
    """
    system = build_condense_system()

    ort = system.split("EIN EINZIGER ORT")[1]
    assert "einzige Kamera" in ort
    # Die Trennwendungen, die den Ausschnitt zerlegen, stehen als Verbot da.
    assert "links" in ort
    assert "Kamera von einem Punkt" in ort
    # Kein Positivbeispiel fuer den einen Ort — Beispielszenen werden
    # abgeschrieben (gemessen 2026-08-30).
    assert "Gut (ein Ort)" not in ort

    # Und im Widerspruch-Feld gilt dasselbe, auch ohne eigene Ueberschrift.
    halbsatz = system.split("DER WIDERSPRUCH")[1]
    assert "Trennlinie" in halbsatz

def test_the_prompt_demands_the_german_wording_when_something_carries_lettering():
    """🔴 Umbenannt und umgeschrieben am 2026-09-02, weil sich die
    ENTSCHEIDUNG geaendert hat, nicht die Formulierung.

    Die Wache hiess vorher `..._prefers_no_lettering_...` und verlangte
    „Regelfall ist ein Bild OHNE Schrift" samt Ausnahmeregel — zusammen 2.422
    Zeichen, 13 % des Prompts. Begruendet war das damit, dass der Wandsatz das
    Textstueck der Arbeit ist und ein zweiter Text im Bild gegen ihn antritt.

    Genau diese Begruendung hat Birk am 2026-08-29 verworfen (config2.toml:
    „SCHRIFT IM BILD IST ERLAUBT … Aufgehoben, weil das Verbot einen
    Bildinhalt unmoeglich machte, den das Material hergibt") und am
    2026-09-02 noch einmal bestaetigt: „die schrift drauf stoert auch nicht".
    Der Prompt hat die aufgehobene Regel danach eine Woche weiter
    durchgesetzt.

    Was BLEIBT und hier geprueft wird, ist der Teil, der nie zur Debatte
    stand: Steht Schrift im Bild, muss ihr WORTLAUT dabeistehen, auf Deutsch.
    Ohne das erfindet das Bildmodell englischen Text — und das Bild haengt in
    einer deutschen Ausstellung.
    """
    system = build_condense_system()
    schrift = system.split("SCHRIFT IM BILD")[1]

    # Gross-/Kleinschreibung offen lassen: der Prompt betont Schluesselwoerter
    # in Versalien, und daran soll eine Wache nicht haengen.
    assert "wortlaut" in schrift.lower()
    assert "anführungszeichen" in schrift.lower()
    assert "the German text reading" in schrift
    # Kein Verbot mehr, nur noch eine Bedingung.
    assert "Regelfall ist ein Bild OHNE Schrift" not in system

def test_the_prompt_asks_for_the_contradiction_in_the_shape_stage_2_appends():
    """kg2/imagegen.py hangs `tension_source` behind a sentence of its own and
    adds the full stop itself. A field that arrived as a whole sentence would
    read as two sentences run together in the prompt that is actually sent,
    so the shape is asked for here rather than repaired there."""
    system = build_condense_system()

    assert "Halbsatz" in system
    assert "ohne Punkt" in system


def test_the_prompt_allows_an_empty_contradiction():
    """The evidence clause again: material without a real contradiction must
    not have one invented for it. An invented tension source would be worse
    than none, because it would be rendered as if it were true."""
    system = build_condense_system()

    assert "leer" in system.lower()


def test_the_form_section_still_governs_only_the_german_wall_sentence():
    """Birk's explicit decision (2026-08-29): the wall stays 16 words, one
    main clause, no comma — measured against legibility in passing, not
    against image quality. The longer text is a SECOND field, never a
    loosening of this one."""
    system = build_condense_system()

    form = system.split("FORM:")[1].split("\n\n")[0]
    assert str(SENTENCE_MAX_WORDS) in form
    assert "Hauptsatz" in form
    assert "OHNE" in form and "Komma" in form
    # The image description's length must not have leaked into FORM.
    assert "50" not in form and "80" not in form


def test_the_prompt_asks_for_mood_and_tension():
    """Spec §5.3: both are part of the record, produced in the SAME call.
    `tension` is explicitly NOT absurdity — see kg2/imagegen.py."""
    system = build_condense_system()

    assert "mood" in system.lower()
    assert "tension" in system.lower()


# -- the material -----------------------------------------------------------


def test_the_user_message_carries_the_weighted_material():
    """🔴 Eigenes, reicheres Material seit 2026-09-01 -- und das gehoert zur
    Aussage. `material()` hat genau zwei Begriffe, und bei so wenig Material
    nimmt `select_required` BEIDE in die Pflichtliste. Seit dem Fix vom
    2026-09-01 steht ein Pflichtbegriff nicht mehr zusaetzlich unter den
    Randnotizen ("Detail und Beiwerk, nicht Thema") -- der Block waere hier
    also leer, und der Test pruefte nur noch den alten Widerspruch.
    """
    nodes = [
        {"id": f"p{i}", "type": "person", "portrait": None, "created_at": float(i),
         "hidden": False, "x": None, "y": None}
        for i in range(8)
    ] + [
        {"id": "t1", "type": "term", "label": "Weiterbauen im Bestand", "mentions": 8,
         "created_at": 2.0, "hidden": False, "x": None, "y": None},
    ] + [
        {"id": f"t{i}", "type": "term", "label": f"Randbegriff {i}", "mentions": 1,
         "created_at": float(i), "hidden": False, "x": None, "y": None}
        for i in range(2, 10)
    ]
    edges = [{"id": f"e{i}", "source": f"p{i}", "target": "t1"} for i in range(8)]
    edges += [{"id": f"ex{i}", "source": f"p{i % 8}", "target": f"t{i}"}
              for i in range(2, 10)]
    reich = build_material({
        "version": 1, "generated_at": 1000.0, "min_mentions": 1,
        "nodes": nodes, "edges": edges, "quotes": [],
    })

    prompt = build_condense_prompt(reich)

    assert "Weiterbauen im Bestand" in prompt
    assert "Randnotizen" in prompt


def test_the_user_message_has_no_leitfrage_line():
    prompt = build_condense_prompt(material())

    assert "Leitfrage" not in prompt


def test_the_user_message_omits_quotes_by_default():
    prompt = build_condense_prompt(material())

    assert "Wir bauen zu viel Neues." not in prompt


def test_the_user_message_includes_quotes_when_asked():
    prompt = build_condense_prompt(material(), include_quotes=True)

    assert "Wir bauen zu viel Neues." in prompt


def test_the_user_message_accepts_calibration_overrides_for_the_gliding_formula():
    """`sim.dream_calibrate terms` needs to try other N/X combinations without
    duplicating build_condense_prompt. `recent_terms=0` isolates this from the
    independent recency block (kg2/weighting.py), which draws from marginal
    terms regardless of the single-mention budget — that overlap is by design,
    not something this test is about."""
    generous = build_condense_prompt(
        material(), single_mention_budget=20, shared_terms_saturation=25, recent_terms=0
    )
    strict = build_condense_prompt(
        material(), single_mention_budget=0, shared_terms_saturation=25, recent_terms=0
    )

    assert "Sickerfähige Beläge" in generous
    assert "Sickerfähige Beläge" not in strict


# -- the call ---------------------------------------------------------------


def test_condense_returns_the_sentence_and_the_full_prompt_record():
    """Spec §5.3: the record is the point. A sentence with no prompt beside it
    cannot be explained after the festival."""
    llm = FakeLLM(sentence="Der Beton träumt vom Wald.")

    result = condense(llm, material())

    assert isinstance(result, CondenseResult)
    assert result.sentence == "Der Beton träumt vom Wald."
    # The persisted prompt is system AND user — either alone is unreproducible.
    assert "Traum" in result.prompt
    assert "Weiterbauen im Bestand" in result.prompt


def test_condense_returns_the_english_sentence_mood_and_tension():
    llm = FakeLLM(
        sentence="Der Beton träumt vom Wald.",
        sentence_en="The concrete dreams of the forest.",
        mood=4,
        tension=2,
    )

    result = condense(llm, material())

    assert result.sentence_en == "The concrete dreams of the forest."
    assert result.mood == 4
    assert result.tension == 2


def test_condense_strips_surrounding_whitespace_and_stray_quotes():
    """Tool 1 hit exactly this: the model echoes its own example's quotation
    marks back (`kg/merging.py`, commit 1016421). A leading „ would then be
    rendered on the wall as part of the sentence."""
    for raw in ('  Der Beton träumt.  ', '„Der Beton träumt."', '"Der Beton träumt."'):
        result = condense(FakeLLM(raw), material())
        assert result.sentence == "Der Beton träumt."


def test_condense_raises_on_an_empty_sentence():
    """An empty sentence is a failed dream, not a dream with nothing to say —
    the cycle must mark it failed and leave the previous image up (spec §8)."""
    with pytest.raises(ValueError):
        condense(FakeLLM("   "), material())


def test_condense_lets_the_llm_error_propagate():
    """The cycle owns the failure policy (spec §8), not this module. Swallowing
    it here would produce a dream with no sentence and no error recorded."""
    with pytest.raises(RuntimeError):
        condense(AngryLLM(), material())


def test_an_overlong_sentence_is_kept_and_logged_not_rejected(caplog):
    """A worse sentence beats a blank change on the wall (spec §8)."""
    long = " ".join(["Wort"] * 30)

    with caplog.at_level("WARNING"):
        result = condense(FakeLLM(long), material())

    assert result.sentence == long
    assert "30" in caplog.text


def test_a_sentence_with_a_comma_is_kept_and_logged_not_rejected(caplog):
    with caplog.at_level("WARNING"):
        result = condense(FakeLLM("Der Beton, der träumt, wacht auf."), material())

    assert result.sentence == "Der Beton, der träumt, wacht auf."
    assert "comma" in caplog.text.lower() or "Komma" in caplog.text


def test_a_short_comma_free_sentence_is_not_logged(caplog):
    with caplog.at_level("WARNING"):
        condense(FakeLLM("Der Beton träumt vom Wald."), material())

    assert caplog.text == ""


# -- truncation ---------------------------------------------------------------


def test_condense_raises_on_a_sentence_with_an_embedded_newline():
    """The real incident (out/calibrate-terms.txt): 'Unsere Klebepunkte ...
    unter zugewachsenen G\\ndie' — a raw control character mid-word where
    generation broke and something else got spliced in. Spec §5.1's FORM
    requires genau ein Hauptsatz on one line; a sentence cannot legitimately
    contain a newline, unlike a merely missing final period, so this is
    treated as a failed dream (spec §8), not logged and kept."""
    broken = (
        "Unsere Klebepunkte versickern pro forma in Tiefgaragen unter "
        "zugewachsenen G\ndie"
    )

    with pytest.raises(ValueError):
        condense(FakeLLM(broken), material())


def test_condense_raises_on_an_english_sentence_with_an_embedded_newline():
    with pytest.raises(ValueError):
        condense(FakeLLM(sentence_en="The dots sink into G\ndie garage."), material())


def test_a_normal_sentence_without_a_final_period_is_not_treated_as_broken():
    """The important test: a real, complete sentence that merely lacks a
    trailing period (accepted and common per the calibration output) must
    NOT be rejected by the same check that catches truncation."""
    result = condense(FakeLLM("Der Beton träumt vom Wald ohne Punkt"), material())

    assert result.sentence == "Der Beton träumt vom Wald ohne Punkt"


# -- mood / tension clamping -------------------------------------------------


def test_condense_clamps_mood_and_tension_above_the_range(caplog):
    with caplog.at_level("WARNING"):
        result = condense(FakeLLM(mood=9, tension=42), material())

    assert result.mood == 5
    assert result.tension == 5


def test_condense_clamps_mood_and_tension_below_the_range(caplog):
    with caplog.at_level("WARNING"):
        result = condense(FakeLLM(mood=0, tension=-3), material())

    assert result.mood == 1
    assert result.tension == 1


def test_condense_leaves_in_range_mood_and_tension_untouched():
    result = condense(FakeLLM(mood=2, tension=4), material())

    assert result.mood == 2
    assert result.tension == 4


# -- English fallback ---------------------------------------------------------


def test_condense_falls_back_to_the_german_sentence_when_english_is_missing(caplog):
    """A missing image motif would be worse than an English caption that is
    actually the German sentence (kg2/imagegen.py's stage 2 needs SOMETHING)."""
    with caplog.at_level("WARNING"):
        result = condense(FakeLLM(sentence="Der Beton träumt.", sentence_en=""), material())

    assert result.sentence_en == "Der Beton träumt."
    assert caplog.text


def test_condense_falls_back_to_german_when_english_is_only_whitespace(caplog):
    with caplog.at_level("WARNING"):
        result = condense(FakeLLM(sentence="Der Beton träumt.", sentence_en="   "), material())

    assert result.sentence_en == "Der Beton träumt."


# -- image description and tension source (2026-08-29) -----------------------


def test_condense_returns_the_image_description_and_the_tension_source():
    """Both are new fields from the SAME call as the sentence (spec §5.3 —
    everything needed to explain a dream is recorded together)."""
    llm = FakeLLM(
        image_description="A concrete slab leans against a birch trunk.",
        tension_source="restoring a façade while billing it as new construction",
    )

    result = condense(llm, material())

    assert result.image_description == "A concrete slab leans against a birch trunk."
    assert result.tension_source == "restoring a façade while billing it as new construction"


def test_an_empty_image_description_is_logged_and_left_empty_not_raised():
    """Same policy as sentence_en: a missing field degrades the image, it
    does not fail the dream (spec §8). Stage 2 falls back on its own
    (kg2/imagegen.py::build_image_prompt), so nothing is substituted here."""
    result = condense(FakeLLM(image_description=""), material())

    assert result.image_description == ""
    assert result.sentence_en  # ...and the fallback stage 2 will use is there


def test_an_empty_image_description_warns_because_it_should_not_happen(caplog):
    with caplog.at_level("WARNING"):
        condense(FakeLLM(image_description="   "), material())

    assert "image description" in caplog.text


def test_a_truncated_image_description_is_dropped_and_logged_not_raised(caplog):
    """`_is_truncated` is applied here too, but its verdict costs only the
    richer prompt — falling back to the literal translation is far better
    than letting a spliced-in fragment reach the image model, and better
    still than losing the dream."""
    with caplog.at_level("WARNING"):
        result = condense(
            FakeLLM(image_description="A slab of concrete stands in a G\ndie clearing."),
            material(),
        )

    assert result.image_description == ""
    assert result.sentence == "Der Beton träumt vom Wald."  # the dream survives
    assert "truncated" in caplog.text


def test_an_empty_tension_source_is_silent_because_it_is_a_legitimate_answer(caplog):
    """Material without a real contradiction must not have one invented for
    it — the prompt asks for the field to be left empty in that case. A
    warning here would train whoever reads the log to ignore the line."""
    with caplog.at_level("WARNING"):
        result = condense(FakeLLM(tension_source=""), material())

    assert result.tension_source == ""
    assert caplog.text == ""


def test_a_whitespace_only_tension_source_is_also_silent(caplog):
    with caplog.at_level("WARNING"):
        result = condense(FakeLLM(tension_source="   "), material())

    assert result.tension_source == ""
    assert caplog.text == ""


def test_a_truncated_tension_source_is_dropped_and_logged_not_raised(caplog):
    with caplog.at_level("WARNING"):
        result = condense(FakeLLM(tension_source="renovating a façade while\nbill"), material())

    assert result.tension_source == ""
    assert result.sentence == "Der Beton träumt vom Wald."
    assert "tension source" in caplog.text


def test_the_image_description_is_stripped_of_wrapping_quotes():
    """Same `_clean` as the sentence: the prompt's own examples are quoted
    and a model echoes the quoting back (kg/merging.py, commit 1016421)."""
    result = condense(FakeLLM(image_description='"A slab of concrete stands alone."'), material())

    assert result.image_description == "A slab of concrete stands alone."


def test_the_output_model_has_exactly_the_six_fields():
    """Anything else in the schema is something the model can spend effort on
    instead of the sentence. Six since 2026-08-29: the two new ones carry the
    image channel, which the 16-word wall sentence cannot (kg2/imagegen.py)."""
    assert set(DreamSentence.model_fields) == {
        "sentence", "sentence_en", "image_description", "tension_source", "mood", "tension",
    }


# -- against the real thing -------------------------------------------------


def test_the_real_replay_graph_produces_a_workable_prompt(real_graph):
    prompt = build_condense_prompt(build_material(real_graph))

    assert "Scheinbeteiligung pro forma" in prompt
    assert "Leitfrage" not in prompt


def test_clean_leaves_a_sentence_with_internal_quotations_alone():
    """Stripping the outermost pair of a sentence that quotes something INSIDE
    itself leaves a stray mark stranded mid-sentence — worse than doing
    nothing, and on the wall rather than in a log."""
    both_ends_quoted = "„Zuhause\" bleibt ein Wort, das der Beton leise 'stumm' nennt"

    result = condense(FakeLLM(both_ends_quoted), material())

    assert result.sentence == both_ends_quoted


# --- Der Wandsatz haelt seine Form nicht ein (Birk, 2026-09-02) -------------
#
# Gemessen am Abend des ersten Ausstellungstags, vier Laeufe auf dem echten
# Graphen: 4 von 4 Saetzen verletzten die Form. 21, 47, 45 und 55 Woerter
# gegen ein Maximum von 16; einer davon auf ENGLISCH, einer eine
# Verweigerung („Eine einzige Satz-Antwort ist nicht moeglich; die
# Instruktion verlangt fuenf Teile ..."). Der echte Traum d1 hatte 26.
#
# Bis dahin wurde das nur protokolliert: „Logged, never rejected" -- ein
# abgelehnter Satz waere eine leere Aenderung an der Wand, und Spec §8 sagt,
# man solle Unvollkommenheit aussitzen statt anzuhalten. Das bleibt richtig.
# Zwischen ablehnen und hinnehmen liegt aber ein dritter Weg, den kg.llm bei
# kaputtem JSON laengst geht: noch einmal fragen. Der Satz steht als
# Bildunterschrift auf einem grossen Schirm und soll im Vorbeigehen in einem
# Blick erfassbar sein; 55 Woerter sind das nicht.


def _antwort(satz, beschreibung="A wall of clay."):
    return {
        "sentence": satz,
        "sentence_en": "A man kneads clay.",
        "image_description": beschreibung,
        "tension_source": "hands against machines",
        "mood": 3,
        "tension": 3,
    }


class _LLMMitFolge:
    """Liefert die vorgegebenen Antworten der Reihe nach."""

    def __init__(self, *antworten):
        self.antworten = list(antworten)
        self.aufrufe = 0

    def parse(self, system, user, output_model):
        self.aufrufe += 1
        d = self.antworten[min(self.aufrufe - 1, len(self.antworten) - 1)]
        return output_model.model_validate(d)


def test_ein_zu_langer_wandsatz_wird_noch_einmal_erfragt():
    lang = " ".join(f"Wort{i}" for i in range(40))
    kurz = "Ein Mann knetet Lehm an einer halbfertigen Wand aus Stampflehm"
    llm = _LLMMitFolge(_antwort(lang), _antwort(kurz))

    r = condense(llm, material())

    assert r.sentence == kurz
    assert llm.aufrufe == 2, "es muss genau einmal nachgefragt worden sein"


def test_ein_satz_mit_komma_wird_noch_einmal_erfragt():
    mit = "Ein Mann knetet Lehm, waehrend ein Kran ein Fass hebt"
    ohne = "Ein Mann knetet Lehm an einer halbfertigen Wand"
    llm = _LLMMitFolge(_antwort(mit), _antwort(ohne))

    assert condense(llm, material()).sentence == ohne
    assert llm.aufrufe == 2


def test_ein_richtiger_satz_kostet_keinen_zweiten_aufruf():
    kurz = "Ein Mann knetet Lehm an einer halbfertigen Wand"
    llm = _LLMMitFolge(_antwort(kurz))

    assert condense(llm, material()).sentence == kurz
    assert llm.aufrufe == 1, "ohne Formfehler darf nicht nachgefragt werden"


def test_bleibt_die_form_falsch_wird_der_traum_trotzdem_geliefert():
    """Spec §8: aussitzen, nicht anhalten. Ein leerer Schirm ist schlimmer als
    ein zu langer Satz — die Wiederholung ist eine Chance, keine Bedingung."""
    lang = " ".join(f"Wort{i}" for i in range(40))
    llm = _LLMMitFolge(_antwort(lang))

    r = condense(llm, material())

    assert r.sentence == lang, "der Traum muss trotzdem herauskommen"
    assert llm.aufrufe <= 3, "aber nicht endlos versuchen"


def test_der_beste_versuch_gewinnt_nicht_der_letzte():
    """Wird auch der zweite Versuch nichts, zaehlt der KUERZERE — sonst macht
    eine Wiederholung den Satz schlimmer, statt ihn zu retten."""
    mittel = " ".join(f"Wort{i}" for i in range(20))
    sehr_lang = " ".join(f"Wort{i}" for i in range(60))
    llm = _LLMMitFolge(_antwort(mittel), _antwort(sehr_lang), _antwort(sehr_lang))

    assert condense(llm, material()).sentence == mittel


# --- Das Gedaechtnis gegen die Wiederholung (Birk, 2026-09-02) ---------------


def test_die_zuletzt_gezeigten_bilder_stehen_im_prompt():
    """🔴 Birk am Ausstellungstag: „Ich habe das Gefühl, dass zum Beispiel Lehm
    in jedem Bild vorkam. Wurde das wirklich in jedem Interview genannt?"

    Gemessen an den ersten zehn Träumen: „Lehmbau" wurde von genau ZWEI
    Menschen genannt, stand aber in NEUN von zehn Prompts — in dreien als
    Pflichtbegriff, in sechs weiteren nur als Zeile „2× Lehmbau" in der Liste
    der geteilten Begriffe. Im Bild erschien es sieben Mal.

    Die Ursache ist keine Panne, sondern eine Anweisung: „BREITE, NICHT NUR DIE
    SPITZE — nimm auch aus der Mitte und dem unteren Teil der Liste, was das
    Bild KONKRET macht." Lehm ist das konkreteste Material der ganzen Liste.
    Das Modell tut also genau das Richtige und kommt jedes Mal zum selben
    Ergebnis, weil jeder Traum für sich entsteht: Es weiß nicht, was zehn
    Minuten vorher an der Wand hing.

    Deshalb bekommt es das jetzt gesagt. Kein neuer Mechanismus, nur die
    fehlende Information.
    """
    from kg2.condense import build_condense_prompt

    mat = material()
    prompt = build_condense_prompt(
        mat,
        zuletzt_gezeigt=["Kinder pressen Lehm gegen Bretter an einer Wand"],
    )
    assert "Kinder pressen Lehm gegen Bretter an einer Wand" in prompt, prompt[-2000:]
    assert "zuletzt" in prompt.lower()


def test_ohne_vorgeschichte_bleibt_der_prompt_wie_er_war():
    """Der erste Traum eines Tages hat keine Vorgeschichte — dann darf auch
    kein leerer Block dastehen, der so aussieht, als sei etwas verlorengegangen."""
    from kg2.condense import build_condense_prompt

    mat = material()
    ohne = build_condense_prompt(mat)
    leer = build_condense_prompt(mat, zuletzt_gezeigt=[])
    assert ohne == leer
    assert "Zuletzt gezeigt" not in ohne
