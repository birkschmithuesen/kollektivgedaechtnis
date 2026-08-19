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
- **Node positions are persisted for crash recovery; every other graph change makes the whole net migrate, slowly and incrementally, never by re-rolling it** (spec §11, revised by Birk 2026-08-14 — this replaces the earlier "existing nodes stay put, the layout must never re-shuffle"). The layout is `cytoscape-fcose` at `quality: "proof"` with `randomize: false`, so the new arrangement always starts from the one on the wall; Cytoscape's own `preset` layout glides the net into it.
- **Node and font sizes are model-unit values, never wall pixels** (spec §10.3, §11): the viewport fit scales them, so the graph always fills the screen — large at three nodes, small at a hundred — and no fixed scale can become unreadable.
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
frontend/static/vendor/layout-base.js       Task 14 (vendored, committed — fcose dependency chain)
frontend/static/vendor/cose-base.js         Task 14 (vendored, committed)
frontend/static/vendor/cytoscape-fcose.js   Task 14 (vendored, committed — the layout)
frontend/static/vendor/cytoscape-layout-utilities.js  Task 14 (vendored, committed — packComponents)
frontend/static/vendor/README.md            Task 14 (versions, globals, load order)
sim/generate_interviews.py     Task 18  synthetic corpus generator
sim/data/interviews/*.json     Task 18  committed fixtures
sim/data/expectations.yaml     Task 18  documented expected merges
sim/replay.py                  Task 19  time-lapse feeder + score
sim/seed_graph.py              Task 20  Store-seeded realistic graph (no simulation)
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
  - `kg.session.SessionTracker(timeout_s, stop_phrases, open_since=None)` with `photo(at)`, `text_message(at)`, `transcript(text, at)`, `tick(now)`, each returning `list[Transition]`, plus the property `open_since: float | None`. `open_since` lets a caller resume an interview that was already open in storage (Task 17, after a crash) instead of losing track of it.

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


def test_a_tracker_can_resume_an_interview_already_open_in_storage():
    t = SessionTracker(timeout_s=900, stop_phrases=PHRASES, open_since=100.0)
    assert t.open_since == 100.0
    assert t.photo(at=400.0) == [
        Transition("closed", 400.0, "new_photo"),
        Transition("opened", 400.0, "photo"),
    ]
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
    def __init__(
        self,
        timeout_s: float,
        stop_phrases: Sequence[str],
        open_since: float | None = None,
    ) -> None:
        self.timeout_s = float(timeout_s)
        self.stop_phrases = list(stop_phrases)
        # Lets a caller resume an interview that was already open in storage
        # (a restart after a crash) instead of silently forgetting it and
        # opening a second one on the next photo.
        self._open_since = open_since

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
Expected: PASS (9 tests)

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
  - `kg.pipeline.process_interview(store, cfg, llm, embedder, transcript_log, person_id, started_at, stopped_at, *, cut_end: float | None = None) -> ProcessResult`

Order (spec §6.1): cut between the markers (`cut_end` defaults to `stopped_at`; only the Telegram-text stop path passes a later one — see Task 17's settle window) → strip the spoken stop command → one extraction call (end detection + terms + quotes) → truncate at the detected end → resolve already-decided labels → one merge call for the rest → persist person↔term edges and quotes → re-export `graph.json`. An LLM failure marks the interview `failed` and leaves the person node standing; it must never crash the process (spec §13).

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
    cfg = Config(data_dir=tmp_path / "state", terms_per_interview=3)
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


def test_the_settled_cut_end_is_handed_to_the_llm_but_transcript_stops_at_the_detected_end(env):
    cfg, store, log = env
    # A final at 150.9 lands just inside a plausible 3s settle window after a
    # stop marker at 150.0 (kg.core.settle_cut_end handles the actual wait;
    # here the caller just passes the resulting cut_end straight through).
    fill_log(log, [("Bodenpreise sind das Problem.", 105.0), ("Wo ist der Kaffee?", 150.9)])
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM(
        [
            ExtractionResult(interview_end_index=len("Bodenpreise sind das Problem."), terms=[], quotes=[]),
            MergeResult(groups=[]),
        ]
    )

    process_interview(
        store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 150.0, cut_end=150.9
    )

    # The settled final was offered to the model...
    assert "Wo ist der Kaffee?" in llm.prompts[0]
    # ...but the stored transcript stops where the interview really ended.
    assert store.get_person(person.id).transcript == "Bodenpreise sind das Problem."


def test_without_cut_end_the_cut_stops_at_stopped_at(env):
    cfg, store, log = env
    fill_log(log, [("Bodenpreise sind das Problem.", 105.0), ("Wo ist der Kaffee?", 150.9)])
    person = store.create_person(started_at=100.0)
    llm = ScriptedLLM(
        [ExtractionResult(interview_end_index=9999, terms=[], quotes=[]), MergeResult(groups=[])]
    )

    process_interview(store, cfg, llm, HashEmbedder(dim=64), log, person.id, 100.0, 150.0)

    assert "Bodenpreise sind das Problem." in llm.prompts[0]
    assert "Wo ist der Kaffee?" not in llm.prompts[0]


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
    *,
    cut_end: float | None = None,
) -> ProcessResult:
    store.set_person_status(person_id, "processing")

    # 1. Cut between the markers. Only the Telegram-text stop path extends the
    # end past stopped_at, to the final that landed inside its settle window
    # (kg.core.settle_cut_end); every other path leaves cut_end at stopped_at.
    raw = transcript_log.text_between(started_at, stopped_at if cut_end is None else cut_end)
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
    assert client.get("/testpattern").status_code == 200
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
"""FastAPI app: three static pages, one SSE stream, the operator API."""

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
- Consumes: `graph-model.js` (Task 13), the vendored Cytoscape build (Task 13) plus the vendored fcose chain (`layout-base` → `cose-base` → `cytoscape-fcose`, and `cytoscape-layout-utilities`), `/events` + `/graph.json` + `POST /api/positions` (Task 12).
- Produces:
  - `camera.js`: `class Camera(cy, {panSpeed, padding, zoomFactor})` with `setMode(mode)`, `get mode()`, `setZoomFactor(factor)`, `get zoomFactor()`, `focus(eles, padding)`, `onGraphChanged()`, `step(dtSeconds)`. The zoom factor and `focus()` came with the second pre-render review (2026-08-14): fit-all at 50 persons is illegible, so the zoom level is a setting of this component rather than a second camera.
  - `projection.js`: `createGraphView(container, {onPositions, migrationDuration}) -> {cy, camera, update(graph, minMentions), setMinMentions(value), layoutPending, migrating, migrationDuration, labelOverlaps(), labelOverlapStats, declutterLabels(), resetLabelOffsets()}`, plus the pieces of the placement pipeline, each exported so it can be exercised on its own: `frameToAspect(cy, target)`, `normaliseDensity(cy, target)`, `separateOverlappingNodes(cy)`, `settlePlacement(cy, {inkFraction})`, `declutterLabels(cy)`, `resetLabelOffsets(cy)`, `countLabelOverlaps(cy) -> {labelPairs, labelsOnPersons, personPairs}`, `LAYOUT`, `MIGRATION_DURATION_MS`. `personPairs` — person discs lying on each other — came with the seventh pre-render review (2026-08-15) and is scored by `settlePlacement`, which is the only pass that can move a disc.
  - `projection.html` exposes `window.kgView` (used by Task 20's pre-render and by these tests) and reads `?theme=` and `?migration=` (glide length in ms).

**Fourth pre-render review — spec change by Birk, 2026-08-14 (binding).** The rule "existing
nodes stay put, the layout must never re-shuffle" is REPLACED: when the graph changes, all
nodes migrate slowly to a better-distributed arrangement that fills the freed space, and node
and font sizes follow the viewport fit so the picture always fills the wall. The anti-jump
requirement is unchanged and is the reason for every option below. **Use the library, do not
hand-build this** (Birk, explicit): the layout is `cytoscape-fcose`, vendored offline like
Cytoscape itself.

- `LAYOUT` is fcose at `quality: "proof"` (the only quality that supports the next two
  options), `randomize: false` (start from the CURRENT positions — the anti-jump guarantee,
  from the library), `nodeDimensionsIncludeLabels: true`, `packComponents: true` (early in
  the festival the net really is disconnected), `animate: false`.
- The glide is Cytoscape's own `preset` layout: `migrate()` computes the new arrangement with
  the animation off, puts every node back where it started, and animates once. Computing
  first means the passes after the layout cannot land as a snap at the end of the animation.
- **Yield a frame between the computation and the glide.** Cytoscape times animations off the
  animation loop's frame clock, and the frame after a long synchronous block carries a
  timestamp from before it: measured, a 2500ms glide ran out in **116ms** of real time — the
  wall froze and then cut. `nextFrame()` (a double `requestAnimationFrame`) fixes it.
- **`nodeDimensionsIncludeLabels` does NOT replace the hand-built label work**, which is what
  the brief expected and what the measurement had to settle. On the seeded 50-person /
  75-term graph at theme B, from an identical starting state: fcose alone leaves **42
  overlapping label pairs, 26 labels on portrait discs, 59% of the canvas width**; with the
  option off it is 156 / 65 / 43%, so the option earns its keep but does not finish the job.
  `settlePlacement()` takes it to 8 / 1 / 89% and `declutterLabels()` to **0 / 0 / 89%**. Both
  passes are therefore kept, each on its own number, and only the parts fcose really did make
  redundant were deleted: `frameToAspect`'s quarter-turn (it existed for a cose bug — fcose
  settles at 1.18:1, already landscape, so it never fired) and the node locking that kept an
  already-placed net frozen.
- **Ask the free lever before the expensive one.** Moving a label costs nothing; spreading the
  net costs type size, because the camera then has more to fit onto the same wall. So
  `settlePlacement()`'s loosening loop runs `declutterLabels()` first and only loosens if that
  was not enough — worth 12.7px of type on the wall instead of 11.4px at 50 persons, at zero
  overlaps either way.
- **A force layout does not scale with how much is in it.** Labels reached the wall at 17 / 21
  / 15 / 15 px across seeded graphs of 3 / 6 / 20 / 50 persons — flat and non-monotone, which
  is the "fixed scale that eventually becomes unreadable" the brief rules out.
  `normaliseDensity()` scales the settled placement uniformly to a constant ink fraction of
  its own bounding box, and `settlePlacement()` loosens that target step by step until the
  picture is clean — so the delivered density is "as tight as these labels allow" rather than
  a constant tuned against one graph and one theme.
- `SEED_RADIUS` is deliberately much shorter than `idealEdgeLength`: `randomize: false` makes
  fcose sensitive to its starting state, and a compact golden-angle start cleared every
  density target to zero where a pre-spread one left 7–8 pairs.
- `placeNewNodes()` from cytoscape-layout-utilities would be the better seeding heuristic and
  is NOT used: it picks its quadrant and its jitter with `Math.random()`, and two pre-render
  runs over the same seed must produce the same picture.

**Third pre-render review — decision by Birk, 2026-08-14 (binding).** The labels must stop
piling up: the layout has to know that a term node is its dot PLUS its text block, a
post-layout pass must nudge label offsets (never node positions) apart, and labels must treat
portrait discs as obstacles they may not sit on — text on a person bubble is worse than text
on text, because the disc becomes a real photograph later. `settlePlacement()` carries the
first, `declutterLabels()` the other two.

Three things that took a measurement to find, all on the seeded 50-person / 75-term graph
(Task 20) at theme b, and all worth keeping in mind before touching this pipeline:

1. ~~**Rotate before separating, never after.**~~ *Retired at the fourth review:*
   `frameToAspect()` began with a quarter turn because cose measured repulsion with each
   node's width and height swapped and so settled a net of wide labels PORTRAIT. fcose does
   not have that bug — its raw output on the same graph is 1.18:1, already landscape — so the
   rotation never fired and was deleted. What the finding taught still stands as a warning: a
   rotation moves the dots while every label stays horizontal, so anything that turns the net
   must run BEFORE the separation, never after it.
2. **Neither relaxation is monotone.** Pushing box A clear of B pushes it into C, so both
   passes wander rather than descend (placement rounds measured 41, 32, 32, 28, 30, 33, 26,
   27, ...; a declutter run measured 44 pairs in and 49 out). Both therefore score every
   state, keep the best one they saw, and apply that — which also makes the declutter pass
   incapable of returning something worse than its own input.
3. **The caps were the binding constraint, not the step sizes.** The declutter pass needed
   300 iterations rather than 30, and the placement loop needs to run until the rounds stop
   paying rather than a fixed few.

The dial's own bug belongs here too: raising `min_mentions` REMOVES term nodes, so lowering it
again re-adds them, and until the server has persisted this session's positions those nodes
carry `x`/`y` null and read as brand new. Under the third review's rule that re-ran a layout
and moved half the net; under the fourth's it would start the returning half from the origin,
which makes their migration a jump while everyone else glides. Either way the fix is the same:
`createGraphView` remembers where each node was last seen and puts returning nodes back
exactly there before the migration begins.

**The Task 14 file listings in Steps 1–4 below predate the fcose migration** (they show the
`cose` layout, the locked-node rule and the rotation). The shipped
`frontend/static/projection.js` and `tests/test_projection.py` are authoritative for that
module; re-pasting them here would only add a second copy to drift.

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
  // cy.fit() takes either a padding or (collection, padding) — the camera
  // uses both, so the stub records which elements it was pointed at.
  fit(a, b) {
    // The real cy.fit() *sets* the zoom to the fit-all level; 1 stands in for
    // that here, so a zoom factor is always applied to a fresh fit and never
    // compounds with the level a previous call left behind.
    this._zoom = 1;
    if (b === undefined) this.calls.push(['fit', a]);
    else this.calls.push(['fit', a.stubName, b]);
  },
  pan(p) { if (p === undefined) return this._pan; this._pan = p; this.calls.push(['pan', p]); },
  // cy.zoom() takes a level or {level, renderedPosition}; the camera zooms
  // about the viewport centre, so the object form has to be understood.
  zoom(z) {
    if (z === undefined) return this._zoom;
    this._zoom = typeof z === 'object' ? z.level : z;
    this.calls.push(['zoom', this._zoom]);
  },
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


def test_the_default_zoom_factor_fits_the_whole_net(camera):
    assert camera.evaluate("window.cam.zoomFactor") == 1
    camera.evaluate("window.cam.onGraphChanged()")
    # Fit-all must stay exactly a fit: no zoom call on top of it.
    assert camera.evaluate("window.cyStub.calls.filter(c => c[0] === 'zoom').length") == 0


def test_a_zoom_factor_sits_that_many_times_tighter_than_fit_all(camera):
    camera.evaluate("window.cam.setZoomFactor(2)")
    assert camera.evaluate("window.cam.zoomFactor") == 2
    # fit() first (the stub leaves zoom at 1 = the fit-all level), then 2x it.
    assert camera.evaluate("window.cyStub._zoom") == 2
    assert camera.evaluate("window.cyStub.calls.filter(c => c[0] === 'fit').length") == 1


def test_the_zoom_factor_is_reapplied_when_the_graph_changes(camera):
    camera.evaluate("window.cam.setZoomFactor(3)")
    camera.evaluate("window.cyStub.calls.length = 0")
    camera.evaluate("window.cam.onGraphChanged()")
    assert camera.evaluate("window.cyStub.calls") == [["fit", 60], ["zoom", 3]]


def test_a_zoom_factor_below_one_is_rejected(camera):
    # Below 1 would frame emptiness around the net on an unattended wall.
    assert (
        camera.evaluate(
            "(() => { try { window.cam.setZoomFactor(0.5); return 'no'; } catch (e) { return 'raised'; } })()"
        )
        == "raised"
    )


def test_manual_mode_is_never_reframed_by_a_zoom_factor_change(camera):
    camera.evaluate("window.cam.setMode('manual')")
    camera.evaluate("window.cyStub.calls.length = 0")
    camera.evaluate("window.cam.setZoomFactor(4)")
    assert camera.evaluate("window.cyStub.calls.length") == 0


def test_focus_frames_only_the_given_elements(camera):
    camera.evaluate("window.cam.focus({stubName: 'cluster'}, 40)")
    assert camera.evaluate("window.cyStub.calls") == [["fit", "cluster", 40]]


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


def _unplaced_net(persons=8, terms_per_person=4, term_pool=12):
    """A graph with no persisted positions: the layout places all of it."""
    nodes = [
        {"id": f"p{i}", "type": "person", "portrait": "", "hidden": False, "x": None, "y": None}
        for i in range(persons)
    ] + [
        {
            "id": f"t{i}",
            "type": "term",
            "label": f"Kreislaufgerechte Bauteilkataloge {i}",
            "mentions": 2,
            "hidden": False,
            "x": None,
            "y": None,
        }
        for i in range(term_pool)
    ]
    edges = [
        {"id": f"e{i}-{j}", "source": f"p{i}", "target": f"t{(i * 3 + j) % term_pool}"}
        for i in range(persons)
        for j in range(terms_per_person)
    ]
    return {"version": 1, "min_mentions": 1, "nodes": nodes, "edges": edges, "quotes": []}


CANVAS_ASPECT = 1920 / 1080


def test_a_from_scratch_layout_is_shaped_like_the_16_9_canvas(view):
    # A force layout is isotropic, so its settled cloud is round and leaves
    # the sides of a 16:9 wall empty (measured 2026-08-14: the node cloud
    # covered 30% of the canvas width). The placement is framed to the
    # canvas instead of the camera over-zooming, which would clip top and
    # bottom.
    update(view, _unplaced_net())

    box = view.evaluate(
        "() => window.kgView.cy.nodes().boundingBox({ includeLabels: true })"
    )
    assert box["w"] / box["h"] == pytest.approx(CANVAS_ASPECT, rel=0.1)


def test_the_framed_net_covers_the_canvas_width_after_a_fit(view):
    # The number that matters is what reaches the wall, so measure the
    # rendered box under the camera's own fit, not just the model box.
    update(view, _unplaced_net())

    covered = view.evaluate(
        """() => {
             const cy = window.kgView.cy;
             const box = cy.nodes().renderedBoundingBox({ includeLabels: true });
             return box.w / cy.width();
           }"""
    )
    assert covered > 0.8


def test_framing_never_reshuffles_an_already_placed_net(view):
    # Framing is part of placing a net from scratch. Once nodes carry
    # positions, spec 11 rules: nothing already on the wall may move.
    update(view, _unplaced_net())
    before = view.evaluate("window.kgView.cy.$('#p0').position()")

    grown = _unplaced_net()
    for node in grown["nodes"]:
        position = view.evaluate("(id) => window.kgView.cy.$id(id).position()", node["id"])
        node["x"], node["y"] = position["x"], position["y"]
    grown["nodes"].append(
        {"id": "pX", "type": "person", "portrait": "", "hidden": False, "x": None, "y": None}
    )
    grown["edges"].append({"id": "eX", "source": "pX", "target": "t0"})
    update(view, grown)

    assert view.evaluate("window.kgView.cy.$('#p0').position()") == before


THEME_LABEL_SIZE = {
    # Declared --label-size tokens from the theme files. Since 2026-08-14 the
    # series is three dark variants that differ in type size and stroke
    # weight only (the inverted variant is gone), so this is the token that
    # separates them — and the one the whole series exists to decide.
    "a": "22px",
    "b": "32px",
    "c": "44px",
}

THEME_RING_WIDTH = {"a": "5px", "b": "7px", "c": "10px"}

ONE_PERSON = {
    "version": 1,
    "min_mentions": 1,
    "nodes": [
        {"id": "p1", "type": "person", "portrait": "", "hidden": False, "x": 0, "y": 0},
        {
            "id": "t1",
            "type": "term",
            "label": "Holzbau",
            "mentions": 1,
            "hidden": False,
            "x": 200,
            "y": 0,
        },
    ],
    "edges": [{"id": "e1", "source": "p1", "target": "t1"}],
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
    sizes = {}
    rings = {}
    for theme in ("a", "b", "c"):
        page.goto(f"{static_server}/frontend/projection.html?theme={theme}")
        page.wait_for_function("window.kgView !== undefined")
        page.evaluate("(g) => window.kgView.update(g, 1)", ONE_PERSON)
        wait_for_layout(page)
        sizes[theme] = page.evaluate("window.kgView.cy.$('#t1').style('font-size')")
        rings[theme] = page.evaluate("window.kgView.cy.$('#p1').style('border-width')")

    assert sizes == THEME_LABEL_SIZE
    assert rings == THEME_RING_WIDTH


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
    assert page.evaluate("window.kgView.cy.nodes().length") == len(ONE_PERSON["nodes"])


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


# --- Label declutter (Birk's third pre-render review, 2026-08-14) ---------
#
# series-b-dark-larger-label32.png (50 persons, 75 terms) showed labels
# piled on top of each other and on top of person discs. Three fixes:
#   a) the from-scratch placement must know a term node is its dot PLUS its
#      label box, not just the dot (cose's own nodeDimensionsIncludeLabels
#      is not enough on its own — measured below);
#   b) a post-layout pass nudges label OFFSETS (never positions) apart;
#   c) that pass treats person discs as fixed obstacles labels may not sit on.

# The real labels the pre-render shoots, not a short cycled sample of them.
# An earlier version of this module cycled 18 strings across 75 term nodes,
# which made the harness net measurably easier than the wall's own graph: the
# whole pipeline came out at 0 overlaps here while the seeded 50-person graph
# came out at 44 (2026-08-14). Distinct labels of very mixed length are the
# thing that makes this hard, so the fixture uses the same source the seeded
# graph does.
from sim.seed_graph import TERM_LABELS


def _dense_net(persons=50, terms=75, edges_per_person=5):
    """The density and label mix that first showed the label collisions this
    module exists to fix (Birk's 3rd pre-render review: 50 persons, 75
    distinct long German term labels, ~250 edges, on a 1920x1080 wall).
    Mentions cycle 1-2-3 so raising min_mentions removes some terms, not all
    of them, which is what the redeclutter-on-filter-change test needs."""
    nodes = [
        {"id": f"p{i}", "type": "person", "portrait": "", "hidden": False, "x": None, "y": None}
        for i in range(persons)
    ] + [
        {
            "id": f"t{i}",
            "type": "term",
            "label": TERM_LABELS[i % len(TERM_LABELS)],
            "mentions": (i % 3) + 1,
            "hidden": False,
            "x": None,
            "y": None,
        }
        for i in range(terms)
    ]
    edges = [
        {"id": f"e{i}-{j}", "source": f"p{i}", "target": f"t{(i * 7 + j * 3) % terms}"}
        for i in range(persons)
        for j in range(edges_per_person)
    ]
    return {"version": 1, "min_mentions": 1, "nodes": nodes, "edges": edges, "quotes": []}


def test_count_label_overlaps_detects_overlapping_labels_and_person_collisions(page, static_server):
    # A narrow, hand-placed unit test of the geometry itself, independent of
    # layout: two identical labels 5px apart must overlap (1 pair), a third
    # label placed exactly on a person disc must count against that person,
    # and a label far from everything must not pollute either count.
    page.goto(f"{static_server}/frontend/static/render-harness.html")
    page.wait_for_function("window.kgView !== undefined")
    result = page.evaluate(
        """async () => {
             const { countLabelOverlaps } = await import('/frontend/static/projection.js');
             const cy = window.kgView.cy;
             cy.add([
               { data: { id: 'pa', type: 'person' }, classes: 'person', position: { x: 0, y: 0 } },
               { data: { id: 'ta', type: 'term', label: 'Alpha Beta Gamma' }, classes: 'term', position: { x: 500, y: 500 } },
               { data: { id: 'tb', type: 'term', label: 'Alpha Beta Gamma' }, classes: 'term', position: { x: 505, y: 500 } },
               { data: { id: 'tc', type: 'term', label: 'Far Away Label' }, classes: 'term', position: { x: 0, y: 0 } },
             ]);
             return countLabelOverlaps(cy);
           }"""
    )
    assert result["labelPairs"] == 1
    assert result["labelsOnPersons"] == 1


def test_reset_label_offsets_returns_to_the_theme_default(view):
    update(view, GRAPH_1)
    result = view.evaluate(
        """async () => {
             const { resetLabelOffsets } = await import('/frontend/static/projection.js');
             const cy = window.kgView.cy;
             const node = cy.$('#t1');
             node.style({ 'text-margin-x': 40, 'text-margin-y': 90 });
             resetLabelOffsets(cy);
             return { x: node.numericStyle('text-margin-x'), y: node.numericStyle('text-margin-y') };
           }"""
    )
    # render-harness.html is pinned to theme-a: --label-margin-y: 6.
    assert result == {"x": 0, "y": 6}


def test_declutter_never_moves_a_node_position(view):
    # Position persistence (spec 11) is untouchable: decluttering is only
    # ever allowed to change where a LABEL sits relative to its own dot.
    update(view, _dense_net())
    before = view.evaluate(
        "() => Object.fromEntries(window.kgView.cy.nodes().map(n => [n.id(), n.position()]))"
    )

    view.evaluate("() => window.kgView.declutterLabels()")

    after = view.evaluate(
        "() => Object.fromEntries(window.kgView.cy.nodes().map(n => [n.id(), n.position()]))"
    )
    assert after == before


def test_declutter_clears_every_label_on_person_overlap(view):
    # Hard rule (c): text on a portrait disc is worse than text on text,
    # because the disc becomes a real photo later.
    update(view, _dense_net())
    overlaps = view.evaluate("() => window.kgView.labelOverlaps()")
    assert overlaps["labelsOnPersons"] == 0


def test_label_overlap_stats_record_before_and_after_declutter(view):
    update(view, _dense_net())
    stats = view.evaluate("() => window.kgView.labelOverlapStats")
    assert set(stats.keys()) == {"before", "after"}
    assert stats["after"]["labelPairs"] <= stats["before"]["labelPairs"]
    assert stats["after"]["labelsOnPersons"] <= stats["before"]["labelsOnPersons"]


def test_declutter_and_placement_are_deterministic(page, static_server):
    # Same seed, same picture: two independent from-scratch runs over the
    # identical graph must settle on identical node positions AND identical
    # label offsets, or the pre-render series (A-D at the same seed) would
    # stop being a fair comparison.
    graph = _dense_net()

    def run_once():
        page.goto(f"{static_server}/frontend/static/render-harness.html")
        page.wait_for_function("window.kgView !== undefined")
        update(page, graph)
        return page.evaluate(
            """() => {
                 const cy = window.kgView.cy;
                 const positions = {};
                 const offsets = {};
                 cy.nodes().forEach((n) => {
                   positions[n.id()] = n.position();
                   offsets[n.id()] = {
                     x: n.numericStyle('text-margin-x'),
                     y: n.numericStyle('text-margin-y'),
                   };
                 });
                 return { positions, offsets };
               }"""
        )

    first = run_once()
    second = run_once()
    assert first == second


def test_declutter_never_reshuffles_an_already_placed_dense_net(view):
    # Mirrors test_framing_never_reshuffles_an_already_placed_net at the
    # density where declutter actually does work: growing an already-placed
    # net must not move any existing node, even though every render re-runs
    # the full declutter pass over the whole graph (including those nodes).
    update(view, _dense_net())
    before = view.evaluate("window.kgView.cy.$('#p0').position()")

    grown = _dense_net()
    for node in grown["nodes"]:
        position = view.evaluate("(id) => window.kgView.cy.$id(id).position()", node["id"])
        node["x"], node["y"] = position["x"], position["y"]
    grown["nodes"].append(
        {"id": "pX", "type": "person", "portrait": "", "hidden": False, "x": None, "y": None}
    )
    grown["edges"].append({"id": "eX", "source": "pX", "target": "t0"})
    update(view, grown)

    assert view.evaluate("window.kgView.cy.$('#p0').position()") == before


def test_the_net_is_turned_to_landscape_before_it_is_separated(view):
    # The bug this pins down (found in the 3rd pre-render run, 2026-08-14):
    # frameToAspect may turn the whole net a quarter turn, and a rotation
    # moves the dots while every label stays horizontal. Separating first and
    # rotating after therefore throws the result away — measured on the
    # seeded graph, separation took 43 overlapping pairs down to 20 and the
    # rotation put it straight back to 48. So by the time the net is settled,
    # it must be BOTH landscape and clear; landscape alone or clear alone
    # would have passed while the picture on the wall was still a pile.
    update(view, _dense_net())

    box = view.evaluate(
        "() => window.kgView.cy.nodes().boundingBox({ includeLabels: true })"
    )
    assert box["w"] > box["h"]
    assert view.evaluate("() => window.kgView.labelOverlaps()") == {
        "labelPairs": 0,
        "labelsOnPersons": 0,
    }


def test_declutter_never_hands_back_a_worse_net_than_it_was_given(view):
    # Relaxation is not monotone: pushing a label clear of a person disc at
    # full strength drops it onto two others, and on the seeded graph a run
    # measured 44 overlapping pairs in and 49 out (2026-08-14). Whatever it
    # does in between, the pass must keep the best state it saw — and its own
    # untouched input is one of the candidates, so it can never regress.
    update(view, _dense_net())
    # Start from a deliberately bad state: every label shoved the same way,
    # so the pass has real work to do and a real chance to overshoot.
    # The braces matter: cy's forEach returns the collection, and serialising
    # that back to the driver crashes the page (same trap as PORTRAITS_LOADED
    # in sim/prerender.py). Return nothing.
    view.evaluate(
        "() => { window.kgView.cy.nodes('.term').forEach(n => n.style({'text-margin-x': 120})); }"
    )
    before = view.evaluate("() => window.kgView.labelOverlaps()")

    view.evaluate("() => window.kgView.declutterLabels()")

    after = view.evaluate("() => window.kgView.labelOverlaps()")
    assert after["labelPairs"] <= before["labelPairs"]
    assert after["labelsOnPersons"] <= before["labelsOnPersons"]


def test_lowering_the_dial_puts_the_returning_terms_back_where_they_were(view):
    # Raising min_mentions REMOVES term nodes from cy, so lowering it again
    # re-adds them. In a session whose positions the server has not yet
    # persisted back into the graph data, those nodes carry x/y null and would
    # read as brand new — which would re-run a layout and reshuffle half the
    # net under the visitor's eyes (spec 11). Found in the 3rd pre-render run:
    # the min_mentions 3 -> 1 shot came back 117% of the canvas height while
    # the identical picture on the way up had been 82%.
    update(view, _dense_net())
    before = view.evaluate(
        "() => Object.fromEntries(window.kgView.cy.nodes().map(n => [n.id(), n.position()]))"
    )

    view.evaluate("() => window.kgView.setMinMentions(3)")
    wait_for_layout(view)
    view.evaluate("() => window.kgView.setMinMentions(1)")
    wait_for_layout(view)

    after = view.evaluate(
        "() => Object.fromEntries(window.kgView.cy.nodes().map(n => [n.id(), n.position()]))"
    )
    assert after == before


def test_raising_min_mentions_redeclutters_and_lowers_overlap_count(view):
    # Removing labels only ever helps decluttering (fewer boxes to collide),
    # and render() must take that free win on every filter change, not just
    # on a from-scratch placement — a min_mentions change adds no new nodes
    # and so runs no layout at all.
    update(view, _dense_net())
    before = view.evaluate("() => window.kgView.labelOverlapStats.after")
    before_term_count = view.evaluate("() => window.kgView.cy.nodes('.term').length")

    view.evaluate("window.kgView.setMinMentions(2)")
    wait_for_layout(view)

    after = view.evaluate("() => window.kgView.labelOverlapStats.after")
    after_term_count = view.evaluate("() => window.kgView.cy.nodes('.term').length")

    assert after_term_count < before_term_count
    assert after["labelPairs"] <= before["labelPairs"]


def test_layout_separation_beats_coses_own_label_handling_alone(page, static_server):
    # cose's nodeDimensionsIncludeLabels only sizes a node's OWN repulsion
    # off its measured extent; it never learns that its neighbours are wide
    # too. Measured 2026-08-14 on theme-b (32px labels) at 50 persons / 75
    # terms, same deterministic golden-angle seeding both sides so this
    # isolates the fix rather than comparing against a differently-seeded
    # run: cose alone (nodeDimensionsIncludeLabels on, no post-layout
    # separation, no declutter) reproducibly settles at 9 overlapping
    # label-box pairs and 3 labels sitting on person discs. The full
    # from-scratch pipeline (separation pass + declutter) reproducibly
    # clears both to zero on this net — not just "fewer", gone.
    page.goto(f"{static_server}/frontend/projection.html?theme=b")
    page.wait_for_function("window.kgView !== undefined")
    graph = _dense_net()
    update(page, graph)

    after = page.evaluate("() => window.kgView.labelOverlaps()")

    raw = page.evaluate(
        """async (graph) => {
             const { toCytoscape } = await import('/frontend/static/graph-model.js');
             const { countLabelOverlaps, LAYOUT } = await import('/frontend/static/projection.js');
             const el = document.createElement('div');
             el.style.width = '1920px';
             el.style.height = '1080px';
             document.body.appendChild(el);
             const cy = cytoscape({
               container: el,
               style: window.kgView.cy.style().json(),
               elements: toCytoscape({ nodes: graph.nodes, edges: graph.edges }),
             });
             // Mirror projection.js's own from-scratch seeding exactly (golden
             // angle, radius 140, around the origin), so the only difference
             // from window.kgView's own run is the separation pass and the
             // declutter pass that follow layoutstop in production.
             graph.nodes.forEach((n, index) => {
               const angle = index * 2.39996;
               cy.$id(n.id).position({ x: Math.cos(angle) * 140, y: Math.sin(angle) * 140 });
             });
             await new Promise((resolve) => {
               const layout = cy.layout({ ...LAYOUT, animate: false });
               layout.one('layoutstop', resolve);
               layout.run();
             });
             const overlaps = countLabelOverlaps(cy);
             cy.destroy();
             el.remove();
             return overlaps;
           }""",
        graph,
    )

    assert raw["labelPairs"] >= 5
    assert raw["labelsOnPersons"] >= 1
    assert after == {"labelPairs": 0, "labelsOnPersons": 0}
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
  constructor(cy, { panSpeed = 18, padding = 60, zoomFactor = 1 } = {}) {
    this.cy = cy;
    this.panSpeed = panSpeed;
    this.padding = padding;
    // 1 = the whole net in frame. >1 = that many times tighter, i.e. only
    // 1/factor of the net's width is on the wall. Fit-all is illegible at 50
    // persons (pre-render series, 2026-08-14), so the zoom level is a setting
    // of this component, not a second camera bolted on next to it.
    this._zoomFactor = 1;
    this._mode = 'fit';
    this._direction = -1;
    // At an unattended exhibition a stray touch/mouse must never be able to
    // pan the viewport off-frame or drag a node off its persisted position.
    // `manual` is the only mode where a visitor is meant to move anything;
    // apply that for the initial mode too, not just from setMode onward.
    this._applyInteractivity(this._mode);
    this.setZoomFactor(zoomFactor);
  }

  get mode() {
    return this._mode;
  }

  get zoomFactor() {
    return this._zoomFactor;
  }

  setMode(mode) {
    if (!MODES.includes(mode)) throw new Error(`unknown camera mode: ${mode}`);
    this._mode = mode;
    this._applyInteractivity(mode);
    if (mode === 'fit') this._frame();
  }

  setZoomFactor(factor) {
    if (!(factor >= 1)) throw new Error(`zoom factor must be >= 1: ${factor}`);
    const changed = factor !== this._zoomFactor;
    this._zoomFactor = factor;
    // Manual is the visitor's mode: re-framing under their hands would fight
    // them. Every other mode is driven, so it re-frames at the new level.
    if (changed && this._mode !== 'manual') this._frame();
  }

  /** Point the camera at a subset — one cluster instead of the whole net.
   *
   * This is the framing an automatic traversal dwells on, and what the
   * pre-render shoots for the close view. It deliberately does not change the
   * mode: the interaction rules stay whatever the operator set. */
  focus(eles, padding = this.padding) {
    this.cy.fit(eles, padding);
  }

  _frame() {
    this.cy.fit(this.padding);
    if (this._zoomFactor === 1) return;
    // Zoom about the middle of the viewport, so the net stays centred on the
    // wall instead of drifting towards the model origin.
    this.cy.zoom({
      level: this.cy.zoom() * this._zoomFactor,
      renderedPosition: { x: this.cy.width() / 2, y: this.cy.height() / 2 },
    });
  }

  _applyInteractivity(mode) {
    const interactive = mode === 'manual';
    this.cy.userPanningEnabled(interactive);
    this.cy.userZoomingEnabled(interactive);
    this.cy.autoungrabify(!interactive);
  }

  onGraphChanged() {
    if (this._mode === 'fit') this._frame();
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
        'background-color': cssVar('--person-fill', '#242424'),
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
        'background-color': cssVar('--term-dot-color', '#FFFFFF'),
        label: 'data(label)',
        color: cssVar('--label-color', '#FFFFFF'),
        'font-family': cssVar('--label-font', 'Georgia, serif'),
        'font-size': cssVar('--label-size', '22'),
        'text-valign': 'bottom',
        // Both scale with the type: a wrap width and a gap tuned for 22px
        // labels turn 44px ones into a stack of short lines under the dot.
        'text-margin-y': cssVar('--label-margin-y', '6'),
        'text-wrap': 'wrap',
        'text-max-width': cssVar('--label-max-width', '220px'),
        'text-outline-width': cssVar('--label-outline-width', '3'),
        'text-outline-color': cssVar('--label-outline-color', '#000000'),
      },
    },
    {
      selector: 'edge.link',
      style: {
        width: cssVar('--edge-width', '2'),
        'line-color': cssVar('--edge-color', '#858585'),
        'curve-style': 'straight',
        opacity: cssVar('--edge-opacity', '0.75'),
      },
    },
  ];
}

