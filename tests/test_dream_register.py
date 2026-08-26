"""Spec §10 / brainstorm §10 — the register is decided at images, not in words.

These tests pin the comparison's honesty (identical content, one variable) and
the standing rule that this module recommends nothing.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from kg2.config import DreamConfig
from sim.dream_register import FICTIONAL_SENTENCE, REGISTERS, render_samples


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


def test_there_are_three_or_four_registers():
    """Brainstorm §10: „three or four samples". More is not a better decision,
    it is a worse one — nobody compares eight images fairly."""
    assert 3 <= len(REGISTERS) <= 4


def test_the_registers_are_genuinely_different_and_none_is_marked_as_preferred():
    names = list(REGISTERS)
    assert len(set(names)) == len(names)
    assert len(set(REGISTERS.values())) == len(REGISTERS)
    for name in names:
        for forbidden in ("empfohlen", "recommended", "best", "default", "favorit"):
            assert forbidden not in name.lower()


def test_every_register_forbids_text_in_the_image():
    """The sentence is a separate displayed artefact (spec §5.2). Text rendered
    inside the picture would compete with it, in every register."""
    for register in REGISTERS.values():
        assert "keine Schrift" in register


def test_the_sample_content_is_fictional_and_not_from_the_corpus(real_graph):
    """A sample built on real interview material invites judging the CONTENT,
    which is not what is being decided here."""
    labels = {
        node["label"] for node in real_graph["nodes"] if node.get("type") == "term"
    }
    for label in labels:
        assert label not in FICTIONAL_SENTENCE


def test_every_sample_renders_the_identical_sentence(tmp_path):
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    prompts = []

    def fake_render(prompt, **kwargs):
        prompts.append(prompt)
        return png_bytes()

    render_samples(tmp_path / "out", cfg, render_fn=fake_render)

    assert len(prompts) == len(REGISTERS)
    # One variable only: strip each register out and the remainder is identical.
    stripped = {
        prompt.replace(register, "<REGISTER>")
        for prompt, register in zip(prompts, REGISTERS.values())
    }
    assert len(stripped) == 1
    assert all(FICTIONAL_SENTENCE in prompt for prompt in prompts)


def test_the_filenames_say_which_register_they_are(tmp_path):
    cfg = DreamConfig(data_dir=tmp_path / "dream")

    samples = render_samples(tmp_path / "out", cfg, render_fn=lambda p, **k: png_bytes())

    for sample, name in zip(samples, REGISTERS):
        assert name in sample.path.name
        assert sample.path.is_file()


def test_the_filenames_carry_no_ranking(tmp_path):
    """Not `1-…`, `2-…`: a numbered series is an implied ordering, and Birk is
    supposed to read them cold."""
    cfg = DreamConfig(data_dir=tmp_path / "dream")

    samples = render_samples(tmp_path / "out", cfg, render_fn=lambda p, **k: png_bytes())

    for sample in samples:
        assert not sample.path.name[0].isdigit()


def test_one_failing_register_does_not_lose_the_others(tmp_path):
    """A rate limit on sample three must not throw away samples one and two —
    they cost real money."""
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    calls = {"n": 0}

    def flaky(prompt, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("429 rate limited")
        return png_bytes()

    samples = render_samples(tmp_path / "out", cfg, render_fn=flaky)

    assert len(samples) == len(REGISTERS) - 1
    assert calls["n"] == len(REGISTERS)


def test_a_rerun_does_not_overwrite_an_earlier_round(tmp_path):
    """Spec §5.2's rule holds here too: an overwritten sample is a lost
    comparison, and these cost money to make."""
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    render_samples(tmp_path / "out", cfg, render_fn=lambda p, **k: png_bytes())

    second = render_samples(tmp_path / "out", cfg, render_fn=lambda p, **k: png_bytes())

    assert second == []  # every target already existed; nothing was clobbered
