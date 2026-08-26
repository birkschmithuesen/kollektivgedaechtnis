"""Every row of spec §8, plus the crash-recovery standard of T1§14 (run 21).

| Failure (spec §8)                        | Covered by                          |
|------------------------------------------|-------------------------------------|
| Stage 1 or 2 fails / times out           | `test_a_dead_cloud_…`               |
| No connectivity at all                   | `test_a_whole_day_of_no_…`          |
| Tool 1 unreachable                       | `test_a_dead_tool_1_…`              |
| Tool 2 process dies                      | `test_a_restart_restores_…`         |
| Image model returns something unusable   | `test_an_unusable_image_…`          |
| Disk fills with images                   | documented, not engineered (below)  |

The two that matter most (spec §11): „cloud dead → last image stays up" and
„restart → strip intact".
"""

from __future__ import annotations

import struct
import zlib

from fastapi.testclient import TestClient

from kg.bus import EventBus
from kg2.config import DreamConfig
from kg2.cycle import run_dream
from kg2.imagegen import ImageError
from kg2.server import create_dream_app, dream_state, seed_display_settings
from kg2.store import DreamStore
from kg2.watcher import DreamWatcher


def png_bytes() -> bytes:
    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
        + chunk(b"IEND", b"")
    )


def graph(persons, generated_at=1000.0) -> dict:
    nodes = [
        {"id": f"p{i}", "type": "person", "portrait": None, "created_at": 1.0,
         "hidden": False, "x": None, "y": None}
        for i in range(1, persons + 1)
    ] + [
        {"id": "t1", "type": "term", "label": "Weiterbauen im Bestand", "mentions": persons,
         "created_at": 2.0, "hidden": False, "x": None, "y": None}
    ]
    return {
        "version": 1, "generated_at": generated_at, "min_mentions": 1, "nodes": nodes,
        "edges": [{"id": f"e{i}", "source": f"p{i}", "target": "t1"}
                  for i in range(1, persons + 1)],
        "quotes": [],
    }


def good_condense(sentence="Der Beton träumt von Wald."):
    from kg2.condense import CondenseResult

    def fn(llm, material, question, contradiction):
        return CondenseResult(prompt="P", sentence=sentence)

    return fn


def good_render(prompt, **kwargs):
    return png_bytes()


def seed_one_good_dream(store, cfg, *, at=1.0, sentence="das gute Bild"):
    return run_dream(store, cfg, object(), graph(3), at,
                     condense_fn=good_condense(sentence), render_fn=good_render)


# -- „cloud dead -> last image stays up" (spec §11's first priority) --------


def test_a_dead_cloud_leaves_the_last_image_up(tmp_path):
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    seed_one_good_dream(store, cfg)

    def dead(prompt, **kwargs):
        raise ImageError("connection reset by peer")

    for index in range(1, 6):
        assert run_dream(store, cfg, object(), graph(3 + index), 300.0 * index,
                         condense_fn=good_condense(), render_fn=dead) is None

    assert store.current_dream().sentence == "das gute Bild"
    assert store.current_dream().image_path == "d1.png"
    store.close()


def test_a_whole_day_of_no_connectivity_still_shows_a_calm_screen(tmp_path):
    """Spec §8: „Screen shows the last dream and a full history strip. Looks
    calm, not broken."""
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    seed_display_settings(store, cfg)
    for index in range(1, 6):
        seed_one_good_dream(store, cfg, at=float(index), sentence=f"traum {index}")

    def dead(llm, material, question, contradiction):
        raise RuntimeError("no route to host")

    for index in range(20):
        run_dream(store, cfg, object(), graph(10), 1000.0 + index,
                  condense_fn=dead, render_fn=good_render)

    state = dream_state(store, cfg)
    assert state["current"]["sentence"] == "traum 5"
    assert len(state["history"]) == 4
    store.close()


