"""Local, append-only transcript log. The STT server stays a pure supplier (spec 4)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class TranscriptionEvent:
    """The verified 10-field STT contract — see docs/stt-contract.md."""

    type: str
    text: str
    timestamp: float
    recognizer_id: str = ""
    backend: str = ""
    status: str | None = None
    confidence: float | None = None
    turn_id: str | None = None
    partial_seq: int | None = None
    # elevenlabs-scribe revises partials mid-utterance: True = extends the
    # previous partial, False = revision, None = backend doesn't distinguish
    # (and always None on finals). We consume finals only, so this field is
    # carried, logged and otherwise ignored.
    extending: bool | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "TranscriptionEvent":
        """Tolerant: unknown keys are dropped, missing keys get defaults."""
        return cls(
            type=str(data.get("type", "")),
            text=str(data.get("text", "")),
            timestamp=float(data.get("timestamp", 0.0)),
            recognizer_id=str(data.get("recognizer_id", "")),
            backend=str(data.get("backend", "")),
            status=data.get("status"),
            confidence=data.get("confidence"),
            turn_id=data.get("turn_id"),
            partial_seq=data.get("partial_seq"),
            extending=data.get("extending"),
        )


class TranscriptLog:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: TranscriptionEvent) -> None:
        if event.type != "final":
            return
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")

    def read_range(self, start: float, end: float) -> list[TranscriptionEvent]:
        if not self.path.exists():
            return []
        events: list[TranscriptionEvent] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = TranscriptionEvent.from_dict(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if event.type == "final" and start <= event.timestamp <= end:
                    events.append(event)
        events.sort(key=lambda e: e.timestamp)
        return events

    def text_between(self, start: float, end: float) -> str:
        return " ".join(e.text.strip() for e in self.read_range(start, end) if e.text.strip())
