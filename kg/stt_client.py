"""Independent SSE consumer for the external STT server. Never modifies it (spec 4)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable

import httpx

from kg.sse import SSEDecoder
from kg.transcript import TranscriptionEvent, TranscriptLog

log = logging.getLogger(__name__)


async def httpx_line_source(url: str) -> AsyncIterator[str]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=None)) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                yield line


class STTClient:
    def __init__(
        self,
        url: str,
        log: TranscriptLog,
        on_final: Callable[[TranscriptionEvent], None],
        on_partial: Callable[[TranscriptionEvent], None] | None = None,
        on_state: Callable[[bool], None] | None = None,
        line_source: Callable[[str], AsyncIterator[str]] = httpx_line_source,
        backoff: Callable[[int], float] = lambda attempt: min(30.0, 2.0**attempt),
        max_cycles: int | None = None,
    ) -> None:
        self.url = url.rstrip("/") + "/events"
        self.log = log
        self.on_final = on_final
        self.on_partial = on_partial or (lambda event: None)
        self.on_state = on_state or (lambda connected: None)
        self.line_source = line_source
        self.backoff = backoff
        self.max_cycles = max_cycles

    async def run(self) -> None:
        """Consume forever, reconnecting with backoff. Never raises on STT failure."""
        attempt = 0
        cycles = 0
        while self.max_cycles is None or cycles < self.max_cycles:
            cycles += 1
            decoder = SSEDecoder()
            try:
                async for line in self.line_source(self.url):
                    payload = decoder.feed(line)
                    if payload is None:
                        continue
                    if attempt or cycles == 1:
                        self.on_state(True)
                        attempt = 0
                    self._dispatch(TranscriptionEvent.from_dict(payload))
            except Exception as exc:  # STT unreachable is a normal on-site state
                log.warning("stt stream failed (%s); reconnecting", exc)
            self.on_state(False)
            attempt += 1
            if self.max_cycles is not None and cycles >= self.max_cycles:
                break  # tests only; live operation never leaves the loop
            await asyncio.sleep(self.backoff(attempt))

    def _dispatch(self, event: TranscriptionEvent) -> None:
        if event.type == "final":
            self.log.append(event)
            self.on_final(event)
        elif event.type == "partial":
            self.on_partial(event)
