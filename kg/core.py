"""Wiring: Telegram + STT in, SQLite and the browser out. The only writer."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from kg.pipeline import process_interview
from kg.server import broadcast_graph, broadcast_state
from kg.session import SessionTracker
from kg.stop_intent import make_stop_intent

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
        wake_llm=None,
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
        # A second, cheap client, separate from the pipeline's `llm`, and only
        # if the config asks for it AND there is a name to gate on. Without it
        # the tracker never asks anyone anything (spec 5, 2026-08-30).
        stop_intent = None
        if wake_llm is not None and cfg.wake_word_llm and cfg.wake_word:
            stop_intent = make_stop_intent(wake_llm, cfg.wake_word_llm_timeout_s)
        self.tracker = SessionTracker(
            cfg.interview_timeout_s,
            cfg.stop_phrases,
            open_since=open_person.started_at if open_person else None,
            wake_word=cfg.wake_word,
            stop_intent=stop_intent,
            # An interview opened by the microphone switch has no portrait
            # yet, and a photo arriving later belongs to that person rather
            # than to a new one (kg.session.photo). The store is what knows
            # this across a restart.
            open_without_portrait=open_person is not None and open_person.portrait_path is None,
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

    def on_mic_switch(self, on: bool, at: float) -> None:
        """The physical switch on the microphone moved (STT server → /api/interview_switch).

        A separate setting from `stt_connected` on purpose. That one says
        whether the STT server's event stream is reachable — a property of the
        network. This says whether the microphone in the room is switched on —
        a property of the visitor's hand. Folding the second into the first
        would make a switched-off microphone indistinguishable from a crashed
        STT server on the operator page, at the one moment when telling them
        apart matters.

        Like every other inbound callback here: never blocks. The open or
        close itself happens in the worker.
        """
        self.store.set_setting("mic_on", "1" if on else "0")
        broadcast_state(self.store, self.bus)
        self._queue.put_nowait(("mic_switch", on, at))

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
            if not transitions:
                # 🔴 Ein Foto ohne laufendes Interview wird zu nichts (seit
                # 2026-09-01). `/api/photo` weist so etwas schon vorher ab und
                # schreibt gar nicht erst -- Telegram kann das nicht, dort
                # liegen die Dateien bereits auf der Platte, wenn wir hier
                # ankommen.
                #
                # Also hier wegraeumen, an der einen Stelle, durch die JEDER
                # Weg laeuft. Ein Portraet, das zu keiner Person gehoert, ist
                # ein Gesicht auf der Platte, das niemand mehr zuordnen kann
                # und niemand aufraeumt -- bei einer Arbeit ueber
                # Datensouveraenitaet ist das kein Schoenheitsfehler.
                self._verwirf_foto(payload)
        elif kind == "text":
            transitions = self.tracker.text_message(at)
        elif kind == "mic_switch":
            transitions = self.tracker.mic_switch(payload, at)
        elif kind == "final":
            if self.tracker.stop_intent is None:
                transitions = self.tracker.transcript(payload, at)
            else:
                # A final may now cost an LLM call, so it must not run on the
                # event loop — the wall, the SSE stream and the Telegram poller
                # all live there. A thread instead of a background task: this
                # worker is the tracker's only caller, so awaiting keeps the
                # event order exactly as it is for every other event, and a
                # photo can never arrive "during" a stop check and get its
                # brand-new interview closed by the answer to the old one.
                # The waiting itself is bounded by kg.stop_intent's own hard
                # timeout, so this can delay the queue by seconds, never hang.
                transitions = await asyncio.to_thread(self.tracker.transcript, payload, at)
        else:
            transitions = self.tracker.tick(at)

        for transition in transitions:
            if transition.kind == "closed":
                self._close(transition)
            elif transition.kind == "portrait":
                self._portrait(payload)
            else:
                self._open(payload, transition)

    def _open(self, payload, transition) -> None:
        # Two entrances, two payloads: the photo path carries the two image
        # paths, the microphone switch carries its own on/off flag and no
        # picture at all. Reading the paths off the reason instead of trying
        # to unpack whatever arrived keeps the photo path exactly as it was —
        # a photo without both paths stays a bug, not a person without a face.
        photo_path, portrait_path = payload if transition.reason == "photo" else (None, None)
        self.store.create_person(
            started_at=transition.at, photo_path=photo_path, portrait_path=portrait_path
        )
        # The person node appears immediately; terms grow after the stop (spec 6).
        broadcast_graph(self.store, self.cfg, self.bus)
        broadcast_state(self.store, self.bus)

    def _verwirf_foto(self, payload) -> None:
        """Loescht ein Bild, das zu keiner Person geworden ist.

        Fehler beim Loeschen werden protokolliert und verschluckt: Die Station
        laeuft vor Publikum, und eine liegengebliebene Datei ist ein Problem
        fuer spaeter -- ein Absturz waere eins fuer jetzt.
        """
        for pfad in payload or ():
            try:
                Path(pfad).unlink(missing_ok=True)
            except OSError as exc:
                log.warning("verworfenes Foto nicht loeschbar (%s): %s", pfad, exc)

    def _portrait(self, payload) -> None:
        """Ein Foto fuer das Interview, das gerade laeuft.

        Seit 2026-09-01 der EINZIGE Weg, auf dem ein Foto etwas bewirkt --
        entweder nachgereicht ("late_photo", die Person hatte noch kein Bild)
        oder ersetzend ("replaced_photo", es gab schon eins). Welcher der
        beiden Faelle vorliegt, entscheidet `kg.session.photo`; hier ist die
        Wirkung dieselbe, und das ist Absicht: In beiden Faellen bleiben
        Person, started_at und Transkriptfenster unangetastet, nur das Bild
        wandert.

        Kein Zustandswechsel, deshalb wird nur der Graph gesendet -- die Wand
        tauscht das Bild an einer Scheibe, die schon dort haengt.
        """
        person = self.store.open_person()
        if person is None:  # closed by another path between queueing and here
            return
        photo_path, portrait_path = payload
        self.store.set_person_portrait(person.id, photo_path, portrait_path)
        broadcast_graph(self.store, self.cfg, self.bus)

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
