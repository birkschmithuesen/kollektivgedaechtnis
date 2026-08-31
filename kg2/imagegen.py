"""Stage 2: the sentence becomes an image (spec §5.2).

Built against `docs/dream-image-contract.md`, which was **verified against the
live endpoint on 2026-08-26** (three real calls, all HTTP 200). The request
shape held; three response details differed from the assumption and are
recorded there:

* `images` carries **two** entries, not one. They were compared and are
  pixel-identical (max channel difference 0.0) — they differ only in ~1.2 kB of
  embedded IPTC/XMP metadata (a per-copy GUID). Taking `images[0]` is therefore
  correct and loses nothing.
* `message.content` is `None`, not prose. That only touches the error path
  below, which is why `decode_image` no longer relies on a dict default.
* The image **format varies per call** — PNG or JPEG, chosen by the model, not
  by the prompt (measured 2 of 5 as JPEG, 2026-08-26, contract document
  „Abweichung 3"). Both are complete, undamaged images. `image_extension`
  below is the one place that decides which extension a given set of bytes
  gets — from the byte header, never from the declared MIME string, which is
  not trustworthy.

Two rules that look like details and are not:

* **The register (machart) is fixed and appended to every prompt.** Never
  model-chosen, never graph-driven (spec §5.2, brainstorm §10). The history
  strip is a measurement series; exactly one variable may change, and that is
  the material.
* **The image is never overwritten** (spec §5.2). An overwrite would silently
  rewrite history, and the strip is the evidence that there was never one vision
  of the future.

There is deliberately NO retry (spec §8). A failed render abandons the dream,
the current image stays up, and the next trigger tries again — that is „ride it
out", and it is also what keeps a conference-wifi outage from tripling the bill.

## The image prompt (revised 2026-08-28, extended 2026-08-29): English prose

The whole prompt is now English (the wall stays German) and connected prose,
not a keyword list — Google's own guidance for this exact model is explicit:
„A simple list of keywords won't cut it; you need to describe the scene
narratively." (`ai.google.dev/gemini-api/docs/interactions/image-generation`,
and the „ultimate prompting guide for nano banana"). `build_image_prompt`
below assembles the blocks in the documented order, `[Subject] + [Action] +
[Location] + [Composition] + [Style]`:

1. **The motif** — stage 1's `image_description`: 3-4 sentences of English
   prose about the scene, naming materials, surfaces, light on the objects,
   spatial arrangement and scale. Variable, changes every dream. Falls back to
   `sentence_en`, then to `sentence`, if the field is empty (see
   `build_image_prompt` for why a missing field may never cost a dream).
2. **Mood** — from `MOOD_LIGHT`, one of five FIXED formulations chosen by
   stage 1's `mood` (1-5). Fixed wording, not model-phrased, so two dreams at
   the same mood produce identical wording here — otherwise the strip would
   show formulation noise instead of material drift.
3. **Tension** — from `TENSION_COHERENCE`, same discipline, keyed by
   stage 1's `tension` (1-5), and — when stage 1 named one — followed by the
   concrete contradiction from `tension_source` in one further sentence.
4. **Register** — `DreamConfig.visual_register`, fixed all day (unchanged
   rule from above).
5. **Format** — aspect ratio and orientation, fixed.

Blocks 2, 4 and 5 are invariant per value; block 1 always varies; block 3
varies only in its optional second sentence. Everything the image model is
told therefore comes from exactly two places: the fixed scales here, and the
material via stage 1.

**Why the motif is no longer the 16-word wall sentence (Birk, 2026-08-29,
measured on five rendered images in `out/tagesverlauf/`).** Stage 1's
`sentence_en` is a LITERAL translation — its prompt forbids embellishment,
because it is the honest counterpart of what visitors read on the wall. That
made it a poor motif: 16 words, one clause, nothing about materials or
arrangement, in direct contradiction to Google's „describe the scene
narratively". `image_description` is the same scene written for the image
model instead of for the wall. The wall sentence itself is UNCHANGED and
stays 16 words — it is measured against legibility in passing, not against
image quality, and the two must not be traded against each other.

**Why the tension block now carries a concrete contradiction.** The
`TENSION_COHERENCE` wordings are deliberately contentless: they set the
DEGREE of coherence, never its subject. But a model told only „two different
qualities sit side by side" has to invent WHICH two — and it does. Handed the
sentence about robots spraying concrete onto an existing façade while billing
it as new construction, it painted two robot arms, one clean and one dirty:
a contradiction it made up, because the real one („renovating" against
„billing as new build") was never in the prompt. `tension_source` supplies
that, and only that: the fixed scale still decides how hard the two things
collide, the material now decides what they are.

**Mood formulations describe ONLY light and colour — Birk's explicit
constraint.** A formulation like „used objects, traces of life" is already
interpretation: it would hallucinate concrete things into the image that are
not in the material. Light is the one thing every image has, regardless of
what it depicts.

**`tension` is NOT „absurdity".** Contradiction in the material is the normal
case (spec §5.1's evidence clause explicitly allows but never forces one), so
if tension mapped to absurdity almost every image would be absurd. Instead
`TENSION_COHERENCE` controls HOW a contradiction shows up in the image — from
„calm, everything belongs together" through „two incompatible things side by
side, both real" to, only at the extreme (stage 5), „physically impossible".
Absurdity is the end of the scale, not the scale itself.

**Deliberately NOT included** (so nobody „cleans this up" later):
film stock / colour grading (would fight the mood channel and make its five
stages indistinguishable), quality/mood adjectives („cinematic", „dramatic",
„award-winning"), a style reference („in the style of X"), a fixed composition
rule (composition is the one thing the sentence itself still gets to decide,
and the highest tension stage depends on being allowed to break it), and
„context and intent" framing (pulls exhibition visitors into the image).
"""

