"""Shared setup for the two end-to-end tests.

Both tests run the real adapters against a local stand-in of the outside
world. They are marked `e2e` and deselected from the standard suite (see
`addopts` in pyproject.toml) — `test_stt_to_wall` spends real Anthropic
tokens, and the standard suite must stay free.

Run them explicitly:

    pytest -m e2e tests/e2e
"""

from __future__ import annotations

import os

import pytest
from PIL import Image

from kg.bus import EventBus
from kg.config import Config
from kg.core import Core
from kg.embeddings import HashEmbedder
from kg.store import Store
from kg.transcript import TranscriptLog


@pytest.fixture()
def cfg(tmp_path) -> Config:
    return Config(
        data_dir=tmp_path / "state",
        portrait_size=64,
        terms_per_interview=5,
        interview_timeout_s=900,
    )


@pytest.fixture()
def station(cfg):
    """Store, bus and transcript log — everything a Core needs but the model."""
    store = Store.open(cfg.db_path)
    log = TranscriptLog(cfg.transcript_log_path)
    yield cfg, store, EventBus(), log
    store.close()


def make_core(cfg, store, bus, log, llm, processor=None) -> Core:
    """A real Core. `embedder` is the hash embedder on purpose.

    Embeddings are preselection only (spec 6.2) and the first interview of a
    run has no existing terms to preselect from, so the real OpenRouter
    embedder would not even be called here — depending on a second API key to
    prove that would be dishonest, not thorough.
    """
    kwargs = {} if processor is None else {"processor": processor}
    return Core(cfg, store, bus, log, llm, HashEmbedder(), **kwargs)


def write_photo(path, size=(800, 1000)):
    """A JPEG on disk. Stands in for what came out of a phone camera."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size, (30, 90, 160))
    for y in range(size[1] // 3):  # a band, so a wrong crop would be visible
        for x in range(size[0]):
            image.putpixel((x, y), (220, 200, 40))
    image.save(path, format="JPEG")
    return path


# A placeholder for the case below. Not a secret and not a credential: the
# local proxy authenticates the machine's own session, but the SDK requires
# *some* key before it will build a client at all.
_PROXY_PLACEHOLDER_KEY = "local-proxy-authenticates-the-session"


def require_anthropic_key() -> str:
    """The credential for the real model call — environment only, never a file.

    Two ways to reach a model, and the production `LLMClient` needs no change
    for either: the Anthropic SDK reads `ANTHROPIC_BASE_URL` from the
    environment itself whenever no `base_url=` is passed, so pointing the
    station at a local Anthropic-compatible proxy is an operator decision
    (docs/operations.md), not a code seam. Building a client here and pushing
    it in through `LLMClient(client=...)` would work too, but it would leave
    the shipped construction path untested — and that path is precisely what
    an end-to-end test is for.
    """
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    if os.environ.get("ANTHROPIC_BASE_URL"):
        return _PROXY_PLACEHOLDER_KEY
    pytest.skip(
        "neither ANTHROPIC_API_KEY nor ANTHROPIC_BASE_URL is set — this test calls the real model"
    )
