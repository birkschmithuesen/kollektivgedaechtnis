# Kollektivgedächtnis — Tool 1 (Live-Interview-Graph) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete backend + renderer for the festival station „Kollektivgedächtnis": Telegram photo triggers an interview, a continuous STT stream is segmented and condensed by an LLM into person/term nodes, and a growing graph is projected at 1920×1080 onto a whiteboard.

**Architecture:** One Python asyncio process (the Core) is the only writer. It consumes the external STT server's SSE `/events` stream into a JSONL transcript log, receives photos and stop commands from a slim Telegram poller, runs a per-interview LLM pipeline (extract → embedding preselect → LLM merge judge → persist), keeps SQLite as the truth, and re-exports a complete `graph.json` after every change. A FastAPI server in the same process serves two static browser pages (projection + operator) and pushes changes over SSE. The frontend is plain ES modules plus a vendored Cytoscape.js — no bundler, no npm at runtime.

**Tech Stack:** Python 3.12 (via `uv`), SQLite (stdlib `sqlite3`, WAL), FastAPI + uvicorn, httpx, python-telegram-bot, Pillow, Anthropic SDK (`claude-opus-5`), OpenRouter `/api/v1/embeddings` via httpx with a persistent embedding cache (spec §6.2 — **no local sentence-transformers**), Cytoscape.js (vendored), Playwright (headless pre-render + frontend tests), pytest.

**Source of truth:** `docs/superpowers/specs/2026-08-12-kollektivgedaechtnis-design.md` (APPROVED). Section references below (§) point into that spec. Everything in spec §12 is out of scope and must not be built.

## Global Constraints

- Output format: **1920×1080, 16:9 landscape** (spec §2).
- Projection surface: **whiteboard** — additive projection, black is not black (spec §2). No design decision may assume true black.
- Expected scale: **~50 person nodes max** over the whole festival (spec §2). Do not build for more.
- Aesthetics: **no legend, no filters, no cluster hubs, no statistics bar** — bare organic net (spec §2).
- GDPR is **not** a selection criterion; cloud services permitted (spec §2).
- Machine: laptop on site, **no GPU assumed** (spec §2). Every model must run on CPU.
- Credentials: read from env only — `ANTHROPIC_API_KEY` (extraction/merge LLM), `KG_TELEGRAM_TOKEN` (bot), `OPENROUTER_API_KEY` (embeddings; a separate key from the extraction LLM is explicitly acceptable, spec §6.2). Never read `~/.hermes/.env`, never commit a key (spec §2).
- Embeddings run against **OpenRouter `/api/v1/embeddings`** (OpenAI-compatible) and **must be cached by term text**, so a simulation re-run is free and offline (spec §6.2). No local embedding model, no `sentence-transformers` dependency.
- **No agent in the live loop** — deterministic plain-Python pipeline, no Hermes runtime (spec §2).
- **Do NOT fork or modify the STT server.** The Core is an independent SSE consumer (spec §4).
- Serial interviews only — exactly one interview open at a time (spec §5).
- **Person↔term edges only.** Never build term↔term edges (spec §6.4).
- Exactly **one runtime dial: minimum mention count**, a pure display filter. No other runtime control may change extraction or merging (spec §7).
- Curation is a **hide flag only** — no approval gate, no editing, no queue (spec §8).
- **Node positions are persisted; the layout must never re-shuffle existing nodes** (spec §11).
- All persisted state must be reconstructible from SQLite after a crash, including positions (spec §10.5, §11).
- Language of all user-visible text, prompts and interview content: **German**. Code, identifiers and comments: English.
- LLM: model id `claude-opus-5` exactly (no date suffix). Adaptive thinking is on by default on this model — do not pass `thinking`. Never pass `temperature`, `top_p`, `top_k`, or `budget_tokens` (they return 400). Depth is controlled by `output_config.effort`.

## Repository layout (created across the tasks below)

```
pyproject.toml                 Task 1
config.example.toml            Task 1
kg/config.py                   Task 1   Config dataclass + load_config
kg/db.py                       Task 2   schema, connect, migrations
kg/models.py                   Task 2   Person/Term/Edge/Quote dataclasses
kg/store.py                    Task 2   ALL SQLite reads/writes (single writer)
kg/sse.py                      Task 3   SSE line decoder (pure)
kg/transcript.py               Task 3   JSONL transcript log + time-range reads
kg/stt_client.py               Task 3   /events consumer with reconnect
kg/segmentation.py             Task 4   stop-phrase matching + stripping
kg/session.py                  Task 5   interview state machine (pure)
kg/photos.py                   Task 6   portrait normalisation
kg/telegram_bot.py             Task 7   photo/stop poller
kg/llm.py                      Task 8   Anthropic wrapper, strict schema, retry
kg/extraction.py               Task 8   extraction prompt + call
kg/embeddings.py               Task 9   Embedder protocol + OpenRouter client + cache
kg/merging.py                  Task 9   candidate preselect + LLM judge + apply
kg/export.py                   Task 10  graph.json builder (atomic write)
kg/pipeline.py                 Task 11  cut → extract → merge → persist → export
kg/bus.py                      Task 12  in-process SSE fanout
kg/server.py                   Task 12  FastAPI app + operator API
kg/core.py                     Task 17  process wiring (STT + Telegram + pipeline)
kg/__main__.py                 Task 17  entrypoint
frontend/projection.html       Task 14
frontend/operator.html         Task 15
frontend/testpattern.html      Task 16
frontend/static/graph-model.js Task 13  pure display-filter logic
frontend/static/camera.js      Task 14  fit / manual / auto-pan
frontend/static/projection.js  Task 14
frontend/static/operator.js    Task 15
frontend/static/base.css + theme-a..d.css   Task 14/16
frontend/static/vendor/cytoscape.min.js     Task 13 (vendored, committed)
sim/generate_interviews.py     Task 18  synthetic corpus generator
sim/data/interviews/*.json     Task 18  committed fixtures
sim/data/expectations.yaml     Task 18  documented expected merges
sim/replay.py                  Task 19  time-lapse feeder + score
sim/prerender.py               Task 20  headless PNG series A–D
docs/stt-contract.md           Task 3   verified event contract
docs/operations.md             Task 21  on-site runbook
tests/...                      per task
```

---

