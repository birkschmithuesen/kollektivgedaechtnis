"""Interview lifecycle (spec 5). Pure state machine: no store, no clock, no I/O.

One microphone means exactly one interview can be open at a time. Every path
out of "open" is forgiving: a text message, a spoken command, the safety
timeout, or the next photo. It can never leave two interviews open.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from kg.segmentation import find_stop_phrase


@dataclass(frozen=True)
class Transition:
    kind: str  # "opened" | "closed"
    at: float
    reason: str  # opened: "photo"; closed: "text" | "spoken" | "timeout" | "new_photo"


class SessionTracker:
    def __init__(self, timeout_s: float, stop_phrases: Sequence[str]) -> None:
        self.timeout_s = float(timeout_s)
        self.stop_phrases = list(stop_phrases)
        self._open_since: float | None = None

    @property
    def open_since(self) -> float | None:
        return self._open_since

    def photo(self, at: float) -> list[Transition]:
        transitions: list[Transition] = []
        if self._open_since is not None:
            transitions.append(Transition("closed", at, "new_photo"))
        self._open_since = at
        transitions.append(Transition("opened", at, "photo"))
        return transitions

    def text_message(self, at: float) -> list[Transition]:
        return self._close(at, "text")

    def transcript(self, text: str, at: float) -> list[Transition]:
        if self._open_since is None:
            return []
        if find_stop_phrase(text, self.stop_phrases) is None:
            return []
        return self._close(at, "spoken")

    def tick(self, now: float) -> list[Transition]:
        if self._open_since is None or now - self._open_since < self.timeout_s:
            return []
        return self._close(now, "timeout")

    def _close(self, at: float, reason: str) -> list[Transition]:
        if self._open_since is None:
            return []
        self._open_since = None
        return [Transition("closed", at, reason)]
