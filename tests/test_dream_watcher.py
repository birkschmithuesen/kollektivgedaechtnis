"""Spec §11's integration requirements: one dream per absorbed interview, the
floor respected, and nothing at all during silence."""

from __future__ import annotations

import pytest

from kg.bus import EventBus
from kg2.config import DreamConfig
from kg2.models import Dream
from kg2.server import seed_display_settings
from kg2.store import DreamStore
from kg2.watcher import DreamWatcher


def graph(persons_with_edges, bare_persons=(), generated_at=1000.0) -> dict:
    nodes = [
        {"id": pid, "type": "person", "portrait": None, "created_at": 1.0,
         "hidden": False, "x": None, "y": None}
        for pid in list(persons_with_edges) + list(bare_persons)
    ] + [
        {"id": "t1", "type": "term", "label": "Weiterbauen im Bestand",
         "mentions": max(1, len(persons_with_edges)), "created_at": 2.0,
         "hidden": False, "x": None, "y": None}
    ]
    return {
        "version": 1, "generated_at": generated_at, "min_mentions": 1, "nodes": nodes,
        "edges": [
            {"id": f"e{i}", "source": pid, "target": "t1"}
            for i, pid in enumerate(persons_with_edges, 1)
        ],
        "quotes": [],
    }


class Harness:
    """A watcher wired to a fake clock, a fake Tool 1 and a counting cycle."""

    def __init__(self, tmp_path, **cfg_overrides):
        self.cfg = DreamConfig(data_dir=tmp_path / "dream", **cfg_overrides)
        self.store = DreamStore.open(self.cfg.db_path)
        seed_display_settings(self.store, self.cfg)
        self.bus = EventBus()
        self.now = 1000.0
        self.graph = graph([])
        self.fail_next = False
        self.cycles: list[tuple[float, tuple]] = []
        self.watcher = DreamWatcher(
            self.cfg, self.store, self.bus, llm=object(),
            fetch=self._fetch, cycle=self._cycle, clock=lambda: self.now,
        )

    def _fetch(self, url, timeout):
        return self.graph

    def _cycle(self, store, cfg, llm, graph, now, **kwargs):
        from kg2.trigger import absorbed_persons
        from kg2.weighting import build_material

        material = build_material(graph)
        self.cycles.append((now, tuple(sorted(absorbed_persons(graph)))))
        dream = store.create_dream(
            created_at=now, graph_generated_at=material.generated_at,
            person_count=material.person_count, term_count=material.term_count,
            edge_count=material.edge_count, contradiction=False,
            guiding_question=cfg.guiding_question,
            absorbed_persons=sorted(absorbed_persons(graph)),
        )
        if self.fail_next:
            store.fail_dream(dream.id, "stubbed failure")
            return None
        store.set_stage1(dream.id, prompt="S1", sentence=f"Traum {dream.id}", model="m")
        store.finish_dream(dream.id, image_path=f"{dream.id}.png")
        return store.get_dream(dream.id)

    def close(self):
        self.store.close()


@pytest.fixture()
def harness(tmp_path):
    h = Harness(tmp_path)
    yield h
    h.close()


# -- the core requirement ---------------------------------------------------


async def test_one_dream_per_absorbed_interview(harness):
    for index in range(1, 5):
        harness.graph = graph([f"p{i}" for i in range(1, index + 1)])
        harness.now += 300.0
        await harness.watcher.tick()

    assert len(harness.cycles) == 4
    assert len(harness.store.visible_dreams()) == 4


async def test_a_bare_person_node_produces_no_dream(harness):
    """Spec §4.1, end to end: Tool 1 published the photo, not the interview."""
    harness.graph = graph([], bare_persons=["p1"])

    assert await harness.watcher.tick() is None
    assert harness.cycles == []


async def test_the_dream_arrives_once_the_pipeline_has_run(harness):
    harness.graph = graph([], bare_persons=["p1"])
    await harness.watcher.tick()

    harness.now += 30.0
    harness.graph = graph(["p1"])
    dream = await harness.watcher.tick()

    assert dream is not None
    assert harness.cycles == [(1030.0, ("p1",))]


async def test_nothing_happens_during_silence(harness):
    harness.graph = graph(["p1"])
    await harness.watcher.tick()

    for _ in range(20):
        harness.now += 300.0
        assert await harness.watcher.tick() is None

    assert len(harness.cycles) == 1


async def test_the_floor_is_respected(harness):
    harness.graph = graph(["p1"])
    await harness.watcher.tick()

    harness.now += 100.0
    harness.graph = graph(["p1", "p2"])
    assert await harness.watcher.tick() is None

    harness.now += 141.0  # total 241 s > 240 s floor
    assert await harness.watcher.tick() is not None
    assert len(harness.cycles) == 2


async def test_interviews_inside_the_floor_collapse_into_one_dream(harness):
    harness.graph = graph(["p1"])
    await harness.watcher.tick()

    for index in (2, 3, 4):
        harness.now += 30.0
        harness.graph = graph([f"p{i}" for i in range(1, index + 1)])
        assert await harness.watcher.tick() is None

    harness.now += 200.0
    await harness.watcher.tick()

    assert len(harness.cycles) == 2
    assert harness.cycles[1][1] == ("p1", "p2", "p3", "p4")


# -- Tool 1 unreachable -----------------------------------------------------


