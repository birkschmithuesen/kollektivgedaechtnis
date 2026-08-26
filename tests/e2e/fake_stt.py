"""A stand-in for the external STT server's `/events` stream.

Speaks exactly the wire format `docs/stt-contract.md` records: unnamed SSE
messages, one JSON object per event, `: keep-alive` comments in between. The
real `STTClient` connects to it over real HTTP with its real default line
source, so the decoder, the reconnect loop and the transcript log all run as
shipped.

What this deliberately does NOT prove: that ElevenLabs Scribe emits exactly
these events. The contract document is the verified source for that (read off
the STT server's own repo); this server only replays it.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeSTT:
    """Serves `GET /events` on 127.0.0.1 on an OS-assigned port."""

    def __init__(self, events: Sequence[dict], gap_s: float = 0.0) -> None:
        self.events = list(events)
        self.gap_s = gap_s
        self.connections = 0
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._done = threading.Event()

    def __enter__(self) -> "FakeSTT":
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args) -> None:
                pass

            def do_GET(self) -> None:
                if self.path != "/events":
                    self.send_error(404)
                    return
                outer.connections += 1
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                try:
                    # A keep-alive comment BEFORE the first event: the decoder
                    # must skip it, and the live server really does open this
                    # way when nobody is speaking yet.
                    self.wfile.write(b": keep-alive\n\n")
                    for event in outer.events:
                        if outer.gap_s:
                            time.sleep(outer.gap_s)
                        payload = json.dumps(event, ensure_ascii=False)
                        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                        self.wfile.flush()
                        self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass  # the consumer went away; that is its right
                finally:
                    outer._done.set()

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        assert self._server is not None
        self._server.shutdown()
        self._server.server_close()
        assert self._thread is not None
        self._thread.join(timeout=5)

    def wait_until_sent(self, timeout: float = 10.0) -> bool:
        """True once the whole event list has been written to a consumer."""
        return self._done.wait(timeout)

    @property
    def url(self) -> str:
        assert self._server is not None
        return f"http://127.0.0.1:{self._server.server_address[1]}"


def final(text: str, timestamp: float, turn_id: str | None = None) -> dict:
    """A `final` exactly as elevenlabs-scribe publishes it (ten fields)."""
    return {
        "recognizer_id": "left",
        "type": "final",
        "text": text,
        "timestamp": timestamp,
        "backend": "elevenlabs-scribe",
        "status": None,
        "confidence": None,
        "turn_id": turn_id,
        "partial_seq": None,
        # finals leave `extending` at its default (contract §"extending")
        "extending": None,
    }


def partial(text: str, timestamp: float, seq: int, extending: bool) -> dict:
    return {
        "recognizer_id": "left",
        "type": "partial",
        "text": text,
        "timestamp": timestamp,
        "backend": "elevenlabs-scribe",
        "status": None,
        "confidence": None,
        "turn_id": "01K2TESTTURN",
        "partial_seq": seq,
        "extending": extending,
    }
