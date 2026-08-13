import unicodedata

import pytest

from kg.segmentation import find_stop_phrase, normalize, strip_stop_phrases

PHRASES = ["Interview beendet", "Aufnahme beenden"]


def test_normalize_folds_case_punctuation_and_umlauts():
    assert normalize("Aufnahme, BEENDEN!") == "aufnahme beenden"
    assert normalize("Größe  Übung") == "groesse uebung"


@pytest.mark.parametrize(
    "text",
    [
        "So, das Interview beendet.",
        "das interview beended",
        "Okay – INTERVIEW BEENDET!",
        "vielen dank, aufnahme beenden",
    ],
)
def test_matching_is_tolerant(text):
    assert find_stop_phrase(text, PHRASES) is not None


@pytest.mark.parametrize(
    "text",
    [
        "Danke, das war es.",
        "Ich bin fertig.",
        "Das Interview war interessant.",
        "",
    ],
)
def test_ordinary_speech_does_not_trigger(text):
    assert find_stop_phrase(text, PHRASES) is None


def test_returns_the_configured_phrase_that_matched():
    assert find_stop_phrase("bitte Aufnahme beenden", PHRASES) == "Aufnahme beenden"


def test_strip_removes_the_command_and_keeps_the_rest():
    text = "Beton ist wichtig. So, das Interview beendet. Tschüss."
    stripped = strip_stop_phrases(text, PHRASES)
    assert "Interview beendet" not in stripped
    assert "Beton ist wichtig." in stripped
    assert "Tschüss." in stripped


def test_strip_handles_the_variant_spelling_too():
    assert "beended" not in strip_stop_phrases("ja das interview beended ok", PHRASES)


def test_strip_is_a_no_op_without_a_match():
    text = "Wir brauchen mehr Genossenschaften."
    assert strip_stop_phrases(text, PHRASES) == text


def test_inflected_word_containing_a_phrase_does_not_trigger():
    text = "Die Aufnahme beendende Handlung war klar."
    assert find_stop_phrase(text, PHRASES) is None
    assert strip_stop_phrases(text, PHRASES) == text


def test_unlisted_punctuation_inside_the_command_is_stripped():
    text = "Bitte Aufnahme… beenden jetzt."
    assert find_stop_phrase(text, PHRASES) == "Aufnahme beenden"
    stripped = strip_stop_phrases(text, PHRASES)
    assert "Aufnahme" not in stripped
    assert "beenden" not in stripped
    assert "…" not in stripped
    assert "Bitte" in stripped
    assert "jetzt" in stripped


def test_nfd_normalized_stop_phrases_match_correctly():
    """Regression: stop phrases in NFD form must be normalized to NFC before tokenizing."""
    nfd_phrase = unicodedata.normalize("NFD", "Größe beenden")
    nfc_phrase = "Größe beenden"
    text = "Bitte Größe beenden jetzt."

    # NFD phrase must match despite its Unicode form
    assert find_stop_phrase(text, [nfd_phrase]) == nfd_phrase

    # Strip must work with NFD phrase
    stripped = strip_stop_phrases(text, [nfd_phrase])
    assert "Größe" not in stripped
    assert "beenden" not in stripped
    assert "Bitte" in stripped
    assert "jetzt" in stripped

    # Verify both forms produce identical results
    assert find_stop_phrase(text, [nfd_phrase]) == nfd_phrase
    assert find_stop_phrase(text, [nfc_phrase]) == nfc_phrase
