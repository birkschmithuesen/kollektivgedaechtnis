"""Extraction: find the real end of the interview, then condense it (spec 6.1, 6.3)."""

from __future__ import annotations

from pydantic import BaseModel

# The three guiding questions actually asked at the station. Single source of
# truth: the simulation corpus generator (sim/generate_interviews.py) imports
# these, so the test corpus can never drift away from the extraction prompt
# (spec 9).
#
# **Three, not five, since 2026-08-30 (Birk).** The five drafts were narrowed
# to the three themes the conference programme itself spends most time on —
# counted over all 37 content slots of both days, each assigned to exactly one
# question: future/what should differ 13, who decides 8, system break 7, AI 6,
# nature/restraint 3. The reasoning is that the station should carry on the
# conversation happening in the halls: a theme the conference already handles
# is a reason to pick it up, not to leave it out. „Der Systembruch beginnt
# jetzt" is the motto of day one.
#
# The two dropped questions are NOT deleted — they are kept below as
# ALTERNATIVES, fully worded, for when someone brings the topic up themselves
# or a main question turns out to be barren on site. Full record, including the
# per-question count and the wording history:
# `entities/artesmobiles/projekte/NewBauhaus/stationen/interview-graph-photobooth/interviewfragen.md`
# in the hermes-entities vault.
#
# Two wordings were sharpened at the same time, both because the old ones
# steered the answers wrong:
# * „das Bestehende klüger reparieren" sounds like masonry although it means
#   RULES — demonstrably so: the old corpus produced the terms „Klüger
#   reparieren" and „Strukturelle Reparatur" as building terms, sitting next to
#   „Weiterbauen im Bestand". Answers about renovation are then
#   indistinguishable from question 1's.
# * „wie Ihr Ort sich verändert … fühlen Sie sich gehört?" assumes a resident's
#   role almost nobody in the hall has (mayors, managing directors, presidiums)
#   and pulls a professional back into a private one.
GUIDING_QUESTIONS = [
    "Wenn Sie an das Haus oder die Stadt denken, in der Sie in 20 Jahren leben "
    "wollen — was wäre das Erste, das anders sein sollte als heute?",
    "Das Bauen erstickt an Normen, Genehmigungen und Standards — braucht es "
    "dafür einen radikalen Bruch, oder lässt sich das bestehende Regelwerk "
    "Schritt für Schritt entrümpeln?",
    "Wer sollte entscheiden, wie sich Städte und Dörfer verändern — und wie "
    "weit sollen die Menschen, die dort leben, wirklich mitbestimmen dürfen?",
]

#: Kept, not asked by default. Available if a visitor goes there on their own,
#: if the station runs more than three questions, or as a replacement should a
#: main question prove barren on site. NOT part of GUIDING_QUESTIONS: the
#: corpus and the extraction prompt must describe what the station actually
#: asks, or the simulation tests a different text genre than the one that
#: arrives on the day.
ALTERNATIVE_QUESTIONS = [
    "Eine KI plant Ihr nächstes Zuhause — bis wohin vertrauen Sie ihr? Wo wollen "
    "Sie unbedingt einen Menschen entscheiden lassen?",
    "Worauf würden Sie beim Bauen verzichten, damit für die Natur mehr übrig "
    "bleibt? Gibt es etwas, auf das Sie niemals verzichten möchten?",
]

_QUESTION_BLOCK = "\n".join(
    f"{number}. {question}" for number, question in enumerate(GUIDING_QUESTIONS, start=1)
)

