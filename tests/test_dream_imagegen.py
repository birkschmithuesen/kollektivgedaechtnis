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
    TENSION_SOURCE_TEMPLATE,
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
#: What stage 1 delivers as `image_description` since 2026-08-29: the same
#: scene as the wall sentence, at length — materials, surfaces, arrangement.
DESCRIPTION = (
    "A slab of raw grey concrete stands upright in a clearing, its formwork "
    "seams still visible and its edges chipped. Thin birch trunks press "
    "against it on three sides, their bark peeling in papery strips. At the "
    "base of the slab a printed invoice lies face up on wet moss, its paper "
    "swollen and curling at the corners."
)
#: A `tension_source`: the two concrete things that contradict each other.
TENSION_SOURCE = "restoring an existing façade while billing it as new construction"


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


# -- the prompt: the blocks, English, in order -------------------------------


def test_the_prompt_is_the_documented_blocks_in_order_motif_first():
    """Doc's own template order: [Subject] + [Action]... first, register and
    format last (google/gemini-3-pro-image prompting guide). The motif is the
    subject and must come first, not the register."""
    prompt = build_image_prompt(
        DESCRIPTION, mood=4, tension=5, register=REGISTER, aspect_ratio="16:9"
    )

    positions = [
        prompt.index(DESCRIPTION),
        prompt.index(MOOD_LIGHT[4]),
        prompt.index(TENSION_COHERENCE[5]),
        prompt.index(REGISTER),
        prompt.index("16:9"),
    ]
    assert positions == sorted(positions)
    assert prompt.index(DESCRIPTION) == 0


def test_the_motif_is_the_long_description_not_the_wall_sentence():
    """Befund B (Birk, 2026-08-29, on five rendered images): the 16-word wall
    sentence gave the image model almost nothing — Google's guidance for this
    model asks for a scene described narratively. The literal translation is
    still recorded (spec §5.3) but is no longer what the image is built on."""
    prompt = build_image_prompt(
        DESCRIPTION,
        sentence_en=SENTENCE,
        sentence="Beton träumt vom Wald.",
        mood=3, tension=3, register=REGISTER, aspect_ratio="16:9",
    )

    assert prompt.startswith(DESCRIPTION)
    # The short forms are not smuggled in alongside it: one motif, not three.
    assert SENTENCE not in prompt
    assert "Beton träumt vom Wald." not in prompt


def test_the_motif_falls_back_to_the_english_sentence():
    """A field stage 1 failed to fill must never cost a dream (spec §8). The
    literal translation is a worse motif than the description and a far
    better one than nothing."""
    prompt = build_image_prompt(
        "", sentence_en=SENTENCE, sentence="Beton träumt vom Wald.",
        mood=3, tension=3, register=REGISTER, aspect_ratio="16:9",
    )

    assert prompt.startswith(SENTENCE)


def test_the_motif_falls_back_to_the_german_sentence_as_a_last_resort():
    """The last rung: a German motif renders worse than an English one — it
    renders, which is what matters at 14:00 on an exhibition day."""
    prompt = build_image_prompt(
        "", sentence_en="", sentence="Beton träumt vom Wald.",
        mood=3, tension=3, register=REGISTER, aspect_ratio="16:9",
    )

    assert prompt.startswith("Beton träumt vom Wald.")


def test_the_motif_fallback_treats_whitespace_and_none_as_missing():
    """`None` is what a NULL column out of dreams.sqlite3 looks like (rows
    from before 2026-08-29), and "   " is what a model leaves behind. Both
    mean the same thing here and must not become the motif."""
    prompt = build_image_prompt(
        "   ", sentence_en=None, sentence="Beton träumt vom Wald.",
        mood=3, tension=3, register=REGISTER, aspect_ratio="16:9",
    )

    assert prompt.startswith("Beton träumt vom Wald.")


def test_the_tension_block_names_the_concrete_contradiction():
    """Befund A (Birk, 2026-08-29): TENSION_COHERENCE sets the DEGREE of
    coherence and names nothing, so a model told only „two different
    qualities sit side by side" invents which two — it painted a clean and a
    dirty robot arm where the real friction was renovating vs. billing as new
    build. The material's own contradiction now travels with the scale."""
    prompt = build_image_prompt(
        DESCRIPTION, tension_source=TENSION_SOURCE,
        mood=3, tension=3, register=REGISTER, aspect_ratio="16:9",
    )

    # The fixed scale is untouched...
    assert TENSION_COHERENCE[3] in prompt
    # ...and the concrete contradiction stands with it, in the same block.
    assert TENSION_SOURCE in prompt
    block = next(b for b in prompt.split("\n\n") if TENSION_COHERENCE[3] in b)
    assert TENSION_SOURCE in block
    assert block.index(TENSION_COHERENCE[3]) < block.index(TENSION_SOURCE)


