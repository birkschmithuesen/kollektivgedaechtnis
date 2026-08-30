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

## What one call returns, and why it is four texts and not one (2026-08-29)

The wall gets ONE of these; stage 2 gets the others. The split exists because
the two channels are measured against different things, and a single text
cannot serve both:

* `sentence` — the wall. Exactly as before: one German main clause, at most
  `SENTENCE_MAX_WORDS` words, no comma. Measured against legibility in
  passing (36 words = 4 lines = ~11 s), and explicitly NOT touched by any of
  what follows. The FORM section of the prompt applies to this field alone.
* `sentence_en` — the literal English counterpart of that same wall sentence.
  Kept and persisted because it is the honest translation of what a visitor
  read; it is no longer stage 2's motif on its own, only a fallback for it.
* `image_description` — the motif for stage 2: 3-4 sentences of English prose
  on the SAME scene, at length. Google's guidance for this exact image model
  is explicit that a narrative description beats a terse line
  (`ai.google.dev/gemini-api/docs/interactions/image-generation`), and the
  16-word wall sentence gave the model almost nothing to work with (Birk,
  2026-08-29, on five rendered images in `out/tagesverlauf/`). It names
  materials, surfaces, light ON the objects, spatial arrangement and scale —
  and deliberately NOT the overall mood/lighting or any camera/style
  instruction, because stage 2 already fixes those in its own blocks and two
  sources for one instruction fight each other.
* `tension_source` — one short English clause naming WHICH two things in the
  material contradict each other. Stage 2's `TENSION_COHERENCE` wording is
  intentionally contentless (it sets the DEGREE of coherence, not its
  subject), so without this the image model invented a contradiction of its
  own: handed „Roboter sprühen Beton auf eine unsexy Bestandsfassade und
  berechnen ihr Honorar nach Neubau" it painted one clean and one dirty robot
  arm, having no way to know the real friction was „renovating" against
  „billing as new build". This field may legitimately be EMPTY — material
  without a real contradiction must not have one invented for it, which is
  the same evidence clause as above.

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
    RECENT_TERMS,
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
Satzform. Sie ist die ehrliche englische Entsprechung des Wandsatzes und wird \
mit ihm zusammen aufbewahrt.

BILDBESCHREIBUNG: Liefere zusätzlich eine ausführlichere englische \
Beschreibung DERSELBEN Szene, die auch der deutsche Satz zeigt — keine zweite, \
andere Szene daneben. Der Wandsatz und diese Beschreibung sind dasselbe Bild, \
einmal knapp und einmal ausführlich. Zusammenhängende Prosa, drei bis vier \
Sätze, ungefähr 50 bis 80 Wörter. Benenne, was konkret zu sehen ist: \
Materialien, Oberflächen, wie das Licht auf den Dingen liegt, wie die Dinge im \
Raum zueinander stehen, wie groß sie im Verhältnis zueinander sind. Diese \
Fassung ist das Bildmotiv für Stufe 2.

SCHRIFT IM BILD: SO WENIG WIE MÖGLICH, UND WENN, DANN MIT WORTLAUT. Der \
Regelfall ist ein Bild OHNE Schrift. Zeige, was gemeint ist, an der FORM der \
Dinge: Werkzeug, Maschinen, Absperrungen, Stempel und Siegel als Gegenstand, \
Menschen und was sie mit den Händen tun, offene und verschlossene Türen, was \
neu und was alt ist. Zwei Gründe, und beide zählen: Der Wandsatz ist das \
Textstück dieser Arbeit, ein zweiter Text im Bild tritt gegen ihn an — und \
Bildmodelle setzen Schrift unzuverlässig, verdrehte Buchstaben stehen dann in \
hyperrealistischer Schärfe an der Wand.

AUSNAHME: Wenn ein beschrifteter Gegenstand der EINZIGE Weg ist, den \
Widerspruch sichtbar zu machen, nimm ihn — aber genau einen, und sage dazu, \
was daraufsteht: als deutschen Wortlaut in Anführungszeichen, mit ausdrücklich \
benannter Sprache. Ohne beides erfindet das Bildmodell einen englischen Text, \
und das Bild hängt in einer deutschen Ausstellung. Kurz halten: ein bis vier \
Wörter oder eine Zahl, mehr wird im Bild unleserlich. Der übrige \
Beschreibungstext bleibt englisch.
- Regelfall (ohne Schrift, Form allein): „a surveyor's tripod and levelling \
staff set up where the old wall is being patched by hand\"
- Falsch (Schrift ohne Wortlaut, Modell erfindet englischen Text): „a printed \
fee schedule board wired to the scaffolding\"
- Ausnahme, richtig gemacht: „a printed fee board wired to the scaffolding, \
the German text reading „NEUBAU 3.200 €/m²\"\"
- Ausnahme, richtig gemacht: „a stamped site plan behind glass, the red German \
stamp reading „GENEHMIGT\"\"

Was du nicht belegen kannst, beschriftest du auch nicht: Erfinde keine Zahlen \
und keine Behauptungen, die nicht im Material stehen. Im Zweifel nenne den \
Gegenstand ohne Beschriftung.

