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
            timeout_s=900, stop_phrases=PHRASES, wake_word="Utopia", stop_intent=intent
        ),
        intent,
    )


def test_ein_foto_ohne_laufendes_interview_bewirkt_nichts():
    """🔴 Die Umstellung vom 2026-09-01 (Birk: „ein foto duerfte eigentlich
    kein interview mehr eroeffnen, das ist ueberholt").

    Am Booth wird probiert und nachjustiert. Solange jedes Foto ein Interview
    eroeffnete, erzeugte jeder Probeausloeser eine Person an der Wand, die nie
    etwas gesagt hat."""
    t = tracker()
    assert t.photo(at=100.0) == []
    assert t.open_since is None


def test_any_text_message_stops_it():
    t = tracker()
    t.mic_switch(True, at=100.0)
    assert t.text_message(at=160.0) == [Transition("closed", 160.0, "text")]
    assert t.open_since is None


def test_spoken_command_in_the_transcript_stops_it():
    t = tracker()
    t.mic_switch(True, at=100.0)
    assert t.transcript("okay, Interview beendet", at=200.0) == [
        Transition("closed", 200.0, "spoken")
    ]


def test_the_bot_addressed_by_name_stops_it():
    """Both entrances run through find_stop_phrase — spoken text as well."""
    t = SessionTracker(timeout_s=900, stop_phrases=PHRASES, wake_word="Utopia")
    t.mic_switch(True, at=100.0)
    assert t.transcript("Utopia, das Interview ist damit beendet", at=200.0) == [
        Transition("closed", 200.0, "spoken")
    ]


def test_the_bots_name_alone_does_not_stop_it():
    t = SessionTracker(timeout_s=900, stop_phrases=PHRASES, wake_word="Utopia")
    t.mic_switch(True, at=100.0)
    assert t.transcript("Utopia hat mir gestern geholfen", at=150.0) == []
    assert t.open_since == 100.0


def test_a_freely_worded_stop_behind_the_name_closes_the_interview():
    """Birk, 2026-08-30, live at the station: 'Hiermit beende ich das Interview.'

    Verb in front, different inflection — no phrase list has this form, and no
    phrase list ever will. Behind the wake word the LLM decides.
    """
    t, intent = llm_tracker(answer=True)
    t.mic_switch(True, at=100.0)

    assert t.transcript("Utopia, hiermit beende ich das Interview", at=200.0) == [
        Transition("closed", 200.0, "spoken_llm")
    ]
    assert t.open_since is None
    # The whole utterance, not just the part behind the name: "Utopia, ich glaube
    # wir sind fertig" and "Utopia, kannst du gleich aufhören?" differ exactly in
    # what surrounds the command.
    assert intent.asked == ["Utopia, hiermit beende ich das Interview"]


def test_the_mechanical_hit_never_costs_an_llm_call():
    """The fast, free, deterministic normal case stays untouched."""
    t, intent = llm_tracker(answer=True)
    t.mic_switch(True, at=100.0)

    assert t.transcript("okay, Interview beendet", at=200.0) == [
        Transition("closed", 200.0, "spoken")
    ]
    assert intent.asked == []


def test_without_the_wake_word_the_llm_is_never_even_asked():
    """The cost guarantee: no wake word, no call. Otherwise it is the
    continuous listening this design exists to avoid."""
    t, intent = llm_tracker(answer=True)
    t.mic_switch(True, at=100.0)

    assert t.transcript("hiermit beende ich das Interview", at=200.0) == []
    assert t.transcript("wir brauchen mehr Holzbau", at=210.0) == []
    assert intent.asked == []
    assert t.open_since == 100.0


def test_a_no_from_the_llm_leaves_the_interview_running():
    t, intent = llm_tracker(answer=False)
    t.mic_switch(True, at=100.0)

    assert t.transcript("Utopia hat mir gestern geholfen", at=200.0) == []
    assert t.open_since == 100.0
    assert len(intent.asked) == 1


def test_a_failing_llm_leaves_the_interview_running_and_is_logged(caplog):
    """A wrongly ended interview is the more expensive mistake: on a timeout,
    an error or an unusable answer nothing closes."""
    t, _ = llm_tracker(answer=TimeoutError("proxy is dead"))
    t.mic_switch(True, at=100.0)

    with caplog.at_level(logging.ERROR):
        assert t.transcript("Utopia, hiermit beende ich das Interview", at=200.0) == []

    assert t.open_since == 100.0
    assert "proxy is dead" in caplog.text


def test_switched_off_the_tracker_behaves_exactly_as_before():
    t = SessionTracker(timeout_s=900, stop_phrases=PHRASES, wake_word="Utopia")
    t.mic_switch(True, at=100.0)

    assert t.transcript("Utopia, hiermit beende ich das Interview", at=200.0) == []
    assert t.open_since == 100.0


def test_ordinary_transcript_does_not_stop_it():
    t = tracker()
    t.mic_switch(True, at=100.0)
    assert t.transcript("wir brauchen mehr Holzbau", at=150.0) == []
    assert t.open_since == 100.0


def test_timeout_closes_a_forgotten_interview():
    t = tracker()
    t.mic_switch(True, at=100.0)
    assert t.tick(now=999.0) == []
    assert t.tick(now=1000.0) == [Transition("closed", 1000.0, "timeout")]
    assert t.open_since is None


def test_ein_zweites_foto_ersetzt_das_bild_statt_das_interview_zu_teilen():
    """Der Kern der Umstellung: Ein Interview wird nicht mehr zerschnitten.

    Wer im laufenden Gespraech noch einmal ausloest, will ein besseres Bild --
    kein zweites Gespraech. `started_at` bleibt deshalb stehen, sonst waere
    das Transkriptfenster der Person ab hier abgeschnitten."""
    t = tracker()
    t.mic_switch(True, at=100.0)
    t.photo(at=200.0)  # das erste Bild, nachgereicht
    assert t.photo(at=400.0) == [Transition("portrait", 400.0, "replaced_photo")]
    assert t.open_since == 100.0


def test_stop_signals_without_an_open_interview_are_ignored():
    t = tracker()
    assert t.text_message(at=10.0) == []
    assert t.transcript("Interview beendet", at=11.0) == []
    assert t.tick(now=99999.0) == []


def test_kein_foto_verschiebt_den_beginn_des_laufenden_interviews():
    """Egal wie oft ausgeloest wird: Es bleibt EIN Interview, und es bleibt
    bei seinem Beginn. Vorher wanderte `open_since` mit jedem Foto mit."""
    t = tracker()
    t.mic_switch(True, at=100.0)
    t.photo(at=200.0)
    t.photo(at=300.0)
    assert t.open_since == 100.0


def test_a_tracker_can_resume_an_interview_already_open_in_storage():
    t = SessionTracker(timeout_s=900, stop_phrases=PHRASES, open_since=100.0)
    assert t.open_since == 100.0
    # Ein wiederaufgenommenes Interview hat laut Vorgabe schon ein Portraet
    # (`open_without_portrait` steht nicht) -- das Foto ersetzt es also.
    assert t.photo(at=400.0) == [Transition("portrait", 400.0, "replaced_photo")]
