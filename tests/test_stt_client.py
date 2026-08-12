import pytest

from kg.stt_client import STTClient
from kg.transcript import TranscriptLog


class FakeStream:
    """Yields SSE lines, then raises to simulate a dropped connection."""

    def __init__(self, batches):
        self.batches = list(batches)
        self.calls = 0

    async def __call__(self, url):
        self.calls += 1
        if not self.batches:
            raise RuntimeError("stt unreachable")
        for line in self.batches.pop(0):
            yield line


async def test_finals_are_logged_and_dispatched(tmp_path):
    log = TranscriptLog(tmp_path / "t.jsonl")
    finals, partials = [], []
    stream = FakeStream(
        [
            [
                # Realistic elevenlabs-scribe shape incl. the 10th field.
                'data: {"type": "partial", "text": "hal", "timestamp": 1.0,'
                ' "backend": "elevenlabs-scribe", "extending": false}',
                "",
                ": keep-alive",
                'data: {"type": "final", "text": "hallo", "timestamp": 2.0,'
                ' "backend": "elevenlabs-scribe", "turn_id": "01K2AB"}',
                "",
            ]
        ]
    )
    client = STTClient(
        url="http://stt",
        log=log,
        on_final=finals.append,
        on_partial=partials.append,
        line_source=stream,
        max_cycles=1,
    )

    await client.run()

    assert [e.text for e in finals] == ["hallo"]
    assert [e.text for e in partials] == ["hal"]
    # Only finals are persisted (spec 4).
    assert log.text_between(0.0, 10.0) == "hallo"


async def test_reconnects_after_a_dropped_stream(tmp_path):
    log = TranscriptLog(tmp_path / "t.jsonl")
    states = []
    stream = FakeStream(
        [
            ['data: {"type": "final", "text": "eins", "timestamp": 1.0}', ""],
            ['data: {"type": "final", "text": "zwei", "timestamp": 2.0}', ""],
        ]
    )
    client = STTClient(
        url="http://stt",
        log=log,
        on_final=lambda e: None,
        line_source=stream,
        on_state=states.append,
        backoff=lambda attempt: 0.0,
        max_cycles=3,
    )

    await client.run()

    assert stream.calls == 3
    # third cycle raised -> disconnected state reported, run() did not raise
    assert states[-1] is False
    assert log.text_between(0.0, 10.0) == "eins zwei"
