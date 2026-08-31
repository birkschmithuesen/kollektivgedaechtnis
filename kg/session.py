"""Interview lifecycle (spec 5). State machine: no store, no clock, no I/O of
its own — the one judgement it cannot make mechanically it delegates to an
injected callable (`stop_intent`, wired to a small model in kg.core).

One microphone means exactly one interview can be open at a time. Every path
out of "open" is forgiving: a text message, a spoken command, the safety
timeout, or the next photo. It can never leave two interviews open.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from kg.segmentation import contains_wake_word, find_stop_phrase

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Transition:
    kind: str  # "opened" | "closed"
    at: float
    # opened: "photo"
    # closed: "text" | "spoken" | "spoken_llm" | "timeout" | "new_photo"
    #       | "mic_switch"
    reason: str


class SessionTracker:
    def __init__(
        self,
        timeout_s: float,
        stop_phrases: Sequence[str],
        open_since: float | None = None,
        wake_word: str | None = None,
        stop_intent: Callable[[str], bool] | None = None,
    ) -> None:
        self.timeout_s = float(timeout_s)
        self.stop_phrases = list(stop_phrases)
        # The bot's name in front of a phrase is the second, looser way to stop
        # (kg.segmentation). Both entrances pass through here: spoken text from
        # the STT and text messages to the bot.
        self.wake_word = wake_word
        # …and the name alone, without a phrase behind it, is the third: it
        # opens the gate to one small LLM call that reads the utterance
        # (kg.stop_intent). `None` switches that way off entirely — then this
        # class behaves exactly as it did before 2026-08-30.
        self.stop_intent = stop_intent
        # Lets a caller resume an interview that was already open in storage
        # (a restart after a crash) instead of silently forgetting it and
        # opening a second one on the next photo.
        self._open_since = open_since

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
        """Three steps, in this order and no other.

        1. The mechanical check. It is fast, free and deterministic, and it is
           the normal case — so it decides alone, and a hit never pays for a
           second opinion.
        2. Only if it did not fire AND the bot was addressed by name: one LLM
           call (`stop_intent`) that reads the whole utterance. Its own reason,
           "spoken_llm", so store and logs keep the two ways apart.
        3. No name, no call. Ever. Asking on every utterance is the continuous
           listening this design exists to avoid — the cost, the latency and
           the non-determinism of it.

        May block for as long as `stop_intent` takes (kg.core runs it off the
        event loop; kg.stop_intent enforces the time budget).
        """
        if self._open_since is None:
            return []
        if find_stop_phrase(text, self.stop_phrases, self.wake_word) is not None:
            return self._close(at, "spoken")
        if self.stop_intent is None or not contains_wake_word(text, self.wake_word):
            return []
        try:
            meant_it = self.stop_intent(text)
        except Exception as exc:
            # Timeout, dead proxy, unusable answer: the interview KEEPS RUNNING.
            # A wrongly ended interview costs the whole conversation; a missed
            # end costs a text message to the bot, and the 15-minute timeout
            # catches it either way.
            log.error("stop-intent check failed, interview stays open: %s", exc)
            return []
        return self._close(at, "spoken_llm") if meant_it else []

    def mic_switch(self, on: bool, at: float) -> list[Transition]:
        """The physical switch on the microphone moved (STT server, 2026-08-31).

        A fourth way out of "open", next to the text message, the spoken
        phrase and the timeout, and the only one that is not a judgement about
        language: the microphone was switched off, so the conversation is over.
        Its own reason, "mic_switch", so store and logs keep it apart from a
        spoken goodbye afterwards.

        Switching ON deliberately opens NOTHING. An interview here is a person
        with a portrait — `photo()` is the only entrance, and `Core._open`
        needs the photo paths to create the person at all. An interview opened
        by a switch would have no face and no node on the wall. The ON signal
        is still worth having (the operator page shows it, see
        `Core.on_mic_switch`), it just cannot be a session boundary.

        Idempotent in both directions: a repeated OFF on an already-closed
        session returns nothing, exactly like `_close` everywhere else.
        """
        if on:
            return []
        return self._close(at, "mic_switch")

    def tick(self, now: float) -> list[Transition]:
        if self._open_since is None or now - self._open_since < self.timeout_s:
            return []
        return self._close(now, "timeout")

    def _close(self, at: float, reason: str) -> list[Transition]:
        if self._open_since is None:
            return []
        self._open_since = None
        return [Transition("closed", at, reason)]
