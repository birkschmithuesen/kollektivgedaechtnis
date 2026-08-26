"""Spec §5.3 + §8 — one dream, and what is left behind when it fails."""

from __future__ import annotations

import base64
import struct
import zlib

from kg2.config import DreamConfig
from kg2.cycle import run_dream
from kg2.imagegen import ImageError
from kg2.store import DreamStore


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


def graph(persons=8, generated_at=1700000000.0) -> dict:
    nodes = [
        {"id": f"p{i}", "type": "person", "portrait": None, "created_at": 1.0,
         "hidden": False, "x": None, "y": None}
        for i in range(persons)
    ] + [
        {"id": "t1", "type": "term", "label": "Weiterbauen im Bestand", "mentions": persons,
         "created_at": 2.0, "hidden": False, "x": None, "y": None}
    ]
    return {
        "version": 1, "generated_at": generated_at, "min_mentions": 1, "nodes": nodes,
        "edges": [{"id": f"e{i}", "source": f"p{i}", "target": "t1"} for i in range(persons)],
        "quotes": [{"id": "q1", "person_id": "p0", "text": "Wir bauen zu viel Neues."}],
    }


def setup(tmp_path, **overrides):
    cfg = DreamConfig(data_dir=tmp_path / "dream", **overrides)
    return cfg, DreamStore.open(cfg.db_path)


def good_condense(sentence="Der Beton träumt von Wald."):
    from kg2.condense import CondenseResult

    def fn(llm, material, question, contradiction):
        return CondenseResult(prompt=f"P(contradiction={contradiction})", sentence=sentence)

    return fn


def good_render(data=None):
    def fn(prompt, **kwargs):
        return data if data is not None else png_bytes()

    return fn


# -- the happy path ---------------------------------------------------------


def test_a_successful_dream_records_everything_spec_5_3_asks_for(tmp_path):
    cfg, store = setup(tmp_path)

    dream = run_dream(
        store, cfg, llm=object(), graph=graph(), now=5000.0,
        condense_fn=good_condense(), render_fn=good_render(),
    )

    assert dream is not None
    assert dream.status == "done"
    assert dream.created_at == 5000.0
    assert dream.graph_generated_at == 1700000000.0
    assert dream.person_count == 8
    assert dream.term_count == 1
    assert dream.edge_count == 8
    assert dream.sentence == "Der Beton träumt von Wald."
    assert dream.stage1_prompt
    assert dream.stage2_prompt
    assert dream.condense_model == "claude-opus-5"
    assert dream.image_model == "google/gemini-3-pro-image"
    assert dream.guiding_question == cfg.guiding_question
    assert dream.absorbed_persons == [f"p{i}" for i in range(8)]
    assert dream.discarded is False
    store.close()


def test_the_image_lands_at_images_slash_dream_id_png(tmp_path):
    cfg, store = setup(tmp_path)

    dream = run_dream(
        store, cfg, llm=object(), graph=graph(), now=1.0,
        condense_fn=good_condense(), render_fn=good_render(),
    )

    assert dream.image_path == "d1.png"
    assert (cfg.image_dir / "d1.png").read_bytes() == png_bytes()
    store.close()


def test_the_new_dream_becomes_the_current_one(tmp_path):
    cfg, store = setup(tmp_path)

    run_dream(store, cfg, object(), graph(), 1.0,
              condense_fn=good_condense("erst"), render_fn=good_render())
    run_dream(store, cfg, object(), graph(), 300.0,
              condense_fn=good_condense("dann"), render_fn=good_render())

    assert store.current_dream().sentence == "dann"
    assert [d.sentence for d in store.history()] == ["erst"]
    store.close()


# -- the contradiction threshold -------------------------------------------


def test_the_contradiction_instruction_is_on_above_the_threshold(tmp_path):
    cfg, store = setup(tmp_path, contradiction_min_persons=6)

    dream = run_dream(store, cfg, object(), graph(persons=8), 1.0,
                      condense_fn=good_condense(), render_fn=good_render())

    assert dream.contradiction is True
    assert "contradiction=True" in dream.stage1_prompt
    store.close()


def test_the_contradiction_instruction_is_off_below_the_threshold(tmp_path):
    """Spec §5.1: with three interviews the model would invent an opposition."""
    cfg, store = setup(tmp_path, contradiction_min_persons=6)

    dream = run_dream(store, cfg, object(), graph(persons=3), 1.0,
                      condense_fn=good_condense(), render_fn=good_render())

    assert dream.contradiction is False
    assert "contradiction=False" in dream.stage1_prompt
    store.close()


# -- failure ----------------------------------------------------------------


