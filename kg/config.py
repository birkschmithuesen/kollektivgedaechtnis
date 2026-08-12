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
    tail_seconds: int = 120
    stop_phrases: list[str] = field(default_factory=lambda: list(DEFAULT_STOP_PHRASES))
    terms_per_interview: int = 5
    merge_neighbours: int = 5
    merge_style: str = DEFAULT_MERGE_STYLE
    llm_model: str = "claude-opus-5"
    llm_effort: str = "high"
    llm_max_tokens: int = 16000
    # Embeddings: OpenRouter, OpenAI-compatible endpoint (spec 6.2). Cloud is
    # explicitly fine here; the cache makes re-runs free and offline.
    embedding_model: str = "openai/text-embedding-3-small"
    embedding_url: str = "https://openrouter.ai/api/v1/embeddings"
    default_min_mentions: int = 1
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
    "tail_seconds",
    "stop_phrases",
    "terms_per_interview",
    "merge_neighbours",
    "merge_style",
    "llm_model",
    "llm_effort",
    "llm_max_tokens",
    "embedding_model",
    "embedding_url",
    "default_min_mentions",
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
