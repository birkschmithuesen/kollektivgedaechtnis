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
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import BaseModel

from kg2.weighting import Material, render_material

log = logging.getLogger(__name__)

#: Spec §5.1 — long enough to carry the fault line, short enough to read at a
#: glance from standing distance. A miss is logged, never rejected.
WORDS_MIN, WORDS_MAX = 20, 40

_BASE = """\
Du bist das Gedächtnis einer Ausstellungsstation auf dem Festival NEW bauhaus \
2026. Den ganzen Tag über haben Menschen dort Interviews über das Bauen, das \
Wohnen und die Zukunft gegeben. Aus allem, was gesagt wurde, ist ein Graph \
geworden. Jetzt träumst du davon.

TRÄUMEN, NICHT ILLUSTRIEREN. Das Ergebnis ist keine Zusammenfassung, kein \
Bericht, keine Illustration und keine plausible Architekturvision. Es ist \
eine Verdichtung im wörtlichen Sinn: mehrere Aussagen fallen in ein Bild \
zusammen, Dinge \
verschieben sich, das Bild darf unmöglich sein. Eine glatte, schöne \
Zukunftsvision wäre das Gegenteil dieser Aufgabe.

DIE LEITFRAGE, die alle Menschen beantwortet haben:
{question}

Dein Satz ist eine Antwort auf genau diese Frage — aber in der Logik des \
Traums, nicht als Auswertung.

GEWICHTUNG. Was viele Menschen gesagt haben, beherrscht das Bild. Was genau \
eine Person gesagt hat, darf als kleines Detail am Rand vorkommen, nie als \
Thema.

VERBOTEN: Namen von Menschen, Zuschreibungen wie „eine Besucherin sagte", \
Aufzählungen, Doppelpunkte mit Listen, Anführungszeichen, Meta-Sätze über den \
Graphen oder über das Träumen selbst. Nenne keine Namen.

FORM: genau einen einzigen Satz auf Deutsch, ungefähr {words_min} bis \
{words_max} Wörter. Er muss aus einiger Entfernung im Stehen lesbar sein.\
"""

# Appended only above `contradiction_min_persons` (spec §5.1). Below it there
# are no real oppositions in the material and the model would invent one.
_CONTRADICTION = """\

WIDERSPRUCH ALS BAUPRINZIP. Suche in dem Material die zwei am weitesten \
voneinander entfernten Haltungen — die beiden, die einander wirklich \
widersprechen. Beide müssen in deinem einen Satz vorkommen, gleichzeitig, im \
selben Bild. Löse den Widerspruch nicht auf. Kein Kompromiss, kein \
„einerseits/andererseits", kein versöhnlicher Schluss. Der Riss bleibt \
sichtbar; er ist das Motiv.\
"""


class DreamSentence(BaseModel):
    sentence: str


@dataclass(frozen=True)
class CondenseResult:
    #: System + user, exactly as sent. Persisted per spec §5.3 — a sentence
    #: without the prompt that produced it cannot be explained afterwards.
    prompt: str
    sentence: str


def build_condense_system(question: str, contradiction: bool) -> str:
    base = _BASE.format(question=question, words_min=WORDS_MIN, words_max=WORDS_MAX)
    return base + _CONTRADICTION if contradiction else base


def build_condense_prompt(material: Material, question: str) -> str:
    return (
        f"{render_material(material)}\n\n"
        f"--- ENDE MATERIAL ---\n\n"
        f"Leitfrage: {question}\n"
        f"Antworte mit genau einem Satz."
    )


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
    if len(cleaned) > 1 and cleaned[0] in quote_chars and cleaned[-1] in quote_chars:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def condense(llm, material: Material, question: str, contradiction: bool) -> CondenseResult:
    """One call. Errors propagate — `kg2.cycle` owns the failure policy (§8)."""
    system = build_condense_system(question, contradiction)
    user = build_condense_prompt(material, question)

    result = llm.parse(system=system, user=user, output_model=DreamSentence)
    sentence = _clean(result.sentence)
    if not sentence:
        raise ValueError("stage 1 returned an empty sentence")

    words = len(sentence.split())
    if not WORDS_MIN <= words <= WORDS_MAX:
        # Logged, never rejected: a sentence of the wrong length is a worse
        # sentence, but a rejected one is a blank change on the wall, and spec
        # §8's whole stance is to ride imperfection out rather than stop.
        log.warning(
            "stage 1 sentence is %s words, outside the %s-%s target: %r",
            words, WORDS_MIN, WORDS_MAX, sentence,
        )

    return CondenseResult(prompt=f"{system}\n\n--- USER ---\n\n{user}", sentence=sentence)
