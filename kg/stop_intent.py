"""Second opinion behind the wake word: did the person just end the interview?

The mechanical check (kg.segmentation) decides FIRST and for free. Only when it
does not fire and the bot's name is in the utterance does this module buy a
single, small LLM call. The wake word is the gatekeeper; the model does the
reading (Birk, 2026-08-30).

The occasion: „Hiermit beende ich das Interview." — verb in front, other
inflection, matched by none of the configured phrases, and no phrase list ever
written will cover every natural German wording. That is the finding, not a gap
to be patched with two more phrases.

Everything here is built for the hot path of a running recording: one boolean
out, a hard time budget, and every failure mode ends in "keep recording".
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from pydantic import BaseModel

log = logging.getLogger(__name__)

#: A small model on purpose — this decides one boolean, not the graph. NOT
#: `llm_model` (Opus, effort high, 16k tokens), which condenses the interview.
#: Sonnet rather than Haiku 4.5 because kg.llm always sends
#: `output_config.effort`, which Haiku 4.5 rejects; keeping one LLMClient for
#: the whole codebase is worth more than the difference in price for ~one call
#: per interview.
STOP_INTENT_EFFORT = "low"

#: Room for the model's own (adaptive) thinking before the two-field answer. A
#: truncated response is an LLMError in kg.llm, i.e. "do not close" — correct,
#: but it would waste the call, so do not tighten this to the size of the JSON.
STOP_INTENT_MAX_TOKENS = 1024

STOP_INTENT_SYSTEM = """\
Du entscheidest eine einzige Frage: Hat die Person mit dieser Äußerung das \
laufende Interview BEENDET?

Der Aufnahme-Bot der Station wird von den Gästen mit Namen angesprochen (in \
den Beispielen „Utopia"). Der Text kommt aus automatischer Spracherkennung: \
Füllwörter, fehlende Satzzeichen, Hörfehler.

JA — ein Beenden-Befehl, beliebig frei formuliert:
- „Utopia, hiermit beende ich das Interview"
- „Utopia, wir sind fertig"
- „Utopia, das war's"
- „Utopia, stopp"
- „Utopia, du kannst jetzt aufhören"

NEIN — kein Befehl, auch wenn vom Beenden die Rede ist:
- „Utopia, kannst du das Interview gleich beenden?" — eine Ankündigung für \
später, kein Befehl für jetzt
- „das Interview ist ja noch gar nicht beendet" — eine Aussage über den Zustand
- „Utopia hat mir gestern geholfen" — der Name kommt vor, sonst nichts
- „bevor das Interview beendet ist, wollte ich noch sagen…" — es geht weiter

Im Zweifel NEIN. Ein fälschlich beendetes Interview kostet das ganze Gespräch \
dieser Person; ein verpasstes Ende kostet eine Textnachricht an den Bot.

Antworte ausschließlich im geforderten JSON-Schema.
"""


class StopIntent(BaseModel):
    is_stop_command: bool


def build_stop_intent_prompt(text: str) -> str:
    """The WHOLE utterance, not just the part behind the name.

    „Utopia, ich glaube wir sind fertig" and „Utopia, kannst du gleich aufhören?"
    differ exactly in what surrounds the command.
    """
    return f"--- ÄUSSERUNG ---\n{text}\n--- ENDE ÄUSSERUNG ---"


def is_stop_command(llm, text: str) -> bool:
    result = llm.parse(
        system=STOP_INTENT_SYSTEM,
        user=build_stop_intent_prompt(text),
        output_model=StopIntent,
    )
    return bool(result.is_stop_command)


def call_with_timeout(fn: Callable[[], bool], timeout_s: float) -> bool:
    """Run `fn` in a daemon thread and give up after `timeout_s`.

    A hard budget, not a polite one: the HTTP client's own timeout is the
    proxy's promise, and on 2026-08-30 the proxy was answering `auth_error`
    with an expired token — the station cannot depend on the other side
    behaving. Whatever the abandoned call eventually returns is discarded, so a
    late "yes" can never close an interview that has meanwhile moved on.

    Daemon, so a hung call cannot hold up the station's shutdown (a
    ThreadPoolExecutor joins its threads at interpreter exit; this does not).
    """
    outcome: dict[str, object] = {}

    def run() -> None:
        try:
            outcome["value"] = fn()
        except Exception as exc:
            outcome["error"] = exc

    thread = threading.Thread(target=run, daemon=True, name="kg-stop-intent")
    thread.start()
    thread.join(timeout_s)
    if thread.is_alive():
        raise TimeoutError(f"stop-intent call exceeded {timeout_s}s")
    if "error" in outcome:
        raise outcome["error"]  # type: ignore[misc]
    return bool(outcome.get("value"))


def make_stop_intent(llm, timeout_s: float) -> Callable[[str], bool]:
    """The callable kg.session asks. Raises on timeout or error — the caller
    turns that into "keep recording"."""

    def ask(text: str) -> bool:
        return call_with_timeout(lambda: is_stop_command(llm, text), timeout_s)

    return ask


def build_stop_intent_llm(cfg):
    """The second, cheap client. `None` when the way is switched off.

    Der Anbieter wird über die eigenen `wake_word_llm_*`-Schlüssel gewählt und
    NICHT vom Pipeline-Modell geerbt (2026-08-31): hier fällt ein Ja/Nein im
    heißen Pfad, dort wird ein ganzes Interview verdichtet, und wer nur eines
    von beiden umstellt, soll genau das bekommen. Ohne diese Schlüssel ist es
    unverändert Anthropic.
    """
    if not (cfg.wake_word_llm and cfg.wake_word):
        return None
    from kg.llm import LLMClient

    return LLMClient(
        model=cfg.wake_word_llm_model,
        effort=STOP_INTENT_EFFORT,
        max_tokens=STOP_INTENT_MAX_TOKENS,
        api_key=cfg.wake_word_llm_api_key,
        api_mode=cfg.wake_word_llm_api_mode,
        url=cfg.wake_word_llm_url,
        reasoning_effort=cfg.wake_word_llm_reasoning_effort,
        # Dasselbe Budget wie der Thread darüber (call_with_timeout): ein
        # Request, der länger offen bleibt, als hier gewartet wird, kostet nur
        # noch Geld. Gilt nur im chat_completions-Modus; der Anthropic-Client
        # bringt sein eigenes Timeout mit.
        timeout=cfg.wake_word_llm_timeout_s,
        # One attempt, not two: kg.llm's retry would double the wall time on
        # the hot path, and a retry that lands after the guest has walked away
        # is worth nothing. The mechanical way and the text message stay.
        max_attempts=1,
    )
