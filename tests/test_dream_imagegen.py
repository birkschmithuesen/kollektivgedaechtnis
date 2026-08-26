"""Spec §5.2 — the image. Every network call is injected; nothing here dials out.

The response shape asserted below is the one recorded in
`docs/dream-image-contract.md` after probing the real endpoint. If that document
and this file ever disagree, the document is right and this file is stale.
"""

from __future__ import annotations

import base64
import struct
import zlib
from pathlib import Path

import pytest

from kg2.imagegen import ImageError, build_image_prompt, decode_image, render_image, save_image

REGISTER = (
    "Malerisch und atmosphärisch, weiche Übergänge, gedämpfte Farbigkeit, "
    "diffuses Licht, sichtbarer Pinselduktus. Kein Fotorealismus, kein "
    "Architektur-Rendering, keine Schrift im Bild."
)
SENTENCE = "Der Beton träumt von Wald, und der Wald schickt Rechnungen."


def png_bytes() -> bytes:
    """A real 1x1 PNG, so `save_image` is tested against a file and not a blob."""
    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
        + chunk(b"IEND", b"")
    )


def response_with(data: bytes) -> dict:
    url = "data:image/png;base64," + base64.b64encode(data).decode("ascii")
    return {
        "choices": [
            {"message": {"role": "assistant", "content": "",
                         "images": [{"type": "image_url", "image_url": {"url": url}}]}}
        ]
    }


# -- the prompt -------------------------------------------------------------


def test_the_register_is_appended_to_every_prompt():
    """Spec §5.2: held in config as a style suffix, never model-chosen, never
    graph-driven. The history strip is a measurement series and exactly one
    variable may change — and that is the material."""
    prompt = build_image_prompt(SENTENCE, REGISTER, "16:9")

    assert SENTENCE in prompt
    assert REGISTER in prompt


def test_the_aspect_ratio_is_landscape_and_stated():
    """Spec §5.2: matching the 65″ screen."""
    prompt = build_image_prompt(SENTENCE, REGISTER, "16:9")

    assert "16:9" in prompt
    assert "Querformat" in prompt


def test_the_sentence_comes_first_so_it_is_the_subject():
    """The register is boilerplate. A prompt that opens with lighting
    instructions gets an image about lighting."""
    prompt = build_image_prompt(SENTENCE, REGISTER, "16:9")

    assert prompt.index(SENTENCE) < prompt.index(REGISTER)


def test_two_sentences_share_a_register_exactly():
    a = build_image_prompt("Satz A.", REGISTER, "16:9")
    b = build_image_prompt("Satz B.", REGISTER, "16:9")

    assert a.replace("Satz A.", "X") == b.replace("Satz B.", "X")


# -- decoding ---------------------------------------------------------------


def test_decode_image_reads_the_data_url_from_the_verified_shape():
    assert decode_image(response_with(png_bytes())) == png_bytes()


def test_decode_image_rejects_a_text_only_answer():
    """The commonest real failure: the model answers ABOUT the image."""
    payload = {"choices": [{"message": {"role": "assistant", "content": "Gerne! Hier..."}}]}

    with pytest.raises(ImageError):
        decode_image(payload)


def test_decode_image_rejects_an_empty_image_list():
    payload = {"choices": [{"message": {"role": "assistant", "content": "", "images": []}}]}

    with pytest.raises(ImageError):
        decode_image(payload)


def test_decode_image_rejects_a_url_that_is_not_inline_data():
    payload = {
        "choices": [{"message": {"images": [{"image_url": {"url": "https://example/x.png"}}]}}]
    }

    with pytest.raises(ImageError):
        decode_image(payload)


def test_decode_image_rejects_an_empty_payload():
    with pytest.raises(ImageError):
        decode_image({"choices": []})


# -- the call ---------------------------------------------------------------


