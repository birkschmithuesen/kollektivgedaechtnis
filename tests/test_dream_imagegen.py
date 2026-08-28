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

from kg2.imagegen import (
    MOOD_LIGHT,
    TENSION_COHERENCE,
    ImageError,
    build_image_prompt,
    decode_image,
    image_extension,
    render_image,
    save_image,
)

REGISTER = (
    "Photographic, natural depth of field, eye-level, no text anywhere in the "
    "frame, a single photograph."
)
SENTENCE = "Concrete dreams of the forest, and the forest sends an invoice."


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


def jpeg_bytes() -> bytes:
    """A minimal valid JFIF/JPEG: SOI, APP0/JFIF, a bare EOI. Not a decodable
    image, but the byte header the contract document recorded from the live
    endpoint (`\\xff\\xd8\\xff\\xe0\\x00\\x10JF`), which is all `save_image`
    inspects."""
    return (
        b"\xff\xd8"  # SOI
        + b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"  # APP0
        + b"\xff\xd9"  # EOI
    )


def response_with(data: bytes, mime: str = "image/png") -> dict:
    url = f"data:{mime};base64," + base64.b64encode(data).decode("ascii")
    return {
        "choices": [
            {"message": {"role": "assistant", "content": "",
                         "images": [{"type": "image_url", "image_url": {"url": url}}]}}
        ]
    }


# -- the prompt: five blocks, English, in order ------------------------------


def test_the_prompt_is_five_blocks_in_order_sentence_first():
    """Doc's own template order: [Subject] + [Action]... first, register and
    format last (google/gemini-3-pro-image prompting guide). The English
    sentence is the motif and must be the subject, not the register."""
    prompt = build_image_prompt(SENTENCE, mood=4, tension=5, register=REGISTER, aspect_ratio="16:9")

    positions = [
        prompt.index(SENTENCE),
        prompt.index(MOOD_LIGHT[4]),
        prompt.index(TENSION_COHERENCE[5]),
        prompt.index(REGISTER),
        prompt.index("16:9"),
    ]
    assert positions == sorted(positions)
    assert prompt.index(SENTENCE) == 0


def test_the_aspect_ratio_is_landscape_and_stated():
    """Spec §5.2: matching the 65″ screen. Googles own example states the
    ratio in the prompt text too, even though it is also a parameter — not
    documented whether the chat/completions path forwards the parameter."""
    prompt = build_image_prompt(SENTENCE, mood=3, tension=3, register=REGISTER, aspect_ratio="16:9")

    assert "16:9" in prompt
    assert "landscape" in prompt.lower()


def test_the_register_is_appended_verbatim():
    """Spec §5.2: held in config as a style suffix, never model-chosen, never
    graph-driven. The history strip is a measurement series and exactly one
    variable may change — and that is the material."""
    prompt = build_image_prompt(SENTENCE, mood=3, tension=3, register=REGISTER, aspect_ratio="16:9")

    assert REGISTER in prompt


def test_two_calls_with_the_same_mood_and_tension_produce_the_same_boilerplate():
    """Reproducibility across the strip: two dreams at the same mood/tension
    must get identical wording for those blocks, or the strip would show
    formulation noise instead of material drift (docs/operations.md finding
    on prompt order, an analogous concern)."""
    a = build_image_prompt("Satz A.", mood=2, tension=4, register=REGISTER, aspect_ratio="16:9")
    b = build_image_prompt("Satz B.", mood=2, tension=4, register=REGISTER, aspect_ratio="16:9")

    assert a.replace("Satz A.", "X") == b.replace("Satz B.", "X")


def test_a_different_mood_changes_only_the_mood_block():
    warm = build_image_prompt(SENTENCE, mood=5, tension=3, register=REGISTER, aspect_ratio="16:9")
    cold = build_image_prompt(SENTENCE, mood=1, tension=3, register=REGISTER, aspect_ratio="16:9")

    assert warm != cold
    assert MOOD_LIGHT[5] in warm
    assert MOOD_LIGHT[1] in cold
    assert MOOD_LIGHT[5] not in cold


