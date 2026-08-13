"""Spoken stop-command detection.

Cheap by construction: a string match on text we already receive (spec 5).
No wake-word engine, no extra model, no extra latency.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

_UMLAUTS = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
_PUNCT = re.compile(r"[^\w\s]", flags=re.UNICODE)
_SPACES = re.compile(r"\s+")
# STT delivers "beended" as well as "beendet": fold a word-final d onto t.
_FINAL_D = re.compile(r"d\b")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    for source, target in _UMLAUTS.items():
        text = text.replace(source, target)
    text = _PUNCT.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def _fuzzy(text: str) -> str:
    return _FINAL_D.sub("t", normalize(text))


def find_stop_phrase(text: str, phrases: Sequence[str]) -> str | None:
    haystack = _fuzzy(text)
    if not haystack:
        return None
    for phrase in phrases:
        needle = _fuzzy(phrase)
        if needle and needle in haystack:
            return phrase
    return None


def strip_stop_phrases(text: str, phrases: Sequence[str]) -> str:
    """Remove every occurrence of a stop phrase. MUST run before extraction (spec 5)."""
    result = text
    for phrase in phrases:
        needle = _fuzzy(phrase)
        if not needle:
            continue
        words = needle.split(" ")
        # Build a whitespace/punctuation tolerant pattern over the raw text.
        pattern = r"[\s,\.\-–—!?;:]*".join(
            _word_pattern(word) for word in words
        )
        result = re.sub(pattern, " ", result, flags=re.IGNORECASE)
    return _SPACES.sub(" ", result).strip()


def _word_pattern(word: str) -> str:
    """Match a normalized word against raw text (umlauts back, final d/t either way)."""
    chars = []
    for index, char in enumerate(word):
        if char == "t" and index == len(word) - 1:
            chars.append("[td]")
        else:
            chars.append(re.escape(char))
    pattern = "".join(chars)
    for folded, raw in (("ae", "[aä]"), ("oe", "[oö]"), ("ue", "[uü]"), ("ss", "(ss|ß)")):
        pattern = pattern.replace(folded, raw)
    return pattern
