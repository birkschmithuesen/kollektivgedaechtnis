"""Extraction: find the real end of the interview, then condense it (spec 6.1, 6.3)."""

from __future__ import annotations

import logging

from pydantic import BaseModel

log = logging.getLogger(__name__)

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

#: Aufgabe 1 im Normalfall: das Ende suchen und danach beschneiden.
_TASK_FIND_END = """\
1. ENDE FINDEN. Bestimme `interview_end_index`: den Zeichen-Index im Transkript, \
an dem das Interview inhaltlich endet. Alles danach ignorierst du vollständig. \
Läuft das Interview bis zum Schluss, gib die Länge des Transkripts an.\
"""

#: Aufgabe 1 im zweiten Anlauf: gar nicht erst suchen. Der Rest des Prompts ist
#: Zeichen für Zeichen derselbe — der Rückfall nimmt genau EINE Variable heraus
#: (die Ende-Beschneidung) und lässt jede inhaltliche Regel stehen. Insbesondere
#: bleiben „Lieber weniger Begriffe als schwache Begriffe" und „Rate nicht" in
#: Kraft: ein Arbeitsgespräch ohne Interview darf auch hier nichts liefern.
_TASK_NO_END = """\
1. KEIN ENDE SUCHEN. Setze `interview_end_index` auf die Zeichenlänge des \
Transkripts, die oben genannt ist. Ein erster Durchgang über genau diesen Text \
hat nichts geliefert; deshalb entfällt jede Beschneidung und du wertest das \
GANZE Transkript aus. Smalltalk und Verabschiedung am Schluss sind weiterhin \
keine Quelle für Begriffe oder das Zitat — aber du verwirfst deswegen nichts.\
"""