def test_a_different_tension_changes_only_the_tension_block():
    calm = build_image_prompt(SENTENCE, mood=3, tension=1, register=REGISTER, aspect_ratio="16:9")
    torn = build_image_prompt(SENTENCE, mood=3, tension=5, register=REGISTER, aspect_ratio="16:9")

    assert calm != torn
    assert TENSION_COHERENCE[1] in calm
    assert TENSION_COHERENCE[5] in torn


def test_there_are_exactly_five_mood_and_five_tension_stages():
    assert set(MOOD_LIGHT) == {1, 2, 3, 4, 5}
    assert set(TENSION_COHERENCE) == {1, 2, 3, 4, 5}


def test_mood_formulations_describe_only_light_and_colour():
    """Birk's explicit constraint: a formulation like "used objects, traces of
    life" is already interpretation and would hallucinate things into the
    image that are not in the material. Light is the one thing every image
    has regardless of its content — checked here by requiring the word and
    forbidding concrete nouns that would smuggle in a scene."""
    forbidden = ("object", "person", "people", "furniture", "figure", "room", "trace")
    for stage, text in MOOD_LIGHT.items():
        lowered = text.lower()
        assert "light" in lowered or "colour" in lowered or "color" in lowered
        for word in forbidden:
            assert word not in lowered, f"mood stage {stage} names a concrete thing: {word!r}"


def test_tension_formulations_name_nothing_concrete():
    forbidden = ("object", "person", "people", "furniture", "figure", "room")
    for stage, text in TENSION_COHERENCE.items():
        lowered = text.lower()
        for word in forbidden:
            assert word not in lowered, f"tension stage {stage} names a concrete thing: {word!r}"


def test_mood_and_tension_formulations_are_english():
    for text in list(MOOD_LIGHT.values()) + list(TENSION_COHERENCE.values()):
        assert "der " not in text.lower() and "und " not in text.lower()


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


def test_decode_image_takes_the_first_of_several_images():
    """The live endpoint returns TWO entries, pixel-identical, differing only
    in embedded metadata (contract document, verified 2026-08-26). Taking the
    first is the documented behaviour, not an accident of indexing."""
    first, second = png_bytes(), png_bytes() + b"\x00"
    payload = response_with(first)
    payload["choices"][0]["message"]["images"].append(
        {"type": "image_url",
         "image_url": {"url": "data:image/png;base64,"
                              + base64.b64encode(second).decode("ascii")}}
    )

    assert decode_image(payload) == first


def test_decode_image_error_does_not_say_none_when_content_is_null():
    """The live endpoint sends `content: None` on the SUCCESS path, so a dict
    default never fires (it only fires on a missing key). Without the `or ""`
    the operator's error message reads "it said: 'None'" instead of naming the
    real problem."""
    payload = {"choices": [{"message": {"role": "assistant", "content": None}}]}

    with pytest.raises(ImageError) as excinfo:
        decode_image(payload)
    assert "None" not in str(excinfo.value)


def test_decode_image_accepts_a_declared_jpeg_mime():
    """The live endpoint declares `data:image/jpeg;base64,` on roughly 2 of 5
    calls (contract document, Abweichung 3, 2026-08-26) — the prefix check
    must not reject on the declared type, only on the `data:`/`base64,` shape."""
    assert decode_image(response_with(jpeg_bytes(), mime="image/jpeg")) == jpeg_bytes()


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


# -- format detection --------------------------------------------------------


def test_image_extension_recognises_png():
    assert image_extension(png_bytes()) == ".png"


