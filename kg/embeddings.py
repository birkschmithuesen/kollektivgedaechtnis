"""Embeddings are preselection only — negligible cost (spec 6.2).

Provider: OpenRouter's OpenAI-compatible /api/v1/embeddings. Deliberately NOT a
local sentence-transformers model — Birk decided for the cloud endpoint
(spec 6.2); do not reintroduce a local model.

Every embedding is cached by (model, text) in SQLite. That is a requirement,
not an optimisation: the simulation (spec 9) is a regression net that must be
re-runnable for free and offline.

The naming decision is the LLM's; see kg.merging.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

_WORD = re.compile(r"\w+", flags=re.UNICODE)


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class HashEmbedder:
    """Deterministic bag-of-words hashing. No download, no GPU, no variance.

    Used by tests and by frozen simulation runs so two runs are comparable.
    """

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._one(text) for text in texts]

    def _one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for word in _WORD.findall(text.lower()):
            digest = hashlib.sha1(word.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dim
            vector[index] += 1.0
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            return vector
        return [v / norm for v in vector]


def _httpx_post(url: str, headers: dict, json: dict) -> dict:
    import httpx

    response = httpx.post(url, headers=headers, json=json, timeout=30.0)
    response.raise_for_status()
    return response.json()


def _normalise(vector: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(float(v) * float(v) for v in vector))
    if norm == 0:
        return [float(v) for v in vector]
    return [float(v) / norm for v in vector]


class OpenRouterEmbedder:
    """OpenAI-compatible embeddings endpoint (spec 6.2).

    `post` is injectable so the tests never touch the network.
    """

    def __init__(
        self,
        model: str,
        api_key: str | None,
        url: str,
        post=_httpx_post,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.url = url
        self.post = post

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        texts = list(texts)
        if not texts:
            return []
        if not self.api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set — embeddings need it on a cache miss"
            )
        payload = self.post(
            self.url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "input": texts},
        )
        rows = payload["data"]
        if len(rows) != len(texts):
            raise RuntimeError(
                f"OpenRouter embeddings: expected {len(texts)} rows for "
                f"{len(texts)} inputs, got {len(rows)}"
            )
        # A row missing "index" (or two rows sharing one) would otherwise
        # collide in the sort below and silently mis-pair a vector onto the
        # wrong label. -1 is never a valid index, so it can never complete a
        # 0..len(texts)-1 permutation — any row that is missing or duplicate
        # is caught here instead of degrading preselection silently.
        indices = sorted(row.get("index", -1) for row in rows)
        if indices != list(range(len(texts))):
            raise RuntimeError(
                "OpenRouter embeddings: response rows are missing or duplicate an index"
            )
        rows = sorted(rows, key=lambda row: row["index"])
        return [_normalise(row["embedding"]) for row in rows]


class EmbeddingCache:
    """One embedding per (model, text), ever. Survives `rm -rf out/`."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS embedding ("
            " model TEXT NOT NULL, text TEXT NOT NULL, vector TEXT NOT NULL,"
            " PRIMARY KEY (model, text))"
        )
        self.conn.commit()

    def get_many(self, model: str, texts: Sequence[str]) -> dict[str, list[float]]:
        found: dict[str, list[float]] = {}
        for text in dict.fromkeys(texts):
            row = self.conn.execute(
                "SELECT vector FROM embedding WHERE model=? AND text=?", (model, text)
            ).fetchone()
            if row:
                found[text] = json.loads(row[0])
        return found

    def put_many(self, model: str, vectors: dict[str, list[float]]) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO embedding(model, text, vector) VALUES (?,?,?)",
            [(model, text, json.dumps(vec)) for text, vec in vectors.items()],
        )
        self.conn.commit()


class CachedEmbedder:
    """Only cache misses go over the network (spec 6.2)."""

    def __init__(self, inner: "Embedder", cache: EmbeddingCache, model: str) -> None:
        self.inner = inner
        self.cache = cache
        self.model = model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        texts = list(texts)
        if not texts:
            return []
        known = self.cache.get_many(self.model, texts)
        missing = [t for t in dict.fromkeys(texts) if t not in known]
        if missing:
            fresh = dict(zip(missing, self.inner.embed(missing)))
            self.cache.put_many(self.model, fresh)
            known |= fresh
        return [known[text] for text in texts]


def build_embedder(cfg, hash_only: bool = False) -> "Embedder":
    """The single place where embedder wiring is decided."""
    if hash_only:
        return HashEmbedder()
    return CachedEmbedder(
        OpenRouterEmbedder(
            model=cfg.embedding_model,
            api_key=cfg.openrouter_api_key,
            url=cfg.embedding_url,
        ),
        EmbeddingCache(cfg.embedding_cache_path),
        model=cfg.embedding_model,
    )


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return float(sum(x * y for x, y in zip(a, b)))


def nearest(vec: Sequence[float], candidates: dict[str, list[float]], k: int) -> list[str]:
    scored = sorted(
        ((key, cosine(vec, value)) for key, value in candidates.items()),
        key=lambda item: (-item[1], item[0]),
    )
    return [key for key, _ in scored[:k]]
