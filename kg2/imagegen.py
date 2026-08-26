"""Stage 2: the sentence becomes an image (spec §5.2).

Built against `docs/dream-image-contract.md`. That document is currently
marked NOT YET VERIFIED: the request/response shapes below are assumed from
the model's documentation, exactly as the brief for this task assumed them,
and have not yet been confirmed by an actual call to the OpenRouter endpoint
(no `OPENROUTER_API_KEY` was available while this module was written). The
probe command that must be run before the exhibition lives in that document.
If the real response differs, the document is what gets corrected first, and
this module follows.

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
_DATA_PREFIX = "data:"


class ImageError(RuntimeError):
    """Stage 2 did not produce an image. One type for `kg2.cycle` to catch."""


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
    """Pull the PNG out of the response recorded in the contract document.

    Every failure below is a real one seen from image endpoints: an answer in
    prose about the picture, an empty list, or a link instead of inline data.
    """
    try:
        message = payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ImageError(f"no choices in the image response: {exc}") from exc

    images = message.get("images") or []
    if not images:
        # The commonest real failure: the model answers ABOUT the image.
        preview = str(message.get("content", ""))[:120]
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
    """Write PNG bytes to `path`. Never overwrites (spec §5.2).

    The magic-number check is not paranoia: a JSON error body that happened to
    survive base64 decoding would otherwise land on disk as `d1.png` and render
    as a broken image on the wall, where nobody can tell it from a bad dream.

    The overwrite guard runs BEFORE the content check, not after: the file is
    opened for exclusive create first, so a second write against an existing
    id fails with `FileExistsError` even if the new bytes happen to be
    garbage. Content validity is never allowed to decide whether an overwrite
    was attempted.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # "xb" rather than a pre-check: exclusive create, so two cycles racing on
    # one id cannot both think they won.
    handle = path.open("xb")
    try:
        if not data.startswith(_PNG_MAGIC):
            raise ImageError(f"stage 2 returned {len(data)} bytes that are not a PNG")
        handle.write(data)
    except ImageError:
        handle.close()
        path.unlink()  # no partial/garbage file left behind
        raise
    except OSError as exc:
        # A full disk mid-write. Rare, but `kg2.cycle` is written to catch ONE
        # exception type from this module, and a bare OSError would also leave
        # the half-written file sitting where the strip expects a picture.
        handle.close()
        path.unlink(missing_ok=True)
        log.error("could not write %s: %s", path, exc)
        raise ImageError(f"could not write {path.name}: {exc}") from exc
    else:
        handle.close()
    return path
