"""Tool 1's Task 20 discipline for Tool 2: judge the strip full, not empty."""

from __future__ import annotations

import struct
import zlib

import pytest

from kg2.config import DreamConfig
from kg2.store import DreamStore
from sim.seed_dreams import SENTENCES, seed_dreams


def png_bytes(index: int = 0) -> bytes:
    """A minimal valid 1x1 PNG, one solid colour keyed off `index`.

    The colour varies by index on purpose (Finding 4): a fixture where every
    pool image is byte-identical makes it IMPOSSIBLE to test that cycling
    actually happened, as opposed to the count merely coming out right — a
    test built on the old constant-bytes version could not have told cycling
    apart from a bug that ran out of images and silently repeated the last
    one forever.
    """
    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    pixel = bytes([0, (index * 37) % 256, (index * 89) % 256])  # filter byte + RGB
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(pixel))
        + chunk(b"IEND", b"")
    )


@pytest.fixture()
def pool(tmp_path):
    directory = tmp_path / "pool"
    directory.mkdir()
    paths = []
    for index in range(6):
        path = directory / f"pool-{index}.png"
        path.write_bytes(png_bytes(index))
        paths.append(path)
    return paths


def test_there_are_enough_sentences_for_a_full_day():
    assert len(SENTENCES) >= 40
    assert len(set(SENTENCES)) == len(SENTENCES)


def test_the_sentences_are_german_and_roughly_the_right_length():
    """Spec §5.1's target, not a looser stand-in for it. The old bound (15-45)
    let the corpus drift to 15-21 words with the docstring still claiming
    20-40 — this asserts the real range, not one loose enough to hide that
    drift happening again."""
    for sentence in SENTENCES:
        assert 20 <= len(sentence.split()) <= 40


def test_the_corpus_actually_reaches_both_ends_of_the_spec_range():
    """A seeded strip judged only on sentences bunched near the bottom of the
    range never exercises the hard case: whether a genuine 36-40 word
    sentence still fits the two-line `#sentence` budget. Asserting the corpus
    contains sentences near BOTH ends (not just that every one is legal) is
    what stops a future edit from quietly shortening them all back to 20ish
    while still passing the range check above."""
    counts = [len(sentence.split()) for sentence in SENTENCES]
    assert min(counts) <= 22, "nothing near the floor of spec §5.1's range"
    assert sum(1 for c in counts if c >= 36) >= 5, "not enough sentences at the hard case (36-40 words)"


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
    correct before the 40 real images are spent on it.

    This must actually verify CYCLING, not just the dream count (which a
    non-cycling implementation — one that ran out of images and errored, or
    silently repeated only the last one — could also satisfy). Dream N and
    dream N + len(pool) are seeded from the SAME source file
    (`seed_dreams`'s `images[index % len(images)]`), so their on-disk image
    bytes must be identical; a dream in between must differ, or the pool
    would not be cycling at all."""
    db_path = seed_dreams(tmp_path / "state", count=20, images=pool)

    cfg = DreamConfig(data_dir=db_path.parent)
    store = DreamStore.open(db_path)
    dreams = store.visible_dreams()
    assert len(dreams) == 20

    def image_bytes(dream):
        return (cfg.image_dir / dream.image_path).read_bytes()

    assert len(pool) == 6, "the cycle-length assumption below needs the fixture's pool size"
    assert image_bytes(dreams[0]) == image_bytes(dreams[6])  # one full cycle apart
    assert image_bytes(dreams[0]) != image_bytes(dreams[1])  # not just one repeated image
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

        # The strip is deliberately capped to the newest `strip_max` dreams
        # (kg2/server.py's dream_state()) — 40 on screen at once was judged
        # too many (docs/operations.md, 2026-08-26). Every entry still comes
        # from the real record; nothing here is about deletion.
        assert page.locator("#strip li").count() == min(size - 1, cfg.default_strip_max)
        assert page.locator("#sentence").inner_text() != ""
        strip = page.locator("#strip").bounding_box()
        assert strip["y"] + strip["height"] <= 1081
        store.close()


# -- Finding 3: --generate dies with an actionable message, not a traceback --


def test_generate_dies_with_an_actionable_message_when_the_api_key_is_unset(tmp_path):
    """--generate used to fall straight into _generate_images and die with a
    raw traceback through render_image -> ImageError. No money was ever at
    risk either way (render_image also checks the key before any network
    call) — but a traceback is not an actionable message on festival morning.
    Same bar _pool_images already sets: a clean SystemExit naming what to
    export and what the run would have cost."""
    from sim.dream_prerender import _check_generate_credentials

    cfg = DreamConfig(data_dir=tmp_path, openrouter_api_key=None)
    with pytest.raises(SystemExit) as excinfo:
        _check_generate_credentials(cfg, count=40)

    message = str(excinfo.value)
    assert "OPENROUTER_API_KEY" in message
    assert "40" in message  # the cost, spelled out, not just "it costs something"


def test_generate_credentials_check_is_a_noop_when_the_key_is_set(tmp_path):
    from sim.dream_prerender import _check_generate_credentials

    cfg = DreamConfig(data_dir=tmp_path, openrouter_api_key="sk-fake-for-the-test")
    _check_generate_credentials(cfg, count=40)  # must not raise


# -- Finding 1: a content-bearing placeholder pool, not solid colours --------


def test_the_placeholder_pool_is_content_bearing_not_solid_colour(tmp_path):
    """Root cause of Finding 1's missed defect: a solid-colour placeholder
    pool crops to the same solid colour at any width, so a strip built on one
    cannot show whether cropping destroyed anything. Checked against actual
    pixel content, not just the PNG header, so this cannot pass on a pool
    that is secretly flat again."""
    from PIL import Image

    from sim.dream_prerender import make_placeholder_pool

    paths = make_placeholder_pool(tmp_path / "pool", 3)

    assert len(paths) == 3
    corners = []
    for path in paths:
        assert path.is_file()
        image = Image.open(path)
        assert image.size == (1600, 900)
        left = image.getpixel((150, 450))
        centre = image.getpixel((800, 450))
        right = image.getpixel((1450, 450))
        # Distinct regions, distinct colours: a solid fill would make all
        # three identical, and a crop of it would prove nothing either.
        assert len({left, centre, right}) == 3
        corners.append(image.getpixel((5, 5)))  # background, outside every shape

    # Distinct index -> distinct background, so the pool images differ from
    # EACH OTHER too, not only internally.
    assert len(set(corners)) == len(paths)