async def test_a_dead_tool_1_produces_no_dream_and_no_exception(harness):
    """Spec §8: „Poll keeps failing quietly." Correct — nothing new was said."""
    harness.watcher.fetch = lambda url, timeout: None

    for _ in range(5):
        harness.now += 300.0
        assert await harness.watcher.tick() is None

    assert harness.cycles == []


async def test_a_dead_tool_1_does_not_swallow_a_pending_dream_now(harness):
    """Fetch BEFORE consuming the flag. Otherwise an outage on the very tick
    the operator pressed the button loses the press silently."""
    harness.graph = graph(["p1"])
    harness.store.set_setting("dream_requested", "1")
    harness.watcher.fetch = lambda url, timeout: None

    await harness.watcher.tick()
    assert harness.store.get_setting("dream_requested", "0") == "1"

    harness.watcher.fetch = lambda url, timeout: harness.graph
    assert await harness.watcher.tick() is not None


async def test_the_display_is_untouched_while_tool_1_is_gone(harness):
    harness.graph = graph(["p1"])
    await harness.watcher.tick()
    harness.watcher.fetch = lambda url, timeout: None

    harness.now += 5000.0
    await harness.watcher.tick()

    assert harness.store.current_dream().sentence == "Traum d1"


# -- flow control -----------------------------------------------------------


async def test_pause_stops_new_dreams(harness):
    harness.store.set_setting("paused", "1")
    harness.graph = graph(["p1"])

    harness.now += 300.0
    assert await harness.watcher.tick() is None
    assert harness.cycles == []


async def test_resume_picks_the_pending_interview_back_up(harness):
    """Pausing must not lose material, for the same reason the floor must not."""
    harness.store.set_setting("paused", "1")
    harness.graph = graph(["p1"])
    harness.now += 300.0
    await harness.watcher.tick()

    harness.store.set_setting("paused", "0")
    assert await harness.watcher.tick() is not None
    assert harness.cycles[0][1] == ("p1",)


async def test_dream_now_ignores_the_floor(harness):
    harness.graph = graph(["p1"])
    await harness.watcher.tick()

    harness.now += 5.0
    harness.store.set_setting("dream_requested", "1")

    assert await harness.watcher.tick() is not None
    assert len(harness.cycles) == 2


async def test_dream_now_works_while_paused(harness):
    """The operator pressed it deliberately (spec §7)."""
    harness.store.set_setting("paused", "1")
    harness.graph = graph(["p1"])
    harness.store.set_setting("dream_requested", "1")

    assert await harness.watcher.tick() is not None


async def test_dream_now_fires_only_once_per_press(harness):
    harness.graph = graph(["p1"])
    harness.store.set_setting("dream_requested", "1")
    await harness.watcher.tick()

    harness.now += 1.0
    assert await harness.watcher.tick() is None
    assert len(harness.cycles) == 1


# -- failures ---------------------------------------------------------------


async def test_a_failed_dream_retries_at_the_next_trigger_not_immediately(harness):
    """Spec §8: „Retry at the next trigger — never a retry storm."""
    harness.graph = graph(["p1"])
    harness.fail_next = True
    await harness.watcher.tick()
    assert len(harness.cycles) == 1

    harness.now += 10.0
    assert await harness.watcher.tick() is None  # inside the floor
    assert len(harness.cycles) == 1

    harness.now += 240.0
    harness.fail_next = False
    assert await harness.watcher.tick() is not None
    assert harness.cycles[1][1] == ("p1",)  # the SAME material, retried


async def test_a_crashing_cycle_does_not_kill_the_poll_loop(harness):
    def boom(*args, **kwargs):
        raise RuntimeError("unexpected")

    harness.watcher.cycle = boom
    harness.graph = graph(["p1"])

    assert await harness.watcher.tick() is None

    harness.watcher.cycle = harness._cycle
    harness.now += 300.0
    assert await harness.watcher.tick() is not None


# -- restart ----------------------------------------------------------------


async def test_a_restart_does_not_re_dream_the_whole_day(tmp_path):
    """Spec §8: everything needed is in SQLite; nothing lives only in memory."""
    first = Harness(tmp_path)
    first.graph = graph(["p1", "p2", "p3"])
    await first.watcher.tick()
    assert len(first.cycles) == 1
    first.close()

    second = Harness(tmp_path)
    second.now = 99999.0
    second.graph = graph(["p1", "p2", "p3"])

    assert await second.watcher.tick() is None
    assert second.cycles == []
    second.close()


async def test_a_restart_still_dreams_for_an_interview_that_arrived_meanwhile(tmp_path):
    first = Harness(tmp_path)
    first.graph = graph(["p1"])
    await first.watcher.tick()
    first.close()

    second = Harness(tmp_path)
    second.now = 99999.0
    second.graph = graph(["p1", "p2"])

    assert await second.watcher.tick() is not None
    assert second.cycles[0][1] == ("p1", "p2")
    second.close()


# -- the SSE push -----------------------------------------------------------


async def test_a_finished_dream_is_pushed_to_the_display(harness):
    queue = harness.bus.subscribe()
    harness.graph = graph(["p1"])

    await harness.watcher.tick()

    event = queue.get_nowait()
    assert event["type"] == "state"
    assert event["state"]["current"]["sentence"] == "Traum d1"


async def test_a_failed_dream_pushes_nothing_new_to_the_display(harness):
    """Spec §8: the screen looks calm, not broken. A push with an unchanged
    current dream is harmless but pointless; a push is only made on success."""
    harness.fail_next = True
    harness.graph = graph(["p1"])
    queue = harness.bus.subscribe()

    await harness.watcher.tick()

    assert queue.empty()
