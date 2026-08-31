import threading
import time

import pytest

from kg.stop_intent import (
    STOP_INTENT_EFFORT,
    STOP_INTENT_SYSTEM,
    StopIntent,
    build_stop_intent_llm,
    build_stop_intent_prompt,
    call_with_timeout,
    is_stop_command,
    make_stop_intent,
)


class FakeLLM:
    """Answers what it was told, records what it was asked."""

    def __init__(self, is_stop=True, delay=0.0):
        self.is_stop = is_stop
        self.delay = delay
        self.calls: list[tuple[str, str]] = []

    def parse(self, system, user, output_model):
        self.calls.append((system, user))
        if self.delay:
            time.sleep(self.delay)
        if isinstance(self.is_stop, Exception):
            raise self.is_stop
        return output_model(is_stop_command=self.is_stop)


def test_the_prompt_separates_a_command_from_a_mention():
    """The whole difficulty of the task, and it is not in the schema."""
    assert "beende ich das Interview" in STOP_INTENT_SYSTEM
    assert "Utopia hat mir gestern geholfen" in STOP_INTENT_SYSTEM
    assert "kannst du das Interview gleich beenden" in STOP_INTENT_SYSTEM


def test_the_prompt_carries_the_whole_utterance():
    prompt = build_stop_intent_prompt("Utopia, ich glaube wir sind fertig")
    assert "Utopia, ich glaube wir sind fertig" in prompt


def test_a_yes_and_a_no_come_back_as_booleans():
    assert is_stop_command(FakeLLM(is_stop=True), "Utopia, das war's") is True
    assert is_stop_command(FakeLLM(is_stop=False), "Utopia hat geholfen") is False


def test_the_call_is_kept_short():
    """Cheap by construction: one utterance in, one boolean out."""
    llm = FakeLLM()
    is_stop_command(llm, "Utopia, das war's")
    system, user = llm.calls[0]
    assert len(user) < 400
    assert list(StopIntent.model_fields) == ["is_stop_command"]


def test_call_with_timeout_gives_up_on_a_hanging_call():
    started = threading.Event()

    def hang():
        started.set()
        time.sleep(30)

    began = time.monotonic()
    with pytest.raises(TimeoutError):
        call_with_timeout(hang, timeout_s=0.05)
    assert time.monotonic() - began < 5.0
    assert started.is_set()


def test_call_with_timeout_leaves_no_thread_that_could_hold_up_a_shutdown():
    """The abandoned call must not keep the process alive — a hung proxy would
    otherwise stall the station's shutdown for as long as its own timeout."""
    # By identity, not by name: an earlier test's abandoned call is still
    # asleep under the same thread name.
    before = {id(t) for t in threading.enumerate()}
    with pytest.raises(TimeoutError):
        call_with_timeout(lambda: time.sleep(30), timeout_s=0.05)
    leftover = [t for t in threading.enumerate() if id(t) not in before]
    assert leftover and all(t.daemon for t in leftover)


def test_call_with_timeout_passes_the_error_through():
    with pytest.raises(RuntimeError, match="auth_error"):
        call_with_timeout(lambda: (_ for _ in ()).throw(RuntimeError("auth_error")), 1.0)


def test_the_asker_answers_within_its_budget():
    intent = make_stop_intent(FakeLLM(is_stop=True), timeout_s=5.0)
    assert intent("Utopia, hiermit beende ich das Interview") is True


def test_a_slow_answer_is_dropped_rather_than_waited_for():
    """A yes that arrives after the guest has left must never close anything —
    the asker gives up, the caller (kg.session) logs and keeps recording."""
    intent = make_stop_intent(FakeLLM(is_stop=True, delay=30.0), timeout_s=0.05)
    began = time.monotonic()
    with pytest.raises(TimeoutError):
        intent("Utopia, hiermit beende ich das Interview")
    assert time.monotonic() - began < 5.0


# --- Verdrahtung des zweiten Clients ---------------------------------------


def make_cfg(tmp_path, **overrides):
    from kg.config import Config

    return Config(data_dir=tmp_path / "state", anthropic_api_key="sk-anthropic", **overrides)


def test_the_second_client_goes_to_anthropic_unless_the_config_says_otherwise(tmp_path):
    """Fallback-Regel: ohne neue Schlüssel exakt der Weg von vor dem Umbau."""
    llm = build_stop_intent_llm(make_cfg(tmp_path))

    assert llm.api_mode == "anthropic"
    assert llm.model == "claude-sonnet-5"
    assert llm.effort == STOP_INTENT_EFFORT
    # Ein Versuch, nicht zwei: ein Retry im heißen Pfad verdoppelt die Wartezeit.
    assert llm.max_attempts == 1


def test_the_second_client_can_be_pointed_at_a_chat_completions_endpoint(tmp_path):
    llm = build_stop_intent_llm(
        make_cfg(
            tmp_path,
            wake_word_llm_api_mode="chat_completions",
            wake_word_llm_model="google/gemma-4-31B-it",
            wake_word_llm_url="https://example.invalid/v1/chat/completions",
            wake_word_llm_reasoning_effort="none",
            wake_word_llm_timeout_s=6.0,
        )
    )

    assert llm.api_mode == "chat_completions"
    assert llm.url == "https://example.invalid/v1/chat/completions"
    assert llm.reasoning_effort == "none"
    # Das Zeitbudget des Threads ist auch das des HTTP-Aufrufs: ein Request,
    # der länger offen bleibt als der Thread wartet, kostet nur noch Geld.
    assert llm.timeout == 6.0


def test_switching_the_way_off_still_builds_no_client_at_all(tmp_path):
    assert build_stop_intent_llm(make_cfg(tmp_path, wake_word_llm=False)) is None
    assert build_stop_intent_llm(make_cfg(tmp_path, wake_word="")) is None