def test_the_concrete_contradiction_is_a_separate_sentence_after_the_scale():
    """Appended, never substituted into the fixed wording: the scale keeps
    deciding HOW hard the two things collide, and stage 1 only says WHAT they
    are. A model-written phrase must not gain control of the coherence
    degree — that is the one variable the history strip holds constant."""
    prompt = build_image_prompt(
        DESCRIPTION, tension_source=TENSION_SOURCE,
        mood=3, tension=4, register=REGISTER, aspect_ratio="16:9",
    )

    expected = (
        f"{TENSION_COHERENCE[4]} "
        f"{TENSION_SOURCE_TEMPLATE.format(source=TENSION_SOURCE)}."
    )
    assert expected in prompt


def test_an_empty_tension_source_leaves_the_block_exactly_as_it_was():
    """Material without a real contradiction must not have one invented for
    it (kg2/condense.py's evidence clause) — and then nothing at all is added
    here, byte for byte the pre-2026-08-29 behaviour."""
    with_source = build_image_prompt(
        DESCRIPTION, tension_source="", mood=2, tension=4,
        register=REGISTER, aspect_ratio="16:9",
    )
    without_argument = build_image_prompt(
        DESCRIPTION, mood=2, tension=4, register=REGISTER, aspect_ratio="16:9"
    )

    assert with_source == without_argument
    block = next(b for b in with_source.split("\n\n") if TENSION_COHERENCE[4] in b)
    assert block == TENSION_COHERENCE[4]


def test_a_whitespace_only_tension_source_counts_as_none():
    """Same reason as the motif's fallback: "   " and None are what an empty
    field really looks like coming out of a model or a NULL column."""
    for empty in ("   ", None):
        prompt = build_image_prompt(
            DESCRIPTION, tension_source=empty, mood=2, tension=4,
            register=REGISTER, aspect_ratio="16:9",
        )
        block = next(b for b in prompt.split("\n\n") if TENSION_COHERENCE[4] in b)
        assert block == TENSION_COHERENCE[4]


def test_the_aspect_ratio_is_landscape_and_stated():
    """Spec §5.2: matching the 65″ screen. Googles own example states the
    ratio in the prompt text too, even though it is also a parameter — not
    documented whether the chat/completions path forwards the parameter."""
    prompt = build_image_prompt(
        DESCRIPTION, mood=3, tension=3, register=REGISTER, aspect_ratio="16:9"
    )

    assert "16:9" in prompt
    assert "landscape" in prompt.lower()


def test_the_register_is_appended_verbatim():
    """Spec §5.2: held in config as a style suffix, never model-chosen, never
    graph-driven. The history strip is a measurement series and exactly one
    variable may change — and that is the material."""
    prompt = build_image_prompt(
        DESCRIPTION, mood=3, tension=3, register=REGISTER, aspect_ratio="16:9"
    )

    assert REGISTER in prompt


def test_two_calls_with_the_same_mood_and_tension_produce_the_same_boilerplate():
    """Reproducibility across the strip: two dreams at the same mood/tension
    must get identical wording for those blocks, or the strip would show
    formulation noise instead of material drift (docs/operations.md finding
    on prompt order, an analogous concern)."""
    a = build_image_prompt("Szene A.", mood=2, tension=4, register=REGISTER, aspect_ratio="16:9")
    b = build_image_prompt("Szene B.", mood=2, tension=4, register=REGISTER, aspect_ratio="16:9")

    assert a.replace("Szene A.", "X") == b.replace("Szene B.", "X")


def test_a_different_mood_changes_only_the_mood_block():
    warm = build_image_prompt(
        DESCRIPTION, mood=5, tension=3, register=REGISTER, aspect_ratio="16:9"
    )
    cold = build_image_prompt(
        DESCRIPTION, mood=1, tension=3, register=REGISTER, aspect_ratio="16:9"
    )

    assert warm != cold
    assert MOOD_LIGHT[5] in warm
    assert MOOD_LIGHT[1] in cold
    assert MOOD_LIGHT[5] not in cold


def test_a_different_tension_changes_only_the_tension_block():
    calm = build_image_prompt(
        DESCRIPTION, mood=3, tension=1, register=REGISTER, aspect_ratio="16:9"
    )
    torn = build_image_prompt(
        DESCRIPTION, mood=3, tension=5, register=REGISTER, aspect_ratio="16:9"
    )

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


