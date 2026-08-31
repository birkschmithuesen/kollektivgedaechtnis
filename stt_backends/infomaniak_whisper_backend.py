"""Infomaniak Whisper als Backend für den externen STT-Server.

**Diese Datei gehört nicht zum Kollektivgedächtnis-Paket.** Sie wird in den
fundusbot-Checkout kopiert (`fundusapps/stt_server/backends/`); wie sie dort
registriert wird, steht in `stt_backends/README.md`. Sie liegt hier, weil der
STT-Server ein fremdes Repo ist, das nicht gegabelt wird (spec 4) — und weil
sie so in der Testsuite dieses Repos steht statt in niemandes.

## Warum Batch überhaupt geht

Der Server kennt zwei Betriebsarten, und die zweite ist genau dieser Fall
(`backends/base.py`):

> *Segmented (wants_streaming() is False): the recognizer accumulates audio
> between VAD trigger events and submits one buffered chunk per phrase. The
> backend may transcribe asynchronously and publish events to the bus on its
> own schedule.*

Damit bleibt ohne Streaming alles erhalten, was die Pipeline braucht:

1. **`final`-Events** sind unverändert. Der Core (`kg/stt_client.py`)
   konsumiert ohnehin NUR `type == "final"` und merkt nicht, woher sie kommen.
   Deshalb ist am Core nichts zu ändern.
2. **Die Segmentierung** macht der vorhandene `VadChunker` (`vad.py`) statt
   des Server-VAD von ElevenLabs: Energieschwelle, `min_silence_ms` /
   `min_speech_ms`. Richtwert 5-15 s Sprache pro Chunk.
3. **Wake-Word und Stopp-Erkennung** arbeiten auf `final`-Texten und laufen
   weiter, nur mit Chunk-Latenz. Der 15-Minuten-Timeout und die Textnachricht
   an den Bot bleiben als sichere Wege bestehen.
4. **`partial`-Events entfallen.** Sie gehen laut STT-Vertrag ausschließlich an
   die Operator-Anzeige, nicht in die Pipeline-Logik — nichts Funktionales
   hängt daran. Die Status-Partials („speech_detected", „transcribing")
   published der Recognizer selbst, sobald `wants_streaming()` False ist; die
   Anzeige bleibt also nicht stumm.
5. **`turn_id`** erzeugt der `VadChunker` (ULID) und reicht sie durch bis
   hierher, damit die Zuordnung Äußerung ↔ Text erhalten bleibt.

## Der Endpunkt (gemessen am 2026-08-31)

* Absenden: ``POST {base}/1/ai/{produkt}/openai/audio/transcriptions``,
  multipart mit `file`, `model=whisper`, `language=de`,
  `response_format=verbose_json` → ``{"batch_id": "..."}``.
  **Nicht** unter ``/2/.../openai/v1/`` — dort antwortet er 404. Das ist die
  Sorte Detail, die man genau einmal herausfindet.
* Ergebnis: ``GET {base}/1/ai/{produkt}/results/{batch_id}`` →
  ``{"status": "success", "data": "<JSON-String>"}``. `data` ist ein STRING,
  der `text`, `segments`, `language` und `duration` enthält.
* Grenzen: 25 MB pro Datei.

Gemessene Ende-zu-Ende-Latenz (Upload + Transkription + Polling): 2,9 s für
5,3 s Audio, 3,6 s für 10,7 s, 3,8 s für 21,4 s, 4,7 s für 32,0 s. **Der
Overhead ist mit ~3 s fast konstant, unabhängig von der Chunklänge.** Längere
Chunks sind also effizienter, aber träger; bei 10-s-Chunks liegt der Text rund
13 s nach Sprechbeginn vor. Wer die VAD-Parameter verstellt, verschiebt genau
diesen Handel.

## Fehlerverhalten

Ein fehlgeschlagener Upload oder Poll darf **nie** den Server anhalten: loggen,
Chunk verwerfen, weiterlaufen — dieselbe Haltung, die `STTClient.run()` auf der
Konsumentenseite schon hat („STT unreachable is a normal on-site state"). Und
kein Retry pro Chunk: eine Wiederholung landet nach dem nächsten Satz und
verwirrt mehr, als sie rettet.

## Zwei Import-Eigenheiten, beide Absicht

* **Kein `import numpy`.** Der Chunk kommt als numpy-Array herein, aber
  gebraucht werden nur `.dtype`, `.astype` und `.tobytes`. So ist die Datei
  auch dort importierbar, wo numpy nicht installiert ist — nämlich in der
  Testsuite des Kollektivgedächtnis-Repos.
* **Die fundusbot-Importe sind tolerant.** Außerhalb des Checkouts fällt die
  Datei auf eine lokale, feldgleiche Ereignisklasse zurück, damit sie testbar
  bleibt. Im Checkout wird immer die echte benutzt.
"""