def test_a_stage_1_timeout_leaves_the_last_image_up(tmp_path):
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    seed_one_good_dream(store, cfg)

    def timeout(llm, material, question, contradiction):
        raise TimeoutError("read timeout")

    assert run_dream(store, cfg, object(), graph(5), 300.0,
                     condense_fn=timeout, render_fn=good_render) is None
    assert store.current_dream().sentence == "das gute Bild"
    store.close()


def test_an_unusable_image_never_reaches_the_wall(tmp_path):
    """Spec §8's „image model returns something unusable" has two halves: a
    malformed body is caught here, and an ugly-but-valid image is the
    operator's discard (tested below)."""
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    seed_one_good_dream(store, cfg)

    assert run_dream(store, cfg, object(), graph(5), 300.0, condense_fn=good_condense(),
                     render_fn=lambda p, **k: b"<html>502 Bad Gateway</html>") is None

    assert store.current_dream().image_path == "d1.png"
    assert not (cfg.image_dir / "d2.png").exists()
    store.close()


def test_the_operator_can_pull_an_embarrassing_image_and_the_previous_returns(tmp_path):
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    seed_display_settings(store, cfg)
    seed_one_good_dream(store, cfg, at=1.0, sentence="harmlos")
    seed_one_good_dream(store, cfg, at=2.0, sentence="peinlich")
    client = TestClient(create_dream_app(store, cfg, EventBus()))

    client.post("/api/discard", json={"dream_id": "d2", "discarded": True})

    state = client.get("/api/state").json()
    assert state["current"]["sentence"] == "harmlos"
    assert state["history"] == []  # spec §7: gone from the strip too
    store.close()


# -- „restart -> strip intact" (spec §11's second priority) -----------------


def test_a_restart_restores_the_current_dream_the_whole_strip_and_the_settings(tmp_path):
    """T1§14 run 21's standard, held for Tool 2: after a restart the screen
    comes back exactly as it stood."""
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    seed_display_settings(store, cfg)
    for index in range(1, 8):
        seed_one_good_dream(store, cfg, at=float(index), sentence=f"traum {index}")
    client = TestClient(create_dream_app(store, cfg, EventBus()))
    # strip_ratio must stay within DisplaySettings' bound (le=0.25, spec §6's
    # measured dominance ceiling) — 0.2 is what tests/test_dream_server.py
    # already uses as a valid, non-default value.
    client.post("/api/display", json={"fade_ms": 700, "typewriter": True, "strip_ratio": 0.2})
    client.post("/api/discard", json={"dream_id": "d3", "discarded": True})
    before = client.get("/api/state").json()
    store.close()  # the crash

    reopened = DreamStore.open(cfg.db_path)
    seed_display_settings(reopened, cfg)
    after = TestClient(create_dream_app(reopened, cfg, EventBus())).get("/api/state").json()

    assert after == before
    assert after["current"]["sentence"] == "traum 7"
    assert len(after["history"]) == 5  # 7 dreams, minus the current, minus d3
    assert after["fade_ms"] == 700
    reopened.close()


def test_the_image_files_survive_a_restart(tmp_path):
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    for index in range(1, 4):
        seed_one_good_dream(store, cfg, at=float(index))
    store.close()

    reopened = DreamStore.open(cfg.db_path)

    for dream in reopened.visible_dreams():
        assert (cfg.image_dir / dream.image_path).is_file()
    reopened.close()


def test_a_dream_interrupted_by_the_crash_is_visibly_incomplete_not_invisible(tmp_path):
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    seed_one_good_dream(store, cfg, sentence="das gute Bild")
    store.create_dream(created_at=300.0, graph_generated_at=299.0, person_count=5,
                       term_count=4, edge_count=6, contradiction=False,
                       guiding_question="Q", absorbed_persons=["p4"])
    store.close()  # killed mid-cycle

    reopened = DreamStore.open(cfg.db_path)

    assert reopened.current_dream().sentence == "das gute Bild"  # not the half one
    assert reopened.get_dream("d2").status == "running"  # honest record
    assert len(reopened.all_dreams()) == 2
    reopened.close()


