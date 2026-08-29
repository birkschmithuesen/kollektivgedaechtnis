"""Failure modes and crash recovery (spec §13, §10.5).

Every failure mode the spec names is covered here or cross-referenced to the
task that already covers it:

| Failure mode                     | Covered by                                |
|----------------------------------|-------------------------------------------|
| STT server unreachable           | Task 3 reconnect test + `test_a_dead_stt…` |
| Telegram offline / broken photo  | Task 7 (`test_a_failed_download…`)        |
| LLM fails / invalid JSON         | Task 8 retry, Task 11 `failed` status     |
| Photo without stop               | Task 5 + the tick timeout                 |
| Stop without photo               | Task 5 (ignored)                          |
| Crash + restart, incl. positions | this file                                 |
"""

from __future__ import annotations

import json

from kg.bus import EventBus
from kg.config import Config
from kg.core import Core
from kg.embeddings import HashEmbedder
from kg.export import build_graph, write_graph_json
from kg.pipeline import ProcessResult
from kg.store import Store
from kg.transcript import TranscriptLog


def build_state(cfg):
    store = Store.open(cfg.db_path)
    person = store.create_person(started_at=100.0, portrait_path="portraits/a.png")
    term = store.get_or_create_term("Recycling-Beton", created_at=110.0)
    store.add_edge(person.id, term.id, created_at=111.0)
    store.add_quote(person.id, "Wir bauen zu viel Neues.", created_at=112.0)
    store.save_positions({person.id: (12.0, -8.0), term.id: (40.0, 3.0)})
    store.set_setting("max_terms", "45")
    store.set_setting("camera_mode", "pan")
    store.close_person(person.id, stopped_at=160.0, reason="text")
    return store


def test_full_state_including_positions_survives_a_restart(tmp_path):
    cfg = Config(data_dir=tmp_path / "state")
    store = build_state(cfg)
    before = build_graph(store)
    store.close()  # simulate the crash

    reopened = Store.open(cfg.db_path)
    after = build_graph(reopened)

    assert after["nodes"] == before["nodes"]
    assert after["edges"] == before["edges"]
    assert after["quotes"] == before["quotes"]
    assert after["max_terms"] == 45
    assert reopened.get_setting("camera_mode", "fit") == "pan"
    reopened.close()


def test_graph_json_is_rebuilt_from_sqlite_after_a_restart(tmp_path):
    cfg = Config(data_dir=tmp_path / "state")
    store = build_state(cfg)
    store.close()
    cfg.graph_json_path.unlink(missing_ok=True)

    reopened = Store.open(cfg.db_path)
    write_graph_json(reopened, cfg.graph_json_path)

    graph = json.loads(cfg.graph_json_path.read_text(encoding="utf-8"))
    assert len(graph["nodes"]) == 2
    positions = {node["id"]: (node["x"], node["y"]) for node in graph["nodes"]}
    assert positions["p1"] == (12.0, -8.0)
    reopened.close()


def test_a_corrupt_graph_json_does_not_block_the_rebuild(tmp_path):
    cfg = Config(data_dir=tmp_path / "state")
    store = build_state(cfg)
    store.close()
    cfg.graph_json_path.write_text("{ half written", encoding="utf-8")

    reopened = Store.open(cfg.db_path)
    write_graph_json(reopened, cfg.graph_json_path)

    assert json.loads(cfg.graph_json_path.read_text(encoding="utf-8"))["version"] == 1
    reopened.close()


async def test_an_interview_open_at_crash_time_can_still_be_closed_after_restart(tmp_path):
    """The restart must RESUME the open interview, not forget it.

    Forgetting it would strand the pre-crash person with `stopped_at IS NULL`
    forever — invisible to every code path — and open a second interview on
    the next photo, breaking the serial-interview guarantee (spec §5).
    """
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    store.create_person(started_at=100.0, portrait_path="portraits/a.png")
    store.close()  # crash while an interview is running

    reopened = Store.open(cfg.db_path)
    assert reopened.open_person().id == "p1"
    processed: list[str] = []

    def processor(store_, cfg_, llm_, embedder_, log_, person_id, *rest, **kwargs):
        processed.append(person_id)
        return ProcessResult(person_id, "done", [], "")

    core = Core(
        cfg=cfg,
        store=reopened,
        bus=EventBus(),
        transcript_log=TranscriptLog(cfg.transcript_log_path),
        llm=object(),
        embedder=HashEmbedder(dim=16),
        processor=processor,
    )
    # The tracker adopted the open interview at construction time.
    assert core.tracker.open_since == 100.0

    core.on_text("fertig", at=500.0)
    await core.drain()

    assert reopened.get_person("p1").stop_reason == "text"
    assert processed == ["p1"]
    reopened.close()


async def test_a_dead_stt_server_is_visible_but_not_fatal(tmp_path):
    """The station keeps working without STT: the portrait still lands."""
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    core = Core(
        cfg=cfg,
        store=store,
        bus=EventBus(),
        transcript_log=TranscriptLog(cfg.transcript_log_path),
        llm=object(),
        embedder=HashEmbedder(dim=16),
        processor=lambda *a: ProcessResult("p1", "done", [], ""),
    )

    core.on_stt_state(False)
    core.on_photo(photo_path="a.jpg", portrait_path="a.png", at=100.0)
    await core.drain()

    assert store.get_setting("stt_connected", "1") == "0"
    assert store.open_person() is not None
    store.close()


def test_the_operators_live_settings_win_over_the_configured_defaults(tmp_path):
    """A restart must not reset the dial the operator turned (spec §7, §10.5)."""
    cfg = Config(data_dir=tmp_path / "state", default_max_terms=32)
    store = Store.open(cfg.db_path)
    store.set_setting_default("max_terms", str(cfg.default_max_terms))
    store.set_setting("max_terms", "45")  # operator opened it up during the day
    store.close()

    reopened = Store.open(cfg.db_path)
    reopened.set_setting_default("max_terms", str(cfg.default_max_terms))

    assert reopened.get_setting("max_terms", "1") == "45"
    reopened.close()
