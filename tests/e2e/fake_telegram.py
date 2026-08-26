"""A stand-in for Telegram's HTTP Bot API, good enough for the real poller.

Used by the end-to-end test only. It speaks the three calls `TelegramSource`
actually makes through python-telegram-bot — `getMe` (on initialize),
`deleteWebhook` (the updater's bootstrap), `getUpdates`, `getFile` — plus the
file download URL that `File.download_to_drive` fetches. Everything else
returns a Bot-API-shaped error, so an unexpected call fails loudly instead of
looking like an empty success.

What this deliberately does NOT prove: that Telegram's real responses look like
these. That is the one remaining gap in the chain and it is intentional (see
docs/briefs/task5-e2e-telegram-stt.md).
"""

from __future__ import annotations

import json
import threading
import time
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

TOKEN = "424242:TESTTOKEN"


class FakeTelegram:
    """Serves the Bot API on 127.0.0.1 on an OS-assigned port."""

    def __init__(self, files: dict[str, Path] | None = None) -> None:
        self.files = dict(files or {})
        self.updates: list[dict] = []
        self.calls: list[str] = []
        self._next_update_id = 1
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # -- lifecycle ----------------------------------------------------------

    def __enter__(self) -> "FakeTelegram":
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args) -> None:  # keep pytest output clean
                pass

            def do_GET(self) -> None:
                outer._handle(self, b"")

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                outer._handle(self, self.rfile.read(length))

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

    @property
    def port(self) -> int:
        assert self._server is not None
        return self._server.server_address[1]

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/bot"

    @property
    def base_file_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/file/bot"

    # -- test-facing API ----------------------------------------------------

    def queue_photo(self, file_id: str, source: Path, chat_id: int, at: float) -> None:
        """Make `source` downloadable as `file_id` and queue a photo update."""
        with self._lock:
            self.files[file_id] = Path(source)
            self.updates.append(
                {
                    "update_id": self._take_update_id(),
                    "message": {
                        "message_id": 100 + len(self.updates),
                        "date": int(at),
                        "chat": {"id": chat_id, "type": "private"},
                        "from": {"id": chat_id, "is_bot": False, "first_name": "Test"},
                        "photo": [
                            {
                                "file_id": f"{file_id}-small",
                                "file_unique_id": f"{file_id}-small-u",
                                "width": 90,
                                "height": 112,
                            },
                            {
                                "file_id": file_id,
                                "file_unique_id": f"{file_id}-u",
                                "width": 800,
                                "height": 1000,
                            },
                        ],
                    },
                }
            )

    def queue_text(self, text: str, chat_id: int, at: float) -> None:
        with self._lock:
            self.updates.append(
                {
                    "update_id": self._take_update_id(),
                    "message": {
                        "message_id": 100 + len(self.updates),
                        "date": int(at),
                        "chat": {"id": chat_id, "type": "private"},
                        "from": {"id": chat_id, "is_bot": False, "first_name": "Test"},
                        "text": text,
                    },
                }
            )

    def _take_update_id(self) -> int:
        update_id = self._next_update_id
        self._next_update_id += 1
        return update_id

    # -- request handling ---------------------------------------------------

    def _handle(self, handler: BaseHTTPRequestHandler, body: bytes) -> None:
        path = unquote(urlsplit(handler.path).path)

        if path.startswith(f"/file/bot{TOKEN}/"):
            self._serve_file(handler, path.split(f"/file/bot{TOKEN}/", 1)[1])
            return

        if not path.startswith(f"/bot{TOKEN}/"):
            self._json(handler, 404, {"ok": False, "error_code": 404, "description": path})
            return

        method = path.split(f"/bot{TOKEN}/", 1)[1]
        with self._lock:
            self.calls.append(method)
        self._json(handler, 200, self._call(method, _parse_body(handler, body)))

    def _call(self, method: str, payload: dict) -> dict:
        if method == "getMe":
            return _ok(
                {
                    "id": 424242,
                    "is_bot": True,
                    "first_name": "Kollektivgedaechtnis",
                    "username": "kg_test_bot",
                }
            )
        if method in ("deleteWebhook", "setWebhook", "close", "logOut"):
            return _ok(True)
        if method == "getUpdates":
            return _ok(self._take_updates(payload))
        if method == "getFile":
            return self._get_file(payload.get("file_id", ""))
        return {
            "ok": False,
            "error_code": 400,
            "description": f"fake telegram: unexpected method {method}",
        }

    def _take_updates(self, payload: dict) -> list[dict]:
        offset = int(payload.get("offset") or 0)
        with self._lock:
            self.updates = [u for u in self.updates if u["update_id"] >= offset]
            batch = list(self.updates)
            self.updates = []
        if not batch:
            # The real API long-polls; returning instantly would turn the
            # updater's loop into a busy spin against this thread.
            time.sleep(0.05)
        return batch

    def _get_file(self, file_id: str) -> dict:
        with self._lock:
            known = file_id in self.files
        if not known:
            return {"ok": False, "error_code": 400, "description": "file not found"}
        return _ok(
            {
                "file_id": file_id,
                "file_unique_id": f"{file_id}-u",
                "file_size": self.files[file_id].stat().st_size,
                "file_path": f"photos/{file_id}.jpg",
            }
        )

    def _serve_file(self, handler: BaseHTTPRequestHandler, file_path: str) -> None:
        file_id = Path(file_path).stem
        with self._lock:
            source = self.files.get(file_id)
        if source is None:
            self._json(handler, 404, {"ok": False, "error_code": 404, "description": file_path})
            return
        data = source.read_bytes()
        handler.send_response(200)
        handler.send_header("Content-Type", "image/jpeg")
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)

    def _json(self, handler: BaseHTTPRequestHandler, status: int, payload: dict | list) -> None:
        data = json.dumps(payload).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)


def _ok(result) -> dict:
    return {"ok": True, "result": result}


def _parse_body(handler: BaseHTTPRequestHandler, body: bytes) -> dict:
    """Read the request payload in whichever encoding PTB chose.

    python-telegram-bot posts `application/x-www-form-urlencoded` for plain
    calls and `multipart/form-data` when files are involved; it does NOT post
    JSON. Decoding it as JSON is what a hand-written fake gets wrong first —
    the poller then silently retries forever and the test only says "nothing
    arrived".
    """
    if not body:
        return {}
    content_type = handler.headers.get("Content-Type") or ""
    if content_type.startswith("application/json"):
        return json.loads(body)
    if content_type.startswith("multipart/form-data"):
        message = BytesParser(policy=default).parsebytes(
            b"Content-Type: " + content_type.encode("utf-8") + b"\r\n\r\n" + body
        )
        fields: dict = {}
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if name:
                fields[str(name)] = part.get_payload(decode=True).decode("utf-8")
        return fields
    return {key: values[0] for key, values in parse_qs(body.decode("utf-8")).items()}