EXTRACTION_SYSTEM = f"""\
Du verdichtest das Transkript eines gesprochenen Interviews auf einer \
Architektur- und Baukultur-Konferenz (Festival NEW bauhaus 2026) zu wenigen, \
sehr konkreten Begriffen.

Den Personen wurden diese drei Leitfragen gestellt:
{_QUESTION_BLOCK}

ZWEI STIMMEN, EIN KANAL. Im Transkript sprechen zwei Menschen: eine fragende \
Person und die befragte Person. Die Spracherkennung trennt sie NICHT — es gibt \
keine Sprecherkennzeichnung, beide Stimmen stehen unmarkiert hintereinander. \
Du musst die Rollen selbst aus dem Inhalt erschliessen.

Woran du die fragende Person erkennst: sie stellt Fragen, hakt nach, fasst \
zusammen, bedankt sich, leitet über („Und wenn Sie jetzt an …", „Darf ich \
nachfragen", „Vielen Dank"). Sie erzaehlt nichts Eigenes.

WAS DAS FUER DICH HEISST:

* BEGRIFFE UND ZITAT KOMMEN AUSSCHLIESSLICH AUS DEN ANTWORTEN. Was die \
fragende Person sagt, ist NIE Quelle für einen Begriff und NIE das Zitat — \
auch dann nicht, wenn sie es besonders treffend formuliert. Sonst steht später \
der Satz der Interviewerin unter dem Portrait der befragten Person.
* DIE FRAGEN SIND TROTZDEM WICHTIG — als KONTEXT. Eine Antwort wie „Ja, \
unbedingt, aber nur wenn die Leute vor Ort mitreden" ist ohne die Frage davor \
nicht zu deuten. Lies die Fragen also mit, um die Antworten zu verstehen, aber \
zitiere und verschlagworte nur die Antworten.
* NIMM DIE FRAGE NICHT ALS THEMA DER ANTWORT. Wenn gefragt wird „Braucht es \
einen radikalen Bruch?" und die Person antwortet „Nein, mir geht es eher um \
die Handwerker, die keiner mehr findet", dann ist der Begriff \
„Handwerkermangel" und nicht „Radikaler Bruch". Verschlagwortet wird, was die \
Person SAGT, nicht, wonach sie gefragt wurde.

DIE FRAGEN WEICHEN AB. Die drei Leitfragen oben sind der Plan, nicht das \
Protokoll. Tatsächlich werden sie frei formuliert, gekürzt, in anderer \
Reihenfolge gestellt, übersprungen oder spontan durch Nachfragen ergänzt; \
manchmal kommen ganz andere Themen auf, weil die Person von sich aus etwas \
erzählt. Nimm die Liste deshalb als Orientierung, welche Themen zu erwarten \
sind — nicht als Raster, in das die Antworten passen müssten. Ein Gespräch, \
das keiner der drei Fragen folgt, ist trotzdem ein gültiges Interview.

Das Transkript kommt aus automatischer Spracherkennung: Füllwörter, \
abgebrochene Sätze, Wiederholungen, Hörfehler. Es reicht absichtlich über das \
Ende des Interviews hinaus — dort stehen Smalltalk, Verabschiedungen, Stimmen \
der nächsten Person oder Raumgeräusch.

Deine vier Aufgaben:

1. ENDE FINDEN. Bestimme `interview_end_index`: den Zeichen-Index im Transkript, \
an dem das Interview inhaltlich endet. Alles danach ignorierst du vollständig. \
Läuft das Interview bis zum Schluss, gib die Länge des Transkripts an.

2. BEGRIFFE. Nur aus dem Text VOR `interview_end_index`. Optimiere auf \
KONKRETHEIT, nicht auf Häufigkeit.
   Gut (konkret, bildhaft, überraschend): „Betonspritzen mit Drohnen", \
„Genossenschaftliches Wohnen", „Recycling-Beton", „Ländlicher Leerstand", \
„Ko-Kreation mit KI", „Modulares Bauen".
   Schlecht (nichtssagend, verbindet alles mit allem): „Nachhaltigkeit", \
„Zukunft", „Digitalisierung", „Veränderung", „Technologie", „Innovation".
   Regeln: deutsche Substantivphrase, 1–4 Wörter, ohne Artikel, keine ganzen \
Sätze, keine Personennamen, keine Firmennamen. Lieber weniger Begriffe als \
schwache Begriffe. `evidence` ist die kurze Textstelle, auf die sich der \
Begriff stützt.

3. ZITAT. Genau EIN wörtliches Zitat der Person, höchstens 200 Zeichen, \
sprachlich geglättet (Füllwörter raus), inhaltlich unverändert. Wähle nicht \
das erste passende, sondern das stärkste: das eigenwilligste, konkreteste, \
das, an dem man diese Person unter allen anderen wiedererkennt.
   Gut (unverwechselbar, hat eine Kante): „Ich will kein Museum bauen, ich \
will einen Ort, an dem meine Enkel noch Dreck machen dürfen."
   Schlecht (könnte jede Person hier gesagt haben): „Ich finde, wir sollten \
insgesamt mehr auf Nachhaltigkeit achten."
   Keine brave Zusammenfassung der Position der Person — ein echter Satz aus \
dem Transkript.

4. NAME. Am Anfang des Interviews stellt sich die befragte Person in der Regel \
vor. Gib diesen Namen an, genau einen, und zwar so, wie sie ihn selbst nennt — \
ein Vorname allein ist völlig in Ordnung. Nur der SELBSTGENANNTE Name der \
befragten Person: nicht die Namen Dritter, die im Gespräch vorkommen, nicht \
der Name der fragenden Person. Achtung, häufiger Fall: auch die fragende \
Person stellt sich vor („Ich bin Nina, ich frage hier ein paar Leute …"), \
oft sogar ZUERST. Der erste Name im Transkript ist also nicht automatisch der \
richtige — gesucht ist der Name dessen, der danach die Antworten gibt. \
Rate nicht. Stellt sich niemand vor oder bist du unsicher, wer da spricht, \
lass die Liste leer — kein Name ist richtig, ein falscher Name steht später \
unter einem fremden Zitat. Der Name ist ein eigenes Feld und wird dadurch \
NICHT zum Begriff: Punkt 2 verbietet Personennamen unter den Begriffen \
weiterhin.

Antworte ausschließlich im geforderten JSON-Schema.
"""


