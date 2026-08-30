"""Spoken stop-command detection.

Cheap by construction: a string match on text we already receive (spec 5).
No wake-word engine, no extra model, no extra latency.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

_UMLAUTS = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
_PUNCT = re.compile(r"[^\w\s]", flags=re.UNICODE)
_SPACES = re.compile(r"\s+")
# STT delivers "beended" as well as "beendet": fold a word-final d onto t.
_FINAL_D = re.compile(r"d\b")
_WORD = re.compile(r"\w+", re.UNICODE)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    for source, target in _UMLAUTS.items():
        text = text.replace(source, target)
    text = _PUNCT.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def _fuzzy(text: str) -> str:
    return _FINAL_D.sub("t", normalize(text))


@dataclass(frozen=True)
class _Token:
    normalized: str
    start: int
    end: int


def _tokenize(text: str) -> tuple[str, list[_Token]]:
    """Tokenise once over NFC text; each raw \\w+ run corresponds 1:1 to a
    normalised token, since normalize() maps every [^\\w\\s] char to a space.
    """
    nfc_text = unicodedata.normalize("NFC", text)
    tokens = [
        _Token(normalized=_fuzzy(match.group()), start=match.start(), end=match.end())
        for match in _WORD.finditer(nfc_text)
    ]
    return nfc_text, tokens


def _phrase_tokens(phrase: str) -> list[str]:
    nfc_phrase = unicodedata.normalize("NFC", phrase)
    return [_fuzzy(word) for word in _WORD.findall(nfc_phrase)]


# Nobody speaks the configured formula literally. Birk closed his interview on
# 2026-08-30 with "Das Interview ist damit beendet." — STT had every word right,
# the run of tokens broke on "damit", and the interview stayed open until the
# 15-minute timeout, which is exactly the failure that drops a person's terms
# into the NEXT person's interview. So the phrase's words must appear in order,
# but ONE foreign word may sit between them (in total, not per gap).
#
# One and not two: at two, "war das Interview eigentlich schon beendet" becomes
# a stop command. The realistic insertions are all single words anyway —
# "damit", "hiermit", "jetzt", "dann", "also".
_MAX_GAP_TOKENS = 1

# …and the match has to sit at the END of what was said. This is the second
# half of the same guard, and the brief's own negative case forces it: "bevor
# das Interview beendet ist, wollte ich noch sagen…" contains the configured
# phrase verbatim and contiguously, so no gap budget can reject it — only its
# position can. A spoken command is the last thing in an utterance; two words
# of trailing courtesy ("…, vielen Dank") are all that ever follows it.
#
# Note this makes the detection STRICTER than it was: that sentence stopped an
# interview before today and no longer does. Deliberate — a wrongly fired stop
# costs a whole interview, a missed one costs a text message to the bot.
_MAX_TRAILING_TOKENS = 2

# Second, deliberately looser way in: the bot's name in front of the phrase
# („Robo, Interview beendet", Birk 2026-08-30). Additive — the phrase alone
# keeps working exactly as above; whoever calls the bot by its name, though,
# means it, so behind a wake word the same phrase may be spoken more freely:
_WAKE_MAX_GAP_TOKENS = 2  # two fillers inside the command instead of one…
_WAKE_MAX_TRAILING_TOKENS = 4  # …and a whole "vielen Dank für das Gespräch"
# behind it instead of two words.
#
# What stays strict is the distance between name and command: at most this many
# foreign words may sit between them. That is what keeps the address a form of
# address and not a topic. It also settles the brief's borderline case,
# "Robo, kannst du das Interview gleich beenden?" — DOES NOT STOP: three words
# ("kannst du das") stand between name and phrase, so it never reaches the
# looser gap budget at all. Deliberate: that sentence asks about an end still
# to come, it does not declare one, and the whole tuning of this module leans
# the same way — a wrongly fired stop costs a whole interview, a missed one
# costs a text message to the bot. Guests who really want to stop have the
# short form and the text message.
_WAKE_LEAD_TOKENS = 2


def _find_phrase_matches(
    needle: list[str], haystack: list[_Token], max_gap: int
) -> list[tuple[int, int]]:
    """Return (first, last) token indices for every in-order occurrence of
    needle in haystack that interleaves at most `max_gap` foreign tokens.

    Each start index yields at most its shortest match (foreign tokens are
    skipped only when the next needle token does not fit right here), which is
    what strip_stop_phrases wants: never cut away more of the sentence than the
    command itself needs.
    """
    if not needle:
        return []
    matches = []
    for i in range(len(haystack)):
        if haystack[i].normalized != needle[0]:
            continue
        position = i + 1
        budget = max_gap
        for word in needle[1:]:
            while (
                position < len(haystack)
                and haystack[position].normalized != word
                and budget > 0
            ):
                position += 1
                budget -= 1
            if position >= len(haystack) or haystack[position].normalized != word:
                break
            position += 1
        else:
            matches.append((i, position - 1))
    return matches


def _spans(needle: list[str], haystack: list[_Token], max_gap: int) -> list[tuple[int, int]]:
    """The raw (start, end) offsets in the NFC text of every match."""
    return [
        (haystack[first].start, haystack[last].end)
        for first, last in _find_phrase_matches(needle, haystack, max_gap)
    ]


def _find_wake_matches(
    wake: list[str], needle: list[str], haystack: list[_Token]
) -> list[tuple[int, int]]:
    """(first, last) token indices of every "<wake word> … <phrase>" occurrence.

    `first` is the wake word's own first token, so a caller that cuts the span
    cuts the name away with the command — otherwise "Robo" would be left
    standing in the extraction input (spec 5).
    """
    wake_spans = _find_phrase_matches(wake, haystack, 0)
    if not wake_spans:
        return []
    matches = []
    for first, last in _find_phrase_matches(needle, haystack, _WAKE_MAX_GAP_TOKENS):
        for wake_first, wake_last in wake_spans:
            if wake_last < first <= wake_last + 1 + _WAKE_LEAD_TOKENS:
                matches.append((wake_first, last))
                break
    return matches


def find_stop_phrase(
    text: str, phrases: Sequence[str], wake_word: str | None = None
) -> str | None:
    _, tokens = _tokenize(text)
    if not tokens:
        return None
    wake = _phrase_tokens(wake_word) if wake_word else []
    for phrase in phrases:
        needle = _phrase_tokens(phrase)
        if not needle:
            continue
        for _first, last in _find_phrase_matches(needle, tokens, _MAX_GAP_TOKENS):
            if len(tokens) - 1 - last <= _MAX_TRAILING_TOKENS:
                return phrase
        if not wake:
            continue
        for _first, last in _find_wake_matches(wake, needle, tokens):
            if len(tokens) - 1 - last <= _WAKE_MAX_TRAILING_TOKENS:
                return phrase
    return None


def strip_stop_phrases(text: str, phrases: Sequence[str], wake_word: str | None = None) -> str:
    """Remove every occurrence of a stop phrase. MUST run before extraction (spec 5).

    Same span finder and the same gap tolerance as find_stop_phrase, so
    everything that counts as a stop is also removed — that is the consistency
    spec 5 needs: the command must never come back out of the LLM as a term.

    Deliberately WITHOUT the trailing-word rule above. This runs over a whole
    interview transcript, not over one spoken utterance, and the cut can reach
    a little past the command (kg.core.settle_cut_end); a positional rule would
    then leave "Interview beendet" standing in the extraction input, which is
    the one thing this function exists to prevent. The price is that a sentence
    merely talking about the end loses those words too — a filler sentence, no
    term in it.

    With a wake word configured the cut starts at the name, not at the phrase:
    "Robo, das Interview ist beendet" must not leave "Robo" behind, or the
    extraction turns the bot's name into a term. A "Robo" NOT followed by a
    command stays — there the name is part of a real sentence ("Robo hat mir
    gestern geholfen"), and cutting words out of it would change what the
    person said.
    """
    nfc_text, tokens = _tokenize(text)
    wake = _phrase_tokens(wake_word) if wake_word else []
    spans: list[tuple[int, int]] = []
    for phrase in phrases:
        needle = _phrase_tokens(phrase)
        if not needle:
            continue
        spans.extend(_spans(needle, tokens, _MAX_GAP_TOKENS))
        if wake:
            spans.extend(
                (tokens[first].start, tokens[last].end)
                for first, last in _find_wake_matches(wake, needle, tokens)
            )

    if not spans:
        return _SPACES.sub(" ", nfc_text).strip()

    spans.sort()
    merged: list[list[int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    pieces = []
    cursor = 0
    for start, end in merged:
        pieces.append(nfc_text[cursor:start])
        pieces.append(" ")
        cursor = end
    pieces.append(nfc_text[cursor:])
    result = "".join(pieces)
    return _SPACES.sub(" ", result).strip()
