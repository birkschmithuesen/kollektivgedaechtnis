"""Configuration loading. Secrets come from the environment, never from the file."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_STOP_PHRASES = [
    "Interview beendet",
    "Interview ist beendet",
    "Aufnahme beenden",
    "Aufnahme ist beendet",
]

# Prompt dial for merge aggressiveness (spec 6.2): calibrated in simulation,
# never exposed at runtime.
DEFAULT_MERGE_STYLE = (
    "Fasse nur zusammen, was wirklich dasselbe meint. Verwandte, aber "
    "unterschiedliche Ideen bleiben getrennte Knoten."
)


@dataclass(frozen=True)
class Config:
    data_dir: Path
    stt_url: str = "http://127.0.0.1:5051"
    telegram_chat_id: int | None = None
    interview_timeout_s: int = 900
    stop_phrases: list[str] = field(default_factory=lambda: list(DEFAULT_STOP_PHRASES))
    terms_per_interview: int = 5
    # Run 19c: 5 was too narrow — in 7 of 8 near-misses of run 19b the
    # concept's own node sat at rank 7-56 in the candidate pool and was never
    # shown to the judge. Embeddings are cached, so the widening costs
    # merge-prompt tokens only.
    merge_neighbours: int = 12
    merge_style: str = DEFAULT_MERGE_STYLE
    llm_model: str = "claude-opus-5"
    llm_effort: str = "high"
    llm_max_tokens: int = 16000
    # Embeddings: OpenRouter, OpenAI-compatible endpoint (spec 6.2). Cloud is
    # explicitly fine here; the cache makes re-runs free and offline.
    embedding_model: str = "openai/text-embedding-3-small"
    embedding_url: str = "https://openrouter.ai/api/v1/embeddings"
    # Replaces the old `default_min_mentions` (a threshold on mention count):
    # spec 2026-08-29 found the threshold an indirect proxy for the real
    # constraint, how many term labels fit on the wall before they collide or
    # shrink below reading size. This is a direct cap on term count instead —
    # a different setting, not a reinterpretation, so an existing database's
    # `min_mentions` value is never read as a `max_terms` value (kg/store.py
    # seeds this key fresh via set_setting_default, spec §4/§6).
    default_max_terms: int = 32
    # The mode the wall opens in on a FRESH database. D4 (2026-08-19) opened on
    # the whole net; revised 2026-08-26 (Birk) once the automatic traversal
    # stopped being a sideways slide and became a tour from term to term —
    # surfaces A and C should both be roaming by default, and a station that
    # comes up motionless reads as broken rather than as "fit to screen".
    # Only a default: the operator's live setting is persisted and wins on
    # every restart (spec 7, 10.5).
    default_camera_mode: str = "pan"
    portrait_size: int = 512
    server_host: str = "127.0.0.1"
    server_port: int = 8800
    anthropic_api_key: str | None = None
    telegram_token: str | None = None
    openrouter_api_key: str | None = None

    @property
    def db_path(self) -> Path:
        return self.data_dir / "kg.db"

    @property
    def embedding_cache_path(self) -> Path:
        # Deliberately in data_dir, not in a run directory: simulation runs wipe
        # their own db but must keep the embedding cache (spec 6.2).
        return self.data_dir / "embeddings.sqlite3"

    @property
    def graph_json_path(self) -> Path:
        return self.data_dir / "graph.json"

    @property
    def transcript_log_path(self) -> Path:
        return self.data_dir / "transcript.jsonl"

    @property
    def photo_dir(self) -> Path:
        return self.data_dir / "photos"

    @property
    def portrait_dir(self) -> Path:
        return self.data_dir / "portraits"

    def __post_init__(self) -> None:
        # Directories exist as soon as a Config exists — the server mounts
        # portrait_dir at import time and every task constructs Config directly.
        for directory in (self.data_dir, self.photo_dir, self.portrait_dir):
            directory.mkdir(parents=True, exist_ok=True)


_FIELD_NAMES = {
    "stt_url",
    "telegram_chat_id",
    "interview_timeout_s",
    "stop_phrases",
    "terms_per_interview",
    "merge_neighbours",
    "merge_style",
    "llm_model",
    "llm_effort",
    "llm_max_tokens",
    "embedding_model",
    "embedding_url",
    "default_max_terms",
    "default_camera_mode",
    "portrait_size",
    "server_host",
    "server_port",
}


def load_config(path: Path | None = None) -> Config:
    path = Path(path) if path else Path("config.toml")
    raw: dict = {}
    if path.exists():
        raw = tomllib.loads(path.read_text(encoding="utf-8"))

    base = path.parent.resolve()
    data_dir = (base / raw.get("data_dir", "data")).resolve()

    kwargs = {k: v for k, v in raw.items() if k in _FIELD_NAMES}
    return Config(
        data_dir=data_dir,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        telegram_token=os.environ.get("KG_TELEGRAM_TOKEN"),
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY"),
        **kwargs,
    )
