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
    # The five real guiding questions, so the right text genre is targeted.
    assert "in 20 Jahren" in EXTRACTION_SYSTEM
    assert "Eine KI plant Ihr nächstes Zuhause" in EXTRACTION_SYSTEM


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


def test_extract_clamps_the_end_index_into_the_transcript():
    transcript = "kurz"
    llm = FakeLLM(ExtractionResult(interview_end_index=9999, terms=[], quotes=[]))
    assert extract(llm, transcript, max_terms=5).interview_end_index == len(transcript)

    llm = FakeLLM(ExtractionResult(interview_end_index=-5, terms=[], quotes=[]))
    assert extract(llm, transcript, max_terms=5).interview_end_index == 0