#: Words that turn a prompt line into an instruction to LEAVE SOMETHING OUT —
#: the pattern Google's „Semantic Negative Prompts" guidance advises against
#: for this model, and the one commit a0a545d removed from all 25
#: combinations („Not a painting, not an illustration, …", „no warmth
#: anywhere").
#:
#: Two deliberate absences from this list, both matching how a0a545d itself
#: counted:
#:
#: * „neither" — TENSION_COHERENCE[4] ends „…both fully real, neither one
#:   dominant". That balances two things that ARE in the frame; it removes
#:   nothing, which is why that commit counted the stage as clean.
#: * „free of" — the register's „Every surface in the frame is free of
#:   writing" is named in that same commit as the ONE formulation that was
#:   already right (a state the surface is in, not a thing to omit).
#:
#: Matched as whole words, so „nowhere" and „nothing" — which name a quality
#: rather than rule one out — do not trip it.
_NEGATIONS = (
    "no", "not", "never", "without", "avoid", "exclude", "omit",
    "don't", "doesn't", "isn't", "won't", "aren't",
)


def _negations_in(text: str) -> list[str]:
    lowered = f" {text.lower()} "
    return [
        word for word in _NEGATIONS
        if any(f" {word}{tail}" in lowered for tail in (" ", ",", ".", ";"))
    ]


def test_the_negation_check_would_catch_the_wording_that_was_removed():
    """The guard's own guard. Two real strings from before commit a0a545d —
    if `_negations_in` stops flagging these, the tests below are vacuous and
    would pass on a prompt that had regressed all the way back."""
    assert _negations_in("no warmth anywhere in the frame")
    assert _negations_in("Not a painting, not an illustration.")
    # ...and it does not fire on the wordings that were kept.
    assert _negations_in("coming from nowhere in particular") == []
    assert _negations_in("both fully real, neither one dominant") == []


def test_every_fixed_prompt_block_stays_free_of_negations():
    """Google's „Semantic Negative Prompts" guidance for this exact model
    (ai.google.dev/gemini-api/docs/interactions/image-generation): describe
    the scene you want instead of negating the one you don't. Decided
    2026-08-29 (commit a0a545d) after eight negations were found in the
    prompt; that commit checked all 25 mood/tension combinations by hand and
    recorded the result in its message only. This is that check, automated,
    so the next edit cannot lose it silently.

    `TENSION_SOURCE_TEMPLATE` (added 2026-08-29) is in scope for the same
    reason as the two scales: it is fixed wording this module owns."""
    for name, text in (
        [(f"MOOD_LIGHT[{k}]", v) for k, v in MOOD_LIGHT.items()]
        + [(f"TENSION_COHERENCE[{k}]", v) for k, v in TENSION_COHERENCE.items()]
        + [("TENSION_SOURCE_TEMPLATE", TENSION_SOURCE_TEMPLATE)]
    ):
        found = _negations_in(text)
        assert not found, f"{name} negates instead of describing: {found} in {text!r}"


def test_all_25_mood_tension_combinations_stay_free_of_negations():
    """The combinations, not just the parts: a0a545d's own claim was about
    all 25, and a future edit could introduce a negation only in a pairing —
    or in the joint the tension source is attached at."""
    for mood in range(1, 6):
        for tension in range(1, 6):
            prompt = build_image_prompt(
                "Ein Motiv.", mood=mood, tension=tension,
                tension_source=TENSION_SOURCE,
                register="Ein Register.", aspect_ratio="16:9",
            )
            # The motif, the register and the format line come from the
            # caller and from config2.toml — this checks what THIS module
            # fixes, which is blocks two and three.
            fixed = "\n\n".join(prompt.split("\n\n")[1:3])
            found = _negations_in(fixed)
            assert not found, f"mood={mood} tension={tension} negates: {found}"


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


# -- der zweite Renderpfad: Black Forest Labs (EU) ---------------------------
#
# Anderer Ablauf als bei OpenRouter: absenden, pollen, dann eine signierte URL
# herunterladen. Wieder ist jeder Netzaufruf injiziert.