from __future__ import annotations

import base64
import logging
import time
from pathlib import Path

log = logging.getLogger(__name__)

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
# The JPEG SOI marker plus the start of the next marker: every JPEG variant
# (JFIF, Exif, ...) starts this way; the marker after it differs by variant,
# so only the first three bytes are checked.
_JPEG_MAGIC = b"\xff\xd8\xff"
_MAGIC_EXTENSIONS = (
    (_PNG_MAGIC, ".png"),
    (_JPEG_MAGIC, ".jpg"),
)
_DATA_PREFIX = "data:"


class ImageError(RuntimeError):
    """Stage 2 did not produce an image. One type for `kg2.cycle` to catch."""


def image_extension(data: bytes) -> str:
    """The file extension for `data`, decided by its byte header — never by a
    declared MIME string, which can lie (contract document, „Abweichung 3").

    This is the single place that decides PNG vs JPEG; nothing downstream may
    make that call independently, or the file on disk and the name recorded
    for it could disagree.
    """
    for magic, extension in _MAGIC_EXTENSIONS:
        if data.startswith(magic):
            return extension
    raise ImageError(f"stage 2 returned {len(data)} bytes that are neither a PNG nor a JPEG")


#: Fixed wording, keyed 1 (coldest/most negative) to 5 (warmest/most
#: positive) — see the module docstring for why these describe ONLY light and
#: colour, never objects, people, or state.
#:
#: Phrased POSITIVELY throughout, per Google's „Semantic Negative Prompts"
#: guidance (ai.google.dev/gemini-api/docs/interactions/image-generation):
#: describe the intended scene rather than negating an unwanted one. Earlier
#: wordings said things like „no warmth anywhere in the frame"; a negation is
#: a weaker instruction to this model than naming the quality that IS there,
#: so „cold" is stated outright instead. Anyone editing these: name the light
#: you want, do not rule out the light you don't.
MOOD_LIGHT: dict[int, str] = {
    1: "The light is cold and flat, coming from nowhere in particular, with "
       "grey-blue colours throughout the frame.",
    2: "The light is cool and low, with muted, slightly desaturated colours "
       "and soft grey shadows.",
    3: "The light is neutral and even, with balanced, ordinary colours and a "
       "plain, matter-of-fact cast.",
    4: "The light is warm and gentle, with soft golden colours and a mild, "
       "inviting glow.",
    5: "The light is warm and low, coming from one side, with long soft "
       "shadows and colours running toward amber.",
}

