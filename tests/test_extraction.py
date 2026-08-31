from kg.extraction import EXTRACTION_SYSTEM, ExtractionResult, build_extraction_prompt, extract


class FakeLLM:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def parse(self, system, user, output_model):
        self.calls.append((system, user, output_model))
        return self.result


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
