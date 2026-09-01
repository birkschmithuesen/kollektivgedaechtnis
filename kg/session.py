"""Interview lifecycle (spec 5). State machine: no store, no clock, no I/O of
its own — the one judgement it cannot make mechanically it delegates to an
injected callable (`stop_intent`, wired to a small model in kg.core).

One microphone means exactly one interview can be open at a time. Every path
out of "open" is forgiving: a text message, a spoken command, the safety
timeout, the microphone switch, or the next photo. It can never leave two
interviews open.

Two ways IN since 2026-09-01: the photo, and the microphone switch for a
visitor who wants no picture taken of them. The second one is why a photo is
no longer unconditionally the next person — see `photo()`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from kg.segmentation import contains_wake_word, find_stop_phrase

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Transition:
    kind: str  # "opened" | "closed" | "portrait"
    at: float
    # opened: "photo" | "mic_switch"
    # closed: "text" | "spoken" | "spoken_llm" | "timeout" | "new_photo"
    #       | "mic_switch"
    # portrait: "late_photo"
    reason: str


class SessionTracker:
    def __init__(
        self,
        timeout_s: float,
        stop_phrases: Sequence[str],
        open_since: float | None = None,
        wake_word: str | None = None,
        stop_intent: Callable[[str], bool] | None = None,
        open_without_portrait: bool = False,
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
        # Whether the open interview still has no portrait — the one thing a
        # photo needs to know to tell "this visitor is handing in their
        # picture after all" from "this is the next visitor". Resumable for
        # the same reason as `open_since`: after a restart the store knows the
        # open person has no portrait, and forgetting that would turn the late
        # photo into a second person for the same conversation.
        self._without_portrait = open_since is not None and open_without_portrait

    @property
    def open_since(self) -> float | None:
        return self._open_since

    def photo(self, at: float) -> list[Transition]:
        """A photo is normally the next visitor — but not always.

        On an interview that was opened by the microphone switch and still has
        no portrait, the photo belongs to the person already talking: they
        changed their mind, or the operator got round to it late. Closing that
        interview and opening a second one would cut one conversation in two.

        Only that one case. A photo after a photo stays what it always was, a
        new visitor with reason "new_photo" — and so does the second photo
        after a handed-in portrait. Otherwise the next visitor would silently
        overwrite the previous one's portrait instead of getting their own
        node.

        OFFEN (Birk, 2026-09-01) — der Alternativ-Cache ist noch nicht gebaut:

            „Wenn während eines laufenden Interviews ein zweites Foto gemacht
            wird, soll das in einen alternativ Foto cache für das laufende
            Interview."

        Das ändert genau den `new_photo`-Zweig unten: ein zweites Foto ist
        dann kein neuer Besuch mehr, sondern eine weitere Aufnahme derselben
        Person, aus der später ausgewählt werden kann. Die Stelle ist hier
        markiert, das Verhalten aber bewusst UNVERÄNDERT gelassen — solange
        es keinen Cache gibt, in den das zweite Bild fällt, wäre das Foto
        sonst schlicht verloren, und das ist schlechter als der heutige
        Stand.

        Was vor dem Bauen entschieden sein muss, weil es sich hinterher nicht
        mehr billig ändern lässt:

        * **Wie fängt dann der nächste Besuch an?** Fällt jedes Foto in den
          Cache, gibt es keinen Weg mehr, per Foto ein neues Interview zu
          eröffnen. Der Schalter kann das (`mic_switch`), der Timeout auch —
          aber das ist eine Entscheidung über den Ablauf an der Station, keine
          Implementierungsfrage.
        * **Wo liegen die Bilder, und wie lange?** `person.photo_path` hält
          genau einen Pfad. Ein Cache braucht eine eigene Tabelle (oder eine
          Liste), plus eine Regel, wann die verworfenen Aufnahmen gelöscht
          werden — bei einer Arbeit über Datenschutz ist ein wachsender Haufen
          nicht ausgewählter Porträts kein Nebenaspekt.
        * **Wer wählt aus?** Operator-Ansicht, automatisch, oder der Gast
          selbst?

        Ausführlich in `docs/HANDOFF-alternativ-foto-cache.md`.
        """
        if self._open_since is not None and self._without_portrait:
            self._without_portrait = False
            return [Transition("portrait", at, "late_photo")]
        transitions: list[Transition] = []
        if self._open_since is not None:
            transitions.append(Transition("closed", at, "new_photo"))
        self._open_since = at
        self._without_portrait = False
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

        OFF is a fourth way out of "open", next to the text message, the spoken
        phrase and the timeout, and the only one that is not a judgement about
        language: the microphone was switched off, so the conversation is over.
        Its own reason, "mic_switch", so store and logs keep it apart from a
        spoken goodbye afterwards.

        ON is a second way IN (Birk, 2026-09-01), and the reason is not
        technical: somebody may not want a photograph taken of them, and in a
        work about surveillance a compulsory portrait as the price of
        admission would be a contradiction in itself. So the switch opens an
        interview, with its own reason "mic_switch" — the person is created
        without photo paths (the columns have always been nullable) and
        appears on the wall as a disc without a picture. A portrait can still
        be handed in later; `photo()` says how.

        Idempotent in both directions: ON with an interview already open opens
        nothing — no second one beside it, no re-opening — exactly as a
        repeated OFF closes nothing.
        """
        if not on:
            return self._close(at, "mic_switch")
        if self._open_since is not None:
            return []
        self._open_since = at
        self._without_portrait = True
        return [Transition("opened", at, "mic_switch")]

    def tick(self, now: float) -> list[Transition]:
        if self._open_since is None or now - self._open_since < self.timeout_s:
            return []
        return self._close(now, "timeout")

    def _close(self, at: float, reason: str) -> list[Transition]:
        if self._open_since is None:
            return []
        self._open_since = None
        self._without_portrait = False
        return [Transition("closed", at, reason)]
