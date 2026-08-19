import yaml

from sim.generate_interviews import (
    DEFAULT_GENERATION_MODEL,
    PLANTED,
    QUESTIONS,
    SPEAKER_TYPES,
    build_generation_prompt,
    plan_corpus,
    write_expectations,
)


def test_the_five_real_guiding_questions_are_used_verbatim():
    assert len(QUESTIONS) == 5
    assert any("in 20 Jahren" in q for q in QUESTIONS)
    assert any("Eine KI plant Ihr nächstes Zuhause" in q for q in QUESTIONS)
    assert any("radikalen Bruch" in q for q in QUESTIONS)
    assert any("Wer sollte entscheiden" in q for q in QUESTIONS)
    assert any("für die Natur mehr übrig" in q for q in QUESTIONS)


def test_the_plan_is_deterministic():
    assert plan_corpus(60) == plan_corpus(60)


def test_every_question_and_every_speaker_type_is_covered():
    plan = plan_corpus(60)
    assert {spec.question_index for spec in plan} == set(range(5))
    assert {spec.speaker_type for spec in plan} == set(SPEAKER_TYPES)


def test_about_a_third_of_the_interviews_carry_a_planted_overlap():
    plan = plan_corpus(60)
    planted = [spec for spec in plan if spec.planted_concept]
    assert 15 <= len(planted) <= 25
    # every planted concept appears at least twice, otherwise it cannot merge
    counts = {}
    for spec in planted:
        counts[spec.planted_concept] = counts.get(spec.planted_concept, 0) + 1
    assert all(count >= 2 for count in counts.values())
    # and the phrasings differ, so a naive string match cannot pass the test
    for concept in counts:
        phrasings = {s.planted_phrasing for s in planted if s.planted_concept == concept}
        assert len(phrasings) >= 2


def test_the_prompt_demands_spoken_language_and_carries_the_question():
    spec = plan_corpus(60)[0]
    prompt = build_generation_prompt(spec)
    assert QUESTIONS[spec.question_index] in prompt
    assert "Füllwörter" in prompt
    assert spec.speaker_type in prompt


def test_planted_prompts_name_the_phrasing_to_use():
    spec = next(s for s in plan_corpus(60) if s.planted_concept)
    assert spec.planted_phrasing in build_generation_prompt(spec)


def test_expectations_document_every_planted_group(tmp_path):
    plan = plan_corpus(60)
    path = tmp_path / "expectations.yaml"

    document = write_expectations(plan, path)

    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert loaded == document
    concepts = {group["concept"] for group in loaded["expected_merges"]}
    assert concepts == {p["concept"] for p in PLANTED if _used(plan, p["concept"])}
    for group in loaded["expected_merges"]:
        assert len(group["interviews"]) >= 2
        assert len(group["phrasings"]) >= 2


def _used(plan, concept):
    return any(spec.planted_concept == concept for spec in plan)


def test_the_generation_model_defaults_to_sonnet():
    # Birk's decision (2026-08-19): synthetic-corpus generation runs on Sonnet,
    # not the Opus default (`cfg.llm_model`) used for real extraction/merge-judge
    # calls — this constant feeds the CLI's --model default.
    assert DEFAULT_GENERATION_MODEL == "claude-sonnet-5"
