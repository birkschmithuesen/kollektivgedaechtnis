"""Wiring: Telegram + STT in, SQLite and the browser out. The only writer."""

from __future__ import annotations

import asyncio
import logging
import time

from kg.pipeline import process_interview
from kg.server import broadcast_graph, broadcast_state
from kg.session import SessionTracker

log = logging.getLogger(__name__)

SETTLE_TIMEOUT_S = 3.0
SETTLE_POLL_S = 0.1


async def settle_cut_end(
    transcript_log,
    stopped_at: float,
    timeout: float = SETTLE_TIMEOUT_S,
    poll_interval: float = SETTLE_POLL_S,
) -> float:
    """Wait briefly for an in-flight final on the Telegram-text stop path.

    This exists ONLY for the Telegram-text race: a human keypress can land
    while the visitor's last sentence is still inside ElevenLabs' server VAD,
    so its final publishes slightly after the stop marker. The spoken and
    timeout paths deliberately never call this — a spoken stop arrives as a
    final itself (finals are ordered, so nothing earlier can still be in
    flight), and after a 15-minute timeout nothing is in flight either.
    """
    deadline = time.monotonic() + timeout
    while True:
        finals = [
            e
            for e in transcript_log.read_range(stopped_at, float("inf"))
            if e.timestamp > stopped_at
        ]
        if finals:
            return max(e.timestamp for e in finals)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return stopped_at
        await asyncio.sleep(min(poll_interval, remaining))


class Core:
    def __init__(
        self,
        cfg,
        store,
        bus,
        transcript_log,
        llm,
        embedder,
        processor=process_interview,
        settle_timeout_s: float = SETTLE_TIMEOUT_S,
        settle_poll_s: float = SETTLE_POLL_S,
    ) -> None:
        self.cfg = cfg
        self.store = store
        self.bus = bus
        self.transcript_log = transcript_log
        self.llm = llm
        self.embedder = embedder
        self.processor = processor
        # Code-level knobs and test seams, deliberately NOT config-file keys.
        self.settle_timeout_s = settle_timeout_s
        self.settle_poll_s = settle_poll_s
        # A crash can leave a person "open" in the store with nothing in
        # memory to say so. Resuming from the store here, instead of always
        # starting empty, is what keeps a restart a resume rather than a
        # reset (spec: state must be reconstructible from SQLite) and keeps
        # the one-interview-at-a-time guarantee across a restart.
        open_person = store.open_person()
        self.tracker = SessionTracker(
            cfg.interview_timeout_s,
            cfg.stop_phrases,
            open_since=open_person.started_at if open_person else None,
            wake_word=cfg.wake_word,
        )
        self._queue: asyncio.Queue = asyncio.Queue()
        self._tasks: set[asyncio.Task] = set()

    # -- inbound callbacks (sync, must never block) -------------------------

    def on_photo(self, photo_path, portrait_path, at: float) -> None:
        self._queue.put_nowait(("photo", (str(photo_path), str(portrait_path)), at))

    def on_text(self, text: str, at: float) -> None:
        self._queue.put_nowait(("text", text, at))

    def on_final(self, event) -> None:
        self._queue.put_nowait(("final", event.text, event.timestamp))
        self.bus.publish({"type": "transcript", "text": event.text})

    def on_partial(self, event) -> None:
        self.bus.publish({"type": "transcript", "text": event.text})

    def on_tick(self, now: float) -> None:
        self._queue.put_nowait(("tick", None, now))

    def on_stt_state(self, connected: bool) -> None:
        self.store.set_setting("stt_connected", "1" if connected else "0")
        broadcast_state(self.store, self.bus)

    # -- queue processing ---------------------------------------------------

    async def run_worker(self) -> None:
        while True:
            kind, payload, at = await self._queue.get()
            try:
                await self._handle(kind, payload, at)
            except Exception as exc:  # a bad event must never kill the station
                log.error("core failed on %s: %s", kind, exc)

    async def run_tick_loop(self, interval: float = 5.0) -> None:
        while True:
            await asyncio.sleep(interval)
            self.on_tick(time.time())

    async def drain(self) -> None:
        """Process everything queued and await running pipelines (tests, shutdown)."""
        while not self._queue.empty():
            kind, payload, at = self._queue.get_nowait()
            try:
                await self._handle(kind, payload, at)
            except Exception as exc:
                log.error("core failed on %s: %s", kind, exc)
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def _handle(self, kind: str, payload, at: float) -> None:
        if kind == "photo":
            transitions = self.tracker.photo(at)
        elif kind == "text":
            transitions = self.tracker.text_message(at)
        elif kind == "final":
            transitions = self.tracker.transcript(payload, at)
        else:
            transitions = self.tracker.tick(at)

        for transition in transitions:
            if transition.kind == "closed":
                self._close(transition)
            else:
                self._open(payload, transition)

    def _open(self, payload, transition) -> None:
        photo_path, portrait_path = payload
        self.store.create_person(
            started_at=transition.at, photo_path=photo_path, portrait_path=portrait_path
        )
        # The person node appears immediately; terms grow after the stop (spec 6).
        broadcast_graph(self.store, self.cfg, self.bus)
        broadcast_state(self.store, self.bus)

    def _close(self, transition) -> None:
        person = self.store.open_person()
        if person is None:
            return
        self.store.close_person(person.id, stopped_at=transition.at, reason=transition.reason)
        broadcast_state(self.store, self.bus)
        task = asyncio.create_task(
            self._process(person.id, person.started_at, transition.at, transition.reason)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _process(
        self, person_id: str, started_at: float, stopped_at: float, reason: str
    ) -> None:
        cut_end = stopped_at
        if reason == "text":
            # Only a Telegram text stop races an in-flight utterance still
            # inside ElevenLabs' server VAD; the spoken and timeout paths have
            # nothing in flight, so they skip the wait entirely.
            cut_end = await settle_cut_end(
                self.transcript_log, stopped_at, self.settle_timeout_s, self.settle_poll_s
            )
        try:
            await asyncio.to_thread(
                self.processor,
                self.store,
                self.cfg,
                self.llm,
                self.embedder,
                self.transcript_log,
                person_id,
                started_at,
                stopped_at,
                cut_end=cut_end,
            )
        except Exception as exc:  # already handled inside the pipeline; belt and braces
            log.error("pipeline crashed for %s: %s", person_id, exc)
            self.store.set_person_status(person_id, "failed")
        broadcast_graph(self.store, self.cfg, self.bus)
        broadcast_state(self.store, self.bus)