class FakeBfl:
    """Absenden, N-mal „Pending", dann „Ready" mit einer signierten URL."""

    def __init__(self, pending=1, data=None, status="Ready", sample="https://signed.invalid/x"):
        self.pending = pending
        self.data = png_bytes() if data is None else data
        self.status = status
        self.sample = sample
        self.posts = []
        self.polls = []
        self.downloads = []
        self.slept = []

    def post(self, url, headers, json, timeout):
        self.posts.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return {"id": "job-1", "polling_url": "https://api.eu.bfl.ai/v1/get_result?id=job-1"}

    def get_json(self, url, headers, timeout):
        self.polls.append({"url": url, "headers": headers})
        if len(self.polls) <= self.pending:
            return {"status": "Pending"}
        return {"status": self.status, "result": {"sample": self.sample}}

    def get_bytes(self, url, timeout):
        self.downloads.append(url)
        return self.data

    def sleep(self, seconds):
        self.slept.append(seconds)

    def render(self, **overrides):
        kwargs = dict(
            model="flux-pro-1.1",
            api_key="bfl-key",
            url="https://api.eu.bfl.ai/v1",
            timeout=180.0,
            api_mode="bfl",
            width=1344,
            height=768,
            post=self.post,
            get_json=self.get_json,
            get_bytes=self.get_bytes,
            sleep=self.sleep,
        )
        kwargs.update(overrides)
        return render_image("ein prompt", **kwargs)


def test_the_default_route_is_still_openrouter():
    """Fallback-Regel: ohne `api_mode` bleibt es beim gebauten und gemessenen
    Weg. Nichts an dieser Datei oben ändert sich."""
    seen = {}

    def fake_post(url, headers, json, timeout):
        seen.update(json=json, headers=headers)
        return response_with(png_bytes())

    render_image("p", model="m", api_key="k", url="u", timeout=1.0, post=fake_post)

    assert seen["json"]["modalities"] == ["image", "text"]
    assert seen["headers"]["Authorization"] == "Bearer k"


def test_bfl_submits_polls_and_downloads_the_signed_url():
    bfl = FakeBfl(pending=2)

    data = bfl.render()

    assert data == png_bytes()
    # Absenden: POST auf <url>/<endpoint>, mit dem Modell als Endpunkt.
    assert bfl.posts[0]["url"] == "https://api.eu.bfl.ai/v1/flux-pro-1.1"
    assert bfl.posts[0]["json"] == {"prompt": "ein prompt", "width": 1344, "height": 768}
    # Gepollt wird die URL aus der Antwort, nicht eine selbst gebaute.
    assert {p["url"] for p in bfl.polls} == {"https://api.eu.bfl.ai/v1/get_result?id=job-1"}
    assert len(bfl.polls) == 3  # zweimal Pending, einmal Ready
    assert bfl.downloads == ["https://signed.invalid/x"]


def test_bfl_authenticates_with_x_key_and_never_with_a_bearer_token():
    """Gemessen: BFL will `x-key`. Ein Authorization-Header wird ignoriert und
    der Request scheitert mit 401 — ein Fehler, der wie ein falscher Schlüssel
    aussieht und keiner ist."""
    bfl = FakeBfl()

    bfl.render()

    assert bfl.posts[0]["headers"]["x-key"] == "bfl-key"
    assert "Authorization" not in bfl.posts[0]["headers"]
    assert bfl.polls[0]["headers"]["x-key"] == "bfl-key"


def test_bfl_never_sends_the_openrouter_peculiarities():
    """`modalities` und die Sonderbehandlung für reine Bildmodelle gehören zu
    OpenRouters Katalog, nicht zu BFL."""
    bfl = FakeBfl()

    bfl.render(model="flux-pro-1.1")

    assert "modalities" not in bfl.posts[0]["json"]
    assert "messages" not in bfl.posts[0]["json"]
    assert "model" not in bfl.posts[0]["json"]  # das Modell IST der Endpunkt


def test_bfl_gives_up_when_the_job_never_becomes_ready():
    """Der Traum wird ausgesessen (spec §8), nicht endlos gepollt: das Zeitbudget
    ist dasselbe wie für den OpenRouter-Aufruf."""
    bfl = FakeBfl(pending=10_000)

    with pytest.raises(ImageError, match="ready"):
        bfl.render(timeout=0.0)


def test_bfl_reports_a_failed_job_as_an_image_error():
    bfl = FakeBfl(pending=0, status="Content Moderated")

    with pytest.raises(ImageError, match="Content Moderated"):
        bfl.render()


def test_bfl_reports_a_ready_job_without_a_sample_url():
    bfl = FakeBfl(pending=0, sample="")

    with pytest.raises(ImageError):
        bfl.render()


def test_bfl_does_not_retry_the_submit():
    """Spec §8 gilt hier genauso. Pollen ist kein Retry: es ist EIN Auftrag,
    nach dessen Ergebnis gefragt wird, und er wird nie zweimal erteilt."""
    calls = []

    def dead_post(url, headers, json, timeout):
        calls.append(1)
        raise OSError("connection reset")

    bfl = FakeBfl()
    with pytest.raises(ImageError):
        bfl.render(post=dead_post)

    assert len(calls) == 1
    assert bfl.polls == []