#: Fixed wording, keyed 1 (everything coheres) to 5 (physically impossible) —
#: describes only the DEGREE of coherence, names nothing concrete. See the
#: module docstring for why this is not "absurdity" as a whole scale.
#: Positively phrased for the same reason as MOOD_LIGHT above.
TENSION_COHERENCE: dict[int, str] = {
    1: "Everything in the frame belongs together, forming one calm and "
       "coherent whole.",
    2: "The scene is coherent, with only a faint sense of something slightly "
       "out of place.",
    3: "Two different qualities sit side by side in the frame, each keeping "
       "its own character.",
    4: "Two clearly incompatible qualities occupy the same frame at once, "
       "both fully real, neither one dominant.",
    5: "The frame holds something physically impossible, as if two realities "
       "had been fused into a single one.",
}


#: How stage 1's `tension_source` is attached to the fixed wording above.
#: Deliberately a SEPARATE sentence, appended after the scale's own: the fixed
#: text keeps deciding HOW hard the two things collide, and this one only
#: names WHAT they are. Substituting it into the scale itself would give a
#: model-written phrase control over the coherence degree, which is exactly
#: the variable the history strip holds constant.
#:
#: The wording is neutral about the frame's degree of coherence on purpose, so
#: it reads correctly behind all five stages — behind stage 1's „everything
#: belongs together" as much as behind stage 5's „two realities fused". It
#: names the two things and leaves how far apart they sit to the scale above.
#:
#: Positively phrased, like everything else in this module: it states what the
#: frame holds rather than ruling anything out, and `tension_source` itself is
#: prompted for as an affirmative clause („restoring an existing façade while
#: billing it as new construction"), never as „not …".
TENSION_SOURCE_TEMPLATE = (
    "Concretely, the two things the frame holds together are these: {source}"
)


def build_image_prompt(
    image_description: str | None,
    *,
    mood: int,
    tension: int,
    register: str,
    aspect_ratio: str,
    sentence_en: str | None = "",
    sentence: str | None = "",
    tension_source: str | None = "",
    include_channels: bool = True,
) -> str:
    """The documented block order (module docstring): subject (the motif)
    first, mood, tension, register, format last.

    Order matters: a prompt that opens with lighting instructions gets an
    image about lighting. The motif is the subject; everything after it is
    how the subject is rendered.

    **Three fallbacks for the motif, in this order:** `image_description`,
    then `sentence_en`, then `sentence`. A field stage 1 failed to fill must
    never cost a dream — spec §8's whole stance is to ride imperfection out —
    and each step down is still a description of the same scene, only shorter
    and (at the last step) in German. A German motif renders worse than an
    English one; it renders, which is what matters at 14:00 on an exhibition
    day. Callers that have only one of the three may pass just that one.

    `tension_source` is optional in the strictest sense: when it is empty the
    tension block is exactly what it was before 2026-08-29, because material
    without a real contradiction must not have one invented for it, here no
    more than in stage 1.

    `include_channels=False` drops the mood and tension blocks entirely,
    leaving motif + register + format. That is NOT a runtime mode — the
    station always sends both — but the control condition for the question
    „do the two fixed scales change the picture at all, or are they only
    text?\" (Birk, 2026-08-30). It is a parameter rather than a separate
    prompt builder so that the compared prompts are provably identical in
    every other byte; a second builder could drift from this one.
    """
    # `or` rather than a chain of ifs: every one of the three can arrive as
    # "" (the dataclass default), as None (a NULL column read straight out of
    # dreams.sqlite3), or as whitespace the model left behind, and all three
    # mean the same thing here — nothing usable. Stripping is what turns "  "
    # into a falsy value, so it is done before the choice, not after it.
    motif = (
        (image_description or "").strip()
        or (sentence_en or "").strip()
        or (sentence or "").strip()
    )

    tension_block = TENSION_COHERENCE.get(tension, TENSION_COHERENCE[3])
    source = (tension_source or "").strip()
    if source:
        # One sentence, appended — see TENSION_SOURCE_TEMPLATE for why it is
        # not substituted into the fixed wording. The trailing period is added
        # here rather than demanded of the model: stage 1 is asked for a
        # clause, and a clause does not come with one.
        tension_block = (
            f"{tension_block} "
            f"{TENSION_SOURCE_TEMPLATE.format(source=source.rstrip('.'))}."
        )

    format_block = (
        f"Aspect ratio {aspect_ratio}, landscape orientation, a single photograph."
    )
    if not include_channels:
        return "\n\n".join([motif, register, format_block])

    return "\n\n".join(
        [
            motif,
            MOOD_LIGHT.get(mood, MOOD_LIGHT[3]),
            tension_block,
            register,
            format_block,
        ]
    )