def test_render_image_posts_the_contracted_request():
    seen = {}

    def fake_post(url, headers, json, timeout):
        seen.update(url=url, headers=headers, json=json, timeout=timeout)
        return response_with(png_bytes())

    data = render_image(
        "ein prompt",
        model="google/gemini-3-pro-image",
        api_key="sk-or-test",
        url="https://openrouter.ai/api/v1/chat/completions",
        timeout=180.0,
        post=fake_post,
    )

    assert data == png_bytes()
    assert seen["json"]["model"] == "google/gemini-3-pro-image"
    # Without `modalities` the model answers in text about the image.
    assert seen["json"]["modalities"] == ["image", "text"]
    assert seen["json"]["messages"] == [{"role": "user", "content": "ein prompt"}]
    assert seen["headers"]["Authorization"] == "Bearer sk-or-test"
    assert seen["timeout"] == 180.0


def test_render_image_without_a_key_fails_loudly():
    """Spec §2: credentials from the environment. A missing key must say so, not
    produce an opaque 401 at 14:00."""
    with pytest.raises(ImageError, match="OPENROUTER_API_KEY"):
        render_image("p", model="m", api_key=None, url="u", timeout=1.0, post=lambda **k: {})


def test_render_image_turns_a_transport_failure_into_an_image_error():
    """One exception type for the cycle to catch (spec §8)."""

    def dead(url, headers, json, timeout):
        raise OSError("connection reset")

    with pytest.raises(ImageError):
        render_image("p", model="m", api_key="k", url="u", timeout=1.0, post=dead)


def test_render_image_does_not_retry():
    """Spec §8: „Retry at the next trigger — never a retry storm." A retry here
    would triple the cost of every outage and delay the next real dream."""
    calls = []

    def counting(url, headers, json, timeout):
        calls.append(1)
        raise OSError("boom")

    with pytest.raises(ImageError):
        render_image("p", model="m", api_key="k", url="u", timeout=1.0, post=counting)

    assert len(calls) == 1


# -- saving -----------------------------------------------------------------


def test_save_image_writes_the_bytes(tmp_path):
    target = save_image(png_bytes(), tmp_path / "d1.png")

    assert target.read_bytes() == png_bytes()


def test_save_image_never_overwrites(tmp_path):
    """Spec §5.2: the image is written to images/<dream_id>.png and never
    overwritten. An overwrite would silently rewrite the history strip."""
    save_image(png_bytes(), tmp_path / "d1.png")

    with pytest.raises(FileExistsError):
        save_image(b"other", tmp_path / "d1.png")


def test_save_image_creates_the_directory(tmp_path):
    target = save_image(png_bytes(), tmp_path / "deep" / "images" / "d1.png")

    assert target.is_file()


def test_save_image_rejects_bytes_that_are_not_a_png(tmp_path):
    """A JSON error body base64-encoded into a data URL would otherwise land on
    disk as `d1.png` and render as a broken image on the wall."""
    with pytest.raises(ImageError):
        save_image(b"{'error': 'nope'}", tmp_path / "d1.png")


def test_save_image_leaves_no_partial_file_when_it_rejects(tmp_path):
    with pytest.raises(ImageError):
        save_image(b"not a png", tmp_path / "d1.png")

    assert not (tmp_path / "d1.png").exists()


def test_save_image_reports_a_full_disk_as_an_image_error(tmp_path, monkeypatch):
    """`kg2.cycle` catches ONE exception type from this module. A bare OSError
    would escape that contract, and the half-written file would sit exactly
    where the history strip expects a picture."""
    import io

    real_open = Path.open

    def failing_open(self, *args, **kwargs):
        handle = real_open(self, *args, **kwargs)

        class _FullDisk(io.RawIOBase):
            def write(self, _data):
                raise OSError(28, "No space left on device")

            def close(self):
                handle.close()

        return _FullDisk()

    monkeypatch.setattr(Path, "open", failing_open)

    with pytest.raises(ImageError, match="No space left on device"):
        save_image(png_bytes(), tmp_path / "d1.png")

    monkeypatch.undo()
    assert not (tmp_path / "d1.png").exists()
