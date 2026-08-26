"""The poll loop: Tool 1's graph in, one dream out (spec §4.1).

Polling a complete-state endpoint rather than subscribing to Tool 1's `/events`
(spec §4.1): it survives a Tool 1 restart with no reconnect logic, it is the
pattern CR-1 already chose, and at a 240 s floor a 5 s detection lag is
invisible. SSE stays available as a later optimisation; nothing here depends on
it.
"""

from __future__ import annotations

import asyncio
import logging
import time

from kg2.cycle import run_dream
from kg2.graph_client import fetch_graph
from kg2.server import broadcast_dream_state
from kg2.trigger import evaluate, resume_state

log = logging.getLogger(__name__)


class DreamWatcher:
    def __init__(self, cfg, store, bus, llm, *, fetch=fetch_graph, cycle=run_dream,
                 clock=time.time) -> None:
        self.cfg = cfg
        self.store = store
        self.bus = bus
        self.llm = llm
        self.fetch = fetch
        self.cycle = cycle
        self.clock = clock
        # A restart is a resume, not a reset (spec §8). Without this the
        # watcher would either dream once for all 40 interviews of the day or
        # never dream again, depending on which way the mistake went.
        self.state = resume_state(store.all_dreams())

    async def tick(self):
        """One poll. Returns the finished Dream, or None."""
        graph = await asyncio.to_thread(
            self.fetch, self.cfg.graph_url, self.cfg.fetch_timeout_s
        )
        if graph is None:
            # Tool 1 unreachable. Quiet, and deliberately BEFORE the flag is
            # read: consuming „dream now" on a tick that cannot fetch would
            # swallow the operator's button press with nothing on screen to
            # say so (spec §8).
            return None

        forced = self.store.get_setting("dream_requested", "0") == "1"
        if forced:
            self.store.set_setting("dream_requested", "0")
        elif self.store.get_setting("paused", "0") == "1":
            # Paused blocks the automatic cycle only. „Dream now" was pressed
            # deliberately and works regardless (spec §7).
            return None

        decision = evaluate(
            self.state, graph, self.clock(), self.cfg.min_interval_s, force=forced
        )
        if not decision.fire:
            return None

        # The floor stamp is adopted BEFORE the cycle and whatever its outcome:
        # a failure must still space out its retry (spec §8).
        self.state = self.state.with_dream_started(decision.started_at)

        loop = asyncio.get_running_loop()

        def announce(sentence: str) -> None:
            # The bus's queues belong to the server's event loop; poking them
            # from this worker thread is not thread-safe. Same hazard, same fix
            # as sim/prerender.py's `publish`.
            loop.call_soon_threadsafe(
                self.bus.publish, {"type": "dreaming", "sentence": sentence}
            )

        try:
            dream = await asyncio.to_thread(
                self.cycle,
                self.store, self.cfg, self.llm, graph, decision.started_at,
                on_sentence=announce,
            )
        except Exception as exc:  # run_dream does not raise; a stub might
            log.error("dream cycle raised: %s", exc)
            return None

        if dream is None:
            # Failed. The seen set is NOT advanced, so the same material is
            # retried at the next trigger past the floor (spec §8).
            return None

        self.state = self.state.with_absorbed(decision.absorbed)
        broadcast_dream_state(self.store, self.cfg, self.bus)
        return dream

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception as exc:  # a bad poll must never kill the station
                log.error("watcher tick failed: %s", exc)
            await asyncio.sleep(self.cfg.poll_interval_s)