BEIDE SEITEN INS BILD: Wenn das Material sowohl Zuversichtliches als auch \
Beunruhigendes hergibt, müssen BEIDE in der Bildbeschreibung vorkommen, und \
zwar gleich groß und gleich konkret — die zuversichtliche Seite nicht als \
Randnotiz hinter dem Verfall. Zeige den Zustand der Dinge so, wie das Material \
ihn hergibt: Was intakt, benutzt, gepflegt oder neu gemacht ist, gehört \
genauso hinein wie was bröckelt, leersteht oder versiegelt ist. Ein Bild, das \
nur den Verfall zeigt, obwohl die Menschen auch von Gelingendem gesprochen \
haben, gibt das Material falsch wieder — und eines, das nur Gelingendes zeigt, \
ebenso.

EIN EINZIGER ORT, EINE EINZIGE AUFNAHME: Die beiden Seiten stehen an DEMSELBEN \
Ort, in DERSELBEN Aufnahme, ineinander verschränkt — nicht als zwei Hälften \
nebeneinander. Beschreibe einen zusammenhängenden Raum, den eine einzige \
Kamera von einem einzigen Standpunkt aus erfasst: das Gelingende und das \
Bröckelnde an derselben Wand, im selben Hof, am selben Haus. Verwende keine \
Wendungen, die den Bildausschnitt teilen („links … rechts\", „auf der einen \
Seite … auf der anderen\", „daneben\", „gegenüber\", „im Gegensatz dazu\"), \
sondern solche, die den Raum zusammenhalten („an derselben Wand\", „durch \
dieselbe Tür\", „hinter\", „darüber\", „mitten in\").
- Schlecht (zwei Bilder in einem): „a freshly rendered house on the left, and \
boarded-up shopfronts on the right\"
- Gut (ein Ort): „a single façade where new render stops halfway and the old \
crumbling plaster carries on beneath it\"

WAS NICHT IN DIE BILDBESCHREIBUNG GEHÖRT: keine Angabe zur Stimmung und keine \
zur Lichtstimmung des ganzen Bildes (warm, kalt, düster, hoffnungsvoll) und \
keine Kamera-, Objektiv-, Film- oder Stilangabe. Beides steht in Stufe 2 \
bereits fest und würde sich mit deiner Fassung schlagen. Das Licht, das du \
beschreibst, ist das Licht AN EINEM DING — ein Glanz auf nassem Beton, ein \
Schatten unter einer Kante —, nicht die Stimmung des Bildes. Auch hier gilt \
die Belegbarkeit: nur was sich auf die gelieferten Begriffe stützt.

WIDERSPRUCH: Liefere zusätzlich einen kurzen englischen Halbsatz, der den \
Widerspruch aus dem Material als etwas SICHTBARES benennt. Er wird in Stufe 2 \
hinter einen einleitenden Satz gehängt und muss deshalb ein Halbsatz bleiben, \
kein ganzer Satz und ohne Punkt am Ende.

WELCHE ZWEI HÄLFTEN: Suche im Material die STÄRKSTE ZUVERSICHTLICHE und die \
STÄRKSTE BEUNRUHIGTE Aussage und stelle beide nebeneinander. Nicht irgendein \
Gegensatzpaar, sondern die beiden äußeren Enden dessen, was die Menschen \
tatsächlich gesagt haben — das ist der Widerspruch, der den Tag trägt. Die \
zuversichtliche Hälfte muss dabei genauso konkret und genauso groß im Bild \
sein wie die beunruhigte; ein Bild, in dem nur der Verfall zu sehen ist und \
die Hoffnung als Randnotiz, gibt das Material falsch wieder. Findet sich zu \
einer der beiden Seiten nichts Belegbares, lass das Feld lieber leer, als die \
fehlende Seite zu erfinden.

ENTSCHEIDEND: Ein Bildmodell kann keinen Vorgang und keine Absicht zeigen, nur \
Dinge im Raum. Nenne deshalb zwei GEGENSTÄNDE, ORTE ODER MENSCHLICHE HANDLUNGEN, \
die man beide gleichzeitig fotografieren könnte, nicht zwei Begriffe oder \
Verfahren. Übersetze den abstrakten Widerspruch in das, woran man ihn sähe.
- Schlecht (unsichtbar): „gathering opinions while decisions are made from \
above\" — „von oben entschieden\" hat kein Aussehen.
- Gut (sichtbar): „a wall of coloured dots stuck on by many hands, and four \
people at a round table behind glass signing the finished plan\"
- Schlecht (unsichtbar): „restoring an existing façade while billing it as new \
construction\"
- Gut (sichtbar): „workers patching old brickwork by hand, beside a printed \
invoice board showing new-build prices\"

AUCH HIER EIN ORT: Die beiden Hälften müssen in derselben Aufnahme stehen \
können, nicht in zwei nebeneinandergestellten. Verbinde sie über den Raum, \
nicht über eine Trennlinie — „hinter der Punktewand hängt der gestempelte \
Plan\" statt „links Punktewand, rechts gestempelter Plan\".

Beide Hälften müssen im Material belegt sein. Wenn dort kein echter Widerspruch \
liegt, lass dieses Feld leer — ein erfundener Widerspruch ist schlechter als \
keiner.

EINSCHÄTZUNG DES MATERIALS. Liefere zusätzlich zwei ganze Zahlen von 1 bis 5:
- mood: Wie blicken die Menschen in diesem Material auf die Zukunft? \
1 = deutlich negativ, 3 = neutral/gemischt, 5 = deutlich positiv.
- tension: Wie weit liegen die Aussagen im Material auseinander? \
1 = einig, 5 = unvereinbar.\
"""


class DreamSentence(BaseModel):
    sentence: str
    sentence_en: str
    image_description: str
    tension_source: str
    mood: int
    tension: int


@dataclass(frozen=True)
class CondenseResult:
    #: System + user, exactly as sent. Persisted per spec §5.3 — a sentence
    #: without the prompt that produced it cannot be explained afterwards.
    prompt: str
    sentence: str
    #: Literal English translation of `sentence` — the honest English
    #: counterpart of what stands on the wall, kept and persisted alongside
    #: it. Since 2026-08-29 it is no longer the image motif on its own:
    #: `image_description` is (see kg2/imagegen.py's module docstring), and
    #: this is only its last-but-one fallback. Falls back to `sentence` if the
    #: model left it empty. Defaulted (not `""`) only so a hand-written test
    #: fake that does not care about translation/mood/tension can still
    #: construct one directly.
    sentence_en: str = ""
    #: The motif fed to stage 2 (kg2/imagegen.py): 3-4 sentences of English
    #: prose describing the SAME scene as `sentence`, only at length — what is
    #: materially visible, not how it is lit or photographed (those two blocks
    #: are stage 2's own and would collide). Empty when the model returned
    #: nothing usable; stage 2 then falls back, and never fails for it.
    image_description: str = ""
    #: One short English clause naming the two concrete things from the
    #: material that contradict each other, e.g. „restoring an existing façade
    #: while billing it as new construction". Legitimately EMPTY: material
    #: without a real contradiction must not have one invented for it (the
    #: same evidence clause that governs the sentence). Stage 2 uses it to
    #: qualify its fixed tension wording — see kg2/imagegen.py.
    tension_source: str = ""
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
    recent_terms: int = RECENT_TERMS,
) -> str:
    """`single_mention_budget`/`shared_terms_saturation`/`recent_terms` only
    exist so `sim.dream_calibrate terms`/`recency` can try other values
    (kg2/weighting.py's gliding formula and recency block) without
    duplicating this function; production always uses the module defaults."""
    rendered = render_material(
        material,
        include_quotes=include_quotes,
        single_mention_budget=single_mention_budget,
        shared_terms_saturation=shared_terms_saturation,
        recent_terms=recent_terms,
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
    recent_terms: int = RECENT_TERMS,
) -> CondenseResult:
    """One call. Errors propagate — `kg2.cycle` owns the failure policy (§8)."""
    system = build_condense_system()
    user = build_condense_prompt(
        material,
        include_quotes=include_quotes,
        single_mention_budget=single_mention_budget,
        shared_terms_saturation=shared_terms_saturation,
        recent_terms=recent_terms,
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

    # `image_description` and `tension_source`, added 2026-08-29, are cleaned
    # the same way but NEVER rejected — unlike `sentence`/`sentence_en` above,
    # a defect here degrades the image rather than destroying the dream, and
    # stage 2's fallback chain (kg2/imagegen.py::build_image_prompt) already
    # covers an empty value. Dropping a broken field to "" therefore costs a
    # richer prompt and nothing else; raising would cost the whole dream, and
    # spec §8 is explicit about riding imperfection out.
    #
    # `_is_truncated` is applied here too even though it was written for the
    # one-clause wall sentence. Its trade-off changes shape but not sign: a
    # multi-sentence description could in principle carry a legitimate
    # newline, so this may occasionally discard a usable description — but the
    # only consequence is a fall back to `sentence_en`, which is the honest
    # translation anyway. A genuinely spliced-in fragment reaching the image
    # model would be the worse outcome of the two.
    image_description = _clean(result.image_description or "")
    if image_description and _is_truncated(image_description):
        log.warning(
            "stage 1 image description looks truncated/corrupted; falling back: %r",
            image_description,
        )
        image_description = ""
    if not image_description:
        log.warning(
            "stage 1 returned no image description; stage 2 falls back to the English sentence"
        )

    # No warning when this one is empty: „no contradiction in the material" is
    # the legitimate, prompted-for answer (the evidence clause forbids
    # inventing one), and warning about it would train whoever reads the log
    # to ignore the line that matters.
    tension_source = _clean(result.tension_source or "")
    if tension_source and _is_truncated(tension_source):
        log.warning(
            "stage 1 tension source looks truncated/corrupted; dropping it: %r", tension_source
        )
        tension_source = ""

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
        image_description=image_description,
        tension_source=tension_source,
        mood=mood,
        tension=tension,
    )
