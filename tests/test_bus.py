import asyncio

from kg.bus import EventBus


async def test_every_subscriber_receives_published_events():
    bus = EventBus()
    a, b = bus.subscribe(), bus.subscribe()

    bus.publish({"type": "graph"})

    assert await asyncio.wait_for(a.get(), 1) == {"type": "graph"}
    assert await asyncio.wait_for(b.get(), 1) == {"type": "graph"}


async def test_a_slow_subscriber_is_dropped_not_blocking():
    bus = EventBus(max_queue=1)
    slow = bus.subscribe()

    bus.publish({"n": 1})
    bus.publish({"n": 2})  # queue is full -> dropped, must not raise

    assert slow.qsize() == 1


async def test_unsubscribe_stops_delivery():
    bus = EventBus()
    q = bus.subscribe()
    bus.unsubscribe(q)

    bus.publish({"type": "graph"})

    assert q.empty()
