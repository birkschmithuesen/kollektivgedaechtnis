from kg.transcript import TranscriptionEvent, TranscriptLog


def test_event_parsing_is_tolerant_of_missing_and_unknown_fields():
    event = TranscriptionEvent.from_dict(
        {"type": "final", "text": "hallo", "timestamp": 5.0, "something_new": 1}
    )
    assert event.type == "final"
    assert event.text == "hallo"
    assert event.timestamp == 5.0
    assert event.turn_id is None
    assert event.backend == ""
    assert event.extending is None


def test_full_elevenlabs_scribe_event_round_trips():
    """The verified 10-field contract (docs/stt-contract.md)."""
    payload = {
        "recognizer_id": "left",
        "type": "final",
        "text": "Wir bauen zu viel Neues.",
        "timestamp": 1754990000.5,
        "backend": "elevenlabs-scribe",
        "status": None,
        "confidence": None,
        "turn_id": "01K2ABCDEF",
        "partial_seq": None,
        "extending": None,
    }
    event = TranscriptionEvent.from_dict(payload)
    assert event.backend == "elevenlabs-scribe"
    assert event.turn_id == "01K2ABCDEF"
    assert event.extending is None


def test_extending_is_tolerated_but_never_changes_handling():
    """Scribe revises partials; we only ever consume finals (spec 4)."""
    revision = TranscriptionEvent.from_dict(
        {"type": "partial", "text": "Wir bauen", "timestamp": 1.0, "extending": False}
    )
    confirmed = TranscriptionEvent.from_dict(
        {"type": "partial", "text": "Wir bauen", "timestamp": 1.0, "extending": True}
    )
    assert revision.extending is False
    assert confirmed.extending is True


def test_append_and_read_range_filters_to_finals_in_window(tmp_path):
    log = TranscriptLog(tmp_path / "transcript.jsonl")
    log.append(TranscriptionEvent(type="final", text="vor dem Fenster", timestamp=10.0))
    log.append(TranscriptionEvent(type="partial", text="ignoriert", timestamp=25.0))
    log.append(TranscriptionEvent(type="final", text="erster Satz", timestamp=20.0))
    log.append(TranscriptionEvent(type="final", text="zweiter Satz", timestamp=30.0))
    log.append(TranscriptionEvent(type="final", text="danach", timestamp=99.0))

    events = log.read_range(15.0, 40.0)
    assert [e.text for e in events] == ["erster Satz", "zweiter Satz"]
    assert log.text_between(15.0, 40.0) == "erster Satz zweiter Satz"


def test_reads_survive_a_reopened_log(tmp_path):
    path = tmp_path / "transcript.jsonl"
    TranscriptLog(path).append(TranscriptionEvent(type="final", text="a", timestamp=1.0))
    TranscriptLog(path).append(TranscriptionEvent(type="final", text="b", timestamp=2.0))
    assert TranscriptLog(path).text_between(0.0, 10.0) == "a b"
