"""Stage 1: the whole graph becomes one German sentence (spec §5.1).

This is the artistic core, and it is a prompt, so it is worth saying what the
prompt is *for*. The deck promises „das Gedächtnis träumt sein eigenes Bild".
An LLM handed 40 contradictory interviews will, unprompted, average them into a
plausible architectural vision — which is precisely the thing this work
criticises (spec §1). Every paragraph below exists to prevent that.

Two stages rather than one (spec §5), because the sentence is itself a
displayed artefact and must be readable on its own. What appears on screen is
THIS output, not stage 2's prompt: the image prompt is a technical artefact
with style boilerplate, and showing it would put lighting instructions on the
wall (spec §5.2).

Two decisions from 2026-08-28, both replacing an earlier mechanism rather than
adding to it:

* The **contradiction clause** ("hold the two most distant positions, do not
  resolve them") is gone. It forced an „aber/oder" into the sentence and
  invited hallucination; the sentences are absurd enough without it. In its
  place: a plain **evidence clause** — everything in the sentence must trace
  back to a delivered term, nothing invented that is not in the material.
* The **guiding question** no longer enters this prompt at all — neither
  system nor user message. It was a sixth question nobody in the room was
  actually asked (the five in `kg.extraction.GUIDING_QUESTIONS` were), and
  imposing it forced a reading direction the material may not contain — the
  same failure mode as the contradiction clause. `DreamConfig.guiding_question`
  still exists, but from here on it steers only the on-screen headline
  (`kg2/server.py`), never the model.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import BaseModel

from kg2.weighting import (
    SHARED_TERMS_SATURATION,
    SINGLE_MENTION_BUDGET,
    Material,
    render_material,
)

log = logging.getLogger(__name__)

#: Spec §5.1, revised 2026-08-28. Measured against the real frontend (1920x1080,
#: `#sentence` at 3.1vh = 33.5px, docs/operations.md): 36 words made 4 lines and
#: ~11s to read, 50 words made 5. At this limit a sentence is 1-2 lines — a
#: caption that can be read at a glance while walking past, which the old
#: "~20-40 words" target (Spec §5.1's original wording) was not. A miss is
#: logged, never rejected (spec §8).
SENTENCE_MAX_WORDS = 16

_BASE = """\
Du bist das Gedächtnis einer Ausstellungsstation auf dem Festival NEW bauhaus \
2026. Den ganzen Tag über haben Menschen dort Interviews über das Bauen, das \
Wohnen und die Zukunft gegeben. Aus allem, was gesagt wurde, ist ein Graph \
geworden. Jetzt beginnt dein Traum davon.

TRÄUMEN, NICHT ILLUSTRIEREN. Das Ergebnis ist keine Zusammenfassung, kein \
Bericht und keine plausible Architekturvision. Es ist \
eine Verdichtung im wörtlichen Sinn: mehrere Aussagen fallen in ein Bild \
zusammen, Dinge \
verschieben sich, das Bild darf unmöglich sein. Eine glatte, schöne \
Zukunftsvision wäre das Gegenteil dieser Aufgabe.

VERDICHTUNGS-ANWEISUNG: Verdichte die Begriffe zu einer einzigen Aussage über \
das Bauen und Wohnen. Sie darf einen Widerspruch enthalten, wenn einer im \
Material liegt, muss aber keinen erfinden.

BELEGBARKEIT: Alles in deinem Satz muss sich auf die gelieferten Begriffe \
stützen. Erfinde nichts hinzu, was nicht im Material steht.

GEWICHTUNG. Was viele Menschen gesagt haben, beherrscht das Bild. Was genau \
eine Person gesagt hat, darf als kleines Detail am Rand vorkommen, nie als \
Thema.

VERBOTEN: Namen von Menschen, Zuschreibungen wie „eine Besucherin sagte", \
Aufzählungen, Doppelpunkte mit Listen, Anführungszeichen, Meta-Sätze über den \
Graphen oder über das Träumen selbst. Nenne keine Namen.