def test_a_stage_1_failure_leaves_the_previous_image_up(tmp_path):
    """Spec §8, the failure mode that matters most."""
    cfg, store = setup(tmp_path)
    run_dream(store, cfg, object(), graph(), 1.0,
              condense_fn=good_condense("das gute Bild"), render_fn=good_render())

    def boom(llm, material, question, contradiction):
        raise RuntimeError("llm call failed after 2 attempts")

    result = run_dream(store, cfg, object(), graph(), 300.0,
                       condense_fn=boom, render_fn=good_render())

    assert result is None
    assert store.current_dream().sentence == "das gute Bild"
    assert store.get_dream("d2").status == "failed"
    assert "llm call failed" in store.get_dream("d2").error
    store.close()


def test_a_stage_2_failure_leaves_the_previous_image_up_and_keeps_the_sentence(tmp_path):
    cfg, store = setup(tmp_path)
    run_dream(store, cfg, object(), graph(), 1.0,
              condense_fn=good_condense("das gute Bild"), render_fn=good_render())

    def boom(prompt, **kwargs):
        raise ImageError("502 from the image model")

    result = run_dream(store, cfg, object(), graph(), 300.0,
                       condense_fn=good_condense("kam bis zum Satz"), render_fn=boom)

    assert result is None
    assert store.current_dream().sentence == "das gute Bild"
    failed = store.get_dream("d2")
    assert failed.status == "failed"
    # Spec §5.3: the prompt that produced nothing is the one worth reading.
    assert failed.sentence == "kam bis zum Satz"
    assert failed.stage2_prompt
    store.close()


def test_a_failure_with_no_previous_dream_leaves_the_screen_empty_not_broken(tmp_path):
    cfg, store = setup(tmp_path)

    def boom(llm, material, question, contradiction):
        raise RuntimeError("no connectivity at all")

    assert run_dream(store, cfg, object(), graph(), 1.0,
                     condense_fn=boom, render_fn=good_render()) is None
    assert store.current_dream() is None
    assert store.history() == []
    store.close()


def test_run_dream_never_raises_for_an_ordinary_failure(tmp_path):
    """The watcher must not be one exception away from a dead poll loop."""
    cfg, store = setup(tmp_path)

    for breaker in (
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
        lambda *a, **k: (_ for _ in ()).throw(ValueError("empty sentence")),
    ):
        assert run_dream(store, cfg, object(), graph(), 1.0,
                         condense_fn=breaker, render_fn=good_render()) is None
    store.close()


def test_a_keyboard_interrupt_propagates_after_closing_the_row(tmp_path):
    """Absorbing the operator's shutdown signal as an ordinary failed dream
    would leave the process running with no way to stop it. The row must
    still be closed honestly, but the interrupt itself has to escape."""
    cfg, store = setup(tmp_path)

    def interrupt(llm, material, question, contradiction):
        raise KeyboardInterrupt()

    try:
        run_dream(store, cfg, object(), graph(), 1.0,
                  condense_fn=interrupt, render_fn=good_render())
        raised = False
    except KeyboardInterrupt:
        raised = True

    assert raised is True
    assert store.get_dream("d1").status == "failed"
    store.close()


# -- adversarial graphs (spec §4.1 boundary, Finding 1) ---------------------


def test_a_person_with_a_list_id_does_not_crash_the_cycle(tmp_path):
    """`kg2.graph_client.fetch_graph` never checks value types. An unhashable
    id used to blow up `absorbed_persons`'s set comprehension before the row
    could even be created, leaving no record at all — the worse failure mode
    Finding 1 called out. Hardened, the bad id is just dropped: the cycle
    degrades to an (almost) empty dream rather than crashing OR skipping."""
    cfg, store = setup(tmp_path)
    bad = {
        "version": 1, "generated_at": 1.0, "min_mentions": 1,
        "nodes": [
            {"id": ["weird"], "type": "person", "hidden": False},
            {"id": "t1", "type": "term", "label": "x", "mentions": 1, "hidden": False},
        ],
        "edges": [{"id": "e1", "source": ["weird"], "target": "t1"}],
        "quotes": [],
    }

    result = run_dream(store, cfg, object(), bad, 1.0,
                       condense_fn=good_condense(), render_fn=good_render())

    assert result is not None
    assert result.status == "done"
    assert result.person_count == 0
    assert result.absorbed_persons == []
    store.close()


