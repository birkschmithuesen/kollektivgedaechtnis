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

* **The register is fixed and appended to every prompt.** Never model-chosen,
  never graph-driven (spec §5.2, brainstorm §10). The history strip is a
  measurement series; exactly one variable may change, and that is the material.
  A travelling style would make the strip show style changes and bury the
  content drift behind them.
* **The image is never overwritten** (spec §5.2). An overwrite would silently
  rewrite history, and the strip is the evidence that there was never one vision
  of the future.

There is deliberately NO retry (spec §8). A failed render abandons the dream,
the current image stays up, and the next trigger tries again — that is „ride it
out", and it is also what keeps a conference-wifi outage from tripling the bill.
"""

from __future__ import annotations

import base64
import logging
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


def build_image_prompt(sentence: str, register: str, aspect_ratio: str) -> str:
    """The sentence first, the register after it.

    Order matters: a prompt that opens with lighting instructions gets an image
    about lighting. The sentence is the subject; the register is how it is
    painted.
    """
    return (
        f"{sentence}\n\n"
        f"Bildsprache (unveränderlich, gilt für jedes Bild dieser Reihe): {register}\n"
        f"Format: Seitenverhältnis {aspect_ratio}, Querformat."
    )


def _httpx_post(url: str, headers: dict, json: dict, timeout: float) -> dict:
    import httpx

    response = httpx.post(url, headers=headers, json=json, timeout=timeout)
    response.raise_for_status()
    return response.json()


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


def render_image(
    prompt: str,
    *,
    model: str,
    api_key: str | None,
    url: str,
    timeout: float,
    post=_httpx_post,
) -> bytes:
    """One call, no retry. `post` is injectable so no test touches the network."""
    if not api_key:
        raise ImageError("OPENROUTER_API_KEY is not set — stage 2 cannot render")

    try:
        payload = post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                # Without `modalities` the model answers in text about the
                # image instead of returning one (contract document).
                "model": model,
                "modalities": ["image", "text"],
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=timeout,
        )
    except ImageError:
        raise
    except Exception as exc:  # transport, HTTP status, JSON — all one failure
        raise ImageError(f"image request failed: {exc}") from exc

    return decode_image(payload)


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