class ExtractedTerm(BaseModel):
    label: str
    evidence: str


class ExtractedQuote(BaseModel):
    text: str


class ExtractedName(BaseModel):
    text: str


class ExtractionResult(BaseModel):
    interview_end_index: int
    terms: list[ExtractedTerm]
    # A list, not a single optional field: `extract()` enforces the "at most
    # one" rule the same way it caps `terms` — by slicing the model's answer
    # after the call — so the two fields share one enforcement pattern instead
    # of the cap living in the type for one and in code for the other.
    quotes: list[ExtractedQuote]
    # Same shape and the same reason as `quotes` above: the "at most one" cap
    # lives in `extract()`, not in the type. Empty is the normal answer for
    # somebody who never said their name — the field stays blank, no
    # placeholder (Birk, 2026-08-31).
    #
    # The default is only for CALLERS: `kg.llm.strict_schema` puts every
    # property into the schema's `required` list, so the model is still asked
    # for the field on every call. It spares the many existing constructions
    # that are about terms or quotes from carrying an empty list they do not
    # care about.
    names: list[ExtractedName] = []


def build_extraction_prompt(transcript: str, max_terms: int) -> str:
    return (
        f"Höchstens {max_terms} Begriffe. Zeichenlänge des Transkripts: "
        f"{len(transcript)}.\n\n"
        f"--- TRANSKRIPT ---\n{transcript}\n--- ENDE TRANSKRIPT ---"
    )


def extract(llm, transcript: str, max_terms: int) -> ExtractionResult:
    result = llm.parse(
        system=EXTRACTION_SYSTEM,
        user=build_extraction_prompt(transcript, max_terms),
        output_model=ExtractionResult,
    )
    end = max(0, min(int(result.interview_end_index), len(transcript)))
    # The cap is enforced here too: graph density must not depend on the model's mood.
    # Same discipline for quotes: exactly one per person, never the prompt's word alone.
    # And for the name, which a person has exactly one of here.
    return ExtractionResult(
        interview_end_index=end,
        terms=list(result.terms)[:max_terms],
        quotes=list(result.quotes)[:1],
        names=list(result.names)[:1],
    )
