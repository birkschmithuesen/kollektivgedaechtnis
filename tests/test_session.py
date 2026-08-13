from kg.session import SessionTracker, Transition

PHRASES = ["Interview beendet"]


def tracker():
    return SessionTracker(timeout_s=900, stop_phrases=PHRASES)


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