def test_mixed_type_person_ids_do_not_crash_the_sort(tmp_path):
    """Two person ids of different types, both with edges: `sorted({2, 'p1'})`
    raised before ids were filtered to strings. The hardened trigger simply
    drops the non-string id rather than treating the whole graph as broken."""
    cfg, store = setup(tmp_path)
    bad = {
        "version": 1, "generated_at": 1.0, "min_mentions": 1,
        "nodes": [
            {"id": "p1", "type": "person", "hidden": False},
            {"id": 2, "type": "person", "hidden": False},
            {"id": "t1", "type": "term", "label": "x", "mentions": 2, "hidden": False},
        ],
        "edges": [
            {"id": "e1", "source": "p1", "target": "t1"},
            {"id": "e2", "source": 2, "target": "t1"},
        ],
        "quotes": [],
    }

    result = run_dream(store, cfg, object(), bad, 1.0,
                       condense_fn=good_condense(), render_fn=good_render())

    assert result is not None
    assert result.status == "done"
    assert result.absorbed_persons == ["p1"]
    store.close()


def test_non_comparable_term_labels_do_not_crash_the_sort(tmp_path):
    """Two terms tied on mention count, one with a string label and one with
    a non-string label: `weights.sort(key=lambda w: (-w.mentions, w.label))`
    raised before labels were filtered to strings."""
    cfg, store = setup(tmp_path)
    bad = {
        "version": 1, "generated_at": 1.0, "min_mentions": 1,
        "nodes": [
            {"id": "p1", "type": "person", "hidden": False},
            {"id": "t1", "type": "term", "label": "x", "mentions": 1, "hidden": False},
            {"id": "t2", "type": "term", "label": 42, "mentions": 1, "hidden": False},
        ],
        "edges": [
            {"id": "e1", "source": "p1", "target": "t1"},
            {"id": "e2", "source": "p1", "target": "t2"},
        ],
        "quotes": [],
    }

    result = run_dream(store, cfg, object(), bad, 1.0,
                       condense_fn=good_condense(), render_fn=good_render())

    assert result is not None
    assert result.status == "done"
    store.close()


def test_a_non_png_body_fails_the_dream_rather_than_landing_on_the_wall(tmp_path):
    cfg, store = setup(tmp_path)

    result = run_dream(store, cfg, object(), graph(), 1.0,
                       condense_fn=good_condense(), render_fn=good_render(b"<html>502</html>"))

    assert result is None
    assert store.get_dream("d1").status == "failed"
    assert not (cfg.image_dir / "d1.png").exists()
    store.close()


def test_the_row_exists_even_if_the_process_dies_mid_cycle(tmp_path):
    """The row is written before the first cloud call, so a kill leaves a
    visibly incomplete record rather than no record."""
    cfg, store = setup(tmp_path)
    seen = {}

    def note_and_die(llm, material, question, contradiction):
        seen["row"] = store.get_dream("d1")
        raise RuntimeError("killed")

    run_dream(store, cfg, object(), graph(), 1.0,
              condense_fn=note_and_die, render_fn=good_render())

    assert seen["row"] is not None
    assert seen["row"].status == "running"
    store.close()


# -- the typewriter hook ----------------------------------------------------


def test_the_sentence_is_announced_as_soon_as_stage_1_returns(tmp_path):
    """Spec §6's typewriter builds the sentence up WHILE stage 2 runs. Without
    this hook the display would only learn of the dream once it was finished,
    and the variant could not exist at all."""
    cfg, store = setup(tmp_path)
    announced = []

    def slow_render(prompt, **kwargs):
        assert announced == ["Der Beton träumt."]  # announced BEFORE the render
        return png_bytes()

    run_dream(store, cfg, object(), graph(), 1.0,
              condense_fn=good_condense("Der Beton träumt."), render_fn=slow_render,
              on_sentence=announced.append)

    assert announced == ["Der Beton träumt."]
    store.close()


def test_a_broken_on_sentence_callback_does_not_fail_the_dream(tmp_path):
    """The typewriter is decoration. It must never cost an image."""
    cfg, store = setup(tmp_path)

    def broken(sentence):
        raise RuntimeError("bus is full")

    dream = run_dream(store, cfg, object(), graph(), 1.0,
                      condense_fn=good_condense(), render_fn=good_render(),
                      on_sentence=broken)

    assert dream is not None
    assert dream.status == "done"
    store.close()


# -- against the real thing -------------------------------------------------


def test_a_dream_over_the_real_replay_graph(real_graph):
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        cfg = DreamConfig(data_dir=Path(tmp) / "dream")
        store = DreamStore.open(cfg.db_path)

        dream = run_dream(store, cfg, object(), real_graph, 1700020000.0,
                          condense_fn=good_condense(), render_fn=good_render())

        assert dream.person_count == 60
        assert dream.term_count == 163
        assert dream.edge_count == 267
        assert len(dream.absorbed_persons) == 60
        assert dream.contradiction is True  # 60 >= 6
        store.close()