# 🔴 WAS IN AUFGABE 2 STEHT UND WARUM — die Begruendungen gehoeren HIERHER,
# nicht in den Prompt (konsolidiert 2026-09-02).
#
# Am Abend des 2026-09-01 ist Aufgabe 2 von rund 1100 auf 3484 Zeichen
# gewachsen, weil zwei fehlende Aspekte nachgeruestet wurden. Dabei standen am
# Ende drei Regeln DOPPELT (Wortzahl, „Substantivphrase, kein Satz",
# Leerwoerter), zwei Absaetze erklaerten dem Modell die Entstehungsgeschichte
# einer Beispielwahl samt Datum, und zwei Anweisungen widersprachen sich:
# „Lieber weniger Begriffe als schwache" gegen „Fehlt eines, ist es vergessen
# worden". Jetzt 2323 Zeichen, jede Regel genau einmal.
#
# Die Belege, die aus dem Prompt entfernt wurden und trotzdem gelten:
#
# * WARUM DER AKTEUR IN DEN BEGRIFF GEHOERT. Birk sagte am 2026-09-01 im
#   ersten echten Interview „Ich hoffe, dass alle Rohstoffabhaengigkeiten von
#   der KI geplant werden." Extrahiert wurde „Rohstoffabhaengigkeiten" — das
#   Thema, nicht die Aussage. Gemessen ueber acht Laeufe: der KI-Aspekt kam in
#   4 von 8 vor. Mit der Regel: 8 von 8.
#
# * WARUM EINE HALTUNG EIN BEGRIFF IST. Derselbe Satz enthielt „und will, dass
#   alles ein bisschen mehr mit der Natur verbunden ist". Das fiel unter den
#   Tisch, weil es der Schlecht-Liste („Nachhaltigkeit") aehnlich sieht.
#   Gemessen: 1 von 8 vorher, 5 von 8 nachher.
#
# * WARUM DIE LAENGE HART IST. Die zwei Regeln darueber verfuehren dazu,
#   Akteur, Sache und Haltung in eine Phrase zu packen. Ohne harte Grenze
#   stieg der Anteil der Begriffe ueber vier Woertern an zwoelf synthetischen
#   Interviews von 2/10 auf 6/11; mit Grenze 3/12. Auf der Wand haengen bis zu
#   32 Etiketten gleichzeitig (`default_max_terms`), lange kollidieren.
#
# * WARUM DAS FORMBEISPIEL NICHT ZUM MATERIAL PASSEN DARF. Als hier eine
#   Beispielphrase stand, die inhaltlich zum Interview passte
#   („KI-geplante Rohstoffketten"), schrieb das Modell ihr Substantiv woertlich
#   ab: in 4 von 8 Laeufen stand „Rohstoffketten" im Begriff — ein Wort, das
#   die Person nie gesagt hatte. Dieselbe Falle ist in kg2/condense.py
#   dokumentiert (dort mit Bildszenen, gemessen am 2026-08-30). Beispiele in
#   diesem Prompt stammen deshalb aus einem fremden Thema.
#
# Messlatte fuer die naechste Aenderung, an Birks echtem Transkript
# (`data/transcript.jsonl`, 679 Zeichen) und den zwoelf Interviews unter
# sim/data/interviews/: KI-Aspekt 8/8, Natur-Aspekt 5/8, Begriffe ueber vier
# Woertern 3/12, leere Extraktionen 0/12.
def _build_system(task_one: str) -> str:
    return f"""\
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

{task_one}

2. BEGRIFFE. Nur aus dem Text VOR `interview_end_index`. Optimiere auf \
KONKRETHEIT, nicht auf Häufigkeit.

   FORM, nicht verhandelbar: deutsche Substantivphrase, HÖCHSTENS VIER Wörter, \
ohne Artikel, kein Satz, keine Personennamen, keine Firmennamen. Der Begriff \
steht als Etikett an einer Wand, auf der bis zu 32 davon gleichzeitig hängen; \
was länger ist, überlappt seine Nachbarn und schrumpft unter Lesegröße. \
Braucht ein Gedanke mehr Worte, sind es ZWEI Begriffe — trenne sie, statt \
einen langen zu bilden.

   WAS HINEINGEHÖRT:
   * Die Sache — und WER oder WOMIT sie geschieht, wenn die Person das sagt. \
Wer plant, baut, entscheidet, bezahlt, pflegt, gehört in den Begriff. Nur den \
Gegenstand zu nehmen lässt das Thema übrig und wirft die Aussage weg. Der \
Akteur reist als Bestimmungswort oder als Partizip mit, nie als Prädikat.
   * WIE JEMAND LEBEN WILL. Danach ist ausdrücklich gefragt worden, die \
Antwort darauf ist kein Beiwerk. Das ist ein eigener Begriff neben der \
Bauweise, kein Anbau an sie: Wer „Lehmhaus" sagt, hat „Lehmhaus" gesagt — \
daraus „Wohnen im Lehmhaus" zu machen verlängert nur das Etikett.

   Gut (konkret, bildhaft, überraschend): „Betonspritzen mit Drohnen", \
„Genossenschaftliches Wohnen", „Recycling-Beton", „Ländlicher Leerstand", \
„Ko-Kreation mit KI", „Modulares Bauen". Die ersten beiden zeigen zugleich, \
wie ein Akteur mitreist — „Drohnen spritzen Beton" wäre ein Satz und falsch.
   Schlecht (nichtssagend, verbindet alles mit allem): „Nachhaltigkeit", \
„Zukunft", „Digitalisierung", „Veränderung", „Technologie", „Innovation". \
Die Probe: Könnten zwei Menschen hier verschieden antworten? „Nachhaltigkeit" \
würde jeder unterschreiben und sagt deshalb nichts.

   🔴 Nimm aus den Beispielen die FORM. Den WORTLAUT nimmst du ausschließlich \
aus dem Transkript — kein Wort, das die Person nicht gesagt hat.

   PRÜFUNG ZUM SCHLUSS, beides in einem Durchgang:
   * Vollständig? Wer eine Bauweise nennt UND ein Verhältnis zur Umgebung UND \
eine Vorstellung davon, wer etwas regeln soll, hat drei Dinge gesagt, nicht \
eins. Ein schwacher Begriff ist schlimmer als ein fehlender — aber ein \
eigenständiger Wunsch, den die Person genannt hat, ist nie schwach.
   * Kurz genug? Zähle die Wörter. Höchstens vier, ohne Ausnahme.

   `evidence` ist die kurze Textstelle, auf die sich der Begriff stützt.

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


EXTRACTION_SYSTEM = _build_system(_TASK_FIND_END)

#: Der Prompt des zweiten Anlaufs (siehe `extract`). Entsteht aus derselben
#: Vorlage, damit die beiden Fassungen nicht auseinanderdriften können.
EXTRACTION_SYSTEM_WITHOUT_END = _build_system(_TASK_NO_END)

#: Untergrenze in Zeichen, ab der ein Transkript überhaupt ein Interview sein
#: kann. Hergeleitet, nicht geschätzt: Aufgabe 3 deckelt das Zitat bei 200
#: Zeichen, und ein Interview, aus dem ein Zitat UND mehrere belegte Begriffe
#: kommen sollen, braucht ein Vielfaches davon. 400 Zeichen sind zwei solche
#: Zitate — darunter liegt kein Gespräch, sondern Raumgeräusch. Zum Vergleich:
#: die fünf am 2026-09-01 gemessenen echten Sitzungen haben 2945 bis 4689
#: Zeichen, also das Sieben- bis Zwölffache.
#:
#: Die Schwelle hat zwei Aufgaben in `extract()`: sie entscheidet, welcher
#: `interview_end_index` noch als Kürzung durchgeht, und welcher Text einen
#: zweiten Anlauf wert ist.
MIN_INTERVIEW_CHARS = 400


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


def _is_empty(result: ExtractionResult) -> bool:
    """Nichts gefunden: kein Begriff, kein Zitat, kein Name.

    Bewusst das UND: eine Antwort mit Zitat, aber ohne Begriff ist mager, aber
    sie ist ein Ergebnis. Nur die vollständig leere Antwort ist der Ausfall, der
    am 2026-09-01 gemessen wurde, und nur sie wird wiederholt.
    """
    return not result.terms and not result.quotes and not result.names


def _resolve_end_index(reported: int, transcript: str) -> int:
    """Der gemeldete Index, in den Text geklemmt — und auf Plausibilität geprüft.

    Die Ende-Suche schneidet einen SCHWANZ ab (Verabschiedung, Smalltalk, die
    nächste Stimme). Ein Wert, der von einem substanziellen Transkript weniger
    übrig lässt als `MIN_INTERVIEW_CHARS`, behauptet, fast die ganze Aufnahme
    sei Beiwerk gewesen — das ist keine knappe Kürzung, sondern ein Fehlgriff,
    und er wird verworfen statt befolgt. Gemessen wurde genau das: 2 % von 2945
    Zeichen (Sitzung 19), also 59 Zeichen Interview.

    Plausible Werte bleiben unangetastet. Die einzige stabile Sitzung der
    Messung schnitt bei 56 bis 100 %; solche Urteile überstimmt diese Funktion
    ausdrücklich nicht.
    """
    end = max(0, min(int(reported), len(transcript)))
    if len(transcript) >= MIN_INTERVIEW_CHARS and end < MIN_INTERVIEW_CHARS:
        log.warning(
            "extraction: end index %s of %s chars leaves no interview — using the full text",
            end,
            len(transcript),
        )
        return len(transcript)
    return end


def extract(llm, transcript: str, max_terms: int) -> ExtractionResult:
    """Ein Aufruf; bei komplett leerem Ergebnis ein zweiter ohne Ende-Suche.

    Warum überhaupt ein zweiter: Ende-Suche und Extraktion stecken in EINEM
    Aufruf, und `interview_end_index` ist das erste Feld des Schemas — das
    Modell muss den Zeichen-Index also nennen, bevor es irgendetwas Inhaltliches
    geschrieben hat, und alles Weitere entsteht unter dieser eigenen, ungeprüften
    Festlegung. Aufgabe 2 sagt dazu „Begriffe nur aus dem Text VOR
    `interview_end_index`". Der zweite Anlauf nimmt genau diese Kopplung heraus
    und sonst nichts.

    Er ist zugleich die Messung: Rettet er die leeren Fälle, ist die Kopplung
    belegt und steht als Warnung im Log der Ausstellung. Rettet er sie nicht,
    lag es nicht an ihr — dann ist es ein Text ohne Interview, und auch das
    steht im Log, statt als leere Scheibe an der Wand zu enden.
    """
    result = llm.parse(
        system=EXTRACTION_SYSTEM,
        user=build_extraction_prompt(transcript, max_terms),
        output_model=ExtractionResult,
    )

    if _is_empty(result) and len(transcript) >= MIN_INTERVIEW_CHARS:
        log.warning(
            "extraction: nothing found in %s chars (end index %s) — asking again "
            "without the end trimming",
            len(transcript),
            result.interview_end_index,
        )
        try:
            second = llm.parse(
                system=EXTRACTION_SYSTEM_WITHOUT_END,
                user=build_extraction_prompt(transcript, max_terms),
                output_model=ExtractionResult,
            )
        except Exception as exc:
            # Der Rückfall darf nie schlimmer sein als kein Rückfall: das erste
            # Ergebnis ist gültig, nur leer. Eine Exception hier machte daraus
            # ein „failed" in der Pipeline und kostete Transkript und Portrait.
            log.error("extraction: the second attempt failed as well: %s", exc)
        else:
            if _is_empty(second):
                log.error(
                    "extraction: still nothing after the second attempt — %s chars "
                    "produced no term, no quote and no name",
                    len(transcript),
                )
            else:
                log.warning(
                    "extraction: the second attempt rescued the interview "
                    "(%s terms, %s quotes, %s names)",
                    len(second.terms),
                    len(second.quotes),
                    len(second.names),
                )
            result = second

    # The cap is enforced here too: graph density must not depend on the model's mood.
    # Same discipline for quotes: exactly one per person, never the prompt's word alone.
    # And for the name, which a person has exactly one of here.
    return ExtractionResult(
        interview_end_index=_resolve_end_index(result.interview_end_index, transcript),
        terms=list(result.terms)[:max_terms],
        quotes=list(result.quotes)[:1],
        names=list(result.names)[:1],
    )
