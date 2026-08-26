"""Spec §5.1 — the sentence. What the prompt must say, and what it must not."""

from __future__ import annotations

import pytest

from kg2.condense import (
    CondenseResult,
    DreamSentence,
    build_condense_prompt,
    build_condense_system,
    condense,
)
from kg2.weighting import build_material

QUESTION = "Wie leben und bauen wir in zehn Jahren?"


class FakeLLM:
    """Records what it was asked, answers what it was told to."""

    def __init__(self, sentence="Der Beton träumt von Wald, und der Wald schickt Rechnungen."):
        self.sentence = sentence
        self.calls: list[tuple[str, str]] = []

    def parse(self, system, user, output_model):
        self.calls.append((system, user))
        return output_model(sentence=self.sentence)


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
    system = build_condense_system(QUESTION, contradiction=False)

    assert "Traum" in system
    assert "Verdichtung" in system
    assert "unmöglich" in system
    # The failure mode named by name, so a later edit cannot lose it silently.
    assert "Zusammenfassung" in system
    assert "Illustration" in system


def test_the_contradiction_instruction_is_present_above_the_threshold():
    """Spec §5.1: hold the two most distant positions in one image WITHOUT
    resolving them. This is the instruction that prevents the consensus
    brochure."""
    system = build_condense_system(QUESTION, contradiction=True)

    assert "Widerspruch" in system
    assert "nicht auf" in system  # „löse ihn nicht auf"
    assert "Kompromiss" in system


def test_the_contradiction_instruction_is_absent_below_the_threshold():
    """Spec §5.1: with three interviews the model would invent an opposition."""
    system = build_condense_system(QUESTION, contradiction=False)

    assert "Widerspruch" not in system
    assert "Kompromiss" not in system


def test_the_two_systems_differ_only_by_the_contradiction_block():
    """One prompt with an optional block, not two prompts that can drift."""
    without = build_condense_system(QUESTION, contradiction=False)
    with_it = build_condense_system(QUESTION, contradiction=True)

    assert with_it.startswith(without.rstrip())
    assert len(with_it) > len(without)


def test_the_guiding_question_is_in_the_system_prompt():
    system = build_condense_system("Wem gehört die Stadt in zehn Jahren?", contradiction=False)

    assert "Wem gehört die Stadt in zehn Jahren?" in system


def test_the_prompt_forbids_naming_anyone():
    """Spec §12: the dream is collective; quotes feed it, attribution does not.
    Also the quieter answer to „where do my statements end up"."""
    system = build_condense_system(QUESTION, contradiction=True)

    assert "keine Namen" in system.lower() or "nenne keine namen" in system.lower()


def test_the_prompt_asks_for_one_german_sentence_of_the_right_length():
    system = build_condense_system(QUESTION, contradiction=False)

    assert "einen einzigen Satz" in system
    assert "20" in system and "40" in system
    assert "Deutsch" in system


# -- the material -----------------------------------------------------------


def test_the_user_message_carries_the_weighted_material():
    prompt = build_condense_prompt(material(), QUESTION)

    assert "Weiterbauen im Bestand" in prompt
    assert "Sickerfähige Beläge" in prompt
    assert "Wir bauen zu viel Neues." in prompt
    assert "Randnotizen" in prompt


def test_the_user_message_repeats_the_question_so_the_answer_stays_anchored():
    prompt = build_condense_prompt(material(), QUESTION)

    assert QUESTION in prompt


# -- the call ---------------------------------------------------------------


def test_condense_returns_the_sentence_and_the_full_prompt_record():
    """Spec §5.3: the record is the point. A sentence with no prompt beside it
    cannot be explained after the festival."""
    llm = FakeLLM("Der Beton träumt von Wald.")

    result = condense(llm, material(), QUESTION, contradiction=True)

    assert isinstance(result, CondenseResult)
    assert result.sentence == "Der Beton träumt von Wald."
    # The persisted prompt is system AND user — either alone is unreproducible.
    assert "Traum" in result.prompt
    assert "Weiterbauen im Bestand" in result.prompt


def test_condense_passes_the_contradiction_flag_through_to_the_system_prompt():
    llm = FakeLLM()

    condense(llm, material(), QUESTION, contradiction=True)
    system_with, _ = llm.calls[0]
    condense(llm, material(), QUESTION, contradiction=False)
    system_without, _ = llm.calls[1]

    assert "Widerspruch" in system_with
    assert "Widerspruch" not in system_without


def test_condense_strips_surrounding_whitespace_and_stray_quotes():
    """Tool 1 hit exactly this: the model echoes its own example's quotation
    marks back (`kg/merging.py`, commit 1016421). A leading „ would then be
    rendered on the wall as part of the sentence."""
    for raw in ('  Der Beton träumt.  ', '„Der Beton träumt."', '"Der Beton träumt."'):
        result = condense(FakeLLM(raw), material(), QUESTION, contradiction=False)
        assert result.sentence == "Der Beton träumt."


def test_condense_raises_on_an_empty_sentence():
    """An empty sentence is a failed dream, not a dream with nothing to say —
    the cycle must mark it failed and leave the previous image up (spec §8)."""
    with pytest.raises(ValueError):
        condense(FakeLLM("   "), material(), QUESTION, contradiction=False)


def test_condense_lets_the_llm_error_propagate():
    """The cycle owns the failure policy (spec §8), not this module. Swallowing
    it here would produce a dream with no sentence and no error recorded."""
    with pytest.raises(RuntimeError):
        condense(AngryLLM(), material(), QUESTION, contradiction=False)


def test_an_overlong_sentence_is_kept_and_logged_not_rejected(caplog):
    """A worse sentence beats a blank change on the wall (spec §8)."""
    long = " ".join(["Wort"] * 60)

    with caplog.at_level("WARNING"):
        result = condense(FakeLLM(long), material(), QUESTION, contradiction=False)

    assert result.sentence == long
    assert "60" in caplog.text


def test_the_output_model_has_exactly_one_field():
    """Anything else in the schema is something the model can spend effort on
    instead of the sentence."""
    assert set(DreamSentence.model_fields) == {"sentence"}


# -- against the real thing -------------------------------------------------


def test_the_real_replay_graph_produces_a_workable_prompt(real_graph):
    prompt = build_condense_prompt(build_material(real_graph), QUESTION)

    assert "Scheinbeteiligung pro forma" in prompt
    assert "60 Menschen" in prompt
    assert QUESTION in prompt