export const LAYOUT = {
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

// Nodes are always visited in this order, never Cytoscape's own collection
// order (which is insertion order and so depends on network/API timing) —
// otherwise the same seed could settle differently between two runs.
function byId(a, b) {
  const idA = a.id();
  const idB = b.id();
  if (idA < idB) return -1;
  if (idA > idB) return 1;
  return 0;
}

function boxesOverlap(a, b) {
  return a.x1 < b.x2 && a.x2 > b.x1 && a.y1 < b.y2 && a.y2 > b.y1;
}

// The minimum-translation vector to move box `a` clear of box `b`, along
// whichever axis needs the smaller push. Ties (concentric boxes) resolve
// toward positive x/y, deterministically, rather than toward whatever
// floating-point noise happens to fall out of the centre comparison.
function overlapVector(a, b) {
  const ox = Math.min(a.x2, b.x2) - Math.max(a.x1, b.x1);
  const oy = Math.min(a.y2, b.y2) - Math.max(a.y1, b.y1);
  if (ox <= 0 || oy <= 0) return null;
  const ac = { x: (a.x1 + a.x2) / 2, y: (a.y1 + a.y2) / 2 };
  const bc = { x: (b.x1 + b.x2) / 2, y: (b.y1 + b.y2) / 2 };
  if (ox < oy) return { x: ac.x >= bc.x ? ox : -ox, y: 0 };
  return { x: 0, y: ac.y >= bc.y ? oy : -oy };
}

/** Count overlapping term-label boxes, and label-on-person collisions.
 *
 * `includeNodes: false` on a boundingBox call isolates the LABEL's own box
 * from its dot — Cytoscape's real measured text extent (font metrics, wrap
 * width), not a guess — so this is exactly what a viewer would see collide.
 * Exported so the pre-render CLI and the dev console can both ask "how bad
 * is it right now" without reaching into private state.
 */
export function countLabelOverlaps(cy) {
  const terms = cy.nodes('.term').sort(byId);
  const boxes = terms.map((node) => node.boundingBox({ includeLabels: true, includeNodes: false }));
  let labelPairs = 0;
  for (let i = 0; i < boxes.length; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      if (boxesOverlap(boxes[i], boxes[j])) labelPairs += 1;
    }
  }

  const personBoxes = cy.nodes('.person').map((node) => node.boundingBox({ includeNodes: true, includeLabels: false }));
  let labelsOnPersons = 0;
  boxes.forEach((box) => {
    personBoxes.forEach((personBox) => {
      if (boxesOverlap(box, personBox)) labelsOnPersons += 1;
    });
  });

  return { labelPairs, labelsOnPersons };
}