async def test_a_restart_mid_day_neither_re_dreams_nor_stops_dreaming(tmp_path):
    """The two ways this goes wrong, both in one test."""
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    seed_display_settings(store, cfg)
    for index in range(1, 4):
        seed_one_good_dream(store, cfg, at=float(index))
    store.close()

    reopened = DreamStore.open(cfg.db_path)
    cycles = []

    def counting_cycle(store_, cfg_, llm, g, now, **kwargs):
        cycles.append(now)
        return run_dream(store_, cfg_, llm, g, now,
                         condense_fn=good_condense(), render_fn=good_render)

    watcher = DreamWatcher(cfg, reopened, EventBus(), llm=object(),
                           fetch=lambda url, timeout: graph(3), cycle=counting_cycle,
                           clock=lambda: 99999.0)

    assert await watcher.tick() is None  # nothing new was said
    assert cycles == []

    watcher.fetch = lambda url, timeout: graph(4)  # a fourth interview lands
    assert await watcher.tick() is not None
    assert len(cycles) == 1
    reopened.close()


# -- Tool 1 unreachable (spec §8) -------------------------------------------


async def test_a_dead_tool_1_leaves_the_display_completely_untouched(tmp_path):
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    seed_display_settings(store, cfg)
    seed_one_good_dream(store, cfg, sentence="das gute Bild")
    before = dream_state(store, cfg)

    # The cycle is counted, not just the return value. Checking only the
    # visible state would pass even if the watcher attempted — and failed — a
    # dream on every single poll: `visible_dreams()` filters `status='done'`,
    # so those rows never reach the screen, and the display would look
    # identical while the station burned an attempt every five seconds. Spec §8
    # says no new dreams, not merely no new PICTURES.
    attempts = []

    def counting_cycle(*args, **kwargs):
        attempts.append(1)
        raise AssertionError("no cycle may run while Tool 1 is unreachable")

    watcher = DreamWatcher(cfg, store, EventBus(), llm=object(),
                           fetch=lambda url, timeout: None, cycle=counting_cycle,
                           clock=lambda: 99999.0)
    for _ in range(10):
        assert await watcher.tick() is None

    assert attempts == []
    assert len(store.all_dreams()) == 1  # the one seeded dream, no phantom rows
    assert dream_state(store, cfg) == before
    store.close()


def test_a_half_written_graph_json_is_ignored_rather_than_dreamt_about(tmp_path):
    """Tool 1 writes graph.json atomically (`os.replace`), but a proxy or a
    truncated HTTP body can still deliver half a document."""
    from kg2.graph_client import fetch_graph

    def truncated(url, timeout):
        raise ValueError("Expecting ',' delimiter")

    assert fetch_graph("http://x/graph.json", get=truncated) is None


# -- the operator surface stays usable in every failure ---------------------


def test_the_operator_ui_still_works_while_the_cloud_is_dead(tmp_path):
    """Spec §7's controls must not depend on the thing that is broken."""
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    seed_display_settings(store, cfg)
    seed_one_good_dream(store, cfg)
    client = TestClient(create_dream_app(store, cfg, EventBus()))

    assert client.post("/api/pause", json={"paused": True}).status_code == 200
    assert client.post("/api/display", json={"fade_ms": 500}).status_code == 200
    assert client.post("/api/dream_now").status_code == 200
    assert client.get("/api/state").status_code == 200
    store.close()


# -- documented, not engineered around (spec §8) ---------------------------


def test_a_days_worth_of_images_is_a_non_issue(tmp_path):
    """Spec §8: „~40 images/day at a few hundred KB — a non-issue for one day;
    documented, not engineered around." This test states the assumption so a
    future change that breaks it is visible."""
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    for index in range(1, 41):
        seed_one_good_dream(store, cfg, at=float(index))

    written = list(cfg.image_dir.glob("*.png"))
    assert len(written) == 40
    # One file per dream, never overwritten (spec §5.2).
    assert len({path.name for path in written}) == 40
    store.close()
