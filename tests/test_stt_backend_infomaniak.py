"""Das Batch-STT-Backend für den externen Server (docs/stt-contract.md §2).

Die Datei unter `stt_backends/` gehört nicht zu diesem Paket — sie wird in den
fundusbot-Checkout kopiert (stt_backends/README.md). Deshalb wird sie hier über
ihren Pfad geladen und nicht importiert: sie darf gerade NICHT Teil von `kg`
werden, und getestet werden muss sie trotzdem.

Kein Test geht ins Netz; Upload, Polling und Download sind injiziert — dieselbe
Disziplin wie überall sonst im Repo.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import threading
import time
import wave
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "stt_backends" / "infomaniak_whisper_backend.py"
_spec = importlib.util.spec_from_file_location("infomaniak_whisper_backend", _PATH)
backend_module = importlib.util.module_from_spec(_spec)
# Vor dem Ausführen registrieren: die Ersatz-Ereignisklasse im Modul ist ein
# dataclass, und dataclasses schlägt in `sys.modules` nach, um die (durch
# `from __future__ import annotations`) verstringten Typen aufzulösen.
sys.modules[_spec.name] = backend_module
_spec.loader.exec_module(backend_module)

BACKEND_NAME = backend_module.BACKEND_NAME
InfomaniakWhisperBackend = backend_module.InfomaniakWhisperBackend
TranscriptionError = backend_module.TranscriptionError
encode_wav = backend_module.encode_wav
fetch_transcript = backend_module.fetch_transcript
submit_transcription = backend_module.submit_transcription


def pcm(seconds: float = 1.0, value: int = 1000) -> bytes:
    """Rohes int16-Mono-PCM bei 16 kHz — was der VadChunker liefert."""
    return (value.to_bytes(2, "little", signed=True)) * int(16000 * seconds)


class FakeArray:
    """Steht für das numpy-Array aus dem VadChunker. numpy ist in diesem Repo
    keine Abhängigkeit; das Backend kommt deshalb ohne numpy-Import aus und
    darf nur `.dtype`, `.astype` und `.tobytes` benutzen."""

    def __init__(self, data: bytes, dtype: str = "int16"):
        self.data = data
        self.dtype = type("D", (), {"name": dtype})()

    def astype(self, name):
        return FakeArray(self.data, dtype=str(name))

    def tobytes(self):
        return self.data


class FakeBus:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


# -- WAV: was hochgeladen wird ----------------------------------------------


def test_the_upload_is_16khz_mono_16bit_wav():
    """Infomaniak nimmt mp3/wav/…; WAV ist das einzige Format, das ohne
    zusätzliche Abhängigkeit aus der Standardbibliothek fällt, und der Server
    darf keine neue Abhängigkeit brauchen."""
    data = encode_wav(pcm(0.5))

    with wave.open(io.BytesIO(data), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == 16000
        assert handle.getnframes() == 8000


# -- absenden ---------------------------------------------------------------


def test_the_submit_goes_to_the_v1_endpoint_and_returns_the_batch_id():
    """Gemessen am 2026-08-31: unter /2/.../openai/v1/ antwortet dieser
    Endpunkt 404. Die Transkription liegt auf /1/, anders als der
    Chat-Endpunkt — das ist die Sorte Detail, die man genau einmal herausfindet
    und danach festschreibt."""
    seen = {}

    def fake_post(url, headers, files, data, timeout):
        seen.update(url=url, headers=headers, files=files, data=data, timeout=timeout)
        return {"batch_id": "abc-123"}

    batch_id = submit_transcription(
        b"WAVE",
        base_url="https://api.infomaniak.com",
        product_id="110416",
        api_key="sk-infomaniak",
        model="whisper",
        language="de",
        timeout=30.0,
        post=fake_post,
    )

    assert batch_id == "abc-123"
    assert seen["url"] == "https://api.infomaniak.com/1/ai/110416/openai/audio/transcriptions"
    assert seen["headers"]["Authorization"] == "Bearer sk-infomaniak"
    assert seen["data"] == {"model": "whisper", "language": "de",
                            "response_format": "verbose_json"}
    assert "file" in seen["files"]


def test_a_submit_without_a_batch_id_is_an_error():
    with pytest.raises(TranscriptionError):
        submit_transcription(
            b"WAVE", base_url="b", product_id="1", api_key="k", model="whisper",
            language="de", timeout=1.0, post=lambda **kwargs: {"error": "nope"},
        )


# -- pollen -----------------------------------------------------------------


def result_payload(text: str) -> dict:
    """`data` kommt als JSON-STRING zurück, nicht als Objekt (gemessen)."""
    return {
        "status": "success",
        "data": json.dumps(
            {
                "text": text,
                "segments": [{"start": 0.0, "end": 1.2, "text": text}],
                "language": "de",
                "duration": 1.2,
            }
        ),
    }


def test_polling_waits_for_success_and_unpacks_the_json_string():
    replies = [{"status": "processing"}, {"status": "processing"},
               result_payload("Beton spritzen mit Drohnen")]
    seen = []
    slept = []

    def fake_get(url, headers, timeout):
        seen.append(url)
        return replies.pop(0)

    text = fetch_transcript(
        "abc-123",
        base_url="https://api.infomaniak.com",
        product_id="110416",
        api_key="sk-infomaniak",
        timeout=30.0,
        poll_interval_s=0.0,
        get_json=fake_get,
        sleep=slept.append,
    )

    assert text == "Beton spritzen mit Drohnen"
    assert seen[0] == "https://api.infomaniak.com/1/ai/110416/results/abc-123"
    assert len(seen) == 3
    assert len(slept) == 2


def test_polling_gives_up_instead_of_waiting_forever():
    """Ein Auftrag, der nie fertig wird, darf den Worker nicht blockieren —
    dahinter stauen sich sonst alle folgenden Chunks."""
    with pytest.raises(TranscriptionError, match="never"):
        fetch_transcript(
            "abc-123", base_url="b", product_id="1", api_key="k", timeout=0.0,
            poll_interval_s=0.0, get_json=lambda **kwargs: {"status": "processing"},
            sleep=lambda s: None,
        )


def test_a_failed_batch_is_reported_and_not_waited_out():
    with pytest.raises(TranscriptionError, match="error"):
        fetch_transcript(
            "abc-123", base_url="b", product_id="1", api_key="k", timeout=5.0,
            poll_interval_s=0.0, get_json=lambda **kwargs: {"status": "error"},
            sleep=lambda s: None,
        )


# -- das Backend ------------------------------------------------------------


def make_backend(bus=None, transcribe=None, **overrides):
    kwargs = dict(
        base_url="https://api.infomaniak.com",
        product_id="110416",
        api_key="sk-infomaniak",
        model="whisper",
        language="de",
        start_worker=False,
    )
    kwargs.update(overrides)
    backend = InfomaniakWhisperBackend(bus or FakeBus(), **kwargs)
    if transcribe is not None:
        backend.transcribe = transcribe
    return backend


def test_the_backend_is_segmented_not_streaming():
    """Der Kern des Auftrags: `wants_streaming() is False` schaltet im
    Recognizer den VadChunker davor, und genau dadurch bleibt ohne Streaming
    alles erhalten, was die Pipeline braucht."""
    backend = make_backend()

    assert backend.wants_streaming() is False


def test_process_chunk_returns_nothing_synchronously():
    """Wie beim WhisperBackend: der Worker published später auf den Bus, der
    Aufrufer bekommt sofort einen leeren Iterator und blockiert nie."""
    backend = make_backend()

    assert list(backend.process_chunk(FakeArray(pcm(0.1)), "regie", "turn-1")) == []


def test_a_chunk_becomes_one_final_event_with_the_same_turn_id():
    """Der Core konsumiert ausschließlich `final` und sieht nicht, woher es
    kommt (docs/stt-contract.md). Die turn_id des VadChunkers reist mit, damit
    die Zuordnung erhalten bleibt."""
    bus = FakeBus()
    backend = make_backend(bus, transcribe=lambda wav: "Wir bauen im Bestand")

    backend.handle_chunk("regie", pcm(1.0), "turn-42", time.time())

    assert len(bus.events) == 1
    event = bus.events[0]
    assert event.type == "final"
    assert event.text == "Wir bauen im Bestand"
    assert event.turn_id == "turn-42"
    assert event.recognizer_id == "regie"
    assert event.backend == BACKEND_NAME


def test_the_event_carries_exactly_the_contracted_fields():
    """Zehn Felder, wie in docs/stt-contract.md verzeichnet. Ein Feld mehr
    bräche den Decoder des Cores nicht, ein Feld weniger schon."""
    bus = FakeBus()
    backend = make_backend(bus, transcribe=lambda wav: "text")

    backend.handle_chunk("regie", pcm(0.2), "turn-1", time.time())

    fields = vars(bus.events[0]).keys()
    assert set(fields) == {
        "recognizer_id", "type", "text", "timestamp", "backend",
        "status", "confidence", "turn_id", "partial_seq", "extending",
    }


def test_silence_publishes_nothing():
    """Whisper liefert für ein Stück Raumton gern einen leeren Text oder eine
    Höflichkeitsfloskel aus dem Nichts. Leer heißt: kein Event, sonst steht im
    Transkript eine Äußerung, die niemand gemacht hat."""
    bus = FakeBus()
    backend = make_backend(bus, transcribe=lambda wav: "   ")

    backend.handle_chunk("regie", pcm(0.2), "turn-1", time.time())

    assert bus.events == []


def test_a_failed_upload_drops_the_chunk_and_keeps_the_server_running():
    """„STT unreachable is a normal on-site state" — auf der Serverseite
    genauso wie im Core. Ein Fehlschlag kostet einen Chunk, nie den Betrieb."""
    bus = FakeBus()
    calls = []

    def flaky(wav):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("connection reset")
        return "der zweite Versuch"

    backend = make_backend(bus, transcribe=flaky)

    backend.handle_chunk("regie", pcm(0.2), "turn-1", time.time())  # darf nicht werfen
    backend.handle_chunk("regie", pcm(0.2), "turn-2", time.time())

    assert [e.text for e in bus.events] == ["der zweite Versuch"]


def test_a_chunk_is_never_retried():
    """Ein Chunk, der scheitert, ist verloren — kein zweiter Upload. Beim
    nächsten Sprechen kommt der nächste Chunk, und der Gast wartet nicht auf
    eine Wiederholung von vorgestern."""
    calls = []

    def dead(wav):
        calls.append(1)
        raise OSError("boom")

    backend = make_backend(transcribe=dead)
    backend.handle_chunk("regie", pcm(0.2), "turn-1", time.time())

    assert len(calls) == 1


def test_an_oversized_chunk_is_dropped_before_the_upload():
    """25 MB pro Datei ist die Grenze des Anbieters. Ein Upload, der sie
    reißt, kostet die volle Wartezeit und scheitert dann — also vorher prüfen."""
    uploaded = []
    backend = make_backend(transcribe=lambda wav: uploaded.append(wav) or "text")
    backend.max_upload_bytes = 1024

    backend.handle_chunk("regie", pcm(1.0), "turn-1", time.time())

    assert uploaded == []


def test_the_worker_thread_drains_the_queue():
    """Die Verdrahtung von process_chunk über die Queue bis zum Bus — der eine
    Test, der den echten Thread laufen lässt."""
    bus = FakeBus()
    done = threading.Event()

    def transcribe(wav):
        done.set()
        return "aus dem Worker"

    backend = make_backend(bus, transcribe=transcribe, start_worker=True)
    try:
        backend.process_chunk(FakeArray(pcm(0.1)), "regie", "turn-9")
        assert done.wait(timeout=5.0)
        for _ in range(50):
            if bus.events:
                break
            time.sleep(0.02)
    finally:
        backend.close()

    assert [e.text for e in bus.events] == ["aus dem Worker"]
    assert bus.events[0].turn_id == "turn-9"


def test_a_float_chunk_is_converted_before_it_is_sent():
    """Der VadChunker liefert int16; ein anderer Weg in den Server könnte
    float32 liefern. Die Konvertierung passiert einmal, hier."""
    backend = make_backend()
    seen = FakeArray(b"\x00\x00", dtype="float32")

    backend.process_chunk(seen, "regie", "turn-1")

    recognizer_id, data, turn_id, _submitted = backend.queue.get_nowait()
    assert (recognizer_id, turn_id) == ("regie", "turn-1")
    assert data == b"\x00\x00"