def _httpx_post(url: str, headers: dict, json: dict, timeout: float) -> dict:
    import httpx

    response = httpx.post(url, headers=headers, json=json, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _httpx_get_json(url: str, headers: dict, timeout: float) -> dict:
    import httpx

    response = httpx.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _httpx_get_bytes(url: str, timeout: float) -> bytes:
    import httpx

    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response.content


def _httpx_post_bytes(url: str, json: dict, timeout: float) -> bytes:
    """POST mit JSON hinein, rohe Bytes heraus — der Vertrag des BFL-Proxys.

    Eigene Funktion neben `_httpx_post`, weil der Proxy KEIN JSON zurückgibt,
    sondern das fertige Bild. Ein gemeinsamer Helfer müsste raten, was er
    gerade vor sich hat; getrennte Funktionen machen den Unterschied im
    Aufrufer sichtbar.

    Fehlerfall: der Proxy antwortet mit JSON (`{"error": ...}`) und einem
    Status ≥ 400. Der Text wird mitgenommen, damit im Log steht, WAS schiefging
    (fehlende Credits, Rate-Limit, abgelehnter Host) statt nur der Statuscode.
    """
    import httpx

    response = httpx.post(url, json=json, timeout=timeout)
    if response.status_code >= 400:
        detail = ""
        try:
            detail = str(response.json().get("error", ""))[:200]
        except Exception:
            detail = response.text[:200]
        raise ImageError(f"bfl-proxy HTTP {response.status_code}: {detail}")
    return response.content


def decode_image(payload: dict) -> bytes:
    """Pull the image bytes out of the response recorded in the contract
    document. Format-agnostic on purpose: the prefix check below only looks
    for `data:` + `base64,`, never for a specific declared MIME type, so a
    `data:image/jpeg;base64,` URL is read exactly like a PNG one (contract
    document, „Abweichung 3" — the model returns either, per call).

    Every failure below is a real one seen from image endpoints: an answer in
    prose about the picture, an empty list, or a link instead of inline data.

    `images` legitimately carries more than one entry (observed: two,
    pixel-identical, differing only in embedded metadata — contract document,
    „Abweichung 1"). The first is taken deliberately, not by oversight.
    """
    try:
        message = payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ImageError(f"no choices in the image response: {exc}") from exc

    images = message.get("images") or []
    if not images:
        # The commonest real failure: the model answers ABOUT the image.
        # `or ""` rather than a `.get` default: on the success path the live
        # endpoint sends `content: None`, and a default only fires on a MISSING
        # key, so a plain default would put the string 'None' in the message.
        preview = str(message.get("content") or "")[:120]
        raise ImageError(f"the model returned no image; it said: {preview!r}")

    url = images[0].get("image_url", {}).get("url", "")
    if not url.startswith(_DATA_PREFIX) or "base64," not in url:
        raise ImageError(f"image url is not inline data: {url[:60]!r}")

    try:
        return base64.b64decode(url.split("base64,", 1)[1])
    except Exception as exc:
        raise ImageError(f"image data is not valid base64: {exc}") from exc


#: Models that declare `output_modalities: ["image"]` WITHOUT text. Asking such
#: a model for text alongside the image is not a harmless extra — OpenRouter
#: answers HTTP 404 „No endpoints found that support the requested output
#: modalities" and the model is unreachable. Matched by substring rather than
#: by exact id because provider ids carry version suffixes (`flux.2-max`,
#: `flux.2-pro`, …) that would each need a new entry here. Checked against the
#: `/endpoints` metadata, which is the authority; see `render_image`.
_IMAGE_ONLY_MARKERS = ("flux",)


def _image_only(model: str) -> bool:
    return any(marker in model.lower() for marker in _IMAGE_ONLY_MARKERS)


def render_image(
    prompt: str,
    *,
    model: str,
    api_key: str | None,
    url: str,
    timeout: float,
    post=_httpx_post,
    aspect_ratio: str | None = None,
    api_mode: str = "openrouter",
    width: int = 1344,
    height: int = 768,
    get_json=_httpx_get_json,
    get_bytes=_httpx_get_bytes,
    post_bytes=_httpx_post_bytes,
    sleep=time.sleep,
) -> bytes:
    """Ein Bild, ein Weg — welcher, entscheidet `api_mode`.

    `"openrouter"` ist der Default und der unten dokumentierte, gemessene
    Ablauf. `"bfl"` schickt denselben Prompt an Black Forest Labs' EU-Endpunkt
    (`_render_bfl`), der anders funktioniert: absenden, pollen, herunterladen.
    `"bfl_proxy"` spricht denselben Anbieter an, aber über den lokalen
    Loopback-Proxy — siehe `_render_bfl_proxy`. Alle Wege bleiben
    funktionsfähig; umgeschaltet wird ausschließlich über `config2.toml`
    (Betriebsentscheidung Birk, 2026-08-31).

    Was für alle gilt und nicht verhandelbar ist: kein Retry (spec §8), das
    Format entscheidet `image_extension` aus den Magic Bytes, und geschrieben
    wird über `save_image` mit exklusivem „xb".
    """
    if api_mode == "bfl_proxy":
        return _render_bfl_proxy(
            prompt,
            endpoint=model,
            url=url,
            timeout=timeout,
            width=width,
            height=height,
            post_bytes=post_bytes,
        )
    if api_mode == "bfl":
        return _render_bfl(
            prompt,
            endpoint=model,
            api_key=api_key,
            url=url,
            timeout=timeout,
            width=width,
            height=height,
            post=post,
            get_json=get_json,
            get_bytes=get_bytes,
            sleep=sleep,
        )
    if api_mode != "openrouter":
        raise ImageError(f"unknown image_api_mode {api_mode!r}")
    return _render_openrouter(
        prompt,
        model=model,
        api_key=api_key,
        url=url,
        timeout=timeout,
        post=post,
        aspect_ratio=aspect_ratio,
    )


def _render_openrouter(
    prompt: str,
    *,
    model: str,
    api_key: str | None,
    url: str,
    timeout: float,
    post=_httpx_post,
    aspect_ratio: str | None = None,
) -> bytes:
    """One call, no retry. `post` is injectable so no test touches the network.

    Two request details are model-dependent and were measured against the live
    endpoint on 2026-08-30, not assumed:

    * **`modalities`.** Google's and OpenAI's image models declare
      `output_modalities: ["image", "text"]` and need the pair, or they answer
      in prose about the picture instead of returning one (contract document).
      Black Forest Labs' `flux.2-max` declares `["image"]` ALONE and answers
      HTTP 404 „No endpoints found that support the requested output
      modalities: image, text\" to the pair. Asking for text from a model that
      cannot produce it excludes it entirely — which is why flux was long
      believed to be absent from OpenRouter (it is also missing from
      `/api/v1/models`, so the catalogue confirms the wrong conclusion).
    * **`image_config.aspect_ratio`.** The aspect ratio otherwise travels as
      prose inside the prompt, and prose is a request, not a setting: measured,
      gemini-3-pro-image honours it (1376x768), while gpt-5-image and
      gemini-2.5-flash-image return a square 1024x1024 regardless — and
      accept every aspect-ratio parameter with HTTP 200 while ignoring it,
      which looks like success. `flux.2-max` DOES honour the parameter
      (2048x1136). It is therefore sent when given, harmless where ignored.
    """
    if not api_key:
        raise ImageError("OPENROUTER_API_KEY is not set — stage 2 cannot render")

    body: dict = {
        "model": model,
        "modalities": ["image"] if _image_only(model) else ["image", "text"],
        "messages": [{"role": "user", "content": prompt}],
    }
    if aspect_ratio:
        body["image_config"] = {"aspect_ratio": aspect_ratio}

    try:
        payload = post(url, headers={"Authorization": f"Bearer {api_key}"},
                       json=body, timeout=timeout)
    except ImageError:
        raise
    except Exception as exc:  # transport, HTTP status, JSON — all one failure
        raise ImageError(f"image request failed: {exc}") from exc

    return decode_image(payload)


#: Sekunden zwischen zwei Nachfragen beim BFL-Auftrag. Kein Konfigurationswert:
#: die Zahl beschreibt den Anbieter, nicht die Station, und sie darf nicht so
#: klein werden, dass das Pollen selbst zur Last wird.
BFL_POLL_INTERVAL_S = 1.5

#: Status-Werte, die BFL für „fertig" und für „daraus wird nichts" sendet.
#: Alles andere (Pending, Request Moderated in Arbeit, …) heißt weiterwarten.
_BFL_READY = "Ready"
_BFL_FAILED = ("Error", "Content Moderated", "Request Moderated", "Task not found")


def _render_bfl_proxy(
    prompt: str,
    *,
    endpoint: str,
    url: str,
    timeout: float,
    width: int,
    height: int,
    post_bytes=_httpx_post_bytes,
) -> bytes:
    """Derselbe Anbieter wie `_render_bfl`, aber über den Loopback-Proxy.

    Warum dieser Umweg existiert (Kurzfassung; die Messungen stehen in
    `~/.hermes/profiles/birk/docs/bfl-wildcard-egress-loesungsweg.md`):

    Die nftables-Firewall der Maschine gibt uid `birk` nur eine enge
    Domain-Allowlist frei. BFL passt dort prinzipiell nicht hinein — die
    Bilder kommen von `delivery.*.bfl.ai`, und BFL rät selbst dazu, die
    WILDCARD freizugeben statt einzelner Regionshostnamen, weil sich die
    Region-Kennungen ändern. nftables kann keine Wildcards (es matcht IPs,
    kein SNI), und die beteiligten Azure-IPs sind geteilte Infrastruktur:
    sie freizugeben öffnete Egress zu fremden Azure-Kunden.

    Deshalb läuft der Netzzugang in einem eigenen OS-User (`bflproxy`), der
    in der bestehenden `broker_egress`-Chain hängt. Dieser Aufruf hier geht
    also nur bis `127.0.0.1` — und braucht folgerichtig **keinen API-Key**:
    den kennt ausschließlich der Proxy. Genau das ist der Gewinn gegenüber
    `api_mode="bfl"`, wo der Schlüssel im Stationsprozess liegt.

    Der Proxy gibt die fertigen Bildbytes zurück, nicht die signierte URL —
    er nimmt uns also auch das Zehn-Minuten-Fenster und das Polling ab. Für
    die Aufrufer bleibt alles gleich: `image_extension` entscheidet weiter
    aus den Magic Bytes, `save_image` schreibt weiter mit exklusivem „xb",
    und es gibt weiterhin keinen Retry (spec §8).
    """
    payload = {
        "prompt": prompt,
        "model": endpoint,
        "width": width,
        "height": height,
    }
    try:
        data = post_bytes(url, payload, timeout)
    except ImageError:
        raise
    except Exception as exc:  # Transport, Verbindung verweigert, Timeout
        raise ImageError(f"bfl-proxy nicht erreichbar ({url}): {exc}") from exc

    if not data:
        raise ImageError("bfl-proxy lieferte eine leere Antwort")
    # Wirft, wenn es kein Bild ist — dieselbe Prüfung wie auf allen anderen
    # Wegen, damit eine durchgereichte Fehlerseite nicht auf der Wand landet.
    image_extension(data)
    return data


def _render_bfl(
    prompt: str,
    *,
    endpoint: str,
    api_key: str | None,
    url: str,
    timeout: float,
    width: int,
    height: int,
    post=_httpx_post,
    get_json=_httpx_get_json,
    get_bytes=_httpx_get_bytes,
    sleep=time.sleep,
) -> bytes:
    """Black Forest Labs, EU-Endpunkt. Drei Schritte statt einem.

    1. ``POST <url>/<endpoint>`` mit ``{"prompt", "width", "height"}``. Das
       Modell IST der Endpunkt (``flux-pro-1.1``, …) — es gibt kein
       ``model``-Feld im Body, und ``modalities``/``_image_only`` sind
       OpenRouter-Eigenheiten, die hier nichts verloren haben.
    2. Die Antwort trägt ``id`` und ``polling_url``. Gepollt wird die
       gelieferte URL, nie eine selbst zusammengesetzte: sie enthält bereits
       alles, was der Anbieter zur Zuordnung braucht.
    3. ``result.sample`` ist eine **signierte URL mit 10 Minuten Gültigkeit**.
       Sie wird sofort geladen und nirgends gespeichert — eine URL, die morgen
       in der Datenbank steht, ist morgen ein toter Link.

    **Der Header heißt ``x-key``, nicht ``Authorization: Bearer``.** Ein
    Bearer-Token wird ignoriert und der Request scheitert mit 401 — ein Fehler,
    der wie ein falscher Schlüssel aussieht und keiner ist.

    **Pollen ist kein Retry** (spec §8): der Auftrag wird genau einmal erteilt,
    danach wird nur noch nach seinem Ergebnis gefragt. Scheitert das Absenden,
    ist der Traum vorbei — kein zweiter Versuch, keine Retry-Kaskade. Das
    Zeitbudget ist dasselbe ``image_timeout_s`` wie beim OpenRouter-Weg; läuft
    es ab, ohne dass der Auftrag fertig ist, wird der Traum ausgesessen und der
    nächste Trigger versucht es neu.
    """
    if not api_key:
        raise ImageError(
            "BFL_API_KEY is not set (or image_api_key_env names an empty "
            "variable) — stage 2 cannot render"
        )

    submit_url = f"{url.rstrip('/')}/{endpoint}"
    headers = {"x-key": api_key}
    try:
        payload = post(
            submit_url,
            headers=headers,
            json={"prompt": prompt, "width": width, "height": height},
            timeout=timeout,
        )
    except ImageError:
        raise
    except Exception as exc:  # transport, HTTP status, JSON — all one failure
        raise ImageError(f"image request failed: {exc}") from exc

    polling_url = (payload or {}).get("polling_url")
    if not polling_url:
        raise ImageError(f"no polling_url in the submit response: {str(payload)[:120]!r}")

    deadline = time.monotonic() + timeout
    while True:
        try:
            result = get_json(polling_url, headers=headers, timeout=timeout)
        except Exception as exc:
            raise ImageError(f"polling the image job failed: {exc}") from exc

        status = (result or {}).get("status")
        if status == _BFL_READY:
            break
        if status in _BFL_FAILED:
            raise ImageError(f"the image job ended as {status!r}")
        if time.monotonic() >= deadline:
            raise ImageError(
                f"the image job was still {status!r} and never became ready "
                f"within {timeout}s"
            )
        sleep(BFL_POLL_INTERVAL_S)

    sample = ((result or {}).get("result") or {}).get("sample")
    if not sample:
        raise ImageError("the image job is ready but carries no result.sample url")

    try:
        # Sofort, nicht später: die URL ist zehn Minuten gültig.
        return get_bytes(sample, timeout=timeout)
    except Exception as exc:
        raise ImageError(f"downloading the finished image failed: {exc}") from exc


def save_image(data: bytes, path: Path) -> Path:
    """Write image bytes to `path`, with the extension corrected to match the
    real content (PNG or JPEG — contract document, „Abweichung 3"). `path` may
    be given with or without a suffix; either way the returned path carries
    the extension the bytes actually have, and that is the only name the
    caller should record anywhere (e.g. `dreams.sqlite3`). Never overwrites
    (spec §5.2).

    The magic-number check is not paranoia: a JSON error body that happened to
    survive base64 decoding would otherwise land on disk and render as a
    broken image on the wall, where nobody can tell it from a bad dream.

    Format is decided FIRST, from the bytes, before any file is touched. Two
    consequences follow:

    * Invalid content never reaches the filesystem at all — there is no
      intermediate name left behind to clean up, because none was ever
      created.
    * The exclusive-create guard runs on the real, final name
      (`path.with_suffix(extension)`), not on a stand-in that gets renamed
      later. A second call for the same id and the SAME format therefore
      fails with `FileExistsError` straight out of the filesystem's own
      exclusive-create (`"xb"`) — airtight, no window where two cycles racing
      on one id could both think they won.

    A second call for the same id under the OTHER accepted format (PNG first,
    then JPEG, or vice versa) is also rejected — a dream may only ever have
    one image, no matter which format each attempt happened to produce — but
    that check is a plain existence test against the sibling filename, not a
    second exclusive-create. It is honest to say this one has a narrow race:
    two processes could both pass it before either has created its file,
    because two different final filenames cannot be reserved by one atomic
    filesystem call the way one filename can. That window does not weaken the
    same-format guarantee above, which is the case that matters in practice
    (a retried or duplicated cycle re-rendering the same dream).
    """
    extension = image_extension(data)  # raises before anything touches disk
    path = Path(path)
    target = path.with_suffix(extension)
    target.parent.mkdir(parents=True, exist_ok=True)

    for _, other_extension in _MAGIC_EXTENSIONS:
        if other_extension == extension:
            continue
        sibling = target.with_suffix(other_extension)
        if sibling.exists():
            raise FileExistsError(f"{sibling} already holds this id's image")

    # "xb" rather than a pre-check: exclusive create, so two cycles racing on
    # one id in the same format cannot both think they won.
    handle = target.open("xb")
    try:
        handle.write(data)
    except OSError as exc:
        # A full disk mid-write. Rare, but `kg2.cycle` is written to catch ONE
        # exception type from this module, and a bare OSError would also leave
        # the half-written file sitting where the strip expects a picture.
        handle.close()
        target.unlink(missing_ok=True)
        log.error("could not write %s: %s", target, exc)
        raise ImageError(f"could not write {target.name}: {exc}") from exc
    else:
        handle.close()

    return target
