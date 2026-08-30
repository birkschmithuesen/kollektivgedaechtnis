import logging

from kg.session import SessionTracker, Transition

PHRASES = ["Interview beendet"]


def tracker():
    return SessionTracker(timeout_s=900, stop_phrases=PHRASES)


class CountingIntent:
    """The LLM gate, faked: answers what it was told and counts every ask.

    The counting is the point in half these tests — the wake word is the only
    thing that may ever buy an LLM call, and a counter is the only way to prove
    it (spec: no continuous listening).
    """

    def __init__(self, answer=True):
        self.answer = answer
        self.asked: list[str] = []

    def __call__(self, text: str) -> bool:
        self.asked.append(text)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def llm_tracker(answer=True):
    intent = CountingIntent(answer)
    return (
        SessionTracker(
            timeout_s=900, stop_phrases=PHRASES, wake_word="Robo", stop_intent=intent
        ),
        intent,
    )


def test_photo_opens_an_interview():
    t = tracker()
    assert t.photo(at=100.0) == [Transition("opened", 100.0, "photo")]
    assert t.open_since == 100.0


def test_any_text_message_stops_it():
    t = tracker()
    t.photo(at=100.0)
    assert t.text_message(at=160.0) == [Transition("closed", 160.0, "text")]
    assert t.open_since is None


def test_spoken_command_in_the_transcript_stops_it():
    t = tracker()
    t.photo(at=100.0)
    assert t.transcript("okay, Interview beendet", at=200.0) == [
        Transition("closed", 200.0, "spoken")
    ]


def test_the_bot_addressed_by_name_stops_it():
    """Both entrances run through find_stop_phrase — spoken text as well."""
    t = SessionTracker(timeout_s=900, stop_phrases=PHRASES, wake_word="Robo")
    t.photo(at=100.0)
    assert t.transcript("Robo, das Interview ist damit beendet", at=200.0) == [
        Transition("closed", 200.0, "spoken")
    ]


def test_the_bots_name_alone_does_not_stop_it():
    t = SessionTracker(timeout_s=900, stop_phrases=PHRASES, wake_word="Robo")
    t.photo(at=100.0)
    assert t.transcript("Robo hat mir gestern geholfen", at=150.0) == []
    assert t.open_since == 100.0


def test_a_freely_worded_stop_behind_the_name_closes_the_interview():
    """Birk, 2026-08-30, live at the station: 'Hiermit beende ich das Interview.'

    Verb in front, different inflection — no phrase list has this form, and no
    phrase list ever will. Behind the wake word the LLM decides.
    """
    t, intent = llm_tracker(answer=True)
    t.photo(at=100.0)

    assert t.transcript("Robo, hiermit beende ich das Interview", at=200.0) == [
        Transition("closed", 200.0, "spoken_llm")
    ]
    assert t.open_since is None
    # The whole utterance, not just the part behind the name: "Robo, ich glaube
    # wir sind fertig" and "Robo, kannst du gleich aufhören?" differ exactly in
    # what surrounds the command.
    assert intent.asked == ["Robo, hiermit beende ich das Interview"]


def test_the_mechanical_hit_never_costs_an_llm_call():
    """The fast, free, deterministic normal case stays untouched."""
    t, intent = llm_tracker(answer=True)
    t.photo(at=100.0)

    assert t.transcript("okay, Interview beendet", at=200.0) == [
        Transition("closed", 200.0, "spoken")
    ]
    assert intent.asked == []


def test_without_the_wake_word_the_llm_is_never_even_asked():
    """The cost guarantee: no wake word, no call. Otherwise it is the
    continuous listening this design exists to avoid."""
    t, intent = llm_tracker(answer=True)
    t.photo(at=100.0)

    assert t.transcript("hiermit beende ich das Interview", at=200.0) == []
    assert t.transcript("wir brauchen mehr Holzbau", at=210.0) == []
    assert intent.asked == []
    assert t.open_since == 100.0


def test_a_no_from_the_llm_leaves_the_interview_running():
    t, intent = llm_tracker(answer=False)
    t.photo(at=100.0)

    assert t.transcript("Robo hat mir gestern geholfen", at=200.0) == []
    assert t.open_since == 100.0
    assert len(intent.asked) == 1


def test_a_failing_llm_leaves_the_interview_running_and_is_logged(caplog):
    """A wrongly ended interview is the more expensive mistake: on a timeout,
    an error or an unusable answer nothing closes."""
    t, _ = llm_tracker(answer=TimeoutError("proxy is dead"))
    t.photo(at=100.0)

    with caplog.at_level(logging.ERROR):
        assert t.transcript("Robo, hiermit beende ich das Interview", at=200.0) == []

    assert t.open_since == 100.0
    assert "proxy is dead" in caplog.text


def test_switched_off_the_tracker_behaves_exactly_as_before():
    t = SessionTracker(timeout_s=900, stop_phrases=PHRASES, wake_word="Robo")
    t.photo(at=100.0)

    assert t.transcript("Robo, hiermit beende ich das Interview", at=200.0) == []
    assert t.open_since == 100.0


def test_ordinary_transcript_does_not_stop_it():
    t = tracker()
    t.photo(at=100.0)
    assert t.transcript("wir brauchen mehr Holzbau", at=150.0) == []
    assert t.open_since == 100.0


def test_timeout_closes_a_forgotten_interview():
    t = tracker()
    t.photo(at=100.0)
    assert t.tick(now=999.0) == []
    assert t.tick(now=1000.0) == [Transition("closed", 1000.0, "timeout")]
    assert t.open_since is None


def test_a_new_photo_implicitly_closes_the_running_interview():
    t = tracker()
    t.photo(at=100.0)
    assert t.photo(at=400.0) == [
        Transition("closed", 400.0, "new_photo"),
        Transition("opened", 400.0, "photo"),
    ]
    assert t.open_since == 400.0


def test_stop_signals_without_an_open_interview_are_ignored():
    t = tracker()
    assert t.text_message(at=10.0) == []
    assert t.transcript("Interview beendet", at=11.0) == []
    assert t.tick(now=99999.0) == []


def test_only_one_interview_can_be_open_at_a_time():
    t = tracker()
    t.photo(at=100.0)
    t.photo(at=200.0)
    t.photo(at=300.0)
    assert t.open_since == 300.0


def test_a_tracker_can_resume_an_interview_already_open_in_storage():
    t = SessionTracker(timeout_s=900, stop_phrases=PHRASES, open_since=100.0)
    assert t.open_since == 100.0
    assert t.photo(at=400.0) == [
        Transition("closed", 400.0, "new_photo"),
        Transition("opened", 400.0, "photo"),
    ]