// cose's own nodeDimensionsIncludeLabels sizes each node's repulsion off its
// OWN measured extent, but never learns that a neighbour's label is wide too
// — measured 2026-08-14 on the seeded 50-person / 75-term graph at theme b,
// cose alone settles at 43 overlapping label-box pairs and 30 labels sitting
// on person discs. This pass pushes the MEASURED dot+label boxes
// (Cytoscape's own boundingBox, not a guessed constant) apart directly, in
// node-position space, so the layout finally "knows" a term node is its dot
// plus its caption.
//
// It is a relaxation with a cap, NOT a solver: on that graph it does not
// reach a clean state within the cap, and raising the cap to 400 only takes
// one round's result from 25 pairs to 17 for ~5x the time. Getting to zero
// is the job of the rounds in settlePlacement() and the declutter pass
// afterwards, both of which are far cheaper per pair removed.
const SEPARATION_ITERATIONS = 60;
// Resolve half of every overlap per pass, not all of it: a node colliding
// with several neighbours at once would otherwise overshoot on each of them
// simultaneously.
const SEPARATION_STEP = 0.5;

function fullBox(node) {
  return node.boundingBox({ includeLabels: true });
}

export function separateOverlappingNodes(cy) {
  const nodes = cy.nodes().sort(byId);
  if (nodes.length < 2) return;
  for (let iteration = 0; iteration < SEPARATION_ITERATIONS; iteration += 1) {
    const boxes = nodes.map((node) => fullBox(node));
    const push = nodes.map(() => ({ x: 0, y: 0 }));
    let anyOverlap = false;
    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        const v = overlapVector(boxes[i], boxes[j]);
        if (!v) continue;
        anyOverlap = true;
        push[i].x += v.x * SEPARATION_STEP;
        push[i].y += v.y * SEPARATION_STEP;
        push[j].x -= v.x * SEPARATION_STEP;
        push[j].y -= v.y * SEPARATION_STEP;
      }
    }
    if (!anyOverlap) break;
    nodes.forEach((node, index) => {
      const at = node.position();
      node.position({ x: at.x + push[index].x, y: at.y + push[index].y });
    });
  }
}

// This is a relaxation, and on a crowded net it needs room to run: measured
// 2026-08-14 from the settled placement of the seeded 50-person / 75-term
// graph at theme b, a 30-iteration cap stalls at 18 overlapping label pairs
// while 300 clears the same state to zero (~1s). The cap is the binding
// constraint here, not the step size and not the displacement budget below —
// no label ever reaches that budget on this net.
const DECLUTTER_ITERATIONS = 300;
const DECLUTTER_STEP = 0.5;
// A label may wander further than this from its dot's default position
// before it stops reading as that dot's caption. Scaled off the label's
// OWN measured box height, not a constant, because the theme series ranges
// from 22px to 44px type — a fixed pixel cap tuned for one theme would be
// meaningless (too tight or too loose) on the others.
const MAX_LABEL_DISPLACEMENT_LINES = 2;
// How many label-on-label pairs one label-on-portrait collision is worth when
// scoring a candidate state (rule (c) over rule (b), see below).
const PERSON_COLLISION_WEIGHT = 3;

