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
        mood=3,
        tension=3,
    ):
        self.sentence = sentence
        self.sentence_en = sentence_en
        self.mood = mood
        self.tension = tension
        self.calls: list[tuple[str, str]] = []

    def parse(self, system, user, output_model):
        self.calls.append((system, user))
        return output_model(
            sentence=self.sentence,
            sentence_en=self.sentence_en,
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
    direction the material may not contain — the config's `guiding_question`
    now steers only the on-screen headline (kg2/server.py), not this prompt."""
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
    """The English sentence is the motif fed to stage 2 (spec §5.2); the
    German one stays on the wall. It must be a translation, not a rewrite."""
    system = build_condense_system()

    assert "Englisch" in system
    assert "wörtlich" in system.lower()


def test_the_prompt_asks_for_mood_and_tension():
    """Spec §5.3: both are part of the record, produced in the SAME call.
    `tension` is explicitly NOT absurdity — see kg2/imagegen.py."""
    system = build_condense_system()

    assert "mood" in system.lower()
    assert "tension" in system.lower()


# -- the material -----------------------------------------------------------


def test_the_user_message_carries_the_weighted_material():
    prompt = build_condense_prompt(material())

    assert "Weiterbauen im Bestand" in prompt
    assert "Sickerfähige Beläge" in prompt
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
    duplicating build_condense_prompt."""
    generous = build_condense_prompt(material(), single_mention_budget=20, shared_terms_saturation=25)
    strict = build_condense_prompt(material(), single_mention_budget=0, shared_terms_saturation=25)

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


def test_the_output_model_has_exactly_the_four_fields():
    """Anything else in the schema is something the model can spend effort on
    instead of the sentence."""
    assert set(DreamSentence.model_fields) == {"sentence", "sentence_en", "mood", "tension"}


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
