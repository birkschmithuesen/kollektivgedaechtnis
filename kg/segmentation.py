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


def _find_sublist_occurrences(
    needle: list[str], haystack: list[_Token]
) -> list[tuple[int, int]]:
    """Return raw (start, end) spans in the NFC text for every contiguous,
    whole-token occurrence of needle in haystack.
    """
    if not needle:
        return []
    spans = []
    n = len(needle)
    for i in range(len(haystack) - n + 1):
        if all(haystack[i + j].normalized == needle[j] for j in range(n)):
            spans.append((haystack[i].start, haystack[i + n - 1].end))
    return spans


def find_stop_phrase(text: str, phrases: Sequence[str]) -> str | None:
    _, tokens = _tokenize(text)
    if not tokens:
        return None
    for phrase in phrases:
        needle = _phrase_tokens(phrase)
        if needle and _find_sublist_occurrences(needle, tokens):
            return phrase
    return None


def strip_stop_phrases(text: str, phrases: Sequence[str]) -> str:
    """Remove every occurrence of a stop phrase. MUST run before extraction (spec 5)."""
    nfc_text, tokens = _tokenize(text)
    spans: list[tuple[int, int]] = []
    for phrase in phrases:
        needle = _phrase_tokens(phrase)
        if not needle:
            continue
        spans.extend(_find_sublist_occurrences(needle, tokens))

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