### Task 1: Project skeleton and configuration

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `config.example.toml`, `kg/__init__.py`, `kg/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `kg.config.Config` (frozen dataclass) and `kg.config.load_config(path: Path | None = None) -> Config`. Every later task takes a `Config` instance.

- [ ] **Step 1: Create the Python environment and project files**

```bash
cd /home/birk/projekte/kollektivgedaechtnis
uv python install 3.12
```

Write `pyproject.toml`:

```toml
[project]
name = "kollektivgedaechtnis"
version = "0.1.0"
description = "Live interview graph installation (NEW bauhaus 2026)"
requires-python = ">=3.12"
dependencies = [
    "anthropic>=0.69",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "httpx>=0.27",
    "python-telegram-bot>=21.6",
    "pillow>=11.0",
    "pydantic>=2.9",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "playwright>=1.48",
    "pyyaml>=6.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["kg"]
```

Write `.gitignore`:

```
.venv/
__pycache__/
*.pyc
data/
out/
.env
sim/data/runs/
```

Create the package marker:

```bash
mkdir -p kg tests
touch kg/__init__.py
uv sync
```

- [ ] **Step 2: Write the failing test**

`tests/test_config.py`:

```python
from pathlib import Path

from kg.config import Config, load_config


def test_load_config_reads_toml_and_resolves_paths(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
        data_dir = "state"
        stt_url = "http://127.0.0.1:5051"
        interview_timeout_s = 900
        terms_per_interview = 5
        stop_phrases = ["Interview beendet", "Aufnahme beenden"]
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("KG_TELEGRAM_TOKEN", "123:abc")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    cfg = load_config(cfg_file)

    assert isinstance(cfg, Config)
    assert cfg.data_dir == (tmp_path / "state").resolve()
    assert cfg.db_path == (tmp_path / "state" / "kg.db").resolve()
    assert cfg.graph_json_path == (tmp_path / "state" / "graph.json").resolve()
    assert cfg.photo_dir == (tmp_path / "state" / "photos").resolve()
    assert cfg.stt_url == "http://127.0.0.1:5051"
    assert cfg.interview_timeout_s == 900
    assert cfg.terms_per_interview == 5
    assert cfg.stop_phrases == ["Interview beendet", "Aufnahme beenden"]
    assert cfg.anthropic_api_key == "sk-test"
    assert cfg.telegram_token == "123:abc"
    assert cfg.openrouter_api_key == "sk-or-test"


def test_defaults_apply_when_keys_missing(tmp_path, monkeypatch):
    # Must not depend on what happens to be exported in the shell.
    for name in ("ANTHROPIC_API_KEY", "KG_TELEGRAM_TOKEN", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('data_dir = "state"\n', encoding="utf-8")

    cfg = load_config(cfg_file)

    assert cfg.llm_model == "claude-opus-5"
    assert cfg.llm_effort == "high"
    assert cfg.default_min_mentions == 1
    assert cfg.tail_seconds == 120
    assert cfg.merge_neighbours == 5
    assert cfg.anthropic_api_key is None
    assert cfg.openrouter_api_key is None
    # Embeddings come from OpenRouter, never from a local model (spec 6.2).
    assert cfg.embedding_url == "https://openrouter.ai/api/v1/embeddings"
    assert cfg.embedding_model == "openai/text-embedding-3-small"


def test_data_dir_is_created(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('data_dir = "state"\n', encoding="utf-8")

    cfg = load_config(cfg_file)

    assert cfg.data_dir.is_dir()
    assert cfg.photo_dir.is_dir()
    assert cfg.portrait_dir.is_dir()


def test_embedding_cache_lives_outside_the_run_directory(tmp_path):
    """The cache must survive `rm -rf out/` between simulation runs (spec 6.2)."""
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('data_dir = "state"\n', encoding="utf-8")

    cfg = load_config(cfg_file)

    assert cfg.embedding_cache_path == (tmp_path / "state" / "embeddings.sqlite3").resolve()
```

- [ ] **Step 3: Run the test and confirm it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kg.config'`

- [ ] **Step 4: Implement `kg/config.py`**

```python
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
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Write `config.example.toml`**

```toml
# Copy to config.toml on the exhibition machine and adjust.
# Secrets are NOT stored here — export them in the environment:
#   export ANTHROPIC_API_KEY=...
#   export KG_TELEGRAM_TOKEN=...
#   export OPENROUTER_API_KEY=...      # embeddings only, may be a separate key

data_dir = "data"

# External STT server (see docs/stt-contract.md). Do not fork it.
# Start it from the fundusbot checkout with:
#   python -m fundusapps.stt_server elevenlabs-scribe --language de
stt_url = "http://127.0.0.1:5051"

# Only accept Telegram messages from this chat (leave unset to accept all).
# telegram_chat_id = 123456789

# Safety net so a forgotten stop cannot swallow the next interview (spec 5).
interview_timeout_s = 900
# Extra transcript beyond the stop marker handed to the LLM (spec 6.1).
tail_seconds = 120

stop_phrases = [
    "Interview beendet",
    "Interview ist beendet",
    "Aufnahme beenden",
    "Aufnahme ist beendet",
]

# Calibrated in simulation (spec 6.3), NOT runtime-adjustable.
terms_per_interview = 5
merge_neighbours = 5

llm_model = "claude-opus-5"
llm_effort = "high"

# Embedding preselection via OpenRouter (spec 6.2). Cached by term text in
# data_dir/embeddings.sqlite3, so simulation re-runs are free and offline.
embedding_model = "openai/text-embedding-3-small"
embedding_url = "https://openrouter.ai/api/v1/embeddings"

# Display filter start value; the operator dial changes it at runtime (spec 7).
default_min_mentions = 1

server_host = "127.0.0.1"
server_port = 8800
```

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock .gitignore config.example.toml kg/__init__.py kg/config.py tests/test_config.py
git commit -m "feat: project skeleton and configuration loading"
```

---

### Task 2: SQLite schema and store

**Files:**
- Create: `kg/db.py`, `kg/models.py`, `kg/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `kg.config.Config` (Task 1).
- Produces:
  - `kg.models.Person(id, started_at, stopped_at, stop_reason, status, transcript, photo_path, portrait_path, hidden)`
  - `kg.models.Term(id, label, created_at, hidden)`
  - `kg.models.Edge(id, person_id, term_id, created_at)`
  - `kg.models.Quote(id, person_id, text, created_at)`
  - `kg.store.Store` with the methods listed in Step 5 below. **`Store` is the only module that talks to SQLite.** Note `set_setting_default(key, value)` — seeds a setting only when absent, so startup can apply the calibrated `Config.default_min_mentions` without clobbering a dial the operator turned before a crash.

IDs are deterministic and human-readable: `p1`, `t1`, `e1`, `q1`, assigned from a `counters` table so two simulation runs over the same data produce identical ids (spec §9 reproducibility).

- [ ] **Step 1: Write the failing test**

`tests/test_store.py`:

```python
import pytest

from kg.store import Store


@pytest.fixture()
def store(tmp_path):
    s = Store.open(tmp_path / "kg.db")
    yield s
    s.close()


def test_ids_are_sequential_and_prefixed(store):
    a = store.create_person(started_at=100.0)
    b = store.create_person(started_at=200.0)
    assert (a.id, b.id) == ("p1", "p2")


def test_person_lifecycle(store):
    person = store.create_person(started_at=100.0, photo_path="photos/a.jpg")
    assert person.status == "open"
    assert store.open_person().id == person.id

    store.close_person(person.id, stopped_at=160.0, reason="spoken")
    reloaded = store.get_person(person.id)
    assert reloaded.stopped_at == 160.0
    assert reloaded.stop_reason == "spoken"
    assert reloaded.status == "closed"
    assert store.open_person() is None

    store.set_person_transcript(person.id, "Guten Tag.")
    store.set_person_status(person.id, "done")
    assert store.get_person(person.id).transcript == "Guten Tag."
    assert store.get_person(person.id).status == "done"


def test_terms_are_unique_by_label_and_aliases_resolve(store):
    t1 = store.get_or_create_term("Recycling-Beton", created_at=1.0)
    t2 = store.get_or_create_term("Recycling-Beton", created_at=2.0)
    assert t1.id == t2.id == "t1"

    store.add_alias(t1.id, "Beton aus Abbruch")
    assert store.find_term_by_alias("Beton aus Abbruch").id == t1.id
    assert store.find_term_by_alias("unbekannt") is None

    store.rename_term(t1.id, "Recyclingbeton")
    assert store.get_term(t1.id).label == "Recyclingbeton"
    # The old label survives as an alias so the decision is never re-derived.
    assert store.find_term_by_alias("Recycling-Beton").id == t1.id


def test_edges_are_idempotent_and_drive_mention_count(store):
    p1 = store.create_person(started_at=1.0)
    p2 = store.create_person(started_at=2.0)
    term = store.get_or_create_term("Modulares Bauen", created_at=1.0)

    store.add_edge(p1.id, term.id, created_at=3.0)
    store.add_edge(p1.id, term.id, created_at=4.0)  # same pair again
    assert len(store.list_edges()) == 1
    assert store.mention_count(term.id) == 1

    store.add_edge(p2.id, term.id, created_at=5.0)
    assert store.mention_count(term.id) == 2


def test_quotes_are_stored_even_though_the_wall_does_not_show_them(store):
    person = store.create_person(started_at=1.0)
    store.add_quote(person.id, "Wir bauen zu viel Neues.", created_at=2.0)
    quotes = store.list_quotes()
    assert [q.text for q in quotes] == ["Wir bauen zu viel Neues."]
    assert quotes[0].person_id == person.id


def test_hidden_flag_applies_to_persons_and_terms(store):
    person = store.create_person(started_at=1.0)
    term = store.get_or_create_term("Nachhaltigkeit", created_at=1.0)

    store.set_hidden(f"person:{person.id}", True)
    store.set_hidden(f"term:{term.id}", True)

    assert store.get_person(person.id).hidden is True
    assert store.get_term(term.id).hidden is True

    store.set_hidden(f"term:{term.id}", False)
    assert store.get_term(term.id).hidden is False

    with pytest.raises(ValueError):
        store.set_hidden("nonsense:1", True)


def test_positions_round_trip(store):
    store.save_positions({"p1": (10.5, -3.25), "t2": (0.0, 0.0)})
    store.save_positions({"p1": (11.0, -3.25)})  # update, not duplicate
    assert store.get_positions() == {"p1": (11.0, -3.25), "t2": (0.0, 0.0)}


def test_merge_decisions_are_persisted(store):
    person = store.create_person(started_at=1.0)
    store.record_merge_decision(person.id, {"groups": [{"canonical_label": "X"}]}, created_at=9.0)
    decisions = store.list_merge_decisions()
    assert decisions[0]["person_id"] == person.id
    assert decisions[0]["payload"]["groups"][0]["canonical_label"] == "X"


def test_settings_round_trip_with_default(store):
    assert store.get_setting("min_mentions", "1") == "1"
    store.set_setting("min_mentions", "2")
    assert store.get_setting("min_mentions", "1") == "2"


def test_set_setting_default_seeds_once_and_never_clobbers(store):
    """Startup seeds the configured density; an operator's live change wins."""
    store.set_setting_default("min_mentions", "3")
    assert store.get_setting("min_mentions", "1") == "3"

    store.set_setting("min_mentions", "1")  # operator turns the dial down
    store.set_setting_default("min_mentions", "3")  # next restart
    assert store.get_setting("min_mentions", "1") == "1"


def test_state_survives_reopening(tmp_path):
    path = tmp_path / "kg.db"
    s1 = Store.open(path)
    person = s1.create_person(started_at=1.0)
    term = s1.get_or_create_term("Ländlicher Leerstand", created_at=1.0)
    s1.add_edge(person.id, term.id, created_at=2.0)
    s1.save_positions({person.id: (5.0, 6.0)})
    s1.close()

    s2 = Store.open(path)
    assert [p.id for p in s2.list_persons()] == [person.id]
    assert [t.label for t in s2.list_terms()] == ["Ländlicher Leerstand"]
    assert len(s2.list_edges()) == 1
    assert s2.get_positions() == {person.id: (5.0, 6.0)}
    s2.close()
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kg.store'`

- [ ] **Step 3: Implement `kg/models.py`**

```python
"""Plain data carriers. Persistence lives in kg.store."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Person:
    """One interviewed visitor. Doubles as the interview record (serial by design)."""

    id: str
    started_at: float
    stopped_at: float | None = None
    stop_reason: str | None = None
    status: str = "open"  # open | closed | processing | done | failed
    transcript: str | None = None
    photo_path: str | None = None
    portrait_path: str | None = None
    hidden: bool = False


@dataclass(frozen=True)
class Term:
    id: str
    label: str
    created_at: float
    hidden: bool = False


@dataclass(frozen=True)
class Edge:
    id: str
    person_id: str
    term_id: str
    created_at: float


@dataclass(frozen=True)
class Quote:
    id: str
    person_id: str
    text: str
    created_at: float
```

- [ ] **Step 4: Implement `kg/db.py`**

```python
"""SQLite schema and connection handling."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS counters (
    name  TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS person (
    id            TEXT PRIMARY KEY,
    started_at    REAL NOT NULL,
    stopped_at    REAL,
    stop_reason   TEXT,
    status        TEXT NOT NULL DEFAULT 'open',
    transcript    TEXT,
    photo_path    TEXT,
    portrait_path TEXT,
    hidden        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS term (
    id         TEXT PRIMARY KEY,
    label      TEXT NOT NULL UNIQUE,
    created_at REAL NOT NULL,
    hidden     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS term_alias (
    surface TEXT PRIMARY KEY,
    term_id TEXT NOT NULL REFERENCES term(id)
);

CREATE TABLE IF NOT EXISTS edge (
    id         TEXT PRIMARY KEY,
    person_id  TEXT NOT NULL REFERENCES person(id),
    term_id    TEXT NOT NULL REFERENCES term(id),
    created_at REAL NOT NULL,
    UNIQUE (person_id, term_id)
);

CREATE TABLE IF NOT EXISTS quote (
    id         TEXT PRIMARY KEY,
    person_id  TEXT NOT NULL REFERENCES person(id),
    text       TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS merge_decision (
    id         TEXT PRIMARY KEY,
    person_id  TEXT NOT NULL REFERENCES person(id),
    payload    TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS position (
    node_id TEXT PRIMARY KEY,
    x       REAL NOT NULL,
    y       REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS setting (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
```

- [ ] **Step 5: Implement `kg/store.py`**

```python
"""The only module that reads from or writes to SQLite."""

from __future__ import annotations

import contextlib
import functools
import json
import sqlite3
import threading
from pathlib import Path

from kg.db import connect
from kg.models import Edge, Person, Quote, Term

_PREFIXES = {"person": "p", "term": "t", "edge": "e", "quote": "q", "merge": "m"}


def _locked(method):
    """Serialise one public `Store` method call through the store-wide lock.

    See the rationale on `Store._lock` in `__init__`. Plain wrapper (not
    itself a `@contextlib.contextmanager`-style method) so it is safe to
    stack on `transaction()`-adjacent methods too: it just acquires
    `self._lock`, runs the wrapped call, and releases it — re-entrant on the
    same thread because `self._lock` is an `RLock`.
    """

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class Store:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        # kg.db.connect opens the connection with check_same_thread=False so
        # a single connection (and this Store) can be shared across threads:
        # FastAPI runs sync route handlers in a threadpool (kg/server.py),
        # and the Core loop and the per-interview pipeline write through the
        # same Store instance from their own threads. Python's sqlite3
        # module does not serialise statements against a shared connection
        # by itself — two threads issuing statements at once can interleave
        # mid-transaction (each sees "no transaction active" and both issue
        # BEGIN, the second raising "cannot start a transaction within a
        # transaction"), or interleave between an UPSERT and the following
        # SELECT in `_next_id` and read the same counter value, minting a
        # duplicate id.
        #
        # This RLock serialises every public method below (via the
        # `@_locked` decorator) — reads included, since a read racing a
        # write on one shared connection is exactly as unsafe as two writes
        # racing. It must be re-entrant, not a plain Lock: `_next_id` is
        # called from inside other locked methods (create_person,
        # get_or_create_term, add_edge, add_quote, record_merge_decision),
        # and `transaction()` below holds this same lock for an entire
        # multi-call block while calling other `@_locked` public methods
        # within that block. A plain Lock would deadlock the instant any of
        # that happened on the thread already holding it.
        self._lock = threading.RLock()
        self._tx_depth = 0

    @classmethod
    def open(cls, path: Path) -> "Store":
        return cls(connect(Path(path)))

    @_locked
    def close(self) -> None:
        self.conn.close()

    @contextlib.contextmanager
    def transaction(self):
        """An all-or-nothing block spanning multiple `Store` calls.

        Every public method below commits its own write individually via
        `_commit`. Inside an open `transaction()`, those per-method commits
        are suppressed; the block commits once, as a whole, on clean exit, or
        rolls back everything on exception. Re-entrant: nesting a
        `transaction()` inside an already-open one only tracks depth — the
        outermost block is the one that actually commits or rolls back — so a
        helper method that opens its own `transaction()` still works
        correctly when called from within a caller's larger one.

        Holds `self._lock` (see `__init__`) for the entire block: the `with
        self._lock:` below wraps everything, including the `yield`, so the
        lock stays held from before the first statement inside the caller's
        `with store.transaction():` body runs until after the last one
        finishes — another thread can never commit, or even interleave a
        statement, inside this open transaction. `self._lock` is an RLock
        precisely so the `@_locked` public methods called inside the block
        (and a nested `transaction()`) can re-acquire it on the same thread
        without deadlocking.
        """
        with self._lock:
            self._tx_depth += 1
            try:
                yield
            except BaseException:
                # Not `except Exception`: a BaseException raised inside the
                # block (KeyboardInterrupt when the operator stops the
                # station, a thread's SystemExit) must roll back too, or
                # `finally` below drops `_tx_depth` back to 0 and releases
                # the lock while `conn` is left sitting in an uncommitted
                # implicit transaction — the next unrelated write's own
                # `_commit()` would then commit this partial write right
                # along with it, permanently persisting a half-applied
                # change (e.g. a `fold_term` with its loser deleted but the
                # loser's edges not yet moved).
                if self._tx_depth == 1:
                    self.conn.rollback()
                raise
            else:
                if self._tx_depth == 1:
                    self.conn.commit()
            finally:
                self._tx_depth -= 1

    def _commit(self) -> None:
        """Commit now, unless an enclosing `transaction()` will do it instead."""
        with self._lock:
            if self._tx_depth == 0:
                self.conn.commit()

    # -- ids ---------------------------------------------------------------

    def _next_id(self, kind: str) -> str:
        # No RETURNING clause: the target SQLite (3.34) predates 3.35's support
        # for it, so this is an upsert followed by a separate read. The two
        # statements are made atomic with `self._lock` (see the rationale in
        # `__init__`): every caller of `_next_id` is itself a `@_locked`
        # public method, so this lock is always re-entrant, but it is taken
        # explicitly here too so `_next_id` stays correct even if ever called
        # some other way.
        with self._lock:
            self.conn.execute(
                "INSERT INTO counters(name, value) VALUES (?, 1) "
                "ON CONFLICT(name) DO UPDATE SET value = value + 1",
                (kind,),
            )
            row = self.conn.execute(
                "SELECT value FROM counters WHERE name=?", (kind,)
            ).fetchone()
        return f"{_PREFIXES[kind]}{row['value']}"

    # -- person ------------------------------------------------------------

    @_locked
    def create_person(
        self,
        started_at: float,
        photo_path: str | None = None,
        portrait_path: str | None = None,
    ) -> Person:
        person_id = self._next_id("person")
        self.conn.execute(
            "INSERT INTO person(id, started_at, photo_path, portrait_path) VALUES (?,?,?,?)",
            (person_id, started_at, photo_path, portrait_path),
        )
        self._commit()
        return self.get_person(person_id)

    @_locked
    def close_person(self, person_id: str, stopped_at: float, reason: str) -> None:
        self.conn.execute(
            "UPDATE person SET stopped_at=?, stop_reason=?, status='closed' WHERE id=?",
            (stopped_at, reason, person_id),
        )
        self._commit()

    @_locked
    def set_person_transcript(self, person_id: str, text: str) -> None:
        self.conn.execute("UPDATE person SET transcript=? WHERE id=?", (text, person_id))
        self._commit()

    @_locked
    def set_person_status(self, person_id: str, status: str) -> None:
        self.conn.execute("UPDATE person SET status=? WHERE id=?", (status, person_id))
        self._commit()

    @_locked
    def set_person_portrait(self, person_id: str, photo_path: str, portrait_path: str) -> None:
        self.conn.execute(
            "UPDATE person SET photo_path=?, portrait_path=? WHERE id=?",
            (photo_path, portrait_path, person_id),
        )
        self._commit()

    @_locked
    def get_person(self, person_id: str) -> Person | None:
        row = self.conn.execute("SELECT * FROM person WHERE id=?", (person_id,)).fetchone()
        return _person(row) if row else None

    @_locked
    def open_person(self) -> Person | None:
        row = self.conn.execute(
            "SELECT * FROM person WHERE stopped_at IS NULL ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return _person(row) if row else None

    @_locked
    def list_persons(self) -> list[Person]:
        rows = self.conn.execute("SELECT * FROM person ORDER BY started_at").fetchall()
        return [_person(r) for r in rows]

    # -- term --------------------------------------------------------------

    @_locked
    def get_or_create_term(self, label: str, created_at: float) -> Term:
        existing = self.get_term_by_label(label)
        if existing:
            return existing
        term_id = self._next_id("term")
        self.conn.execute(
            "INSERT INTO term(id, label, created_at) VALUES (?,?,?)",
            (term_id, label, created_at),
        )
        self.conn.execute(
            "INSERT OR REPLACE INTO term_alias(surface, term_id) VALUES (?,?)",
            (label, term_id),
        )
        self._commit()
        return self.get_term(term_id)

    @_locked
    def get_term(self, term_id: str) -> Term | None:
        row = self.conn.execute("SELECT * FROM term WHERE id=?", (term_id,)).fetchone()
        return _term(row) if row else None

    @_locked
    def get_term_by_label(self, label: str) -> Term | None:
        row = self.conn.execute("SELECT * FROM term WHERE label=?", (label,)).fetchone()
        return _term(row) if row else None

    @_locked
    def rename_term(self, term_id: str, new_label: str) -> None:
        old = self.get_term(term_id)
        if old is None or old.label == new_label:
            return
        self.conn.execute("UPDATE term SET label=? WHERE id=?", (new_label, term_id))
        # Keep the old label reachable: a decision once made is never re-derived.
        for surface in (old.label, new_label):
            self.conn.execute(
                "INSERT OR REPLACE INTO term_alias(surface, term_id) VALUES (?,?)",
                (surface, term_id),
            )
        self._commit()

    @_locked
    def add_alias(self, term_id: str, surface: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO term_alias(surface, term_id) VALUES (?,?)",
            (surface, term_id),
        )
        self._commit()

    @_locked
    def fold_term(self, loser_id: str, winner_id: str) -> None:
        """Merge `loser_id` into `winner_id` (spec 6.2, 7): a merge is the
        finding that more people meant the same thing, so the winner must
        come out at least as strong as either term was alone — every alias
        and edge the loser carried moves onto the winner, mention counts
        combine, and the loser term itself is deleted so it cannot linger as
        an unreachable second node on the wall.

        Edges are folded through `add_edge`, which is idempotent per
        (person_id, term_id): a person who mentioned both terms ends up with
        exactly one edge to the winner, never two (edge has
        UNIQUE(person_id, term_id)).
        """
        if loser_id == winner_id:
            return
        loser = self.get_term(loser_id)
        if loser is None:
            return
        with self.transaction():
            # Point every alias the loser owned at the winner instead. The
            # loser's own label must stay reachable too — a decision, once
            # made, is never re-derived.
            self.conn.execute(
                "UPDATE term_alias SET term_id=? WHERE term_id=?", (winner_id, loser_id)
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO term_alias(surface, term_id) VALUES (?,?)",
                (loser.label, winner_id),
            )
            loser_edges = self.conn.execute(
                "SELECT person_id, created_at FROM edge WHERE term_id=?", (loser_id,)
            ).fetchall()
            for row in loser_edges:
                self.add_edge(row["person_id"], winner_id, created_at=row["created_at"])
            self.conn.execute("DELETE FROM edge WHERE term_id=?", (loser_id,))
            # The loser's position row would otherwise point at a deleted node.
            self.conn.execute("DELETE FROM position WHERE node_id=?", (f"term:{loser_id}",))
            self.conn.execute("DELETE FROM term WHERE id=?", (loser_id,))

    @_locked
    def find_term_by_alias(self, surface: str) -> Term | None:
        row = self.conn.execute(
            "SELECT t.* FROM term_alias a JOIN term t ON t.id = a.term_id WHERE a.surface=?",
            (surface,),
        ).fetchone()
        return _term(row) if row else None

    @_locked
    def list_terms(self) -> list[Term]:
        rows = self.conn.execute("SELECT * FROM term ORDER BY created_at, id").fetchall()
        return [_term(r) for r in rows]

    # -- edges / quotes ----------------------------------------------------

    @_locked
    def add_edge(self, person_id: str, term_id: str, created_at: float) -> Edge:
        row = self.conn.execute(
            "SELECT * FROM edge WHERE person_id=? AND term_id=?", (person_id, term_id)
        ).fetchone()
        if row:
            return _edge(row)
        edge_id = self._next_id("edge")
        self.conn.execute(
            "INSERT INTO edge(id, person_id, term_id, created_at) VALUES (?,?,?,?)",
            (edge_id, person_id, term_id, created_at),
        )
        self._commit()
        row = self.conn.execute("SELECT * FROM edge WHERE id=?", (edge_id,)).fetchone()
        return _edge(row)

    @_locked
    def list_edges(self) -> list[Edge]:
        rows = self.conn.execute("SELECT * FROM edge ORDER BY created_at, id").fetchall()
        return [_edge(r) for r in rows]

    @_locked
    def mention_count(self, term_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(DISTINCT person_id) AS n FROM edge WHERE term_id=?", (term_id,)
        ).fetchone()
        return int(row["n"])

    @_locked
    def add_quote(self, person_id: str, text: str, created_at: float) -> Quote:
        quote_id = self._next_id("quote")
        self.conn.execute(
            "INSERT INTO quote(id, person_id, text, created_at) VALUES (?,?,?,?)",
            (quote_id, person_id, text, created_at),
        )
        self._commit()
        row = self.conn.execute("SELECT * FROM quote WHERE id=?", (quote_id,)).fetchone()
        return Quote(row["id"], row["person_id"], row["text"], row["created_at"])

    @_locked
    def list_quotes(self) -> list[Quote]:
        rows = self.conn.execute("SELECT * FROM quote ORDER BY created_at, id").fetchall()
        return [Quote(r["id"], r["person_id"], r["text"], r["created_at"]) for r in rows]

    # -- flags, positions, decisions, settings ------------------------------

    @_locked
    def set_hidden(self, node_id: str, hidden: bool) -> None:
        kind, _, ident = node_id.partition(":")
        if kind not in ("person", "term") or not ident:
            raise ValueError(f"unknown node id: {node_id!r}")
        self.conn.execute(f"UPDATE {kind} SET hidden=? WHERE id=?", (1 if hidden else 0, ident))
        self._commit()

    @_locked
    def save_positions(self, positions: dict[str, tuple[float, float]]) -> None:
        self.conn.executemany(
            "INSERT INTO position(node_id, x, y) VALUES (?,?,?) "
            "ON CONFLICT(node_id) DO UPDATE SET x=excluded.x, y=excluded.y",
            [(node_id, float(x), float(y)) for node_id, (x, y) in positions.items()],
        )
        self._commit()

    @_locked
    def get_positions(self) -> dict[str, tuple[float, float]]:
        rows = self.conn.execute("SELECT node_id, x, y FROM position").fetchall()
        return {r["node_id"]: (r["x"], r["y"]) for r in rows}

    @_locked
    def record_merge_decision(self, person_id: str, payload: dict, created_at: float) -> None:
        self.conn.execute(
            "INSERT INTO merge_decision(id, person_id, payload, created_at) VALUES (?,?,?,?)",
            (self._next_id("merge"), person_id, json.dumps(payload, ensure_ascii=False), created_at),
        )
        self._commit()

    @_locked
    def list_merge_decisions(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM merge_decision ORDER BY created_at, id"
        ).fetchall()
        return [
            {
                "id": r["id"],
                "person_id": r["person_id"],
                "payload": json.loads(r["payload"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    @_locked
    def get_setting(self, key: str, default: str) -> str:
        row = self.conn.execute("SELECT value FROM setting WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    @_locked
    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO setting(key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        self._commit()

    @_locked
    def set_setting_default(self, key: str, value: str) -> None:
        """Seed a setting only if it has never been set.

        Startup uses this to apply the calibrated `default_min_mentions` without
        overwriting a dial the operator turned before the crash (spec 7, 10.5).
        """
        self.conn.execute(
            "INSERT OR IGNORE INTO setting(key, value) VALUES (?,?)", (key, str(value))
        )
        self._commit()


def _person(row: sqlite3.Row) -> Person:
    return Person(
        id=row["id"],
        started_at=row["started_at"],
        stopped_at=row["stopped_at"],
        stop_reason=row["stop_reason"],
        status=row["status"],
        transcript=row["transcript"],
        photo_path=row["photo_path"],
        portrait_path=row["portrait_path"],
        hidden=bool(row["hidden"]),
    )


def _term(row: sqlite3.Row) -> Term:
    return Term(
        id=row["id"], label=row["label"], created_at=row["created_at"], hidden=bool(row["hidden"])
    )


def _edge(row: sqlite3.Row) -> Edge:
    return Edge(
        id=row["id"],
        person_id=row["person_id"],
        term_id=row["term_id"],
        created_at=row["created_at"],
    )
```

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_store.py -v`
Expected: PASS (19 tests — the 11 above plus a concurrency test proving `_next_id` never mints a duplicate id under threaded use, 6 tests for `transaction()` and `fold_term()` (including a regression test that a `BaseException` raised inside `transaction()` still rolls back and leaves the `Store` usable), plus a multi-threaded regression test (task 12b) driving concurrent pipeline-style writes against concurrent operator-style writes on the same `Store` and asserting the resulting state is uncorrupted — every public method (including reads) is guarded by a store-wide `threading.RLock`, so two threads never issue overlapping statements on the shared connection. Verified: `uv run pytest tests/test_store.py -q` → 19 passed.)

- [ ] **Step 7: Commit**

```bash
git add kg/db.py kg/models.py kg/store.py tests/test_store.py
git commit -m "feat: sqlite schema and store (single writer)"
```

---

### Task 3: STT contract (verified), SSE decoder, transcript log, STT consumer

**Files:**
- Create: `docs/stt-contract.md`, `kg/sse.py`, `kg/transcript.py`, `kg/stt_client.py`
- Test: `tests/test_sse.py`, `tests/test_transcript.py`, `tests/test_stt_client.py`

**Interfaces:**
- Consumes: `kg.config.Config` (Task 1).
- Produces:
  - `kg.sse.SSEDecoder.feed(line: str) -> dict | None` — returns the parsed JSON payload when a `data:` block is terminated by a blank line; `None` otherwise (comments, keep-alives, partial blocks).
  - `kg.transcript.TranscriptionEvent` frozen dataclass with `from_dict(d: dict)` — carries all **ten** verified fields incl. `extending: bool | None`.
  - `kg.transcript.TranscriptLog(path)` with `append(event)`, `read_range(start, end) -> list[TranscriptionEvent]`, `text_between(start, end) -> str`.
  - `kg.stt_client.STTClient(url, log, on_final, on_partial, on_state)` with `async def run()`.

**✅ The contract is VERIFIED (2026-08-12) — no open item left (spec §4, §14.1 RESOLVED).** Source of truth: private repo **`meredityman/fundusbot`**, branch **`win_fundusfantasma-dev-clean`**, path `fundusapps/stt_server/` (reachable via `gh api` as `birkschmithuesen`). Verified against `events.py`, `app.py`, `args.py` and `backends/elevenlabs_scribe_backend.py`.

The event has **ten** fields — `extending` is new versus the older copy. We consume `type == "final"` only, so `extending` must merely be **tolerated** by the decoder, never acted on.

- [ ] **Step 1: Write down the verified contract in `docs/stt-contract.md`**

No verification work is left; this step records the facts below verbatim. **Do not modify or fork the STT server** (spec §4).

````markdown
# STT server contract (verified 2026-08-12)

**Source of truth:** private repo `meredityman/fundusbot`, branch
`win_fundusfantasma-dev-clean`, path `fundusapps/stt_server/`.
Read with `gh api repos/meredityman/fundusbot/contents/fundusapps/stt_server/<file>?ref=win_fundusfantasma-dev-clean --jq .content | base64 -d`.
Verified files: `events.py`, `app.py`, `args.py`,
`backends/elevenlabs_scribe_backend.py`.

**Do NOT fork or modify this server.** The Core is an independent SSE consumer.

## Run

```bash
python -m fundusapps.stt_server elevenlabs-scribe --language de
```

Backend name on the wire: `elevenlabs-scribe` (`BACKEND_NAME` in
`elevenlabs_scribe_backend.py`). API key from the env var named by
`--api-key-env`, default **`ELEVENLABS_API_KEY`**. Other options: `--model`
(default `scribe_v2_realtime`), `--commit-strategy` (`vad` | `manual`, default
`vad`), `--silence-timeout` (default `0.7`). Host/port come from `STT_HOST` /
`STT_PORT` in the server's own `.env`.

## Endpoints

`GET /events` (SSE), `GET /status`, `POST /pause`, `POST /resume`,
`GET /operator`. We use `/events` and `/status` only.

## Wire format

Unnamed SSE messages, one JSON object per event:

```
data: {"recognizer_id": "left", "type": "final", ...}\n\n
```

Between events, `: keep-alive\n\n` comments every 15 s (from `app.py:events()`).

## Event fields (`events.py`, TranscriptionEvent — TEN fields)

| field | type | note |
|---|---|---|
| `recognizer_id` | str | per audio channel |
| `type` | `"partial"` \| `"final"` | we consume `final` only |
| `text` | str | |
| `timestamp` | float | wall clock, epoch seconds |
| `backend` | str | `elevenlabs-scribe` here |
| `status` | str \| null | |
| `confidence` | float \| null | not set by the Scribe backend |
| `turn_id` | str \| null | ULID, stable per utterance |
| `partial_seq` | int \| null | partials only |
| `extending` | bool \| null | **NEW** — see below |

## `extending` — why it exists

ElevenLabs Scribe **revises** partials mid-utterance (unlike the
LocalAgreement-2 whisper path, whose partials are strictly growing prefixes).
Per `on_partial_transcript`, the backend emits two parallel partial streams:
`extending=False` for every distinct live partial (the revisable full text) and
`extending=True` for the confirmed, strictly-growing prefix. `null` means the
backend does not distinguish (legacy vosk / whisper).

`final` events are published by `on_committed_transcript` and leave `extending`
at its default `null`.

**Consequence for us:** we consume `type == "final"` only, so `extending` never
affects our logic — the decoder must merely tolerate the field. Partials go to
the operator display, where revision is fine.

## Utterance boundaries are the provider's, not ours

With the default `--commit-strategy vad`, a `final` is emitted exactly when
ElevenLabs' server VAD sends `committed_transcript`
(`elevenlabs_scribe_backend.py`; its `tick()` is a documented no-op).
**We do not implement silence detection.**

## Optional live re-check on site

```bash
curl -s http://127.0.0.1:5051/status
curl -N -s --max-time 20 http://127.0.0.1:5051/events | head -20
```
````

- [ ] **Step 2: Write the failing tests**

`tests/test_sse.py`:

```python
import json

from kg.sse import SSEDecoder


def test_decodes_one_data_block_per_blank_line():
    decoder = SSEDecoder()
    assert decoder.feed('data: {"type": "final", "text": "hallo"}') is None
    event = decoder.feed("")
    assert event == {"type": "final", "text": "hallo"}


def test_keep_alive_comments_and_blank_lines_are_ignored():
    decoder = SSEDecoder()
    assert decoder.feed(": keep-alive") is None
    assert decoder.feed("") is None
    assert decoder.feed("") is None


def test_multiline_data_is_joined_with_newline():
    decoder = SSEDecoder()
    payload = {"text": "a\nb"}
    line = json.dumps(payload)
    decoder.feed(f"data: {line}")
    assert decoder.feed("") == payload


def test_invalid_json_is_dropped_without_raising():
    decoder = SSEDecoder()
    decoder.feed("data: not json")
    assert decoder.feed("") is None
    # decoder stays usable
    decoder.feed('data: {"ok": true}')
    assert decoder.feed("") == {"ok": True}
```

`tests/test_transcript.py`:

```python
from kg.transcript import TranscriptionEvent, TranscriptLog


def test_event_parsing_is_tolerant_of_missing_and_unknown_fields():
    event = TranscriptionEvent.from_dict(
        {"type": "final", "text": "hallo", "timestamp": 5.0, "something_new": 1}
    )
    assert event.type == "final"
    assert event.text == "hallo"
    assert event.timestamp == 5.0
    assert event.turn_id is None
    assert event.backend == ""
    assert event.extending is None


def test_full_elevenlabs_scribe_event_round_trips():
    """The verified 10-field contract (docs/stt-contract.md)."""
    payload = {
        "recognizer_id": "left",
        "type": "final",
        "text": "Wir bauen zu viel Neues.",
        "timestamp": 1754990000.5,
        "backend": "elevenlabs-scribe",
        "status": None,
        "confidence": None,
        "turn_id": "01K2ABCDEF",
        "partial_seq": None,
        "extending": None,
    }
    event = TranscriptionEvent.from_dict(payload)
    assert event.backend == "elevenlabs-scribe"
    assert event.turn_id == "01K2ABCDEF"
    assert event.extending is None


def test_extending_is_tolerated_but_never_changes_handling():
    """Scribe revises partials; we only ever consume finals (spec 4)."""
    revision = TranscriptionEvent.from_dict(
        {"type": "partial", "text": "Wir bauen", "timestamp": 1.0, "extending": False}
    )
    confirmed = TranscriptionEvent.from_dict(
        {"type": "partial", "text": "Wir bauen", "timestamp": 1.0, "extending": True}
    )
    assert revision.extending is False
    assert confirmed.extending is True


def test_append_and_read_range_filters_to_finals_in_window(tmp_path):
    log = TranscriptLog(tmp_path / "transcript.jsonl")
    log.append(TranscriptionEvent(type="final", text="vor dem Fenster", timestamp=10.0))
    log.append(TranscriptionEvent(type="partial", text="ignoriert", timestamp=25.0))
    log.append(TranscriptionEvent(type="final", text="erster Satz", timestamp=20.0))
    log.append(TranscriptionEvent(type="final", text="zweiter Satz", timestamp=30.0))
    log.append(TranscriptionEvent(type="final", text="danach", timestamp=99.0))

    events = log.read_range(15.0, 40.0)
    assert [e.text for e in events] == ["erster Satz", "zweiter Satz"]
    assert log.text_between(15.0, 40.0) == "erster Satz zweiter Satz"


def test_reads_survive_a_reopened_log(tmp_path):
    path = tmp_path / "transcript.jsonl"
    TranscriptLog(path).append(TranscriptionEvent(type="final", text="a", timestamp=1.0))
    TranscriptLog(path).append(TranscriptionEvent(type="final", text="b", timestamp=2.0))
    assert TranscriptLog(path).text_between(0.0, 10.0) == "a b"
```

`tests/test_stt_client.py`:

```python
import pytest

from kg.stt_client import STTClient
from kg.transcript import TranscriptLog


class FakeStream:
    """Yields SSE lines, then raises to simulate a dropped connection."""

    def __init__(self, batches):
        self.batches = list(batches)
        self.calls = 0

    async def __call__(self, url):
        self.calls += 1
        if not self.batches:
            raise RuntimeError("stt unreachable")
        for line in self.batches.pop(0):
            yield line


async def test_finals_are_logged_and_dispatched(tmp_path):
    log = TranscriptLog(tmp_path / "t.jsonl")
    finals, partials = [], []
    stream = FakeStream(
        [
            [
                # Realistic elevenlabs-scribe shape incl. the 10th field.
                'data: {"type": "partial", "text": "hal", "timestamp": 1.0,'
                ' "backend": "elevenlabs-scribe", "extending": false}',
                "",
                ": keep-alive",
                'data: {"type": "final", "text": "hallo", "timestamp": 2.0,'
                ' "backend": "elevenlabs-scribe", "turn_id": "01K2AB"}',
                "",
            ]
        ]
    )
    client = STTClient(
        url="http://stt",
        log=log,
        on_final=finals.append,
        on_partial=partials.append,
        line_source=stream,
        max_cycles=1,
    )

    await client.run()

    assert [e.text for e in finals] == ["hallo"]
    assert [e.text for e in partials] == ["hal"]
    # Only finals are persisted (spec 4).
    assert log.text_between(0.0, 10.0) == "hallo"


async def test_reconnects_after_a_dropped_stream(tmp_path):
    log = TranscriptLog(tmp_path / "t.jsonl")
    states = []
    stream = FakeStream(
        [
            ['data: {"type": "final", "text": "eins", "timestamp": 1.0}', ""],
            ['data: {"type": "final", "text": "zwei", "timestamp": 2.0}', ""],
        ]
    )
    client = STTClient(
        url="http://stt",
        log=log,
        on_final=lambda e: None,
        line_source=stream,
        on_state=states.append,
        backoff=lambda attempt: 0.0,
        max_cycles=3,
    )

    await client.run()

    assert stream.calls == 3
    # third cycle raised -> disconnected state reported, run() did not raise
    assert states[-1] is False
    assert log.text_between(0.0, 10.0) == "eins zwei"
```

- [ ] **Step 3: Run the tests and confirm they fail**

Run: `uv run pytest tests/test_sse.py tests/test_transcript.py tests/test_stt_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kg.sse'`

- [ ] **Step 4: Implement `kg/sse.py`, `kg/transcript.py`, `kg/stt_client.py`**

`kg/sse.py`:

```python
"""Minimal SSE decoder. Deliberately ours: the contract is tiny and must be testable."""

from __future__ import annotations

import json


class SSEDecoder:
    def __init__(self) -> None:
        self._data: list[str] = []

    def feed(self, line: str) -> dict | None:
        """Feed one line (without trailing newline). Returns an event when complete."""
        if line.startswith(":"):  # keep-alive comment
            return None
        if line == "":
            if not self._data:
                return None
            raw = "\n".join(self._data)
            self._data = []
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None
        if line.startswith("data:"):
            self._data.append(line[5:].lstrip())
        return None
```

`kg/transcript.py`:

```python
"""Local, append-only transcript log. The STT server stays a pure supplier (spec 4)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class TranscriptionEvent:
    """The verified 10-field STT contract — see docs/stt-contract.md."""

    type: str
    text: str
    timestamp: float
    recognizer_id: str = ""
    backend: str = ""
    status: str | None = None
    confidence: float | None = None
    turn_id: str | None = None
    partial_seq: int | None = None
    # elevenlabs-scribe revises partials mid-utterance: True = extends the
    # previous partial, False = revision, None = backend doesn't distinguish
    # (and always None on finals). We consume finals only, so this field is
    # carried, logged and otherwise ignored.
    extending: bool | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "TranscriptionEvent":
        """Tolerant: unknown keys are dropped, missing keys get defaults."""
        return cls(
            type=str(data.get("type", "")),
            text=str(data.get("text", "")),
            timestamp=float(data.get("timestamp", 0.0)),
            recognizer_id=str(data.get("recognizer_id", "")),
            backend=str(data.get("backend", "")),
            status=data.get("status"),
            confidence=data.get("confidence"),
            turn_id=data.get("turn_id"),
            partial_seq=data.get("partial_seq"),
            extending=data.get("extending"),
        )


class TranscriptLog:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: TranscriptionEvent) -> None:
        if event.type != "final":
            return
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")

    def read_range(self, start: float, end: float) -> list[TranscriptionEvent]:
        if not self.path.exists():
            return []
        events: list[TranscriptionEvent] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = TranscriptionEvent.from_dict(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if event.type == "final" and start <= event.timestamp <= end:
                    events.append(event)
        events.sort(key=lambda e: e.timestamp)
        return events

    def text_between(self, start: float, end: float) -> str:
        return " ".join(e.text.strip() for e in self.read_range(start, end) if e.text.strip())
```

`kg/stt_client.py`:

```python
"""Independent SSE consumer for the external STT server. Never modifies it (spec 4)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable

import httpx

from kg.sse import SSEDecoder
from kg.transcript import TranscriptionEvent, TranscriptLog

log = logging.getLogger(__name__)


async def httpx_line_source(url: str) -> AsyncIterator[str]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=None)) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                yield line


class STTClient:
    def __init__(
        self,
        url: str,
        log: TranscriptLog,
        on_final: Callable[[TranscriptionEvent], None],
        on_partial: Callable[[TranscriptionEvent], None] | None = None,
        on_state: Callable[[bool], None] | None = None,
        line_source: Callable[[str], AsyncIterator[str]] = httpx_line_source,
        backoff: Callable[[int], float] = lambda attempt: min(30.0, 2.0**attempt),
        max_cycles: int | None = None,
    ) -> None:
        self.url = url.rstrip("/") + "/events"
        self.log = log
        self.on_final = on_final
        self.on_partial = on_partial or (lambda event: None)
        self.on_state = on_state or (lambda connected: None)
        self.line_source = line_source
        self.backoff = backoff
        self.max_cycles = max_cycles

    async def run(self) -> None:
        """Consume forever, reconnecting with backoff. Never raises on STT failure."""
        attempt = 0
        cycles = 0
        while self.max_cycles is None or cycles < self.max_cycles:
            cycles += 1
            decoder = SSEDecoder()
            try:
                async for line in self.line_source(self.url):
                    payload = decoder.feed(line)
                    if payload is None:
                        continue
                    if attempt or cycles == 1:
                        self.on_state(True)
                        attempt = 0
                    self._dispatch(TranscriptionEvent.from_dict(payload))
            except Exception as exc:  # STT unreachable is a normal on-site state
                log.warning("stt stream failed (%s); reconnecting", exc)
            self.on_state(False)
            attempt += 1
            if self.max_cycles is not None and cycles >= self.max_cycles:
                break  # tests only; live operation never leaves the loop
            await asyncio.sleep(self.backoff(attempt))

    def _dispatch(self, event: TranscriptionEvent) -> None:
        if event.type == "final":
            self.log.append(event)
            self.on_final(event)
        elif event.type == "partial":
            self.on_partial(event)
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_sse.py tests/test_transcript.py tests/test_stt_client.py -v`
Expected: PASS (11 tests)

- [ ] **Step 6: Commit**

```bash
git add docs/stt-contract.md kg/sse.py kg/transcript.py kg/stt_client.py tests/test_sse.py tests/test_transcript.py tests/test_stt_client.py
git commit -m "feat: STT SSE consumer, transcript log, verified contract"
```

---

### Task 4: Stop-command matching and stripping

**Files:**
- Create: `kg/segmentation.py`
- Test: `tests/test_segmentation.py`

**Interfaces:**
- Consumes: `Config.stop_phrases` (Task 1).
- Produces:
  - `kg.segmentation.normalize(text: str) -> str`
  - `kg.segmentation.find_stop_phrase(text: str, phrases: Sequence[str]) -> str | None` (returns the matched configured phrase)
  - `kg.segmentation.strip_stop_phrases(text: str, phrases: Sequence[str]) -> str` — **must run before extraction** so the LLM cannot derive a term from the command (spec §5).

Matching is case-insensitive, punctuation-insensitive, umlaut-folding, and tolerant of the common STT `t`/`d` ending confusion („beended" ↔ „beendet").

- [ ] **Step 1: Write the failing test**

`tests/test_segmentation.py`:

```python
import unicodedata

import pytest

from kg.segmentation import find_stop_phrase, normalize, strip_stop_phrases

PHRASES = ["Interview beendet", "Aufnahme beenden"]


def test_normalize_folds_case_punctuation_and_umlauts():
    assert normalize("Aufnahme, BEENDEN!") == "aufnahme beenden"
    assert normalize("Größe  Übung") == "groesse uebung"


@pytest.mark.parametrize(
    "text",
    [
        "So, das Interview beendet.",
        "das interview beended",
        "Okay – INTERVIEW BEENDET!",
        "vielen dank, aufnahme beenden",
    ],
)
def test_matching_is_tolerant(text):
    assert find_stop_phrase(text, PHRASES) is not None


@pytest.mark.parametrize(
    "text",
    [
        "Danke, das war es.",
        "Ich bin fertig.",
        "Das Interview war interessant.",
        "",
    ],
)
def test_ordinary_speech_does_not_trigger(text):
    assert find_stop_phrase(text, PHRASES) is None


def test_returns_the_configured_phrase_that_matched():
    assert find_stop_phrase("bitte Aufnahme beenden", PHRASES) == "Aufnahme beenden"


def test_strip_removes_the_command_and_keeps_the_rest():
    text = "Beton ist wichtig. So, das Interview beendet. Tschüss."
    stripped = strip_stop_phrases(text, PHRASES)
    assert "Interview beendet" not in stripped
    assert "Beton ist wichtig." in stripped
    assert "Tschüss." in stripped


def test_strip_handles_the_variant_spelling_too():
    assert "beended" not in strip_stop_phrases("ja das interview beended ok", PHRASES)


def test_strip_is_a_no_op_without_a_match():
    text = "Wir brauchen mehr Genossenschaften."
    assert strip_stop_phrases(text, PHRASES) == text


def test_inflected_word_containing_a_phrase_does_not_trigger():
    text = "Die Aufnahme beendende Handlung war klar."
    assert find_stop_phrase(text, PHRASES) is None
    assert strip_stop_phrases(text, PHRASES) == text


def test_unlisted_punctuation_inside_the_command_is_stripped():
    text = "Bitte Aufnahme… beenden jetzt."
    assert find_stop_phrase(text, PHRASES) == "Aufnahme beenden"
    stripped = strip_stop_phrases(text, PHRASES)
    assert "Aufnahme" not in stripped
    assert "beenden" not in stripped
    assert "…" not in stripped
    assert "Bitte" in stripped
    assert "jetzt" in stripped


def test_nfd_normalized_stop_phrases_match_correctly():
    """Regression: stop phrases in NFD form must be normalized to NFC before tokenizing."""
    nfd_phrase = unicodedata.normalize("NFD", "Größe beenden")
    nfc_phrase = "Größe beenden"
    text = "Bitte Größe beenden jetzt."

    # NFD phrase must match despite its Unicode form
    assert find_stop_phrase(text, [nfd_phrase]) == nfd_phrase

    # Strip must work with NFD phrase
    stripped = strip_stop_phrases(text, [nfd_phrase])
    assert "Größe" not in stripped
    assert "beenden" not in stripped
    assert "Bitte" in stripped
    assert "jetzt" in stripped

    # Verify both forms produce identical results
    assert find_stop_phrase(text, [nfd_phrase]) == nfd_phrase
    assert find_stop_phrase(text, [nfc_phrase]) == nfc_phrase
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_segmentation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kg.segmentation'`

- [ ] **Step 3: Implement `kg/segmentation.py`**

```python
"""Spoken stop-command detection.

Cheap by construction: a string match on text we already receive (spec 5).
No wake-word engine, no extra model, no extra latency.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

_UMLAUTS = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
_PUNCT = re.compile(r"[^\w\s]", flags=re.UNICODE)
_SPACES = re.compile(r"\s+")
# STT delivers "beended" as well as "beendet": fold a word-final d onto t.
_FINAL_D = re.compile(r"d\b")
_WORD = re.compile(r"\w+", re.UNICODE)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    for source, target in _UMLAUTS.items():
        text = text.replace(source, target)
    text = _PUNCT.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def _fuzzy(text: str) -> str:
    return _FINAL_D.sub("t", normalize(text))


@dataclass(frozen=True)
class _Token:
    normalized: str
    start: int
    end: int


def _tokenize(text: str) -> tuple[str, list[_Token]]:
    """Tokenise once over NFC text; each raw \\w+ run corresponds 1:1 to a
    normalised token, since normalize() maps every [^\\w\\s] char to a space.
    """
    nfc_text = unicodedata.normalize("NFC", text)
    tokens = [
        _Token(normalized=_fuzzy(match.group()), start=match.start(), end=match.end())
        for match in _WORD.finditer(nfc_text)
    ]
    return nfc_text, tokens


def _phrase_tokens(phrase: str) -> list[str]:
    nfc_phrase = unicodedata.normalize("NFC", phrase)
    return [_fuzzy(word) for word in _WORD.findall(nfc_phrase)]


def _find_sublist_occurrences(
    needle: list[str], haystack: list[_Token]
) -> list[tuple[int, int]]:
    """Return raw (start, end) spans in the NFC text for every contiguous,
    whole-token occurrence of needle in haystack.
    """
    if not needle:
        return []
    spans = []
    n = len(needle)
    for i in range(len(haystack) - n + 1):
        if all(haystack[i + j].normalized == needle[j] for j in range(n)):
            spans.append((haystack[i].start, haystack[i + n - 1].end))
    return spans


def find_stop_phrase(text: str, phrases: Sequence[str]) -> str | None:
    _, tokens = _tokenize(text)
    if not tokens:
        return None
    for phrase in phrases:
        needle = _phrase_tokens(phrase)
        if needle and _find_sublist_occurrences(needle, tokens):
            return phrase
    return None


def strip_stop_phrases(text: str, phrases: Sequence[str]) -> str:
    """Remove every occurrence of a stop phrase. MUST run before extraction (spec 5)."""
    nfc_text, tokens = _tokenize(text)
    spans: list[tuple[int, int]] = []
    for phrase in phrases:
        needle = _phrase_tokens(phrase)
        if not needle:
            continue
        spans.extend(_find_sublist_occurrences(needle, tokens))

    if not spans:
        return _SPACES.sub(" ", nfc_text).strip()

    spans.sort()
    merged: list[list[int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    pieces = []
    cursor = 0
    for start, end in merged:
        pieces.append(nfc_text[cursor:start])
        pieces.append(" ")
        cursor = end
    pieces.append(nfc_text[cursor:])
    result = "".join(pieces)
    return _SPACES.sub(" ", result).strip()
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_segmentation.py -v`
Expected: PASS (16 tests)

- [ ] **Step 5: Commit**

```bash
git add kg/segmentation.py tests/test_segmentation.py
git commit -m "feat: tolerant spoken stop-command matching and stripping"
```

---

### Task 5: Interview state machine

**Files:**
- Create: `kg/session.py`
- Test: `tests/test_session.py`

**Interfaces:**
- Consumes: `kg.segmentation.find_stop_phrase` (Task 4), `Config.interview_timeout_s`, `Config.stop_phrases` (Task 1).
- Produces:
  - `kg.session.Transition(kind: str, at: float, reason: str)` — `kind` is `"opened"` or `"closed"`; `reason` is `"photo"` for opens and one of `"text" | "spoken" | "timeout" | "new_photo"` for closes.
  - `kg.session.SessionTracker(timeout_s, stop_phrases)` with `photo(at)`, `text_message(at)`, `transcript(text, at)`, `tick(now)`, each returning `list[Transition]`, plus the property `open_since: float | None`.

`SessionTracker` is pure — no store, no clock, no I/O — so every lifecycle rule from spec §5 is unit-testable. Task 11 executes the transitions.

- [ ] **Step 1: Write the failing test**

`tests/test_session.py`:

```python
from kg.session import SessionTracker, Transition

PHRASES = ["Interview beendet"]


def tracker():
    return SessionTracker(timeout_s=900, stop_phrases=PHRASES)


def test_photo_opens_an_interview():
    t = tracker()
    assert t.photo(at=100.0) == [Transition("opened", 100.0, "photo")]
    assert t.open_since == 100.0


def test_any_text_message_stops_it():
    t = tracker()
    t.photo(at=100.0)
    assert t.text_message(at=160.0) == [Transition("closed", 160.0, "text")]
    assert t.open_since is None


def test_spoken_command_in_the_transcript_stops_it():
    t = tracker()
    t.photo(at=100.0)
    assert t.transcript("okay, Interview beendet", at=200.0) == [
        Transition("closed", 200.0, "spoken")
    ]


def test_ordinary_transcript_does_not_stop_it():
    t = tracker()
    t.photo(at=100.0)
    assert t.transcript("wir brauchen mehr Holzbau", at=150.0) == []
    assert t.open_since == 100.0


def test_timeout_closes_a_forgotten_interview():
    t = tracker()
    t.photo(at=100.0)
    assert t.tick(now=999.0) == []
    assert t.tick(now=1000.0) == [Transition("closed", 1000.0, "timeout")]
    assert t.open_since is None


def test_a_new_photo_implicitly_closes_the_running_interview():
    t = tracker()
    t.photo(at=100.0)
    assert t.photo(at=400.0) == [
        Transition("closed", 400.0, "new_photo"),
        Transition("opened", 400.0, "photo"),
    ]
    assert t.open_since == 400.0


def test_stop_signals_without_an_open_interview_are_ignored():
    t = tracker()
    assert t.text_message(at=10.0) == []
    assert t.transcript("Interview beendet", at=11.0) == []
    assert t.tick(now=99999.0) == []


def test_only_one_interview_can_be_open_at_a_time():
    t = tracker()
    t.photo(at=100.0)
    t.photo(at=200.0)
    t.photo(at=300.0)
    assert t.open_since == 300.0
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_session.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kg.session'`

- [ ] **Step 3: Implement `kg/session.py`**

```python
"""Interview lifecycle (spec 5). Pure state machine: no store, no clock, no I/O.

One microphone means exactly one interview can be open at a time. Every path
out of "open" is forgiving: a text message, a spoken command, the safety
timeout, or the next photo. It can never leave two interviews open.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from kg.segmentation import find_stop_phrase


@dataclass(frozen=True)
class Transition:
    kind: str  # "opened" | "closed"
    at: float
    reason: str  # opened: "photo"; closed: "text" | "spoken" | "timeout" | "new_photo"


class SessionTracker:
    def __init__(self, timeout_s: float, stop_phrases: Sequence[str]) -> None:
        self.timeout_s = float(timeout_s)
        self.stop_phrases = list(stop_phrases)
        self._open_since: float | None = None

    @property
    def open_since(self) -> float | None:
        return self._open_since

    def photo(self, at: float) -> list[Transition]:
        transitions: list[Transition] = []
        if self._open_since is not None:
            transitions.append(Transition("closed", at, "new_photo"))
        self._open_since = at
        transitions.append(Transition("opened", at, "photo"))
        return transitions

    def text_message(self, at: float) -> list[Transition]:
        return self._close(at, "text")

    def transcript(self, text: str, at: float) -> list[Transition]:
        if self._open_since is None:
            return []
        if find_stop_phrase(text, self.stop_phrases) is None:
            return []
        return self._close(at, "spoken")

    def tick(self, now: float) -> list[Transition]:
        if self._open_since is None or now - self._open_since < self.timeout_s:
            return []
        return self._close(now, "timeout")

    def _close(self, at: float, reason: str) -> list[Transition]:
        if self._open_since is None:
            return []
        self._open_since = None
        return [Transition("closed", at, reason)]
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_session.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add kg/session.py tests/test_session.py
git commit -m "feat: interview lifecycle state machine"
```

---

### Task 6: Portrait normalisation

**Files:**
- Create: `kg/photos.py`
- Test: `tests/test_photos.py`

**Interfaces:**
- Consumes: `Config.portrait_size` (Task 1).
- Produces: `kg.photos.make_portrait(src: Path, dest: Path, size: int = 512) -> Path` — writes a square, circle-masked RGBA PNG of exactly `size × size`.

Arbitrary phone resolution in, normalised out (spec §10.2). The crop is centred horizontally and biased upward vertically, because portraits from a photo booth put the face above centre.

- [ ] **Step 1: Write the failing test**

`tests/test_photos.py`:

```python
from PIL import Image

from kg.photos import make_portrait


def _write_source(path, width, height, colour=(200, 30, 30)):
    Image.new("RGB", (width, height), colour).save(path)
    return path


def test_output_is_a_square_rgba_png_of_the_requested_size(tmp_path):
    src = _write_source(tmp_path / "in.jpg", 4032, 3024)
    dest = tmp_path / "out.png"

    result = make_portrait(src, dest, size=256)

    assert result == dest
    with Image.open(dest) as img:
        assert img.size == (256, 256)
        assert img.mode == "RGBA"
        assert img.format == "PNG"


def test_the_mask_is_circular(tmp_path):
    src = _write_source(tmp_path / "in.jpg", 1000, 1000)
    dest = tmp_path / "out.png"

    make_portrait(src, dest, size=256)

    with Image.open(dest) as img:
        assert img.getpixel((128, 128))[3] == 255  # centre opaque
        assert img.getpixel((0, 0))[3] == 0  # corner transparent
        assert img.getpixel((255, 255))[3] == 0


def test_portrait_orientation_crops_from_the_upper_part(tmp_path):
    # Top half red, bottom half blue: an upward-biased square crop keeps mostly red.
    src = tmp_path / "in.jpg"
    img = Image.new("RGB", (600, 1200), (255, 0, 0))
    img.paste(Image.new("RGB", (600, 600), (0, 0, 255)), (0, 600))
    img.save(src)
    dest = tmp_path / "out.png"

    make_portrait(src, dest, size=256)

    with Image.open(dest) as out:
        r, g, b, _ = out.getpixel((128, 128))
        assert r > b


def test_landscape_input_is_centre_cropped(tmp_path):
    src = _write_source(tmp_path / "in.jpg", 1600, 900)
    dest = tmp_path / "out.png"

    make_portrait(src, dest, size=128)

    with Image.open(dest) as out:
        assert out.size == (128, 128)
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_photos.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kg.photos'`

- [ ] **Step 3: Implement `kg/photos.py`**

```python
"""Portrait normalisation: arbitrary phone resolution in, uniform circle out (spec 10.2)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

# Faces sit above the vertical centre in booth portraits.
VERTICAL_BIAS = 0.35


def make_portrait(src: Path, dest: Path, size: int = 512) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(src) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGB")
        square = _square_crop(image)
        square = square.resize((size, size), Image.LANCZOS)

    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    mask = mask.resize((size, size), Image.LANCZOS)

    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(square, (0, 0), mask)
    out.save(dest, format="PNG")
    return dest


def _square_crop(image: Image.Image) -> Image.Image:
    width, height = image.size
    side = min(width, height)
    left = (width - side) // 2
    if height > side:
        top = int((height - side) * VERTICAL_BIAS)
    else:
        top = 0
    return image.crop((left, top, left + side, top + side))
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_photos.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add kg/photos.py tests/test_photos.py
git commit -m "feat: portrait normalisation (square crop + circle mask)"
```

---

### Task 7: Telegram source (photo trigger + text stop)

**Files:**
- Create: `kg/telegram_bot.py`
- Test: `tests/test_telegram_bot.py`

**Interfaces:**
- Consumes: `kg.photos.make_portrait` (Task 6), `Config.telegram_token`, `Config.telegram_chat_id`, `Config.photo_dir`, `Config.portrait_dir`, `Config.portrait_size` (Task 1).
- Produces: `kg.telegram_bot.TelegramSource(token, chat_id, photo_dir, portrait_dir, portrait_size, on_photo, on_text, downloader)` with:
  - `async def dispatch(self, update: dict) -> None` — pure-ish; drives the whole decision from a raw Telegram update dict, so it is fully testable without a network.
  - `def build_application(self)` — wires python-telegram-bot to `dispatch`.
  - Callback signatures: `on_photo(photo_path: Path, portrait_path: Path, at: float)`, `on_text(text: str, at: float)`.

Telegram carries **only** the photo and the control commands — never audio (spec §5).

- [ ] **Step 1: Write the failing test**

`tests/test_telegram_bot.py`:

```python
from pathlib import Path

from PIL import Image

from kg.telegram_bot import TelegramSource


def make_source(tmp_path, chat_id=None, photos=None, texts=None):
    def downloader(file_id: str, dest: Path) -> None:
        Image.new("RGB", (800, 1000), (10, 120, 200)).save(dest)

    return TelegramSource(
        token="123:abc",
        chat_id=chat_id,
        photo_dir=tmp_path / "photos",
        portrait_dir=tmp_path / "portraits",
        portrait_size=64,
        on_photo=lambda photo, portrait, at: photos.append((photo, portrait, at)),
        on_text=lambda text, at: texts.append((text, at)),
        downloader=downloader,
    )


def photo_update(file_id="F1", date=1700.0, chat_id=42):
    return {
        "update_id": 1,
        "message": {
            "message_id": 7,
            "date": date,
            "chat": {"id": chat_id},
            "photo": [
                {"file_id": "small", "width": 90, "height": 120},
                {"file_id": file_id, "width": 800, "height": 1000},
            ],
        },
    }


def text_update(text="stop", date=1800.0, chat_id=42):
    return {
        "update_id": 2,
        "message": {"message_id": 8, "date": date, "chat": {"id": chat_id}, "text": text},
    }


async def test_photo_downloads_the_largest_size_and_normalises_it(tmp_path):
    photos, texts = [], []
    source = make_source(tmp_path, photos=photos, texts=texts)

    await source.dispatch(photo_update())

    assert len(photos) == 1
    photo_path, portrait_path, at = photos[0]
    assert at == 1700.0
    assert photo_path.exists() and portrait_path.exists()
    with Image.open(portrait_path) as img:
        assert img.size == (64, 64)
        assert img.mode == "RGBA"
    assert texts == []


async def test_any_text_message_is_a_stop_signal(tmp_path):
    photos, texts = [], []
    source = make_source(tmp_path, photos=photos, texts=texts)

    await source.dispatch(text_update(text="fertig", date=1900.0))

    assert texts == [("fertig", 1900.0)]
    assert photos == []


async def test_other_chats_are_ignored_when_a_chat_id_is_configured(tmp_path):
    photos, texts = [], []
    source = make_source(tmp_path, chat_id=42, photos=photos, texts=texts)

    await source.dispatch(photo_update(chat_id=999))
    await source.dispatch(text_update(chat_id=999))

    assert photos == [] and texts == []


async def test_updates_without_a_message_are_ignored(tmp_path):
    photos, texts = [], []
    source = make_source(tmp_path, photos=photos, texts=texts)

    await source.dispatch({"update_id": 3})
    await source.dispatch({"update_id": 4, "message": {"date": 1.0, "chat": {"id": 42}}})

    assert photos == [] and texts == []


async def test_a_failed_download_does_not_raise(tmp_path):
    photos, texts = [], []

    def broken(file_id, dest):
        raise OSError("telegram offline")

    source = TelegramSource(
        token="123:abc",
        chat_id=None,
        photo_dir=tmp_path / "photos",
        portrait_dir=tmp_path / "portraits",
        portrait_size=64,
        on_photo=lambda photo, portrait, at: photos.append(photo),
        on_text=lambda text, at: texts.append(text),
        downloader=broken,
    )

    await source.dispatch(photo_update())

    assert photos == []
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_telegram_bot.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kg.telegram_bot'`

- [ ] **Step 3: Implement `kg/telegram_bot.py`**

```python
"""Slim Telegram poller: photos start an interview, any text stops it (spec 5).

This is NOT the Hermes gateway. It carries no audio and holds no state.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

from kg.photos import make_portrait

log = logging.getLogger(__name__)


class TelegramSource:
    def __init__(
        self,
        token: str,
        chat_id: int | None,
        photo_dir: Path,
        portrait_dir: Path,
        portrait_size: int,
        on_photo: Callable[[Path, Path, float], None],
        on_text: Callable[[str, float], None],
        downloader: Callable[[str, Path], None] | None = None,
    ) -> None:
        self.token = token
        self.chat_id = chat_id
        self.photo_dir = Path(photo_dir)
        self.portrait_dir = Path(portrait_dir)
        self.portrait_size = portrait_size
        self.on_photo = on_photo
        self.on_text = on_text
        self.downloader = downloader or self._download_via_bot
        self._bot = None
        self.photo_dir.mkdir(parents=True, exist_ok=True)
        self.portrait_dir.mkdir(parents=True, exist_ok=True)

    async def dispatch(self, update: dict) -> None:
        message = update.get("message") or update.get("channel_post")
        if not isinstance(message, dict):
            return
        if self.chat_id is not None and message.get("chat", {}).get("id") != self.chat_id:
            return

        at = float(message.get("date", 0.0))
        photos = message.get("photo") or []
        if photos:
            await self._handle_photo(photos, message.get("message_id", 0), at)
            return

        text = message.get("text")
        if isinstance(text, str) and text.strip():
            self.on_text(text.strip(), at)

    async def _handle_photo(self, photos: list[dict], message_id: int, at: float) -> None:
        largest = max(photos, key=lambda p: p.get("width", 0) * p.get("height", 0))
        photo_path = self.photo_dir / f"{int(at)}_{message_id}.jpg"
        portrait_path = self.portrait_dir / f"{int(at)}_{message_id}.png"
        try:
            await asyncio.to_thread(self.downloader, largest["file_id"], photo_path)
            await asyncio.to_thread(
                make_portrait, photo_path, portrait_path, self.portrait_size
            )
        except Exception as exc:  # Telegram offline / broken image: stay alive
            log.warning("photo handling failed (%s)", exc)
            return
        self.on_photo(photo_path, portrait_path, at)

    def _download_via_bot(self, file_id: str, dest: Path) -> None:
        from telegram import Bot  # imported lazily so tests need no network stack

        async def _run() -> None:
            bot = Bot(self.token)
            file = await bot.get_file(file_id)
            await file.download_to_drive(custom_path=str(dest))

        asyncio.run(_run())

    def build_application(self):
        """Wire python-telegram-bot to dispatch(). Called only by kg.core."""
        from telegram.ext import Application, MessageHandler, filters

        application = Application.builder().token(self.token).build()

        async def handler(update, context) -> None:
            await self.dispatch(update.to_dict())

        application.add_handler(MessageHandler(filters.ALL, handler))
        return application
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_telegram_bot.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add kg/telegram_bot.py tests/test_telegram_bot.py
git commit -m "feat: telegram photo trigger and text stop"
```

---

### Task 8: LLM client and extraction

**Files:**
- Create: `kg/llm.py`, `kg/extraction.py`
- Test: `tests/test_llm.py`, `tests/test_extraction.py`

**Interfaces:**
- Consumes: `Config.llm_model`, `Config.llm_effort`, `Config.llm_max_tokens`, `Config.terms_per_interview`, `Config.anthropic_api_key` (Task 1).
- Produces:
  - `kg.llm.LLMError` (raised after retries are exhausted or validation fails).
  - `kg.llm.strict_schema(model: type[BaseModel]) -> dict` — Pydantic JSON schema hardened for structured outputs (`additionalProperties: false`, every property required, on every object including `$defs`).
  - `kg.llm.LLMClient(model, effort, max_tokens, api_key=None, client=None, max_attempts=2)` with `parse(system: str, user: str, output_model: type[T]) -> T`.
  - `kg.extraction.ExtractionResult(interview_end_index: int, terms: list[ExtractedTerm], quotes: list[ExtractedQuote])`, `ExtractedTerm(label, evidence)`, `ExtractedQuote(text)`.
  - `kg.extraction.extract(llm, transcript, max_terms) -> ExtractionResult` and `kg.extraction.EXTRACTION_SYSTEM`.

The end-of-interview detection and the extraction share **one** call (spec §6.1 steps 2–3; §6.2 counts one extraction call plus one merge call per interview). The prompt optimises for concreteness, not frequency, with the briefing's good/bad examples verbatim (spec §6.3).

- [ ] **Step 1: Write the failing tests**

`tests/test_llm.py`:

```python
import json

import pytest
from pydantic import BaseModel

from kg.llm import LLMClient, LLMError, strict_schema


class Inner(BaseModel):
    label: str


class Outer(BaseModel):
    count: int
    items: list[Inner]


def test_strict_schema_hardens_every_object_including_defs():
    schema = strict_schema(Outer)

    assert schema["additionalProperties"] is False
    assert sorted(schema["required"]) == ["count", "items"]
    inner = schema["$defs"]["Inner"]
    assert inner["additionalProperties"] is False
    assert inner["required"] == ["label"]


class FakeMessages:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply

        class Block:
            type = "text"
            text = reply

        class Response:
            stop_reason = "end_turn"
            content = [Block()]

        return Response()


class FakeAnthropic:
    def __init__(self, replies):
        self.messages = FakeMessages(replies)


def test_parse_returns_a_validated_model_and_sends_the_documented_parameters():
    fake = FakeAnthropic([json.dumps({"count": 2, "items": [{"label": "a"}]})])
    client = LLMClient(model="claude-opus-5", effort="high", max_tokens=16000, client=fake)

    result = client.parse(system="S", user="U", output_model=Outer)

    assert result.count == 2 and result.items[0].label == "a"
    call = fake.messages.calls[0]
    assert call["model"] == "claude-opus-5"
    assert call["output_config"]["effort"] == "high"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["system"] == "S"
    assert "thinking" not in call
    assert "temperature" not in call


def test_invalid_json_is_retried_once_then_raises():
    fake = FakeAnthropic(["not json", "still not json"])
    client = LLMClient(
        model="claude-opus-5", effort="high", max_tokens=16000, client=fake, max_attempts=2
    )

    with pytest.raises(LLMError):
        client.parse(system="S", user="U", output_model=Outer)
    assert len(fake.messages.calls) == 2


def test_a_retry_can_succeed():
    fake = FakeAnthropic(["broken", json.dumps({"count": 1, "items": []})])
    client = LLMClient(
        model="claude-opus-5", effort="high", max_tokens=16000, client=fake, max_attempts=2
    )

    assert client.parse(system="S", user="U", output_model=Outer).count == 1


def test_a_refusal_raises_llm_error():
    class RefusingMessages:
        def create(self, **kwargs):
            class Response:
                stop_reason = "refusal"
                content = []

            return Response()

    class RefusingClient:
        messages = RefusingMessages()

    client = LLMClient(
        model="claude-opus-5", effort="high", max_tokens=16000, client=RefusingClient(), max_attempts=1
    )

    with pytest.raises(LLMError):
        client.parse(system="S", user="U", output_model=Outer)
```

`tests/test_extraction.py`:

```python
from kg.extraction import EXTRACTION_SYSTEM, ExtractionResult, build_extraction_prompt, extract


class FakeLLM:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def parse(self, system, user, output_model):
        self.calls.append((system, user, output_model))
        return self.result


def test_the_prompt_carries_the_concreteness_examples_verbatim():
    assert "Betonspritzen mit Drohnen" in EXTRACTION_SYSTEM
    assert "Nachhaltigkeit" in EXTRACTION_SYSTEM
    # The five real guiding questions, so the right text genre is targeted.
    assert "in 20 Jahren" in EXTRACTION_SYSTEM
    assert "Eine KI plant Ihr nächstes Zuhause" in EXTRACTION_SYSTEM


def test_the_user_prompt_states_the_hard_cap_and_carries_the_transcript():
    prompt = build_extraction_prompt("Beton ist wichtig.", max_terms=5)
    assert "5" in prompt
    assert "Beton ist wichtig." in prompt


def test_extract_truncates_the_term_list_to_the_configured_cap():
    result = ExtractionResult(
        interview_end_index=10,
        terms=[{"label": f"t{i}", "evidence": "e"} for i in range(9)],
        quotes=[{"text": "z"}],
    )
    llm = FakeLLM(result)

    out = extract(llm, "irgendein transkript", max_terms=3)

    assert len(out.terms) == 3
    assert llm.calls[0][2] is ExtractionResult


def test_extract_clamps_the_end_index_into_the_transcript():
    transcript = "kurz"
    llm = FakeLLM(ExtractionResult(interview_end_index=9999, terms=[], quotes=[]))
    assert extract(llm, transcript, max_terms=5).interview_end_index == len(transcript)

    llm = FakeLLM(ExtractionResult(interview_end_index=-5, terms=[], quotes=[]))
    assert extract(llm, transcript, max_terms=5).interview_end_index == 0
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `uv run pytest tests/test_llm.py tests/test_extraction.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kg.llm'`

- [ ] **Step 3: Implement `kg/llm.py`**

```python
"""Anthropic wrapper. Deterministic pipeline step, not an agent (spec 2)."""

from __future__ import annotations

import json
import logging
from typing import TypeVar

from pydantic import BaseModel

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """The model failed, refused, or returned something that is not our schema."""


def strict_schema(model: type[BaseModel]) -> dict:
    """Pydantic schema hardened for structured outputs.

    Structured outputs require additionalProperties: false and an explicit
    `required` list on every object, including nested $defs.
    """
    schema = model.model_json_schema()

    def harden(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            for value in node.values():
                harden(value)
        elif isinstance(node, list):
            for item in node:
                harden(item)

    harden(schema)
    return schema


class LLMClient:
    def __init__(
        self,
        model: str,
        effort: str,
        max_tokens: int,
        api_key: str | None = None,
        client=None,
        max_attempts: int = 2,
    ) -> None:
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.max_attempts = max_attempts
        if client is not None:
            self._client = client
        else:
            import anthropic

            self._client = (
                anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
            )

    def parse(self, system: str, user: str, output_model: type[T]) -> T:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self._client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=system,
                    output_config={
                        "effort": self.effort,
                        "format": {
                            "type": "json_schema",
                            "schema": strict_schema(output_model),
                        },
                    },
                    messages=[{"role": "user", "content": user}],
                )
                if getattr(response, "stop_reason", None) == "refusal":
                    raise LLMError("model refused the request")
                text = next(
                    (b.text for b in response.content if getattr(b, "type", "") == "text"), ""
                )
                return output_model.model_validate(json.loads(text))
            except Exception as exc:  # JSONDecodeError, ValidationError, API errors, refusals
                last_error = exc
                log.warning("llm attempt %s/%s failed: %s", attempt, self.max_attempts, exc)
        raise LLMError(f"llm call failed after {self.max_attempts} attempts: {last_error}")
```

- [ ] **Step 4: Implement `kg/extraction.py`**

```python
"""Extraction: find the real end of the interview, then condense it (spec 6.1, 6.3)."""

from __future__ import annotations

from pydantic import BaseModel

# The five real guiding questions from the briefing. Single source of truth:
# the simulation corpus generator (sim/generate_interviews.py) imports these,
# so the test corpus can never drift away from the extraction prompt (spec 9).
GUIDING_QUESTIONS = [
    "Wenn Sie an das Haus oder die Stadt denken, in der Sie in 20 Jahren leben "
    "wollen — was wäre das Erste, das anders sein sollte als heute?",
    "Eine KI plant Ihr nächstes Zuhause — bis wohin vertrauen Sie ihr? Wo wollen "
    "Sie unbedingt einen Menschen entscheiden lassen?",
    "Braucht das Bauen einen radikalen Bruch mit dem System — oder reicht es, das "
    "Bestehende klüger zu reparieren?",
    "Wer sollte entscheiden, wie Ihr Ort/Ihre Stadt sich verändert — und fühlen "
    "Sie sich dabei gehört?",
    "Worauf würden Sie beim Bauen verzichten, damit für die Natur mehr übrig "
    "bleibt? Gibt es etwas, auf das Sie niemals verzichten möchten?",
]

_QUESTION_BLOCK = "\n".join(
    f"{number}. {question}" for number, question in enumerate(GUIDING_QUESTIONS, start=1)
)

EXTRACTION_SYSTEM = f"""\
Du verdichtest das Transkript eines gesprochenen Interviews auf einer \
Architektur- und Baukultur-Konferenz (Festival NEW bauhaus 2026) zu wenigen, \
sehr konkreten Begriffen.

Den Personen wurden diese fünf Leitfragen gestellt:
{_QUESTION_BLOCK}

Das Transkript kommt aus automatischer Spracherkennung: Füllwörter, \
abgebrochene Sätze, Wiederholungen, Hörfehler. Es reicht absichtlich über das \
Ende des Interviews hinaus — dort stehen Smalltalk, Verabschiedungen, Stimmen \
der nächsten Person oder Raumgeräusch.

Deine drei Aufgaben:

1. ENDE FINDEN. Bestimme `interview_end_index`: den Zeichen-Index im Transkript, \
an dem das Interview inhaltlich endet. Alles danach ignorierst du vollständig. \
Läuft das Interview bis zum Schluss, gib die Länge des Transkripts an.

2. BEGRIFFE. Nur aus dem Text VOR `interview_end_index`. Optimiere auf \
KONKRETHEIT, nicht auf Häufigkeit.
   Gut (konkret, bildhaft, überraschend): „Betonspritzen mit Drohnen", \
„Genossenschaftliches Wohnen", „Recycling-Beton", „Ländlicher Leerstand", \
„Ko-Kreation mit KI", „Modulares Bauen".
   Schlecht (nichtssagend, verbindet alles mit allem): „Nachhaltigkeit", \
„Zukunft", „Digitalisierung", „Veränderung", „Technologie", „Innovation".
   Regeln: deutsche Substantivphrase, 1–4 Wörter, ohne Artikel, keine ganzen \
Sätze, keine Personennamen, keine Firmennamen. Lieber weniger Begriffe als \
schwache Begriffe. `evidence` ist die kurze Textstelle, auf die sich der \
Begriff stützt.

3. ZITATE. Ein bis zwei wörtliche Zitate der Person, je höchstens 200 Zeichen, \
sprachlich geglättet (Füllwörter raus), inhaltlich unverändert.

Antworte ausschließlich im geforderten JSON-Schema.
"""


class ExtractedTerm(BaseModel):
    label: str
    evidence: str


class ExtractedQuote(BaseModel):
    text: str


class ExtractionResult(BaseModel):
    interview_end_index: int
    terms: list[ExtractedTerm]
    quotes: list[ExtractedQuote]


def build_extraction_prompt(transcript: str, max_terms: int) -> str:
    return (
        f"Höchstens {max_terms} Begriffe. Zeichenlänge des Transkripts: "
        f"{len(transcript)}.\n\n"
        f"--- TRANSKRIPT ---\n{transcript}\n--- ENDE TRANSKRIPT ---"
    )


def extract(llm, transcript: str, max_terms: int) -> ExtractionResult:
    result = llm.parse(
        system=EXTRACTION_SYSTEM,
        user=build_extraction_prompt(transcript, max_terms),
        output_model=ExtractionResult,
    )
    end = max(0, min(int(result.interview_end_index), len(transcript)))
    # The cap is enforced here too: graph density must not depend on the model's mood.
    return ExtractionResult(
        interview_end_index=end,
        terms=list(result.terms)[:max_terms],
        quotes=list(result.quotes),
    )
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_llm.py tests/test_extraction.py -v`
Expected: PASS (9 tests)

- [ ] **Step 6: Commit**

```bash
git add kg/llm.py kg/extraction.py tests/test_llm.py tests/test_extraction.py
git commit -m "feat: LLM client with strict schemas and interview extraction"
```

---

### Task 9: Embeddings and merging (embedding filter + LLM judge)

**Files:**
- Create: `kg/embeddings.py`, `kg/merging.py`
- Test: `tests/test_embeddings.py`, `tests/test_merging.py`

**Interfaces:**
- Consumes: `kg.store.Store` (Task 2), `kg.llm.LLMClient` (Task 8), `Config.merge_neighbours`, `Config.merge_style`, `Config.embedding_model`, `Config.embedding_url`, `Config.openrouter_api_key`, `Config.embedding_cache_path` (Task 1).
- Produces:
  - `kg.embeddings.Embedder` protocol with `embed(texts: Sequence[str]) -> list[list[float]]`.
  - `kg.embeddings.HashEmbedder` — deterministic, dependency-free; used by tests and by the simulation's frozen mode.
  - `kg.embeddings.OpenRouterEmbedder(model, api_key, url, post=...)` — OpenAI-compatible `POST /api/v1/embeddings` over httpx, injectable transport for tests (spec §6.2).
  - `kg.embeddings.EmbeddingCache(path)` — SQLite, keyed by `(model, text)`.
  - `kg.embeddings.CachedEmbedder(inner, cache, model)` — **only cache misses go over the network**.
  - `kg.embeddings.build_embedder(cfg, hash_only=False) -> Embedder` — the one place the wiring is decided.
  - `kg.embeddings.cosine(a, b) -> float`, `kg.embeddings.nearest(vec, candidates: dict[str, list[float]], k) -> list[str]`.

**Embeddings run in the cloud (OpenRouter), not locally** — Birk decided this explicitly (spec §6.2); `sentence-transformers` is not a dependency and must not be reintroduced. The cache is **mandatory**, not an optimisation: without it every simulation re-run costs money and needs the network, which would make the §9 regression runs slow and online-only.
  - `kg.merging.MergeGroup(canonical_label: str, members: list[str])`, `kg.merging.MergeResult(groups: list[MergeGroup])`.
  - `kg.merging.split_known(store, labels) -> tuple[dict[str, str], list[str]]` — already-decided labels resolve straight to term ids, no LLM.
  - `kg.merging.build_candidates(new_labels, existing_labels, embedder, k) -> dict[str, list[str]]`.
  - `kg.merging.decide_merges(llm, new_labels, candidates, merge_style) -> MergeResult` — **exactly one LLM call per interview**.
  - `kg.merging.apply_merges(store, person_id, new_labels, result, at) -> list[str]` (term ids, input order preserved).

Embedding is preselection only; the LLM judges and names (spec §6.2). Merge aggressiveness lives in the prompt (`Config.merge_style`), never in a similarity threshold, and is never exposed at runtime (spec §6.2, §7).

- [ ] **Step 1: Write the failing tests**

`tests/test_embeddings.py`:

```python
import pytest

from kg.embeddings import (
    CachedEmbedder,
    EmbeddingCache,
    HashEmbedder,
    OpenRouterEmbedder,
    cosine,
    nearest,
)


def test_hash_embedder_is_deterministic_and_normalised():
    e = HashEmbedder(dim=32)
    a1, a2 = e.embed(["Recycling-Beton"])[0], e.embed(["Recycling-Beton"])[0]
    assert a1 == a2
    assert abs(sum(x * x for x in a1) - 1.0) < 1e-6


def test_hash_embedder_scores_shared_words_higher_than_unrelated_text():
    e = HashEmbedder(dim=64)
    a, b, c = e.embed(["Recycling Beton", "Beton Recycling Verfahren", "Ländlicher Leerstand"])
    assert cosine(a, b) > cosine(a, c)


def test_nearest_returns_the_k_closest_keys_in_order():
    e = HashEmbedder(dim=64)
    query = e.embed(["modulares Bauen"])[0]
    candidates = {
        "t1": e.embed(["modulares Bauen im Bestand"])[0],
        "t2": e.embed(["Bodenversiegelung"])[0],
        "t3": e.embed(["modulares Bauen"])[0],
    }
    assert nearest(query, candidates, k=2) == ["t3", "t1"]


def test_nearest_handles_fewer_candidates_than_k():
    e = HashEmbedder(dim=16)
    assert nearest(e.embed(["x"])[0], {}, k=5) == []


class FakePost:
    """Stands in for the httpx POST. Records every request body."""

    def __init__(self, dim=4):
        self.dim = dim
        self.bodies = []

    def __call__(self, url, headers, json):
        self.bodies.append(json)
        return {
            "data": [
                {"index": i, "embedding": [float(len(t))] + [0.0] * (self.dim - 1)}
                for i, t in enumerate(json["input"])
            ]
        }


def test_openrouter_embedder_sends_an_openai_compatible_request():
    post = FakePost()
    embedder = OpenRouterEmbedder(
        model="openai/text-embedding-3-small",
        api_key="sk-or-test",
        url="https://openrouter.ai/api/v1/embeddings",
        post=post,
    )

    vectors = embedder.embed(["Holzbau", "Bodenpreise"])

    assert post.bodies == [
        {"model": "openai/text-embedding-3-small", "input": ["Holzbau", "Bodenpreise"]}
    ]
    assert len(vectors) == 2
    # Vectors come back normalised so `cosine` is a plain dot product.
    assert abs(sum(x * x for x in vectors[0]) - 1.0) < 1e-6


def test_openrouter_embedder_reorders_by_index():
    class ShuffledPost:
        def __call__(self, url, headers, json):
            return {"data": [
                {"index": 1, "embedding": [0.0, 1.0]},
                {"index": 0, "embedding": [1.0, 0.0]},
            ]}

    embedder = OpenRouterEmbedder("m", "k", "u", post=ShuffledPost())
    assert embedder.embed(["a", "b"]) == [[1.0, 0.0], [0.0, 1.0]]


def test_openrouter_embedder_refuses_to_run_without_a_key():
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        OpenRouterEmbedder("m", None, "u").embed(["a"])


def test_openrouter_embedder_skips_the_call_for_an_empty_batch():
    post = FakePost()
    assert OpenRouterEmbedder("m", "k", "u", post=post).embed([]) == []
    assert post.bodies == []


def test_cache_only_sends_misses_and_preserves_input_order(tmp_path):
    post = FakePost()
    inner = OpenRouterEmbedder("m", "k", "u", post=post)
    cache = EmbeddingCache(tmp_path / "emb.sqlite3")
    embedder = CachedEmbedder(inner, cache, model="m")

    first = embedder.embed(["Holzbau", "Bodenpreise"])
    second = embedder.embed(["Bodenpreise", "Holzbau", "Leerstand"])

    # Second call sends ONLY the unseen label.
    assert [b["input"] for b in post.bodies] == [
        ["Holzbau", "Bodenpreise"],
        ["Leerstand"],
    ]
    assert second[0] == first[1]
    assert second[1] == first[0]


def test_cache_survives_a_restart_so_a_rerun_is_offline_and_free(tmp_path):
    """Spec 6.2: the second simulation run must need neither key nor network."""
    path = tmp_path / "emb.sqlite3"
    post = FakePost()
    warm = CachedEmbedder(OpenRouterEmbedder("m", "k", "u", post=post), EmbeddingCache(path), "m")
    expected = warm.embed(["Holzbau"])

    class ExplodingPost:
        def __call__(self, *args, **kwargs):
            raise AssertionError("cache miss: the re-run went online")

    offline = CachedEmbedder(
        OpenRouterEmbedder("m", None, "u", post=ExplodingPost()), EmbeddingCache(path), "m"
    )
    assert offline.embed(["Holzbau"]) == expected


def test_cache_is_keyed_by_model_as_well_as_text(tmp_path):
    cache = EmbeddingCache(tmp_path / "emb.sqlite3")
    post = FakePost()
    CachedEmbedder(OpenRouterEmbedder("m1", "k", "u", post=post), cache, "m1").embed(["Holzbau"])
    CachedEmbedder(OpenRouterEmbedder("m2", "k", "u", post=post), cache, "m2").embed(["Holzbau"])
    assert len(post.bodies) == 2
```

`tests/test_merging.py`:

```python
import pytest

from kg.embeddings import HashEmbedder
from kg.merging import (
    MERGE_SYSTEM,
    MergeGroup,
    MergeResult,
    apply_merges,
    build_candidates,
    build_merge_prompt,
    decide_merges,
    split_known,
)
from kg.store import Store


@pytest.fixture()
def store(tmp_path):
    s = Store.open(tmp_path / "kg.db")
    yield s
    s.close()


class FakeLLM:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def parse(self, system, user, output_model):
        self.calls.append((system, user))
        return self.result


def test_split_known_resolves_persisted_decisions_without_an_llm(store):
    term = store.get_or_create_term("Recycling-Beton", created_at=1.0)
    store.add_alias(term.id, "Beton aus Abbruch")

    known, unknown = split_known(store, ["Beton aus Abbruch", "Holzbau"])

    assert known == {"Beton aus Abbruch": term.id}
    assert unknown == ["Holzbau"]


def test_build_candidates_offers_the_nearest_existing_labels():
    embedder = HashEmbedder(dim=64)
    existing = ["modulares Bauen im Bestand", "Bodenversiegelung", "Genossenschaft"]

    candidates = build_candidates(["modulares Bauen"], existing, embedder, k=2)

    assert candidates["modulares Bauen"][0] == "modulares Bauen im Bestand"
    assert len(candidates["modulares Bauen"]) == 2


def test_merge_prompt_carries_the_style_dial_and_both_sides():
    prompt = build_merge_prompt(
        ["Drohnenbeton"], {"Drohnenbeton": ["Betonspritzen mit Drohnen"]}, "STYLE-DIAL"
    )
    assert "STYLE-DIAL" in prompt
    assert "Drohnenbeton" in prompt
    assert "Betonspritzen mit Drohnen" in prompt
    assert "konkret" in MERGE_SYSTEM


def test_decide_merges_makes_exactly_one_call():
    llm = FakeLLM(MergeResult(groups=[]))
    decide_merges(llm, ["a", "b", "c"], {"a": ["x"], "b": [], "c": []}, "style")
    assert len(llm.calls) == 1


def test_apply_merges_reuses_an_existing_term_and_renames_it(store):
    existing = store.get_or_create_term("Betonspritzen mit Drohnen", created_at=1.0)
    result = MergeResult(
        groups=[
            MergeGroup(
                canonical_label="Roboter auf der Baustelle",
                members=["Betonspritzen mit Drohnen", "3D-Druck vor Ort"],
            )
        ]
    )
    person = store.create_person(started_at=1.0)

    term_ids = apply_merges(store, person.id, ["3D-Druck vor Ort"], result, at=2.0)

    assert term_ids == [existing.id]
    assert store.get_term(existing.id).label == "Roboter auf der Baustelle"
    # Every surface form now resolves to the same node — never re-derived.
    assert store.find_term_by_alias("3D-Druck vor Ort").id == existing.id
    assert store.find_term_by_alias("Betonspritzen mit Drohnen").id == existing.id
    assert store.list_merge_decisions()[0]["person_id"] == person.id


def test_apply_merges_creates_one_node_for_a_group_of_only_new_labels(store):
    person = store.create_person(started_at=1.0)
    result = MergeResult(
        groups=[MergeGroup(canonical_label="Ländlicher Leerstand", members=["leere Dörfer", "Leerstand auf dem Land"])]
    )

    term_ids = apply_merges(store, person.id, ["leere Dörfer", "Leerstand auf dem Land"], result, at=2.0)

    assert term_ids[0] == term_ids[1]
    assert len(store.list_terms()) == 1
    assert store.list_terms()[0].label == "Ländlicher Leerstand"


def test_labels_outside_any_group_stay_separate(store):
    person = store.create_person(started_at=1.0)
    result = MergeResult(groups=[])

    term_ids = apply_merges(store, person.id, ["Holzbau", "Bodenpreise"], result, at=2.0)

    assert len(set(term_ids)) == 2
    assert sorted(t.label for t in store.list_terms()) == ["Bodenpreise", "Holzbau"]


def test_apply_merges_is_idempotent_for_a_repeated_label(store):
    person = store.create_person(started_at=1.0)
    apply_merges(store, person.id, ["Holzbau"], MergeResult(groups=[]), at=2.0)
    person2 = store.create_person(started_at=3.0)

    term_ids = apply_merges(store, person2.id, ["Holzbau"], MergeResult(groups=[]), at=4.0)

    assert len(store.list_terms()) == 1
    assert term_ids == [store.list_terms()[0].id]
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `uv run pytest tests/test_embeddings.py tests/test_merging.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kg.embeddings'`

- [ ] **Step 3: Implement `kg/embeddings.py`**

```python
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
```

- [ ] **Step 4: Implement `kg/merging.py`**

```python
"""Merging: embedding preselection, LLM judgement and naming (spec 6.2).

One LLM call per interview, roughly 50 over the whole festival. Decisions are
persisted as aliases and a decision log; they are never re-derived, so the
graph cannot wobble in live operation.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic import BaseModel

from kg.embeddings import Embedder, nearest

MERGE_SYSTEM = """\
Du pflegst die Begriffsknoten eines wachsenden Beziehungsgraphen über Bauen, \
Stadt und Zukunft. Aus einem neuen Interview kommen NEUE Begriffe. Dazu \
bekommst du je Begriff die ähnlichsten BESTEHENDEN Knoten.

Entscheide:
- Welche neuen Begriffe meinen dasselbe wie ein bestehender Knoten?
- Welche neuen Begriffe meinen untereinander dasselbe?
- Wie heißt der gemeinsame Knoten?

Der Name des gemeinsamen Knotens ist die eigentliche Arbeit: er steht später \
auf der Wand. Er muss konkret, bildhaft und höchstens vier Wörter lang sein. \
Wähle bevorzugt eine der vorhandenen Formulierungen; erfinde nur dann eine \
neue, wenn keine der Formulierungen die Gruppe gut trifft. Steige NIE auf \
einen Oberbegriff hoch („Nachhaltigkeit", „Digitalisierung") — das zerstört \
das Bild.

Gib nur Gruppen mit mindestens zwei Mitgliedern zurück. Begriffe, die für sich \
stehen, lässt du weg.

Antworte ausschließlich im geforderten JSON-Schema.
"""


class MergeGroup(BaseModel):
    canonical_label: str
    members: list[str]


class MergeResult(BaseModel):
    groups: list[MergeGroup]


def split_known(store, labels: Sequence[str]) -> tuple[dict[str, str], list[str]]:
    """Labels with a persisted decision resolve directly; the rest go to the LLM."""
    known: dict[str, str] = {}
    unknown: list[str] = []
    for label in labels:
        term = store.find_term_by_alias(label)
        if term is not None:
            known[label] = term.id
        elif label not in unknown:
            unknown.append(label)
    return known, unknown


def build_candidates(
    new_labels: Sequence[str],
    existing_labels: Sequence[str],
    embedder: Embedder,
    k: int,
) -> dict[str, list[str]]:
    if not new_labels:
        return {}
    if not existing_labels:
        return {label: [] for label in new_labels}
    existing_vectors = dict(zip(existing_labels, embedder.embed(list(existing_labels))))
    new_vectors = embedder.embed(list(new_labels))
    return {
        label: nearest(vector, existing_vectors, k)
        for label, vector in zip(new_labels, new_vectors)
    }


def build_merge_prompt(
    new_labels: Sequence[str], candidates: dict[str, list[str]], merge_style: str
) -> str:
    lines = [f"Maßstab für das Zusammenfassen: {merge_style}", "", "NEUE BEGRIFFE:"]
    for label in new_labels:
        neighbours = candidates.get(label) or []
        suffix = ", ".join(f"„{n}“" for n in neighbours) if neighbours else "(keine)"
        lines.append(f"- „{label}“ — ähnliche bestehende Knoten: {suffix}")
    return "\n".join(lines)


def decide_merges(
    llm, new_labels: Sequence[str], candidates: dict[str, list[str]], merge_style: str
) -> MergeResult:
    if not new_labels:
        return MergeResult(groups=[])
    return llm.parse(
        system=MERGE_SYSTEM,
        user=build_merge_prompt(new_labels, candidates, merge_style),
        output_model=MergeResult,
    )


def apply_merges(
    store, person_id: str, new_labels: Sequence[str], result: MergeResult, at: float
) -> list[str]:
    """Persist the decision and return one term id per input label, in order.

    Runs as a single `store.transaction()`: a crash partway through must
    leave no rename, fold or alias committed without the matching decision
    log, or the graph state could never be reproduced or undone.
    """
    resolved: dict[str, str] = {}
    claimed: set[str] = set()  # members an earlier group in this call already used

    with store.transaction():
        for group in result.groups:
            members = list(dict.fromkeys(m for m in group.members if m))
            # Group 1's aliases are visible to group 2 within the same call.
            # A member an earlier group already claimed must not silently
            # drag this group's *other* members along with it — drop it here
            # and let it resolve on its own (standalone) below.
            members = [m for m in members if m not in claimed]
            if len(members) < 2:
                continue

            existing_ids: list[str] = []
            for member in members:
                term = store.find_term_by_alias(member) or store.get_term_by_label(member)
                if term is not None and term.id not in existing_ids:
                    existing_ids.append(term.id)

            # The model was told to prefer an existing formulation, so the
            # canonical label itself may already belong to some OTHER term
            # (`term.label` is UNIQUE). Treat that as a merge with that term
            # too, rather than letting the rename below raise.
            collision = store.get_term_by_label(group.canonical_label)
            if collision is not None and collision.id not in existing_ids:
                existing_ids.append(collision.id)

            if existing_ids:
                # Every existing term the group touches folds onto one
                # winner — the loser's edges and aliases move over, nothing
                # is left stranded on an unreachable second node.
                winner_id, *loser_ids = existing_ids
                for loser_id in loser_ids:
                    store.fold_term(loser_id, winner_id)
                winner = store.get_term(winner_id)
                if winner.label != group.canonical_label:
                    store.rename_term(winner_id, group.canonical_label)
            else:
                winner_id = store.get_or_create_term(group.canonical_label, created_at=at).id

            for member in members:
                store.add_alias(winner_id, member)
                resolved[member] = winner_id
                claimed.add(member)

        term_ids: list[str] = []
        for label in new_labels:
            term_id = resolved.get(label)
            if term_id is None:
                existing = store.find_term_by_alias(label)
                term = existing or store.get_or_create_term(label, created_at=at)
                term_id = term.id
                resolved[label] = term_id
            term_ids.append(term_id)

        store.record_merge_decision(
            person_id,
            json.loads(result.model_dump_json()) | {"labels": list(new_labels)},
            created_at=at,
        )
    return term_ids
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_embeddings.py tests/test_merging.py -v`
Expected: PASS (26 tests)

- [ ] **Step 6: Commit**

```bash
git add kg/embeddings.py kg/merging.py tests/test_embeddings.py tests/test_merging.py
git commit -m "feat: embedding preselection and persisted LLM merge decisions"
```

---

### Task 10: graph.json export

**Files:**
- Create: `kg/export.py`
- Test: `tests/test_export.py`

**Interfaces:**
- Consumes: `kg.store.Store` (Task 2), `Config.graph_json_path` (Task 1).
- Produces:
  - `kg.export.build_graph(store) -> dict`
  - `kg.export.write_graph_json(store, path) -> dict` (atomic: temp file + `os.replace`)

The export carries the **complete** state with flags and counts; filtering is the consumer's job. That keeps the display filter instant and reversible (spec §7) and makes the same file the read-only interface for Tool 2 (spec §11).

Shape:

```json
{
  "version": 1,
  "generated_at": 1755000000.0,
  "min_mentions": 1,
  "nodes": [
    {"id": "p1", "type": "person", "portrait": "/media/portraits/1700_7.png",
     "created_at": 1700.0, "hidden": false, "x": 12.0, "y": -3.0},
    {"id": "t4", "type": "term", "label": "Recycling-Beton", "mentions": 3,
     "created_at": 1710.0, "hidden": false, "x": null, "y": null}
  ],
  "edges": [{"id": "e7", "source": "p1", "target": "t4"}],
  "quotes": [{"id": "q2", "person_id": "p1", "text": "…"}]
}
```

- [ ] **Step 1: Write the failing test**

`tests/test_export.py`:

```python
import json

import pytest

from kg.export import build_graph, write_graph_json
from kg.store import Store


@pytest.fixture()
def store(tmp_path):
    s = Store.open(tmp_path / "kg.db")
    yield s
    s.close()


def seed(store):
    p1 = store.create_person(started_at=100.0, portrait_path="portraits/a.png")
    p2 = store.create_person(started_at=200.0, portrait_path="portraits/b.png")
    t1 = store.get_or_create_term("Recycling-Beton", created_at=110.0)
    t2 = store.get_or_create_term("Holzbau", created_at=210.0)
    store.add_edge(p1.id, t1.id, created_at=111.0)
    store.add_edge(p2.id, t1.id, created_at=211.0)
    store.add_edge(p2.id, t2.id, created_at=212.0)
    store.add_quote(p1.id, "Wir bauen zu viel Neues.", created_at=112.0)
    store.save_positions({p1.id: (10.0, 20.0)})
    return p1, p2, t1, t2


def test_graph_carries_full_state_with_counts_flags_and_positions(store):
    p1, p2, t1, t2 = seed(store)

    graph = build_graph(store)

    nodes = {n["id"]: n for n in graph["nodes"]}
    assert nodes[p1.id]["type"] == "person"
    assert nodes[p1.id]["portrait"] == "/media/portraits/a.png"
    assert nodes[p1.id]["x"] == 10.0 and nodes[p1.id]["y"] == 20.0
    assert nodes[p2.id]["x"] is None
    assert nodes[t1.id]["label"] == "Recycling-Beton"
    assert nodes[t1.id]["mentions"] == 2
    assert nodes[t2.id]["mentions"] == 1
    assert len(graph["edges"]) == 3
    assert graph["quotes"][0]["text"] == "Wir bauen zu viel Neues."
    assert graph["version"] == 1


def test_hidden_entries_are_exported_with_the_flag_not_removed(store):
    p1, _, t1, _ = seed(store)
    store.set_hidden(f"term:{t1.id}", True)
    store.set_hidden(f"person:{p1.id}", True)

    graph = build_graph(store)
    nodes = {n["id"]: n for n in graph["nodes"]}

    assert nodes[t1.id]["hidden"] is True
    assert nodes[p1.id]["hidden"] is True
    # Nothing is discarded: hiding is reversible (spec 8).
    assert len(graph["edges"]) == 3


def test_min_mentions_is_reported_but_not_applied(store):
    seed(store)
    store.set_setting("min_mentions", "2")

    graph = build_graph(store)

    assert graph["min_mentions"] == 2
    assert len(graph["nodes"]) == 4  # filtering happens in the consumer


def test_write_is_atomic_and_leaves_valid_json(store, tmp_path):
    seed(store)
    path = tmp_path / "out" / "graph.json"

    graph = write_graph_json(store, path)

    assert path.exists()
    assert not list(path.parent.glob("*.tmp"))
    assert json.loads(path.read_text(encoding="utf-8")) == graph


def test_export_of_an_empty_graph_is_valid(store, tmp_path):
    graph = write_graph_json(store, tmp_path / "graph.json")
    assert graph["nodes"] == [] and graph["edges"] == [] and graph["quotes"] == []
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_export.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kg.export'`

- [ ] **Step 3: Implement `kg/export.py`**

```python
"""Complete graph.json after every change — no delta mechanism (spec 11).

This file is also the read-only interface for Tool 2 („Kollektivtraum"), so it
carries the full state including quotes and flags; consumers filter.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


def build_graph(store) -> dict:
    positions = store.get_positions()
    nodes: list[dict] = []

    for person in store.list_persons():
        x, y = positions.get(person.id, (None, None))
        nodes.append(
            {
                "id": person.id,
                "type": "person",
                "portrait": _portrait_url(person.portrait_path),
                "created_at": person.started_at,
                "hidden": person.hidden,
                "x": x,
                "y": y,
            }
        )

    for term in store.list_terms():
        x, y = positions.get(term.id, (None, None))
        nodes.append(
            {
                "id": term.id,
                "type": "term",
                "label": term.label,
                "mentions": store.mention_count(term.id),
                "created_at": term.created_at,
                "hidden": term.hidden,
                "x": x,
                "y": y,
            }
        )

    return {
        "version": 1,
        "generated_at": time.time(),
        "min_mentions": int(store.get_setting("min_mentions", "1")),
        "nodes": nodes,
        "edges": [
            {"id": e.id, "source": e.person_id, "target": e.term_id} for e in store.list_edges()
        ],
        "quotes": [
            {"id": q.id, "person_id": q.person_id, "text": q.text} for q in store.list_quotes()
        ],
    }


def write_graph_json(store, path: Path) -> dict:
    graph = build_graph(store)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return graph


def _portrait_url(portrait_path: str | None) -> str | None:
    if not portrait_path:
        return None
    return f"/media/portraits/{Path(portrait_path).name}"
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_export.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add kg/export.py tests/test_export.py
git commit -m "feat: complete graph.json export (atomic write)"
```

---

### Task 11: Per-interview pipeline

**Files:**
- Create: `kg/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: everything from Tasks 2, 3, 4, 8, 9, 10.
- Produces:
  - `kg.pipeline.ProcessResult(person_id: str, status: str, term_ids: list[str], transcript: str)` — `status` is `"done"` or `"failed"`.
  - `kg.pipeline.process_interview(store, cfg, llm, embedder, transcript_log, person_id, started_at, stopped_at) -> ProcessResult`

Order (spec §6.1): cut with a generous tail → strip the spoken stop command → one extraction call (end detection + terms + quotes) → truncate at the detected end → resolve already-decided labels → one merge call for the rest → persist person↔term edges and quotes → re-export `graph.json`. An LLM failure marks the interview `failed` and leaves the person node standing; it must never crash the process (spec §13).

- [ ] **Step 1: Write the failing test**

`tests/test_pipeline.py`:

```python
import json

import pytest

from kg.config import Config
from kg.embeddings import HashEmbedder
from kg.extraction import ExtractionResult
from kg.llm import LLMError
from kg.merging import MergeGroup, MergeResult
from kg.pipeline import process_interview
from kg.store import Store
from kg.transcript import TranscriptionEvent, TranscriptLog


@pytest.fixture()
def env(tmp_path):
    cfg = Config(data_dir=tmp_path / "state", terms_per_interview=3, tail_seconds=60)
    store = Store.open(cfg.db_path)
    log = TranscriptLog(cfg.transcript_log_path)
    yield cfg, store, log
    store.close()


class ScriptedLLM:
    """Returns one queued result per call and records the prompts it saw."""

    def __init__(self, results):
        self.results = list(results)
        self.prompts = []

    def parse(self, system, user, output_model):
        self.prompts.append(user)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def fill_log(log, texts_at):
    for text, at in texts_at:
        log.append(TranscriptionEvent(type="final", text=text, timestamp=at))


def test_happy_path_creates_edges_quotes_and_graph_json(env):
    cfg, store, log = env
    fill_log(
        log,
        [
            ("Wir sollten mit Recycling-Beton bauen.", 105.0),
            ("Und Genossenschaften stärken.", 115.0),
            ("So, Interview beendet.", 160.0),
            ("Nächste Person bitte.", 200.0),
        ],
    )
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM(
        [
            ExtractionResult(
                interview_end_index=10_000,
                terms=[
                    {"label": "Recycling-Beton", "evidence": "Recycling-Beton bauen"},
                    {"label": "Genossenschaftliches Wohnen", "evidence": "Genossenschaften"},
                ],
                quotes=[{"text": "Wir sollten mit Recycling-Beton bauen."}],
            ),
            MergeResult(groups=[]),
        ]
    )

    result = process_interview(
        store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 160.0
    )

    assert result.status == "done"
    assert len(result.term_ids) == 2
    assert len(store.list_edges()) == 2
    assert len(store.list_quotes()) == 1
    assert store.get_person(person.id).status == "done"
    graph = json.loads(cfg.graph_json_path.read_text(encoding="utf-8"))
    assert {n["type"] for n in graph["nodes"]} == {"person", "term"}


def test_the_stop_command_is_stripped_before_the_llm_sees_the_text(env):
    cfg, store, log = env
    fill_log(log, [("Holzbau ist gut.", 105.0), ("Interview beendet", 150.0)])
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM(
        [ExtractionResult(interview_end_index=9999, terms=[], quotes=[]), MergeResult(groups=[])]
    )

    process_interview(store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 150.0)

    assert "Interview beendet" not in llm.prompts[0]
    assert "Holzbau ist gut." in llm.prompts[0]


def test_the_tail_is_handed_over_but_cut_at_the_detected_end(env):
    cfg, store, log = env
    fill_log(log, [("Bodenpreise sind das Problem.", 105.0), ("Wo ist der Kaffee?", 175.0)])
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM(
        [
            ExtractionResult(interview_end_index=len("Bodenpreise sind das Problem."), terms=[], quotes=[]),
            MergeResult(groups=[]),
        ]
    )

    process_interview(store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 150.0)

    # Tail was offered to the model...
    assert "Wo ist der Kaffee?" in llm.prompts[0]
    # ...but the stored transcript stops where the interview really ended.
    assert store.get_person(person.id).transcript == "Bodenpreise sind das Problem."


def test_a_merge_maps_a_new_label_onto_an_existing_node(env):
    cfg, store, log = env
    existing = store.get_or_create_term("Betonspritzen mit Drohnen", created_at=1.0)
    fill_log(log, [("Roboter drucken Beton auf der Baustelle.", 105.0)])
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM(
        [
            ExtractionResult(
                interview_end_index=9999,
                terms=[{"label": "3D-Druck vor Ort", "evidence": "Roboter drucken Beton"}],
                quotes=[],
            ),
            MergeResult(
                groups=[
                    MergeGroup(
                        canonical_label="Roboter auf der Baustelle",
                        members=["3D-Druck vor Ort", "Betonspritzen mit Drohnen"],
                    )
                ]
            ),
        ]
    )

    result = process_interview(
        store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 150.0
    )

    assert result.term_ids == [existing.id]
    assert store.get_term(existing.id).label == "Roboter auf der Baustelle"
    assert len(store.list_terms()) == 1


def test_an_already_decided_label_skips_the_merge_call(env):
    cfg, store, log = env
    term = store.get_or_create_term("Holzbau", created_at=1.0)
    fill_log(log, [("Holzbau überall.", 105.0)])
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM(
        [
            ExtractionResult(
                interview_end_index=9999,
                terms=[{"label": "Holzbau", "evidence": "Holzbau"}],
                quotes=[],
            )
        ]
    )  # note: no MergeResult queued — a second call would raise IndexError

    result = process_interview(
        store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 150.0
    )

    assert result.term_ids == [term.id]
    assert len(llm.prompts) == 1


def test_an_llm_failure_marks_the_interview_failed_and_keeps_the_person(env):
    cfg, store, log = env
    fill_log(log, [("Irgendwas.", 105.0)])
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM([LLMError("boom")])

    result = process_interview(
        store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 150.0
    )

    assert result.status == "failed"
    assert store.get_person(person.id).status == "failed"
    assert store.list_edges() == []
    # The wall still shows the portrait, and graph.json is still written.
    assert cfg.graph_json_path.exists()


def test_an_empty_transcript_is_not_sent_to_the_llm(env):
    cfg, store, log = env
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM([])

    result = process_interview(
        store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 150.0
    )

    assert result.status == "done"
    assert result.term_ids == []
    assert llm.prompts == []
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kg.pipeline'`

- [ ] **Step 3: Implement `kg/pipeline.py`**

```python
"""Per-interview condensation (spec 6.1). Deterministic, plain Python, no agent."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from kg.export import write_graph_json
from kg.extraction import extract
from kg.merging import apply_merges, build_candidates, decide_merges, split_known
from kg.segmentation import strip_stop_phrases

log = logging.getLogger(__name__)


@dataclass
class ProcessResult:
    person_id: str
    status: str
    term_ids: list[str] = field(default_factory=list)
    transcript: str = ""


def process_interview(
    store,
    cfg,
    llm,
    embedder,
    transcript_log,
    person_id: str,
    started_at: float,
    stopped_at: float,
) -> ProcessResult:
    store.set_person_status(person_id, "processing")

    # 1. Cut, with a generous tail beyond the stop marker (spec 6.1).
    raw = transcript_log.text_between(started_at, stopped_at + cfg.tail_seconds)
    text = strip_stop_phrases(raw, cfg.stop_phrases)

    if not text.strip():
        store.set_person_transcript(person_id, "")
        store.set_person_status(person_id, "done")
        write_graph_json(store, cfg.graph_json_path)
        return ProcessResult(person_id, "done", [], "")

    try:
        # 2.+3. Find the real end and extract, in one call.
        result = extract(llm, text, cfg.terms_per_interview)
        transcript = text[: result.interview_end_index].strip() or text.strip()
        labels = [t.label.strip() for t in result.terms if t.label.strip()]

        # 4. Merge: persisted decisions first, one LLM call for the rest.
        known, unknown = split_known(store, labels)
        if unknown:
            candidates = build_candidates(
                unknown, [t.label for t in store.list_terms()], embedder, cfg.merge_neighbours
            )
            decision = decide_merges(llm, unknown, candidates, cfg.merge_style)
            resolved = dict(zip(unknown, apply_merges(store, person_id, unknown, decision, stopped_at)))
        else:
            resolved = {}
        term_ids: list[str] = []
        for label in labels:
            term_id = known.get(label) or resolved.get(label)
            if term_id and term_id not in term_ids:
                term_ids.append(term_id)

        # 5. Persist.
        store.set_person_transcript(person_id, transcript)
        for term_id in term_ids:
            store.add_edge(person_id, term_id, created_at=stopped_at)
        for quote in result.quotes:
            if quote.text.strip():
                store.add_quote(person_id, quote.text.strip(), created_at=stopped_at)
        store.set_person_status(person_id, "done")
        status = "done"
    except Exception as exc:  # a bad LLM turn must never stop the station
        log.error("interview %s failed: %s", person_id, exc)
        store.set_person_status(person_id, "failed")
        term_ids, transcript, status = [], text.strip(), "failed"
        store.set_person_transcript(person_id, transcript)

    write_graph_json(store, cfg.graph_json_path)
    return ProcessResult(person_id, status, term_ids, transcript)
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Run the whole backend suite**

Run: `uv run pytest -v`
Expected: PASS (all tests from Tasks 1–11)

- [ ] **Step 6: Commit**

```bash
git add kg/pipeline.py tests/test_pipeline.py
git commit -m "feat: per-interview pipeline (cut, extract, merge, persist, export)"
```

---

### Task 12: Event bus and HTTP/SSE server

**Files:**
- Create: `kg/bus.py`, `kg/server.py`, plus the minimal pages the server mounts: `frontend/projection.html`, `frontend/operator.html`, `frontend/static/graph-model.js` (Step 5 — they are replaced/extended by Tasks 13–15)
- Test: `tests/test_bus.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: `kg.store.Store` (Task 2), `kg.export.build_graph` / `write_graph_json` (Task 10), `Config` (Task 1).
- Produces:
  - `kg.bus.EventBus` with `subscribe() -> asyncio.Queue`, `unsubscribe(q)`, `publish(event: dict)` (drops for slow consumers, never blocks).
  - `kg.server.create_app(store, cfg, bus) -> FastAPI`
  - `kg.server.broadcast_graph(store, cfg, bus)` and `kg.server.broadcast_state(store, bus)` — used by Task 17 to push after a pipeline run.

Endpoints (the browser is the only client):

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | redirect to `/projection` |
| GET | `/projection` | projection page (beamer, fullscreen) |
| GET | `/operator` | operator page (laptop display) |
| GET | `/static/*` | JS/CSS, vendored Cytoscape |
| GET | `/media/portraits/*` | normalised portraits |
| GET | `/graph.json` | complete current state (also Tool 2's read interface) |
| GET | `/events` | SSE: `{"type": "graph"|"state"|"transcript", ...}` |
| GET | `/api/state` | `{min_mentions, camera_mode, interview, stt_connected}` |
| POST | `/api/min_mentions` | `{"value": int}` — the one runtime dial (spec §7) |
| POST | `/api/hidden` | `{"node_id": "term:t4", "hidden": true}` — the emergency exit (spec §8) |
| POST | `/api/camera` | `{"mode": "fit"|"manual"|"pan"}` |
| POST | `/api/positions` | `{"positions": {"t4": {"x": 1.0, "y": 2.0}}}` — persisted layout (spec §11) |

The route handlers below are plain sync `def`s, so FastAPI runs each call in its
threadpool: an operator action (`/api/min_mentions`, `/api/hidden`,
`/api/camera`, `/api/positions`) can run on a different thread, at the same
time, as the Core loop or the per-interview pipeline (Task 11) writing through
the same `Store` instance. **Do not "fix" this by making the routes `async`.**
That is deliberately not the mechanism: `kg.store.Store` (Task 2) serialises
every public method — reads and writes — through one store-wide
`threading.RLock` (task 12b), so two threads calling into the same `Store`
from different route handlers (or from a route handler and the pipeline) are
already safe. The sync handlers stay sync; `Store` is the only place that
knows about the shared SQLite connection, so it is the only place that needs
to know about the lock.

- [ ] **Step 1: Write the failing tests**

`tests/test_bus.py`:

```python
import asyncio

from kg.bus import EventBus


async def test_every_subscriber_receives_published_events():
    bus = EventBus()
    a, b = bus.subscribe(), bus.subscribe()

    bus.publish({"type": "graph"})

    assert await asyncio.wait_for(a.get(), 1) == {"type": "graph"}
    assert await asyncio.wait_for(b.get(), 1) == {"type": "graph"}


async def test_a_slow_subscriber_is_dropped_not_blocking():
    bus = EventBus(max_queue=1)
    slow = bus.subscribe()

    bus.publish({"n": 1})
    bus.publish({"n": 2})  # queue is full -> dropped, must not raise

    assert slow.qsize() == 1


async def test_unsubscribe_stops_delivery():
    bus = EventBus()
    q = bus.subscribe()
    bus.unsubscribe(q)

    bus.publish({"type": "graph"})

    assert q.empty()
```

`tests/test_server.py`:

```python
import pytest
from fastapi.testclient import TestClient

from kg.bus import EventBus
from kg.config import Config
from kg.server import create_app
from kg.store import Store


@pytest.fixture()
def client(tmp_path):
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    person = store.create_person(started_at=1.0, portrait_path="portraits/a.png")
    term = store.get_or_create_term("Holzbau", created_at=2.0)
    store.add_edge(person.id, term.id, created_at=3.0)
    app = create_app(store, cfg, EventBus())
    with TestClient(app) as test_client:
        test_client.store = store
        test_client.cfg = cfg
        yield test_client
    store.close()


def test_graph_json_serves_the_current_state(client):
    data = client.get("/graph.json").json()
    assert {n["type"] for n in data["nodes"]} == {"person", "term"}
    assert len(data["edges"]) == 1


def test_min_mentions_is_persisted_and_reported(client):
    assert client.post("/api/min_mentions", json={"value": 3}).status_code == 200
    assert client.get("/api/state").json()["min_mentions"] == 3
    assert client.store.get_setting("min_mentions", "1") == "3"


def test_min_mentions_rejects_nonsense(client):
    assert client.post("/api/min_mentions", json={"value": 0}).status_code == 422
    assert client.post("/api/min_mentions", json={"value": "viele"}).status_code == 422


def test_hiding_sets_the_flag_without_deleting_anything(client):
    term_id = client.store.list_terms()[0].id

    assert client.post("/api/hidden", json={"node_id": f"term:{term_id}", "hidden": True}).status_code == 200

    assert client.store.get_term(term_id).hidden is True
    graph = client.get("/graph.json").json()
    assert [n for n in graph["nodes"] if n["id"] == term_id][0]["hidden"] is True
    assert len(graph["edges"]) == 1


def test_hiding_an_unknown_node_is_a_client_error(client):
    assert client.post("/api/hidden", json={"node_id": "nonsense:1", "hidden": True}).status_code == 400


def test_camera_mode_round_trips(client):
    assert client.post("/api/camera", json={"mode": "pan"}).status_code == 200
    assert client.get("/api/state").json()["camera_mode"] == "pan"
    assert client.post("/api/camera", json={"mode": "warp"}).status_code == 422


def test_positions_are_persisted_so_the_layout_never_reshuffles(client):
    term_id = client.store.list_terms()[0].id

    response = client.post("/api/positions", json={"positions": {term_id: {"x": 4.5, "y": -2.0}}})

    assert response.status_code == 200
    assert client.store.get_positions()[term_id] == (4.5, -2.0)
    node = [n for n in client.get("/graph.json").json()["nodes"] if n["id"] == term_id][0]
    assert (node["x"], node["y"]) == (4.5, -2.0)


def test_pages_and_static_assets_are_served(client):
    assert client.get("/", follow_redirects=False).status_code in (302, 307)
    assert client.get("/projection").status_code == 200
    assert client.get("/operator").status_code == 200
    assert client.get("/static/graph-model.js").status_code == 200
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `uv run pytest tests/test_bus.py tests/test_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kg.bus'`

- [ ] **Step 3: Implement `kg/bus.py`**

```python
"""In-process pub/sub for the browser SSE fanout.

Same rule as the STT server's bus: a slow browser tab must never stall the Core.
"""

from __future__ import annotations

import asyncio


class EventBus:
    def __init__(self, max_queue: int = 100) -> None:
        self.max_queue = max_queue
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self.max_queue)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    def publish(self, event: dict) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass  # drop for slow consumers
```

- [ ] **Step 4: Implement `kg/server.py`**

```python
"""FastAPI app: two static pages, one SSE stream, the operator API."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from kg.export import build_graph, write_graph_json

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


class MinMentions(BaseModel):
    value: int = Field(ge=1, le=10)


class HiddenFlag(BaseModel):
    node_id: str
    hidden: bool


class CameraMode(BaseModel):
    mode: Literal["fit", "manual", "pan"]


class Point(BaseModel):
    x: float
    y: float


class Positions(BaseModel):
    positions: dict[str, Point]


def current_state(store) -> dict:
    person = store.open_person()
    return {
        "min_mentions": int(store.get_setting("min_mentions", "1")),
        "camera_mode": store.get_setting("camera_mode", "fit"),
        "stt_connected": store.get_setting("stt_connected", "0") == "1",
        "interview": None
        if person is None
        else {"person_id": person.id, "started_at": person.started_at},
    }


def broadcast_graph(store, cfg, bus) -> None:
    bus.publish({"type": "graph", "graph": write_graph_json(store, cfg.graph_json_path)})


def broadcast_state(store, bus) -> None:
    bus.publish({"type": "state", "state": current_state(store)})


def create_app(store, cfg, bus) -> FastAPI:
    app = FastAPI(title="Kollektivgedächtnis")
    app.mount("/static", StaticFiles(directory=FRONTEND / "static"), name="static")
    app.mount("/media/portraits", StaticFiles(directory=cfg.portrait_dir), name="portraits")

    @app.get("/")
    def index() -> RedirectResponse:
        return RedirectResponse("/projection")

    @app.get("/projection")
    def projection() -> FileResponse:
        return FileResponse(FRONTEND / "projection.html")

    @app.get("/operator")
    def operator() -> FileResponse:
        return FileResponse(FRONTEND / "operator.html")

    @app.get("/graph.json")
    def graph_json() -> JSONResponse:
        return JSONResponse(build_graph(store))

    @app.get("/api/state")
    def api_state() -> dict:
        return current_state(store)

    @app.post("/api/min_mentions")
    def api_min_mentions(payload: MinMentions) -> dict:
        store.set_setting("min_mentions", str(payload.value))
        broadcast_state(store, bus)
        broadcast_graph(store, cfg, bus)
        return {"ok": True}

    @app.post("/api/hidden")
    def api_hidden(payload: HiddenFlag) -> dict:
        try:
            store.set_hidden(payload.node_id, payload.hidden)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        broadcast_graph(store, cfg, bus)
        return {"ok": True}

    @app.post("/api/camera")
    def api_camera(payload: CameraMode) -> dict:
        store.set_setting("camera_mode", payload.mode)
        broadcast_state(store, bus)
        return {"ok": True}

    @app.post("/api/positions")
    def api_positions(payload: Positions) -> dict:
        # No broadcast: positions come FROM the renderer; echoing them would loop.
        store.save_positions({k: (p.x, p.y) for k, p in payload.positions.items()})
        return {"ok": True}

    @app.get("/events")
    async def events() -> StreamingResponse:
        queue = bus.subscribe()

        async def stream():
            try:
                yield _sse({"type": "graph", "graph": build_graph(store)})
                yield _sse({"type": "state", "state": current_state(store)})
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    except TimeoutError:
                        yield ": keep-alive\n\n"
                        continue
                    yield _sse(event)
            finally:
                bus.unsubscribe(queue)

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
```

- [ ] **Step 5: Create placeholder frontend files so the server tests can pass**

```bash
mkdir -p frontend/static/vendor
printf '<!doctype html>\n<title>Projektion</title>\n' > frontend/projection.html
printf '<!doctype html>\n<title>Operator</title>\n' > frontend/operator.html
printf '// filled in Task 13\nexport const PLACEHOLDER = true;\n' > frontend/static/graph-model.js
```

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_bus.py tests/test_server.py -v`
Expected: PASS (11 tests)

- [ ] **Step 7: Commit**

```bash
git add kg/bus.py kg/server.py frontend/projection.html frontend/operator.html frontend/static/graph-model.js tests/test_bus.py tests/test_server.py
git commit -m "feat: SSE event bus and HTTP server with operator API"
```

---

### Task 13: Display-filter logic in the browser

**Files:**
- Create: `frontend/static/graph-model.js`, `frontend/static/test-harness.html`, `frontend/static/vendor/cytoscape.min.js`
- Test: `tests/test_graph_model.py`, `tests/conftest.py`

**Interfaces:**
- Consumes: the `graph.json` shape from Task 10.
- Produces (ES module `graph-model.js`):
  - `visibleGraph(graph, minMentions) -> {nodes, edges}`
  - `toCytoscape(view) -> [{data, position?, classes}]`
  - `newNodeIds(previousIds, view) -> string[]`

The whole display filter lives here so it is instant and reversible in the browser and never touches the store (spec §7, §8). The frontend is tested through Playwright from pytest — one test runner for the whole project.

- [ ] **Step 1: Vendor Cytoscape.js and install the browser**

```bash
curl -fsSL https://unpkg.com/cytoscape@3.30.2/dist/cytoscape.min.js -o frontend/static/vendor/cytoscape.min.js
grep -c cytoscape frontend/static/vendor/cytoscape.min.js   # must be > 0
uv run playwright install chromium
```

The file is **committed**: the exhibition machine must not need npm or the network (spec §2, §10.5).

- [ ] **Step 2: Write the failing test**

`tests/conftest.py`:

```python
import functools
import http.server
import socketserver
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def static_server():
    """Serve the repo over http so ES modules can be imported by the browser."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(REPO_ROOT))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
        httpd.shutdown()


@pytest.fixture(scope="module")
def browser():
    # Module-scoped, not session-scoped: playwright's sync API drives its
    # event loop with a greenlet in this OS thread and leaves that loop
    # marked "running" for as long as the `sync_playwright()` context stays
    # open. A session-scoped browser would therefore still be open while
    # later pytest-asyncio tests run in the same thread, and every one of
    # them would fail with "Cannot run the event loop while another loop is
    # running". Module scope still amortises the browser launch across all
    # tests in this file while closing it before the next test module runs.
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:
            # This host's OS predates what the installed playwright package's
            # pinned chromium revision supports, so `playwright install`
            # refuses to fetch it (and the exhibition machine has no network
            # access to fall back on anyway). Reuse whatever chromium build
            # is already present in the local playwright cache instead of
            # requiring an exact revision match.
            candidates = sorted(Path.home().glob(".cache/ms-playwright/chromium-*/chrome-linux64/chrome"))
            if not candidates:
                raise
            browser = p.chromium.launch(executable_path=str(candidates[-1]))
        yield browser
        browser.close()


@pytest.fixture()
def page(browser):
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    yield page
    page.close()
```

`tests/test_graph_model.py`:

```python
import pytest

GRAPH = {
    "version": 1,
    "min_mentions": 1,
    "nodes": [
        {"id": "p1", "type": "person", "portrait": "/media/portraits/a.png", "hidden": False, "x": 1, "y": 2},
        {"id": "p2", "type": "person", "portrait": "/media/portraits/b.png", "hidden": False, "x": None, "y": None},
        {"id": "p3", "type": "person", "portrait": None, "hidden": True, "x": None, "y": None},
        {"id": "t1", "type": "term", "label": "Holzbau", "mentions": 2, "hidden": False, "x": None, "y": None},
        {"id": "t2", "type": "term", "label": "Bodenpreise", "mentions": 1, "hidden": False, "x": None, "y": None},
        {"id": "t3", "type": "term", "label": "Unfug", "mentions": 5, "hidden": True, "x": None, "y": None},
    ],
    "edges": [
        {"id": "e1", "source": "p1", "target": "t1"},
        {"id": "e2", "source": "p2", "target": "t1"},
        {"id": "e3", "source": "p1", "target": "t2"},
        {"id": "e4", "source": "p3", "target": "t3"},
    ],
    "quotes": [],
}


@pytest.fixture()
def model(page, static_server):
    page.goto(f"{static_server}/frontend/static/test-harness.html")
    page.wait_for_function("window.kgModel !== undefined")
    return page


def call(page, fn, *args):
    return page.evaluate(f"(args) => window.kgModel.{fn}(...args)", list(args))


def test_min_mentions_one_shows_every_unhidden_term(model):
    view = call(model, "visibleGraph", GRAPH, 1)
    assert sorted(n["id"] for n in view["nodes"]) == ["p1", "p2", "t1", "t2"]


def test_raising_the_dial_leaves_only_what_is_shared(model):
    view = call(model, "visibleGraph", GRAPH, 2)
    assert sorted(n["id"] for n in view["nodes"]) == ["p1", "p2", "t1"]
    assert [e["id"] for e in view["edges"]] == ["e1", "e2"]


def test_hidden_entries_never_appear_at_any_dial_setting(model):
    for value in (1, 2, 3):
        view = call(model, "visibleGraph", GRAPH, value)
        ids = {n["id"] for n in view["nodes"]}
        assert "t3" not in ids and "p3" not in ids


def test_the_dial_is_fully_reversible(model):
    before = call(model, "visibleGraph", GRAPH, 1)
    call(model, "visibleGraph", GRAPH, 3)
    after = call(model, "visibleGraph", GRAPH, 1)
    assert before == after


def test_edges_need_both_endpoints_visible(model):
    view = call(model, "visibleGraph", GRAPH, 3)
    assert view["edges"] == []


def test_person_nodes_stay_even_without_visible_terms(model):
    view = call(model, "visibleGraph", GRAPH, 5)
    assert sorted(n["id"] for n in view["nodes"]) == ["p1", "p2"]


def test_to_cytoscape_maps_positions_labels_and_classes(model):
    view = call(model, "visibleGraph", GRAPH, 1)
    elements = call(model, "toCytoscape", view)
    by_id = {e["data"]["id"]: e for e in elements}
    assert by_id["p1"]["classes"] == "person"
    assert by_id["p1"]["position"] == {"x": 1, "y": 2}
    assert "position" not in by_id["p2"]
    assert by_id["t1"]["data"]["label"] == "Holzbau"
    assert by_id["e1"]["data"]["source"] == "p1"


def test_new_node_ids_reports_only_what_the_renderer_has_not_placed(model):
    view = call(model, "visibleGraph", GRAPH, 1)
    assert sorted(call(model, "newNodeIds", ["p1", "t1"], view)) == ["p2", "t2"]
    assert call(model, "newNodeIds", ["p1", "p2", "t1", "t2"], view) == []
```

- [ ] **Step 3: Run the test and confirm it fails**

Run: `uv run pytest tests/test_graph_model.py -v`
Expected: FAIL — timeout waiting for `window.kgModel` (the harness does not exist yet)

- [ ] **Step 4: Implement `frontend/static/graph-model.js`**

```javascript
// Pure display logic. The store keeps everything; the wall shows a view of it.
// The minimum-mention dial is a display filter: instant, reversible, lossless.

export function visibleGraph(graph, minMentions) {
  const threshold = Math.max(1, Number(minMentions) || 1);
  const nodes = graph.nodes.filter((node) => {
    if (node.hidden) return false;
    if (node.type === 'term') return (node.mentions || 0) >= threshold;
    return true;
  });
  const visibleIds = new Set(nodes.map((node) => node.id));
  const edges = graph.edges.filter(
    (edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target),
  );
  return { nodes, edges };
}

export function toCytoscape(view) {
  const elements = [];
  for (const node of view.nodes) {
    const element = {
      data: {
        id: node.id,
        type: node.type,
        label: node.type === 'term' ? node.label : '',
        portrait: node.portrait || '',
        mentions: node.mentions || 0,
      },
      classes: node.type,
    };
    if (node.x !== null && node.x !== undefined && node.y !== null && node.y !== undefined) {
      element.position = { x: node.x, y: node.y };
    }
    elements.push(element);
  }
  for (const edge of view.edges) {
    elements.push({
      data: { id: edge.id, source: edge.source, target: edge.target },
      classes: 'link',
    });
  }
  return elements;
}

export function newNodeIds(previousIds, view) {
  const known = new Set(previousIds);
  return view.nodes.map((node) => node.id).filter((id) => !known.has(id));
}
```

- [ ] **Step 5: Implement `frontend/static/test-harness.html`**

```html
<!doctype html>
<meta charset="utf-8">
<title>graph-model test harness</title>
<script type="module">
  import * as model from './graph-model.js';
  window.kgModel = model;
</script>
```

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_graph_model.py -v`
Expected: PASS (8 tests)

- [ ] **Step 7: Commit**

```bash
git add frontend/static/graph-model.js frontend/static/test-harness.html frontend/static/vendor/cytoscape.min.js tests/conftest.py tests/test_graph_model.py
git commit -m "feat: browser display-filter logic with playwright tests"
```

---

### Task 14: Projection renderer, camera and themes

**Files:**
- Create: `frontend/static/camera.js`, `frontend/static/projection.js`, `frontend/static/render-harness.html`, `frontend/static/base.css`, `frontend/static/theme-a.css`, `frontend/static/theme-b.css`, `frontend/static/theme-c.css`
- Modify: `frontend/projection.html`
- Test: `tests/test_camera.py`, `tests/test_projection.py`

**Interfaces:**
- Consumes: `graph-model.js` (Task 13), the vendored Cytoscape build (Task 13), `/events` + `/graph.json` + `POST /api/positions` (Task 12).
- Produces:
  - `camera.js`: `class Camera(cy, {panSpeed})` with `setMode(mode)`, `get mode()`, `onGraphChanged()`, `step(dtSeconds)`.
  - `projection.js`: `createGraphView(container, {onPositions}) -> {cy, camera, update(graph, minMentions), setMinMentions(value)}`.
  - `projection.html` exposes `window.kgView` (used by Task 20's pre-render and by these tests).

The camera is its own component **from the start**, even if everything ends up fitting (spec §10.3): `fit` (fit-all), `manual` (zoom/pan by hand or touch), `pan` (slow automatic pan — this mode *is* the touch fallback). Node design: person = portrait circle with a golden ring, no name, no quote; term = its label, the only text in the net (spec §10.2).

**Touch needs no gesture code here.** Cytoscape.js handles Pointer Events (pinch-zoom, drag-pan) natively in `manual` mode. What must be true is a hardware property — the device registers as an HID multitouch digitizer, not an HID mouse — and that check belongs on site (`dmesg | grep -i hid`, `libinput list-devices` → `ABS_MT_*` axes); it goes into `docs/operations.md` in Task 21. If touch is absent, mode `pan` carries the station (spec §10.6).

- [ ] **Step 1: Write the failing tests**

`tests/test_camera.py`:

```python
import pytest

CY_STUB = """
window.cyStub = {
  calls: [],
  // Interactivity toggles are recorded separately from `calls` so that
  // existing assertions on `calls` (e.g. "manual mode produces zero calls")
  // are unaffected by the interactivity gating the camera also does now.
  interactivity: [],
  _pan: {x: 0, y: 0},
  _zoom: 1,
  _panningEnabled: true,
  _zoomingEnabled: true,
  _autoungrabify: false,
  fit(padding) { this.calls.push(['fit', padding]); },
  pan(p) { if (p === undefined) return this._pan; this._pan = p; this.calls.push(['pan', p]); },
  zoom(z) { if (z === undefined) return this._zoom; this._zoom = z; },
  extent() { return {x1: 0, y1: 0, x2: 4000, y2: 1000, w: 4000, h: 1000}; },
  width() { return 1920; },
  height() { return 1080; },
  elements() { return {length: 4}; },
  userPanningEnabled(v) {
    if (v === undefined) return this._panningEnabled;
    this._panningEnabled = v;
    this.interactivity.push(['userPanningEnabled', v]);
  },
  userZoomingEnabled(v) {
    if (v === undefined) return this._zoomingEnabled;
    this._zoomingEnabled = v;
    this.interactivity.push(['userZoomingEnabled', v]);
  },
  autoungrabify(v) {
    if (v === undefined) return this._autoungrabify;
    this._autoungrabify = v;
    this.interactivity.push(['autoungrabify', v]);
  },
};
"""


@pytest.fixture()
def camera(page, static_server):
    page.goto(f"{static_server}/frontend/static/test-harness.html")
    page.evaluate(CY_STUB)
    page.evaluate(
        """async () => {
             const { Camera } = await import('./camera.js');
             window.cam = new Camera(window.cyStub, { panSpeed: 100 });
           }"""
    )
    return page


def test_default_mode_is_fit_and_fits_on_graph_change(camera):
    assert camera.evaluate("window.cam.mode") == "fit"
    camera.evaluate("window.cam.onGraphChanged()")
    assert camera.evaluate("window.cyStub.calls.filter(c => c[0] === 'fit').length") == 1


def test_manual_mode_never_moves_the_viewport_by_itself(camera):
    camera.evaluate("window.cam.setMode('manual')")
    camera.evaluate("window.cam.onGraphChanged()")
    camera.evaluate("window.cam.step(1.0)")
    assert camera.evaluate("window.cyStub.calls.length") == 0


def test_pan_mode_moves_the_viewport_over_time(camera):
    camera.evaluate("window.cam.setMode('pan')")
    camera.evaluate("window.cam.step(1.0)")
    first = camera.evaluate("window.cyStub._pan.x")
    camera.evaluate("window.cam.step(1.0)")
    second = camera.evaluate("window.cyStub._pan.x")
    assert first != 0
    assert second != first


def test_pan_reverses_at_the_edge_instead_of_running_away(camera):
    camera.evaluate("window.cam.setMode('pan')")
    camera.evaluate("for (let i = 0; i < 400; i++) window.cam.step(1.0)")
    positions = camera.evaluate(
        "window.cyStub.calls.filter(c => c[0] === 'pan').map(c => c[1].x)"
    )
    assert min(positions) > -100000 and max(positions) < 100000
    assert any(a > b for a, b in zip(positions, positions[1:]))  # direction reversed


def test_an_unknown_mode_is_rejected(camera):
    assert camera.evaluate("(() => { try { window.cam.setMode('warp'); return 'no'; } catch (e) { return 'raised'; } })()") == "raised"


def test_initial_fit_mode_disables_panning_zooming_and_grabbing(camera):
    # A stray touch/mouse must not be able to pan the wall or drag a node off
    # its persisted position from the moment the camera is constructed, not
    # only from the first setMode() call onward.
    assert camera.evaluate("window.cyStub._panningEnabled") is False
    assert camera.evaluate("window.cyStub._zoomingEnabled") is False
    assert camera.evaluate("window.cyStub._autoungrabify") is True


def test_manual_mode_enables_panning_zooming_and_grabbing(camera):
    camera.evaluate("window.cyStub.interactivity.length = 0")
    camera.evaluate("window.cam.setMode('manual')")
    calls = camera.evaluate("window.cyStub.interactivity")
    assert ["userPanningEnabled", True] in calls
    assert ["userZoomingEnabled", True] in calls
    assert ["autoungrabify", False] in calls
    assert camera.evaluate("window.cyStub._panningEnabled") is True
    assert camera.evaluate("window.cyStub._zoomingEnabled") is True
    assert camera.evaluate("window.cyStub._autoungrabify") is False


def test_fit_and_pan_modes_disable_panning_zooming_and_grabbing(camera):
    for mode in ("fit", "pan"):
        camera.evaluate("window.cyStub.interactivity.length = 0")
        camera.evaluate(f"window.cam.setMode('{mode}')")
        calls = camera.evaluate("window.cyStub.interactivity")
        assert ["userPanningEnabled", False] in calls, mode
        assert ["userZoomingEnabled", False] in calls, mode
        assert ["autoungrabify", True] in calls, mode
        assert camera.evaluate("window.cyStub._panningEnabled") is False, mode
        assert camera.evaluate("window.cyStub._zoomingEnabled") is False, mode
        assert camera.evaluate("window.cyStub._autoungrabify") is True, mode
```

`tests/test_projection.py`:

```python
import pytest

GRAPH_1 = {
    "version": 1,
    "min_mentions": 1,
    "nodes": [
        {"id": "p1", "type": "person", "portrait": "", "hidden": False, "x": 100, "y": 100},
        {"id": "t1", "type": "term", "label": "Holzbau", "mentions": 1, "hidden": False, "x": None, "y": None},
    ],
    "edges": [{"id": "e1", "source": "p1", "target": "t1"}],
    "quotes": [],
}

GRAPH_2 = {
    "version": 1,
    "min_mentions": 1,
    "nodes": GRAPH_1["nodes"]
    + [
        {"id": "p2", "type": "person", "portrait": "", "hidden": False, "x": None, "y": None},
        {"id": "t2", "type": "term", "label": "Bodenpreise", "mentions": 1, "hidden": False, "x": None, "y": None},
    ],
    "edges": GRAPH_1["edges"] + [{"id": "e2", "source": "p2", "target": "t2"}],
    "quotes": [],
}


@pytest.fixture()
def view(page, static_server):
    page.goto(f"{static_server}/frontend/static/render-harness.html")
    page.wait_for_function("window.kgView !== undefined")
    return page


def wait_for_layout(page):
    """The cose layout is animated (LAYOUT.animationDuration) and positions are
    only reported at `layoutstop`. Wait for the real signal — a fixed timeout
    shorter than the animation would make these tests flaky."""
    page.wait_for_function("() => window.kgView.layoutPending === false")


def update(page, graph, min_mentions=1):
    page.evaluate("(args) => window.kgView.update(args[0], args[1])", [graph, min_mentions])
    wait_for_layout(page)


def test_nodes_and_edges_are_rendered(view):
    update(view, GRAPH_1)
    assert view.evaluate("window.kgView.cy.nodes().length") == 2
    assert view.evaluate("window.kgView.cy.edges().length") == 1
    assert view.evaluate("window.kgView.cy.$('#p1').hasClass('person')") is True


def test_a_persisted_position_is_honoured_exactly(view):
    update(view, GRAPH_1)
    assert view.evaluate("window.kgView.cy.$('#p1').position()") == {"x": 100, "y": 100}


def test_existing_nodes_never_move_when_new_nodes_arrive(view):
    update(view, GRAPH_1)
    before = view.evaluate("window.kgView.cy.$('#t1').position()")

    update(view, GRAPH_2)

    after = view.evaluate("window.kgView.cy.$('#t1').position()")
    assert after == before
    assert view.evaluate("window.kgView.cy.nodes().length") == 4


def test_new_node_positions_are_reported_for_persistence(view):
    update(view, GRAPH_1)
    view.evaluate("window.kgPositions.length = 0")

    update(view, GRAPH_2)

    reported = view.evaluate("Object.keys(Object.assign({}, ...window.kgPositions))")
    assert "p2" in reported and "t2" in reported


THEME_RING_COLOR = {
    # Declared --ring-color tokens from the theme files, as Cytoscape reports
    # a resolved colour back through its own style API (rgb(...), no spaces).
    "a": "rgb(201,162,39)",  # theme-a.css --ring-color: #C9A227
    "b": "rgb(138,107,31)",  # theme-b.css --ring-color: #8A6B1F
    "c": "rgb(224,181,49)",  # theme-c.css --ring-color: #E0B531
}

ONE_PERSON = {
    "version": 1,
    "min_mentions": 1,
    "nodes": [{"id": "p1", "type": "person", "portrait": "", "hidden": False, "x": 0, "y": 0}],
    "edges": [],
    "quotes": [],
}


def test_theme_query_param_reaches_the_baked_cytoscape_style(page, static_server):
    # Regression test for a bug where createGraphView() ran before the
    # `?theme=` stylesheet swap had actually loaded: cssVar() reads through
    # getComputedStyle synchronously, so it silently baked in the PREVIOUS
    # (default theme-a) stylesheet's values regardless of `?theme=`. Only the
    # live CSS background (base.css `background: var(--bg)`) ever switched.
    # A test that only checks the background would not catch this — it must
    # read a value Cytoscape itself baked into style, through Cytoscape's own
    # API, on a real Chromium page loading the actual `projection.html`.
    colors = {}
    for theme in ("a", "b", "c"):
        page.goto(f"{static_server}/frontend/projection.html?theme={theme}")
        page.wait_for_function("window.kgView !== undefined")
        page.evaluate("(g) => window.kgView.update(g, 1)", ONE_PERSON)
        wait_for_layout(page)
        colors[theme] = page.evaluate("window.kgView.cy.$('#p1').style('border-color')")

    assert colors["a"] != colors["b"] != colors["c"] != colors["a"]
    assert colors == THEME_RING_COLOR


def test_unknown_theme_falls_back_and_still_renders(page, static_server):
    # Regression test: a `?theme=` value that does not resolve to an existing
    # stylesheet must never leave the theme-load promise unresolved forever.
    # That is the worst failure mode for an unattended wall — window.kgView
    # never gets set, /events never connects, and the projection shows
    # nothing indefinitely with no operator recourse. A bad theme must
    # degrade to the default theme and still render, not hang. The wait is
    # bounded so a regression fails the suite instead of hanging it.
    page.goto(f"{static_server}/frontend/projection.html?theme=nonexistent")
    page.wait_for_function("window.kgView !== undefined", timeout=5000)
    page.evaluate("(g) => window.kgView.update(g, 1)", ONE_PERSON)
    page.wait_for_function("() => window.kgView.layoutPending === false", timeout=5000)
    assert page.evaluate("window.kgView.cy.nodes().length") == 1


def test_raising_the_dial_removes_terms_without_touching_the_rest(view):
    update(view, GRAPH_2)
    person_position = view.evaluate("window.kgView.cy.$('#p1').position()")

    view.evaluate("window.kgView.setMinMentions(2)")
    wait_for_layout(view)

    assert view.evaluate("window.kgView.cy.$('#t1').length") == 0
    assert view.evaluate("window.kgView.cy.$('#p1').length") == 1
    view.evaluate("window.kgView.setMinMentions(1)")
    wait_for_layout(view)
    assert view.evaluate("window.kgView.cy.$('#t1').length") == 1
    assert view.evaluate("window.kgView.cy.$('#p1').position()") == person_position
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `uv run pytest tests/test_camera.py tests/test_projection.py -v`
Expected: FAIL — `camera.js` / `render-harness.html` do not exist (404 / import error)

- [ ] **Step 3: Implement `frontend/static/camera.js`**

```javascript
// The camera is its own component from the start, even if everything fits.
// Mode 'pan' IS the touch fallback: a non-interactive automatic animation.

const MODES = ['fit', 'manual', 'pan'];

export class Camera {
  constructor(cy, { panSpeed = 18, padding = 60 } = {}) {
    this.cy = cy;
    this.panSpeed = panSpeed;
    this.padding = padding;
    this._mode = 'fit';
    this._direction = -1;
    // At an unattended exhibition a stray touch/mouse must never be able to
    // pan the viewport off-frame or drag a node off its persisted position.
    // `manual` is the only mode where a visitor is meant to move anything;
    // apply that for the initial mode too, not just from setMode onward.
    this._applyInteractivity(this._mode);
  }

  get mode() {
    return this._mode;
  }

  setMode(mode) {
    if (!MODES.includes(mode)) throw new Error(`unknown camera mode: ${mode}`);
    this._mode = mode;
    this._applyInteractivity(mode);
    if (mode === 'fit') this.cy.fit(this.padding);
  }

  _applyInteractivity(mode) {
    const interactive = mode === 'manual';
    this.cy.userPanningEnabled(interactive);
    this.cy.userZoomingEnabled(interactive);
    this.cy.autoungrabify(!interactive);
  }

  onGraphChanged() {
    if (this._mode === 'fit') this.cy.fit(this.padding);
  }

  step(dtSeconds) {
    if (this._mode !== 'pan') return;
    const extent = this.cy.extent();
    const graphWidth = extent.x2 - extent.x1;
    if (graphWidth <= 0) return;
    const pan = this.cy.pan();
    const dx = this._direction * this.panSpeed * dtSeconds;
    const next = pan.x + dx;
    const limit = Math.max(graphWidth, this.cy.width());
    if (next < -limit || next > limit) this._direction *= -1;
    this.cy.pan({ x: pan.x + this._direction * this.panSpeed * dtSeconds, y: pan.y });
  }
}
```

- [ ] **Step 4: Implement `frontend/static/projection.js`**

```javascript
import { newNodeIds, toCytoscape, visibleGraph } from './graph-model.js';
import { Camera } from './camera.js';

function cssVar(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function style() {
  return [
    {
      selector: 'node.person',
      style: {
        shape: 'ellipse',
        width: cssVar('--person-size', '96'),
        height: cssVar('--person-size', '96'),
        'background-color': cssVar('--person-fill', '#222'),
        'background-image': (ele) => ele.data('portrait') || 'none',
        'background-fit': 'cover',
        'border-width': cssVar('--ring-width', '5'),
        'border-color': cssVar('--ring-color', '#C9A227'),
        label: '',
      },
    },
    {
      selector: 'node.term',
      style: {
        shape: 'ellipse',
        width: cssVar('--term-dot', '14'),
        height: cssVar('--term-dot', '14'),
        'background-color': cssVar('--term-dot-color', '#EDE7D8'),
        label: 'data(label)',
        color: cssVar('--label-color', '#F5F1E6'),
        'font-family': cssVar('--label-font', 'Georgia, serif'),
        'font-size': cssVar('--label-size', '22'),
        'text-valign': 'bottom',
        'text-margin-y': 6,
        'text-wrap': 'wrap',
        'text-max-width': '220px',
        'text-outline-width': cssVar('--label-outline-width', '3'),
        'text-outline-color': cssVar('--label-outline-color', '#101014'),
      },
    },
    {
      selector: 'edge.link',
      style: {
        width: cssVar('--edge-width', '2'),
        'line-color': cssVar('--edge-color', '#8A8578'),
        'curve-style': 'straight',
        opacity: cssVar('--edge-opacity', '0.75'),
      },
    },
  ];
}

const LAYOUT = {
  name: 'cose',
  randomize: false,
  animate: true,
  animationDuration: 1200,
  fit: false,
  padding: 60,
  nodeRepulsion: 12000,
  idealEdgeLength: 160,
  nodeDimensionsIncludeLabels: true,
};

export function createGraphView(container, { onPositions = () => {} } = {}) {
  const cy = cytoscape({ container, style: style(), wheelSensitivity: 0.2 });
  const camera = new Camera(cy);
  let lastGraph = { nodes: [], edges: [], min_mentions: 1 };
  let minMentions = 1;
  // True while an animated layout is running. Tests and the pre-render wait on
  // this instead of guessing a timeout; positions land only at `layoutstop`.
  let layoutPending = false;

  function render() {
    const view = visibleGraph(lastGraph, minMentions);
    const wanted = new Set(view.nodes.map((n) => n.id).concat(view.edges.map((e) => e.id)));
    const present = cy.elements().map((el) => el.id());

    // Remove what dropped out of the view. Positions of the rest are untouched.
    cy.elements()
      .filter((el) => !wanted.has(el.id()))
      .remove();

    // A node that arrives with a persisted position is NOT "fresh": it is
    // already placed and must be locked like any long-standing node (spec 11).
    const placed = new Set(
      view.nodes
        .filter((n) => n.x !== null && n.x !== undefined && n.y !== null && n.y !== undefined)
        .map((n) => n.id),
    );
    const fresh = newNodeIds(present, view).filter((id) => !placed.has(id));
    const toAdd = toCytoscape(view).filter((el) => cy.$id(el.data.id).length === 0);
    if (toAdd.length) cy.add(toAdd);

    if (fresh.length) {
      // Seed each new node next to a neighbour it already has, so the layout
      // starts from a sensible place instead of the origin. The offset is
      // derived from the index (golden angle), not random: two pre-render runs
      // over the same graph must produce the same picture.
      fresh.forEach((id, index) => {
        const node = cy.$id(id);
        // `fresh` already excludes every id in `placed` (an explicit x/y
        // null-check against the graph data, not a truthy check on the
        // rendered position), so every node reached here is genuinely
        // unseeded and must always be positioned. A `position('x') ||
        // position('y')` guard here would be confused by a node legitimately
        // seeded to exactly (0, 0) and skip it.
        const anchor = node.neighborhood('node').filter((n) => !fresh.includes(n.id()))[0];
        const base = anchor ? anchor.position() : { x: 0, y: 0 };
        const angle = index * 2.39996;
        node.position({ x: base.x + Math.cos(angle) * 140, y: base.y + Math.sin(angle) * 140 });
      });
      // Existing nodes are locked: the net must never re-shuffle (spec 11).
      const existing = cy.nodes().filter((n) => !fresh.includes(n.id()));
      existing.lock();
      const layout = cy.layout(LAYOUT);
      layoutPending = true;
      layout.one('layoutstop', () => {
        existing.unlock();
        const positions = {};
        cy.nodes().forEach((n) => {
          positions[n.id()] = { x: n.position('x'), y: n.position('y') };
        });
        onPositions(positions);
        camera.onGraphChanged();
        layoutPending = false;
      });
      layout.run();
    } else {
      camera.onGraphChanged();
    }
  }

  let last = performance.now();
  function tick(now) {
    camera.step((now - last) / 1000);
    last = now;
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);

  return {
    cy,
    camera,
    get layoutPending() {
      return layoutPending;
    },
    update(graph, value) {
      lastGraph = graph;
      if (value !== undefined) minMentions = value;
      else if (graph.min_mentions) minMentions = graph.min_mentions;
      render();
    },
    setMinMentions(value) {
      minMentions = value;
      render();
    },
  };
}
```

- [ ] **Step 5: Implement the harness, the page and the themes**

`frontend/static/render-harness.html`:

```html
<!doctype html>
<meta charset="utf-8">
<title>render harness</title>
<link rel="stylesheet" href="./base.css">
<link rel="stylesheet" href="./theme-a.css">
<style>#cy { width: 1920px; height: 1080px; }</style>
<div id="cy"></div>
<script src="./vendor/cytoscape.min.js"></script>
<script type="module">
  import { createGraphView } from './projection.js';
  window.kgPositions = [];
  window.kgView = createGraphView(document.getElementById('cy'), {
    onPositions: (p) => window.kgPositions.push(p),
  });
</script>
```

`frontend/projection.html`:

```html
<!doctype html>
<html lang="de">
<meta charset="utf-8">
<title>Kollektivgedächtnis</title>
<!-- Asset paths are relative so the page also loads from a plain file server
     (tests, pre-render harness); served at /projection they resolve to /static/… -->
<link rel="stylesheet" href="static/base.css">
<link id="theme" rel="stylesheet" href="static/theme-a.css">
<div id="cy"></div>
<script src="static/vendor/cytoscape.min.js"></script>
<script type="module">
  import { createGraphView } from './static/projection.js';

  const themeLink = document.getElementById('theme');
  const params = new URLSearchParams(location.search);
  // Validate against the themes that actually exist. This is an unattended
  // wall, not a form with a user to correct a typo: an unrecognised
  // `?theme=` value (typo, retired name, anything) must fall back to the
  // default rather than ever producing a broken href.
  const KNOWN_THEMES = ['a', 'b', 'c'];
  const requestedTheme = params.get('theme');
  const theme = KNOWN_THEMES.includes(requestedTheme) ? requestedTheme : 'a';
  const themeHref = `static/theme-${theme}.css`;
  // Swapping `href` starts an async fetch. createGraphView() reads the
  // stylesheet synchronously via getComputedStyle (projection.js's cssVar()),
  // so it must not run until the new stylesheet has actually loaded — a
  // requestAnimationFrame is not a substitute for the real `load` event,
  // it only guarantees a paint tick, not that the async fetch resolved.
  // Reassigning `href` to the value it already has (the `?theme=a` default,
  // matching the markup's initial href) does NOT fire another `load` event
  // in Chromium, so that case must resolve immediately instead of waiting.
  const themeLoaded = new Promise((resolve) => {
    if (themeLink.getAttribute('href') === themeHref) {
      resolve();
      return;
    }
    themeLink.addEventListener('load', resolve, { once: true });
    // Defensive fallback for a legitimate theme file missing or broken at
    // deploy time (the `?theme=` value itself is already validated above,
    // so this only fires for a deploy-time asset problem). A stylesheet
    // that fails to load fires `error`, never `load` — without this, the
    // promise above would hang forever and the wall would show nothing
    // indefinitely with no operator recourse. A degraded render (whatever
    // CSS state exists) beats a blank wall.
    themeLink.addEventListener(
      'error',
      () => {
        console.warn(`theme stylesheet failed to load: ${themeHref}`);
        resolve();
      },
      { once: true },
    );
    themeLink.href = themeHref;
  });

  themeLoaded.then(() => {
    const view = createGraphView(document.getElementById('cy'), {
      onPositions: (positions) =>
        fetch('/api/positions', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ positions }),
        }).catch((error) => console.warn('failed to persist positions', error)),
    });
    window.kgView = view;
    window.kgReady = false;

    const events = new EventSource('/events');
    events.onmessage = (message) => {
      const payload = JSON.parse(message.data);
      if (payload.type === 'graph') {
        view.update(payload.graph);
        window.kgReady = true;
      } else if (payload.type === 'state') {
        view.setMinMentions(payload.state.min_mentions);
        view.camera.setMode(payload.state.camera_mode);
      }
    };
  });
</script>
</html>
```

`frontend/static/base.css`:

```css
html, body { margin: 0; padding: 0; overflow: hidden; background: var(--bg); }
#cy { position: fixed; inset: 0; width: 100vw; height: 100vh; }
```

`frontend/static/theme-a.css` — **A: dark mode as in the concept rendering (reference)**:

```css
:root {
  --bg: #101014;
  --person-size: 96;
  --person-fill: #23232a;
  --ring-color: #C9A227;
  --ring-width: 5;
  --term-dot: 14;
  --term-dot-color: #EDE7D8;
  --label-color: #F5F1E6;
  --label-font: Georgia, "Times New Roman", serif;
  --label-size: 22;
  --label-outline-width: 3;
  --label-outline-color: #101014;
  --edge-color: #8A8578;
  --edge-width: 2;
  --edge-opacity: 0.75;
}
```

`frontend/static/theme-b.css` — **B: inverted, light ground, dark lines/labels** (the whiteboard's own white is the darkest available "black"):

```css
:root {
  --bg: #F4F1EA;
  --person-size: 96;
  --person-fill: #E2DED3;
  --ring-color: #8A6B1F;
  --ring-width: 5;
  --term-dot: 14;
  --term-dot-color: #2B2B2B;
  --label-color: #1A1A1A;
  --label-font: Georgia, "Times New Roman", serif;
  --label-size: 22;
  --label-outline-width: 2;
  --label-outline-color: #F4F1EA;
  --edge-color: #4A4A4A;
  --edge-width: 2;
  --edge-opacity: 0.85;
}
```

`frontend/static/theme-c.css` — **C: dark mode with markedly heavier strokes and a larger minimum font**:

```css
:root {
  --bg: #101014;
  --person-size: 112;
  --person-fill: #23232a;
  --ring-color: #E0B531;
  --ring-width: 9;
  --term-dot: 20;
  --term-dot-color: #FFFFFF;
  --label-color: #FFFFFF;
  --label-font: Georgia, "Times New Roman", serif;
  --label-size: 30;
  --label-outline-width: 5;
  --label-outline-color: #101014;
  --edge-color: #C8C3B4;
  --edge-width: 4;
  --edge-opacity: 1;
}
```

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_camera.py tests/test_projection.py -v`
Expected: PASS (15 tests) — verified by a real run on 2026-08-13 during the
task-14 review-findings pass (8 camera + 7 projection; the original brief's
10 became 15 after adding the camera-interactivity tests for finding 3, the
theme-baking regression test for finding 1, and the theme-error-fallback
regression test for the finding-2 follow-up (a bad `?theme=` value must
degrade to the default theme and still render instead of hanging the
theme-load promise forever).

- [ ] **Step 7: Commit**

```bash
git add frontend/static/camera.js frontend/static/projection.js frontend/static/render-harness.html frontend/static/base.css frontend/static/theme-a.css frontend/static/theme-b.css frontend/static/theme-c.css frontend/projection.html tests/test_camera.py tests/test_projection.py
git commit -m "feat: projection renderer, camera modes and comparison themes"
```

---

### Task 15: Operator UI

**Files:**
- Create: `frontend/static/operator.js`, `frontend/static/operator.css`
- Modify: `frontend/operator.html`
- Test: `tests/test_operator_ui.py`

**Interfaces:**
- Consumes: `/graph.json`, `/events`, `/api/*` (Task 12).
- Produces: `frontend/operator.html` exposing `window.kgOperator = {render(graph, state)}` so the DOM logic is testable without a live server.

The operator page has exactly: the running transcript (partials), the one density dial, the camera mode switch, and a list of entries with exactly one action each — **hide** (spec §7, §8). No approve, no edit, no queue.

- [ ] **Step 1: Write the failing test**

`tests/test_operator_ui.py`:

```python
import pytest

GRAPH = {
    "min_mentions": 1,
    "nodes": [
        {"id": "p1", "type": "person", "portrait": "", "hidden": False, "created_at": 2},
        {"id": "t1", "type": "term", "label": "Holzbau", "mentions": 2, "hidden": False, "created_at": 3},
        {"id": "t2", "type": "term", "label": "Unfug", "mentions": 1, "hidden": True, "created_at": 4},
    ],
    "edges": [],
    "quotes": [{"id": "q1", "person_id": "p1", "text": "Wir bauen zu viel."}],
}
STATE = {"min_mentions": 2, "camera_mode": "pan", "stt_connected": True, "interview": None}


@pytest.fixture()
def ui(page, static_server):
    page.goto(f"{static_server}/frontend/operator.html")
    page.wait_for_function("window.kgOperator !== undefined")
    page.evaluate("window.kgFetches = []")
    page.evaluate(
        "window.fetch = (url, opts) => { window.kgFetches.push([url, JSON.parse(opts.body)]);"
        " return Promise.resolve({ok: true, json: () => Promise.resolve({})}); }"
    )
    page.evaluate("(args) => window.kgOperator.render(args[0], args[1])", [GRAPH, STATE])
    return page


def test_entries_are_listed_newest_first_with_one_hide_button_each(ui):
    labels = ui.eval_on_selector_all(".entry .label", "els => els.map(e => e.textContent)")
    assert labels == ["Unfug", "Holzbau"]
    assert ui.eval_on_selector_all(".entry button.hide", "els => els.length") == 2
    assert ui.eval_on_selector_all(".entry button", "els => els.length") == 2  # no approve/edit


def test_hidden_entries_are_marked_and_offer_unhide(ui):
    assert ui.eval_on_selector("#entry-t2", "el => el.classList.contains('hidden')") is True
    assert ui.eval_on_selector("#entry-t2 button.hide", "el => el.textContent") == "einblenden"


def test_clicking_hide_posts_the_flag(ui):
    ui.click("#entry-t1 button.hide")
    assert ui.evaluate("window.kgFetches[0]") == ["/api/hidden", {"node_id": "term:t1", "hidden": True}]


def test_the_density_dial_reflects_state_and_posts_changes(ui):
    assert ui.eval_on_selector("#min-mentions", "el => el.value") == "2"
    ui.select_option("#min-mentions", "3")
    assert ui.evaluate("window.kgFetches.at(-1)") == ["/api/min_mentions", {"value": 3}]


def test_the_camera_switch_reflects_state_and_posts_changes(ui):
    assert ui.eval_on_selector("#camera", "el => el.value") == "pan"
    ui.select_option("#camera", "fit")
    assert ui.evaluate("window.kgFetches.at(-1)") == ["/api/camera", {"mode": "fit"}]


def test_the_transcript_area_shows_partials(ui):
    ui.evaluate("window.kgOperator.showTranscript('wir bauen zu viel neu')")
    assert ui.eval_on_selector("#transcript", "el => el.textContent") == "wir bauen zu viel neu"


def test_stt_connection_state_is_visible(ui):
    assert ui.eval_on_selector("#stt", "el => el.classList.contains('ok')") is True
    ui.evaluate(
        "(args) => window.kgOperator.render(args[0], args[1])",
        [GRAPH, {**STATE, "stt_connected": False}],
    )
    assert ui.eval_on_selector("#stt", "el => el.classList.contains('ok')") is False
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_operator_ui.py -v`
Expected: FAIL — timeout waiting for `window.kgOperator`

- [ ] **Step 3: Implement `frontend/operator.html`**

```html
<!doctype html>
<html lang="de">
<meta charset="utf-8">
<title>Kollektivgedächtnis — Operator</title>
<!-- Relative, like projection.html: served at /operator these resolve to /static/… -->
<link rel="stylesheet" href="static/operator.css">
<header>
  <span id="stt" class="badge">STT</span>
  <label>Dichte
    <select id="min-mentions">
      <option value="1">1 — alles</option>
      <option value="2">2 — geteilt</option>
      <option value="3">3 — nur häufig</option>
    </select>
  </label>
  <label>Kamera
    <select id="camera">
      <option value="fit">alles zeigen</option>
      <option value="manual">manuell</option>
      <option value="pan">automatisch schwenken</option>
    </select>
  </label>
  <span id="interview"></span>
</header>
<pre id="transcript"></pre>
<ul id="entries"></ul>
<script type="module" src="static/operator.js"></script>
</html>
```

- [ ] **Step 4: Implement `frontend/static/operator.js`**

```javascript
// One action per entry: hide. No approving, no editing, no queue (spec 8).

function post(url, body) {
  return fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
}

function entryRow(node) {
  const item = document.createElement('li');
  item.className = `entry ${node.hidden ? 'hidden' : ''}`.trim();
  item.id = `entry-${node.id}`;

  const label = document.createElement('span');
  label.className = 'label';
  label.textContent = node.type === 'term' ? node.label : node.id;
  item.appendChild(label);

  const meta = document.createElement('span');
  meta.className = 'meta';
  meta.textContent = node.type === 'term' ? `${node.mentions}×` : 'Person';
  item.appendChild(meta);

  const button = document.createElement('button');
  button.className = 'hide';
  button.textContent = node.hidden ? 'einblenden' : 'ausblenden';
  button.addEventListener('click', () =>
    post('/api/hidden', { node_id: `${node.type}:${node.id}`, hidden: !node.hidden }),
  );
  item.appendChild(button);
  return item;
}

function render(graph, state) {
  document.getElementById('min-mentions').value = String(state.min_mentions);
  document.getElementById('camera').value = state.camera_mode;
  document.getElementById('stt').classList.toggle('ok', Boolean(state.stt_connected));
  document.getElementById('interview').textContent = state.interview
    ? 'Interview läuft'
    : 'kein Interview';

  const list = document.getElementById('entries');
  list.replaceChildren();
  graph.nodes
    .filter((node) => node.type === 'term')
    .slice()
    .sort((a, b) => (b.created_at || 0) - (a.created_at || 0))
    .forEach((node) => list.appendChild(entryRow(node)));
}

function showTranscript(text) {
  document.getElementById('transcript').textContent = text;
}

document.getElementById('min-mentions').addEventListener('change', (event) =>
  post('/api/min_mentions', { value: Number(event.target.value) }),
);
document.getElementById('camera').addEventListener('change', (event) =>
  post('/api/camera', { mode: event.target.value }),
);

window.kgOperator = { render, showTranscript };

let graph = { nodes: [], edges: [], quotes: [] };
let state = { min_mentions: 1, camera_mode: 'fit', stt_connected: false, interview: null };
const events = new EventSource('/events');
events.onmessage = (message) => {
  const payload = JSON.parse(message.data);
  if (payload.type === 'graph') graph = payload.graph;
  else if (payload.type === 'state') state = payload.state;
  else if (payload.type === 'transcript') return showTranscript(payload.text);
  render(graph, state);
};
```

- [ ] **Step 5: Implement `frontend/static/operator.css`**

```css
body { font: 15px/1.5 system-ui, sans-serif; margin: 0; background: #16161a; color: #eee; }
header { display: flex; gap: 1.5rem; align-items: center; padding: 0.75rem 1rem; background: #1f1f26; }
select { font: inherit; padding: 0.2rem; }
.badge { padding: 0.15rem 0.5rem; border-radius: 3px; background: #7a2626; }
.badge.ok { background: #2c6e3f; }
#transcript { margin: 0; padding: 0.75rem 1rem; min-height: 4rem; color: #b9b9c4; white-space: pre-wrap; }
#entries { list-style: none; margin: 0; padding: 0 1rem 2rem; }
.entry { display: flex; gap: 1rem; align-items: center; padding: 0.5rem 0; border-bottom: 1px solid #2a2a33; }
.entry .label { flex: 1; }
.entry .meta { color: #8b8b96; }
.entry.hidden .label { text-decoration: line-through; color: #7a7a85; }
button.hide { font: inherit; padding: 0.25rem 0.75rem; cursor: pointer; }
```

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_operator_ui.py -v`
Expected: PASS (7 tests)

- [ ] **Step 7: Commit**

```bash
git add frontend/operator.html frontend/static/operator.js frontend/static/operator.css tests/test_operator_ui.py
git commit -m "feat: operator UI with the density dial and hide button"
```

---

### Task 16: Legibility test pattern (comparison series D)

**Files:**
- Create: `frontend/testpattern.html`, `frontend/static/theme-d.css`
- Modify: `kg/server.py` (add the `/testpattern` route)
- Test: `tests/test_testpattern.py`

**Interfaces:**
- Consumes: nothing (self-contained page).
- Produces: `GET /testpattern` — a 1920×1080 page with an 11-step greyscale wedge and a font-size ladder, used on site to measure the real black level on the whiteboard and the legibility limit (spec §10.4 variant D).

- [ ] **Step 1: Write the failing test**

`tests/test_testpattern.py`:

```python
import pytest


@pytest.fixture()
def pattern(page, static_server):
    page.goto(f"{static_server}/frontend/testpattern.html")
    page.wait_for_selector(".wedge")
    return page


def test_the_greyscale_wedge_has_eleven_steps_from_black_to_white(pattern):
    steps = pattern.eval_on_selector_all(".wedge .step", "els => els.map(e => e.dataset.value)")
    assert steps == [str(v) for v in range(0, 101, 10)]


def test_the_font_ladder_covers_the_expected_sizes(pattern):
    sizes = pattern.eval_on_selector_all(".ladder .rung", "els => els.map(e => e.dataset.size)")
    assert sizes == ["14", "18", "22", "26", "30", "36", "44"]


def test_each_rung_shows_a_real_term_label_not_lorem_ipsum(pattern):
    texts = pattern.eval_on_selector_all(".ladder .rung", "els => els.map(e => e.textContent)")
    assert all("Betonspritzen mit Drohnen" in text for text in texts)


def test_the_page_fills_exactly_1920x1080(pattern):
    size = pattern.evaluate("({w: document.body.scrollWidth, h: document.body.scrollHeight})")
    assert size == {"w": 1920, "h": 1080}
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_testpattern.py -v`
Expected: FAIL — 404 / selector `.wedge` never appears

- [ ] **Step 3: Implement `frontend/testpattern.html`**

```html
<!doctype html>
<html lang="de">
<meta charset="utf-8">
<title>Testbild — Whiteboard</title>
<!-- Ground comes from theme-d.css so the wedge is read against the same
     background as variant A, not against a hard-coded copy of it. -->
<link rel="stylesheet" href="static/theme-d.css">
<style>
  html, body { margin: 0; padding: 0; }
  body { width: 1920px; height: 1080px; overflow: hidden; background: var(--bg); color: #fff;
         font-family: Georgia, 'Times New Roman', serif; }
  .wedge { display: flex; height: 260px; }
  .wedge .step { flex: 1; display: flex; align-items: flex-end; justify-content: center;
                 font: 14px system-ui, sans-serif; padding-bottom: 8px; }
  .ladder { padding: 40px 60px; }
  .rung { margin-bottom: 18px; white-space: nowrap; }
  .rule { height: 2px; background: #fff; margin: 0 60px 30px; }
  .strokes { display: flex; gap: 40px; padding: 0 60px; align-items: center; }
  .strokes div { background: #fff; width: 240px; }
</style>
<div class="wedge"></div>
<div class="rule"></div>
<div class="ladder"></div>
<div class="strokes">
  <div style="height:1px"></div><div style="height:2px"></div>
  <div style="height:4px"></div><div style="height:6px"></div><div style="height:9px"></div>
</div>
<script>
  const wedge = document.querySelector('.wedge');
  for (let value = 0; value <= 100; value += 10) {
    const step = document.createElement('div');
    step.className = 'step';
    step.dataset.value = String(value);
    const channel = Math.round((value / 100) * 255);
    step.style.background = `rgb(${channel},${channel},${channel})`;
    step.style.color = value > 50 ? '#000' : '#fff';
    step.textContent = `${value}%`;
    wedge.appendChild(step);
  }

  const ladder = document.querySelector('.ladder');
  for (const size of [14, 18, 22, 26, 30, 36, 44]) {
    const rung = document.createElement('div');
    rung.className = 'rung';
    rung.dataset.size = String(size);
    rung.style.fontSize = `${size}px`;
    rung.textContent = `${size}px — Betonspritzen mit Drohnen · Genossenschaftliches Wohnen`;
    ladder.appendChild(rung);
  }
</script>
</html>
```

- [ ] **Step 4: Add `theme-d.css` and the server route**

`frontend/static/theme-d.css` — the test pattern's own background, so it is measured against the same ground as variant A:

```css
/* Variant D is the test pattern page, not a graph theme: it is rendered from
   /testpattern, not from /projection?theme=d. Its ground matches theme A so
   the greyscale wedge is read against the reference background. */
:root { --bg: #101014; }
```

`frontend/testpattern.html` must therefore link `base.css` and `theme-d.css` rather than carrying an inline `<style>` block for the background — otherwise this file is dead weight.

In `kg/server.py`, next to the `/operator` route:

```python
    @app.get("/testpattern")
    def testpattern() -> FileResponse:
        return FileResponse(FRONTEND / "testpattern.html")
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_testpattern.py tests/test_server.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/testpattern.html frontend/static/theme-d.css kg/server.py tests/test_testpattern.py
git commit -m "feat: whiteboard legibility test pattern (series D)"
```

---

### Task 17: Core wiring and entrypoint

**Files:**
- Create: `kg/core.py`, `kg/__main__.py`
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: Tasks 2, 3, 5, 8, 9, 11, 12.
- Produces:
  - `kg.core.Core(cfg, store, bus, transcript_log, llm, embedder, processor=process_interview)` with the sync callbacks `on_photo(photo_path, portrait_path, at)`, `on_text(text, at)`, `on_final(event)`, `on_partial(event)`, `on_stt_state(connected)`, the coroutine `run_tick_loop(interval=5.0)`, and `async def drain()` (tests + shutdown: process the queue and await running pipeline tasks).
  - `python -m kg [--config config.toml] [--no-telegram] [--no-stt]`

The person node with the portrait appears **immediately** on the photo trigger; terms grow only after the stop (spec §6). The pipeline therefore runs as a background task so the next photo is never blocked by a running LLM call.

- [ ] **Step 1: Write the failing test**

`tests/test_core.py`:

```python
import pytest

from kg.config import Config
from kg.bus import EventBus
from kg.core import Core
from kg.embeddings import HashEmbedder
from kg.pipeline import ProcessResult
from kg.store import Store
from kg.transcript import TranscriptionEvent, TranscriptLog


@pytest.fixture()
def core(tmp_path):
    cfg = Config(data_dir=tmp_path / "state", interview_timeout_s=900)
    store = Store.open(cfg.db_path)
    calls = []

    def processor(store_, cfg_, llm_, embedder_, log_, person_id, started_at, stopped_at):
        calls.append((person_id, started_at, stopped_at))
        return ProcessResult(person_id, "done", [], "")

    instance = Core(
        cfg=cfg,
        store=store,
        bus=EventBus(),
        transcript_log=TranscriptLog(cfg.transcript_log_path),
        llm=object(),
        embedder=HashEmbedder(dim=16),
        processor=processor,
    )
    instance.processed = calls
    yield instance
    store.close()


async def test_a_photo_creates_the_person_node_immediately(core):
    events = core.bus.subscribe()

    core.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await core.drain()

    person = core.store.open_person()
    assert person is not None
    assert person.portrait_path == "p.png"
    kinds = []
    while not events.empty():
        kinds.append(events.get_nowait()["type"])
    assert "graph" in kinds  # the wall learns about it at once
    assert core.processed == []  # nothing extracted yet


async def test_a_text_message_closes_the_interview_and_runs_the_pipeline(core):
    core.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await core.drain()

    core.on_text("fertig", at=200.0)
    await core.drain()

    assert core.store.open_person() is None
    assert core.processed == [("p1", 100.0, 200.0)]
    assert core.store.get_person("p1").stop_reason == "text"


async def test_a_spoken_command_in_a_final_closes_it(core):
    core.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await core.drain()

    core.on_final(TranscriptionEvent(type="final", text="okay, Interview beendet", timestamp=180.0))
    await core.drain()

    assert core.store.get_person("p1").stop_reason == "spoken"
    assert core.processed == [("p1", 100.0, 180.0)]


async def test_the_timeout_closes_a_forgotten_interview(core):
    core.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await core.drain()

    core.on_tick(now=1100.0)
    await core.drain()

    assert core.store.get_person("p1").stop_reason == "timeout"
    assert core.processed[0][2] == 1100.0


async def test_a_new_photo_closes_the_previous_interview_and_opens_the_next(core):
    core.on_photo(photo_path="a.jpg", portrait_path="a.png", at=100.0)
    await core.drain()
    core.on_photo(photo_path="b.jpg", portrait_path="b.png", at=400.0)
    await core.drain()

    assert core.store.get_person("p1").stop_reason == "new_photo"
    assert core.store.open_person().id == "p2"
    assert core.processed == [("p1", 100.0, 400.0)]


async def test_stop_signals_without_an_interview_do_nothing(core):
    core.on_text("hallo", at=10.0)
    core.on_tick(now=99999.0)
    await core.drain()

    assert core.store.list_persons() == []
    assert core.processed == []


async def test_partials_are_pushed_to_the_operator_but_not_stored(core):
    events = core.bus.subscribe()

    core.on_partial(TranscriptionEvent(type="partial", text="wir bau", timestamp=5.0))

    payload = events.get_nowait()
    assert payload == {"type": "transcript", "text": "wir bau"}
    assert not core.cfg.transcript_log_path.exists()


async def test_stt_connection_state_is_recorded_and_broadcast(core):
    events = core.bus.subscribe()

    core.on_stt_state(True)
    assert core.store.get_setting("stt_connected", "0") == "1"
    assert events.get_nowait()["type"] == "state"

    core.on_stt_state(False)
    assert core.store.get_setting("stt_connected", "0") == "0"


async def test_a_failing_pipeline_does_not_stop_the_core(tmp_path):
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)

    def exploding(*args, **kwargs):
        raise RuntimeError("boom")

    core = Core(
        cfg=cfg,
        store=store,
        bus=EventBus(),
        transcript_log=TranscriptLog(cfg.transcript_log_path),
        llm=object(),
        embedder=HashEmbedder(dim=16),
        processor=exploding,
    )
    core.on_photo(photo_path="p.jpg", portrait_path="p.png", at=100.0)
    await core.drain()
    core.on_text("stop", at=200.0)
    await core.drain()

    core.on_photo(photo_path="q.jpg", portrait_path="q.png", at=300.0)
    await core.drain()
    assert core.store.open_person().id == "p2"
    store.close()
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_core.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kg.core'`

- [ ] **Step 3: Implement `kg/core.py`**

```python
"""Wiring: Telegram + STT in, SQLite and the browser out. The only writer."""

from __future__ import annotations

import asyncio
import logging
import time

from kg.pipeline import process_interview
from kg.server import broadcast_graph, broadcast_state
from kg.session import SessionTracker

log = logging.getLogger(__name__)


class Core:
    def __init__(
        self,
        cfg,
        store,
        bus,
        transcript_log,
        llm,
        embedder,
        processor=process_interview,
    ) -> None:
        self.cfg = cfg
        self.store = store
        self.bus = bus
        self.transcript_log = transcript_log
        self.llm = llm
        self.embedder = embedder
        self.processor = processor
        self.tracker = SessionTracker(cfg.interview_timeout_s, cfg.stop_phrases)
        self._queue: asyncio.Queue = asyncio.Queue()
        self._tasks: set[asyncio.Task] = set()

    # -- inbound callbacks (sync, must never block) -------------------------

    def on_photo(self, photo_path, portrait_path, at: float) -> None:
        self._queue.put_nowait(("photo", (str(photo_path), str(portrait_path)), at))

    def on_text(self, text: str, at: float) -> None:
        self._queue.put_nowait(("text", text, at))

    def on_final(self, event) -> None:
        self._queue.put_nowait(("final", event.text, event.timestamp))
        self.bus.publish({"type": "transcript", "text": event.text})

    def on_partial(self, event) -> None:
        self.bus.publish({"type": "transcript", "text": event.text})

    def on_tick(self, now: float) -> None:
        self._queue.put_nowait(("tick", None, now))

    def on_stt_state(self, connected: bool) -> None:
        self.store.set_setting("stt_connected", "1" if connected else "0")
        broadcast_state(self.store, self.bus)

    # -- queue processing ---------------------------------------------------

    async def run_worker(self) -> None:
        while True:
            kind, payload, at = await self._queue.get()
            try:
                await self._handle(kind, payload, at)
            except Exception as exc:  # a bad event must never kill the station
                log.error("core failed on %s: %s", kind, exc)

    async def run_tick_loop(self, interval: float = 5.0) -> None:
        while True:
            await asyncio.sleep(interval)
            self.on_tick(time.time())

    async def drain(self) -> None:
        """Process everything queued and await running pipelines (tests, shutdown)."""
        while not self._queue.empty():
            kind, payload, at = self._queue.get_nowait()
            try:
                await self._handle(kind, payload, at)
            except Exception as exc:
                log.error("core failed on %s: %s", kind, exc)
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def _handle(self, kind: str, payload, at: float) -> None:
        if kind == "photo":
            transitions = self.tracker.photo(at)
        elif kind == "text":
            transitions = self.tracker.text_message(at)
        elif kind == "final":
            transitions = self.tracker.transcript(payload, at)
        else:
            transitions = self.tracker.tick(at)

        for transition in transitions:
            if transition.kind == "closed":
                self._close(transition)
            else:
                self._open(payload, transition)

    def _open(self, payload, transition) -> None:
        photo_path, portrait_path = payload
        self.store.create_person(
            started_at=transition.at, photo_path=photo_path, portrait_path=portrait_path
        )
        # The person node appears immediately; terms grow after the stop (spec 6).
        broadcast_graph(self.store, self.cfg, self.bus)
        broadcast_state(self.store, self.bus)

    def _close(self, transition) -> None:
        person = self.store.open_person()
        if person is None:
            return
        self.store.close_person(person.id, stopped_at=transition.at, reason=transition.reason)
        broadcast_state(self.store, self.bus)
        task = asyncio.create_task(self._process(person.id, person.started_at, transition.at))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _process(self, person_id: str, started_at: float, stopped_at: float) -> None:
        try:
            await asyncio.to_thread(
                self.processor,
                self.store,
                self.cfg,
                self.llm,
                self.embedder,
                self.transcript_log,
                person_id,
                started_at,
                stopped_at,
            )
        except Exception as exc:  # already handled inside the pipeline; belt and braces
            log.error("pipeline crashed for %s: %s", person_id, exc)
            self.store.set_person_status(person_id, "failed")
        broadcast_graph(self.store, self.cfg, self.bus)
        broadcast_state(self.store, self.bus)
```

- [ ] **Step 4: Implement `kg/__main__.py`**

```python
"""Entrypoint: one process, four concerns (STT, Telegram, pipeline, HTTP)."""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

import uvicorn

from kg.bus import EventBus
from kg.config import load_config
from kg.core import Core
from kg.embeddings import build_embedder
from kg.export import write_graph_json
from kg.llm import LLMClient
from kg.server import create_app
from kg.store import Store
from kg.stt_client import STTClient
from kg.telegram_bot import TelegramSource
from kg.transcript import TranscriptLog


async def main_async(args) -> None:
    cfg = load_config(Path(args.config) if args.config else None)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    store = Store.open(cfg.db_path)
    # Apply the calibrated start density on a fresh database. On a restart the
    # operator's live setting is already stored and must win (spec 7, 10.5).
    store.set_setting_default("min_mentions", str(cfg.default_min_mentions))
    bus = EventBus()
    transcript_log = TranscriptLog(cfg.transcript_log_path)
    llm = LLMClient(
        model=cfg.llm_model,
        effort=cfg.llm_effort,
        max_tokens=cfg.llm_max_tokens,
        api_key=cfg.anthropic_api_key,
    )
    # OpenRouter + persistent cache (spec 6.2). Nothing to warm up: no local
    # model, and repeated terms are served from the cache.
    embedder = build_embedder(cfg)

    core = Core(cfg, store, bus, transcript_log, llm, embedder)
    write_graph_json(store, cfg.graph_json_path)  # state is reconstructed from SQLite

    app = create_app(store, cfg, bus)
    server = uvicorn.Server(
        uvicorn.Config(app, host=cfg.server_host, port=cfg.server_port, log_level="info")
    )

    tasks = [
        asyncio.create_task(server.serve()),
        asyncio.create_task(core.run_worker()),
        asyncio.create_task(core.run_tick_loop()),
    ]

    if not args.no_stt:
        stt = STTClient(
            url=cfg.stt_url,
            log=transcript_log,
            on_final=core.on_final,
            on_partial=core.on_partial,
            on_state=core.on_stt_state,
        )
        tasks.append(asyncio.create_task(stt.run()))

    if not args.no_telegram and cfg.telegram_token:
        source = TelegramSource(
            token=cfg.telegram_token,
            chat_id=cfg.telegram_chat_id,
            photo_dir=cfg.photo_dir,
            portrait_dir=cfg.portrait_dir,
            portrait_size=cfg.portrait_size,
            on_photo=core.on_photo,
            on_text=core.on_text,
        )
        application = source.build_application()
        await application.initialize()
        await application.updater.start_polling()
        await application.start()

    print(f"projection:  http://{cfg.server_host}:{cfg.server_port}/projection")
    print(f"operator:    http://{cfg.server_host}:{cfg.server_port}/operator")
    await asyncio.gather(*tasks)


def main() -> None:
    parser = argparse.ArgumentParser(prog="kg")
    parser.add_argument("--config", default=None)
    parser.add_argument("--no-telegram", action="store_true")
    parser.add_argument("--no-stt", action="store_true")
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_core.py -v`
Expected: PASS (9 tests)

- [ ] **Step 6: Smoke-test the process without external services**

```bash
cp config.example.toml config.toml
uv run python -m kg --no-telegram --no-stt &
sleep 8
curl -s http://127.0.0.1:8800/graph.json | head -5
curl -s http://127.0.0.1:8800/api/state
kill %1
```

Expected: a valid empty graph and a state object. No model download and no network call happens here — embeddings are only requested when an interview is processed, and then only for terms that are not already in the cache.

- [ ] **Step 7: Commit**

```bash
git add kg/core.py kg/__main__.py tests/test_core.py
git commit -m "feat: core wiring and process entrypoint"
```

---

### Task 18: Synthetic interview corpus and expectations

**Files:**
- Create: `sim/__init__.py`, `sim/generate_interviews.py`, `sim/data/interviews/*.json` (generated, committed), `sim/data/expectations.yaml` (generated, committed)
- Test: `tests/test_sim_generator.py`

**Interfaces:**
- Consumes: `kg.llm.LLMClient` (Task 8).
- Produces:
  - `sim.generate_interviews.QUESTIONS` (the five real guiding questions), `SPEAKER_TYPES`, `PLANTED`
  - `plan_corpus(count: int = 60) -> list[InterviewSpec]` — deterministic, seed-free (index-derived), so two runs produce the same plan.
  - `InterviewSpec(index, question_index, speaker_type, planted_concept: str | None, planted_phrasing: str | None)`
  - `build_generation_prompt(spec) -> str`
  - `write_expectations(plan, path) -> dict`
  - CLI: `uv run python -m sim.generate_interviews --count 60 --out sim/data`

The corpus is the prerequisite for judging anything (spec §9). It is generated from the **five real guiding questions**, in spoken language with filler words and broken sentences, across speaker types from terse to rambling, with ~1/3 of the interviews carrying a deliberately different formulation of a concept another interview also touches. Those planted overlaps are the documented expected merges — without them "good result" is unfalsifiable.

- [ ] **Step 1: Write the failing test**

`tests/test_sim_generator.py`:

```python
import yaml

from sim.generate_interviews import (
    PLANTED,
    QUESTIONS,
    SPEAKER_TYPES,
    build_generation_prompt,
    plan_corpus,
    write_expectations,
)


def test_the_five_real_guiding_questions_are_used_verbatim():
    assert len(QUESTIONS) == 5
    assert any("in 20 Jahren" in q for q in QUESTIONS)
    assert any("Eine KI plant Ihr nächstes Zuhause" in q for q in QUESTIONS)
    assert any("radikalen Bruch" in q for q in QUESTIONS)
    assert any("Wer sollte entscheiden" in q for q in QUESTIONS)
    assert any("für die Natur mehr übrig" in q for q in QUESTIONS)


def test_the_plan_is_deterministic():
    assert plan_corpus(60) == plan_corpus(60)


def test_every_question_and_every_speaker_type_is_covered():
    plan = plan_corpus(60)
    assert {spec.question_index for spec in plan} == set(range(5))
    assert {spec.speaker_type for spec in plan} == set(SPEAKER_TYPES)


def test_about_a_third_of_the_interviews_carry_a_planted_overlap():
    plan = plan_corpus(60)
    planted = [spec for spec in plan if spec.planted_concept]
    assert 15 <= len(planted) <= 25
    # every planted concept appears at least twice, otherwise it cannot merge
    counts = {}
    for spec in planted:
        counts[spec.planted_concept] = counts.get(spec.planted_concept, 0) + 1
    assert all(count >= 2 for count in counts.values())
    # and the phrasings differ, so a naive string match cannot pass the test
    for concept in counts:
        phrasings = {s.planted_phrasing for s in planted if s.planted_concept == concept}
        assert len(phrasings) >= 2


def test_the_prompt_demands_spoken_language_and_carries_the_question():
    spec = plan_corpus(60)[0]
    prompt = build_generation_prompt(spec)
    assert QUESTIONS[spec.question_index] in prompt
    assert "Füllwörter" in prompt
    assert spec.speaker_type in prompt


def test_planted_prompts_name_the_phrasing_to_use():
    spec = next(s for s in plan_corpus(60) if s.planted_concept)
    assert spec.planted_phrasing in build_generation_prompt(spec)


def test_expectations_document_every_planted_group(tmp_path):
    plan = plan_corpus(60)
    path = tmp_path / "expectations.yaml"

    document = write_expectations(plan, path)

    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert loaded == document
    concepts = {group["concept"] for group in loaded["expected_merges"]}
    assert concepts == {p["concept"] for p in PLANTED if _used(plan, p["concept"])}
    for group in loaded["expected_merges"]:
        assert len(group["interviews"]) >= 2
        assert len(group["phrasings"]) >= 2


def _used(plan, concept):
    return any(spec.planted_concept == concept for spec in plan)
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_sim_generator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sim'`

- [ ] **Step 3: Implement `sim/generate_interviews.py`**

```python
"""Synthetic interview corpus (spec 9). STT is out of scope: this starts from text.

Deterministic by construction — no random seeds — so two runs over the same
corpus are comparable.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from kg.extraction import GUIDING_QUESTIONS as QUESTIONS  # noqa: F401  (re-exported)

# NOT redefined here: the corpus must be generated from the SAME five guiding
# questions the extraction prompt names, otherwise the simulation tests the
# wrong text genre (spec 9).

SPEAKER_TYPES = [
    "sehr knapp, zwei Sätze, fast unwillig",
    "ausschweifend, fünf Minuten, mit zwei Abschweifungen",
    "Fachjargon, Planerin oder Ingenieur, sehr präzise",
    "Alltagssprache, keine Fachbegriffe, sehr bildhaft",
    "unentschlossen, wägt ab, widerspricht sich einmal",
    "klare Position, pointiert, leicht polemisch",
]

# Deliberate overlaps: the same idea in deliberately different words (spec 9).
PLANTED = [
    {
        "concept": "Roboter auf der Baustelle",
        "phrasings": [
            "Maschinen, die den Beton selber aufsprühen, so Drohnen halt",
            "3D-Drucker, die das Haus direkt auf dem Grundstück ausdrucken",
            "Roboterarme, die auf der Baustelle mauern",
        ],
    },
    {
        "concept": "Genossenschaftliches Wohnen",
        "phrasings": [
            "wenn die Leute das Haus zusammen besitzen, so als Verein",
            "Baugruppen, die gemeinsam bauen und dann gemeinsam drin wohnen",
            "wo nicht ein Investor gehört, sondern denen, die drin wohnen",
        ],
    },
    {
        "concept": "Recycling-Beton",
        "phrasings": [
            "den alten Bauschutt einfach wieder neu anmischen",
            "Beton aus Abbruchmaterial, also wirklich aus dem alten Haus",
            "Material aus dem Rückbau nochmal verwenden statt neu zu kaufen",
        ],
    },
    {
        "concept": "Ländlicher Leerstand",
        "phrasings": [
            "die ganzen leeren Häuser in den Dörfern, wo keiner mehr wohnt",
            "auf dem Land stehen ganze Straßen leer",
            "die Ortskerne draußen sterben aus, da ist alles frei",
        ],
    },
    {
        "concept": "Bodenversiegelung",
        "phrasings": [
            "dass alles zubetoniert wird, jeder Parkplatz asphaltiert",
            "der Boden kriegt keine Luft mehr, überall Beton drauf",
            "wir pflastern die Landschaft einfach zu",
        ],
    },
]


@dataclass(frozen=True)
class InterviewSpec:
    index: int
    question_index: int
    speaker_type: str
    planted_concept: str | None = None
    planted_phrasing: str | None = None


def plan_corpus(count: int = 60) -> list[InterviewSpec]:
    """Deterministic assignment — index arithmetic, no randomness."""
    specs: list[InterviewSpec] = []
    planted_position = 0
    for index in range(count):
        concept = phrasing = None
        if index % 3 == 0:  # ~1/3 carry a planted overlap
            group = PLANTED[planted_position % len(PLANTED)]
            concept = group["concept"]
            phrasing = group["phrasings"][
                (planted_position // len(PLANTED)) % len(group["phrasings"])
            ]
            planted_position += 1
        specs.append(
            InterviewSpec(
                index=index,
                question_index=index % len(QUESTIONS),
                speaker_type=SPEAKER_TYPES[index % len(SPEAKER_TYPES)],
                planted_concept=concept,
                planted_phrasing=phrasing,
            )
        )
    return specs


def build_generation_prompt(spec: InterviewSpec) -> str:
    lines = [
        "Schreibe das Transkript EINER Interviewantwort auf einer Architektur- und "
        "Baukultur-Konferenz, so wie eine automatische Spracherkennung es liefern "
        "würde: gesprochene Sprache, Füllwörter („also", „ähm", „ne"), abgebrochene "
        "Sätze, Wiederholungen, kleine Abschweifungen, keine Absätze, keine "
        "Anführungszeichen, kein Sprecherlabel.",
        "",
        f"Gestellte Frage: {QUESTIONS[spec.question_index]}",
        f"Sprechertyp: {spec.speaker_type}",
    ]
    if spec.planted_phrasing:
        lines += [
            "",
            "Die Person soll dabei — beiläufig, in eigenen Worten, ohne Fachbegriff — "
            f"genau diesen Gedanken äußern: „{spec.planted_phrasing}". Verwende NICHT "
            f"den Ausdruck „{spec.planted_concept}".",
        ]
    lines += ["", "Gib nur das Transkript aus, sonst nichts."]
    return "\n".join(lines)


def write_expectations(plan: list[InterviewSpec], path: Path) -> dict:
    groups: dict[str, dict] = {}
    for spec in plan:
        if not spec.planted_concept:
            continue
        group = groups.setdefault(
            spec.planted_concept, {"concept": spec.planted_concept, "interviews": [], "phrasings": []}
        )
        group["interviews"].append(spec.index)
        group["phrasings"].append(spec.planted_phrasing)
    document = {
        "note": "Erwartete Zusammenfassungen. Ohne diese Datei ist 'gutes Ergebnis' nicht falsifizierbar.",
        "expected_merges": [groups[key] for key in sorted(groups)],
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return document


def main() -> None:
    from kg.config import load_config
    from kg.llm import LLMClient
    from pydantic import BaseModel

    class Transcript(BaseModel):
        text: str

    parser = argparse.ArgumentParser(prog="sim.generate_interviews")
    parser.add_argument("--count", type=int, default=60)
    parser.add_argument("--out", default="sim/data")
    args = parser.parse_args()

    cfg = load_config()
    llm = LLMClient(
        model=cfg.llm_model, effort="medium", max_tokens=4000, api_key=cfg.anthropic_api_key
    )
    out = Path(args.out)
    (out / "interviews").mkdir(parents=True, exist_ok=True)

    plan = plan_corpus(args.count)
    for spec in plan:
        target = out / "interviews" / f"{spec.index:03d}.json"
        if target.exists():
            continue  # generation is resumable and never rewrites a committed fixture
        result = llm.parse(
            system="Du erzeugst realistische deutsche Interviewtranskripte.",
            user=build_generation_prompt(spec),
            output_model=Transcript,
        )
        payload = asdict(spec) | {"text": result.text}
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {target}")

    write_expectations(plan, out / "expectations.yaml")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests and confirm they pass**

```bash
touch sim/__init__.py
uv run pytest tests/test_sim_generator.py -v
```
Expected: PASS (7 tests)

- [ ] **Step 5: Generate and commit the corpus**

```bash
export ANTHROPIC_API_KEY=...    # LLM key, from the environment
uv run python -m sim.generate_interviews --count 60 --out sim/data
ls sim/data/interviews | wc -l   # 60
head -20 sim/data/expectations.yaml
```

Read three of the generated files. They must look like speech, not like an essay — filler words, broken sentences, one digression. If they read as clean prose, tighten `build_generation_prompt` and delete the affected files before regenerating (generation skips files that already exist).

- [ ] **Step 6: Commit**

```bash
git add sim/__init__.py sim/generate_interviews.py sim/data/interviews sim/data/expectations.yaml tests/test_sim_generator.py
git commit -m "feat: synthetic interview corpus with documented expected merges"
```

---

### Task 19: Replay harness and scoring

**Files:**
- Create: `sim/replay.py`
- Test: `tests/test_replay.py`

**Interfaces:**
- Consumes: Tasks 2, 3, 9, 11, 18.
- Produces:
  - `sim.replay.load_corpus(directory) -> list[dict]` (sorted by `index`)
  - `sim.replay.replay(corpus, store, cfg, llm, embedder, start_time=1_700_000_000.0, spacing=300.0, speed=0.0, on_step=None) -> list[str]` (person ids in corpus order)
  - `sim.replay.score_run(store, expectations, person_ids) -> dict`
  - CLI: `uv run python -m sim.replay --db out/sim.db --speed 120`

This is the primary integration harness (spec §13): text in, graph state out. It feeds the interviews in original order and relative spacing, accelerated by `--speed` (0 = as fast as possible), and can pause at any point so Task 20 can shoot a PNG. Scoring is against the documented expectations from Task 18, so a prompt change is visibly better or worse.

- [ ] **Step 1: Write the failing test**

`tests/test_replay.py`:

```python
import json

import pytest

from kg.config import Config
from kg.embeddings import HashEmbedder
from kg.pipeline import ProcessResult
from kg.store import Store
from sim.replay import load_corpus, replay, score_run


@pytest.fixture()
def corpus_dir(tmp_path):
    directory = tmp_path / "interviews"
    directory.mkdir()
    for index, text in enumerate(["eins", "zwei", "drei"]):
        (directory / f"{index:03d}.json").write_text(
            json.dumps({"index": index, "question_index": 0, "speaker_type": "x", "text": text}),
            encoding="utf-8",
        )
    return directory


def test_load_corpus_is_ordered_by_index(corpus_dir):
    assert [item["index"] for item in load_corpus(corpus_dir)] == [0, 1, 2]


def test_replay_creates_one_person_per_interview_with_spaced_timestamps(tmp_path, corpus_dir):
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    seen = []

    def processor(store_, cfg_, llm_, embedder_, log_, person_id, started_at, stopped_at):
        seen.append((person_id, started_at, stopped_at))
        return ProcessResult(person_id, "done", [], "")

    ids = replay(
        load_corpus(corpus_dir),
        store,
        cfg,
        llm=object(),
        embedder=HashEmbedder(dim=16),
        start_time=1000.0,
        spacing=300.0,
        processor=processor,
    )

    assert ids == ["p1", "p2", "p3"]
    assert [start for _, start, _ in seen] == [1000.0, 1300.0, 1600.0]
    assert all(stop > start for _, start, stop in seen)
    # the text really reached the transcript log
    assert "zwei" in cfg.transcript_log_path.read_text(encoding="utf-8")
    store.close()


def test_on_step_is_called_after_every_interview(tmp_path, corpus_dir):
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    steps = []

    replay(
        load_corpus(corpus_dir),
        store,
        cfg,
        llm=object(),
        embedder=HashEmbedder(dim=16),
        # positional order: store, cfg, llm, embedder, log, person_id, started, stopped
        processor=lambda *a: ProcessResult(a[5], "done", [], ""),
        on_step=lambda index, person_id: steps.append((index, person_id)),
    )

    assert steps == [(0, "p1"), (1, "p2"), (2, "p3")]
    store.close()


def test_score_run_reports_satisfied_and_missed_expectations(tmp_path):
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    persons = [store.create_person(started_at=float(i)) for i in range(4)]
    shared = store.get_or_create_term("Recycling-Beton", created_at=1.0)
    other_a = store.get_or_create_term("Holzbau", created_at=2.0)
    other_b = store.get_or_create_term("Bodenpreise", created_at=3.0)
    store.add_edge(persons[0].id, shared.id, created_at=4.0)
    store.add_edge(persons[3].id, shared.id, created_at=5.0)
    store.add_edge(persons[1].id, other_a.id, created_at=6.0)
    store.add_edge(persons[2].id, other_b.id, created_at=7.0)

    expectations = {
        "expected_merges": [
            {"concept": "Recycling-Beton", "interviews": [0, 3]},
            {"concept": "Ländlicher Leerstand", "interviews": [1, 2]},
        ]
    }

    report = score_run(store, expectations, [p.id for p in persons])

    assert report["satisfied"] == 1
    assert report["total"] == 2
    assert report["score"] == 0.5
    by_concept = {g["concept"]: g for g in report["groups"]}
    assert by_concept["Recycling-Beton"]["merged"] is True
    assert by_concept["Recycling-Beton"]["label"] == "Recycling-Beton"
    assert by_concept["Ländlicher Leerstand"]["merged"] is False
    assert report["term_count"] == 3


def test_score_run_handles_an_interview_without_terms(tmp_path):
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    persons = [store.create_person(started_at=float(i)) for i in range(2)]

    report = score_run(
        store, {"expected_merges": [{"concept": "X", "interviews": [0, 1]}]}, [p.id for p in persons]
    )

    assert report["satisfied"] == 0
    assert report["groups"][0]["merged"] is False
    store.close()
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_replay.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sim.replay'`

- [ ] **Step 3: Implement `sim/replay.py`**

```python
"""Time-lapse replay of the synthetic corpus (spec 9).

Text in, graph state out. STT is deliberately out of scope: the transcript log
is written directly, then the real pipeline runs unchanged.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from kg.pipeline import process_interview
from kg.transcript import TranscriptionEvent, TranscriptLog

INTERVIEW_LENGTH = 180.0  # synthetic spoken duration of one interview


def load_corpus(directory: Path) -> list[dict]:
    items = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(Path(directory).glob("*.json"))
    ]
    return sorted(items, key=lambda item: item["index"])


def replay(
    corpus: list[dict],
    store,
    cfg,
    llm,
    embedder,
    start_time: float = 1_700_000_000.0,
    spacing: float = 300.0,
    speed: float = 0.0,
    processor=process_interview,
    on_step=None,
) -> list[str]:
    transcript_log = TranscriptLog(cfg.transcript_log_path)
    person_ids: list[str] = []

    for position, item in enumerate(corpus):
        started_at = start_time + position * spacing
        stopped_at = started_at + INTERVIEW_LENGTH
        person = store.create_person(
            started_at=started_at, photo_path=None, portrait_path=None
        )
        # Spread the text over the interview so the time cut is exercised too.
        sentences = [s.strip() for s in item["text"].split(".") if s.strip()] or [item["text"]]
        step = INTERVIEW_LENGTH / (len(sentences) + 1)
        for offset, sentence in enumerate(sentences, start=1):
            transcript_log.append(
                TranscriptionEvent(
                    type="final", text=sentence + ".", timestamp=started_at + offset * step
                )
            )
        store.close_person(person.id, stopped_at=stopped_at, reason="text")
        processor(store, cfg, llm, embedder, transcript_log, person.id, started_at, stopped_at)
        person_ids.append(person.id)
        if on_step:
            on_step(item["index"], person.id)
        if speed > 0 and position + 1 < len(corpus):
            time.sleep(spacing / speed)

    return person_ids


def score_run(store, expectations: dict, person_ids: list[str]) -> dict:
    edges = store.list_edges()
    terms_by_person: dict[str, set[str]] = {}
    for edge in edges:
        terms_by_person.setdefault(edge.person_id, set()).add(edge.term_id)

    groups = []
    for expected in expectations.get("expected_merges", []):
        indices = expected["interviews"]
        term_sets = [
            terms_by_person.get(person_ids[i], set()) for i in indices if i < len(person_ids)
        ]
        shared = set.intersection(*term_sets) if term_sets and all(term_sets) else set()
        term_id = sorted(shared)[0] if shared else None
        groups.append(
            {
                "concept": expected["concept"],
                "interviews": indices,
                "merged": term_id is not None,
                "term_id": term_id,
                "label": store.get_term(term_id).label if term_id else None,
            }
        )

    satisfied = sum(1 for group in groups if group["merged"])
    return {
        "groups": groups,
        "satisfied": satisfied,
        "total": len(groups),
        "score": round(satisfied / len(groups), 3) if groups else 0.0,
        "term_count": len(store.list_terms()),
        "person_count": len(person_ids),
        "edge_count": len(edges),
    }


def main() -> None:
    import yaml

    from kg.config import load_config
    from kg.embeddings import build_embedder
    from kg.export import write_graph_json
    from kg.llm import LLMClient
    from kg.store import Store

    parser = argparse.ArgumentParser(prog="sim.replay")
    parser.add_argument("--data", default="sim/data")
    parser.add_argument("--db", default="out/sim.db")
    parser.add_argument("--speed", type=float, default=0.0, help="0 = as fast as possible")
    parser.add_argument("--limit", type=int, default=0, help="stop after N interviews")
    parser.add_argument(
        "--hash-embedder", action="store_true", help="deterministic local hashing, no API call"
    )
    args = parser.parse_args()

    cfg = load_config()
    data = Path(args.data)
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    # A fresh run needs a fresh transcript log too.
    run_cfg = type(cfg)(**{**cfg.__dict__, "data_dir": db_path.parent})
    if run_cfg.transcript_log_path.exists():
        run_cfg.transcript_log_path.unlink()

    store = Store.open(db_path)
    llm = LLMClient(
        model=cfg.llm_model,
        effort=cfg.llm_effort,
        max_tokens=cfg.llm_max_tokens,
        api_key=cfg.anthropic_api_key,
    )
    # NB: built from `cfg`, not `run_cfg` — the embedding cache must live in the
    # real data_dir so a second run over the same corpus is free and offline.
    embedder = build_embedder(cfg, hash_only=args.hash_embedder)

    corpus = load_corpus(data / "interviews")
    if args.limit:
        corpus = corpus[: args.limit]

    person_ids = replay(
        corpus,
        store,
        run_cfg,
        llm,
        embedder,
        speed=args.speed,
        on_step=lambda index, person_id: print(f"interview {index:03d} -> {person_id}"),
    )

    expectations = yaml.safe_load((data / "expectations.yaml").read_text(encoding="utf-8"))
    report = score_run(store, expectations, person_ids)
    write_graph_json(store, db_path.parent / "graph.json")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    store.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_replay.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Run the real simulation and record the calibration values**

```bash
uv run python -m sim.replay --db out/sim.db --limit 12       # short smoke run
uv run python -m sim.replay --db out/sim.db                  # full 60-interview run
```

Record in `docs/operations.md` (created in Task 21):
- the score and term count for `terms_per_interview` = 4, 5 and 6 (edit `config.toml` between runs),
- how the picture reads at `min_mentions` 1, 2 and 3,
- the merge-style wording that produced the best score.

These are the **calibration values produced BY the simulation** (spec §14.4); they are not guessable in advance. `terms_per_interview` and `merge_style` are then frozen in `config.toml` and never exposed at runtime (spec §6.3, §7).

- [ ] **Step 6: Commit**

```bash
git add sim/replay.py tests/test_replay.py
git commit -m "feat: time-lapse replay harness with expectation scoring"
```

---

### Task 20: Pre-render comparison series (A–D)

**Files:**
- Create: `sim/prerender.py`
- Test: `tests/test_prerender.py`

**Interfaces:**
- Consumes: `kg.server.create_app` (Task 12), the themes (Task 14, 16), a simulation database (Task 19).
- Produces:
  - `sim.prerender.serve(store, cfg) -> (base_url, shutdown)` — starts the real app on an ephemeral port in a background thread.
  - `sim.prerender.render_series(db_path, out_dir, themes=("a", "b", "c"), include_testpattern=True) -> list[Path]`
  - CLI: `uv run python -m sim.prerender --db out/sim.db --out out/prerender`

The PNGs are shot at exactly 1920×1080 **with the same renderer that later runs live** (spec §10.4) and are fed by real graph states from the simulation, not fixtures. Variants: **A** dark reference, **B** inverted, **C** heavier strokes and larger minimum font, **D** the test pattern.

- [ ] **Step 1: Write the failing test**

`tests/test_prerender.py`:

```python
from PIL import Image

from kg.config import Config
from kg.store import Store
from sim.prerender import render_series


def build_db(tmp_path):
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    for index in range(4):
        person = store.create_person(started_at=float(index))
        term = store.get_or_create_term(f"Begriff {index}", created_at=float(index))
        store.add_edge(person.id, term.id, created_at=float(index))
        if index:
            store.add_edge(person.id, store.list_terms()[0].id, created_at=float(index))
    store.close()
    return cfg.db_path


def test_the_series_renders_one_png_per_variant_at_1920x1080(tmp_path):
    db_path = build_db(tmp_path)
    out_dir = tmp_path / "prerender"

    paths = render_series(db_path, out_dir)

    assert [p.name for p in paths] == ["a.png", "b.png", "c.png", "d.png"]
    for path in paths:
        with Image.open(path) as img:
            assert img.size == (1920, 1080)


def test_the_variants_differ_from_each_other(tmp_path):
    db_path = build_db(tmp_path)
    out_dir = tmp_path / "prerender"

    paths = render_series(db_path, out_dir, themes=("a", "b"), include_testpattern=False)

    assert paths[0].read_bytes() != paths[1].read_bytes()
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_prerender.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sim.prerender'`

- [ ] **Step 3: Implement `sim/prerender.py`**

```python
"""Headless 1920x1080 PNGs with the renderer that later runs live (spec 10.4)."""

from __future__ import annotations

import argparse
import socket
import threading
import time
from pathlib import Path

import uvicorn

from kg.bus import EventBus
from kg.config import Config
from kg.server import create_app
from kg.store import Store


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def serve(store, cfg) -> tuple[str, callable]:
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(store, cfg, EventBus()), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        raise RuntimeError("prerender server did not start")

    def shutdown() -> None:
        server.should_exit = True
        thread.join(timeout=10)

    return f"http://127.0.0.1:{port}", shutdown


def render_series(
    db_path: Path,
    out_dir: Path,
    themes: tuple[str, ...] = ("a", "b", "c"),
    include_testpattern: bool = True,
) -> list[Path]:
    from playwright.sync_api import sync_playwright

    db_path = Path(db_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = Config(data_dir=db_path.parent)
    store = Store.open(db_path)
    base_url, shutdown = serve(store, cfg)
    written: list[Path] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            for theme in themes:
                page.goto(f"{base_url}/projection?theme={theme}")
                page.wait_for_function("window.kgReady === true", timeout=20000)
                # Wait for the real signal, not a guessed duration: the cose
                # layout is animated and nodes are still moving until layoutstop.
                page.wait_for_function(
                    "() => window.kgView && window.kgView.layoutPending === false",
                    timeout=20000,
                )
                page.wait_for_timeout(200)  # let the final frame paint
                target = out_dir / f"{theme}.png"
                page.screenshot(path=str(target))
                written.append(target)
            if include_testpattern:
                page.goto(f"{base_url}/testpattern")
                page.wait_for_selector(".wedge")
                target = out_dir / "d.png"
                page.screenshot(path=str(target))
                written.append(target)
            browser.close()
    finally:
        shutdown()
        store.close()
    return written


def main() -> None:
    parser = argparse.ArgumentParser(prog="sim.prerender")
    parser.add_argument("--db", default="out/sim.db")
    parser.add_argument("--out", default="out/prerender")
    args = parser.parse_args()
    for path in render_series(Path(args.db), Path(args.out)):
        print(path)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_prerender.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Produce the real comparison series and hand it to Birk**

```bash
uv run python -m sim.replay --db out/sim.db          # if not already run
uv run python -m sim.prerender --db out/sim.db --out out/prerender
```

Show `out/prerender/{a,b,c,d}.png` to Birk and ask which variant the whiteboard gets. The named outcomes to decide between (spec §10.3): (1) everything is displayable at once, (2) the font would have to become too small → zoom is needed, (3) an automatic pan is needed once the graph exceeds the frame. The camera already supports all three; this is a setting, not a rebuild.

- [ ] **Step 6: Commit**

```bash
git add sim/prerender.py tests/test_prerender.py
git commit -m "feat: headless 1920x1080 pre-render comparison series"
```

---

### Task 21: Failure modes, crash recovery and the on-site runbook

**Files:**
- Create: `tests/test_resilience.py`, `docs/operations.md`, `scripts/start.sh`
- Modify: `kg/session.py` (adds `SessionTracker.adopt()`), `kg/core.py` (adds `Core.recover()`), `kg/__main__.py` (calls it at startup)
- Test: `tests/test_resilience.py`

**Interfaces:**
- Consumes: everything.
- Produces: `scripts/start.sh` (kiosk launcher with auto-restart) and `docs/operations.md` (runbook).

Every failure mode named in spec §13 gets a test here or is explicitly cross-referenced to the task that already covers it:

| Failure mode | Covered by |
|---|---|
| STT server unreachable | Task 3 (`test_reconnects_after_a_dropped_stream`) + this task's state test |
| Telegram offline / broken photo | Task 7 (`test_a_failed_download_does_not_raise`) |
| LLM fails or returns invalid JSON | Task 8 (retry), Task 11 (`failed` status), Task 17 (core survives) |
| Photo without stop | Task 5 + Task 17 (timeout) |
| Stop without photo | Task 5 + Task 17 (ignored) |
| Crash + restart, incl. positions | **this task** |

- [ ] **Step 1: Write the failing test**

`tests/test_resilience.py`:

```python
import json

import pytest

from kg.config import Config
from kg.bus import EventBus
from kg.core import Core
from kg.embeddings import HashEmbedder
from kg.export import build_graph, write_graph_json
from kg.pipeline import ProcessResult
from kg.store import Store
from kg.transcript import TranscriptLog


def build_state(cfg):
    store = Store.open(cfg.db_path)
    person = store.create_person(started_at=100.0, portrait_path="portraits/a.png")
    term = store.get_or_create_term("Recycling-Beton", created_at=110.0)
    store.add_edge(person.id, term.id, created_at=111.0)
    store.add_quote(person.id, "Wir bauen zu viel Neues.", created_at=112.0)
    store.save_positions({person.id: (12.0, -8.0), term.id: (40.0, 3.0)})
    store.set_setting("min_mentions", "2")
    store.set_setting("camera_mode", "pan")
    store.close_person(person.id, stopped_at=160.0, reason="text")
    return store


def test_full_state_including_positions_survives_a_restart(tmp_path):
    cfg = Config(data_dir=tmp_path / "state")
    store = build_state(cfg)
    before = build_graph(store)
    store.close()  # simulate the crash

    reopened = Store.open(cfg.db_path)
    after = build_graph(reopened)

    assert after["nodes"] == before["nodes"]
    assert after["edges"] == before["edges"]
    assert after["quotes"] == before["quotes"]
    assert after["min_mentions"] == 2
    assert reopened.get_setting("camera_mode", "fit") == "pan"
    reopened.close()


def test_graph_json_is_rebuilt_from_sqlite_after_a_restart(tmp_path):
    cfg = Config(data_dir=tmp_path / "state")
    store = build_state(cfg)
    store.close()
    cfg.graph_json_path.unlink(missing_ok=True)

    reopened = Store.open(cfg.db_path)
    write_graph_json(reopened, cfg.graph_json_path)

    graph = json.loads(cfg.graph_json_path.read_text(encoding="utf-8"))
    assert len(graph["nodes"]) == 2
    positions = {node["id"]: (node["x"], node["y"]) for node in graph["nodes"]}
    assert positions["p1"] == (12.0, -8.0)
    reopened.close()


def test_a_corrupt_graph_json_does_not_block_the_rebuild(tmp_path):
    cfg = Config(data_dir=tmp_path / "state")
    store = build_state(cfg)
    store.close()
    cfg.graph_json_path.write_text("{ half written", encoding="utf-8")

    reopened = Store.open(cfg.db_path)
    write_graph_json(reopened, cfg.graph_json_path)

    assert json.loads(cfg.graph_json_path.read_text(encoding="utf-8"))["version"] == 1
    reopened.close()


async def test_an_interview_open_at_crash_time_can_still_be_closed_after_restart(tmp_path):
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    store.create_person(started_at=100.0, portrait_path="portraits/a.png")
    store.close()  # crash while an interview is running

    reopened = Store.open(cfg.db_path)
    assert reopened.open_person().id == "p1"
    processed = []
    core = Core(
        cfg=cfg,
        store=reopened,
        bus=EventBus(),
        transcript_log=TranscriptLog(cfg.transcript_log_path),
        llm=object(),
        embedder=HashEmbedder(dim=16),
        processor=lambda *a: (processed.append(a[5]), ProcessResult(a[5], "done", [], ""))[1],
    )
    core.recover()  # adopt the open interview into the fresh tracker

    core.on_text("fertig", at=500.0)
    await core.drain()

    assert reopened.get_person("p1").stop_reason == "text"
    assert processed == ["p1"]
    reopened.close()


async def test_a_dead_stt_server_is_visible_but_not_fatal(tmp_path):
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    core = Core(
        cfg=cfg,
        store=store,
        bus=EventBus(),
        transcript_log=TranscriptLog(cfg.transcript_log_path),
        llm=object(),
        embedder=HashEmbedder(dim=16),
        processor=lambda *a: ProcessResult(a[5], "done", [], ""),
    )

    core.on_stt_state(False)
    core.on_photo(photo_path="a.jpg", portrait_path="a.png", at=100.0)
    await core.drain()

    # The station keeps working: the portrait still lands on the wall.
    assert store.get_setting("stt_connected", "1") == "0"
    assert store.open_person() is not None
    store.close()
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_resilience.py -v`
Expected: FAIL — `AttributeError: 'Core' object has no attribute 'recover'`

- [ ] **Step 3: Add `SessionTracker.adopt()` and `Core.recover()`**

In `kg/session.py`, next to `tick`:

```python
    def adopt(self, at: float) -> None:
        """Re-enter the open state after a restart (spec 10.5)."""
        self._open_since = at
```

In `kg/core.py`:

```python
    def recover(self) -> None:
        """Adopt an interview that was open when the process died (spec 10.5)."""
        person = self.store.open_person()
        if person is not None:
            self.tracker.adopt(person.started_at)
            log.info("recovered open interview %s", person.id)
```

Call it in `kg/__main__.py` immediately after `core = Core(...)`:

```python
    core.recover()
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_resilience.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Write `scripts/start.sh`**

```bash
#!/usr/bin/env bash
# On-site launcher: core + two browser windows, each restarted if it dies.
set -u
cd "$(dirname "$0")/.."

: "${ANTHROPIC_API_KEY:?export ANTHROPIC_API_KEY first}"
: "${KG_TELEGRAM_TOKEN:?export KG_TELEGRAM_TOKEN first}"
: "${OPENROUTER_API_KEY:?export OPENROUTER_API_KEY first}"

HOST=127.0.0.1
PORT=8800

while true; do
  uv run python -m kg --config config.toml
  echo "core exited ($?), restarting in 3s" >&2
  sleep 3
done &
CORE_PID=$!

sleep 8

# Projection: fullscreen kiosk on the beamer (second display).
while true; do
  chromium --kiosk --window-position=1920,0 --noerrdialogs \
    --disable-session-crashed-bubble --disable-infobars --incognito \
    --autoplay-policy=no-user-gesture-required \
    "http://$HOST:$PORT/projection"
  echo "projection window exited, restarting" >&2
  sleep 2
done &

# Operator: ordinary window on the laptop display. Never the same window.
while true; do
  chromium --new-window --window-position=0,0 --window-size=1280,900 \
    "http://$HOST:$PORT/operator"
  sleep 2
done &

wait $CORE_PID
```

```bash
chmod +x scripts/start.sh
```

- [ ] **Step 6: Write `docs/operations.md`**

Include, with the values measured during Tasks 19–20:

```markdown
# Betrieb — Station Kollektivgedächtnis

## Vor dem Festival
1. `export ANTHROPIC_API_KEY=...`, `export KG_TELEGRAM_TOKEN=...` und
   `export OPENROUTER_API_KEY=...` (nur diese drei Geheimnisse; nie
   `~/.hermes/.env` verwenden). `OPENROUTER_API_KEY` ist nur für die
   Embeddings und darf ein eigener Schlüssel sein.
2. `cp config.example.toml config.toml` und Werte prüfen —
   `terms_per_interview`, `merge_style` und `default_min_mentions` stehen auf den
   in der Simulation kalibrierten Werten (siehe unten) und werden im Betrieb NICHT verändert.
3. `uv sync` und einmal `uv run python -m kg --no-telegram --no-stt` starten
   (Rauchtest). Es wird kein Modell heruntergeladen; Embeddings kommen von
   OpenRouter und liegen danach im Cache `data/embeddings.sqlite3` — diese
   Datei nicht löschen, sie spart Geld und macht Wiederholungsläufe offline-fähig.
4. STT-Server starten (siehe `docs/stt-contract.md`):
   `python -m fundusapps.stt_server elevenlabs-scribe --language de`
   (braucht `ELEVENLABS_API_KEY` in dessen eigener Umgebung) und
   `curl -N http://127.0.0.1:5051/events` gegenprüfen.

## Start am Ausstellungstag
`./scripts/start.sh` — startet Core, Projektionsfenster (Beamer, Kiosk) und
Operator-Fenster (Laptop). Jeder Teil startet nach einem Absturz neu; der
Zustand wird vollständig aus SQLite rekonstruiert, inklusive Knotenpositionen.

## Ein Interview
1. Foto per Telegram → Personenknoten mit Portrait erscheint sofort.
2. Interview führen (Funkmikro läuft dauerhaft in den STT-Server).
3. Beenden: beliebige Textnachricht in Telegram ODER gesprochen
   „Interview beendet" ODER nach 15 min automatisch.
4. Begriffe wachsen nach dem Stopp nach.

## Die eine Live-Stellschraube
Dichte-Regler im Operator-UI: 1 = alles, 2 = nur Geteiltes, 3 = nur Häufiges.
Reiner Anzeigefilter — verwirft nichts, jederzeit umkehrbar, wirkt sofort auf
den gesamten Bestand.

## Notausgang
„ausblenden" neben einem Eintrag im Operator-UI. Kein Löschen, kein Bearbeiten.
Wieder einblenden ist derselbe Knopf.

## Wenn etwas ausfällt
| Symptom | Bedeutung | Maßnahme |
|---|---|---|
| STT-Badge rot | STT-Server weg | Server neu starten; Core verbindet sich selbst neu. Fotos/Personenknoten laufen weiter. |
| Kein Personenknoten nach Foto | Telegram/Bot offline | Bot-Token prüfen, Core-Log ansehen. |
| Begriffe fehlen bei einer Person | LLM-Aufruf gescheitert (`status=failed`) | Nichts tun — der Personenknoten steht; das Interview lässt sich nicht wiederholen. |
| Zwei Interviews scheinen offen | Kann nicht passieren | Ein neues Foto schließt das laufende implizit. |
| Graph verschoben | Layout-Fehler | Kamera auf „alles zeigen" stellen; Positionen bleiben persistiert. |

## Touch prüfen (nur falls Touch-Hardware da ist)
```
dmesg | grep -i hid
libinput list-devices     # muss ABS_MT_* Achsen zeigen
```
Meldet sich das Gerät als HID-Maus statt als Multitouch-Digitizer, gibt es nur
einen Kontaktpunkt und keine Gesten. Dann Kamera auf „automatisch schwenken"
stellen — dieser Modus ist der vorgesehene Fallback.

## Kalibrierte Werte (aus der Simulation, Task 19)
- `terms_per_interview` = <Wert eintragen> (Score <…>, <…> Begriffsknoten bei 60 Interviews)
- `merge_style` = "<Wortlaut eintragen>"
- Empfohlene Startdichte = <1|2|3>
- Gewählte Pre-Render-Variante = <A|B|C> (Entscheidung Birk, Datum)
```

- [ ] **Step 7: Run the complete suite**

Run: `uv run pytest -v`
Expected: PASS — every test from Tasks 1–21

- [ ] **Step 8: Commit**

```bash
git add tests/test_resilience.py docs/operations.md scripts/start.sh kg/core.py kg/session.py kg/__main__.py
git commit -m "feat: crash recovery, failure-mode coverage and on-site runbook"
```

---

## Open items carried forward from the spec (§14)

1. ~~Verify the current STT server repo~~ — **RESOLVED 2026-08-12** (spec §14.1). Source, branch, run command and the changed 10-field event contract (`extending`) are recorded in Task 3, Step 1 and in the spec §4. Nothing is blocked.
2. **Second screen specs** from the organiser — affects Tool 2, not this build. Nothing here depends on it.
3. **Touch hardware decision** — procurement track. If touch is absent, camera mode `pan` (Task 14) carries the station; no code change needed.
4. **Density calibration values** — produced by Task 19, recorded in `docs/operations.md` in Task 21.

## Explicitly out of scope (spec §12 — do not build)

Tool 2 „Kollektivtraum"; quote on touch; terms growing *during* the interview; term↔term edges; runtime-adjustable extraction settings; pre-roll transcription; diarisation / parallel interviews.
