"""Minimal SSE decoder. Deliberately ours: the contract is tiny and must be testable."""

from __future__ import annotations

import json


class SSEDecoder:
    def __init__(self) -> None:
        self._data: list[str] = []

    def feed(self, line: str) -> dict | None:
        """Feed one line (without trailing newline). Returns an event when complete."""
        if line.startswith(":"):  # keep-alive comment
            return None
        if line == "":
            if not self._data:
                return None
            raw = "\n".join(self._data)
            self._data = []
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None
        if line.startswith("data:"):
            self._data.append(line[5:].lstrip())
        return None
