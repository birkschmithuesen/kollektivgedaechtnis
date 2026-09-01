import logging

from kg.extraction import (
    EXTRACTION_SYSTEM,
    EXTRACTION_SYSTEM_WITHOUT_END,
    MIN_INTERVIEW_CHARS,
    ExtractionResult,
    build_extraction_prompt,
    extract,
)


class FakeLLM:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def parse(self, system, user, output_model):
        self.calls.append((system, user, output_model))
        return self.result


class ScriptedLLM:
    """Ein Ergebnis je Aufruf aus der Warteschlange; merkt sich die Systemprompts.

    Exceptions in der Warteschlange werden geworfen — so lässt sich ein
    fehlschlagender zweiter Anlauf ohne Netz nachstellen.
    """

    def __init__(self, *results):
        self.results = list(results)
        self.systems = []

    def parse(self, system, user, output_model):
        self.systems.append(system)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


SATZ = "Also wir brauchen wieder mehr Genossenschaften, ähm, wirklich. "


def substantial(zeichen=3000):
    """Ein Transkript in der Länge der echten Sitzungen (gemessen: 2945–4689).

    Synthetisch, nie ein echtes Transkript: die realen Aufnahmen enthalten
    Aussagen anwesender Personen und liegen aus gutem Grund nicht im Repo.
    """
    return SATZ * (zeichen // len(SATZ) + 1)


def leer(end_index):
    return ExtractionResult(interview_end_index=end_index, terms=[], quotes=[], names=[])


def voll(end_index):
    return ExtractionResult(
        interview_end_index=end_index,
        terms=[{"label": "Genossenschaftliches Wohnen", "evidence": "mehr Genossenschaften"}],
        quotes=[{"text": "Wir brauchen wieder mehr Genossenschaften."}],
        names=[{"text": "Mara"}],
    )


def test_the_prompt_carries_the_concreteness_examples_verbatim():
    assert "Betonspritzen mit Drohnen" in EXTRACTION_SYSTEM
    assert "Nachhaltigkeit" in EXTRACTION_SYSTEM
    # The three real guiding questions, so the right text genre is targeted —
    # and the two ALTERNATIVE_QUESTIONS explicitly NOT, because the extraction
    # prompt must describe what the station actually asks (2026-08-30).
    assert "in 20 Jahren" in EXTRACTION_SYSTEM
    assert "Regelwerk" in EXTRACTION_SYSTEM
    assert "Städte und Dörfer" in EXTRACTION_SYSTEM
    assert "Eine KI plant Ihr nächstes Zuhause" not in EXTRACTION_SYSTEM


def test_the_user_prompt_states_the_hard_cap_and_carries_the_transcript():
    prompt = build_extraction_prompt("Beton ist wichtig.", max_terms=5)
    assert "5" in prompt
    assert "Beton ist wichtig." in prompt


def test_extract_truncates_the_term_list_to_the_configured_cap():
    result = ExtractionResult(
        interview_end_index=10,
        terms=[{"label": f"t{i}", "evidence": "e"} for i in range(9)],
        quotes=[{"text": "z"}],
    )
    llm = FakeLLM(result)

    out = extract(llm, "irgendein transkript", max_terms=3)

    assert len(out.terms) == 3
    assert llm.calls[0][2] is ExtractionResult


def test_extract_caps_the_quote_list_to_one_even_if_the_model_sends_more():
    result = ExtractionResult(
        interview_end_index=10,
        terms=[],
        quotes=[{"text": "Erstes Zitat."}, {"text": "Zweites Zitat."}],
    )
    llm = FakeLLM(result)

    out = extract(llm, "irgendein transkript", max_terms=3)

    assert len(out.quotes) == 1
    assert out.quotes[0].text == "Erstes Zitat."


def test_extract_clamps_the_end_index_into_the_transcript():
    transcript = "kurz"
    llm = FakeLLM(ExtractionResult(interview_end_index=9999, terms=[], quotes=[]))
    assert extract(llm, transcript, max_terms=5).interview_end_index == len(transcript)

    llm = FakeLLM(ExtractionResult(interview_end_index=-5, terms=[], quotes=[]))
    assert extract(llm, transcript, max_terms=5).interview_end_index == 0


def test_the_prompt_asks_for_the_self_given_name_and_forbids_guessing():
    """Der Name steht später unter einem Zitat auf der Wand.

    Ein geratener oder aus dem Gespräch aufgeschnappter Name wäre dort eine
    Falschaussage über eine anwesende Person — teurer als gar kein Name.
    """
    assert "4. NAME." in EXTRACTION_SYSTEM
    assert "Rate nicht." in EXTRACTION_SYSTEM
    assert "lass die Liste leer" in EXTRACTION_SYSTEM
    # Der Name ist ein eigenes Feld und hebt Punkt 2 nicht auf: Personennamen
    # bleiben als BEGRIFFE verboten, sonst hinge die Person als Knoten im Netz.
    assert "keine Personennamen" in EXTRACTION_SYSTEM


def test_extract_caps_the_name_list_to_one_even_if_the_model_sends_more():
    """Dieselbe Bauart wie bei `quotes`: eine Liste, die hier geschnitten wird.

    Eine Person hat in diesem Datenmodell genau einen Namen; die Durchsetzung
    steht in `extract()` und nicht im Typ, damit beide Felder auf demselben Weg
    begrenzt werden.
    """
    result = ExtractionResult(
        interview_end_index=10,
        terms=[],
        quotes=[],
        names=[{"text": "Anna Weber"}, {"text": "Herr Neumann"}],
    )

    out = extract(FakeLLM(result), "irgendein transkript", max_terms=3)

    assert len(out.names) == 1
    assert out.names[0].text == "Anna Weber"


def test_extract_leaves_the_name_empty_when_nobody_introduced_themselves():
    """Kein Platzhalter, kein „Anonym" — am Zitat steht dann gar kein Name."""
    out = extract(
        FakeLLM(ExtractionResult(interview_end_index=10, terms=[], quotes=[], names=[])),
        "irgendein transkript",
        max_terms=3,
    )

    assert out.names == []


# --- Der Ausfall vom 2026-09-01: Interviews liefern reproduzierbar nichts ----
#
# Gemessen (docs/STAND.md 2h): 17 von 30 Läufen leer. Die naheliegende
# Erklärung — `interview_end_index = 0` verwirft das Interview — trägt NICHT:
# in mindestens 6 leeren Läufen stand das Ende bei 100 %, es wurde also gar
# nichts beschnitten. Deshalb greifen hier drei getrennte Sicherungen.


def test_an_impossible_end_index_is_discarded_instead_of_obeyed():
    """Ein Ende, hinter dem kein Interview mehr Platz hat, ist keine Kürzung.

    Die Ende-Suche soll einen SCHWANZ abschneiden — Verabschiedung, Smalltalk,
    die nächste Stimme. Ein Wert, der von einem substanziellen Transkript
    weniger übrig lässt als der kürzeste denkbare Gesprächsrest, ist kein
    knapper Schnitt, sondern ein Fehlgriff. Ihn zu befolgen kostet das
    gespeicherte Transkript (gemessen: 2 % von 2945 Zeichen = 59 Zeichen).
    """
    transcript = substantial()
    llm = FakeLLM(
        ExtractionResult(
            interview_end_index=0,
            terms=[{"label": "Genossenschaftliches Wohnen", "evidence": "e"}],
            quotes=[],
        )
    )

    assert extract(llm, transcript, max_terms=5).interview_end_index == len(transcript)


def test_a_barely_nonzero_end_index_is_discarded_too():
    """Sitzung 19 lieferte 2 % — dieselbe Klasse Unsinn wie die glatte Null."""
    transcript = substantial()
    llm = FakeLLM(
        ExtractionResult(
            interview_end_index=int(0.02 * len(transcript)),
            terms=[{"label": "Recycling-Beton", "evidence": "e"}],
            quotes=[],
        )
    )

    assert extract(llm, transcript, max_terms=5).interview_end_index == len(transcript)


def test_a_plausible_end_index_is_still_obeyed():
    """Die Sicherung verwirft Unsinn, sie überstimmt kein Urteil.

    Sitzung 37 — die einzige stabile — schnitt bei 56 bis 100 %. Solche Werte
    müssen durchgehen, sonst bleibt der Smalltalk im Transkript stehen.
    """
    transcript = substantial()
    plausibel = int(0.56 * len(transcript))
    llm = FakeLLM(
        ExtractionResult(
            interview_end_index=plausibel,
            terms=[{"label": "Recycling-Beton", "evidence": "e"}],
            quotes=[],
        )
    )

    assert extract(llm, transcript, max_terms=5).interview_end_index == plausibel


def test_a_completely_empty_result_is_asked_again_without_the_end_trimming():
    """Der zweite Anlauf entkoppelt Ende-Suche und Extraktion.

    Beide stecken heute in EINEM Aufruf, und das Schema verlangt den
    Zeichen-Index als ERSTES Feld — vor allem Inhaltlichen. Ist die Antwort
    komplett leer, wird ohne diese Kopplung noch einmal gefragt.
    """
    transcript = substantial()
    llm = ScriptedLLM(leer(len(transcript)), voll(len(transcript)))

    out = extract(llm, transcript, max_terms=5)

    assert llm.systems == [EXTRACTION_SYSTEM, EXTRACTION_SYSTEM_WITHOUT_END]
    assert [t.label for t in out.terms] == ["Genossenschaftliches Wohnen"]
    assert len(out.quotes) == 1
    assert [n.text for n in out.names] == ["Mara"]


def test_a_partial_result_is_kept_and_never_asked_again():
    """Nur die VOLLSTÄNDIG leere Antwort wird wiederholt.

    Sonst könnte der zweite Anlauf ein bereits gefundenes Zitat gegen nichts
    eintauschen — die Rückfrage soll nie schlechter machen, was schon da ist.
    """
    transcript = substantial()
    nur_zitat = ExtractionResult(
        interview_end_index=len(transcript),
        terms=[],
        quotes=[{"text": "Wir brauchen wieder mehr Genossenschaften."}],
        names=[],
    )
    llm = ScriptedLLM(nur_zitat)

    out = extract(llm, transcript, max_terms=5)

    assert llm.systems == [EXTRACTION_SYSTEM]
    assert len(out.quotes) == 1


def test_a_scrap_of_text_is_not_asked_again():
    """Ein paar Sekunden Raumgeräusch sind kein Interview.

    Dort ist die leere Antwort die richtige Antwort; ein zweiter Aufruf kostete
    nur Zeit und Geld und lockte Begriffe aus einem Nichts hervor.
    """
    llm = ScriptedLLM(leer(0))

    out = extract(llm, "Ähm. Ja. Mhm.", max_terms=5)

    assert llm.systems == [EXTRACTION_SYSTEM]
    assert out.terms == []


def test_the_second_attempt_may_also_come_back_empty_and_that_is_the_answer(caplog):
    """Ein Arbeitsgespräch korrekt zu verwerfen bleibt richtig — aber laut.

    Der Rückfall bettelt nicht um Begriffe, er nimmt nur die Ende-Beschneidung
    heraus. Kommt auch dann nichts, ist das ein Ausfall und gehört ins Log,
    statt als leere Scheibe an der Wand zu enden.
    """
    transcript = substantial()
    llm = ScriptedLLM(leer(len(transcript)), leer(len(transcript)))

    with caplog.at_level(logging.WARNING, logger="kg.extraction"):
        out = extract(llm, transcript, max_terms=5)

    assert len(llm.systems) == 2
    assert out.terms == [] and out.quotes == [] and out.names == []
    assert any(record.levelno >= logging.WARNING for record in caplog.records)


def test_a_failing_second_attempt_does_not_destroy_the_first_answer(caplog):
    """Ein Rückfall, der selbst scheitert, darf nicht schlimmer sein als keiner.

    Ohne diesen Fang würde aus einem (leeren, aber gültigen) Ergebnis eine
    Exception — und die Pipeline setzte die Person auf „failed", statt sie
    wenigstens mit Portrait und Transkript zu behalten.
    """
    transcript = substantial()
    llm = ScriptedLLM(leer(len(transcript)), RuntimeError("zweiter Anlauf gescheitert"))

    with caplog.at_level(logging.WARNING, logger="kg.extraction"):
        out = extract(llm, transcript, max_terms=5)

    assert out.terms == []
    assert out.interview_end_index == len(transcript)


def test_the_retry_prompt_drops_the_end_finding_and_nothing_else():
    """Die zweite Fassung darf sich nur in Aufgabe 1 unterscheiden.

    Sonst driften die beiden Prompts auseinander und der Rückfall misst etwas
    anderes als den Wegfall der Kopplung. Die beiden Textmarken, an denen
    `scripts/ab-analyse-prompt.py` auf der Station schneidet, müssen in BEIDEN
    Fassungen stehen bleiben.
    """
    assert "1. ENDE FINDEN." in EXTRACTION_SYSTEM
    assert "1. ENDE FINDEN." not in EXTRACTION_SYSTEM_WITHOUT_END

    gemeinsam = [
        "ZWEI STIMMEN, EIN KANAL.",  # Schnittmarke des A/B-Skripts
        "Das Transkript kommt aus automatischer",  # zweite Schnittmarke
        "2. BEGRIFFE.",
        "3. ZITAT.",
        "4. NAME.",
        "Betonspritzen mit Drohnen",
        "Rate nicht.",
    ]
    for marke in gemeinsam:
        assert marke in EXTRACTION_SYSTEM, marke
        assert marke in EXTRACTION_SYSTEM_WITHOUT_END, marke