/** Nudge label OFFSETS (never node positions) until no two term-label boxes
 * overlap, and no term-label box overlaps a person disc.
 *
 * Idempotent: it starts from whatever text-margin-x/y a node already
 * carries (0 / the theme's --label-margin-y default if untouched, or a
 * previous call's result), so calling it again on an already-clear net
 * measures zero overlaps on the first iteration and changes nothing.
 * Person discs are fixed obstacles here — only the label moves.
 */
export function declutterLabels(cy) {
  const terms = cy.nodes('.term').sort(byId);
  if (terms.length === 0) return;
  const persons = cy.nodes('.person').toArray();
  const baseMarginY = Number(cssVar('--label-margin-y', '6'));

  const state = terms.map((node) => ({
    node,
    x: node.numericStyle('text-margin-x'),
    y: node.numericStyle('text-margin-y'),
    // A label's own box height barely changes with its margin (the margin
    // shifts it, the wrap width sizes it), so its displacement budget is
    // measured once, up front, from that near-constant height.
    cap: node.boundingBox({ includeLabels: true, includeNodes: false }).h * MAX_LABEL_DISPLACEMENT_LINES,
  }));

  const applyState = () => state.forEach(({ node, x, y }) => node.style({ 'text-margin-x': x, 'text-margin-y': y }));

  // Relaxation this simple is not monotone: a label pushed clear of a person
  // disc at full strength lands on two other labels, and on a crowded net a
  // late iteration can end up worse than an early one (measured 2026-08-14:
  // 48 pairs in, 70 pairs out, on the seeded graph before this guard). So
  // every iteration is scored and the best one is what gets applied at the
  // end — including iteration 0, the untouched input, which makes the pass
  // incapable of handing back something worse than it was given.
  let best = null;
  const remember = (score) => {
    if (best && score >= best.score) return;
    best = { score, offsets: state.map(({ x, y }) => ({ x, y })) };
  };

  for (let iteration = 0; iteration < DECLUTTER_ITERATIONS; iteration += 1) {
    applyState();
    const boxes = state.map(({ node }) => node.boundingBox({ includeLabels: true, includeNodes: false }));
    const personBoxes = persons.map((p) => p.boundingBox({ includeNodes: true, includeLabels: false }));

    const push = state.map(() => ({ x: 0, y: 0 }));
    let anyOverlap = false;
    let labelPairs = 0;
    let labelsOnPersons = 0;

    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        const v = overlapVector(boxes[i], boxes[j]);
        if (!v) continue;
        anyOverlap = true;
        labelPairs += 1;
        push[i].x += v.x * DECLUTTER_STEP;
        push[i].y += v.y * DECLUTTER_STEP;
        push[j].x -= v.x * DECLUTTER_STEP;
        push[j].y -= v.y * DECLUTTER_STEP;
      }
      // A person disc never moves, so a label overlapping one is resolved
      // at full strength rather than split — the hard "may not overlap"
      // rule (c) should win out over the softer label-label spacing (b).
      personBoxes.forEach((personBox) => {
        const v = overlapVector(boxes[i], personBox);
        if (!v) return;
        anyOverlap = true;
        labelsOnPersons += 1;
        push[i].x += v.x;
        push[i].y += v.y;
      });
    }

    // Rule (c) outranks rule (b): a label on a portrait disc is worse than a
    // label on a label, because the disc becomes a real photograph later. A
    // state that clears one person collision is therefore preferred even if
    // it costs a few label-on-label pairs.
    remember(labelPairs + PERSON_COLLISION_WEIGHT * labelsOnPersons);
    if (!anyOverlap) break;

    state.forEach((entry, index) => {
      entry.x += push[index].x;
      entry.y += push[index].y;
      const dx = entry.x;
      const dy = entry.y - baseMarginY;
      const dist = Math.hypot(dx, dy);
      if (dist > entry.cap && dist > 0) {
        const scale = entry.cap / dist;
        entry.x = dx * scale;
        entry.y = baseMarginY + dy * scale;
      }
    });
  }

  if (best) {
    state.forEach((entry, index) => {
      entry.x = best.offsets[index].x;
      entry.y = best.offsets[index].y;
    });
  }
  applyState();
}

/** Clear every per-node label offset back to the theme default, undoing
 * declutterLabels(). Removing the style bypass (rather than setting it to
 * a computed default) means a later theme swap still takes effect through
 * the normal stylesheet cascade.
 */
export function resetLabelOffsets(cy) {
  cy.nodes('.term').forEach((node) => node.removeStyle('text-margin-x text-margin-y'));
}

// The projection surface is 16:9. A force layout is isotropic, so its settled
// cloud is round: on 1920x1080 that leaves the sides empty (measured
// 2026-08-14: 30% of the canvas width) and the camera cannot recover it —
// zooming in further only clips the top and bottom.
const CANVAS_ASPECT = 16 / 9;
// A label keeps its own width when the nodes around it move apart, so one
// correction always undershoots the target. Iterate to it instead.
const FRAME_STEPS = 6;
const FRAME_TOLERANCE = 0.01;
// The stretch is the part of the framing that does distort, so it is bounded:
// beyond this the net is a smear, and something about the layout is wrong.
const MAX_STRETCH = 3;

/** Shape a from-scratch placement like the canvas it is projected onto.
 *
 * Deterministic: a pure function of the settled positions, so the same seed
 * still yields the same picture. Exported so it can be exercised on its own.
 */
export function frameToAspect(cy, target = CANVAS_ASPECT, { rotate = true } = {}) {
  const nodes = cy.nodes();
  if (nodes.length < 2) return;
  let box = nodes.boundingBox({ includeLabels: true });
  if (!(box.w > 0) || !(box.h > 0)) return;

  // Cytoscape's cose measures repulsion with each node's width and height
  // swapped, so a net of wide labels settles PORTRAIT — exactly the wrong way
  // round for this wall. A quarter turn costs no distortion at all and does
  // most of the work; only what remains is stretched.
  if (rotate && (box.w < box.h) === (target > 1)) {
    const centre = { x: (box.x1 + box.x2) / 2, y: (box.y1 + box.y2) / 2 };
    nodes.positions((node) => {
      const at = node.position();
      return { x: centre.x + (at.y - centre.y), y: centre.y - (at.x - centre.x) };
    });
    box = nodes.boundingBox({ includeLabels: true });
  }

  let stretched = 1;
  for (let step = 0; step < FRAME_STEPS; step += 1) {
    const aspect = box.w / box.h;
    // Only ever pull the short axis out to the target. Squeezing the long one
    // would push labels together, which is what this whole series is about.
    const scale = aspect < target ? { x: target / aspect, y: 1 } : { x: 1, y: aspect / target };
    if (Math.max(scale.x, scale.y) < 1 + FRAME_TOLERANCE) return;
    const capped = Math.min(Math.max(scale.x, scale.y), MAX_STRETCH / stretched);
    if (capped <= 1) return;
    stretched *= capped;
    const factor = { x: scale.x > 1 ? capped : 1, y: scale.y > 1 ? capped : 1 };
    const centre = { x: (box.x1 + box.x2) / 2, y: (box.y1 + box.y2) / 2 };
    nodes.positions((node) => {
      const at = node.position();
      return {
        x: centre.x + (at.x - centre.x) * factor.x,
        y: centre.y + (at.y - centre.y) * factor.y,
      };
    });
    box = nodes.boundingBox({ includeLabels: true });
  }
}

// Separation and framing pull against each other, so one round of each
// undershoots: separating pushes boxes apart along whichever axis is
// cheapest, which pulls the cloud back towards square, and re-stretching it
// to 16:9 opens gaps that let the next separation round resolve collisions
// it previously had no room for. It takes several rounds to break through —
// measured 2026-08-14 on the live projection page at theme b with the seeded
// 50-person / 75-term graph, overlapping label pairs by round: 24, 24, 24,
// 24, 5, 4, 2, then flat. Stopping at four (which looked like plenty on the
// offline runs) leaves 18 pairs on the wall; running on to convergence
// leaves 2.
//
// So this is a cap, not a target: the loop below stops as soon as the rounds
// stop paying, and each round costs real time (~1-3s on that graph, all of
// it inside boundingBox). It runs once, on a from-scratch placement only.
const PLACEMENT_ROUNDS = 16;
// Rounds that buy nothing before giving up. One flat round is not enough
// evidence — the measurement above sat at 24 for four rounds before it broke
// through to 5.
const PLACEMENT_PATIENCE = 5;

/** Shape a from-scratch placement for this wall: 16:9, and with the layout
 * finally knowing that a term node is its dot PLUS its label box.
 *
 * ORDER MATTERS, and it is the opposite of the obvious one. `frameToAspect`
 * may turn the whole net a quarter turn, and a rotation moves the dots while
 * every label stays horizontal — so a net separated first and rotated after
 * comes out overlapping again (measured on the same graph: separation took
 * 43 pairs down to 20, and the rotation put it back to 48). Rotate FIRST, in
 * the orientation the wall will actually show, and only then separate.
 */
export function settlePlacement(cy) {
  frameToAspect(cy);
  const nodes = cy.nodes().sort(byId);
  const snapshot = () => nodes.map((node) => ({ ...node.position() }));
  let best = { score: Infinity, positions: null };
  let flatRounds = 0;

  for (let round = 0; round < PLACEMENT_ROUNDS; round += 1) {
    separateOverlappingNodes(cy);
    // No rotation from here on: the orientation is settled above, and a
    // separation round that happens to leave the cloud taller than wide must
    // not be allowed to spin the whole picture a quarter turn.
    frameToAspect(cy, CANVAS_ASPECT, { rotate: false });
    const { labelPairs, labelsOnPersons } = countLabelOverlaps(cy);
    const score = labelPairs + PERSON_COLLISION_WEIGHT * labelsOnPersons;
    if (score < best.score) {
      best = { score, positions: snapshot() };
      flatRounds = 0;
    } else if ((flatRounds += 1) >= PLACEMENT_PATIENCE) {
      break;
    }
    if (labelPairs === 0 && labelsOnPersons === 0) break;
  }

  // Pushing node A clear of B can push it into C, so the rounds do not
  // descend cleanly — measured 2026-08-14 on the seeded graph they wander
  // (41, 32, 32, 28, 30, 33, 26, 27, ...). Ending on whatever the last round
  // happened to produce would throw away a better picture the loop had
  // already found and paid for, so the best one is what gets kept.
  if (best.positions) {
    nodes.forEach((node, index) => node.position({ ...best.positions[index] }));
  }
}

// Reset then declutter, and measure both sides of it. `before` is the
// layout's own settled state (positions final, labels still at the theme
// default); `after` is what a viewer actually sees. Run on every render —
// including a min_mentions change, which adds no new nodes and so runs no
// layout — because raising the dial only ever removes labels and the pass
// should take that free win immediately, not carry over stale offsets
// sized for a denser picture.
function settleLabels(cy) {
  resetLabelOffsets(cy);
  const before = countLabelOverlaps(cy);
  declutterLabels(cy);
  const after = countLabelOverlaps(cy);
  return { before, after };
}

