"""In-process pub/sub for the browser SSE fanout.

Same rule as the STT server's bus: a slow browser tab must never stall the Core.
"""

from __future__ import annotations

import asyncio


class EventBus:
    def __init__(self, max_queue: int = 100) -> None:
        self.max_queue = max_queue
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self.max_queue)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    def publish(self, event: dict) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass  # drop for slow consumers
