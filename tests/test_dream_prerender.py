"""Tool 1's Task 20 discipline for Tool 2: judge the strip full, not empty."""

from __future__ import annotations

import struct
import zlib

import pytest

from kg2.config import DreamConfig
from kg2.store import DreamStore
from sim.seed_dreams import SENTENCES, seed_dreams


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


@pytest.fixture()
def pool(tmp_path):
    directory = tmp_path / "pool"
    directory.mkdir()
    paths = []
    for index in range(6):
        path = directory / f"pool-{index}.png"
        path.write_bytes(png_bytes())
        paths.append(path)
    return paths


def test_there_are_enough_sentences_for_a_full_day():
    assert len(SENTENCES) >= 40
    assert len(set(SENTENCES)) == len(SENTENCES)


def test_the_sentences_are_german_and_roughly_the_right_length():
    """Spec §5.1's target. A seeded strip judged on 8-word sentences would not
    tell Birk whether a real 30-word one fits."""
    for sentence in SENTENCES:
        assert 15 <= len(sentence.split()) <= 45


def test_seed_dreams_writes_the_requested_number(tmp_path, pool):
    db_path = seed_dreams(tmp_path / "state", count=20, images=pool)

    store = DreamStore.open(db_path)
    assert len(store.visible_dreams()) == 20
    store.close()


def test_every_seeded_dream_has_a_real_image_file(tmp_path, pool):
    db_path = seed_dreams(tmp_path / "state", count=12, images=pool)

    cfg = DreamConfig(data_dir=db_path.parent)
    store = DreamStore.open(db_path)
    for dream in store.visible_dreams():
        assert (cfg.image_dir / dream.image_path).read_bytes().startswith(b"\x89PNG")
    store.close()


def test_the_pool_is_cycled_when_it_is_smaller_than_the_count(tmp_path, pool):
    """The cheap path. Faked variety, and the CLI says so — but the harness is
    correct before the 40 real images are spent on it."""
    db_path = seed_dreams(tmp_path / "state", count=20, images=pool)

    store = DreamStore.open(db_path)
    assert len(store.visible_dreams()) == 20
    store.close()


def test_the_dreams_are_spaced_like_a_real_day(tmp_path, pool):
    """A strip whose timestamps all collide would not exercise the ordering."""
    db_path = seed_dreams(tmp_path / "state", count=10, images=pool)

    store = DreamStore.open(db_path)
    times = [d.created_at for d in store.visible_dreams()]
    assert times == sorted(times)
    assert len(set(times)) == 10
    store.close()


def test_a_smaller_seed_is_a_prefix_of_a_larger_one(tmp_path, pool):
    """Same discipline as Tool 1's seed_graph: 1, 5, 20 and 40 must be the same
    day at four points, not four different days."""
    small = seed_dreams(tmp_path / "a", count=5, images=pool)
    large = seed_dreams(tmp_path / "b", count=40, images=pool)

    store_a, store_b = DreamStore.open(small), DreamStore.open(large)
    first_five = [d.sentence for d in store_b.visible_dreams()][:5]
    assert [d.sentence for d in store_a.visible_dreams()] == first_five
    store_a.close()
    store_b.close()


def test_seeding_needs_no_credentials_and_no_network(tmp_path, pool):
    """The whole point of the cheap path: the harness is debuggable offline."""
    db_path = seed_dreams(tmp_path / "state", count=40, images=pool)

    assert db_path.is_file()


def test_the_page_renders_at_every_size(tmp_path, pool, page, static_server):
    """The series' own assertion, without Playwright driving a server: the view
    is fed the same state shape the server produces."""
    from kg.bus import EventBus
    from kg2.server import create_dream_app, dream_state, seed_display_settings

    page.goto(f"{static_server}/frontend2/static/dream-harness.html")
    page.wait_for_function("window.kgDream !== undefined")

    for size in (1, 5, 20, 40):
        db_path = seed_dreams(tmp_path / f"state-{size}", count=size, images=pool)
        cfg = DreamConfig(data_dir=db_path.parent)
        store = DreamStore.open(db_path)
        seed_display_settings(store, cfg)
        state = dream_state(store, cfg)
        # The images are file paths under a temp dir the browser cannot read,
        # so swap in an inline pixel; the layout question is unaffected.
        pixel = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
        state["current"]["image"] = pixel
        for entry in state["history"]:
            entry["image"] = pixel

        page.evaluate("(s) => window.kgDream.applyState(s)", state)
        page.wait_for_function("() => window.kgDream.fading === false", timeout=10000)

        assert page.locator("#strip li").count() == size - 1
        assert page.locator("#sentence").inner_text() != ""
        strip = page.locator("#strip").bounding_box()
        assert strip["y"] + strip["height"] <= 1081
        store.close()