from __future__ import annotations

import io
import json
import logging
import queue
import threading
import time
import wave

try:  # im fundusbot-Checkout: die echten Klassen
    from fundusapps.stt_server.backends.base import RecognizerBackend
    from fundusapps.stt_server.events import TranscriptionEvent
except ImportError:  # außerhalb: nur damit Import und Test funktionieren
    from dataclasses import dataclass
    from typing import Optional

    class RecognizerBackend:  # type: ignore[no-redef]
        def __init__(self, event_bus):
            self._bus = event_bus

    @dataclass
    class TranscriptionEvent:  # type: ignore[no-redef]
        """Feldgleiche Kopie von `fundusapps/stt_server/events.py` (zehn Felder,
        docs/stt-contract.md). Steht hier NUR für den Import außerhalb des
        Checkouts; wer sie ändert, muss dort nachziehen."""

        recognizer_id: str
        type: str
        text: str
        timestamp: float
        backend: str
        status: Optional[str] = None
        confidence: Optional[float] = None
        turn_id: Optional[str] = None
        partial_seq: Optional[int] = None
        extending: Optional[bool] = None


log = logging.getLogger(__name__)

#: Der Name auf der Leitung, im Subparser und im `backend`-Feld jedes Events.
BACKEND_NAME = "infomaniak-whisper"

#: Der Recognizer resampled auf 16 kHz, bevor er den VadChunker füttert.
SAMPLE_RATE = 16000

#: Grenze des Anbieters. Bei 16 kHz/16 bit mono sind das rund 13 Minuten am
#: Stück — eine VAD-Segmentierung erreicht das nie, ein hängengebliebener
#: Puffer schon.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

#: Sekunden zwischen zwei Nachfragen. Der Overhead liegt bei ~3 s, häufiger zu
#: fragen bringt nichts und belastet nur die Quote.
POLL_INTERVAL_S = 0.5

#: „success" beendet das Warten, diese hier beenden es ebenfalls — nur ohne
#: Ergebnis. Alles andere heißt weiterwarten, begrenzt vom Zeitbudget: die
#: Namen der Zwischenzustände sind nicht abschließend bekannt, und ein
#: unbekannter Status darf nicht als Fehler durchgehen.
_DONE = "success"
_FAILED = ("error", "failed", "aborted", "canceled", "cancelled")


class TranscriptionError(RuntimeError):
    """Ein Chunk wurde nicht zu Text. Ein Typ, den der Worker fängt."""


def encode_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """int16-Mono-PCM in einen WAV-Container, ohne neue Abhängigkeit.

    WAV statt mp3, weil `wave` in der Standardbibliothek liegt: der STT-Server
    darf für dieses Backend keinen Encoder mitschleppen. Der Aufpreis ist
    Bandbreite (rund 32 kB pro Sekunde Sprache), und die ist im lokalen Netz
    der Station nicht die knappe Ressource — die ~3 s Overhead sind es.
    """
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)
    return buffer.getvalue()