FORM: genau ein Hauptsatz auf Deutsch, höchstens {max_words} Wörter, OHNE \
Komma, ohne Nebensatz, ohne Gedankenstrich. Ein einziges Bild, kein zweites \
daneben. Er steht als Bildunterschrift auf einem großen Schirm und muss im \
Vorbeigehen in einem Blick erfassbar sein.

ÜBERSETZUNG: Liefere zusätzlich denselben Satz als wörtliche Übersetzung ins \
Englische — keine inhaltliche Veränderung, keine Ausschmückung, dieselbe \
Satzform. Diese englische Fassung ist das Bildmotiv für Stufe 2, nicht der \
deutsche Satz.

EINSCHÄTZUNG DES MATERIALS. Liefere zusätzlich zwei ganze Zahlen von 1 bis 5:
- mood: Wie blicken die Menschen in diesem Material auf die Zukunft? \
1 = deutlich negativ, 3 = neutral/gemischt, 5 = deutlich positiv.
- tension: Wie weit liegen die Aussagen im Material auseinander? \
1 = einig, 5 = unvereinbar.\
"""


class DreamSentence(BaseModel):
    sentence: str
    sentence_en: str
    mood: int
    tension: int


@dataclass(frozen=True)
class CondenseResult:
    #: System + user, exactly as sent. Persisted per spec §5.3 — a sentence
    #: without the prompt that produced it cannot be explained afterwards.
    prompt: str
    sentence: str
    #: Literal English translation of `sentence` — the motif fed to stage 2
    #: (kg2/imagegen.py). Falls back to `sentence` if the model left it empty.
    #: Defaulted (not `""`) only so a hand-written test fake that does not
    #: care about translation/mood/tension can still construct one directly.
    sentence_en: str = ""
    #: 1-5, how the material looks at the future. Clamped after the call.
    mood: int = 3
    #: 1-5, how far the material's statements diverge. NOT absurdity — see
    #: kg2/imagegen.py's module docstring.
    tension: int = 3


def build_condense_system() -> str:
    return _BASE.format(max_words=SENTENCE_MAX_WORDS)


def build_condense_prompt(
    material: Material,
    *,
    include_quotes: bool = False,
    single_mention_budget: int = SINGLE_MENTION_BUDGET,
    shared_terms_saturation: int = SHARED_TERMS_SATURATION,
) -> str:
    """`single_mention_budget`/`shared_terms_saturation` only exist so
    `sim.dream_calibrate terms` can try other N/X values (kg2/weighting.py's
    gliding formula) without duplicating this function; production always
    uses the module defaults."""
    rendered = render_material(
        material,
        include_quotes=include_quotes,
        single_mention_budget=single_mention_budget,
        shared_terms_saturation=shared_terms_saturation,
    )
    return f"{rendered}\n\n--- ENDE MATERIAL ---\n\nAntworte mit genau einem Satz."


def _clean(sentence: str) -> str:
    """Trim, and drop a pair of quotation marks the model wrapped around itself.

    Not hypothetical: Tool 1 hit exactly this in `kg.merging` (commit 1016421),
    because the prompt's own examples are quoted and the model echoes the
    quoting back. Here it would put a stray „ on the wall.
    """
    cleaned = sentence.strip()
    # Any quote character at both ends, not just matched pairs: a model that
    # opens with „ often closes with a plain " rather than the typographic “,
    # and the point is to catch the wrapping, not to validate its typography.
    quote_chars = "„“”«»'‘’\""
    if (
        len(cleaned) > 1
        and cleaned[0] in quote_chars
        and cleaned[-1] in quote_chars
        # ...but only when nothing in between is quoted too. Two unrelated
        # internal quotations would otherwise be mistaken for one wrapper, and
        # stripping them leaves a stray „ stranded mid-sentence — worse than
        # doing nothing, and on the wall rather than in a log.
        and not any(char in quote_chars for char in cleaned[1:-1])
    ):
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _is_truncated(sentence: str) -> bool:
    """A raw control character inside the sentence body — not just missing
    trailing punctuation.

    The real incident this guards against (`docs/operations.md`,
    `out/calibrate-terms.txt`): a stage 1 call returned a syntactically valid
    JSON payload whose `sentence` field was
    ``"...unter zugewachsenen G\\ndie"`` — generation broke mid-word and a
    second, unrelated fragment was spliced in after a literal newline, all
    inside one JSON string. `kg/llm.py`'s `stop_reason == "max_tokens"` check
    catches a cut that leaves invalid JSON behind; it does not catch one that
    (by luck or by a schema-constrained decoder closing the structure early)
    still parses. This is the second line of defence, checked on the
    already-parsed value.

    Deliberately NOT "missing terminal punctuation": Spec §8 requires riding
    out imperfection rather than halting for it, and stage 1 routinely (and
    acceptably, see `out/calibrate-*.txt`) returns a complete sentence with no
    final period — `SENTENCE_MAX_WORDS` and the comma check above already log
    that without rejecting it. A raw control character is categorically
    different: FORM demands "genau ein Hauptsatz" — one clause, one line —
    and no legitimate answer to that instruction contains a newline, tab, or
    carriage return; every real example in `out/calibrate-*.txt` confirms
    that. So this predicate can only fire on a genuinely broken value, never
    on a stylistically rough but complete one, which is what makes it safe to
    reject rather than merely log.
    """
    return any(control in sentence for control in ("\n", "\r", "\t"))


def _clamp_1_to_5(value: int, name: str) -> int:
    """Enforced here, not just in the prompt — same discipline as
    `terms_per_interview` in kg/extraction.py:95: "The cap is enforced here
    too ... must not depend on the model's mood." """
    clamped = max(1, min(5, value))
    if clamped != value:
        log.warning("stage 1 returned %s=%s, outside 1-5; clamped to %s", name, value, clamped)
    return clamped