def test_image_extension_recognises_jpeg():
    """Contract document, Abweichung 3 (2026-08-26): the live endpoint returns
    JPEG on roughly 2 of 5 calls, byte-identical in spirit to the JFIF header
    actually observed (`\\xff\\xd8\\xff\\xe0\\x00\\x10JF`)."""
    assert image_extension(jpeg_bytes()) == ".jpg"


def test_image_extension_rejects_bytes_that_are_neither():
    """The protection this function exists for: reject content that is not a
    real image at all (e.g. a base64-decoded error body), not JPEG."""
    with pytest.raises(ImageError):
        image_extension(b"{'error': 'nope'}")


# -- saving -----------------------------------------------------------------


def test_save_image_writes_the_bytes(tmp_path):
    target = save_image(png_bytes(), tmp_path / "d1.png")

    assert target.read_bytes() == png_bytes()


def test_save_image_keeps_the_png_extension_for_png_bytes(tmp_path):
    target = save_image(png_bytes(), tmp_path / "d1")

    assert target == tmp_path / "d1.png"


def test_save_image_accepts_jpeg_and_gives_it_the_jpg_extension(tmp_path):
    """Both formats are equally valid for display (contract document,
    Abweichung 3) — a JPEG is not rejected for arriving as JPEG."""
    target = save_image(jpeg_bytes(), tmp_path / "d1")

    assert target == tmp_path / "d1.jpg"
    assert target.read_bytes() == jpeg_bytes()


def test_save_image_corrects_a_wrong_declared_extension(tmp_path):
    """The extension must come from the real bytes, never from what the
    caller assumed: JPEG data handed in at a path that still says `.png` is
    renamed, not trusted (no second, disagreeing truth about the format)."""
    target = save_image(jpeg_bytes(), tmp_path / "d1.png")

    assert target == tmp_path / "d1.jpg"
    assert not (tmp_path / "d1.png").exists()
    assert target.read_bytes() == jpeg_bytes()


def test_save_image_never_overwrites(tmp_path):
    """Spec §5.2: the image is written to images/<dream_id>.<ext> and never
    overwritten. An overwrite would silently rewrite the history strip."""
    save_image(png_bytes(), tmp_path / "d1.png")

    with pytest.raises(FileExistsError):
        save_image(png_bytes(), tmp_path / "d1.png")

    assert (tmp_path / "d1.png").read_bytes() == png_bytes()


def test_save_image_never_overwrites_across_a_format_change(tmp_path):
    """PNG now, JPEG later (or vice versa) for the same id is still one
    dream's image, not two: a format change between attempts must not let a
    second render sneak in under a different filename."""
    save_image(png_bytes(), tmp_path / "d1")

    with pytest.raises(FileExistsError):
        save_image(jpeg_bytes(), tmp_path / "d1")

    assert (tmp_path / "d1.png").read_bytes() == png_bytes()
    assert not (tmp_path / "d1.jpg").exists()


def test_save_image_creates_the_directory(tmp_path):
    target = save_image(png_bytes(), tmp_path / "deep" / "images" / "d1.png")

    assert target.is_file()


def test_save_image_rejects_bytes_that_are_neither_png_nor_jpeg(tmp_path):
    """A JSON error body base64-encoded into a data URL would otherwise land on
    disk as `d1.png` and render as a broken image on the wall."""
    with pytest.raises(ImageError):
        save_image(b"{'error': 'nope'}", tmp_path / "d1.png")


def test_save_image_leaves_no_partial_file_when_it_rejects(tmp_path):
    with pytest.raises(ImageError):
        save_image(b"not a png", tmp_path / "d1.png")

    assert not (tmp_path / "d1.png").exists()


def test_save_image_leaves_the_directory_empty_when_it_rejects(tmp_path):
    """Format is decided before any file is opened, so invalid bytes must not
    even leave an extension-less stand-in behind — not just the named target."""
    with pytest.raises(ImageError):
        save_image(b"not a png", tmp_path / "d1")

    assert list(tmp_path.iterdir()) == []


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
