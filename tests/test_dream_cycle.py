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


def jpeg_bytes() -> bytes:
    """A minimal valid JFIF/JPEG header (SOI, APP0, EOI) — the byte shape the
    contract document recorded from the live endpoint, „Abweichung 3"."""
    return (
        b"\xff\xd8"
        + b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        + b"\xff\xd9"
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


def good_condense(
    sentence="Der Beton träumt von Wald.",
    sentence_en=None,
    image_description="A slab of grey concrete stands in a clearing of thin birch trunks.",
    tension_source="restoring an existing façade while billing it as new construction",
    mood=3,
    tension=3,
):
    from kg2.condense import CondenseResult

    def fn(llm, material, **_):
        return CondenseResult(
            prompt="P", sentence=sentence,
            sentence_en=sentence_en if sentence_en is not None else sentence,
            image_description=image_description,
            tension_source=tension_source,
            mood=mood, tension=tension,
        )

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


def test_everything_stage_1_produced_is_recorded_including_the_image_channel(tmp_path):
    """Spec §5.3: what was sent is what is stored. Since 2026-08-29 stage 1
    returns two more texts than the wall needs — the longer description the
    image is built on and the material's own contradiction — and both are
    part of the record, not scratch values thrown away after the render."""
    cfg, store = setup(tmp_path)

    dream = run_dream(
        store, cfg, llm=object(), graph=graph(), now=1.0,
        condense_fn=good_condense(
            sentence="Der Beton träumt von Wald.",
            sentence_en="Concrete dreams of the forest.",
            image_description="A slab of grey concrete stands among thin birch trunks.",
            tension_source="renovating a façade while billing it as new construction",
        ),
        render_fn=good_render(),
    )

    assert dream.sentence == "Der Beton träumt von Wald."
    assert dream.sentence_en == "Concrete dreams of the forest."
    assert dream.image_description == "A slab of grey concrete stands among thin birch trunks."
    assert dream.tension_source == "renovating a façade while billing it as new construction"
    store.close()


def test_the_image_prompt_is_built_from_the_description_and_the_contradiction(tmp_path):
    """The two findings of 2026-08-29, end to end: the image model is given
    the longer description as its motif (Befund B) and is told what the
    contradiction actually is instead of inventing one (Befund A). Asserted
    on `stage2_prompt`, which is by definition what was sent (spec §5.3)."""
    cfg, store = setup(tmp_path)
    sent = []

    dream = run_dream(
        store, cfg, llm=object(), graph=graph(), now=1.0,
        condense_fn=good_condense(
            sentence="Der Beton träumt von Wald.",
            sentence_en="Concrete dreams of the forest.",
            image_description="A slab of grey concrete stands among thin birch trunks.",
            tension_source="renovating a façade while billing it as new construction",
        ),
        render_fn=lambda prompt, **kwargs: (sent.append(prompt), png_bytes())[1],
    )

    assert dream.stage2_prompt.startswith(
        "A slab of grey concrete stands among thin birch trunks."
    )
    assert "renovating a façade while billing it as new construction" in dream.stage2_prompt
    # The literal wall translation is recorded but is no longer the motif.
    assert "Concrete dreams of the forest." not in dream.stage2_prompt
    assert sent == [dream.stage2_prompt]  # what was recorded is what was sent
    store.close()


def test_a_dream_without_the_new_fields_still_renders(tmp_path):
    """The failure that must never happen: a stage 1 that returned neither a
    description nor a contradiction still produces an image, because
    `build_image_prompt` falls back to the English sentence (spec §8)."""
    cfg, store = setup(tmp_path)

    dream = run_dream(
        store, cfg, llm=object(), graph=graph(), now=1.0,
        condense_fn=good_condense(
            sentence="Der Beton träumt von Wald.",
            sentence_en="Concrete dreams of the forest.",
            image_description="",
            tension_source="",
        ),
        render_fn=good_render(),
    )

    assert dream.status == "done"
    assert dream.stage2_prompt.startswith("Concrete dreams of the forest.")
    store.close()


def test_a_jpeg_response_lands_with_a_jpg_extension_everywhere_the_path_is_read(tmp_path):
    """Contract document, „Abweichung 3": the model returns JPEG on roughly 2
    of 5 calls, an equally valid image. The name recorded in `dreams.sqlite3`
    (`image_path`) must be the same name the file actually has on disk, or
    `/media/images/<image_path>` (kg2/server.py) 404s in the browser."""
    cfg, store = setup(tmp_path)

    dream = run_dream(
        store, cfg, llm=object(), graph=graph(), now=1.0,
        condense_fn=good_condense(), render_fn=good_render(jpeg_bytes()),
    )

    assert dream.status == "done"
    assert dream.image_path == "d1.jpg"
    assert (cfg.image_dir / "d1.jpg").read_bytes() == jpeg_bytes()
    assert not (cfg.image_dir / "d1.png").exists()
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


# -- the contradiction clause is gone (2026-08-28) ---------------------------


def test_a_dream_never_records_a_contradiction_regardless_of_size(tmp_path):
    """The clause is gone (kg2/condense.py); the DB column stays for the old
    schema shape but is always written False now (kg2/store.py)."""
    cfg, store = setup(tmp_path)

    small = run_dream(store, cfg, object(), graph(persons=3), 1.0,
                       condense_fn=good_condense(), render_fn=good_render())
    large = run_dream(store, cfg, object(), graph(persons=8), 300.0,
                       condense_fn=good_condense(), render_fn=good_render())

    assert small.contradiction is False
    assert large.contradiction is False
    store.close()


# -- failure ----------------------------------------------------------------


def test_a_stage_1_failure_leaves_the_previous_image_up(tmp_path):
    """Spec §8, the failure mode that matters most."""
    cfg, store = setup(tmp_path)
    run_dream(store, cfg, object(), graph(), 1.0,
              condense_fn=good_condense("das gute Bild"), render_fn=good_render())

    def boom(llm, material, **_):
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

    def boom(llm, material, **_):
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

    def interrupt(llm, material, **_):
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
    Finding 1 called out. Hardened, the bad id is just dropped rather than
    crashing — but dropping it also leaves zero real material (the term node
    survives, but with no valid edge reaching it once its only source id is
    filtered out), so Finding 2's empty-material guard now means this
    degrades to no dream and no row at all, not a `done` dream over an
    all-zero graph."""
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

    assert result is None
    assert store.all_dreams() == []
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

    def note_and_die(llm, material, **_):
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


# -- empty material (Finding 2) ---------------------------------------------


def empty_graph() -> dict:
    return {
        "version": 1, "generated_at": 1.0, "min_mentions": 1,
        "nodes": [], "edges": [], "quotes": [],
    }


def one_unprocessed_person_graph() -> dict:
    """T1's first `graph.json` broadcast per interview (spec §4.1): the photo
    landed, the pipeline has not run yet. Same shape of nothing as the empty
    graph — "1 Menschen, 0 Begriffe" is still zero terms for stage 1."""
    return {
        "version": 1, "generated_at": 1.0, "min_mentions": 1,
        "nodes": [
            {"id": "p1", "type": "person", "portrait": None, "created_at": 1.0,
             "hidden": False, "x": None, "y": None},
        ],
        "edges": [], "quotes": [],
    }


def test_a_forced_cycle_on_an_empty_graph_produces_no_dream_and_no_row(tmp_path):
    """Finding 2: exactly the spec's own use case for 'Dream now' — someone
    from the organiser at 09:00, before the first interview. Without the
    guard, stage 1's prompt still ends 'Antworte mit genau einem Satz' and
    the model invents a dream from nothing."""
    cfg, store = setup(tmp_path)

    result = run_dream(store, cfg, object(), empty_graph(), 1.0,
                       condense_fn=good_condense(), render_fn=good_render())

    assert result is None
    assert store.all_dreams() == []
    store.close()


def test_a_forced_cycle_on_one_photographed_unprocessed_person_produces_no_dream(tmp_path):
    cfg, store = setup(tmp_path)

    result = run_dream(store, cfg, object(), one_unprocessed_person_graph(), 1.0,
                       condense_fn=good_condense(), render_fn=good_render())

    assert result is None
    assert store.all_dreams() == []
    store.close()


def test_a_forced_cycle_with_real_material_still_works(tmp_path):
    """The guard must not swallow a legitimate 'Dream now' that has real
    material behind it — only the genuinely empty case."""
    cfg, store = setup(tmp_path)

    result = run_dream(store, cfg, object(), graph(persons=3), 1.0,
                       condense_fn=good_condense(), render_fn=good_render())

    assert result is not None
    assert result.status == "done"
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
        assert dream.contradiction is False
        store.close()