def condense(
    llm,
    material: Material,
    *,
    include_quotes: bool = False,
    single_mention_budget: int = SINGLE_MENTION_BUDGET,
    shared_terms_saturation: int = SHARED_TERMS_SATURATION,
) -> CondenseResult:
    """One call. Errors propagate — `kg2.cycle` owns the failure policy (§8)."""
    system = build_condense_system()
    user = build_condense_prompt(
        material,
        include_quotes=include_quotes,
        single_mention_budget=single_mention_budget,
        shared_terms_saturation=shared_terms_saturation,
    )

    result = llm.parse(system=system, user=user, output_model=DreamSentence)
    sentence = _clean(result.sentence)
    if not sentence:
        raise ValueError("stage 1 returned an empty sentence")
    if _is_truncated(sentence):
        # Broken, not merely imperfect — see _is_truncated's docstring for
        # why this is rejected while a missing final period is not.
        raise ValueError(f"stage 1 sentence looks truncated/corrupted: {sentence!r}")

    sentence_en = _clean(result.sentence_en or "")
    if _is_truncated(sentence_en):
        raise ValueError(f"stage 1 English sentence looks truncated/corrupted: {sentence_en!r}")
    if not sentence_en:
        # A missing image motif would be worse than reusing the German
        # sentence — stage 2 (kg2/imagegen.py) needs SOMETHING to render.
        log.warning("stage 1 returned no English sentence; falling back to the German one")
        sentence_en = sentence

    mood = _clamp_1_to_5(int(result.mood), "mood")
    tension = _clamp_1_to_5(int(result.tension), "tension")

    words = len(sentence.split())
    has_comma = "," in sentence
    if words > SENTENCE_MAX_WORDS or has_comma:
        # Logged, never rejected: a sentence of the wrong form is a worse
        # sentence, but a rejected one is a blank change on the wall, and spec
        # §8's whole stance is to ride imperfection out rather than stop.
        log.warning(
            "stage 1 sentence is %s words (max %s), comma=%s: %r",
            words, SENTENCE_MAX_WORDS, has_comma, sentence,
        )

    return CondenseResult(
        prompt=f"{system}\n\n--- USER ---\n\n{user}",
        sentence=sentence,
        sentence_en=sentence_en,
        mood=mood,
        tension=tension,
    )
