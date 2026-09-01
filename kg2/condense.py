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
  same failure mode as the contradiction clause. Nach diesem Schritt steuerte
  `DreamConfig.guiding_question` nur noch eine Überschrift auf dem Schirm; am
  2026-08-31 ist sie deshalb ersatzlos entfallen (`kg2/config.py`), samt
  Anzeige und Schaltern. Es gibt keine Leitfrage mehr, weder hier noch dort.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import BaseModel

from kg2.weighting import (
    QUOTE_PERSONS,
    RECENCY_SHARE,
    RECENT_TERMS,
    REQUIRED_TERMS,
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

#: Wie oft Stufe 1 hoechstens gefragt wird, wenn der Wandsatz seine FORM
#: verfehlt (zu lang oder mit Komma).
#:
#: Gemessen am Abend des ersten Ausstellungstags, vier Laeufe auf dem echten
#: Graphen: 4 von 4 Saetzen verletzten die Form -- 21, 47, 45 und 55 Woerter
#: gegen ein Maximum von 16, einer davon auf Englisch, einer eine
#: Verweigerung. Der echte Traum d1 hatte 26. Bis dahin wurde das nur
#: protokolliert („Logged, never rejected").
#:
#: Diese Haltung bleibt richtig und aendert sich hier NICHT: ein abgelehnter
#: Satz waere eine leere Aenderung an der Wand, und Spec §8 sagt, man solle
#: Unvollkommenheit aussitzen statt anzuhalten. Zwischen ablehnen und
#: hinnehmen liegt aber ein dritter Weg, den `kg.llm` bei kaputtem JSON
#: laengst geht: noch einmal fragen. Bleibt es auch beim letzten Versuch
#: falsch, wird der Traum trotzdem geliefert -- mit dem KUERZESTEN der
#: Versuche, nicht dem letzten.
#:
#: Drei und nicht mehr: der Satz steht auf einem grossen Schirm und wird
#: alle `min_interval_s` (240 s) erneuert; drei Aufrufe sind dagegen billig,
#: eine offene Schleife waere es nicht.
SENTENCE_FORM_ATTEMPTS = 3

_BASE = """\
Du bist das Gedächtnis einer Ausstellungsstation auf dem Festival NEW bauhaus \
2026. Den ganzen Tag über haben Menschen dort Interviews über das Bauen, das \
Wohnen und die Zukunft gegeben. Aus allem, was gesagt wurde, ist ein Graph \
geworden. Jetzt beginnt dein Traum davon.

Du lieferst fünf Dinge, in dieser Reihenfolge: eine englische \
BILDBESCHREIBUNG, den deutschen WANDSATZ dazu, seine ÜBERSETZUNG, einen \
WIDERSPRUCH und zwei Zahlen. Was zuerst kommt, ist das Bild — der Satz wird \
daraus verdichtet, nicht umgekehrt.


=== WAS FÜR ALLES GILT ===

TRÄUMEN, NICHT ILLUSTRIEREN. Das Ergebnis ist keine Zusammenfassung, kein \
Bericht und keine plausible Architekturvision. Es ist eine Verdichtung im \
wörtlichen Sinn: mehrere Aussagen fallen in ein Bild zusammen, Dinge \
verschieben sich, das Bild darf unmöglich sein. Eine glatte, schöne \
Zukunftsvision wäre das Gegenteil dieser Aufgabe. Verdichte die Begriffe zu \
EINER Aussage über das Bauen und Wohnen.

BELEGBARKEIT. Alles stützt sich auf die gelieferten Begriffe und Zitate. \
Erfinde nichts hinzu, keine Zahlen und keine Behauptungen — was du nicht \
belegen kannst, darfst du auch nicht erfinden. Ein Widerspruch \
darf vorkommen, wenn einer im Material liegt — erfinde keinen.

DER BEGRIFF IST DIE ABKÜRZUNG, NICHT DIE SACHE. Was im Material steht, sind \
verdichtete Etiketten aus einem Gespräch. Jedes ist die Kurzform eines \
VORGANGS, an dem Menschen beteiligt sind, und die Kurzform allein ergibt kein \
Bild. Frage bei jedem Begriff: Wer tut hier was, und wie sähe der Moment aus, \
in dem er es tut? Setze DAS ins Bild. Nur wenn zu einem Begriff wirklich \
niemand handelt, zeige die Spur allein.
- Zu wenig (nur die Spur, der Vorgang fehlt): „a wall covered in hundreds of \
coloured adhesive dots\\"
- Zu wenig (nur der Gegenstand): „a stamped building permit on a table\\"

FINDE DIE SZENE SELBST. Zu den beiden Zeilen oben gibt es absichtlich keine \
Musterlösung, und auch sonst steht in diesem Prompt keine Beispielszene: Ein \
Bildmodell und ein Sprachmodell ahmen jedes gezeigte Vorbild nach, statt es \
als eine Möglichkeit unter vielen zu lesen. Der Vorgang, den ein Begriff \
meint, sieht jedes Mal anders aus — in einer Halle oder auf der Straße, im \
Sitzen oder im Stehen, mit zwanzig Menschen oder mit zweien, mitten im \
Geschehen oder danach, wenn alle weg sind. Nimm nicht die naheliegendste \
Fassung, sondern die, die zu den heute genannten Begriffen passt.

WELCHE BEGRIFFE INS BILD GEHÖREN. Das Material beginnt mit einer kurzen Liste \
von PFLICHTBEGRIFFEN. Sie ist nicht gemeint, sondern gerechnet — aus der Zahl \
der Menschen, die einen Begriff genannt haben, und dem Zeitpunkt, an dem er \
zuerst fiel. Jeder davon steht in der Bildbeschreibung, als das was er meint, \
nicht nur als sein Wort.
Das ist die halbe Antwort. Die andere ist deine, und dafür gelten drei Dinge:
- BREITE, NICHT NUR DIE SPITZE. Die meistgenannten Begriffe stehen oft den \
ganzen Tag oben, weil sie früh fielen. Wer nur sie nimmt, träumt bei zehn \
Interviews dasselbe wie bei sechzig. Nimm deshalb auch aus der Mitte und dem \
unteren Teil der Liste, was das Bild konkret macht.
- DU WÄHLST DAS TRAGENDE MOTIV. Die Pflichtliste sagt, WAS vorkommt, nicht \
was im Mittelpunkt steht. Nimm als tragendes Motiv den Begriff, der die \
stärkste Szene hergibt, und stelle die übrigen daneben: als Gegenstand am \
Rand, als Spur an einer Fläche, als etwas, das gerade vorbei ist oder erst \
noch kommt. So zeigt nicht jedes Bild des Tages dieselbe Sache mit \
wechselnder Kulisse.
- DER JÜNGSTE BLOCK MUSS SICHTBAR WERDEN. Unter „Zuletzt gesagt" stehen die \
Begriffe aus den letzten Gesprächen; mindestens zwei davon gehören ins Bild, \
als etwas, das man sieht. Das ist die einzige Stelle, an der das Bild auf die \
Menschen reagiert, die gerade eben gesprochen haben.

VERBOTEN, überall: Namen von Menschen, Zuschreibungen wie „eine Besucherin \
sagte", Aufzählungen, Doppelpunkte mit Listen, Anführungszeichen, Meta-Sätze \
über den Graphen oder über das Träumen selbst. Nenne keine Namen.


=== 1. DIE BILDBESCHREIBUNG (englisch) — das Bild, aus dem alles Weitere folgt ===

Zusammenhängende englische Prosa, sechs bis acht Sätze, ungefähr 130 bis 180 \
Wörter. Nimm dir diesen Raum wirklich: Das Material eines Ausstellungstags \
trägt dutzende Begriffe, und eine zu knappe Beschreibung zwingt dich, fast \
alles wegzulassen. Ein Bildmodell verkraftet viele Einzelheiten in einem \
Raum; was es nicht verkraftet, sind zwei Räume.

Benenne, was konkret zu sehen ist: Materialien, Oberflächen, den Zustand der \
Dinge, wie sie im Raum zueinander stehen, wie groß sie im Verhältnis \
zueinander sind, was die Menschen mit den Händen tun, und was in der Tiefe \
des Bildes liegt. Geh vom Vordergrund nach hinten durch.

MENSCHEN GEHÖREN INS BILD, wo das Material von Menschen handelt. Beteiligung, \
Entscheidung, Streit, Pflege, Handwerk, Wohnen: das sind Dinge, die Menschen \
TUN. Zeige sie bei der Tätigkeit — die Hände am Werkzeug, den Körper in der \
Haltung, in der man arbeitet, wartet, zeigt oder sich abwendet. Gesichter \
müssen nicht erkennbar sein, aber ein Mensch im Bild ist ganz im Bild und \
nicht am Rand angeschnitten.

BEIDE MASSSTÄBE IN DERSELBEN AUFNAHME. Was die Menschen erzählen, betrifft \
Straßenzüge, Ortschaften, Landschaften, nicht nur eine Wand; ein Bild, das \
ausschließlich einen Ausschnitt zeigt, macht aus einer Zukunftsvorstellung \
eine Baustellennotiz.
- NAH: was Menschen konkret tun, mit den Händen, an einem bestimmten Ding.
- WEIT: dahinter oder darüber sichtbar, wie weit das reicht — Dächer bis zum \
Ortsrand, ein Straßenzug, eine Talseite, ein Stadtrand.
Der weite Teil ist kein Hintergrundschmuck: An ihm muss man ABLESEN können, \
was die Begriffe im Großen bedeuten. Bei versiegelten Flächen sieht man nicht \
einen Hof, sondern wie weit der Asphalt reicht. Wähle den Standpunkt \
entsprechend — von einem Dach, aus einem oberen Fenster, von einer Anhöhe —, \
irgendwo, wo Nahes und Weites in EINEM Blick liegen.

BEIDE SEITEN INS BILD. Gibt das Material Zuversichtliches UND Beunruhigendes \
her, kommt beides vor, gleich groß und gleich konkret: Was intakt, benutzt \
oder neu gemacht ist, gehört genauso hinein wie was bröckelt, leersteht oder \
versiegelt ist.
🔴 EIN EINZIGER ORT, EINE EINZIGE AUFNAHME: Beides steht an DEMSELBEN Ort, \
ineinander verschränkt — nicht als zwei Hälften nebeneinander. Beschreibe \
einen zusammenhängenden Raum, den eine einzige Kamera von einem einzigen \
Standpunkt aus erfasst. Verwende keine Wendungen, die den Ausschnitt teilen („links … \
rechts", „auf der einen Seite … auf der anderen", „daneben", „gegenüber", \
„im Gegensatz dazu"), sondern solche, die den Raum zusammenhalten („an \
derselben Wand", „durch dieselbe Tür", „hinter", „darüber", „mitten in").
- Schlecht (zwei Bilder in einem): „a freshly rendered house on the left, and \
boarded-up shopfronts on the right\\"
Prüfe: Steht alles, was du nennst, in einem Raum, den eine Kamera von einem \
Punkt aus erfasst?

WAS NICHT HINEINGEHÖRT: keine Stimmung, keine Lichtstimmung (warm, kalt, \
düster, hoffnungsvoll), keine Kamera-, Objektiv-, Film- oder Stilangabe — und \
KEINE LICHTQUELLE, keine Tageszeit, keine Lichtrichtung. Kein Sonnenstand, \
kein „afternoon light", kein „low sun", kein „daylight", kein Strahl, der von \
irgendwo einfällt. Das entscheidet Stufe 2 aus mood; nennst du es selbst, \
gewinnt deine Fassung und die Stimmung des Tages steht nicht mehr im Bild.
Beschreibe stattdessen den ZUSTAND DER OBERFLÄCHE: nass, trocken, staubig, \
matt, verkrustet, frisch gestrichen, ausgeblichen, moosig, abgegriffen, \
gerissen. Das hält unter jedem Licht.
- Falsch (Lichtquelle und Tageszeit): „the wet surface glinting in low \
afternoon light\\"
- Falsch (Sonnenstand und Richtung): „low sun grazing the raised dots\\"

SCHRIFT IM BILD ist erlaubt und muss nicht vermieden werden. Nur eines ist \
Pflicht: Wenn etwas Beschriftetes vorkommt, sage den WORTLAUT dazu — als \
deutschen Text in Anführungszeichen, mit ausdrücklich benannter Sprache, ein \
bis vier Wörter oder eine Zahl. Ohne das erfindet das Bildmodell englischen \
Text, und das Bild hängt in einer deutschen Ausstellung. Der übrige \
Beschreibungstext bleibt englisch.
- Richtig: „a printed fee board wired to the scaffolding, the German text \
reading „NEUBAU 3.200 €/m²""


=== 2. DER WANDSATZ (deutsch) ===

FORM: genau ein Hauptsatz auf Deutsch, höchstens {max_words} Wörter, OHNE Komma, ohne \
Nebensatz, ohne Gedankenstrich. Er steht als Bildunterschrift auf einem \
großen Schirm und muss im Vorbeigehen in einem Blick erfassbar sein.

🔴 DER SATZ TRÄGT NICHT DAS GANZE BILD. Er zeigt DERSELBEN Szene wie die Bildbeschreibung oben, keine zweite \
daneben, und ist ihre VERDICHTUNG: EIN Vorgang daraus, der eine, an dem man die anderen ahnt. \
Die Pflichtbegriffe, das Nahe und das Weite, beide Seiten — das alles steht \
oben in der Beschreibung und muss hier nicht noch einmal vorkommen. Wer \
versucht, alles hineinzupacken, bekommt zwangsläufig Kommas und Nebensätze: \
In {max_words} Wörtern haben drei Begriffe plus Vorder- und Hintergrund \
keinen Platz. Nenne weniger und zeige das genau.
Eine Aufzählung ist nicht die Rettung: „A und B steigen aus C auf" hält zwar \
die Wortzahl ein, ist aber kein Bild, sondern eine Liste mit Verb.


=== 3. DIE ÜBERSETZUNG (englisch) ===

Derselbe Satz, wörtlich ins Englische — keine inhaltliche Veränderung, keine \
Ausschmückung, dieselbe Satzform.


=== 4. DER WIDERSPRUCH (englisch) ===

Ein kurzer Halbsatz, kein ganzer Satz, ohne Punkt am Ende — er wird in Stufe \
2 hinter einen einleitenden Satz gehängt.

Er benennt den Widerspruch aus dem Material als etwas SICHTBARES.

WELCHE ZWEI HÄLFTEN: die STÄRKSTE ZUVERSICHTLICHE und die STÄRKSTE \
BEUNRUHIGTE Aussage im Material, nicht irgendein Gegensatzpaar. Beide gleich \
konkret. Findet sich zu einer Seite nichts Belegbares, lass das Feld LEER, statt \
die fehlende Seite zu erfinden — ein erfundener Widerspruch ist schlechter \
als keiner.

SICHTBAR MACHEN: Ein Bildmodell kann keinen Vorgang und keine Absicht zeigen, \
nur Dinge im Raum. Nenne zwei GEGENSTÄNDE, ORTE ODER HANDLUNGEN, die man \
beide gleichzeitig fotografieren könnte — und verbinde sie über den Raum, \
nicht über eine Trennlinie.
- Schlecht (unsichtbar): „gathering opinions while decisions are made from \
above\\" — „von oben entschieden" hat kein Aussehen.
- Schlecht (unsichtbar): „restoring an existing façade while billing it as new \
construction\\"
Prüfe an einer Frage: Könnte ein Fotograf das mit einer einzigen Aufnahme \
festhalten? Wenn er dafür wissen müsste, was jemand denkt, vorhat oder \
abrechnet, ist es noch nicht sichtbar.


=== 5. MOOD UND TENSION (zwei ganze Zahlen von 1 bis 5) ===

mood: Wie blicken die Menschen auf die ZUKUNFT? 1 = deutlich negativ, \
3 = neutral/gemischt, 5 = deutlich positiv.
Entscheidend ist die RICHTUNG, nicht der Ton. Wer ein Problem scharf benennt \
und dazu sagt, was man tun müsste, blickt zuversichtlich nach vorn — auch \
wenn jedes Wort nach Missstand klingt. Vorschläge setzen voraus, dass sich \
etwas ändern lässt; zähle sie als das. Negativ ist Material erst, wenn die \
Menschen keinen Weg mehr sehen: wenn sie resignieren, andere für unbelehrbar \
halten oder erwarten, dass alles so bleibt. Wäge ab, statt den lautesten \
Begriff entscheiden zu lassen: Wie viele Aussagen benennen einen Weg, wie \
viele nur einen Missstand? Bei ungefähr gleich vielen ist 3 richtig.

tension: Wie weit liegen die Aussagen auseinander? 1 = einig, 5 = unvereinbar.\
"""


class DreamSentence(BaseModel):
    """🔴 Die REIHENFOLGE der Felder ist Absicht, seit 2026-09-02.

    Vorher stand `sentence` an erster Stelle. Ein Modell fuellt die Felder in
    genau dieser Reihenfolge -- der Wandsatz entstand also, BEVOR es die
    ausfuehrliche Bildbeschreibung gab, und trug deshalb die ganze Last: alle
    Pflichtbegriffe, das Nahe und das Weite, beide Seiten des Widerspruchs.
    In 16 Woertern ohne Komma passt das nicht.

    Gemessen am 2026-09-02, vier Laeufe mit je bis zu drei Versuchen: 1 von
    12 Saetzen hielt die Form ein, die anderen hatten 27 bis 55 Woerter. Der
    Prompt selbst sagt es richtig -- „Der Wandsatz und diese Beschreibung sind
    dasselbe Bild, einmal knapp und einmal ausfuehrlich" --, nur in der
    falschen Reihenfolge: Man verdichtet ein Bild, das man schon hat.

    Jetzt entsteht erst die Beschreibung mit allem darin, dann der Satz als
    ihre Verdichtung. Die DB-Spalten heissen unveraendert, sie werden ueber
    ihren Namen geschrieben -- diese Aenderung beruehrt nur, in welcher
    Reihenfolge das Modell denkt.
    """

    image_description: str
    sentence: str
    sentence_en: str
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
    quote_persons: int = QUOTE_PERSONS,
    single_mention_budget: int = SINGLE_MENTION_BUDGET,
    shared_terms_saturation: int = SHARED_TERMS_SATURATION,
    recent_terms: int = RECENT_TERMS,
    required_terms: int = REQUIRED_TERMS,
    recency_share: float = RECENCY_SHARE,
    last_person_id: str | None = None,
) -> str:
    """`single_mention_budget`/`shared_terms_saturation`/`recent_terms` only
    exist so `sim.dream_calibrate terms`/`recency` can try other values
    (kg2/weighting.py's gliding formula and recency block) without
    duplicating this function; production always uses the module defaults.

    `required_terms`/`recency_share` are the two dials behind the mechanical
    required-terms block (`kg2.weighting.select_required`, added 2026-08-30 on
    Birk's suggestion). They are passed through for the same reason — and
    because a calibration run that sets `single_mention_budget=0` must not get
    single mentions back through the required block, which would make that
    dial silently mean nothing.
    """
    rendered = render_material(
        material,
        include_quotes=include_quotes,
        quote_persons=quote_persons,
        single_mention_budget=single_mention_budget,
        shared_terms_saturation=shared_terms_saturation,
        recent_terms=recent_terms,
        required_terms=required_terms,
        recency_share=recency_share,
        last_person_id=last_person_id,
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


#: Wendungen, mit denen ein Modell die AUFGABE beschreibt, statt sie zu lösen.
#: Gemessen am 2026-08-31 an der Wand: Als Traumsatz stand dort wörtlich
#: „language not specified", als Bildbeschreibung „no explicit 'your MOTD'
#: found". Beides kam mit HTTP 200 und gültigem Schema zurück — für jede
#: bestehende Prüfung ein einwandfreier String, für die Ausstellung eine
#: Fehlermeldung an der Wand.
#:
#: Bewusst eng gefasst und ausschliesslich ENGLISCH: Der Wandsatz ist deutsch
#: (FORM-Abschnitt des Prompts), also kann keine dieser Wendungen in einer
#: gültigen Antwort vorkommen. Eine deutsche Wendung wie „nicht angegeben"
#: steht absichtlich NICHT hier — sie könnte Teil eines echten Satzes sein,
#: und ein zu breiter Filter, der gute Sätze wegwirft, wäre schlimmer als der
#: Fehler, den er verhindern soll.
_META_WENDUNGEN = (
    "not specified",
    "no explicit",
    "not provided",
    "placeholder",
    "insert the actual",
    "no material",
    "not available",
    "unable to determine",
)


def _ist_meta_antwort(text: str) -> bool:
    """Beschreibt der Text die Aufgabe, statt sie zu erfüllen?

    Zwei Merkmale, beide notwendig gegen Fehlalarm:

    1. Eine der Wendungen oben — alle englisch, während der Wandsatz deutsch
       sein muss.
    2. ODER der Text zitiert die Anweisung selbst zurück. Gemessen mit Kimi
       K2.6 bei einer Person ohne ausgewertete Begriffe: „Ein einzelner
       Hauptsatz auf Deutsch, höchstens 16 Wörter, ohne Komma…". Erkennbar
       daran, dass mehrere Wörter aus dem FORM-Abschnitt gemeinsam auftreten —
       ein echter Traumsatz über eine Ausstellung sagt nicht „Hauptsatz" und
       „Nebensatz" in einem Atemzug.
    """
    if not text:
        return False
    klein = text.lower()
    if any(w in klein for w in _META_WENDUNGEN):
        return True
    anweisungswoerter = ("hauptsatz", "nebensatz", "gedankenstrich", "höchstens")
    return sum(w in klein for w in anweisungswoerter) >= 2


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
    quote_persons: int = QUOTE_PERSONS,
    single_mention_budget: int = SINGLE_MENTION_BUDGET,
    shared_terms_saturation: int = SHARED_TERMS_SATURATION,
    recent_terms: int = RECENT_TERMS,
    last_person_id: str | None = None,
) -> CondenseResult:
    """One call. Errors propagate — `kg2.cycle` owns the failure policy (§8).

    `last_person_id` verankert die Bildbegriffe bei der zuletzt befragten
    Person (Birk, 2026-08-30, siehe `kg2.weighting.select_required`): Der
    Ausschnitt wandert dann mit den Gespraechen durch den Graphen, statt den
    ganzen Tag um denselben Spitzenreiter zu kreisen. Ohne Wert bleibt es beim
    meistgenannten Begriff des ganzen Materials.
    """
    system = build_condense_system()
    user = build_condense_prompt(
        material,
        include_quotes=include_quotes,
        quote_persons=quote_persons,
        single_mention_budget=single_mention_budget,
        shared_terms_saturation=shared_terms_saturation,
        recent_terms=recent_terms,
        last_person_id=last_person_id,
    )

    def _form_stimmt(satz: str) -> bool:
        """Ein Hauptsatz, hoechstens `SENTENCE_MAX_WORDS` Woerter, kein Komma."""
        return len(satz.split()) <= SENTENCE_MAX_WORDS and "," not in satz

    versuche: list[DreamSentence] = []
    for n in range(1, SENTENCE_FORM_ATTEMPTS + 1):
        kandidat = llm.parse(system=system, user=user, output_model=DreamSentence)
        versuche.append(kandidat)
        roh = _clean(kandidat.sentence)
        if _form_stimmt(roh):
            break
        log.warning(
            "stage 1 sentence form wrong (%s words, comma=%s) — asking again, "
            "attempt %s of %s: %r",
            len(roh.split()), "," in roh, n, SENTENCE_FORM_ATTEMPTS, roh,
        )
    # Der erste formrichtige gewinnt. Gibt es keinen, der KUERZESTE — nicht der
    # letzte: sonst macht eine Wiederholung den Satz schlimmer, statt ihn zu
    # retten (gemessen: 21, dann 47, dann 45 Woerter).
    result = next(
        (k for k in versuche if _form_stimmt(_clean(k.sentence))),
        None,
    )
    if result is None:
        result = min(
            versuche,
            key=lambda k: (len(_clean(k.sentence).split()), "," in _clean(k.sentence)),
        )
    sentence = _clean(result.sentence)
    if not sentence:
        raise ValueError("stage 1 returned an empty sentence")
    if _is_truncated(sentence):
        # Broken, not merely imperfect — see _is_truncated's docstring for
        # why this is rejected while a missing final period is not.
        raise ValueError(f"stage 1 sentence looks truncated/corrupted: {sentence!r}")
    if _ist_meta_antwort(sentence):
        # Wie `_is_truncated`: lieber kein Traum als ein falscher. Der Traum
        # scheitert, der Watcher versucht es beim nächsten Auslöser erneut
        # (spec §8) — und auf Schirm B bleibt der letzte gute Traum stehen,
        # statt von einer Fehlermeldung ersetzt zu werden.
        raise ValueError(f"stage 1 described the task instead of doing it: {sentence!r}")

    sentence_en = _clean(result.sentence_en or "")
    if _is_truncated(sentence_en):
        raise ValueError(f"stage 1 English sentence looks truncated/corrupted: {sentence_en!r}")
    if _ist_meta_antwort(sentence_en):
        raise ValueError(f"stage 1 English sentence is a meta answer: {sentence_en!r}")
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
    if image_description and _ist_meta_antwort(image_description):
        # Hier VERWERFEN statt scheitern — anders als beim Wandsatz oben. Der
        # Unterschied ist derselbe, den der Kommentar unten begründet: Ein
        # Defekt hier verschlechtert das Bild, zerstört aber nicht den Traum,
        # und Stufe 2 hat mit `sentence_en` einen ehrlichen Rückweg.
        # „no explicit 'your MOTD' found" ging am 2026-08-31 genau hier durch.
        log.warning(
            "stage 1 image description describes the task instead of a motif; falling back: %r",
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
