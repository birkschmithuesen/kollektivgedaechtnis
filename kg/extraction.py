"""Extraction: find the real end of the interview, then condense it (spec 6.1, 6.3)."""

from __future__ import annotations

from pydantic import BaseModel

# The five real guiding questions from the briefing. Single source of truth:
# the simulation corpus generator (sim/generate_interviews.py) imports these,
# so the test corpus can never drift away from the extraction prompt (spec 9).
GUIDING_QUESTIONS = [
    "Wenn Sie an das Haus oder die Stadt denken, in der Sie in 20 Jahren leben "
    "wollen — was wäre das Erste, das anders sein sollte als heute?",
    "Eine KI plant Ihr nächstes Zuhause — bis wohin vertrauen Sie ihr? Wo wollen "
    "Sie unbedingt einen Menschen entscheiden lassen?",
    "Braucht das Bauen einen radikalen Bruch mit dem System — oder reicht es, das "
    "Bestehende klüger zu reparieren?",
    "Wer sollte entscheiden, wie Ihr Ort/Ihre Stadt sich verändert — und fühlen "
    "Sie sich dabei gehört?",
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

Den Personen wurden diese fünf Leitfragen gestellt:
{_QUESTION_BLOCK}

Das Transkript kommt aus automatischer Spracherkennung: Füllwörter, \
abgebrochene Sätze, Wiederholungen, Hörfehler. Es reicht absichtlich über das \
Ende des Interviews hinaus — dort stehen Smalltalk, Verabschiedungen, Stimmen \
der nächsten Person oder Raumgeräusch.

Deine drei Aufgaben:

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

Antworte ausschließlich im geforderten JSON-Schema.
"""


class ExtractedTerm(BaseModel):
    label: str
    evidence: str


class ExtractedQuote(BaseModel):
    text: str


class ExtractionResult(BaseModel):
    interview_end_index: int
    terms: list[ExtractedTerm]
    # A list, not a single optional field: `extract()` enforces the "at most
    # one" rule the same way it caps `terms` — by slicing the model's answer
    # after the call — so the two fields share one enforcement pattern instead
    # of the cap living in the type for one and in code for the other.
    quotes: list[ExtractedQuote]


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
    return ExtractionResult(
        interview_end_index=end,
        terms=list(result.terms)[:max_terms],
        quotes=list(result.quotes)[:1],
    )