def _default_post_multipart(url, headers, files, data, timeout) -> dict:
    """Multipart-Upload mit dem, was im Checkout schon da ist."""
    try:
        import requests
    except ImportError:
        requests = None
    if requests is not None:
        response = requests.post(url, headers=headers, files=files, data=data, timeout=timeout)
        response.raise_for_status()
        return response.json()

    import httpx

    response = httpx.post(url, headers=headers, files=files, data=data, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _default_get_json(url, headers, timeout) -> dict:
    try:
        import requests
    except ImportError:
        requests = None
    if requests is not None:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.json()

    import httpx

    response = httpx.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def submit_transcription(
    wav: bytes,
    *,
    base_url: str,
    product_id: str,
    api_key: str,
    model: str,
    language: str,
    timeout: float,
    post=_default_post_multipart,
) -> str:
    """Den Chunk absenden und die `batch_id` zurückgeben. `post` ist
    injizierbar, damit kein Test ins Netz geht."""
    url = f"{base_url.rstrip('/')}/1/ai/{product_id}/openai/audio/transcriptions"
    payload = post(
        url=url,
        headers={"Authorization": f"Bearer {api_key}"},
        files={"file": ("chunk.wav", wav, "audio/wav")},
        data={"model": model, "language": language, "response_format": "verbose_json"},
        timeout=timeout,
    )
    batch_id = (payload or {}).get("batch_id")
    if not batch_id:
        raise TranscriptionError(f"no batch_id in the submit response: {str(payload)[:200]!r}")
    return str(batch_id)


def fetch_transcript(
    batch_id: str,
    *,
    base_url: str,
    product_id: str,
    api_key: str,
    timeout: float,
    poll_interval_s: float = POLL_INTERVAL_S,
    get_json=_default_get_json,
    sleep=time.sleep,
) -> str:
    """Auf das Ergebnis warten und den Text herausholen.

    Das Zeitbudget ist hart: ein Auftrag, der nie fertig wird, würde sonst den
    Worker blockieren, und dahinter stauen sich alle folgenden Chunks — aus
    einer verlorenen Äußerung würde ein verlorenes Interview.
    """
    url = f"{base_url.rstrip('/')}/1/ai/{product_id}/results/{batch_id}"
    headers = {"Authorization": f"Bearer {api_key}"}
    deadline = time.monotonic() + timeout
    while True:
        payload = get_json(url=url, headers=headers, timeout=timeout) or {}
        status = str(payload.get("status", "")).lower()
        if status == _DONE:
            break
        if status in _FAILED:
            raise TranscriptionError(f"the transcription batch ended as {status!r}")
        if time.monotonic() >= deadline:
            raise TranscriptionError(
                f"batch {batch_id} was still {status!r} and never finished within {timeout}s"
            )
        sleep(poll_interval_s)

    data = payload.get("data")
    if isinstance(data, str):
        # Gemessen: `data` ist ein JSON-STRING, kein Objekt.
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            raise TranscriptionError(f"result data is not json: {exc}") from exc
    if not isinstance(data, dict):
        raise TranscriptionError(f"result data has no text: {str(data)[:120]!r}")
    return str(data.get("text") or "")


def _pcm_bytes(audio) -> bytes:
    """Rohes int16-PCM aus dem Chunk des VadChunkers — ohne numpy zu importieren
    (Modul-Docstring). `dtype` fehlt nur bei Stand-ins aus den Tests."""
    dtype = getattr(audio, "dtype", None)
    if dtype is not None and getattr(dtype, "name", "") != "int16":
        audio = audio.astype("int16")
    return audio.tobytes()


class InfomaniakWhisperBackend(RecognizerBackend):
    """Queue + Worker-Thread, nach dem Muster von `whisper_backend.py`.

    `process_chunk` legt den Chunk in die Queue und gibt sofort einen leeren
    Iterator zurück; der Worker lädt hoch, pollt und published pro Ergebnis ein
    `final`-Event mit derselben `turn_id`.
    """

    def __init__(
        self,
        event_bus,
        *,
        base_url: str = "https://api.infomaniak.com",
        product_id: str = "110416",
        api_key: str = "",
        model: str = "whisper",
        language: str = "de",
        request_timeout_s: float = 60.0,
        poll_interval_s: float = POLL_INTERVAL_S,
        start_worker: bool = True,
        post=_default_post_multipart,
        get_json=_default_get_json,
    ):
        super().__init__(event_bus)
        self.base_url = base_url
        self.product_id = product_id
        self.api_key = api_key
        self.model = model
        self.language = language
        self.request_timeout_s = request_timeout_s
        self.poll_interval_s = poll_interval_s
        self.max_upload_bytes = MAX_UPLOAD_BYTES
        self._post = post
        self._get_json = get_json

        self.queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._worker = None
        if start_worker:
            self._worker = threading.Thread(
                target=self._run_worker, daemon=True, name="infomaniak-whisper"
            )
            self._worker.start()
        logging.info("InfomaniakWhisperBackend ready (product %s, model %s).", product_id, model)

    # -- die Schnittstelle des Servers --------------------------------------

    def wants_streaming(self) -> bool:
        """False — und das ist der ganze Trick. Der Recognizer schaltet damit
        den VadChunker davor und schickt einen gepufferten Chunk pro Äußerung."""
        return False

    @classmethod
    def from_args(cls, event_bus, args) -> "InfomaniakWhisperBackend":
        import os

        key_env = getattr(args, "api_key_env", "INFOMANIAK_API_KEY")
        api_key = os.environ.get(key_env, "")
        if not api_key:
            # Laut und früh: ohne Schlüssel wird jeder Chunk stumm verworfen,
            # und ein STT-Server, der scheinbar läuft und nichts liefert, ist
            # das teuerste Fehlerbild am Aufbautag.
            logging.error(
                "%s is empty — set it before starting, or every chunk will be dropped", key_env
            )
        return cls(
            event_bus=event_bus,
            base_url=getattr(args, "base_url", "https://api.infomaniak.com"),
            product_id=str(getattr(args, "product_id", "110416")),
            api_key=api_key,
            model=getattr(args, "model", "whisper"),
            language=getattr(args, "language", "de"),
            request_timeout_s=float(getattr(args, "request_timeout", 60.0)),
        )

    def process_chunk(self, audio, recognizer_id: str, turn_id=None):
        """Einreihen und sofort zurück. Der Aufrufer ist der Audio-Thread und
        darf unter keinen Umständen auf ein Netz warten."""
        self.queue.put((recognizer_id, _pcm_bytes(audio), turn_id, time.time()))
        return iter(())

    def close(self) -> None:
        self._stop.set()
        if self._worker is not None:
            self._worker.join(timeout=5.0)

    # -- der Weg eines Chunks ------------------------------------------------

    def transcribe(self, wav: bytes) -> str:
        """WAV rein, Text raus. Eine Methode, damit die Tests sie ersetzen
        können, ohne Upload und Polling nachzubauen."""
        batch_id = submit_transcription(
            wav,
            base_url=self.base_url,
            product_id=self.product_id,
            api_key=self.api_key,
            model=self.model,
            language=self.language,
            timeout=self.request_timeout_s,
            post=self._post,
        )
        return fetch_transcript(
            batch_id,
            base_url=self.base_url,
            product_id=self.product_id,
            api_key=self.api_key,
            timeout=self.request_timeout_s,
            poll_interval_s=self.poll_interval_s,
            get_json=self._get_json,
        )

    def handle_chunk(self, recognizer_id: str, pcm: bytes, turn_id, submitted_at: float) -> None:
        """Ein Chunk, von den Rohbytes bis zum Event. Wirft nie."""
        wav = encode_wav(pcm)
        if len(wav) > self.max_upload_bytes:
            # Vorher prüfen: ein zu großer Upload kostet die volle Wartezeit
            # und scheitert dann doch.
            log.error(
                "dropping a %.1f MB chunk from %s: over the %.0f MB upload limit",
                len(wav) / 1e6, recognizer_id, self.max_upload_bytes / 1e6,
            )
            return
        try:
            text = self.transcribe(wav)
        except Exception as exc:
            # Kein Retry, kein Anhalten: der Chunk ist verloren, der Server
            # läuft weiter, der nächste Satz kommt.
            log.error("infomaniak transcription failed for turn %s: %s", turn_id, exc)
            return

        text = (text or "").strip()
        if not text:
            # Stille bleibt Stille — ein leeres `final` wäre eine Äußerung im
            # Transkript, die niemand gemacht hat.
            log.debug(
                "no text for turn %s (%.2fs round trip)", turn_id, time.time() - submitted_at
            )
            return

        self._bus.publish(
            TranscriptionEvent(
                recognizer_id=recognizer_id,
                type="final",
                text=text,
                timestamp=time.time(),
                backend=BACKEND_NAME,
                # `confidence` liefert dieser Endpunkt nicht, `partial_seq` und
                # `extending` gehören zu Partials, die es hier nicht gibt.
                turn_id=turn_id,
            )
        )
        log.info(
            "[%s] turn %s: %.2fs from speech end to final", recognizer_id, turn_id,
            time.time() - submitted_at,
        )

    def _run_worker(self) -> None:
        while not self._stop.is_set():
            try:
                recognizer_id, pcm, turn_id, submitted_at = self.queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self.handle_chunk(recognizer_id, pcm, turn_id, submitted_at)
            except Exception as exc:  # doppelter Boden: der Thread stirbt nie
                log.error("infomaniak worker error: %s", exc)