export function createGraphView(container, { onPositions = () => {} } = {}) {
  const cy = cytoscape({ container, style: style(), wheelSensitivity: 0.2 });
  const camera = new Camera(cy);
  let lastGraph = { nodes: [], edges: [], min_mentions: 1 };
  let minMentions = 1;
  // True while an animated layout is running. Tests and the pre-render wait on
  // this instead of guessing a timeout; positions land only at `layoutstop`.
  let layoutPending = false;
  const emptyStats = { labelPairs: 0, labelsOnPersons: 0 };
  let labelOverlapStats = { before: emptyStats, after: emptyStats };
  // Where each node was last seen, by id. The dial hides term nodes by
  // REMOVING them from cy, so turning it back down re-adds them — and until
  // the server has round-tripped this session's positions back into
  // `lastGraph`, those nodes carry x/y null and would read as brand new. Left
  // to that, lowering the dial would re-run a layout and visibly reshuffle
  // the returning half of the net (spec 11). They go back exactly where they
  // were instead.
  const lastSeen = new Map();

  function render() {
    const view = visibleGraph(lastGraph, minMentions);
    const wanted = new Set(view.nodes.map((n) => n.id).concat(view.edges.map((e) => e.id)));
    const present = cy.elements().map((el) => el.id());

    cy.nodes().forEach((n) => lastSeen.set(n.id(), { ...n.position() }));

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
    const returning = newNodeIds(present, view).filter((id) => !placed.has(id) && lastSeen.has(id));
    const fresh = newNodeIds(present, view).filter((id) => !placed.has(id) && !lastSeen.has(id));
    const toAdd = toCytoscape(view).filter((el) => cy.$id(el.data.id).length === 0);
    if (toAdd.length) cy.add(toAdd);
    returning.forEach((id) => cy.$id(id).position({ ...lastSeen.get(id) }));

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
      // Nothing is placed yet, so this layout owns the whole picture and may
      // shape it to the canvas. Every later layout only adds to a net that is
      // already on the wall, and must leave that net exactly where it is.
      const fromScratch = existing.length === 0;
      const layout = cy.layout(LAYOUT);
      layoutPending = true;
      layout.one('layoutstop', () => {
        existing.unlock();
        // The layout only ever separated dots; this shapes the placement to
        // the wall and teaches it about the label boxes it settled without.
        if (fromScratch) settlePlacement(cy);
        labelOverlapStats = settleLabels(cy);
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
      labelOverlapStats = settleLabels(cy);
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
    get labelOverlapStats() {
      return labelOverlapStats;
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
    declutterLabels() {
      declutterLabels(cy);
    },
    resetLabelOffsets() {
      resetLabelOffsets(cy);
    },
    labelOverlaps() {
      return countLabelOverlaps(cy);
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

`frontend/static/theme-a.css` — **A: the reference — white on black at the concept
rendering's weights** (second pre-render review, revised 2026-08-14: the series A-B-C now
varies only type size and stroke/outline weight; Birk could not read the 22px labels on
1080 lines):

```css
/* A: the reference. White on black at the concept rendering's weights.
   The series A-B-C varies ONLY type size and stroke/outline weight (Birk,
   2026-08-14: he could not read the labels at 22px on 1080 lines). Every
   colour below is therefore identical in all three themes — a variant that
   also moved the palette would not answer the legibility question.

   PURE black ground and PURE white text (Birk, 2026-08-15, binding, applied
   to a/b/c alike): the ground was #101014 and the labels #F5F1E6, a
   blue-tinted near-black under a cream near-white. Projection is additive and
   the surface is a whiteboard, so on-site black is whatever ambient light
   sits on it (spec 10.4) — a tint gains nothing there and costs contrast,
   while pure values hand the projector its full range (16.8:1 before,
   21:1 now). --label-outline-color follows --bg exactly, or the outline
   reads as a halo instead of disappearing into the ground. --term-dot-color
   went to pure white with the labels: the dot and its caption are one node
   and nothing asks them to differ. --edge-color was restated as the NEUTRAL
   grey of the same relative luminance (#8A8578 -> #858585, L=0.235 either
   way), so edges stay exactly as subordinate to the labels as they were
   tuned to be. --ring-color stays gold: it is the concept's signature and is
   the one element that is not greyscale.

   --person-size shrunk 96 -> 56 (Birk's 3rd review, 2026-08-14): the fill is
   now a flat placeholder colour with no information in it, so the disc no
   longer needs to be large enough to carry a face-shaped gradient — only the
   --ring-color ring does, and that stays untouched here. --person-fill was
   neutralised with the rest (#23232a -> #242424, same luminance): it is only
   ever seen when a portrait is missing, and a blue cast there would be the
   one tint left on the wall. */
:root {
  --bg: #000000;
  --person-size: 56;
  --person-fill: #242424;
  --ring-color: #C9A227;
  --ring-width: 5;
  --term-dot: 14;
  --term-dot-color: #FFFFFF;
  --label-color: #FFFFFF;
  --label-font: Georgia, "Times New Roman", serif;
  --label-size: 22;
  --label-outline-width: 3;
  --label-outline-color: #000000;
  --label-max-width: 220px;
  --label-margin-y: 6;
  --edge-color: #858585;
  --edge-width: 2;
  --edge-opacity: 0.75;
}
```

`frontend/static/theme-b.css` — **B: larger type** (second pre-render review, revised
2026-08-14: B was the inverted light-ground variant until now; Birk rejected that outright
— white on black stays — and the slot went to legibility instead):

```css
/* B: larger type. 32px labels (1.45x A) with the dots, rings, edges and text
   outline scaled with them so the picture stays balanced rather than becoming
   big text over a thin net. Same dark ground and same palette as A — this
   variant answers "is it the size?", nothing else.

   B was the inverted light-ground variant until 2026-08-14; Birk rejected
   that outright (white on black stays), and the slot went to legibility.

   --person-size shrunk 128 -> 76 (Birk's 3rd review, same date), same ratio
   as A and C: the placeholder fill is now uniform and carries no
   information, so the disc can shrink while --ring-width stays as heavy as
   before — the ring, not the fill, is the concept's carrier.

   The palette went to PURE black / PURE white on 2026-08-15 (Birk, binding,
   identically in a/b/c). The rationale and the per-token derivation live in
   theme-a.css, which is this ladder's reference; the values below must stay
   character-for-character identical to it, since the series answers "is it
   the size?" and nothing else. */
:root {
  --bg: #000000;
  --person-size: 76;
  --person-fill: #242424;
  --ring-color: #C9A227;
  --ring-width: 7;
  --term-dot: 20;
  --term-dot-color: #FFFFFF;
  --label-color: #FFFFFF;
  --label-font: Georgia, "Times New Roman", serif;
  --label-size: 32;
  --label-outline-width: 4;
  --label-outline-color: #000000;
  --label-max-width: 320px;
  --label-margin-y: 8;
  --edge-color: #858585;
  --edge-width: 3;
  --edge-opacity: 0.8;
}
```

`frontend/static/theme-c.css` — **C: much larger type, heaviest strokes** (second
pre-render review, revised 2026-08-14: same dark ground and palette as A and B, not a
separate colour treatment):

```css
/* C: much larger type, heaviest strokes. 44px labels (2x A), a 6px outline
   under them, and rings/dots/edges heavy enough to still read as a net at
   that type size. Same dark ground and same palette as A and B. This is the
   upper end of the legibility ladder: whatever cannot be read here cannot be
   read at all at 50 persons in one frame, and the answer is the camera
   (spec 10.3), not more type.

   --person-size shrunk 168 -> 100 (Birk's 3rd review, same date), keeping
   the A/B/C ladder proportional: the fill is now a flat, information-free
   placeholder, so it no longer needs to dominate the frame — --ring-width
   stays at its full weight and does that job instead.

   The palette went to PURE black / PURE white on 2026-08-15 (Birk, binding,
   identically in a/b/c). The rationale and the per-token derivation live in
   theme-a.css, which is this ladder's reference; the values below must stay
   character-for-character identical to it, since the series answers "is it
   the size?" and nothing else. */
:root {
  --bg: #000000;
  --person-size: 100;
  --person-fill: #242424;
  --ring-color: #C9A227;
  --ring-width: 10;
  --term-dot: 28;
  --term-dot-color: #FFFFFF;
  --label-color: #FFFFFF;
  --label-font: Georgia, "Times New Roman", serif;
  --label-size: 44;
  --label-outline-width: 6;
  --label-outline-color: #000000;
  --label-max-width: 440px;
  --label-margin-y: 11;
  --edge-color: #858585;
  --edge-width: 5;
  --edge-opacity: 0.85;
}
```

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_camera.py tests/test_projection.py -v`
Expected: PASS (24 tests) — 15 verified by a real run on 2026-08-13 during
the task-14 review-findings pass (8 camera + 7 projection; the original
brief's 10 became 15 after adding the camera-interactivity tests for finding
3, the theme-baking regression test for finding 1, and the
theme-error-fallback regression test for the finding-2 follow-up (a bad
`?theme=` value must degrade to the default theme and still render instead of
hanging the theme-load promise forever)). The second pre-render review
(2026-08-14) added the remaining 9: six for the camera's zoom factor and
`focus()`, and three for the 16:9 framing of a from-scratch placement.

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
    # The trailing `void 0;` is load-bearing, not stylistic: without it the
    # expression's completion value is the assigned function itself, and
    # Playwright's evaluate() calls that completion value with no arguments
    # while producing its own return value — a driver-level artifact
    # (reproduces on about:blank with any unrelated global name, nothing to
    # do with fetch or this app), which throws inside our mock on
    # `opts.body` before `render()` ever gets a chance to run.
    page.evaluate(
        "window.fetch = (url, opts) => { window.kgFetches.push([url, JSON.parse(opts.body)]);"
        " return Promise.resolve({ok: true, json: () => Promise.resolve({})}); }; void 0;"
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


def test_a_rejected_fetch_reverts_the_dial_and_camera_and_the_page_keeps_working(ui):
    warnings = []
    ui.on("console", lambda msg: warnings.append(msg.text) if msg.type == "warning" else None)
    ui.evaluate("window.fetch = () => Promise.reject(new Error('network down')); void 0;")

    ui.select_option("#min-mentions", "3")
    assert ui.eval_on_selector("#min-mentions", "el => el.value") == "2"

    ui.select_option("#camera", "fit")
    assert ui.eval_on_selector("#camera", "el => el.value") == "pan"

    assert any("api/min_mentions" in w for w in warnings)
    assert any("api/camera" in w for w in warnings)

    # The page keeps working afterwards: a subsequent request still fires normally.
    ui.evaluate(
        "window.fetch = (url, opts) => { window.kgFetches.push([url, JSON.parse(opts.body)]);"
        " return Promise.resolve({ok: true, json: () => Promise.resolve({})}); }; void 0;"
    )
    ui.click("#entry-t1 button.hide")
    assert ui.evaluate("window.kgFetches[0]") == ["/api/hidden", {"node_id": "term:t1", "hidden": True}]


def test_a_non_ok_response_reverts_the_dial_and_camera_and_the_page_keeps_working(ui):
    warnings = []
    ui.on("console", lambda msg: warnings.append(msg.text) if msg.type == "warning" else None)
    ui.evaluate(
        "window.fetch = () => Promise.resolve({ok: false, status: 400, statusText: 'Bad Request',"
        " json: () => Promise.resolve({})}); void 0;"
    )

    ui.select_option("#min-mentions", "3")
    assert ui.eval_on_selector("#min-mentions", "el => el.value") == "2"

    ui.select_option("#camera", "fit")
    assert ui.eval_on_selector("#camera", "el => el.value") == "pan"

    assert any("api/min_mentions" in w for w in warnings)
    assert any("api/camera" in w for w in warnings)

    # The page keeps working afterwards: the hide list still re-renders and a
    # subsequent request still fires normally.
    assert ui.eval_on_selector_all(".entry .label", "els => els.map(e => e.textContent)") == [
        "Unfug",
        "Holzbau",
    ]
    ui.evaluate(
        "window.fetch = (url, opts) => { window.kgFetches.push([url, JSON.parse(opts.body)]);"
        " return Promise.resolve({ok: true, json: () => Promise.resolve({})}); }; void 0;"
    )
    ui.click("#entry-t1 button.hide")
    assert ui.evaluate("window.kgFetches[0]") == ["/api/hidden", {"node_id": "term:t1", "hidden": True}]
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

// The last graph/state a render() call actually received — from the server,
// via /events, not merely attempted. post() reverts to these on failure, so
// this is the exhibition's only feedback for a control the server never
// confirmed (see the catch below): no toast/banner, just the control
// snapping back to the truth.
let lastGraph = { nodes: [], edges: [], quotes: [] };
let lastState = { min_mentions: 1, camera_mode: 'fit', stt_connected: false, interview: null };

function post(url, body) {
  return fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
    .then((response) => {
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    })
    .catch((error) => {
      // This is the sole human control surface for the exhibition: a write
      // that the server never confirmed must not leave the operator staring
      // at a control showing a change that did not happen.
      console.warn(`request to ${url} failed`, error);
      render(lastGraph, lastState);
    });
}

function entryRow(node) {
  const item = document.createElement('li');
  item.className = `entry ${node.hidden ? 'hidden' : ''}`.trim();
  item.id = `entry-${node.id}`;

  // render() only ever passes term nodes here (see the filter below), so
  // this has no person branch to fall into — kept simple on purpose rather
  // than handling a case that can't occur.
  const label = document.createElement('span');
  label.className = 'label';
  label.textContent = node.label;
  item.appendChild(label);

  const meta = document.createElement('span');
  meta.className = 'meta';
  meta.textContent = `${node.mentions}×`;
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
  lastGraph = graph;
  lastState = state;

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
Expected: PASS (9 tests)

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
<!-- Relative, like projection.html: served at /testpattern these resolve to
     /static/…. Ground comes from theme-d.css, linked after base.css (same
     order as projection.html), so the wedge is read against the same
     background as variant A, not a hard-coded copy of it. -->
<link rel="stylesheet" href="static/base.css">
<link rel="stylesheet" href="static/theme-d.css">
<style>
  body { width: 1920px; height: 1080px; color: #fff;
         font-family: Georgia, "Times New Roman", serif; }
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
   the greyscale wedge is read against the reference background — which went
   to pure #000000 with the graph themes on 2026-08-15, so the wedge's own 0%
   step and the page it sits on are now the same value. That is the point of
   the pattern on site: whatever the whiteboard shows there IS the black
   level, and the wedge measures it. */
:root { --bg: #000000; }
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
  - `kg.core.settle_cut_end(transcript_log, stopped_at, timeout=SETTLE_TIMEOUT_S, poll_interval=SETTLE_POLL_S) -> float` — the ≤3 s Telegram-text-only settle window (spec §5).
  - `kg.core.Core(cfg, store, bus, transcript_log, llm, embedder, processor=process_interview, settle_timeout_s=SETTLE_TIMEOUT_S, settle_poll_s=SETTLE_POLL_S)` with the sync callbacks `on_photo(photo_path, portrait_path, at)`, `on_text(text, at)`, `on_final(event)`, `on_partial(event)`, `on_stt_state(connected)`, the coroutine `run_tick_loop(interval=5.0)`, and `async def drain()` (tests + shutdown: process the queue and await running pipeline tasks).
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


async def test_a_restart_resumes_an_interview_left_open_by_a_crash(tmp_path):
    cfg = Config(data_dir=tmp_path / "state", interview_timeout_s=900)
    calls = []

    def processor(store_, cfg_, llm_, embedder_, log_, person_id, started_at, stopped_at):
        calls.append((person_id, started_at, stopped_at))
        return ProcessResult(person_id, "done", [], "")

    # Session 1: open an interview, then "crash" (no close_person call).
    store1 = Store.open(cfg.db_path)
    core1 = Core(
        cfg=cfg,
        store=store1,
        bus=EventBus(),
        transcript_log=TranscriptLog(cfg.transcript_log_path),
        llm=object(),
        embedder=HashEmbedder(dim=16),
        processor=processor,
    )
    core1.on_photo(photo_path="a.jpg", portrait_path="a.png", at=100.0)
    await core1.drain()
    store1.close()

    # Session 2: a fresh process against the same database must resume the
    # still-open interview, not lose track of it and open a second one.
    store2 = Store.open(cfg.db_path)
    core2 = Core(
        cfg=cfg,
        store=store2,
        bus=EventBus(),
        transcript_log=TranscriptLog(cfg.transcript_log_path),
        llm=object(),
        embedder=HashEmbedder(dim=16),
        processor=processor,
    )
    core2.on_photo(photo_path="b.jpg", portrait_path="b.png", at=500.0)
    await core2.drain()

    persons = {p.id: p for p in core2.store.list_persons()}
    assert persons["p1"].stop_reason == "new_photo"
    assert persons["p1"].stopped_at == 500.0
    assert core2.store.open_person().id == "p2"
    assert calls == [("p1", 100.0, 500.0)]
    store2.close()
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

SETTLE_TIMEOUT_S = 3.0
SETTLE_POLL_S = 0.1


async def settle_cut_end(
    transcript_log,
    stopped_at: float,
    timeout: float = SETTLE_TIMEOUT_S,
    poll_interval: float = SETTLE_POLL_S,
) -> float:
    """Wait briefly for an in-flight final on the Telegram-text stop path.

    This exists ONLY for the Telegram-text race: a human keypress can land
    while the visitor's last sentence is still inside ElevenLabs' server VAD,
    so its final publishes slightly after the stop marker. The spoken and
    timeout paths deliberately never call this — a spoken stop arrives as a
    final itself (finals are ordered, so nothing earlier can still be in
    flight), and after a 15-minute timeout nothing is in flight either.
    """
    deadline = time.monotonic() + timeout
    while True:
        finals = [
            e
            for e in transcript_log.read_range(stopped_at, float("inf"))
            if e.timestamp > stopped_at
        ]
        if finals:
            return max(e.timestamp for e in finals)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return stopped_at
        await asyncio.sleep(min(poll_interval, remaining))


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
        settle_timeout_s: float = SETTLE_TIMEOUT_S,
        settle_poll_s: float = SETTLE_POLL_S,
    ) -> None:
        self.cfg = cfg
        self.store = store
        self.bus = bus
        self.transcript_log = transcript_log
        self.llm = llm
        self.embedder = embedder
        self.processor = processor
        # Code-level knobs and test seams, deliberately NOT config-file keys.
        self.settle_timeout_s = settle_timeout_s
        self.settle_poll_s = settle_poll_s
        # A crash can leave a person "open" in the store with nothing in
        # memory to say so. Resuming from the store here, instead of always
        # starting empty, is what keeps a restart a resume rather than a
        # reset (spec: state must be reconstructible from SQLite) and keeps
        # the one-interview-at-a-time guarantee across a restart.
        open_person = store.open_person()
        self.tracker = SessionTracker(
            cfg.interview_timeout_s,
            cfg.stop_phrases,
            open_since=open_person.started_at if open_person else None,
        )
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
        task = asyncio.create_task(
            self._process(person.id, person.started_at, transition.at, transition.reason)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _process(
        self, person_id: str, started_at: float, stopped_at: float, reason: str
    ) -> None:
        cut_end = stopped_at
        if reason == "text":
            # Only a Telegram text stop races an in-flight utterance still
            # inside ElevenLabs' server VAD; the spoken and timeout paths have
            # nothing in flight, so they skip the wait entirely.
            cut_end = await settle_cut_end(
                self.transcript_log, stopped_at, self.settle_timeout_s, self.settle_poll_s
            )
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
                cut_end=cut_end,
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
Expected: PASS (10 tests)

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
- Create: `sim/__init__.py`, `sim/seed_graph.py`, `sim/prerender.py`
- Test: `tests/test_seed_graph.py`, `tests/test_prerender.py`

**REPRIORITISED AND DECOUPLED — decision by Birk, 2026-08-14 (binding).** Task 20 runs BEFORE Tasks
18 and 19, and must NOT depend on the simulation. The graph state is seeded directly through the
Store: ~50 person nodes plus terms, realistic long German term labels, a realistic edge
distribution, portraits substituted by placeholder images. Rationale: the point of the series is
legibility, stroke weight and black level on a whiteboard, which needs realistic **density** and
**label lengths** — not real LLM extraction. Spec §10.4 amended to match.

**Interfaces:**
- Consumes: `kg.server.create_app` (Task 12), the themes (Task 14, 16), `kg.store.Store` and `kg.photos.make_portrait` (Tasks 2, 6). NOT the simulation.
- Produces:
  - `sim.seed_graph.TERM_LABELS` — 100 realistic long German labels; list order IS the Zipf popularity ranking.
  - `sim.seed_graph.seed_graph(data_dir, persons=50, seed=20260814) -> Path` — deterministic; returns `Config(data_dir).db_path`.
  - `sim.seed_graph.PersonSpec` / `person_specs(persons, seed) -> list[PersonSpec]` / `write_person(store, cfg, spec)` — the seeded plan split from the writing (fifth review). `person_specs` walks the rng exactly as `seed_graph` does, one throwaway draw plus a term draw per person, so the entry for person N is the same whether 31 or 50 were planned. This is what lets `seq-new-person` drop the (N+1)th interview into a graph that is already settled and on screen.
  - `sim.prerender.serve(store, cfg, bus=None) -> (base_url, shutdown, publish)` — starts the real app on an ephemeral port in a background thread. `publish` hands an SSE event to the server's OWN event loop (`call_soon_threadsafe`); the bus's `asyncio.Queue`s belong to that loop and must not be poked from the renderer's thread.
  - `sim.prerender.Served` — frozen dataclass `(base_url, store, cfg, publish)`, what `_served` yields.
  - `sim.prerender.Sequence` — frozen dataclass `(directory, description, frames, fps, glide_ms, tail_ms, compute_s, mp4, coverage)`; `duration_s` is `frames / fps`.
  - `sim.prerender.render_sequences(dbs, out_dir, theme="b", names=SEQUENCES, fps=25, ffmpeg=None, encode=True, glide_ms=2500, tail_ms=500, seed=20260814, new_person_base=30) -> list[Sequence]` — films each transition into `out_dir/seq-<name>/` as `frame-0001.png` …, writes `motion.json` beside them (per frame: elapsed time, zoom, pan and every node position — the artefact the determinism claim is made on, since the PNGs are not byte-reproducible) and encodes the whole thing.
  - `sim.prerender.find_ffmpeg(explicit=None) -> Path | None` and `encode_sequence(sequence, ffmpeg) -> Path` — H.264 / yuv420p / `+faststart`, so the file plays inline rather than only in VLC. Frames are the deliverable when no encoder is found.
  - `sim.prerender.Shot` — frozen dataclass `(path, description, coverage)`; `coverage` is a measurement dict (fraction of the canvas the node cloud covers, zoom, fraction of nodes in frame, etc.).
  - `sim.prerender.seed_sizes(state_dir, sizes, seed, reseed=False) -> dict[int, Path]` — one seeded db per person count, all from one seed, so the smaller ones are strict prefixes of the largest (`seed_graph` walks its rng once per person). Read-only masters.
  - `sim.prerender.render_series(dbs, out_dir, theme="b", themes=(), include_fill_series=True, include_density_series=True, include_migration_series=True, include_testpattern=False, include_camera_views=False, camera_theme="b", min_mentions_values=(1, 2, 3), migration_ms=8000) -> list[Shot]` — a pure renderer over seeded dbs. Every series is served a **throwaway copy** of its db, because the renderer persists the placement it settles on back into the db it reads and the next load restores it (spec §10.5) — without the copy, whichever series ran first would silently pin every series after it.
  - CLI: `uv run python -m sim.prerender --state out/prerender6-state --out out/prerender6 --sizes 5 20 50 --seed 20260814 [--reseed] [--sequences dial-1-to-2 dial-2-to-1 new-person | --no-sequences] [--fps 25] [--glide-ms 2500] [--ffmpeg PATH | --no-mp4] [--stills [--themes {a,b,c}] [--migration-ms 8000] [--no-migration-stills] [--camera-views] [--testpattern]]`.
    Sequences run by default (fifth round); `--stills` adds the fourth round's PNG series, and `--no-migration-stills` drops the four-frame slowed migration series out of it — the frame sequences replaced it as the evidence for motion, so a stills-only round (the sixth) does not render it. Output: `seq-{dial-1-to-2,dial-2-to-1,new-person}/frame-<0001..>.png` plus a sibling `.mp4` each, and under `--stills` `theme-b-fill-{05,20,50}-persons-<n>-terms.png`, `theme-b-min-mentions-{1,2,3}-<n>-terms.png`, `theme-b-migration-dial-1-to-2-frame-<i>-of-4-t<seconds>s.png`, and behind the flags `series-{a,b,c}-*.png`, `camera-{1,2,3}-*.png`, `series-d-testpattern-greyscale-and-font-ladder.png`.
    `--sizes` is the fill series' person counts; the 30-person db `seq-new-person` joins is seeded alongside them automatically.

The PNGs are shot at exactly 1920×1080 **with the same renderer that later runs live** (spec §10.4). Variants: **A** dark reference, **B** larger type, **C** much larger type and heaviest strokes — all three share one dark palette and background, differing only in size and stroke weight — **D** the test pattern.

**Second pre-render review — decision by Birk, 2026-08-14 (binding).** White on black stays:
the inverted, light-ground variant (the old B) is rejected outright and dropped from the
series; its slot became a legibility variant instead, so A/B/C now differ only in type size
and stroke/outline weight over one shared dark palette (see the theme files, Task 14). Two
more findings from the same review: the settled placement is now framed to the 16:9 canvas
(`frameToAspect()` in `projection.js` — a from-scratch layout only, never an already-placed
net, per spec §11) — at 50 persons / 125 nodes the node cloud went from 30% of the canvas
width to about 89%; and the camera (Task 14) gained `setZoomFactor()` and `focus()`, since
fit-all at 50 persons is settled as illegible. `sim/prerender.py` now also shoots a camera
series over the identical graph and reports a `coverage` measurement per shot. Every graph
variant still shares one placement — the renderer persists settled positions and the next
variant loads them; laid out separately, a bigger label size would spread the net out and
the camera's fit would zoom back out by the same factor, so the labels would reach the wall
at the same size and the series would compare nothing. Spec §10.4 amended to match.

**Third pre-render review — decision by Birk, 2026-08-14 (binding).** Theme B (32px labels) is
his settled choice and becomes the default theme rendered; A and C stay regenerable behind
`--themes`, because only a real projector on site can make the final call. Three findings:

1. The multicoloured placeholder discs are misleading — the colours mean nothing — and they
   fight the term text. All placeholders are now one muted colour and noticeably smaller,
   with the golden ring kept at full weight: the ring, not the fill, is the concept's carrier
   (Task 14's themes and `sim/seed_graph.py`).
2. The label pile-up gets three structural fixes, carried by Task 14 and described there.
3. The `min_mentions` dial gets its own series — the SAME graph at 1, 2 and 3 — because it may
   already solve much of the crowding and Birk has never seen it. It goes through the real
   display-filter path (Task 13's `visibleGraph`, driven here through
   `window.kgView.setMinMentions`), never a second, special-case renderer.

No separate theme-B full-graph shot is rendered: `min_mentions=1` hides nothing, so that shot
IS the theme-B picture, and delivering the identical picture twice under two filenames would
read as two findings. One extra shot repeats it with the declutter pass switched off, so the
improvement can be seen and not only read as a pair count.

Measured on the seeded graph at theme b, overlapping label pairs / labels sitting on portrait
discs: 43 / 30 from cose alone, 24 / 14 after the placement pipeline, 18 / 4 after the
declutter pass. Raising the dial takes the same picture to 16 / 13 -> 12 / 3 at
`min_mentions=2` (50 terms) and 9 / 12 -> 8 / 2 at 3 (31 terms). Spec §10.4 amended to match.

**Fourth pre-render review — spec change by Birk, 2026-08-14 (binding).** Spec §11's "existing
nodes stay put" is replaced by "the whole net migrates, slowly and never by re-rolling", and
node/font size must follow the fit so the graph always fills the wall (Task 14 carries the
implementation and the measurements). Three series answer it, all at theme B:

1. **Fill the screen** — the same seeded graph at 5 / 20 / 50 persons. Type on the wall 26 /
   16 / 13px, discs 63 / 38 / 30px, canvas fill 89% × 89% and zero overlaps at all three:
   the evidence for "always readable, never overcrowded".
2. **The density dial** at `min_mentions` 1 / 2 / 3 again, but now each step re-lays the net
   out. Up to the third round every step shared one placement and the picture shrank as terms
   were hidden (93% → 80% → 73% of the canvas width, 6 / 1 / 0 overlapping pairs); now the
   survivors migrate into the freed space — 89% at every step, 0 pairs at every step, and the
   type grows 13 → 14 → 18px as the dial rises.
3. **The migration itself** — one transition (the dial going 1 → 2) shot as a numbered
   sequence of frames through the animation, because a PNG cannot show motion. Each frame's
   real elapsed time is measured and goes into its filename, and the glide is slowed to 8s for
   this series only (at the wall's own 2.5s a screenshot round trip eats a fifth of it).

Two structural changes here: `render_series` now takes a **dict of seeded dbs** rather than
one path, and it serves each series a throwaway **copy** of its db. Both exist for the same
reason — a series must be reproducible from the seed alone. The declutter-off comparison shot
of the third round is dropped: the pass's before/after counts are already reported per shot.

**Fifth pre-render review — decision by Birk, 2026-08-15 (binding).** Two things.

**(a) Colour correction, applied before anything was rendered.** The ground is now pure
`#000000` and the label text pure `#FFFFFF`, in ALL THREE graph themes — it was `#101014`
under `#F5F1E6`, a blue-tinted near-black under a cream near-white. Projection is additive
and the surface is a whiteboard, so on-site black is whatever ambient light sits on it
(spec §10.4): a tint gains nothing there and costs contrast. White-on-black goes 16.8:1 →
21:1. `--label-outline-color` follows `--bg` exactly (a near-black outline over a pure
black ground shows as a halo); `--term-dot-color` went to pure white with the labels;
`--edge-color` was restated as the NEUTRAL grey of the same relative luminance
(`#8A8578` → `#858585`, L = 0.235 either way) so edges stay exactly as subordinate as they
were tuned to be; `--person-fill` likewise (`#23232a` → `#242424`). **`--ring-color` stays
gold** — the concept's signature, the one non-greyscale element. `sim/seed_graph.py`'s
placeholder portrait followed (`#3A3A42` → `#3B3B3B`, same luminance): it is a stand-in for
a photograph rather than a theme token, but on a pure black ground it would have been the
only tinted thing on the wall. Theme D follows theme A's ground as always, so the test
pattern's page and its wedge's own 0% step are now the same value.
`tests/test_projection.py` pins all of it through Cytoscape's baked style. Spec §10.4
amended to match.

**(b) Frame sequences, because four stills cannot show a glide.** The fourth round
delivered the migration as four PNGs, which played back look exactly like the jumping the
rule exists to disprove. `sim/prerender.py` now also renders **25 fps sequences over the
wall's own 2500ms glide** plus a 0.5s settled tail — 76 frames, 3.04s — into
`out/prerender5/seq-<name>/`, each encoded to H.264 / yuv420p. Three of them: `dial-1-to-2`
(25 terms vanish), `dial-2-to-1` (the harder direction, the one that used to re-shuffle)
and `new-person` (one interview joining a settled 30-person net, over SSE, exactly as the
Core pushes it).

The capture is the part that needed designing. A 1920×1080 screenshot costs a fifth of a
2.5s glide, so sampling a freely running animation would bunch the frames at one end and
would repeat neither between runs nor between machines — and determinism is a requirement
of this series. So `_FRAME_CLOCK` replaces `window.requestAnimationFrame` and
`performance.now()` AFTER the page has loaded and settled, and the driver advances them by
exactly 40ms per frame. The renderer is not patched and does not know: Cytoscape resolves
both dynamically off `window`/`performance` at call time (verified against the vendored
bundle).

**Determinism is of the MODEL, not of the pixels, and that had to be established rather than
assumed.** Two cold runs of the 50-person graph agree exactly on node positions, label
offsets, measured label boxes and zoom — and still produce PNGs differing in ~0.5% of
pixels, always confined to a handful of captions. Chased down: Cytoscape rasterises a label
into its texture cache at a sub-pixel phase that depends on how that cache was packed
(cropped and compared, the two renderings of the same caption sit within 0.2px of each
other's ink centroid — invisible). A seeded `Math.random` was tried first, on the theory
that `cose-base.js` breaks ties for pruned degree-1 nodes with it; the placement turned out
to be identical with and without, so that machinery was deleted rather than kept on a
justification it had not earned. What ships instead is `motion.json` next to each sequence —
elapsed time, zoom, pan and every node position, per frame — so the claim is checkable on
the delivered files rather than only by re-rendering, and `tests/test_prerender.py` compares
that instead of PNG bytes.

Two rejected alternatives for the clock, both measured: CDP `Emulation.setVirtualTimePolicy`
freezes `performance.now()` perfectly but suppresses rAF, so the canvas stops being redrawn
(3 distinct frames out of 20) and both `Page.captureScreenshot` and `page.screenshot()`
hang while it is paused; time-dilated real-time capture is geometrically exact but samples
within ~1ms of the target and so does not repeat byte for byte.

Measured on the delivered sequences (from their `motion.json`): every frame lands on the
40ms grid exactly (t = 0 … 3000ms), all 63 glide frames are different pictures, the
arrangement is reached exactly at the end (frames 64-76 identical), and no single frame
carries more than **4.4%** of the transition's total travel in any of the three — a cut
would put 100% in one frame. The landing is not a snap either: the last step (the animation
ending plus `declutterLabels()` running after it) changes FEWER pixels than the
second-to-last step of the glide.

**Found, and carried to spec §14 rather than tuned here:** the glide is preceded by a
freeze. fcose at `quality: "proof"` plus `settlePlacement()` compute the new arrangement
before anything moves, and on the development machine that was 2.3s (dial 1 → 2), 3.3s (new
person) and 6.6s (dial 2 → 1, 125 nodes) — real CPU time, and it moves with load (an earlier
run under a parallel job: 2.6 / 3.4 / 9.9s). `Sequence.compute_s` reports it per sequence so
it cannot be lost again.

The Step 1–4 listings below predate the fourth and fifth rounds for `sim/prerender.py` and
`tests/test_prerender.py`; the shipped files are authoritative for those two.

The db must sit at `<data_dir>/kg.db`: `render_series` derives `Config(data_dir=db_path.parent)` and the app mounts `cfg.portrait_dir` from it, so a db elsewhere silently breaks the portraits. The `wait_for_function` timeouts are 60000 ms, not the 20000 ms a toy graph needed. `sim/prerender.py` reuses `tests/conftest.py`'s cached-chromium `executable_path` fallback — this host cannot `playwright install`.

- [ ] **Step 1: Write the failing test**

`tests/test_prerender.py`:

```python
"""sim.prerender shoots the live renderer headless (Task 20 brief).

Adapted from the plan's Task 20 Step 1, but fed by sim.seed_graph through the
Store instead of fixture edges (Birk's 2026-08-14 decision: no simulation
dependency), and against a small seeded db so the test stays fast.
"""

from __future__ import annotations

import pytest
from PIL import Image

from sim.prerender import render_series
from sim.seed_graph import seed_graph

PERSONS = 6
SEED = 20260814


@pytest.fixture(scope="module")
def seeded_db(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("prerender-state")
    return seed_graph(data_dir, persons=PERSONS, seed=SEED)


def _placement_by_id(coverage):
    # coverage["placement"] is a list of [id, x, y] triples from MEASURE,
    # arriving from Playwright as JSON (lists, not tuples) — reshape once here
    # instead of repeating the conversion in every test.
    return {row[0]: (row[1], row[2]) for row in coverage["placement"]}


def test_the_series_renders_one_png_per_variant_at_1920x1080(tmp_path, seeded_db):
    out_dir = tmp_path / "prerender"

    shots = render_series(seeded_db, out_dir)

    # Third iteration's default: the density dial's four shots on theme B
    # (Birk's settled choice) and nothing else. No separate theme-B shot —
    # min_mentions=1 hides nothing, so that IS the full-graph theme-B
    # picture; a/c, the camera series and the test pattern are all opt-in
    # this round (see CLI flags).
    names = [s.path.name for s in shots]
    assert names[0].startswith("theme-b-min-mentions-1-all-") and names[0].endswith("-terms.png")
    assert names[1].startswith("theme-b-min-mentions-2-") and names[1].endswith("-terms.png")
    assert names[2].startswith("theme-b-min-mentions-3-") and names[2].endswith("-terms.png")
    assert names[3] == "theme-b-min-mentions-1-labels-BEFORE-declutter.png"
    assert len(names) == 4
    for shot in shots:
        with Image.open(shot.path) as img:
            assert img.size == (1920, 1080)


def test_the_variants_differ_from_each_other(tmp_path, seeded_db):
    out_dir = tmp_path / "prerender"

    shots = render_series(
        seeded_db,
        out_dir,
        themes=("a", "b"),
        include_testpattern=False,
        include_camera_views=False,
        include_density_series=False,
    )

    assert shots[0].path.read_bytes() != shots[1].path.read_bytes()


def test_every_graph_variant_shares_one_placement(tmp_path, seeded_db):
    # The variants differ in type size. If each got its own layout, the bigger
    # type would spread the net out and the camera's fit would zoom back out
    # by the same factor — the labels would reach the wall at the same size
    # and the series would compare nothing.
    shots = render_series(
        seeded_db,
        tmp_path / "prerender",
        themes=("a", "b", "c"),
        include_testpattern=False,
        include_camera_views=False,
        include_density_series=False,
    )

    placements = {tuple(tuple(row) for row in shot.coverage["placement"]) for shot in shots}
    assert len(placements) == 1


def test_the_placement_fills_the_16_9_canvas(tmp_path, seeded_db):
    # The measurement Birk asked for: before the layout was framed to the
    # canvas, the node cloud covered 30% of the width (2026-08-14 baseline).
    shots = render_series(
        seeded_db,
        tmp_path / "prerender",
        themes=("a",),
        include_testpattern=False,
        include_camera_views=False,
        include_density_series=False,
    )

    assert shots[0].coverage["width_fraction_with_labels"] > 0.8


def test_the_camera_views_frame_progressively_less_of_the_net(tmp_path, seeded_db):
    shots = render_series(
        seeded_db,
        tmp_path / "prerender",
        themes=(),
        include_testpattern=False,
        include_camera_views=True,
        include_density_series=False,
    )

    assert [s.path.name for s in shots] == [
        "camera-1-fit-all-reference.png",
        "camera-2-zoom2x-half-the-net.png",
        "camera-3-cluster-closeup.png",
    ]
    zooms = [s.coverage["zoom"] for s in shots]
    assert zooms[0] < zooms[1] < zooms[2]
    # Fit-all is the only view that holds the whole net; both zoomed views
    # trade coverage for size. Which of the two holds more depends on how
    # dense the chosen cluster is, so only the fit-all baseline is ordered.
    in_frame = [s.coverage["nodes_in_frame"] for s in shots]
    assert in_frame[0] == 1.0
    assert in_frame[1] < 1.0 and in_frame[2] < 1.0


def test_the_density_dial_shows_the_same_graph_at_three_thresholds(tmp_path, seeded_db):
    # Item 3 of the third brief: the SAME graph at min_mentions 1/2/3,
    # through the real display-filter path (window.kgView.setMinMentions ->
    # render() -> graph-model.js visibleGraph), never a second renderer.
    shots = render_series(
        seeded_db,
        tmp_path / "prerender",
        themes=(),
        include_testpattern=False,
        include_camera_views=False,
        include_density_series=True,
        min_mentions_values=(1, 2, 3),
    )

    dial_shots = shots[:3]
    for shot in dial_shots:
        with Image.open(shot.path) as img:
            assert img.size == (1920, 1080)

    terms = [s.coverage["term_nodes"] for s in dial_shots]
    edges = [s.coverage["edges"] for s in dial_shots]
    persons = [s.coverage["person_nodes"] for s in dial_shots]
    assert terms[0] > terms[1] > terms[2]
    assert edges[0] > edges[1] > edges[2]
    assert persons[0] == persons[1] == persons[2] == PERSONS


def test_the_density_shots_share_one_placement(tmp_path, seeded_db):
    # Raising the dial only hides term nodes — it must never re-run the
    # layout. min_mentions=3 shows the fewest nodes, so its ids are a subset
    # of the other two; every id it has must sit at the identical position.
    shots = render_series(
        seeded_db,
        tmp_path / "prerender",
        themes=(),
        include_testpattern=False,
        include_camera_views=False,
        include_density_series=True,
        min_mentions_values=(1, 2, 3),
    )

    by_id = [_placement_by_id(s.coverage) for s in shots[:3]]
    shared_ids = set(by_id[2])
    assert shared_ids  # the graph must not be filtered down to nothing
    assert shared_ids <= set(by_id[0])
    assert shared_ids <= set(by_id[1])
    for node_id in shared_ids:
        assert by_id[0][node_id] == by_id[1][node_id] == by_id[2][node_id]


def test_the_declutter_off_shot_is_the_same_picture_and_never_the_better_one(
    tmp_path, seeded_db
):
    # Birk has only seen the label-overlap count, never the picture: this
    # comparison shot puts the pass's own effect on the exact graph the
    # min_mentions=1 dial shot above it also shows.
    #
    # What is asserted here is the direction, not a margin. This module's
    # seeded db is deliberately small (PERSONS = 6) so the suite stays fast,
    # and at that size the placement pass alone already clears every overlap
    # — so both shots read zero and there is nothing left for the declutter
    # pass to improve. The margin at the density that actually matters (50
    # persons / 75 distinct long labels: 24 pairs down to 18, 14 labels on
    # portrait discs down to 4) belongs to the front end and is measured in
    # tests/test_projection.py against exactly that net.
    shots = render_series(
        seeded_db,
        tmp_path / "prerender",
        themes=(),
        include_testpattern=False,
        include_camera_views=False,
        include_density_series=True,
        min_mentions_values=(1,),
    )

    after_shot, before_shot = shots[0], shots[1]
    assert before_shot.path.name == "theme-b-min-mentions-1-labels-BEFORE-declutter.png"
    assert (
        before_shot.coverage["label_overlaps"]["labelPairs"]
        >= after_shot.coverage["label_overlaps"]["labelPairs"]
    )
    assert (
        before_shot.coverage["label_overlaps"]["labelsOnPersons"]
        >= after_shot.coverage["label_overlaps"]["labelsOnPersons"]
    )
    # Same graph, same placement — the ids present are identical, and every
    # id's position matches, so the two shots really are the same picture.
    before_ids = _placement_by_id(before_shot.coverage)
    after_ids = _placement_by_id(after_shot.coverage)
    assert before_ids == after_ids
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_prerender.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sim.prerender'`

- [ ] **Step 3: Implement `sim/prerender.py`**

```python
"""Headless 1920x1080 PNGs with the renderer that later runs live (spec 10.4).

Adapted from the plan's Task 20 Step 3. Per Birk's 2026-08-14 decision (see
the Task 20 brief), this no longer depends on a simulation database (Tasks
18/19 don't exist yet): the CLI seeds the db directly through
`sim.seed_graph.seed_graph` if it doesn't already exist. `render_series`
itself stays a pure renderer over an existing db — it does not know or care
how that db was populated.

Second iteration (Birk's 2026-08-14 pre-render review, binding):
- the inverted light-ground variant is dropped; all three graph variants are
  white on black and differ in type size and stroke weight only,
- the placement fills the 16:9 canvas (see `frameToAspect` in projection.js),
  and every shot reports how much of the canvas the node cloud covers,
- a camera series shows what zoomed operation looks like over the SAME graph,
  since fit-all at 50 persons is settled as illegible.

Third iteration (Birk's 2026-08-14 review of series 2, item 3 of that brief):
- theme B (32px labels) is Birk's settled choice and is now the default
  graph theme rendered; A and C stay regenerable behind `--themes` for the
  final call, which only a real projector on site can make,
- the minimum-mentions dial (Task 13's display filter — graph-model.js
  `visibleGraph`, driven here through `window.kgView.setMinMentions`, never
  a second filtering renderer) gets its own series: the SAME placement shot
  at min_mentions 1/2/3, so the dial's own effect on crowding is visible
  before any layout fix is judged,
- and because that dial's first step (min_mentions=1) hides nothing, it IS
  the theme-B full-graph shot — so the type-ladder series renders nothing by
  default. Delivering the identical picture twice under two filenames would
  read as two findings; `--themes a c` regenerates the other two rungs.
- one more shot repeats the min_mentions=1 picture with the label-declutter
  pass switched off, so that improvement is seen against the identical
  graph, not only reported as a pair count,
- the camera series and the test pattern stay regenerable but are off by
  default this round — the question this round is the dial, not the camera.
"""

from __future__ import annotations

import argparse
import shutil
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import uvicorn

from kg.bus import EventBus
from kg.config import Config
from kg.server import create_app
from kg.store import Store


@dataclass(frozen=True)
class Shot:
    """One delivered PNG: where it is, what it shows, and what it measures."""

    path: Path
    description: str
    coverage: dict = field(default_factory=dict)


# The legibility ladder. Same graph, same positions, same palette — only type
# size and stroke weight change, which is the whole question this series asks.
SERIES = {
    "a": (
        "series-a-dark-base-label22",
        "A (reference): white on black, 22px labels, 5px rings, 2px edges — the concept rendering's weights.",
    ),
    "b": (
        "series-b-dark-larger-label32",
        "B: 32px labels (1.45x A), 7px rings, 20px term dots, 3px edges, 4px text outline — same ground, same palette.",
    ),
    "c": (
        "series-c-dark-largest-label44",
        "C: 44px labels (2x A), 10px rings, 28px term dots, 5px edges, 6px text outline — the upper end of the ladder.",
    ),
}

TESTPATTERN = (
    "series-d-testpattern-greyscale-and-font-ladder",
    "D: test pattern — greyscale wedge and font-size ladder, for the whiteboard's real black level on site.",
)

# Camera views over the identical graph. They call the live Camera component
# (window.kgView.camera), never cy.zoom/cy.pan directly: what is shot here is
# what the wall would actually do.
CAMERA_VIEWS = [
    (
        "camera-1-fit-all-reference",
        "Camera 1: fit mode, the whole net in frame — the reference, and the view that is settled as illegible at 50 persons.",
        "() => { const c = window.kgView.camera; c.setZoomFactor(1); c.setMode('fit'); }",
    ),
    (
        "camera-2-zoom2x-half-the-net",
        "Camera 2: fit mode at zoom factor 2 — half the net's width across the wall, centred.",
        "() => { const c = window.kgView.camera; c.setMode('fit'); c.setZoomFactor(2); }",
    ),
    (
        "camera-3-cluster-closeup",
        "Camera 3: the camera on the tightest person-and-terms cluster in the net, plus whoever else falls in that frame — the view an automatic traversal dwells on.",
        # Deterministic pick: smallest cluster box by area, ties by person id.
        """() => {
             const cy = window.kgView.cy;
             let best = null;
             cy.nodes('.person').forEach((person) => {
               const cluster = person.union(person.neighborhood('node.term'));
               const box = cluster.boundingBox({ includeLabels: true });
               const area = box.w * box.h;
               if (!best || area < best.area || (area === best.area && person.id() < best.id)) {
                 best = { area, id: person.id(), cluster };
               }
             });
             window.kgView.camera.focus(best.cluster);
           }""",
    ),
]

# What the layout fix is judged by: the rendered box of all nodes as a
# fraction of the 1920x1080 canvas, plus how much of the net is in frame.
MEASURE = """
() => {
  const cy = window.kgView.cy;
  const nodes = cy.nodes();
  const bare = nodes.renderedBoundingBox({ includeLabels: false });
  const withLabels = nodes.renderedBoundingBox({ includeLabels: true });
  const extent = cy.extent();
  // Keyed by node id, not summed: the density dial changes which nodes are
  // even present (term nodes below the threshold drop out), so a sum over a
  // shorter node set would drift even when every surviving node sits exactly
  // where it did. Sorted by id so two evaluations are comparable regardless
  // of cy's own iteration order.
  const placement = nodes
    .map((n) => [n.id(), Math.round(n.position('x') * 1000) / 1000, Math.round(n.position('y') * 1000) / 1000])
    .sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
  const inFrame = nodes.filter((n) => {
    const p = n.position();
    return p.x >= extent.x1 && p.x <= extent.x2 && p.y >= extent.y1 && p.y <= extent.y2;
  }).length;
  return {
    nodes: nodes.length,
    // What is actually on the wall at this shot — the density dial's whole
    // point, so it is reported per shot, not just derived from a filename.
    term_nodes: cy.nodes('.term').length,
    person_nodes: cy.nodes('.person').length,
    edges: cy.edges('.link').length,
    zoom: cy.zoom(),
    // Fingerprint of the placement, so a shared one can be asserted.
    placement,
    width_fraction: bare.w / cy.width(),
    height_fraction: bare.h / cy.height(),
    width_fraction_with_labels: withLabels.w / cy.width(),
    height_fraction_with_labels: withLabels.h / cy.height(),
    nodes_in_frame: inFrame / nodes.length,
    // The front end's own overlap count, not a second one computed here —
    // this file renders, it does not re-implement label-collision judgement.
    label_overlaps: window.kgView.labelOverlaps(),
    label_overlap_stats: window.kgView.labelOverlapStats,
  };
}
"""

# Positions are persisted by the renderer itself (POST /api/positions) and the
# next variant loads them, so every variant shares one placement — without
# that, a bigger label size would spread the layout out and the camera's fit
# would zoom back out by the same factor, leaving the type visually identical
# and the whole comparison meaningless.
POSITIONS_PERSISTED = """
async () => {
  const graph = await (await fetch('/graph.json')).json();
  return graph.nodes.every((n) => n.x !== null && n.x !== undefined);
}
"""

# Portraits are background-images: Cytoscape paints the ring first and fills
# it in whenever each file arrives. Without waiting for them a cold-cache run
# shoots half-drawn person nodes — which is exactly what a first run is.
PORTRAITS_LOADED = """
() =>
  Promise.all(
    window.kgView.cy
      .nodes('.person')
      .map((node) => node.data('portrait'))
      .filter(Boolean)
      .map(
        (url) =>
          new Promise((resolve) => {
            const image = new Image();
            image.onload = resolve;
            image.onerror = resolve;
            image.src = url;
          }),
      ),
  ).then(() => {
    // Cytoscape redraws by itself as each image lands, but say so explicitly
    // — and return a plain value, never the cy instance: serialising that
    // back to the driver crashes the page.
    window.kgView.cy.forceRender();
    return true;
  })
"""


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


def _launch_chromium(playwright):
    # This Debian 11 host cannot `playwright install` the pinned chromium
    # revision (no network access, OS predates what it needs), but a
    # compatible build is already cached. Same fallback as tests/conftest.py
    # — reused here, not reinvented, or this breaks on this exact machine.
    try:
        return playwright.chromium.launch()
    except Exception:
        candidates = sorted(Path.home().glob(".cache/ms-playwright/chromium-*/chrome-linux64/chrome"))
        if not candidates:
            raise
        return playwright.chromium.launch(executable_path=str(candidates[-1]))


def _open_projection(page, base_url: str, theme: str) -> None:
    page.goto(f"{base_url}/projection?theme={theme}")
    # The 50-person / ~75-term graph and its animated cose layout take real
    # wall-clock time — 60s (not the toy-graph 20s the plan used) is the
    # budget, not a guess to shrink.
    page.wait_for_function("window.kgReady === true", timeout=60000)
    # Wait for the real signal, not a guessed duration: the cose layout is
    # animated and nodes are still moving until layoutstop.
    page.wait_for_function(
        "() => window.kgView && window.kgView.layoutPending === false",
        timeout=60000,
    )
    # The renderer POSTs the settled positions back; the next page load must
    # read them, not lay the net out a second time.
    page.wait_for_function(POSITIONS_PERSISTED, timeout=60000)
    page.evaluate(PORTRAITS_LOADED)
    page.wait_for_timeout(500)  # let the final frame paint


# The dial's own series (Task 3 of the third brief). Same graph, same
# placement, only the threshold moves — through the real display-filter path
# (window.kgView.setMinMentions -> render() -> graph-model.js visibleGraph),
# never a second, special-case renderer that filters the graph data itself.
DENSITY_MIN_MENTIONS = (1, 2, 3)
DENSITY_THEME = "b"  # Birk's settled choice this round (see module docstring)


def _density_shots(page, base_url: str, out_dir: Path, theme: str, min_mentions_values) -> list[Shot]:
    shots: list[Shot] = []
    _open_projection(page, base_url, theme)
    first = min_mentions_values[0]
    for value in min_mentions_values:
        page.evaluate(f"() => window.kgView.setMinMentions({value})")
        # No new nodes arrive when the dial only hides existing ones, so
        # render() never starts a layout — layoutPending stays false and this
        # is purely the declutter pass (over fewer, now-visible labels)
        # settling, not a layout wait.
        page.wait_for_timeout(200)
        data = page.evaluate(MEASURE)
        # The filename carries the REAL remaining count, not the threshold
        # alone — a filename must tell Birk what he is looking at without
        # opening the file.
        qualifier = "all-" if value == first else ""
        stem = f"theme-{theme}-min-mentions-{value}-{qualifier}{data['term_nodes']}-terms"
        description = (
            f"Density dial at min_mentions={value}: {data['term_nodes']} term nodes, "
            f"{data['person_nodes']} persons, {data['edges']} edges on the wall — same "
            "placement as the other two steps, only the dial moved."
        )
        target = out_dir / f"{stem}.png"
        page.screenshot(path=str(target))
        shots.append(Shot(target, description, data))

    # BEFORE/AFTER declutter comparison on the exact picture the min_mentions
    # equal to `first` shot above already is — so the improvement is seen
    # against the identical graph, not only reported as a pair count.
    page.evaluate(f"() => window.kgView.setMinMentions({first})")
    page.wait_for_timeout(200)
    page.evaluate("() => window.kgView.resetLabelOffsets()")
    page.wait_for_timeout(200)
    before_data = page.evaluate(MEASURE)
    before_target = out_dir / f"theme-{theme}-min-mentions-{first}-labels-BEFORE-declutter.png"
    page.screenshot(path=str(before_target))
    page.evaluate("() => window.kgView.declutterLabels()")
    page.wait_for_timeout(200)
    after_overlaps = page.evaluate("() => window.kgView.labelOverlaps()")
    # Override the generic auto-recorded stats: those describe the LAST
    # render's own pass, not this manual reset/redeclutter demonstration.
    before_data["label_overlap_stats"] = {"before": before_data["label_overlaps"], "after": after_overlaps}
    shots.append(
        Shot(
            before_target,
            f"Same picture as min_mentions={first} above, label declutter pass switched OFF: "
            f"{before_data['label_overlaps']['labelPairs']} overlapping label pairs "
            f"(vs {after_overlaps['labelPairs']} once the pass runs).",
            before_data,
        )
    )
    return shots


def render_series(
    db_path: Path,
    out_dir: Path,
    themes: tuple[str, ...] = (),
    include_testpattern: bool = False,
    include_camera_views: bool = False,
    camera_theme: str = "a",
    include_density_series: bool = True,
    density_theme: str = DENSITY_THEME,
    min_mentions_values: tuple[int, ...] = DENSITY_MIN_MENTIONS,
) -> list[Shot]:
    from playwright.sync_api import sync_playwright

    db_path = Path(db_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = Config(data_dir=db_path.parent)
    store = Store.open(db_path)
    base_url, shutdown = serve(store, cfg)
    shots: list[Shot] = []
    try:
        with sync_playwright() as playwright:
            browser = _launch_chromium(playwright)
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            for theme in themes:
                stem, description = SERIES[theme]
                _open_projection(page, base_url, theme)
                target = out_dir / f"{stem}.png"
                page.screenshot(path=str(target))
                shots.append(Shot(target, description, page.evaluate(MEASURE)))
            if include_density_series:
                shots.extend(_density_shots(page, base_url, out_dir, density_theme, min_mentions_values))
            if include_camera_views:
                _open_projection(page, base_url, camera_theme)
                for stem, description, setup in CAMERA_VIEWS:
                    page.evaluate(setup)
                    page.wait_for_timeout(200)
                    target = out_dir / f"{stem}.png"
                    page.screenshot(path=str(target))
                    shots.append(
                        Shot(target, f"{description} [theme {camera_theme}]", page.evaluate(MEASURE))
                    )
            if include_testpattern:
                stem, description = TESTPATTERN
                page.goto(f"{base_url}/testpattern")
                page.wait_for_selector(".wedge")
                target = out_dir / f"{stem}.png"
                page.screenshot(path=str(target))
                shots.append(Shot(target, description))
            browser.close()
    finally:
        shutdown()
        store.close()
    return shots


def main() -> None:
    from sim.seed_graph import seed_graph

    parser = argparse.ArgumentParser(prog="sim.prerender")
    parser.add_argument("--db", default="out/prerender3-state/kg.db")
    parser.add_argument("--out", default="out/prerender3")
    parser.add_argument("--persons", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260814)
    parser.add_argument(
        "--reseed",
        action="store_true",
        help="delete the seeded state first. The renderer persists node positions "
        "into it, so an existing db pins the placement — required after any "
        "change to the layout.",
    )
    parser.add_argument(
        "--themes",
        nargs="+",
        default=[],
        choices=sorted(SERIES),
        help="which type-size variants to render as their own full-graph shot "
        "(default: none — theme b, Birk's settled choice this round, is already "
        "the density series' min_mentions=1 shot; pass a and/or c to regenerate "
        "the other rungs for the on-site projector call)",
    )
    parser.add_argument(
        "--camera-theme",
        default="a",
        choices=sorted(SERIES),
        help="theme for the camera series (default a, so it compares directly with series A)",
    )
    parser.add_argument(
        "--camera-views", action="store_true", help="also render the camera series (off by default this round)"
    )
    parser.add_argument(
        "--testpattern",
        action="store_true",
        help="also render the greyscale/font-ladder test pattern (off by default this round)",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if args.reseed and db_path.parent.exists():
        shutil.rmtree(db_path.parent)
    if not db_path.exists():
        seed_graph(db_path.parent, persons=args.persons, seed=args.seed)

    shots = render_series(
        db_path,
        Path(args.out),
        themes=tuple(args.themes),
        include_testpattern=args.testpattern,
        include_camera_views=args.camera_views,
        camera_theme=args.camera_theme,
    )
    for shot in shots:
        print(shot.path.resolve())
        print(f"    {shot.description}")
        if shot.coverage:
            print(
                "    node cloud: {width_fraction:.0%} of canvas width, "
                "{height_fraction:.0%} of height (with labels "
                "{width_fraction_with_labels:.0%} x {height_fraction_with_labels:.0%}); "
                "zoom {zoom:.3f}; {nodes_in_frame:.0%} of {nodes} nodes in frame".format(
                    **shot.coverage
                )
            )
            if "term_nodes" in shot.coverage:
                print(
                    "    on the wall: {term_nodes} term nodes, {person_nodes} persons, "
                    "{edges} edges".format(**shot.coverage)
                )
            stats = shot.coverage.get("label_overlap_stats")
            if stats:
                before, after = stats["before"], stats["after"]
                print(
                    f"    labels: {before['labelPairs']} overlapping pairs before -> "
                    f"{after['labelPairs']} after the declutter pass; "
                    f"{before['labelsOnPersons']} on person discs before -> "
                    f"{after['labelsOnPersons']} after"
                )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_prerender.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Produce the real comparison series and hand it to Birk**

```bash
uv run python -m sim.prerender --reseed
```

Show `out/prerender3/theme-b-min-mentions-*.png` — the dial at 1, 2 and 3 over one shared
placement, plus the declutter-off comparison — to Birk. `--reseed` is not optional after any
change to the layout: the renderer persists node positions into the db, so an existing db
pins the placement and would hide the change.

Each earlier round's decisions are recorded above: the second review (white on black stays,
the inverted variant rejected, fit-all at 50 persons illegible — the camera carries that with
`setZoomFactor` and `focus`) and the third (theme B is the settled choice, one muted smaller
placeholder disc, the label fixes, and the dial series this step now renders). The camera
series, the test pattern and themes A and C stay one flag away: `--camera-views`,
`--testpattern`, `--themes a c`.

- [ ] **Step 6: Commit**

```bash
git add sim/ tests/test_seed_graph.py tests/test_prerender.py .gitignore
git commit -m "feat: store-seeded pre-render comparison series (A-D) at 1920x1080"
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
