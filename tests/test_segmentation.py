import unicodedata

import pytest

from kg.config import DEFAULT_STOP_PHRASES
from kg.segmentation import find_stop_phrase, normalize, strip_stop_phrases

PHRASES = ["Interview beendet", "Aufnahme beenden"]

# The list the station actually runs (`config.example.toml` mirrors it). The
# short PHRASES above stays the fixture for the matching mechanics; the
# stop/no-stop judgements below have to be made against the real list, because
# whether an inserted "damit" still fits depends on which phrases are
# configured — "Interview ist beendet" is one of them and the short list has it
# not.
CONFIGURED = DEFAULT_STOP_PHRASES


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


@pytest.mark.parametrize(
    "text",
    [
        # Birk's own closing sentence at the station, 2026-08-30. STT had it
        # right; the interview stayed open because "damit" broke the token run.
        "Das Interview ist damit beendet.",
        "Das Interview ist hiermit beendet.",
        "Das Interview ist jetzt beendet.",
        "So, das Interview ist dann beendet.",
        # Already worked before, and has to keep working: the command with a
        # short goodbye behind it (this is the e2e run's own sentence).
        "Gut, dann Interview beendet, vielen Dank.",
    ],
)
def test_one_filler_word_inside_the_command_still_stops(text):
    """Nobody speaks the configured formula literally (spec 5, Birk 2026-08-30)."""
    assert find_stop_phrase(text, CONFIGURED) is not None


@pytest.mark.parametrize(
    "text",
    [
        # The three cases from the brief: talking ABOUT the end of an interview
        # must never end one. A wrong stop costs a whole interview; a missed
        # one costs a text message to the bot, so this direction wins ties.
        "das Interview ist ja noch gar nicht beendet",
        "bevor das Interview beendet ist, wollte ich noch sagen…",
        "ich hab gestern ein Interview gegeben, das war schnell beendet",
        # Two more of the same shape, guarding the two knobs separately: this
        # one has two words in the gap (the tolerance is one)…
        "war das Interview eigentlich schon beendet",
        # …and this one has the command's words in order but a whole clause
        # behind them, which no spoken command has.
        "wir sollten die Aufnahme später mal beenden, aber jetzt noch nicht",
    ],
)
def test_talking_about_the_end_does_not_stop(text):
    assert find_stop_phrase(text, CONFIGURED) is None


def test_what_counts_as_a_stop_is_also_removed_from_the_transcript():
    """Spec 5: the command must not survive into extraction as a term."""
    text = "Beton ist wichtig. Das Interview ist damit beendet."
    assert find_stop_phrase(text, CONFIGURED) is not None

    stripped = strip_stop_phrases(text, CONFIGURED)
    assert "beendet" not in stripped.lower()
    assert "damit" not in stripped.lower()
    assert "Beton ist wichtig." in stripped