def test_bfl_without_a_key_fails_loudly_and_names_the_variable():
    """BFL_API_KEY existiert noch nicht. Fehlt er, muss das dastehen — nicht
    ein undurchsichtiger 401 um 14:00 (wie beim OpenRouter-Pfad)."""
    bfl = FakeBfl()

    with pytest.raises(ImageError, match="BFL_API_KEY"):
        bfl.render(api_key=None)

    assert bfl.posts == []


def test_bfl_download_failure_is_an_image_error_like_any_other():
    """Die signierte URL gilt nur 10 Minuten. Läuft sie ab oder bricht der
    Download, ist das ein gescheiterter Traum, kein Traceback."""

    def dead_get(url, timeout):
        raise OSError("410 gone")

    bfl = FakeBfl()
    with pytest.raises(ImageError):
        bfl.render(get_bytes=dead_get)


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


# --- api_mode="bfl_proxy": der Weg über den Loopback-Egress-Broker ---------
#
# Der Proxy existiert, weil uid `birk` per nftables keinen Egress zu bfl.ai
# hat und BFL Wildcard-Freigaben verlangt, die nftables nicht kann (Messungen:
# ~/.hermes/profiles/birk/docs/bfl-wildcard-egress-loesungsweg.md). Diese
# Tests sichern die drei Eigenschaften, auf die es dabei ankommt: kein Key im
# Stationsprozess, keine Fehlerseite auf der Wand, und der Default bleibt.

def test_bfl_proxy_schickt_prompt_und_bekommt_bytes():
    gesehen = {}

    def fake_post_bytes(url, json, timeout):
        gesehen["url"] = url
        gesehen["json"] = json
        return png_bytes()

    data = render_image(
        "ein Betonwuerfel",
        model="flux-2-pro-preview",
        api_key=None,
        url="http://127.0.0.1:8791/render",
        timeout=180.0,
        api_mode="bfl_proxy",
        width=1344,
        height=768,
        post_bytes=fake_post_bytes,
    )

    assert data == png_bytes()
    assert gesehen["url"] == "http://127.0.0.1:8791/render"
    assert gesehen["json"]["prompt"] == "ein Betonwuerfel"
    assert gesehen["json"]["model"] == "flux-2-pro-preview"
    assert gesehen["json"]["width"] == 1344
    assert gesehen["json"]["height"] == 768


def test_bfl_proxy_schickt_niemals_einen_api_key():
    """Der Kern des Proxy-Gewinns: das Geheimnis bleibt im Proxy.

    Selbst wenn ein Key konfiguriert ist, darf er den Stationsprozess nicht
    verlassen — sonst wäre der Umweg sinnlos.
    """
    gesehen = {}

    def fake_post_bytes(url, json, timeout):
        gesehen["json"] = json
        return png_bytes()

    render_image(
        "p",
        model="flux-2-pro-preview",
        api_key="streng-geheim",
        url="http://127.0.0.1:8791/render",
        timeout=10.0,
        api_mode="bfl_proxy",
        post_bytes=fake_post_bytes,
    )

    assert "streng-geheim" not in str(gesehen["json"])
    assert not any("key" in k.lower() for k in gesehen["json"])


def test_bfl_proxy_lehnt_nicht_bild_antwort_ab():
    """Eine durchgereichte HTML-Fehlerseite darf nicht auf der Wand landen."""
    def fake_post_bytes(url, json, timeout):
        return b"<html>Fehler</html>"

    with pytest.raises(ImageError):
        render_image(
            "p",
            model="flux-2-pro-preview",
            api_key=None,
            url="http://127.0.0.1:8791/render",
            timeout=10.0,
            api_mode="bfl_proxy",
            post_bytes=fake_post_bytes,
        )


def test_bfl_proxy_meldet_unerreichbaren_proxy_verstaendlich():
    def fake_post_bytes(url, json, timeout):
        raise ConnectionRefusedError("connection refused")

    with pytest.raises(ImageError, match="nicht erreichbar"):
        render_image(
            "p",
            model="flux-2-pro-preview",
            api_key=None,
            url="http://127.0.0.1:8791/render",
            timeout=10.0,
            api_mode="bfl_proxy",
            post_bytes=fake_post_bytes,
        )


def test_default_bleibt_openrouter_trotz_neuem_modus():
    """Fallback-Regel: eine unveränderte Config verhält sich wie vorher."""
    from kg2.config import DreamConfig

    assert DreamConfig.__dataclass_fields__["image_api_mode"].default == "openrouter"
