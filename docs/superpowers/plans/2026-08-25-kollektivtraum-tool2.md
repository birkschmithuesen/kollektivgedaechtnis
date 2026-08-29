# Kollektivtraum — Tool 2 Implementation Plan

> ## ⚠️ ERLEDIGT UND TEILWEISE ÜBERHOLT — historisches Bauprotokoll
>
> Alle 18 Tasks sind gebaut und abgenommen (`.superpowers/sdd/progress.md`:
> „TOOL 2 COMPLETE"). Die offenen Checkboxen unten sind **Bauhistorie, keine
> offene Arbeit** — sie wurden beim Abarbeiten nie abgehakt.
>
> **Mehrere Festlegungen in diesem Plan gelten nicht mehr.** Er beschreibt den
> Stand vom 2026-08-25; am 2026-08-28/29 wurden auf Birks Entscheidung hin
> geändert:
>
> | Steht hier noch | Gilt heute |
> |---|---|
> | „`min_mentions` is NOT applied — the dream reads everything" | Gleitende Auswahl: alle geteilten Begriffe + jüngste Einmal-Nennungen |
> | Widerspruchs-Klausel, `contradiction_min_persons = 6` | Ersatzlos gestrichen, dafür Belegbarkeits-Klausel |
> | Satzlänge ~20–40 Wörter | Ein Hauptsatz, max. 16 Wörter, kein Komma |
> | Leitfrage im Stufe-1-Prompt | Nicht mehr im Prompt, steuert nur die Überschrift |
> | Zitate im Materialblock | Entfernt (waren 76 % des Blocks) |
> | Bildprompt = Motiv + Register | Fünf Bausteine, englisch, mit `mood`/`tension` |
> | `default_min_mentions` (Tool 1) | `default_max_terms` |
>
> **Verbindlich sind stattdessen:** `docs/superpowers/specs/2026-08-25-kollektivtraum-design.md`
> (nachgezogen), `docs/operations.md` (kalibrierte Werte) und
> `docs/HANDOFF-2026-08-29.md` (aktueller Stand). Dieses Dokument nur noch
> lesen, um zu verstehen, **warum** etwas ursprünglich so gebaut wurde.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the screen that stands beside the graph wall and, whenever Tool 1 has absorbed a new interview, condenses the whole current graph into one German sentence and one image — keeping every earlier dream of the day visible as a strip beneath.

**Architecture:** A second Python asyncio process (`kg2/`) on its own machine. A watcher polls Tool 1's `GET /graph.json` every 5 s and detects an *absorbed* interview from the data alone — a `type:"person"` node that has at least one edge, never a bare person node (spec §4.1). When one appears and the floor has expired, a two-stage dream cycle runs: graph → German sentence (`claude-opus-5`), sentence → image (`google/gemini-3-pro-image` via OpenRouter). Everything is persisted to its own `dreams.sqlite3` and pushed over its own SSE bus to its own two pages, `/dream` and `/operator`. Tool 2 is read-only against Tool 1 over HTTP and shares no code path that could let a Tool 2 fault reach the wall.

**Tech Stack:** Python 3.12 (via `uv`), SQLite (stdlib `sqlite3`, WAL), FastAPI + uvicorn, httpx, Anthropic SDK (`claude-opus-5`), OpenRouter chat-completions for image generation, plain ES modules (no bundler, no npm at runtime), Playwright (headless pre-render + frontend tests), pytest.

**Source of truth:** `docs/superpowers/specs/2026-08-25-kollektivtraum-design.md` (SPEC, approved). Section references below (§) point into that spec unless prefixed `T1§`, which points into `docs/superpowers/specs/2026-08-12-kollektivgedaechtnis-design.md`. Everything in spec §12 is out of scope and must not be built. The predecessor `2026-08-25-kollektivtraum-brainstorm.md` holds the reasoning; it does not override the spec.

## Global Constraints

- **Read-only against Tool 1** (§2). Tool 2 never writes to Tool 1's SQLite, never POSTs positions, never mutates `graph.json`. `kg2/graph_client.py` is the only module that talks to Tool 1 and it has no write verb at all.
- **Tool 2 may import *pure* helpers from `kg`** (dataclass shapes, the SSE decoder, `kg.llm.LLMClient`, `kg.bus.EventBus`) but **never `kg.store`, `kg.core` or `kg.server`** (§3). Every such import must carry a one-line comment naming §3.
- **Exactly ONE change inside `kg/` in this whole plan** (Task 1): `kg/__main__.py` prints the resolved LAN address instead of `0.0.0.0`. No other file under `kg/` may be touched by any task. Not the renderer, not the pipeline, not the schema (§3.1).
- **Package layout:** `kg2/` beside `kg/`, frontend in `frontend2/`, tests named `tests/test_dream_*.py` (§3).
- **Neither tool is in the other's critical path** (§2). Tool 1 dead → Tool 2 shows its last dream and its history. Tool 2 dead → screen B goes blank, A and C untouched.
- **Trigger is event-driven with a floor, never a timer, nothing during silence** (§4). A dream is due when the set of non-hidden `type:"person"` node ids has grown **and that new person has at least one edge**. A person node with no edges is Tool 1's step 1 and is explicitly ignored until its edges appear.
- **Floor:** `min_interval_s`, default **240 s**, measured since the last dream *started*. Several interviews inside the floor collapse into **one** dream (§4.1).
- **Hidden nodes are excluded from the dream** (§5.1). `min_mentions` is **NOT** applied — that dial is the wall's legibility filter, not a statement about what was said.
- **Contradiction as construction principle** (§5.1): the two most distant positions are held in one image without being resolved. Dropped below `contradiction_min_persons`, default **6**.
- **The visual register is fixed all day** (§5.2), held in config as a style suffix appended to every prompt — never model-chosen, never graph-driven.
- **The sentence shown on screen is stage 1's output, not stage 2's prompt** (§5.2).
- **Images are never overwritten**: `images/<dream_id>.png` (§5.2).
- **Failures ride it out** (§8): a failed stage abandons the dream, marks it `failed`, and **the current image stays up**. Retry at the next trigger, never a retry storm.
- **Discard removes the dream from the large screen AND from the history strip in one step** (§7). The row is kept with `discarded: true`, never deleted.
- **Crash recovery is Tool 1's standard** (§8): after a restart the screen comes back exactly as it stood — current dream, full strip, settings. Nothing lives only in memory.
- **No dashboard** (§6): no counters, no progress bars, no „generating…" spinner. The only motion is the fade and, optionally, the typewriter.
- **Sizing follows Tool 1's rule** (§6, T1§11): everything in viewport-relative units, so a different screen changes nothing.
- **Credentials from env only** — `ANTHROPIC_API_KEY` (stage 1), `OPENROUTER_API_KEY` (stage 2). Never committed, never written into a project `.env` (§2). The exhibition machine gets them by `export` and nothing else — it has no Hermes install. On Birk's vServer, and only for preparation runs, loading them from `~/.hermes/.env` into the environment is permitted (`set -a; . ~/.hermes/.env; set +a`) — released by Birk 2026-08-26.
- **Language:** German for all visitor-facing text and all prompts; English for code, identifiers and comments.
- **LLM:** model id `claude-opus-5` exactly (no date suffix). Adaptive thinking is on by default — do not pass `thinking`. Never pass `temperature`, `top_p`, `top_k`, or `budget_tokens` (they return 400). Depth is controlled by `output_config.effort`.
- **Contract tests run against a REAL `graph.json` produced by `sim/replay.py`** (§11), committed as `sim/data/graph-19c.json` — never a hand-written fixture, and never a fresh replay run (that needs credentials and minutes; Tool 2's suite must stay runnable offline).
- **Aesthetic judgements are Birk's** (standing rule, 2026-08-25): the visual register and the guiding-question wording are decided by him at the artefacts. Tasks 15 and 16 BUILD the artefacts and print them with **no recommendation marked**.
- **A spec defect gets corrected, not worked around** (standing rule, 2026-08-25): if a task hits something that contradicts the spec, amend the spec with a dated note in the same task.

## Repository layout (created across the tasks below)

```
config2.example.toml           Task 2   Tool 2 config template (no secrets)
kg2/__init__.py                Task 2
kg2/config.py                  Task 2   DreamConfig + load_dream_config
kg2/graph_client.py            Task 3   read-only GET of Tool 1's /graph.json
kg2/db.py                      Task 4   dreams.sqlite3 schema + connect
kg2/models.py                  Task 4   Dream dataclass
kg2/store.py                   Task 4   ALL dream SQLite reads/writes
kg2/trigger.py                 Task 5   the §4.1 race, the floor, collapsing (PURE)
kg2/weighting.py               Task 6   graph -> dream material (hidden excluded)
kg2/condense.py                Task 7   stage 1: material -> German sentence
kg2/imagegen.py                Task 8   stage 2: sentence -> image prompt -> PNG
kg2/cycle.py                   Task 9   one dream: condense -> render -> persist
kg2/server.py                  Task 10  FastAPI app + SSE + operator API
kg2/watcher.py                 Task 11  poll loop, resume, flow control
kg2/__main__.py                Task 11  entrypoint
frontend2/dream.html           Task 12  screen B
frontend2/static/dream.js      Task 12
frontend2/static/dream.css     Task 12
frontend2/static/dream-harness.html  Task 12  (test harness, no EventSource)
frontend2/operator.html        Task 13
frontend2/static/operator.js   Task 13
frontend2/static/operator.css  Task 13
sim/data/graph-19c.json        Task 3   REAL replay artefact (60 interviews)
sim/data/graph-19c.provenance.md  Task 3
sim/dream_register.py          Task 15  3-4 register samples, identical content
sim/dream_calibrate.py         Task 16  question wordings, contradiction, floor
sim/seed_dreams.py             Task 17  seed N dreams for the pre-render
sim/dream_prerender.py         Task 17  the page at 1 / 5 / 20 / 40 dreams
docs/dream-image-contract.md   Task 8   VERIFIED OpenRouter image contract
docs/operations.md             Task 1 (bind) + Task 18 (dream runbook)
tests/test_dream_*.py          per task
```

---

### Task 1: Correct spec §3.1, and make the LAN bind honest

**Files:**
- Modify: `docs/superpowers/specs/2026-08-25-kollektivtraum-design.md` (§3.1)
- Modify: `docs/superpowers/specs/2026-08-12-kollektivgedaechtnis-design.md` (§12, the "One change lands *in* this tool" paragraph)
- Modify: `kg/__main__.py`
- Modify: `docs/operations.md`
- Test: `tests/test_dream_bind.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `kg.__main__.resolved_host(host: str) -> str`.

**THIS IS THE ONLY TASK IN THIS PLAN THAT MAY TOUCH `kg/`, AND IT MAY TOUCH EXACTLY ONE FILE: `kg/__main__.py`.** Not the renderer, not the pipeline, not the schema, not `kg/config.py`, not `kg/server.py` (§3.1). If a later task feels like it needs a change in `kg/`, that is a finding to report, not a change to make.

Spec §3.1 claims `server_host` "must become bindable to the LAN interface". **That claim is wrong.** Verified 2026-08-25: `server_host` is already a `Config` field (`kg/config.py:48`), already in `_FIELD_NAMES` (`kg/config.py:102`), already documented in `config.example.toml:59`, and already passed to uvicorn (`kg/__main__.py`). The mechanism exists. What is missing is configuration, documentation, a cross-machine verification — and one real trap: `kg/__main__.py` prints `http://{cfg.server_host}:{port}`, so with the exhibition value `0.0.0.0` it prints a URL that cannot be opened from the dream machine. A runbook that tells the operator to open an unreachable URL on the festival morning is a trap, not a cosmetic issue.

- [ ] **Step 1: Write the failing test**

`tests/test_dream_bind.py`:

```python
"""The LAN bind (spec §3.1) — the ONE thing Tool 1 changes for Tool 2.

Spec §3.1 originally claimed `server_host` had to *become* bindable. It was
already bindable; this file pins the two things that were actually missing —
that the value round-trips through `load_config`, and that what gets PRINTED
is an address the other machine can open.
"""

from __future__ import annotations

import ipaddress

from kg.__main__ import resolved_host
from kg.config import load_config


def test_server_host_round_trips_through_load_config(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('data_dir = "state"\nserver_host = "0.0.0.0"\n', encoding="utf-8")

    cfg = load_config(cfg_file)

    assert cfg.server_host == "0.0.0.0"


def test_the_documented_default_is_still_localhost(tmp_path):
    """Spec §3.1: the documented default stays 127.0.0.1; the exhibition value
    goes into config.toml on site, so a developer machine is never exposed by
    merely checking the repo out."""
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('data_dir = "state"\n', encoding="utf-8")

    assert load_config(cfg_file).server_host == "127.0.0.1"


def test_resolved_host_leaves_a_literal_host_alone():
    assert resolved_host("127.0.0.1") == "127.0.0.1"
    assert resolved_host("192.168.1.23") == "192.168.1.23"
    assert resolved_host("dream.local") == "dream.local"


def test_resolved_host_replaces_the_wildcard_with_a_routable_address():
    """`http://0.0.0.0:8800/graph.json` is not openable from the dream machine.
    Whatever comes back must be a real IPv4 address, never the wildcard."""
    shown = resolved_host("0.0.0.0")

    assert shown != "0.0.0.0"
    ipaddress.IPv4Address(shown)  # raises if it is not an address at all


def test_resolved_host_handles_the_ipv6_wildcard_too():
    shown = resolved_host("::")

    assert shown != "::"
    ipaddress.IPv4Address(shown)
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_dream_bind.py -v`
Expected: FAIL — `ImportError: cannot import name 'resolved_host' from 'kg.__main__'`

- [ ] **Step 3: Add `resolved_host` to `kg/__main__.py`**

Add this function directly below the imports in `kg/__main__.py`:

```python
def resolved_host(host: str) -> str:
    """The address to PRINT. Never the address to bind.

    Binding to `0.0.0.0` is correct and stays exactly as configured — that is
    what makes Tool 1 reachable from the dream machine (spec §3.1 of the
    Kollektivtraum spec). Printing it is a trap: `http://0.0.0.0:8800` opens
    nothing from another box, and `docs/operations.md` tells the operator to
    open what this line prints. So the wildcard is resolved to the interface
    the default route actually leaves through.

    No packet is sent: `connect()` on a UDP socket only selects a route, and
    192.0.2.1 is TEST-NET-1, reserved and guaranteed unroutable. With no
    default route at all (a laptop with every interface down) this falls back
    to localhost, which is honest — that machine is not reachable either.
    """
    if host not in ("0.0.0.0", "::"):
        return host
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 1))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()
```

Add `import socket` to the import block at the top of the file (alphabetical, after `import logging`).

- [ ] **Step 4: Print the resolved address, and name `graph.json` as Tool 2's entry point**

In `kg/__main__.py`, replace the two `print(...)` lines near the end of `main_async` with:

```python
    shown = resolved_host(cfg.server_host)
    print(f"projection:  http://{shown}:{cfg.server_port}/projection")
    print(f"operator:    http://{shown}:{cfg.server_port}/operator")
    # Named explicitly: this is the one URL the dream machine needs, and the
    # cross-machine check in docs/operations.md is run against exactly it.
    print(f"graph.json:  http://{shown}:{cfg.server_port}/graph.json   (Tool 2 liest das)")
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_dream_bind.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Correct spec §3.1 with a dated note**

In `docs/superpowers/specs/2026-08-25-kollektivtraum-design.md`, replace the whole of §3.1 up to (but not including) the "Nothing else in Tool 1 changes." sentence with:

```markdown
### 3.1 The one change inside Tool 1

> **Correction, 2026-08-25 (plan cycle, Task 1).** This section originally
> claimed `server_host = "127.0.0.1"` was hard-coded and "must become bindable
> to the LAN interface". **That was wrong.** Verified against the code:
> `server_host` is already a `Config` field (`kg/config.py:48`), already in
> `_FIELD_NAMES` (`kg/config.py:102`), already documented in
> `config.example.toml:59`, and already passed to uvicorn in `kg/__main__.py`.
> The mechanism has existed since Task 1 of Tool 1. The original claim is left
> here rather than deleted, because this spec is a decision record and a wrong
> claim that quietly disappears teaches nobody anything.

What is actually missing is **configuration, documentation and verification**,
plus one real defect: `kg/__main__.py` printed `http://{server_host}:{port}`,
so with the exhibition value `0.0.0.0` it printed a URL that cannot be opened
from the dream machine — while `docs/operations.md` tells the operator to open
exactly what is printed.

**This is the same requirement CR-1 has for screen C.** Scope strictly:

- `server_host` stays configurable with the documented default `127.0.0.1`; the
  exhibition value `0.0.0.0` goes into `config.toml` on site, never into the
  repo.
- `kg/__main__.py` resolves the wildcard to the routable interface address for
  the three URLs it prints, and names `/graph.json` as Tool 2's entry point.
  **This is the only code change inside `kg/` in the entire Tool 2 build.**
- **No authentication.** The station runs on an isolated local network for one
  day; adding auth here is complexity that buys nothing and adds a failure mode
  at 9 a.m. Documented as a deliberate choice, not an oversight.
- `docs/operations.md` gains the bind value and the cross-machine check — and
  the check must be run **from the other box**, never from localhost on the
  server (the pitfall CR-1 already names).
```

- [ ] **Step 7: Correct the matching claim in Tool 1's spec §12**

In `docs/superpowers/specs/2026-08-12-kollektivgedaechtnis-design.md` §12, replace the paragraph beginning "One change lands *in* this tool:" with:

```markdown
  One change lands *in* this tool, and it is smaller than Tool 2's spec first
  claimed: `server_host` was **already** LAN-bindable (`kg/config.py:48`,
  `config.example.toml:59`) — corrected 2026-08-25, see Tool 2 spec §3.1. All
  that lands here is `kg/__main__.py` printing the *resolved* interface address
  instead of the literal `0.0.0.0`, so the URL the runbook tells the operator to
  open is one the dream machine can actually open. Nothing else in `kg/` is
  touched by the Tool 2 build.
```

- [ ] **Step 8: Add the bind value and the cross-machine check to the runbook**

In `docs/operations.md`, insert this section immediately before `## Ein Interview`:

```markdown
## Netzwerk für Screen B und Screen C

Tool 1 hört im Normalfall nur auf `127.0.0.1` — dann erreicht **keine** andere
Maschine die Station. Für den Ausstellungstag in `config.toml`:

```toml
server_host = "0.0.0.0"
```

Bewusste Entscheidung: **keine Authentifizierung** (Tool-2-Spec §3.1). Die
Station läuft einen Tag lang in einem isolierten lokalen Netz; ein Login wäre
hier zusätzliche Komplexität und eine zusätzliche Fehlerquelle um 9 Uhr
morgens.

Nach dem Start druckt der Core drei URLs — mit der **aufgelösten** Adresse,
nicht mit `0.0.0.0`. Die dritte ist die, die die Traum-Maschine braucht.

**Die Prüfung wird von der ANDEREN Maschine aus gefahren, niemals per
localhost auf dem Ausstellungsrechner.** Ein `curl` auf dem Server selbst
gelingt auch dann, wenn der Bind falsch ist, und beweist deshalb nichts:

```bash
# auf der Traum-Maschine, nicht auf dem Ausstellungsrechner:
curl -s http://<adresse-vom-core-ausgegeben>:8800/graph.json | head -c 200
```

Kommt hier JSON mit `"version": 1` zurück, ist die Netzwerkhälfte beantwortet
— und zwar genau mit dem Aufruf, den der Watcher im Betrieb macht.

Schlägt es fehl: Bind prüfen (`ss -ltnp | grep 8800` muss `0.0.0.0:8800`
zeigen, nicht `127.0.0.1:8800`), dann die Firewall, dann ob beide Maschinen
wirklich im selben Netz hängen.
```

- [ ] **Step 9: Run the full existing suite to prove nothing in Tool 1 broke**

Run: `uv run pytest tests/ -x -q --ignore=tests/test_projection.py`
Expected: PASS. The one changed file is `kg/__main__.py`, and only its print lines and one new function; `tests/test_core.py`, `tests/test_server.py` and the rest must be untouched by this.

- [ ] **Step 10: Commit**

```bash
git add kg/__main__.py tests/test_dream_bind.py docs/operations.md \
        docs/superpowers/specs/2026-08-25-kollektivtraum-design.md \
        docs/superpowers/specs/2026-08-12-kollektivgedaechtnis-design.md
git commit -m "fix: print the resolved LAN address, and correct spec 3.1's bind claim

server_host was already bindable — the spec was wrong and is corrected with a
dated note rather than quietly edited. The real defect was printing
http://0.0.0.0:8800, a URL the dream machine cannot open, in a runbook that
tells the operator to open what is printed."
```

---

### Task 2: `kg2` skeleton and configuration

**Files:**
- Create: `kg2/__init__.py`, `kg2/config.py`, `config2.example.toml`
- Modify: `pyproject.toml`, `.gitignore`
- Test: `tests/test_dream_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `kg2.config.DreamConfig` (frozen dataclass) and `kg2.config.load_dream_config(path: Path | None = None) -> DreamConfig`. Every later task takes a `DreamConfig` instance. Also `kg2.config.DEFAULT_GUIDING_QUESTION` and `kg2.config.DEFAULT_VISUAL_REGISTER`, both **placeholders that Birk replaces at Tasks 15/16**.

A separate config file, not a `[dream]` section in Tool 1's `config.toml`: Tool 2 runs on a different machine (§9), so a shared file would be a lie. Note the split between `guiding_question`/`visual_register` (set in the morning, in the file, **never** runtime-adjustable — §7) and the `default_*` display fields, which only seed the store on a fresh database and are then owned by the operator UI (the same `set_setting_default` discipline Tool 1 uses for `default_min_mentions`).

- [ ] **Step 1: Write the failing test**

`tests/test_dream_config.py`:

```python
from pathlib import Path

import pytest

from kg2.config import DreamConfig, load_dream_config


def test_load_reads_toml_and_resolves_paths(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config2.toml"
    cfg_file.write_text(
        """
        data_dir = "dream-state"
        tool1_url = "http://192.168.1.10:8800"
        poll_interval_s = 5.0
        min_interval_s = 240
        contradiction_min_persons = 6
        guiding_question = "Wie leben und bauen wir in zehn Jahren?"
        visual_register = "malerisch, atmosphaerisch, weich"
        server_host = "0.0.0.0"
        server_port = 8810
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    cfg = load_dream_config(cfg_file)

    assert isinstance(cfg, DreamConfig)
    assert cfg.data_dir == (tmp_path / "dream-state").resolve()
    assert cfg.db_path == (tmp_path / "dream-state" / "dreams.sqlite3").resolve()
    assert cfg.image_dir == (tmp_path / "dream-state" / "images").resolve()
    assert cfg.tool1_url == "http://192.168.1.10:8800"
    assert cfg.graph_url == "http://192.168.1.10:8800/graph.json"
    assert cfg.poll_interval_s == 5.0
    assert cfg.min_interval_s == 240
    assert cfg.contradiction_min_persons == 6
    assert cfg.guiding_question == "Wie leben und bauen wir in zehn Jahren?"
    assert cfg.visual_register == "malerisch, atmosphaerisch, weich"
    assert cfg.server_host == "0.0.0.0"
    assert cfg.server_port == 8810
    assert cfg.anthropic_api_key == "sk-test"
    assert cfg.openrouter_api_key == "sk-or-test"


def test_defaults_are_the_spec_values(tmp_path, monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    cfg_file = tmp_path / "config2.toml"
    cfg_file.write_text('data_dir = "dream-state"\n', encoding="utf-8")

    cfg = load_dream_config(cfg_file)

    # Spec §4.1 / §5.1 / §10 — the calibration START values, not final ones.
    assert cfg.poll_interval_s == 5.0
    assert cfg.min_interval_s == 240
    assert cfg.contradiction_min_persons == 6
    # Spec §5.1 / §5.2 — one model to reason about, one credential each.
    assert cfg.condense_model == "claude-opus-5"
    assert cfg.image_model == "google/gemini-3-pro-image"
    # Spec §3.1: the documented default stays localhost here too.
    assert cfg.server_host == "127.0.0.1"
    # Deliberately NOT 8800: both processes must be runnable on one box during
    # development without a port clash.
    assert cfg.server_port == 8810
    assert cfg.anthropic_api_key is None
    assert cfg.openrouter_api_key is None


def test_directories_are_created(tmp_path):
    cfg_file = tmp_path / "config2.toml"
    cfg_file.write_text('data_dir = "dream-state"\n', encoding="utf-8")

    cfg = load_dream_config(cfg_file)

    assert cfg.data_dir.is_dir()
    assert cfg.image_dir.is_dir()


def test_a_trailing_slash_on_tool1_url_does_not_double_up(tmp_path):
    cfg_file = tmp_path / "config2.toml"
    cfg_file.write_text(
        'data_dir = "d"\ntool1_url = "http://10.0.0.2:8800/"\n', encoding="utf-8"
    )

    assert load_dream_config(cfg_file).graph_url == "http://10.0.0.2:8800/graph.json"


def test_the_example_config_carries_no_credentials():
    """Same rule as Tool 1 (spec §2): keys come from the environment only."""
    text = Path("config2.example.toml").read_text(encoding="utf-8")

    # No assignment of a key-shaped field, and no key-shaped literal anywhere.
    assignments = [
        line.split("=")[0].strip()
        for line in text.splitlines()
        if "=" in line and not line.strip().startswith("#")
    ]
    assert "anthropic_api_key" not in assignments
    assert "openrouter_api_key" not in assignments
    for forbidden in ("sk-ant-", "sk-or-v1-"):
        assert forbidden not in text


def test_the_example_config_loads(tmp_path, monkeypatch):
    """A template that does not parse is a 9 a.m. failure, so it is tested."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    target = tmp_path / "config2.toml"
    target.write_text(
        Path("config2.example.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )

    cfg = load_dream_config(target)

    assert cfg.tool1_url.startswith("http://")
    assert cfg.guiding_question
    assert cfg.visual_register
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_dream_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kg2'`

- [ ] **Step 3: Create the package and the config module**

```bash
mkdir -p kg2 frontend2/static
touch kg2/__init__.py
```

Write `kg2/config.py`:

```python
"""Tool 2's own configuration. Secrets come from the environment, never here.

Deliberately a SEPARATE file from Tool 1's `config.toml`, not a section inside
it: Tool 2 runs on its own machine (spec §9), so a shared file would describe a
sharing that does not exist.

Two kinds of value live here and they must not be confused:

* `guiding_question` and `visual_register` are set in the morning and are
  **never** runtime-adjustable (spec §7). Changing the question mid-day destroys
  exactly the comparability the history strip exists for.
* the `default_*` fields only SEED the store on a fresh database. After that the
  operator UI owns them and a restart must restore the operator's value, not the
  file's — the same `set_setting_default` discipline Tool 1 uses for
  `default_min_mentions`.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

# PLACEHOLDER. The wording is decided by Birk at Task 16, from sentences the
# calibration run prints — not chosen here (spec §10, brainstorm §7). It must
# stay wide enough to carry all three interview themes: future of building,
# AI in building, new forms of living together.
DEFAULT_GUIDING_QUESTION = "Wie leben und bauen wir in zehn Jahren?"

# PLACEHOLDER. The register is decided by Birk AT IMAGES at Task 15, not in
# words (spec §10, brainstorm §10). This starting value describes the register
# of the approved rendering kollektivtraum-screen_v2_2026-08-16.png.
# „keine Schrift im Bild" is load-bearing, not decoration: the sentence is a
# separate displayed artefact (spec §5.2) and text rendered inside the image
# would compete with it.
DEFAULT_VISUAL_REGISTER = (
    "Malerisch und atmosphärisch, weiche Übergänge, gedämpfte Farbigkeit, "
    "diffuses Licht, sichtbarer Pinselduktus. Kein Fotorealismus, kein "
    "Architektur-Rendering, keine Schrift im Bild."
)


@dataclass(frozen=True)
class DreamConfig:
    data_dir: Path

    # -- Tool 1, over the network only (spec §2, §9) ------------------------
    tool1_url: str = "http://127.0.0.1:8800"
    poll_interval_s: float = 5.0
    fetch_timeout_s: float = 10.0

    # -- the trigger (spec §4.1, calibrated at Task 16) ---------------------
    min_interval_s: int = 240

    # -- the dream (spec §5, calibrated at Tasks 15/16) ---------------------
    contradiction_min_persons: int = 6
    guiding_question: str = DEFAULT_GUIDING_QUESTION
    visual_register: str = DEFAULT_VISUAL_REGISTER

    # -- stage 1 (spec §5.1) ------------------------------------------------
    condense_model: str = "claude-opus-5"
    condense_effort: str = "high"
    condense_max_tokens: int = 16000

    # -- stage 2 (spec §5.2; the endpoint shape is verified at Task 8) ------
    image_model: str = "google/gemini-3-pro-image"
    image_url: str = "https://openrouter.ai/api/v1/chat/completions"
    image_aspect_ratio: str = "16:9"
    image_timeout_s: float = 180.0

    # -- display start values, owned by the operator UI afterwards (spec §7)
    default_question_visible: bool = True
    default_question_seconds: int = 0  # 0 = permanent
    default_fade_ms: int = 1200  # spec §6: cross-fade, default 1.2 s
    default_strip_ratio: float = 0.22
    default_typewriter: bool = False  # spec §6: Birk decides visually on site

    # -- Tool 2's own server ------------------------------------------------
    server_host: str = "127.0.0.1"
    server_port: int = 8810

    anthropic_api_key: str | None = None
    openrouter_api_key: str | None = None

    @property
    def db_path(self) -> Path:
        return self.data_dir / "dreams.sqlite3"

    @property
    def image_dir(self) -> Path:
        return self.data_dir / "images"

    @property
    def graph_url(self) -> str:
        """The one URL Tool 2 ever calls on Tool 1 (spec §2, §4.1)."""
        return f"{self.tool1_url.rstrip('/')}/graph.json"

    def __post_init__(self) -> None:
        # Directories exist as soon as a DreamConfig exists — the server mounts
        # image_dir at import time, exactly as Tool 1's Config does for
        # portrait_dir.
        for directory in (self.data_dir, self.image_dir):
            directory.mkdir(parents=True, exist_ok=True)


_FIELD_NAMES = {
    "tool1_url",
    "poll_interval_s",
    "fetch_timeout_s",
    "min_interval_s",
    "contradiction_min_persons",
    "guiding_question",
    "visual_register",
    "condense_model",
    "condense_effort",
    "condense_max_tokens",
    "image_model",
    "image_url",
    "image_aspect_ratio",
    "image_timeout_s",
    "default_question_visible",
    "default_question_seconds",
    "default_fade_ms",
    "default_strip_ratio",
    "default_typewriter",
    "server_host",
    "server_port",
}


def load_dream_config(path: Path | None = None) -> DreamConfig:
    path = Path(path) if path else Path("config2.toml")
    raw: dict = {}
    if path.exists():
        raw = tomllib.loads(path.read_text(encoding="utf-8"))

    base = path.parent.resolve()
    data_dir = (base / raw.get("data_dir", "dream-data")).resolve()

    kwargs = {k: v for k, v in raw.items() if k in _FIELD_NAMES}
    return DreamConfig(
        data_dir=data_dir,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY"),
        **kwargs,
    )
```

- [ ] **Step 4: Write `config2.example.toml`**

```toml
# Kollektivtraum (Tool 2) — auf der Traum-Maschine nach config2.toml kopieren.
# Geheimnisse stehen NICHT hier, sondern in der Umgebung:
#   export ANTHROPIC_API_KEY=...      # Stufe 1: Graph -> Satz
#   export OPENROUTER_API_KEY=...     # Stufe 2: Satz -> Bild

data_dir = "dream-data"

# Tool 1 über das Netz, nie über das Dateisystem (Spec §2, §9).
# Die Adresse druckt der Core beim Start; von DIESER Maschine aus prüfen:
#   curl -s http://<adresse>:8800/graph.json | head -c 200
tool1_url = "http://127.0.0.1:8800"

# Vollständiger Zustand, kein Delta (Spec §4.1). 5 s sind bei 240 s
# Mindestabstand unsichtbar; hier verstellbar, falls das Netz vor Ort zickt.
poll_interval_s = 5.0

# Mindestabstand zwischen zwei Träumen, gemessen ab dem START des letzten.
# Startwert 240 — kalibriert, siehe docs/operations.md.
min_interval_s = 240

# Ab wie vielen Personen der Widerspruch als Konstruktionsprinzip eingeschaltet
# wird (Spec §5.1). Darunter läuft Stufe 1 allein auf der Gewichtung, weil das
# Modell bei drei Interviews einen Gegensatz erfinden würde.
contradiction_min_persons = 6

# EINE Leitfrage, den ganzen Tag (Spec §7). Nicht zur Laufzeit änderbar:
# eine wandernde Frage macht den Verlaufsstreifen unlesbar.
guiding_question = "Wie leben und bauen wir in zehn Jahren?"

# EIN Bildregister, den ganzen Tag (Spec §5.2, §10). Wird an jeden Bildprompt
# angehängt, nie vom Modell gewählt, nie aus dem Graphen abgeleitet.
visual_register = "Malerisch und atmosphärisch, weiche Übergänge, gedämpfte Farbigkeit, diffuses Licht, sichtbarer Pinselduktus. Kein Fotorealismus, kein Architektur-Rendering, keine Schrift im Bild."

condense_model = "claude-opus-5"
condense_effort = "high"

# Vertrag verifiziert in docs/dream-image-contract.md.
image_model = "google/gemini-3-pro-image"
image_url = "https://openrouter.ai/api/v1/chat/completions"
image_aspect_ratio = "16:9"

# Startwerte der Anzeige. Danach gehören sie dem Operator-UI, und ein Neustart
# stellt DESSEN Wert wieder her, nicht diesen hier.
default_question_visible = true
default_question_seconds = 0     # 0 = dauerhaft
default_fade_ms = 1200           # Überblendung, kein Morph (Spec §6)
default_strip_ratio = 0.22
default_typewriter = false       # Birk entscheidet vor Ort

# Am Ausstellungstag auf "0.0.0.0", damit das Operator-Fenster von einem
# zweiten Gerät erreichbar ist. 8810, damit beide Tools auf einer Kiste laufen
# können, ohne sich den Port zu nehmen.
server_host = "127.0.0.1"
server_port = 8810
```

- [ ] **Step 5: Add `kg2` to the wheel and ignore the dream state directory**

In `pyproject.toml`, change the packages line:

```toml
[tool.hatch.build.targets.wheel]
packages = ["kg", "kg2"]
```

Append to `.gitignore`:

```
dream-data/
```

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_dream_config.py -v`
Expected: PASS (6 tests)

- [ ] **Step 7: Commit**

```bash
git add kg2/__init__.py kg2/config.py config2.example.toml pyproject.toml \
        .gitignore tests/test_dream_config.py
git commit -m "feat: kg2 package skeleton and its own configuration"
```

---

### Task 3: The Tool 1 contract — a real fixture, a drift guard, and the read-only client

**Files:**
- Create: `sim/data/graph-19c.json`, `sim/data/graph-19c.provenance.md`, `kg2/graph_client.py`
- Test: `tests/test_dream_contract.py`

**Interfaces:**
- Consumes: Task 2 (`DreamConfig.graph_url`).
- Produces:
  - `kg2.graph_client.fetch_graph(url: str, timeout: float = 10.0, get=...) -> dict | None`
  - `tests/test_dream_contract.py::REAL_GRAPH` — the loaded fixture, imported by every later contract test via the `real_graph` fixture in `tests/conftest.py`.

Spec §11 requires contract tests against a **real** `graph.json` from `sim/replay.py`, never a hand-written fixture, "because a fixture would encode today's assumption about the format and pass forever while the real file drifts". Run 19c's output is a real artefact of the harness (60 persons, 163 terms, 267 edges, 117 quotes) but lives under the gitignored `out/`, so it is copied into the repo with its provenance recorded beside it.

The fixture alone does not solve the drift problem — it only moves it. **The drift guard is the more important half:** a test that builds a graph through the live `kg.export.build_graph` and asserts the *key sets and types* still match the committed artefact. Values are deliberately not compared (Birk, 2026-08-25): interview content changes legitimately and must not turn tests red.

Contract tests must **not** invoke a fresh replay run — that needs credentials and minutes, and would make Tool 2's suite unrunnable offline, which Tool 1 deliberately avoided (its embedding cache exists for exactly that reason).

- [ ] **Step 1: Copy the real artefact in and record where it came from**

```bash
cp out/sim19c/graph.json sim/data/graph-19c.json
python3 -c "
import json; g=json.load(open('sim/data/graph-19c.json'))
p=[n for n in g['nodes'] if n['type']=='person']; t=[n for n in g['nodes'] if n['type']=='term']
print(len(p),'persons',len(t),'terms',len(g['edges']),'edges',len(g['quotes']),'quotes')"
```
Expected: `60 persons 163 terms 267 edges 117 quotes`

Write `sim/data/graph-19c.provenance.md`:

```markdown
# `graph-19c.json` — where this file comes from

**Not a fixture. A real artefact.** Spec §11 of the Kollektivtraum design
requires Tool 2's contract tests to run against a real `graph.json` produced by
`sim/replay.py`, never a hand-written one — because a hand-written fixture
encodes today's assumption about the format and then passes forever while the
real file drifts away from it.

| | |
|---|---|
| Produced by | `uv run python -m sim.replay --db out/sim19c/sim.db` |
| Run | **19c** — the run that produced Tool 1's calibrated values (`docs/operations.md`, „Kalibrierte Werte") |
| Corpus | `sim/data/interviews/*.json`, all 60 synthetic interviews |
| Settings of that run | `terms_per_interview = 5`, `merge_neighbours = 12`, name lock D5 active |
| Contents | 60 persons, 163 terms, 267 edges, 117 quotes |
| Copied into the repo | 2026-08-25, Tool 2 plan Task 3 |

Why a copy and not a re-run: `out/` is gitignored, and re-running the harness
needs `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY` and several minutes. Tool 2's
test suite must stay runnable offline and for free, the same property Tool 1's
embedding cache exists to protect.

**Every `x` and `y` in this file is `null`, and that is correct** — positions
are written by the renderer (`POST /api/positions`), and a replay run has no
renderer. Tool 2 never reads positions, so this costs it nothing; a test that
starts depending on a non-null `x` is testing the wrong thing.

**All `hidden` flags are `false`** — nobody operated the wall during a replay.
Hidden-node exclusion (spec §5.1) is therefore tested against graphs derived
from this one by flipping the flag, not against the file as it stands.

If this file is ever regenerated, `tests/test_dream_contract.py` is what proves
the new one still matches what `kg.export.build_graph` produces today.
```

- [ ] **Step 2: Write the failing test**

`tests/test_dream_contract.py`:

```python
"""Tool 1's `graph.json` is Tool 2's entire input. This file pins the contract.

Two halves, and the second is the important one:

1. The fixture is a REAL artefact of `sim/replay.py` (see
   `sim/data/graph-19c.provenance.md`), not a hand-written dict.
2. The DRIFT GUARD builds a graph through the live `kg.export.build_graph` and
   asserts the key sets and types still agree with that artefact. Values are
   deliberately never compared: interview content changes legitimately, and a
   test that goes red for that teaches the reader to ignore it.

Spec §13 names five properties of Tool 1 that are now load-bearing. Four of
them are pinned here; the fifth (`broadcast_graph` firing after the pipeline)
is a timing property and lives in `tests/test_dream_trigger.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kg.config import Config
from kg.export import build_graph
from kg.store import Store
from kg2.graph_client import fetch_graph

FIXTURE = Path(__file__).resolve().parent.parent / "sim" / "data" / "graph-19c.json"
REAL_GRAPH = json.loads(FIXTURE.read_text(encoding="utf-8"))

# Every JSON path Tool 2 reads, and the type it must find there. This list is
# the contract, written out rather than derived, so that deleting a field from
# Tool 1's export fails here with the field's name in the message.
REQUIRED: dict[str, set[str]] = {
    ".version": {"int"},
    ".generated_at": {"float"},
    ".nodes[].id": {"str"},
    ".nodes[].type": {"str"},
    ".nodes[].created_at": {"float"},
    ".nodes[].hidden": {"bool"},
    ".nodes[].label": {"str"},  # terms only
    ".nodes[].mentions": {"int"},  # terms only — spec §13(3), the weighting input
    ".edges[].id": {"str"},
    ".edges[].source": {"str"},
    ".edges[].target": {"str"},
    ".quotes[].id": {"str"},  # spec §13(2), kept for Tool 2's benefit alone
    ".quotes[].person_id": {"str"},
    ".quotes[].text": {"str"},
}


def type_map(value, prefix: str = "") -> dict[str, set[str]]:
    """Every JSON path in `value`, mapped to the set of types found there.

    List indices collapse to `[]`, so 60 person nodes contribute one entry per
    field rather than sixty. Values themselves are never recorded — this is a
    contract check, and the contract is shape, not content.
    """
    out: dict[str, set[str]] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            for path, types in type_map(item, f"{prefix}.{key}").items():
                out.setdefault(path, set()).update(types)
    elif isinstance(value, list):
        for item in value:
            for path, types in type_map(item, f"{prefix}[]").items():
                out.setdefault(path, set()).update(types)
    else:
        out[prefix] = {type(value).__name__}
    return out


def live_graph(tmp_path) -> dict:
    """A graph built through the REAL exporter, covering every optional branch.

    Deliberately exercises both sides of every nullable field — a person with a
    portrait and one without, a placed node and an unplaced one, a hidden term —
    so the type map below carries `NoneType` exactly where the export really can
    produce it.
    """
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    with_portrait = store.create_person(started_at=100.0, portrait_path="portraits/a.png")
    without = store.create_person(started_at=200.0)
    shared = store.get_or_create_term("Recycling-Beton", created_at=110.0)
    lonely = store.get_or_create_term("Sickerfähige Beläge", created_at=210.0)
    store.add_edge(with_portrait.id, shared.id, created_at=120.0)
    store.add_edge(without.id, shared.id, created_at=220.0)
    store.add_edge(without.id, lonely.id, created_at=221.0)
    store.add_quote(with_portrait.id, "Wir bauen zu viel Neues.", created_at=130.0)
    store.set_hidden(f"term:{lonely.id}", True)
    store.save_positions({shared.id: (12.0, -8.0)})  # the other nodes stay null
    graph = build_graph(store)
    store.close()
    return graph


def test_the_fixture_is_the_real_run_and_not_a_toy(tmp_path):
    persons = [n for n in REAL_GRAPH["nodes"] if n["type"] == "person"]
    terms = [n for n in REAL_GRAPH["nodes"] if n["type"] == "term"]

    assert len(persons) == 60
    assert len(terms) == 163
    assert len(REAL_GRAPH["edges"]) == 267
    assert len(REAL_GRAPH["quotes"]) == 117
    # A hand-written fixture would not have a long tail of single mentions.
    singletons = [t for t in terms if t["mentions"] == 1]
    assert len(singletons) > 100


def test_every_path_tool_2_reads_exists_in_the_real_artefact():
    found = type_map(REAL_GRAPH)

    for path, types in REQUIRED.items():
        assert path in found, f"{path} is missing from sim/data/graph-19c.json"
        assert types <= found[path], f"{path}: expected {types}, found {found[path]}"


def test_every_path_tool_2_reads_is_still_produced_by_the_live_exporter(tmp_path):
    """The drift guard. If Tool 1's export loses a field, this fails here —
    not silently, months later, on the festival morning."""
    found = type_map(live_graph(tmp_path))

    for path, types in REQUIRED.items():
        assert path in found, f"kg.export.build_graph no longer produces {path}"
        assert types <= found[path], f"{path}: expected {types}, found {found[path]}"


def test_the_committed_artefact_and_the_live_exporter_agree_on_the_key_set(tmp_path):
    """Key sets, not values (Birk, 2026-08-25): content changes legitimately."""
    fixture_paths = set(type_map(REAL_GRAPH))
    live_paths = set(type_map(live_graph(tmp_path)))

    assert fixture_paths == live_paths, (
        "sim/data/graph-19c.json and kg.export.build_graph have drifted apart:\n"
        f"  only in the fixture: {sorted(fixture_paths - live_paths)}\n"
        f"  only in the export:  {sorted(live_paths - fixture_paths)}"
    )


def test_graph_json_is_complete_state_with_no_delta_mechanism():
    """Spec §13(1). A `changed`/`removed`/`since` key would mean Tool 2's poll
    is no longer sufficient and the whole §4.1 design has to be revisited."""
    assert set(REAL_GRAPH) == {"version", "generated_at", "min_mentions", "nodes", "edges", "quotes"}


def test_hidden_stays_in_the_payload():
    """Spec §13(4) — it is Tool 2's exclusion input (§5.1)."""
    assert all("hidden" in node for node in REAL_GRAPH["nodes"])


def test_fetch_graph_returns_the_payload(tmp_path):
    calls = []

    def fake_get(url, timeout):
        calls.append((url, timeout))
        return REAL_GRAPH

    graph = fetch_graph("http://10.0.0.2:8800/graph.json", timeout=7.0, get=fake_get)

    assert graph["version"] == 1
    assert calls == [("http://10.0.0.2:8800/graph.json", 7.0)]


def test_fetch_graph_returns_none_when_tool_1_is_unreachable():
    """Spec §8: „Poll keeps failing quietly." Never an exception, because an
    exception in the watcher loop is one restart away from a blank screen B."""

    def dead(url, timeout):
        raise OSError("connection refused")

    assert fetch_graph("http://10.0.0.2:8800/graph.json", get=dead) is None


def test_fetch_graph_returns_none_for_a_truncated_body():
    def half_written(url, timeout):
        raise ValueError("Expecting value: line 1 column 1 (char 0)")

    assert fetch_graph("http://x/graph.json", get=half_written) is None


def test_fetch_graph_rejects_a_payload_that_is_not_a_graph():
    """An HTML error page parsed as JSON, or a proxy's `{"error": ...}`, must
    not be handed on as if it were state."""

    def wrong(url, timeout):
        return {"error": "bad gateway"}

    assert fetch_graph("http://x/graph.json", get=wrong) is None


def test_the_graph_client_has_no_way_to_write_to_tool_1():
    """Spec §2 is a guarantee, and the cheapest guarantee is having no verb.

    A source-level check on purpose: a future edit that adds a POST „just for
    the operator" fails here with the reason attached, which a behavioural test
    over the current code could never do.
    """
    import kg2.graph_client

    source = Path(kg2.graph_client.__file__).read_text(encoding="utf-8")

    for verb in (".post(", ".put(", ".patch(", ".delete("):
        assert verb not in source, f"kg2/graph_client.py must never {verb}"
```

- [ ] **Step 3: Run the test and confirm it fails**

Run: `uv run pytest tests/test_dream_contract.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kg2.graph_client'`

- [ ] **Step 4: Implement `kg2/graph_client.py`**

```python
"""The only thing Tool 2 ever says to Tool 1, and it is a question.

Read-only by construction (spec §2): this module has no POST, no PUT, no PATCH
and no DELETE, and `tests/test_dream_contract.py` asserts on the source that it
never grows one. Tool 1 must keep working when Tool 2 is broken, and the
cheapest way to guarantee that is to have no way to write at all.

Polling a complete-state endpoint, not subscribing to `/events` (spec §4.1):
it survives a Tool 1 restart with no reconnect logic, it is the pattern CR-1
already chose, and at a 240 s floor a 5 s detection lag is invisible.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# The keys that make a payload Tool 1's state rather than an error page, a
# proxy's JSON or half a file. Checked before the payload is handed on, because
# a caller that gets `{"error": ...}` here would read `graph["nodes"]` and
# crash the watcher loop.
_REQUIRED_KEYS = frozenset({"version", "nodes", "edges"})


def _httpx_get(url: str, timeout: float) -> dict:
    import httpx

    response = httpx.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_graph(url: str, timeout: float = 10.0, get=_httpx_get) -> dict | None:
    """Tool 1's complete state, or None. NEVER raises.

    `get` is injectable so no test ever touches the network.

    Every failure — refused connection, DNS, timeout, 500, truncated body, an
    HTML error page — collapses to None, and the caller does nothing. That is
    spec §8's „poll keeps failing quietly": nothing new was said, so no new
    dream is correct behaviour, and the display is untouched either way.
    """
    try:
        payload = get(url, timeout)
    except Exception as exc:  # network, HTTP status, JSON — all the same to us
        log.debug("graph fetch failed: %s", exc)
        return None
    if not isinstance(payload, dict) or not _REQUIRED_KEYS <= set(payload):
        log.warning("graph fetch returned something that is not a graph: %r", type(payload))
        return None
    return payload
```

- [ ] **Step 5: Add the shared `real_graph` fixture**

Append to `tests/conftest.py`:

```python
@pytest.fixture(scope="session")
def real_graph():
    """The real `graph.json` of replay run 19c (spec §11).

    Session-scoped and returned as a fresh deep copy per use is deliberately
    NOT done: every consumer treats the graph as read-only input, and a copy
    per test of a 92 KB document 20 times over is waste. A test that needs to
    mutate it must `copy.deepcopy` it itself and say why.
    """
    import json

    path = REPO_ROOT / "sim" / "data" / "graph-19c.json"
    return json.loads(path.read_text(encoding="utf-8"))
```

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_dream_contract.py -v`
Expected: PASS (11 tests)

- [ ] **Step 7: Commit**

```bash
git add sim/data/graph-19c.json sim/data/graph-19c.provenance.md \
        kg2/graph_client.py tests/test_dream_contract.py tests/conftest.py
git commit -m "feat: pin Tool 1's graph.json contract against a real replay artefact

The drift guard is the point: a committed fixture alone would pass forever
while kg.export.build_graph moved away from it. Key sets and types are
compared, never values."
```

---

### Task 4: The dream store

**Files:**
- Create: `kg2/db.py`, `kg2/models.py`, `kg2/store.py`
- Test: `tests/test_dream_store.py`

**Interfaces:**
- Consumes: Task 2 (`DreamConfig.db_path`).
- Produces:
  - `kg2.models.Dream` — frozen dataclass with fields `id, created_at, graph_generated_at, person_count, term_count, edge_count, contradiction, guiding_question, absorbed_persons, stage1_prompt, sentence, stage2_prompt, condense_model, image_model, image_path, status, error, discarded`
  - `kg2.db.connect(path: Path) -> sqlite3.Connection`, `kg2.db.SCHEMA`
  - `kg2.store.DreamStore` with `open(path)`, `close()`, `create_dream(...) -> Dream`, `set_stage1(dream_id, prompt, sentence, model)`, `set_stage2_prompt(dream_id, prompt, model)`, `finish_dream(dream_id, image_path)`, `fail_dream(dream_id, error)`, `set_discarded(dream_id, discarded)`, `get_dream(dream_id) -> Dream | None`, `all_dreams() -> list[Dream]`, `visible_dreams() -> list[Dream]`, `current_dream() -> Dream | None`, `history() -> list[Dream]`, `get_setting(key, default)`, `set_setting(key, value)`, `set_setting_default(key, value)`

Everything screen B shows must be reconstructible from this file after a crash (§8) — current dream, full strip, every display setting. Nothing lives only in memory.

Two decisions worth stating, because both are easy to get wrong:

- **A failed or discarded dream still counts as a dream that STARTED.** `last_started_at()` spans every row regardless of status, because §8's „retry at the next trigger — never a retry storm" is exactly the floor applying to failures too.
- **`absorbed_persons` is stored per dream.** Without it a restart cannot tell which interviews have already been condensed, and the watcher would either dream immediately for all 40 or never dream again. It is a JSON array of the person ids the dream consumed, and only `status='done'` rows count as consuming.

- [ ] **Step 1: Write the failing test**

`tests/test_dream_store.py`:

```python
"""Everything screen B shows survives a restart, because none of it is in RAM."""

from __future__ import annotations

from kg2.models import Dream
from kg2.store import DreamStore


def open_store(tmp_path) -> DreamStore:
    return DreamStore.open(tmp_path / "dreams.sqlite3")


def make_dream(store, *, at: float, persons=("p1",), sentence="Ein Satz.", image="a.png"):
    dream = store.create_dream(
        created_at=at,
        graph_generated_at=at - 1.0,
        person_count=len(persons),
        term_count=3,
        edge_count=4,
        contradiction=False,
        guiding_question="Wie leben und bauen wir in zehn Jahren?",
        absorbed_persons=list(persons),
    )
    store.set_stage1(dream.id, prompt="S1", sentence=sentence, model="claude-opus-5")
    store.set_stage2_prompt(dream.id, prompt="S2", model="google/gemini-3-pro-image")
    store.finish_dream(dream.id, image_path=image)
    return store.get_dream(dream.id)


def test_a_finished_dream_carries_every_field_the_record_needs(tmp_path):
    """Spec §5.3 — file + parameters + machine-readable record."""
    store = open_store(tmp_path)

    dream = make_dream(store, at=1000.0, persons=("p1", "p2"))

    assert isinstance(dream, Dream)
    assert dream.id == "d1"
    assert dream.created_at == 1000.0
    assert dream.graph_generated_at == 999.0
    assert dream.person_count == 2
    assert dream.term_count == 3
    assert dream.edge_count == 4
    assert dream.contradiction is False
    assert dream.guiding_question == "Wie leben und bauen wir in zehn Jahren?"
    assert dream.absorbed_persons == ["p1", "p2"]
    assert dream.stage1_prompt == "S1"
    assert dream.sentence == "Ein Satz."
    assert dream.stage2_prompt == "S2"
    assert dream.condense_model == "claude-opus-5"
    assert dream.image_model == "google/gemini-3-pro-image"
    assert dream.image_path == "a.png"
    assert dream.status == "done"
    assert dream.discarded is False
    store.close()


def test_a_dream_row_exists_before_the_first_cloud_call(tmp_path):
    """A crash between create and finish must leave an honest record, not a hole."""
    store = open_store(tmp_path)

    dream = store.create_dream(
        created_at=1.0, graph_generated_at=0.0, person_count=1, term_count=1,
        edge_count=1, contradiction=False, guiding_question="Q", absorbed_persons=["p1"],
    )

    assert dream.status == "running"
    assert store.current_dream() is None  # a running dream is not on screen yet
    store.close()


def test_current_is_the_newest_visible_dream_and_history_is_the_rest(tmp_path):
    store = open_store(tmp_path)
    make_dream(store, at=1.0, sentence="erst")
    make_dream(store, at=2.0, sentence="dann")
    make_dream(store, at=3.0, sentence="jetzt")

    assert store.current_dream().sentence == "jetzt"
    # Oldest to newest (spec §6) — the strip is a time axis, not a stack.
    assert [d.sentence for d in store.history()] == ["erst", "dann"]
    store.close()


def test_discard_removes_the_dream_from_the_screen_and_from_the_strip(tmp_path):
    """Spec §7, Birk: one step, both places. An image pulled for embarrassment
    must not live on below."""
    store = open_store(tmp_path)
    make_dream(store, at=1.0, sentence="erst")
    bad = make_dream(store, at=2.0, sentence="peinlich")

    store.set_discarded(bad.id, True)

    assert store.current_dream().sentence == "erst"  # the previous one returns
    assert [d.sentence for d in store.history()] == []
    assert all(d.sentence != "peinlich" for d in store.visible_dreams())
    store.close()


def test_a_discarded_dream_from_the_middle_leaves_no_hole_in_the_strip(tmp_path):
    store = open_store(tmp_path)
    make_dream(store, at=1.0, sentence="a")
    middle = make_dream(store, at=2.0, sentence="b")
    make_dream(store, at=3.0, sentence="c")

    store.set_discarded(middle.id, True)

    assert store.current_dream().sentence == "c"
    assert [d.sentence for d in store.history()] == ["a"]
    store.close()


def test_a_discarded_dream_is_kept_never_deleted(tmp_path):
    """Spec §7: the row stays so the record stays honest; the display filters."""
    store = open_store(tmp_path)
    bad = make_dream(store, at=1.0, sentence="peinlich")

    store.set_discarded(bad.id, True)

    assert store.get_dream(bad.id).discarded is True
    assert store.get_dream(bad.id).sentence == "peinlich"
    assert len(store.all_dreams()) == 1
    store.close()


def test_discard_is_reversible(tmp_path):
    """Same logic as Tool 1's hide flag (T1§8, docs/operations.md: „Wieder
    einblenden ist derselbe Knopf"). An emergency exit that cannot be undone
    turns a misclick into a permanent loss."""
    store = open_store(tmp_path)
    dream = make_dream(store, at=1.0, sentence="doch nicht peinlich")

    store.set_discarded(dream.id, True)
    store.set_discarded(dream.id, False)

    assert store.current_dream().sentence == "doch nicht peinlich"
    store.close()


def test_a_failed_dream_never_reaches_the_screen(tmp_path):
    """Spec §8: „the current image stays up"."""
    store = open_store(tmp_path)
    make_dream(store, at=1.0, sentence="gut")
    broken = store.create_dream(
        created_at=2.0, graph_generated_at=1.5, person_count=1, term_count=1,
        edge_count=1, contradiction=False, guiding_question="Q", absorbed_persons=["p9"],
    )

    store.fail_dream(broken.id, "read timeout")

    assert store.current_dream().sentence == "gut"
    assert store.get_dream(broken.id).status == "failed"
    assert store.get_dream(broken.id).error == "read timeout"
    store.close()


def test_a_stage_2_failure_still_records_the_sentence(tmp_path):
    """Reproducibility (spec §5.3) does not depend on the run succeeding — the
    prompt that produced nothing is exactly the one worth being able to read."""
    store = open_store(tmp_path)
    dream = store.create_dream(
        created_at=1.0, graph_generated_at=0.0, person_count=6, term_count=9,
        edge_count=12, contradiction=True, guiding_question="Q", absorbed_persons=["p1"],
    )
    store.set_stage1(dream.id, prompt="S1", sentence="Der Satz kam durch.", model="claude-opus-5")
    store.set_stage2_prompt(dream.id, prompt="S2", model="google/gemini-3-pro-image")

    store.fail_dream(dream.id, "502 from the image model")

    stored = store.get_dream(dream.id)
    assert stored.sentence == "Der Satz kam durch."
    assert stored.stage1_prompt == "S1"
    assert stored.stage2_prompt == "S2"
    assert stored.status == "failed"
    store.close()


def test_last_started_at_counts_failed_and_discarded_dreams_too(tmp_path):
    """Spec §8: „Retry at the next trigger — never a retry storm." A failure
    that did not move the floor would retry on the very next poll."""
    store = open_store(tmp_path)
    make_dream(store, at=100.0)
    failed = store.create_dream(
        created_at=200.0, graph_generated_at=199.0, person_count=1, term_count=1,
        edge_count=1, contradiction=False, guiding_question="Q", absorbed_persons=["p2"],
    )
    store.fail_dream(failed.id, "timeout")

    assert store.last_started_at() == 200.0
    store.close()


def test_an_empty_store_has_no_last_start(tmp_path):
    store = open_store(tmp_path)

    assert store.last_started_at() is None
    assert store.current_dream() is None
    assert store.history() == []
    store.close()


def test_the_whole_strip_and_every_setting_survive_a_restart(tmp_path):
    """Spec §8 / T1§14 run 21: the screen comes back exactly as it stood."""
    store = open_store(tmp_path)
    for index in range(5):
        make_dream(store, at=float(index), sentence=f"traum {index}", image=f"d{index}.png")
    store.set_setting("fade_ms", "800")
    store.set_setting("typewriter", "1")
    store.set_setting("paused", "1")
    before = [d.id for d in store.visible_dreams()]
    store.close()  # the crash

    reopened = DreamStore.open(tmp_path / "dreams.sqlite3")

    assert [d.id for d in reopened.visible_dreams()] == before
    assert reopened.current_dream().sentence == "traum 4"
    assert len(reopened.history()) == 4
    assert reopened.get_setting("fade_ms", "1200") == "800"
    assert reopened.get_setting("typewriter", "0") == "1"
    assert reopened.get_setting("paused", "0") == "1"
    reopened.close()


def test_set_setting_default_never_overwrites_the_operator(tmp_path):
    """A restart must restore the operator's value, not config's start value —
    the same rule Tool 1 holds for min_mentions."""
    store = open_store(tmp_path)
    store.set_setting_default("fade_ms", "1200")
    store.set_setting("fade_ms", "400")

    store.set_setting_default("fade_ms", "1200")

    assert store.get_setting("fade_ms", "1200") == "400"
    store.close()


def test_ids_never_repeat_even_after_a_discard(tmp_path):
    """Image files are named after the dream id and are never overwritten
    (spec §5.2), so a reused id would be a silent overwrite."""
    store = open_store(tmp_path)
    first = make_dream(store, at=1.0)
    store.set_discarded(first.id, True)
    second = make_dream(store, at=2.0)

    assert first.id == "d1"
    assert second.id == "d2"
    store.close()
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_dream_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kg2.models'`

- [ ] **Step 3: Write `kg2/models.py`**

```python
"""Plain data carriers. Persistence lives in kg2.store.

Same shape and the same rule as `kg.models` (spec §3 permits reusing Tool 1's
dataclass shapes), but a separate file: Tool 2's store must never import Tool
1's, and sharing a module would be the first step towards it.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Dream:
    """One dream, and everything needed to explain it afterwards (spec §5.3)."""

    id: str
    created_at: float
    graph_generated_at: float | None = None
    person_count: int = 0
    term_count: int = 0
    edge_count: int = 0
    contradiction: bool = False
    guiding_question: str = ""
    # The person ids this dream condensed. Persisted because a restart has no
    # other way to know which interviews have already been dreamt — without it
    # the watcher would either fire once for all 40 or never fire again.
    absorbed_persons: list[str] = field(default_factory=list)
    stage1_prompt: str | None = None
    sentence: str | None = None
    stage2_prompt: str | None = None
    condense_model: str | None = None
    image_model: str | None = None
    image_path: str | None = None
    status: str = "running"  # running | done | failed
    error: str | None = None
    discarded: bool = False
```

- [ ] **Step 4: Write `kg2/db.py`**

```python
"""SQLite schema and connection handling for Tool 2's own store.

Deliberately a separate database file from Tool 1's (`dreams.sqlite3` next to
`kg.db`, and on a different machine entirely): spec §2 — Tool 2 never writes to
Tool 1's SQLite, and the surest way to keep that true is never to open it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS counters (
    name  TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS dream (
    id                 TEXT PRIMARY KEY,
    created_at         REAL NOT NULL,
    graph_generated_at REAL,
    person_count       INTEGER NOT NULL DEFAULT 0,
    term_count         INTEGER NOT NULL DEFAULT 0,
    edge_count         INTEGER NOT NULL DEFAULT 0,
    contradiction      INTEGER NOT NULL DEFAULT 0,
    guiding_question   TEXT NOT NULL DEFAULT '',
    absorbed_persons   TEXT NOT NULL DEFAULT '[]',
    stage1_prompt      TEXT,
    sentence           TEXT,
    stage2_prompt      TEXT,
    condense_model     TEXT,
    image_model        TEXT,
    image_path         TEXT,
    status             TEXT NOT NULL DEFAULT 'running',
    error              TEXT,
    discarded          INTEGER NOT NULL DEFAULT 0
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

- [ ] **Step 5: Write `kg2/store.py`**

```python
"""The only module that reads from or writes to Tool 2's SQLite.

Same discipline as `kg.store`, and for the same reason: FastAPI runs sync route
handlers in a threadpool while the watcher loop and the dream cycle write from
their own threads, and Python's `sqlite3` does not serialise statements against
a shared connection by itself. Every public method goes through one re-entrant
lock.

Smaller than Tool 1's store on purpose — there is one table with one row per
dream and no merging, no positions, no aliases.
"""

from __future__ import annotations

import functools
import json
import sqlite3
import threading
from pathlib import Path

from kg2.db import connect
from kg2.models import Dream


def _locked(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


def _row(row: sqlite3.Row) -> Dream:
    return Dream(
        id=row["id"],
        created_at=row["created_at"],
        graph_generated_at=row["graph_generated_at"],
        person_count=row["person_count"],
        term_count=row["term_count"],
        edge_count=row["edge_count"],
        contradiction=bool(row["contradiction"]),
        guiding_question=row["guiding_question"],
        absorbed_persons=json.loads(row["absorbed_persons"]),
        stage1_prompt=row["stage1_prompt"],
        sentence=row["sentence"],
        stage2_prompt=row["stage2_prompt"],
        condense_model=row["condense_model"],
        image_model=row["image_model"],
        image_path=row["image_path"],
        status=row["status"],
        error=row["error"],
        discarded=bool(row["discarded"]),
    )


class DreamStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._lock = threading.RLock()

    @classmethod
    def open(cls, path: Path) -> "DreamStore":
        return cls(connect(Path(path)))

    @_locked
    def close(self) -> None:
        self.conn.close()

    def _next_id(self) -> str:
        self.conn.execute(
            "INSERT INTO counters(name, value) VALUES ('dream', 1) "
            "ON CONFLICT(name) DO UPDATE SET value = value + 1"
        )
        row = self.conn.execute("SELECT value FROM counters WHERE name='dream'").fetchone()
        return f"d{row[0]}"

    # -- writing ------------------------------------------------------------

    @_locked
    def create_dream(
        self,
        *,
        created_at: float,
        graph_generated_at: float | None,
        person_count: int,
        term_count: int,
        edge_count: int,
        contradiction: bool,
        guiding_question: str,
        absorbed_persons: list[str],
    ) -> Dream:
        """Insert the row BEFORE the first cloud call.

        A crash or a kill between here and `finish_dream` then leaves a row
        stuck at `running` — visibly incomplete, which is the honest record —
        rather than leaving no trace that a dream was ever attempted.
        """
        dream_id = self._next_id()
        self.conn.execute(
            "INSERT INTO dream(id, created_at, graph_generated_at, person_count,"
            " term_count, edge_count, contradiction, guiding_question,"
            " absorbed_persons, status)"
            " VALUES (?,?,?,?,?,?,?,?,?, 'running')",
            (
                dream_id,
                created_at,
                graph_generated_at,
                person_count,
                term_count,
                edge_count,
                int(contradiction),
                guiding_question,
                json.dumps(sorted(absorbed_persons)),
            ),
        )
        self.conn.commit()
        return self.get_dream(dream_id)

    @_locked
    def set_stage1(self, dream_id: str, *, prompt: str, sentence: str, model: str) -> None:
        self.conn.execute(
            "UPDATE dream SET stage1_prompt=?, sentence=?, condense_model=? WHERE id=?",
            (prompt, sentence, model, dream_id),
        )
        self.conn.commit()

    @_locked
    def set_stage2_prompt(self, dream_id: str, *, prompt: str, model: str) -> None:
        """Recorded BEFORE the render, so a failed render still leaves the
        prompt that failed — which is the one worth reading (spec §5.3)."""
        self.conn.execute(
            "UPDATE dream SET stage2_prompt=?, image_model=? WHERE id=?",
            (prompt, model, dream_id),
        )
        self.conn.commit()

    @_locked
    def finish_dream(self, dream_id: str, *, image_path: str) -> None:
        self.conn.execute(
            "UPDATE dream SET image_path=?, status='done', error=NULL WHERE id=?",
            (image_path, dream_id),
        )
        self.conn.commit()

    @_locked
    def fail_dream(self, dream_id: str, error: str) -> None:
        self.conn.execute(
            "UPDATE dream SET status='failed', error=? WHERE id=?", (error, dream_id)
        )
        self.conn.commit()

    @_locked
    def set_discarded(self, dream_id: str, discarded: bool) -> None:
        """The row is never deleted (spec §7) — the record stays honest and the
        display filters. Reversible, like Tool 1's hide flag."""
        self.conn.execute(
            "UPDATE dream SET discarded=? WHERE id=?", (int(discarded), dream_id)
        )
        self.conn.commit()

    # -- reading ------------------------------------------------------------

    @_locked
    def get_dream(self, dream_id: str) -> Dream | None:
        row = self.conn.execute("SELECT * FROM dream WHERE id=?", (dream_id,)).fetchone()
        return _row(row) if row else None

    @_locked
    def all_dreams(self) -> list[Dream]:
        """Every row, whatever its status. The record, not the display."""
        rows = self.conn.execute("SELECT * FROM dream ORDER BY created_at, id").fetchall()
        return [_row(row) for row in rows]

    @_locked
    def visible_dreams(self) -> list[Dream]:
        """What screen B shows, oldest to newest: finished and not discarded.

        A `running` dream is not here — the screen keeps the previous image
        until the new one exists, which is what makes a 60 s generation
        invisible and a failure look like nothing at all (spec §8).
        """
        rows = self.conn.execute(
            "SELECT * FROM dream WHERE status='done' AND discarded=0 "
            "ORDER BY created_at, id"
        ).fetchall()
        return [_row(row) for row in rows]

    def current_dream(self) -> Dream | None:
        visible = self.visible_dreams()
        return visible[-1] if visible else None

    def history(self) -> list[Dream]:
        """The strip: every earlier dream, oldest first (spec §6)."""
        return self.visible_dreams()[:-1]

    @_locked
    def last_started_at(self) -> float | None:
        """The floor's reference point (spec §4.1: since the last dream STARTED).

        Spans every row, including `failed` and `discarded`: a failure that did
        not move the floor would be retried on the very next poll, which is the
        retry storm spec §8 forbids.
        """
        row = self.conn.execute("SELECT MAX(created_at) FROM dream").fetchone()
        return row[0]

    # -- settings -----------------------------------------------------------

    @_locked
    def get_setting(self, key: str, default: str) -> str:
        row = self.conn.execute("SELECT value FROM setting WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    @_locked
    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO setting(key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        self.conn.commit()

    @_locked
    def set_setting_default(self, key: str, value: str) -> None:
        """Seed a setting only if it has never been set — so a restart restores
        the operator's value, not config2.toml's start value."""
        self.conn.execute(
            "INSERT OR IGNORE INTO setting(key, value) VALUES (?,?)", (key, str(value))
        )
        self.conn.commit()
```

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_dream_store.py -v`
Expected: PASS (14 tests)

- [ ] **Step 7: Commit**

```bash
git add kg2/db.py kg2/models.py kg2/store.py tests/test_dream_store.py
git commit -m "feat: dream store — the strip, the record, and discard semantics"
```

---

### Task 5: The trigger — the §4.1 race, the floor, and collapsing

**Files:**
- Create: `kg2/trigger.py`
- Test: `tests/test_dream_trigger.py`

**Interfaces:**
- Consumes: Task 3 (the real graph fixture), Task 4 (`Dream`).
- Produces:
  - `kg2.trigger.absorbed_persons(graph: dict) -> set[str]`
  - `kg2.trigger.TriggerState` — frozen dataclass `(seen_persons: frozenset[str], last_started_at: float | None)` with `with_dream_started(at: float) -> TriggerState` and `with_absorbed(ids) -> TriggerState`
  - `kg2.trigger.Decision` — frozen dataclass `(fire: bool, reason: str, absorbed: frozenset[str], started_at: float | None)`
  - `kg2.trigger.evaluate(state, graph, now, min_interval_s, force=False) -> Decision`
  - `kg2.trigger.resume_state(dreams: Sequence[Dream]) -> TriggerState`

**THIS IS THE DEFECT MOST LIKELY TO SHIP.** Read spec §4.1 before writing a line.

Tool 1's timing, verified against `kg/core.py:150-199` on 2026-08-25:

1. `_open()` — a photo arrives, the person node is created and **`broadcast_graph` fires immediately**. The person is in `graph.json` **with no edges**. Its terms do not exist yet.
2. `_process()` runs the pipeline in a thread — settle, transcribe, extract, embed, merge. **Seconds to tens of seconds.**
3. `_close()` → after the pipeline, `broadcast_graph()` fires again (`kg/core.py:198`) — now the new person has edges.

A dream triggered at step 1 would condense a graph the interviewee has contributed nothing to yet, and the visitor standing in front of screen B would watch their own interview *not* arrive. Because A and B stand side by side, that failure is visible to everyone in the room.

So the rule, and it is the whole task: **a person node counts as absorbed only once it has at least one edge.**

Three further properties that are each one line of code and each a silent bug if missed:

- **The floor is a delay, not a drop.** When `evaluate` declines because of the floor, the seen set must be returned *unchanged*, so the pending interview is still pending at the next poll and fires the moment the floor expires. Updating it there would silently swallow the dream forever.
- **The seen set is monotone.** Ids are only ever added. The operator hiding a person after their dream must not make them "new" again when unhidden.
- **The seen set is adopted only on success.** `Decision.started_at` is adopted whatever happens (so a failure cannot retry-storm — §8), but `Decision.absorbed` is adopted only when the cycle actually produced a dream, so a failed dream's material is retried at the next trigger, exactly as §8 says.

- [ ] **Step 1: Write the failing test**

`tests/test_dream_trigger.py`:

```python
"""Spec §4.1 — when a dream is due, and the race that makes it hard.

Tool 1 broadcasts the graph TWICE per interview: once at the photo, when the
person node exists with no edges (`kg/core.py:156`), and once after the
pipeline, when the terms are in (`kg/core.py:198`). Only the second one means
„absorbed". Every test below exists because the first one must not fire a dream.
"""

from __future__ import annotations

import copy

from kg2.models import Dream
from kg2.trigger import TriggerState, absorbed_persons, evaluate, resume_state

EMPTY = TriggerState(frozenset(), None)


def graph(persons, edges=(), *, hidden_persons=(), generated_at=1000.0) -> dict:
    """A minimal graph.json in Tool 1's real shape. Terms only where edges need
    them — the trigger never looks at terms."""
    nodes = [
        {
            "id": pid,
            "type": "person",
            "portrait": None,
            "created_at": 1.0,
            "hidden": pid in hidden_persons,
            "x": None,
            "y": None,
        }
        for pid in persons
    ]
    targets = sorted({target for _, target in edges})
    nodes += [
        {
            "id": tid,
            "type": "term",
            "label": tid,
            "mentions": 1,
            "created_at": 2.0,
            "hidden": False,
            "x": None,
            "y": None,
        }
        for tid in targets
    ]
    return {
        "version": 1,
        "generated_at": generated_at,
        "min_mentions": 1,
        "nodes": nodes,
        "edges": [
            {"id": f"e{i}", "source": s, "target": t} for i, (s, t) in enumerate(edges, 1)
        ],
        "quotes": [],
    }


# -- the race itself --------------------------------------------------------


def test_a_person_node_without_edges_is_not_absorbed():
    """Tool 1 step 1: the photo landed, the pipeline has not run. THE bug."""
    assert absorbed_persons(graph(["p1"])) == set()


def test_a_person_node_with_an_edge_is_absorbed():
    """Tool 1 step 3: `broadcast_graph` after the pipeline."""
    assert absorbed_persons(graph(["p1"], [("p1", "t1")])) == {"p1"}


def test_a_bare_person_node_never_fires_a_dream():
    decision = evaluate(EMPTY, graph(["p1"]), now=5000.0, min_interval_s=240)

    assert decision.fire is False
    assert decision.reason == "nothing new"


def test_the_same_person_fires_once_the_pipeline_has_run():
    """The two polls a real interview produces, in order."""
    state = EMPTY
    at_photo = evaluate(state, graph(["p1"]), now=5000.0, min_interval_s=240)
    assert at_photo.fire is False

    after_pipeline = evaluate(
        state, graph(["p1"], [("p1", "t1")]), now=5030.0, min_interval_s=240
    )

    assert after_pipeline.fire is True
    assert after_pipeline.absorbed == frozenset({"p1"})
    assert after_pipeline.started_at == 5030.0


def test_a_new_bare_person_beside_an_absorbed_one_does_not_fire_again():
    """Person 2's photo lands while person 1's dream is done. Nothing new has
    been SAID yet, so nothing may happen."""
    state = TriggerState(frozenset({"p1"}), 5000.0)

    decision = evaluate(
        state, graph(["p1", "p2"], [("p1", "t1")]), now=6000.0, min_interval_s=240
    )

    assert decision.fire is False


# -- the floor --------------------------------------------------------------


def test_the_floor_blocks_a_second_dream():
    state = TriggerState(frozenset({"p1"}), 5000.0)

    decision = evaluate(
        state, graph(["p1", "p2"], [("p1", "t1"), ("p2", "t2")]), now=5100.0, min_interval_s=240
    )

    assert decision.fire is False
    assert decision.reason == "floor"


def test_an_interview_that_lands_inside_the_floor_is_not_lost():
    """The floor is a DELAY, not a drop. If `evaluate` folded p2 into the seen
    set while declining, p2's dream would never happen at all."""
    state = TriggerState(frozenset({"p1"}), 5000.0)
    full = graph(["p1", "p2"], [("p1", "t1"), ("p2", "t2")])

    blocked = evaluate(state, full, now=5100.0, min_interval_s=240)
    assert blocked.fire is False

    later = evaluate(state, full, now=5241.0, min_interval_s=240)

    assert later.fire is True
    assert later.absorbed == frozenset({"p1", "p2"})


def test_the_floor_is_measured_from_the_start_of_the_last_dream():
    state = TriggerState(frozenset({"p1"}), 5000.0)
    full = graph(["p1", "p2"], [("p1", "t1"), ("p2", "t2")])

    assert evaluate(state, full, now=5239.0, min_interval_s=240).fire is False
    assert evaluate(state, full, now=5240.0, min_interval_s=240).fire is True


def test_the_first_dream_of_the_day_has_no_floor():
    decision = evaluate(EMPTY, graph(["p1"], [("p1", "t1")]), now=1.0, min_interval_s=240)

    assert decision.fire is True


# -- collapsing -------------------------------------------------------------


def test_several_interviews_inside_the_floor_collapse_into_one_dream():
    """Spec §4.1: the dream is of the whole graph, not of one person, so there
    is nothing to queue."""
    state = TriggerState(frozenset({"p1"}), 5000.0)
    three_more = graph(
        ["p1", "p2", "p3", "p4"],
        [("p1", "t1"), ("p2", "t2"), ("p3", "t3"), ("p4", "t4")],
    )

    decision = evaluate(state, three_more, now=5300.0, min_interval_s=240)

    assert decision.fire is True
    assert decision.absorbed == frozenset({"p1", "p2", "p3", "p4"})


# -- silence ----------------------------------------------------------------


def test_silence_never_fires_a_dream():
    """Spec §4: nothing during silence. A dream appearing while nothing
    happened on the left exposes the station as a random generator."""
    state = TriggerState(frozenset({"p1", "p2"}), 5000.0)
    unchanged = graph(["p1", "p2"], [("p1", "t1"), ("p2", "t2")])

    for now in (5300.0, 9000.0, 50000.0):
        assert evaluate(state, unchanged, now=now, min_interval_s=240).fire is False


def test_an_empty_graph_never_fires():
    assert evaluate(EMPTY, graph([]), now=1.0, min_interval_s=240).fire is False


# -- hidden nodes -----------------------------------------------------------


def test_a_hidden_person_does_not_fire_a_dream():
    """The operator pulled them from the wall (T1§8); they must not drive the
    dream either, and §5.1 already excludes them from its material."""
    hidden = graph(["p1"], [("p1", "t1")], hidden_persons=["p1"])

    assert absorbed_persons(hidden) == set()
    assert evaluate(EMPTY, hidden, now=1.0, min_interval_s=240).fire is False


def test_hiding_and_unhiding_a_person_afterwards_never_fires_a_second_dream():
    """The seen set is monotone. Without that, hide-then-unhide reads as a new
    absorption and dreams twice on the same material."""
    state = TriggerState(frozenset({"p1"}), 5000.0)
    hidden = graph(["p1"], [("p1", "t1")], hidden_persons=["p1"])
    shown = graph(["p1"], [("p1", "t1")])

    assert evaluate(state, hidden, now=9000.0, min_interval_s=240).fire is False
    assert evaluate(state, shown, now=9000.0, min_interval_s=240).fire is False


# -- „Dream now" ------------------------------------------------------------


def test_force_ignores_the_floor():
    """Spec §7: needed the moment someone from the organiser stands in front of
    the screen and wants to see how it works."""
    state = TriggerState(frozenset({"p1"}), 5000.0)

    decision = evaluate(
        state, graph(["p1"], [("p1", "t1")]), now=5001.0, min_interval_s=240, force=True
    )

    assert decision.fire is True
    assert decision.reason == "forced"


def test_force_fires_even_in_total_silence():
    state = TriggerState(frozenset({"p1"}), 5000.0)

    decision = evaluate(
        state, graph(["p1"], [("p1", "t1")]), now=9000.0, min_interval_s=240, force=True
    )

    assert decision.fire is True
    assert decision.absorbed == frozenset({"p1"})


def test_force_on_an_empty_graph_still_fires():
    """A forced dream of an empty graph is a legitimate thing to ask for at
    9 a.m. — the cycle decides what to make of it, not the trigger."""
    assert evaluate(EMPTY, graph([]), now=1.0, min_interval_s=240, force=True).fire is True


# -- state transitions ------------------------------------------------------


def test_the_floor_stamp_is_adopted_separately_from_the_seen_set():
    """Spec §8: a failed dream must still move the floor (no retry storm) while
    leaving its material unconsumed (retry at the next trigger)."""
    state = TriggerState(frozenset(), None)
    decision = evaluate(state, graph(["p1"], [("p1", "t1")]), now=100.0, min_interval_s=240)

    after_failure = state.with_dream_started(decision.started_at)
    assert after_failure.seen_persons == frozenset()
    assert after_failure.last_started_at == 100.0

    after_success = after_failure.with_absorbed(decision.absorbed)
    assert after_success.seen_persons == frozenset({"p1"})
    assert after_success.last_started_at == 100.0


def test_a_failed_dream_retries_the_same_material_at_the_next_trigger():
    state = TriggerState(frozenset(), None)
    material = graph(["p1"], [("p1", "t1")])

    first = evaluate(state, material, now=100.0, min_interval_s=240)
    state = state.with_dream_started(first.started_at)  # failure: absorbed NOT adopted

    retry = evaluate(state, material, now=341.0, min_interval_s=240)

    assert retry.fire is True
    assert retry.absorbed == frozenset({"p1"})


def test_a_failed_dream_does_not_retry_before_the_floor():
    state = TriggerState(frozenset(), None).with_dream_started(100.0)

    assert evaluate(
        state, graph(["p1"], [("p1", "t1")]), now=101.0, min_interval_s=240
    ).fire is False


# -- restart ----------------------------------------------------------------


def dream(dream_id, at, persons, status="done", discarded=False) -> Dream:
    return Dream(
        id=dream_id,
        created_at=at,
        absorbed_persons=list(persons),
        status=status,
        discarded=discarded,
        sentence="x",
        image_path=f"{dream_id}.png",
    )


def test_a_restart_does_not_re_dream_everything_already_dreamt():
    state = resume_state([dream("d1", 100.0, ["p1"]), dream("d2", 400.0, ["p1", "p2"])])

    assert state.seen_persons == frozenset({"p1", "p2"})
    assert state.last_started_at == 400.0


def test_a_restart_keeps_the_floor_of_a_failed_dream():
    state = resume_state([dream("d1", 100.0, ["p1"]), dream("d2", 400.0, ["p2"], status="failed")])

    assert state.seen_persons == frozenset({"p1"})  # p2 was never condensed
    assert state.last_started_at == 400.0


def test_a_restart_counts_a_discarded_dream_as_dreamt():
    """Discard removes it from the SCREEN (spec §7). It was still dreamt, and
    re-dreaming the same material would just produce the same embarrassment."""
    state = resume_state([dream("d1", 100.0, ["p1"], discarded=True)])

    assert state.seen_persons == frozenset({"p1"})


def test_a_restart_on_an_empty_store_starts_from_nothing():
    assert resume_state([]) == TriggerState(frozenset(), None)


def test_a_restart_ignores_a_dream_left_running_by_the_crash():
    state = resume_state([dream("d1", 100.0, ["p1"], status="running")])

    assert state.seen_persons == frozenset()
    assert state.last_started_at == 100.0  # it did start, so the floor applies


# -- against the real thing -------------------------------------------------


def test_every_person_in_the_real_replay_graph_is_absorbed(real_graph):
    """Spec §11: contract against the real artefact, never a hand-written one.
    All 60 interviews in run 19c ran the full pipeline, so all 60 have edges."""
    assert len(absorbed_persons(real_graph)) == 60


def test_a_bare_person_appended_to_the_real_graph_is_not_absorbed(real_graph):
    """The §4.1 race on real data: exactly what Tool 1 publishes at the photo."""
    graph_with_photo = copy.deepcopy(real_graph)
    graph_with_photo["nodes"].append(
        {
            "id": "p61",
            "type": "person",
            "portrait": "/media/portraits/p61.jpg",
            "created_at": 1700020000.0,
            "hidden": False,
            "x": None,
            "y": None,
        }
    )

    assert "p61" not in absorbed_persons(graph_with_photo)

    state = TriggerState(frozenset(absorbed_persons(real_graph)), 1700019000.0)
    assert evaluate(
        state, graph_with_photo, now=1700020000.0, min_interval_s=240
    ).fire is False


def test_the_real_graph_fires_once_the_appended_person_has_an_edge(real_graph):
    graph_after_pipeline = copy.deepcopy(real_graph)
    graph_after_pipeline["nodes"].append(
        {
            "id": "p61",
            "type": "person",
            "portrait": None,
            "created_at": 1700020000.0,
            "hidden": False,
            "x": None,
            "y": None,
        }
    )
    graph_after_pipeline["edges"].append({"id": "e999", "source": "p61", "target": "t9"})

    state = TriggerState(frozenset(absorbed_persons(real_graph)), 1700019000.0)
    decision = evaluate(state, graph_after_pipeline, now=1700020000.0, min_interval_s=240)

    assert decision.fire is True
    assert "p61" in decision.absorbed
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_dream_trigger.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kg2.trigger'`

- [ ] **Step 3: Implement `kg2/trigger.py`**

```python
"""When a dream is due. Pure functions over a graph payload — no I/O, no store.

This module exists because of one race (spec §4.1), and it is worth stating in
full because getting it wrong is invisible until an exhibition day.

Tool 1 publishes `graph.json` twice per interview:

  1. at the photo (`kg/core.py:156`) — the person node exists, **with no
     edges**. The interview has not been transcribed, let alone extracted.
  2. after the pipeline (`kg/core.py:198`) — the person now has edges to their
     terms. Seconds to tens of seconds later.

A dream triggered by (1) would condense a graph the interviewee has contributed
nothing to yet — and because screens A and B stand side by side, the visitor
would watch their own interview *not* arrive. So the only signal Tool 2 trusts
is structural: **a person node that has at least one edge**.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass


def absorbed_persons(graph: dict | None) -> set[str]:
    """Person ids whose interview Tool 1 has finished processing.

    „Has at least one edge" is the whole test. It is a property of the data, so
    it needs no access to Tool 1's internals, survives a Tool 1 restart, and
    cannot drift out of step with the pipeline the way a timer would.

    Hidden persons are excluded: the operator pulled them from the wall (T1§8)
    and spec §5.1 already excludes them from the dream's material, so letting
    one trigger a dream it is not in would be incoherent.
    """
    if not graph:
        return set()
    persons = {
        node["id"]
        for node in graph.get("nodes", ())
        if node.get("type") == "person" and not node.get("hidden")
    }
    with_edges = {edge["source"] for edge in graph.get("edges", ())}
    return persons & with_edges


@dataclass(frozen=True)
class TriggerState:
    """What the watcher remembers between polls.

    `seen_persons` only ever grows (see `with_absorbed`). That monotonicity is
    what makes hiding and unhiding a person afterwards a no-op rather than a
    second dream on the same material.
    """

    seen_persons: frozenset[str] = frozenset()
    last_started_at: float | None = None

    def with_dream_started(self, at: float | None) -> "TriggerState":
        """Adopt the floor stamp. Done whatever the cycle's outcome is — a
        failed dream must still space out its retry (spec §8)."""
        return TriggerState(self.seen_persons, at)

    def with_absorbed(self, ids: Iterable[str]) -> "TriggerState":
        """Consume material. Done ONLY after a dream actually succeeded, so a
        failure retries the same interviews at the next trigger (spec §8)."""
        return TriggerState(self.seen_persons | frozenset(ids), self.last_started_at)


@dataclass(frozen=True)
class Decision:
    fire: bool
    reason: str
    #: What a SUCCESSFUL dream would consume. Adopted by the caller only then.
    absorbed: frozenset[str] = frozenset()
    #: The floor stamp to adopt regardless of outcome. None when not firing.
    started_at: float | None = None


def evaluate(
    state: TriggerState,
    graph: dict | None,
    now: float,
    min_interval_s: float,
    force: bool = False,
) -> Decision:
    """Is a dream due? Pure; the caller owns the state and the side effects.

    `force` is the operator's „Dream now" (spec §7): it ignores the floor and
    ignores silence, because its whole purpose is to demonstrate the station on
    demand.
    """
    absorbed = frozenset(absorbed_persons(graph))

    if force:
        return Decision(True, "forced", absorbed, now)

    fresh = absorbed - state.seen_persons
    if not fresh:
        # Either silence, or a person node that is still only a photo. Both are
        # correctly nothing: no new material has been said.
        return Decision(False, "nothing new")

    if state.last_started_at is not None and now - state.last_started_at < min_interval_s:
        # THE FLOOR IS A DELAY, NOT A DROP. `state` is returned untouched and no
        # `absorbed` is reported, so the same fresh persons are still fresh at
        # the next poll and the dream fires the moment the floor expires. Folding
        # them in here would swallow the interview silently and forever — and
        # nothing on screen would ever say so.
        return Decision(False, "floor")

    # Everything absorbed so far, not just `fresh`: the dream is of the whole
    # graph, so several interviews inside the floor collapse into one (spec §4.1)
    # and there is nothing to queue.
    return Decision(True, "absorbed", absorbed, now)


def resume_state(dreams: Sequence) -> TriggerState:
    """Rebuild the watcher's memory from the store after a restart (spec §8).

    Takes rows, not a store, so it stays pure and testable.

    * A `done` dream consumed its material — discarded or not. Discard removes
      it from the SCREEN (spec §7); re-dreaming the same graph would only
      reproduce whatever was discarded.
    * A `failed` or `running` dream consumed nothing, so its persons stay fresh
      and are retried — but it did START, so it still counts for the floor.
    """
    seen: set[str] = set()
    last: float | None = None
    for dream in dreams:
        last = dream.created_at if last is None else max(last, dream.created_at)
        if dream.status == "done":
            seen |= set(dream.absorbed_persons)
    return TriggerState(frozenset(seen), last)
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_dream_trigger.py -v`
Expected: PASS (27 tests)

- [ ] **Step 5: Commit**

```bash
git add kg2/trigger.py tests/test_dream_trigger.py
git commit -m "feat: the dream trigger — a person with edges, never a bare person node

Spec 4.1's race, which is the defect most likely to ship: Tool 1 broadcasts the
graph at the photo AND after the pipeline. Only the second means absorbed. Also
pins the floor as a delay rather than a drop, collapsing, and monotone seen ids."
```

---

### Task 6: Weighting — graph to dream material

**Files:**
- Create: `kg2/weighting.py`
- Test: `tests/test_dream_weighting.py`

**Interfaces:**
- Consumes: Task 3 (the real graph fixture).
- Produces:
  - `kg2.weighting.TermWeight` — frozen dataclass `(label: str, mentions: int)`
  - `kg2.weighting.Material` — frozen dataclass `(person_count, term_count, edge_count, generated_at, shared: list[TermWeight], marginal: list[TermWeight], quotes: list[str])`
  - `kg2.weighting.build_material(graph: dict) -> Material`
  - `kg2.weighting.render_material(material: Material) -> str` (the German prompt block)
  - `kg2.weighting.contradiction_enabled(material, threshold: int) -> bool`

Spec §5.1, four rules, each with a reason that must survive into the code:

- **Weight by structure.** `mentions` and the edges already exist in `graph.json`; frequently mentioned terms enter as dominant, single mentions enter as marginal detail **explicitly labelled as such**, so the model can place them as a detail rather than a theme.
- **Quotes are included.** They exist in the payload for exactly this (T1§11 stores them for Tool 2's benefit even though the wall never shows them).
- **Hidden nodes are excluded.** The operator's emergency exit on the wall must not reappear in the dream.
- **`min_mentions` is NOT applied.** That dial is the wall's legibility filter, not a statement about what was said.

One consequence the spec does not spell out but the code must get right: **`mentions` in the payload counts edges from hidden persons too.** If the operator hides a person, that person's contribution has to vanish from the dream — so mentions are recomputed from the surviving edges, never read off the node.

- [ ] **Step 1: Write the failing test**

`tests/test_dream_weighting.py`:

```python
"""Spec §5.1 — what goes into stage 1, and what deliberately does not."""

from __future__ import annotations

import copy

from kg2.weighting import (
    Material,
    build_material,
    contradiction_enabled,
    render_material,
)


def graph(nodes, edges, quotes=(), *, min_mentions=1, generated_at=1000.0) -> dict:
    return {
        "version": 1,
        "generated_at": generated_at,
        "min_mentions": min_mentions,
        "nodes": nodes,
        "edges": [
            {"id": f"e{i}", "source": s, "target": t} for i, (s, t) in enumerate(edges, 1)
        ],
        "quotes": [
            {"id": f"q{i}", "person_id": p, "text": text}
            for i, (p, text) in enumerate(quotes, 1)
        ],
    }


def person(pid, hidden=False) -> dict:
    return {
        "id": pid, "type": "person", "portrait": None, "created_at": 1.0,
        "hidden": hidden, "x": None, "y": None,
    }


def term(tid, label, mentions, hidden=False) -> dict:
    return {
        "id": tid, "type": "term", "label": label, "mentions": mentions,
        "created_at": 2.0, "hidden": hidden, "x": None, "y": None,
    }


def test_shared_terms_are_ordered_by_how_many_people_said_them():
    material = build_material(
        graph(
            [person("p1"), person("p2"), person("p3"),
             term("t1", "Weiterbauen im Bestand", 3), term("t2", "Holzbau", 2)],
            [("p1", "t1"), ("p2", "t1"), ("p3", "t1"), ("p1", "t2"), ("p2", "t2")],
        )
    )

    assert [(w.label, w.mentions) for w in material.shared] == [
        ("Weiterbauen im Bestand", 3),
        ("Holzbau", 2),
    ]
    assert material.marginal == []


def test_a_term_said_by_one_person_is_marginal_not_shared():
    material = build_material(
        graph(
            [person("p1"), person("p2"),
             term("t1", "Holzbau", 2), term("t2", "Sickerfähige Beläge", 1)],
            [("p1", "t1"), ("p2", "t1"), ("p1", "t2")],
        )
    )

    assert [w.label for w in material.shared] == ["Holzbau"]
    assert [w.label for w in material.marginal] == ["Sickerfähige Beläge"]


def test_min_mentions_is_never_applied():
    """Spec §5.1: that dial is the wall's legibility filter, not a statement
    about what was said. The dream reads everything."""
    material = build_material(
        graph(
            [person("p1"), term("t1", "Sickerfähige Beläge", 1)],
            [("p1", "t1")],
            min_mentions=3,
        )
    )

    assert [w.label for w in material.marginal] == ["Sickerfähige Beläge"]


def test_a_hidden_term_is_excluded():
    """T1§8's emergency exit: something pulled from the wall must not reappear
    in the dream."""
    material = build_material(
        graph(
            [person("p1"), person("p2"),
             term("t1", "Holzbau", 2), term("t2", "Peinlich", 2, hidden=True)],
            [("p1", "t1"), ("p2", "t1"), ("p1", "t2"), ("p2", "t2")],
        )
    )

    labels = [w.label for w in material.shared + material.marginal]
    assert labels == ["Holzbau"]
    assert material.term_count == 1


def test_a_hidden_person_is_excluded_and_their_mentions_do_not_count():
    """The payload's `mentions` counts edges from hidden persons too. Reading it
    off the node would leave a hidden visitor's voice in the dream."""
    material = build_material(
        graph(
            [person("p1"), person("p2", hidden=True), term("t1", "Holzbau", 2)],
            [("p1", "t1"), ("p2", "t1")],
        )
    )

    assert material.person_count == 1
    # Recomputed from the surviving edges: 1, not the payload's 2.
    assert [(w.label, w.mentions) for w in material.marginal] == [("Holzbau", 1)]
    assert material.shared == []


def test_a_term_left_with_no_speakers_disappears_entirely():
    material = build_material(
        graph(
            [person("p1", hidden=True), term("t1", "Holzbau", 1)],
            [("p1", "t1")],
        )
    )

    assert material.shared == []
    assert material.marginal == []
    assert material.term_count == 0
    assert material.edge_count == 0


def test_quotes_are_included():
    """T1§11 stores them for Tool 2's benefit even though the wall never shows
    them (spec §5.1)."""
    material = build_material(
        graph(
            [person("p1"), term("t1", "Holzbau", 1)],
            [("p1", "t1")],
            [("p1", "Wir bauen zu viel Neues.")],
        )
    )

    assert material.quotes == ["Wir bauen zu viel Neues."]


def test_a_hidden_persons_quote_is_excluded():
    material = build_material(
        graph(
            [person("p1"), person("p2", hidden=True), term("t1", "Holzbau", 2)],
            [("p1", "t1"), ("p2", "t1")],
            [("p1", "bleibt"), ("p2", "verschwindet")],
        )
    )

    assert material.quotes == ["bleibt"]


def test_counts_describe_what_the_dream_actually_saw():
    material = build_material(
        graph(
            [person("p1"), person("p2"), term("t1", "a", 2), term("t2", "b", 1)],
            [("p1", "t1"), ("p2", "t1"), ("p1", "t2")],
            generated_at=1700000000.0,
        )
    )

    assert material == Material(
        person_count=2,
        term_count=2,
        edge_count=3,
        generated_at=1700000000.0,
        shared=material.shared,
        marginal=material.marginal,
        quotes=[],
    )


def test_an_empty_graph_produces_empty_material():
    material = build_material(graph([], []))

    assert material.person_count == 0
    assert material.shared == []
    assert material.marginal == []
    assert material.quotes == []


def test_render_labels_the_marginal_terms_as_detail_not_theme():
    """Spec §5.1: single mentions enter „explicitly labelled as such so the
    model can place them as a detail rather than a theme"."""
    material = build_material(
        graph(
            [person("p1"), person("p2"),
             term("t1", "Holzbau", 2), term("t2", "Sickerfähige Beläge", 1)],
            [("p1", "t1"), ("p2", "t1"), ("p1", "t2")],
            [("p1", "Wir bauen zu viel Neues.")],
        )
    )

    text = render_material(material)

    assert "Holzbau" in text
    assert "2×" in text
    assert "Sickerfähige Beläge" in text
    # The label is what makes the weighting legible to the model.
    assert "Detail" in text
    assert "Randnotiz" in text
    assert "Wir bauen zu viel Neues." in text


def test_render_omits_a_section_that_has_nothing_in_it():
    """An empty heading reads to the model as „there were no quotes", which is
    true but noisy; leaving it out is the same statement, shorter."""
    material = build_material(
        graph([person("p1"), person("p2"), term("t1", "Holzbau", 2)],
              [("p1", "t1"), ("p2", "t1")])
    )

    text = render_material(material)

    assert "Randnotiz" not in text
    assert "Stimmen" not in text


def test_the_contradiction_threshold_is_a_person_count():
    """Spec §5.1: with three interviews there are no real oppositions and the
    model would invent one."""
    small = build_material(graph([person(f"p{i}") for i in range(3)], []))
    large = build_material(
        graph(
            [person(f"p{i}") for i in range(8)] + [term("t1", "a", 8)],
            [(f"p{i}", "t1") for i in range(8)],
        )
    )

    assert contradiction_enabled(small, threshold=6) is False
    assert contradiction_enabled(large, threshold=6) is True


def test_the_threshold_counts_visible_persons_only():
    material = build_material(
        graph(
            [person(f"p{i}", hidden=i >= 4) for i in range(8)] + [term("t1", "a", 8)],
            [(f"p{i}", "t1") for i in range(8)],
        )
    )

    assert material.person_count == 4
    assert contradiction_enabled(material, threshold=6) is False


# -- against the real thing -------------------------------------------------


def test_the_real_replay_graph_yields_realistic_material(real_graph):
    """Spec §11: contract against a real artefact. Run 19c has a long tail of
    single mentions — the shape the weighting exists to handle."""
    material = build_material(real_graph)

    assert material.person_count == 60
    assert material.term_count == 163
    assert material.edge_count == 267
    assert len(material.quotes) == 117
    assert len(material.shared) + len(material.marginal) == 163
    # 114 of 163 terms were said by exactly one person (docs/operations.md).
    assert len(material.marginal) == 114
    assert material.shared[0].mentions == 7


def test_the_real_graph_renders_into_a_prompt_of_workable_size(real_graph):
    """~50 persons is the ceiling (T1§2), so this stays bounded — and nothing
    is silently truncated to make it so."""
    text = render_material(build_material(real_graph))

    assert "Scheinbeteiligung pro forma" in text  # the most-mentioned term
    assert 5_000 < len(text) < 60_000


def test_hiding_a_person_in_the_real_graph_removes_their_voice(real_graph):
    graph_with_hidden = copy.deepcopy(real_graph)
    for node in graph_with_hidden["nodes"]:
        if node["id"] == "p1":
            node["hidden"] = True

    material = build_material(graph_with_hidden)
    quotes_of_p1 = [q["text"] for q in real_graph["quotes"] if q["person_id"] == "p1"]

    assert material.person_count == 59
    assert all(quote not in material.quotes for quote in quotes_of_p1)
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_dream_weighting.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kg2.weighting'`

- [ ] **Step 3: Implement `kg2/weighting.py`**

```python
"""graph.json -> the material stage 1 reasons over (spec §5.1).

Four rules, each with a reason that has to survive a later edit:

* **Weight by structure.** The numbers already exist in the payload, so nothing
  is computed on Tool 1's side. Frequently mentioned terms are dominant; single
  mentions are marginal detail, and are LABELLED as such in the rendered block
  so the model can place them as a detail rather than as a theme.
* **Quotes are in.** They are in `graph.json` for exactly this reason (T1§11
  stores them for Tool 2's benefit even though the wall never renders them).
* **Hidden nodes are out.** `hidden: true` is the operator's emergency exit on
  the wall (T1§8); something pulled from the wall must not reappear in the dream.
* **`min_mentions` is NOT applied.** That dial is the wall's legibility filter,
  not a statement about what was said. The dream reads everything and the
  weighting handles prominence.

One thing the spec does not spell out and the code must: the payload's
`mentions` counts edges from hidden persons too, so it is RECOMPUTED here from
the surviving edges. Reading it off the node would leave a hidden visitor's
voice weighting the dream they were pulled out of.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TermWeight:
    label: str
    mentions: int


@dataclass(frozen=True)
class Material:
    person_count: int
    term_count: int
    edge_count: int
    generated_at: float | None
    #: Said by two or more people, most-said first.
    shared: list[TermWeight]
    #: Said by exactly one person. Detail, not theme.
    marginal: list[TermWeight]
    quotes: list[str]


def build_material(graph: dict | None) -> Material:
    if not graph:
        return Material(0, 0, 0, None, [], [], [])

    nodes = graph.get("nodes", ())
    persons = {n["id"] for n in nodes if n.get("type") == "person" and not n.get("hidden")}
    terms = {
        n["id"]: n.get("label", "")
        for n in nodes
        if n.get("type") == "term" and not n.get("hidden")
    }

    counts: dict[str, int] = {}
    edge_count = 0
    for edge in graph.get("edges", ()):
        if edge["source"] in persons and edge["target"] in terms:
            counts[edge["target"]] = counts.get(edge["target"], 0) + 1
            edge_count += 1

    weights = [TermWeight(terms[tid], count) for tid, count in counts.items()]
    # Descending by count, then by label: two runs over the same graph must
    # produce the same prompt, or the record in spec §5.3 explains nothing.
    weights.sort(key=lambda w: (-w.mentions, w.label))

    quotes = [
        quote["text"]
        for quote in graph.get("quotes", ())
        if quote.get("person_id") in persons
    ]

    return Material(
        person_count=len(persons),
        term_count=len(weights),
        edge_count=edge_count,
        generated_at=graph.get("generated_at"),
        shared=[w for w in weights if w.mentions >= 2],
        marginal=[w for w in weights if w.mentions == 1],
        quotes=quotes,
    )


def render_material(material: Material) -> str:
    """The German block that goes into stage 1's user message.

    Nothing is truncated. At Tool 1's documented ceiling of ~50 persons (T1§2)
    this stays comfortably inside the model's window, and a silent cap would
    make the dream quietly stop reading the day's later interviews — the one
    failure this station cannot afford, because the strip is what makes drift
    visible.
    """
    blocks: list[str] = []

    if material.shared:
        lines = "\n".join(f"  {w.mentions}× {w.label}" for w in material.shared)
        blocks.append(
            "GETEILTE BEGRIFFE — die Zahl sagt, wie viele Menschen sie genannt "
            "haben. Was oft genannt wurde, beherrscht das Bild:\n" + lines
        )

    if material.marginal:
        lines = "\n".join(f"  {w.label}" for w in material.marginal)
        blocks.append(
            "RANDNOTIZEN — jede davon hat genau ein Mensch gesagt. Das sind "
            "Detail und Beiwerk, nicht Thema. Sie dürfen im Bild vorkommen, "
            "aber klein und am Rand:\n" + lines
        )

    if material.quotes:
        # Single-quoted f-string: the German quotation marks are literal text,
        # and a double-quoted one would end at the closing „ ".
        lines = "\n".join(f'  „{quote}"' for quote in material.quotes)
        blocks.append("STIMMEN aus den Interviews, wörtlich:\n" + lines)

    header = (
        f"Der Graph umfasst {material.person_count} Menschen, "
        f"{material.term_count} Begriffe und {material.edge_count} Verbindungen."
    )
    return "\n\n".join([header, *blocks])


def contradiction_enabled(material: Material, threshold: int) -> bool:
    """Spec §5.1: below the threshold the contradiction instruction is dropped
    and stage 1 runs on weighting alone. With three interviews there are no real
    oppositions and the model would invent one."""
    return material.person_count >= threshold
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_dream_weighting.py -v`
Expected: PASS (17 tests)

- [ ] **Step 5: Commit**

```bash
git add kg2/weighting.py tests/test_dream_weighting.py
git commit -m "feat: weight the graph into dream material

Hidden nodes out, quotes in, min_mentions deliberately not applied. Mentions are
recomputed from surviving edges rather than read off the node, so hiding a
person really removes their voice."
```

---

### Task 7: Stage 1 — the graph becomes a German sentence

**Files:**
- Create: `kg2/condense.py`
- Test: `tests/test_dream_condense.py`

**Interfaces:**
- Consumes: Task 6 (`Material`, `render_material`), `kg.llm.LLMClient` (permitted by spec §3 — a pure client wrapper that imports neither `kg.store`, `kg.core` nor `kg.server`).
- Produces:
  - `kg2.condense.DreamSentence` — pydantic model with one field `sentence: str`
  - `kg2.condense.build_condense_system(question: str, contradiction: bool) -> str`
  - `kg2.condense.build_condense_prompt(material: Material, question: str) -> str`
  - `kg2.condense.CondenseResult` — frozen dataclass `(prompt: str, sentence: str)` where `prompt` is the full system+user record persisted per spec §5.3
  - `kg2.condense.condense(llm, material, question, contradiction) -> CondenseResult`

The artistic core (§5.1). Two things this prompt must do that no default LLM behaviour will do for you:

- **It is a dream, not an illustration.** Condensation, displacement, contradiction preserved. The image may be impossible. An LLM that smooths 40 contradictory interviews into a glossy render *is* the thing the work criticises (§1).
- **Contradiction as construction principle.** The model locates the two most distant positions and holds them in one image **without resolving them**. Without this instruction every model smooths back into the consensus brochure. Dropped below `contradiction_min_persons` (§5.1) — with three interviews there are no real oppositions and the model would invent one.

And two prohibitions from §12: **no person is named**, and the output is not a summary — it answers the guiding question in the dream's own logic.

Length target ~20–40 words (§5.1): long enough to carry the fault line, short enough to read at a glance from standing distance. Enforced in the prompt and *logged* when missed, never rejected — a 46-word sentence is a worse sentence, but a failed dream is a blank change on the wall, and §8's whole stance is to ride it out.

- [ ] **Step 1: Write the failing test**

`tests/test_dream_condense.py`:

```python
"""Spec §5.1 — the sentence. What the prompt must say, and what it must not."""

from __future__ import annotations

import pytest

from kg2.condense import (
    CondenseResult,
    DreamSentence,
    build_condense_prompt,
    build_condense_system,
    condense,
)
from kg2.weighting import build_material

QUESTION = "Wie leben und bauen wir in zehn Jahren?"


class FakeLLM:
    """Records what it was asked, answers what it was told to."""

    def __init__(self, sentence="Der Beton träumt von Wald, und der Wald schickt Rechnungen."):
        self.sentence = sentence
        self.calls: list[tuple[str, str]] = []

    def parse(self, system, user, output_model):
        self.calls.append((system, user))
        return output_model(sentence=self.sentence)


class AngryLLM:
    def parse(self, system, user, output_model):
        raise RuntimeError("llm call failed after 2 attempts")


def material(persons=8, quotes=("Wir bauen zu viel Neues.",)):
    nodes = [
        {"id": f"p{i}", "type": "person", "portrait": None, "created_at": 1.0,
         "hidden": False, "x": None, "y": None}
        for i in range(persons)
    ] + [
        {"id": "t1", "type": "term", "label": "Weiterbauen im Bestand", "mentions": persons,
         "created_at": 2.0, "hidden": False, "x": None, "y": None},
        {"id": "t2", "type": "term", "label": "Sickerfähige Beläge", "mentions": 1,
         "created_at": 2.0, "hidden": False, "x": None, "y": None},
    ]
    edges = [{"id": f"e{i}", "source": f"p{i}", "target": "t1"} for i in range(persons)]
    edges.append({"id": "ex", "source": "p0", "target": "t2"})
    return build_material(
        {
            "version": 1, "generated_at": 1000.0, "min_mentions": 1,
            "nodes": nodes, "edges": edges,
            "quotes": [{"id": f"q{i}", "person_id": "p0", "text": t}
                       for i, t in enumerate(quotes, 1)],
        }
    )


# -- the stance -------------------------------------------------------------


def test_the_system_prompt_asks_for_a_dream_not_an_illustration():
    """Spec §1: not a plausible architectural vision. The friction is the
    subject matter, and no model does this without being told."""
    system = build_condense_system(QUESTION, contradiction=False)

    assert "Traum" in system
    assert "Verdichtung" in system
    assert "unmöglich" in system
    # The failure mode named by name, so a later edit cannot lose it silently.
    assert "Zusammenfassung" in system
    assert "Illustration" in system


def test_the_contradiction_instruction_is_present_above_the_threshold():
    """Spec §5.1: hold the two most distant positions in one image WITHOUT
    resolving them. This is the instruction that prevents the consensus
    brochure."""
    system = build_condense_system(QUESTION, contradiction=True)

    assert "Widerspruch" in system
    assert "nicht auf" in system  # „löse ihn nicht auf"
    assert "Kompromiss" in system


def test_the_contradiction_instruction_is_absent_below_the_threshold():
    """Spec §5.1: with three interviews the model would invent an opposition."""
    system = build_condense_system(QUESTION, contradiction=False)

    assert "Widerspruch" not in system
    assert "Kompromiss" not in system


def test_the_two_systems_differ_only_by_the_contradiction_block():
    """One prompt with an optional block, not two prompts that can drift."""
    without = build_condense_system(QUESTION, contradiction=False)
    with_it = build_condense_system(QUESTION, contradiction=True)

    assert with_it.startswith(without.rstrip())
    assert len(with_it) > len(without)


def test_the_guiding_question_is_in_the_system_prompt():
    system = build_condense_system("Wem gehört die Stadt in zehn Jahren?", contradiction=False)

    assert "Wem gehört die Stadt in zehn Jahren?" in system


def test_the_prompt_forbids_naming_anyone():
    """Spec §12: the dream is collective; quotes feed it, attribution does not.
    Also the quieter answer to „where do my statements end up"."""
    system = build_condense_system(QUESTION, contradiction=True)

    assert "keine Namen" in system.lower() or "nenne keine namen" in system.lower()


def test_the_prompt_asks_for_one_german_sentence_of_the_right_length():
    system = build_condense_system(QUESTION, contradiction=False)

    assert "einen einzigen Satz" in system
    assert "20" in system and "40" in system
    assert "Deutsch" in system


# -- the material -----------------------------------------------------------


def test_the_user_message_carries_the_weighted_material():
    prompt = build_condense_prompt(material(), QUESTION)

    assert "Weiterbauen im Bestand" in prompt
    assert "Sickerfähige Beläge" in prompt
    assert "Wir bauen zu viel Neues." in prompt
    assert "RANDNOTIZEN" in prompt


def test_the_user_message_repeats_the_question_so_the_answer_stays_anchored():
    prompt = build_condense_prompt(material(), QUESTION)

    assert QUESTION in prompt


# -- the call ---------------------------------------------------------------


def test_condense_returns_the_sentence_and_the_full_prompt_record():
    """Spec §5.3: the record is the point. A sentence with no prompt beside it
    cannot be explained after the festival."""
    llm = FakeLLM("Der Beton träumt von Wald.")

    result = condense(llm, material(), QUESTION, contradiction=True)

    assert isinstance(result, CondenseResult)
    assert result.sentence == "Der Beton träumt von Wald."
    # The persisted prompt is system AND user — either alone is unreproducible.
    assert "Traum" in result.prompt
    assert "Weiterbauen im Bestand" in result.prompt


def test_condense_passes_the_contradiction_flag_through_to_the_system_prompt():
    llm = FakeLLM()

    condense(llm, material(), QUESTION, contradiction=True)
    system_with, _ = llm.calls[0]
    condense(llm, material(), QUESTION, contradiction=False)
    system_without, _ = llm.calls[1]

    assert "Widerspruch" in system_with
    assert "Widerspruch" not in system_without


def test_condense_strips_surrounding_whitespace_and_stray_quotes():
    """Tool 1 hit exactly this: the model echoes its own example's quotation
    marks back (`kg/merging.py`, commit 1016421). A leading „ would then be
    rendered on the wall as part of the sentence."""
    for raw in ('  Der Beton träumt.  ', '„Der Beton träumt."', '"Der Beton träumt."'):
        result = condense(FakeLLM(raw), material(), QUESTION, contradiction=False)
        assert result.sentence == "Der Beton träumt."


def test_condense_raises_on_an_empty_sentence():
    """An empty sentence is a failed dream, not a dream with nothing to say —
    the cycle must mark it failed and leave the previous image up (spec §8)."""
    with pytest.raises(ValueError):
        condense(FakeLLM("   "), material(), QUESTION, contradiction=False)


def test_condense_lets_the_llm_error_propagate():
    """The cycle owns the failure policy (spec §8), not this module. Swallowing
    it here would produce a dream with no sentence and no error recorded."""
    with pytest.raises(RuntimeError):
        condense(AngryLLM(), material(), QUESTION, contradiction=False)


def test_an_overlong_sentence_is_kept_and_logged_not_rejected(caplog):
    """A worse sentence beats a blank change on the wall (spec §8)."""
    long = " ".join(["Wort"] * 60)

    with caplog.at_level("WARNING"):
        result = condense(FakeLLM(long), material(), QUESTION, contradiction=False)

    assert result.sentence == long
    assert "60" in caplog.text


def test_the_output_model_has_exactly_one_field():
    """Anything else in the schema is something the model can spend effort on
    instead of the sentence."""
    assert set(DreamSentence.model_fields) == {"sentence"}


# -- against the real thing -------------------------------------------------


def test_the_real_replay_graph_produces_a_workable_prompt(real_graph):
    prompt = build_condense_prompt(build_material(real_graph), QUESTION)

    assert "Scheinbeteiligung pro forma" in prompt
    assert "60 Menschen" in prompt
    assert QUESTION in prompt
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_dream_condense.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kg2.condense'`

- [ ] **Step 3: Implement `kg2/condense.py`**

```python
"""Stage 1: the whole graph becomes one German sentence (spec §5.1).

This is the artistic core, and it is a prompt, so it is worth saying what the
prompt is *for*. The deck promises „das Gedächtnis träumt sein eigenes Bild".
An LLM handed 40 contradictory interviews will, unprompted, average them into a
plausible architectural vision — which is precisely the thing this work
criticises (spec §1). Every paragraph below exists to prevent that.

Two stages rather than one (spec §5), because the sentence is itself a
displayed artefact and must be readable on its own. What appears on screen is
THIS output, not stage 2's prompt: the image prompt is a technical artefact
with style boilerplate, and showing it would put lighting instructions on the
wall (spec §5.2).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import BaseModel

from kg2.weighting import Material, render_material

log = logging.getLogger(__name__)

#: Spec §5.1 — long enough to carry the fault line, short enough to read at a
#: glance from standing distance. A miss is logged, never rejected.
WORDS_MIN, WORDS_MAX = 20, 40

_BASE = """\
Du bist das Gedächtnis einer Ausstellungsstation auf dem Festival NEW bauhaus \
2026. Den ganzen Tag über haben Menschen dort Interviews über das Bauen, das \
Wohnen und die Zukunft gegeben. Aus allem, was gesagt wurde, ist ein Graph \
geworden. Jetzt träumst du davon.

TRÄUMEN, NICHT ILLUSTRIEREN. Das Ergebnis ist keine Zusammenfassung, kein \
Bericht und keine plausible Architekturvision. Es ist eine Verdichtung im \
wörtlichen Sinn: mehrere Aussagen fallen in ein Bild zusammen, Dinge \
verschieben sich, das Bild darf unmöglich sein. Eine glatte, schöne \
Zukunftsvision wäre das Gegenteil dieser Aufgabe.

DIE LEITFRAGE, die alle Menschen beantwortet haben:
{question}

Dein Satz ist eine Antwort auf genau diese Frage — aber in der Logik des \
Traums, nicht als Auswertung.

GEWICHTUNG. Was viele Menschen gesagt haben, beherrscht das Bild. Was genau \
eine Person gesagt hat, darf als kleines Detail am Rand vorkommen, nie als \
Thema.

VERBOTEN: Namen von Menschen, Zuschreibungen wie „eine Besucherin sagte", \
Aufzählungen, Doppelpunkte mit Listen, Anführungszeichen, Meta-Sätze über den \
Graphen oder über das Träumen selbst. Nenne keine Namen.

FORM: genau einen einzigen Satz auf Deutsch, ungefähr {words_min} bis \
{words_max} Wörter. Er muss aus einiger Entfernung im Stehen lesbar sein.\
"""

# Appended only above `contradiction_min_persons` (spec §5.1). Below it there
# are no real oppositions in the material and the model would invent one.
_CONTRADICTION = """\

WIDERSPRUCH ALS BAUPRINZIP. Suche in dem Material die zwei am weitesten \
voneinander entfernten Haltungen — die beiden, die einander wirklich \
widersprechen. Beide müssen in deinem einen Satz vorkommen, gleichzeitig, im \
selben Bild. Löse den Widerspruch nicht auf. Kein Kompromiss, kein \
„einerseits/andererseits", kein versöhnlicher Schluss. Der Riss bleibt \
sichtbar; er ist das Motiv.\
"""


class DreamSentence(BaseModel):
    sentence: str


@dataclass(frozen=True)
class CondenseResult:
    #: System + user, exactly as sent. Persisted per spec §5.3 — a sentence
    #: without the prompt that produced it cannot be explained afterwards.
    prompt: str
    sentence: str


def build_condense_system(question: str, contradiction: bool) -> str:
    base = _BASE.format(question=question, words_min=WORDS_MIN, words_max=WORDS_MAX)
    return base + _CONTRADICTION if contradiction else base


def build_condense_prompt(material: Material, question: str) -> str:
    return (
        f"{render_material(material)}\n\n"
        f"--- ENDE MATERIAL ---\n\n"
        f"Leitfrage: {question}\n"
        f"Antworte mit genau einem Satz."
    )


def _clean(sentence: str) -> str:
    """Trim, and drop a pair of quotation marks the model wrapped around itself.

    Not hypothetical: Tool 1 hit exactly this in `kg.merging` (commit 1016421),
    because the prompt's own examples are quoted and the model echoes the
    quoting back. Here it would put a stray „ on the wall.
    """
    cleaned = sentence.strip()
    for opening, closing in (("„", "“"), ('"', '"'), ("»", "«"), ("'", "'")):
        if cleaned.startswith(opening) and cleaned.endswith(closing) and len(cleaned) > 1:
            cleaned = cleaned[len(opening) : -len(closing)].strip()
    return cleaned


def condense(llm, material: Material, question: str, contradiction: bool) -> CondenseResult:
    """One call. Errors propagate — `kg2.cycle` owns the failure policy (§8)."""
    system = build_condense_system(question, contradiction)
    user = build_condense_prompt(material, question)

    result = llm.parse(system=system, user=user, output_model=DreamSentence)
    sentence = _clean(result.sentence)
    if not sentence:
        raise ValueError("stage 1 returned an empty sentence")

    words = len(sentence.split())
    if not WORDS_MIN <= words <= WORDS_MAX:
        # Logged, never rejected: a sentence of the wrong length is a worse
        # sentence, but a rejected one is a blank change on the wall, and spec
        # §8's whole stance is to ride imperfection out rather than stop.
        log.warning(
            "stage 1 sentence is %s words, outside the %s-%s target: %r",
            words, WORDS_MIN, WORDS_MAX, sentence,
        )

    return CondenseResult(prompt=f"{system}\n\n--- USER ---\n\n{user}", sentence=sentence)
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_dream_condense.py -v`
Expected: PASS (17 tests)

- [ ] **Step 5: Commit**

```bash
git add kg2/condense.py tests/test_dream_condense.py
git commit -m "feat: stage 1 — the graph condenses into one German sentence

The contradiction instruction is the load-bearing part: without it every model
smooths 40 interviews into the consensus brochure spec 1 rejects. Dropped below
the person threshold, where an opposition would have to be invented."
```

---

### Task 8: Stage 2 — the sentence becomes an image (probe the endpoint first)

**Files:**
- Create: `docs/dream-image-contract.md`, `kg2/imagegen.py`
- Test: `tests/test_dream_imagegen.py`

**Interfaces:**
- Consumes: Task 2 (`DreamConfig`), Task 7 (the sentence).
- Produces:
  - `kg2.imagegen.build_image_prompt(sentence: str, register: str, aspect_ratio: str) -> str`
  - `kg2.imagegen.render_image(prompt: str, *, model, api_key, url, timeout, post=...) -> bytes`
  - `kg2.imagegen.decode_image(payload: dict) -> bytes`
  - `kg2.imagegen.save_image(data: bytes, path: Path) -> Path`
  - `docs/dream-image-contract.md` — the **verified** request/response shape

**Do not write the client before the probe.** This is the discipline Tool 1 used for the STT server (`docs/stt-contract.md`, „verified event contract"): call the real endpoint once, record what it actually returns, then code against the record. Building an image client against an assumed request shape is how the mismatch gets discovered on site.

If the probe shows the model id or the response shape differs from what spec §5.2 assumes, **that is a finding to write down, not to paper over** — record it in the contract doc and, if the spec is wrong, amend the spec with a dated note (standing rule, 2026-08-25).

- [ ] **Step 1: Probe the real endpoint**

Needs `OPENROUTER_API_KEY` in the environment. One call, a few cents.

```bash
uv run python - <<'PY'
import json, os, httpx
key = os.environ["OPENROUTER_API_KEY"]
response = httpx.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={"Authorization": f"Bearer {key}"},
    json={
        "model": "google/gemini-3-pro-image",
        "modalities": ["image", "text"],
        "messages": [{"role": "user", "content":
            "Ein Betonhof, in dem Kinder Bäume pflanzen. "
            "Malerisch und atmosphärisch, weiche Übergänge, gedämpfte Farbigkeit, "
            "diffuses Licht. Kein Fotorealismus, keine Schrift im Bild. "
            "Seitenverhältnis 16:9, Querformat."}],
    },
    timeout=180.0,
)
print("HTTP", response.status_code)
payload = response.json()
# Print the SHAPE, not the base64 payload — a data URL is megabytes.
def shape(value, depth=0):
    pad = "  " * depth
    if isinstance(value, dict):
        for key, item in value.items():
            print(f"{pad}{key}:")
            shape(item, depth + 1)
    elif isinstance(value, list):
        print(f"{pad}[{len(value)} items]")
        if value:
            shape(value[0], depth + 1)
    elif isinstance(value, str) and len(value) > 120:
        print(f"{pad}<str len={len(value)}> starts: {value[:80]!r}")
    else:
        print(f"{pad}{value!r}")
shape(payload)
PY
```

Record the exact output. The shape this plan assumes — and which the contract doc must either confirm or correct — is:

```
choices[0].message.images[0].image_url.url  ->  "data:image/png;base64,...."
```

- [ ] **Step 2: Write `docs/dream-image-contract.md` from what actually came back**

Use this template and **fill it with the real observed values**, not the assumed ones. Where the observation contradicts the assumption, say so in the „Abweichungen" row rather than editing the assumption away.

```markdown
# Bild-Endpunkt — verifizierter Vertrag

Wie `docs/stt-contract.md` für Tool 1: **erst am echten Endpunkt geprüft, dann
dagegen programmiert.** Ein Bildclient gegen eine vermutete Request-Form ist
genau die Sorte Fehler, die man vor Ort entdeckt.

| | |
|---|---|
| Geprüft am | 2026-08-26 |
| Endpunkt | `POST https://openrouter.ai/api/v1/chat/completions` |
| Modell | `google/gemini-3-pro-image` |
| Auth | `Authorization: Bearer $OPENROUTER_API_KEY` |
| Abweichungen von Spec §5.2 | *(hier eintragen, oder „keine")* |

## Request

```json
{
  "model": "google/gemini-3-pro-image",
  "modalities": ["image", "text"],
  "messages": [{"role": "user", "content": "<Prompt>"}]
}
```

`modalities` ist nicht optional: ohne den Eintrag antwortet das Modell mit Text
über das Bild statt mit dem Bild.

## Response — beobachtete Form

*(hier die echte, mit dem Skript aus Task 8 Schritt 1 gedruckte Struktur
eintragen)*

```
choices: [1 items]
  message:
    role: 'assistant'
    content: ...
    images: [1 items]
      type: 'image_url'
      image_url:
        url: <str len=…> starts: 'data:image/png;base64,iVBORw0KGgo…'
```

Das Bild kommt als **Data-URL im Body**, nicht als Link, den man nachladen
müsste. Der Client dekodiert Base64 und schreibt PNG-Bytes.

## Was schiefgehen kann

| Fall | Erkennung | Verhalten |
|---|---|---|
| Kein `images` im Ergebnis (Modell antwortet in Text) | `KeyError`/leere Liste | `ImageError` → Traum `failed`, letztes Bild bleibt stehen (Spec §8) |
| `url` ist kein `data:`-URL | Präfixprüfung | `ImageError` |
| HTTP 429 / 5xx | `raise_for_status` | `ImageError`, kein Retry-Sturm — der nächste Trigger versucht es erneut |
| Timeout | `httpx` | dito; das Zeitlimit steht in `config2.toml` (`image_timeout_s`) |

**Kein lokales Bildmodell als Fallback** (Spec §8, Brainstorm §5): zwei
Bildsprachen zu pflegen und eine GPU im Show-Rechner. Der physische
Rückfallweg ist ein LTE-Stick und steht im Runbook, nicht im Code.
```

- [ ] **Step 3: Write the failing test**

`tests/test_dream_imagegen.py`:

```python
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

from kg2.imagegen import ImageError, build_image_prompt, decode_image, render_image, save_image

REGISTER = (
    "Malerisch und atmosphärisch, weiche Übergänge, gedämpfte Farbigkeit, "
    "diffuses Licht, sichtbarer Pinselduktus. Kein Fotorealismus, kein "
    "Architektur-Rendering, keine Schrift im Bild."
)
SENTENCE = "Der Beton träumt von Wald, und der Wald schickt Rechnungen."


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


def response_with(data: bytes) -> dict:
    url = "data:image/png;base64," + base64.b64encode(data).decode("ascii")
    return {
        "choices": [
            {"message": {"role": "assistant", "content": "",
                         "images": [{"type": "image_url", "image_url": {"url": url}}]}}
        ]
    }


# -- the prompt -------------------------------------------------------------


def test_the_register_is_appended_to_every_prompt():
    """Spec §5.2: held in config as a style suffix, never model-chosen, never
    graph-driven. The history strip is a measurement series and exactly one
    variable may change — and that is the material."""
    prompt = build_image_prompt(SENTENCE, REGISTER, "16:9")

    assert SENTENCE in prompt
    assert REGISTER in prompt


def test_the_aspect_ratio_is_landscape_and_stated():
    """Spec §5.2: matching the 65″ screen."""
    prompt = build_image_prompt(SENTENCE, REGISTER, "16:9")

    assert "16:9" in prompt
    assert "Querformat" in prompt


def test_the_sentence_comes_first_so_it_is_the_subject():
    """The register is boilerplate. A prompt that opens with lighting
    instructions gets an image about lighting."""
    prompt = build_image_prompt(SENTENCE, REGISTER, "16:9")

    assert prompt.index(SENTENCE) < prompt.index(REGISTER)


def test_two_sentences_share_a_register_exactly():
    a = build_image_prompt("Satz A.", REGISTER, "16:9")
    b = build_image_prompt("Satz B.", REGISTER, "16:9")

    assert a.replace("Satz A.", "X") == b.replace("Satz B.", "X")


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


# -- saving -----------------------------------------------------------------


def test_save_image_writes_the_bytes(tmp_path):
    target = save_image(png_bytes(), tmp_path / "d1.png")

    assert target.read_bytes() == png_bytes()


def test_save_image_never_overwrites(tmp_path):
    """Spec §5.2: the image is written to images/<dream_id>.png and never
    overwritten. An overwrite would silently rewrite the history strip."""
    save_image(png_bytes(), tmp_path / "d1.png")

    with pytest.raises(FileExistsError):
        save_image(b"other", tmp_path / "d1.png")


def test_save_image_creates_the_directory(tmp_path):
    target = save_image(png_bytes(), tmp_path / "deep" / "images" / "d1.png")

    assert target.is_file()


def test_save_image_rejects_bytes_that_are_not_a_png(tmp_path):
    """A JSON error body base64-encoded into a data URL would otherwise land on
    disk as `d1.png` and render as a broken image on the wall."""
    with pytest.raises(ImageError):
        save_image(b"{'error': 'nope'}", tmp_path / "d1.png")


def test_save_image_leaves_no_partial_file_when_it_rejects(tmp_path):
    with pytest.raises(ImageError):
        save_image(b"not a png", tmp_path / "d1.png")

    assert not (tmp_path / "d1.png").exists()
```

- [ ] **Step 4: Run the test and confirm it fails**

Run: `uv run pytest tests/test_dream_imagegen.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kg2.imagegen'`

- [ ] **Step 5: Implement `kg2/imagegen.py`**

Adjust the `decode_image` path if — and only if — the probe in Step 1 recorded a different response shape. `docs/dream-image-contract.md` is the authority.

```python
"""Stage 2: the sentence becomes an image (spec §5.2).

Built against `docs/dream-image-contract.md`, which was written by probing the
real endpoint — the same discipline `docs/stt-contract.md` established for Tool
1. If this module and that document disagree, the document is right.

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
    """
    if not data.startswith(_PNG_MAGIC):
        raise ImageError(f"stage 2 returned {len(data)} bytes that are not a PNG")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # "xb" rather than a pre-check: exclusive create, so two cycles racing on
    # one id cannot both think they won.
    with path.open("xb") as handle:
        handle.write(data)
    return path
```

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_dream_imagegen.py -v`
Expected: PASS (17 tests)

- [ ] **Step 7: Commit**

```bash
git add kg2/imagegen.py docs/dream-image-contract.md tests/test_dream_imagegen.py
git commit -m "feat: stage 2 — sentence to image, against a probed contract

The endpoint was called once for real and what it returned is recorded in
docs/dream-image-contract.md; the client is written against that document, the
way Tool 1's STT client was written against docs/stt-contract.md. No retry, by
spec 8: the next trigger is the retry."
```

---

### Task 9: The dream cycle

**Files:**
- Create: `kg2/cycle.py`
- Test: `tests/test_dream_cycle.py`

**Interfaces:**
- Consumes: Tasks 4, 6, 7, 8.
- Produces:
  - `kg2.cycle.run_dream(store, cfg, llm, graph, now, *, condense_fn=condense, render_fn=render_image, on_sentence=None) -> Dream | None`

The place where §5.3's reproducibility and §8's failure policy meet. Three properties, all tested:

- **The row is created before the first cloud call.** A crash mid-cycle then leaves a `running` row — visibly incomplete, which is the honest record — instead of no trace at all.
- **It never raises.** Any failure marks the dream `failed` and returns `None`. The watcher must not be one exception away from a dead poll loop.
- **The current image stays up.** That is free, because `DreamStore.visible_dreams()` only returns `status='done'` rows — so nothing has to be undone on failure. Tested rather than assumed.

`on_sentence` exists for §6's typewriter variant: it fires the moment stage 1 returns, so the page can build the sentence up word by word *while* stage 2 runs. Without it the typewriter cannot exist, because the display would only learn of the dream once it was finished.

- [ ] **Step 1: Write the failing test**

`tests/test_dream_cycle.py`:

```python
"""Spec §5.3 + §8 — one dream, and what is left behind when it fails."""

from __future__ import annotations

import base64
import struct
import zlib

from kg2.config import DreamConfig
from kg2.cycle import run_dream
from kg2.imagegen import ImageError
from kg2.store import DreamStore


def png_bytes() -> bytes:
    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
        + chunk(b"IEND", b"")
    )


def graph(persons=8, generated_at=1700000000.0) -> dict:
    nodes = [
        {"id": f"p{i}", "type": "person", "portrait": None, "created_at": 1.0,
         "hidden": False, "x": None, "y": None}
        for i in range(persons)
    ] + [
        {"id": "t1", "type": "term", "label": "Weiterbauen im Bestand", "mentions": persons,
         "created_at": 2.0, "hidden": False, "x": None, "y": None}
    ]
    return {
        "version": 1, "generated_at": generated_at, "min_mentions": 1, "nodes": nodes,
        "edges": [{"id": f"e{i}", "source": f"p{i}", "target": "t1"} for i in range(persons)],
        "quotes": [{"id": "q1", "person_id": "p0", "text": "Wir bauen zu viel Neues."}],
    }


def setup(tmp_path, **overrides):
    cfg = DreamConfig(data_dir=tmp_path / "dream", **overrides)
    return cfg, DreamStore.open(cfg.db_path)


def good_condense(sentence="Der Beton träumt von Wald."):
    from kg2.condense import CondenseResult

    def fn(llm, material, question, contradiction):
        return CondenseResult(prompt=f"P(contradiction={contradiction})", sentence=sentence)

    return fn


def good_render(data=None):
    def fn(prompt, **kwargs):
        return data if data is not None else png_bytes()

    return fn


# -- the happy path ---------------------------------------------------------


def test_a_successful_dream_records_everything_spec_5_3_asks_for(tmp_path):
    cfg, store = setup(tmp_path)

    dream = run_dream(
        store, cfg, llm=object(), graph=graph(), now=5000.0,
        condense_fn=good_condense(), render_fn=good_render(),
    )

    assert dream is not None
    assert dream.status == "done"
    assert dream.created_at == 5000.0
    assert dream.graph_generated_at == 1700000000.0
    assert dream.person_count == 8
    assert dream.term_count == 1
    assert dream.edge_count == 8
    assert dream.sentence == "Der Beton träumt von Wald."
    assert dream.stage1_prompt
    assert dream.stage2_prompt
    assert dream.condense_model == "claude-opus-5"
    assert dream.image_model == "google/gemini-3-pro-image"
    assert dream.guiding_question == cfg.guiding_question
    assert dream.absorbed_persons == [f"p{i}" for i in range(8)]
    assert dream.discarded is False
    store.close()


def test_the_image_lands_at_images_slash_dream_id_png(tmp_path):
    cfg, store = setup(tmp_path)

    dream = run_dream(
        store, cfg, llm=object(), graph=graph(), now=1.0,
        condense_fn=good_condense(), render_fn=good_render(),
    )

    assert dream.image_path == "d1.png"
    assert (cfg.image_dir / "d1.png").read_bytes() == png_bytes()
    store.close()


def test_the_new_dream_becomes_the_current_one(tmp_path):
    cfg, store = setup(tmp_path)

    run_dream(store, cfg, object(), graph(), 1.0,
              condense_fn=good_condense("erst"), render_fn=good_render())
    run_dream(store, cfg, object(), graph(), 300.0,
              condense_fn=good_condense("dann"), render_fn=good_render())

    assert store.current_dream().sentence == "dann"
    assert [d.sentence for d in store.history()] == ["erst"]
    store.close()


# -- the contradiction threshold -------------------------------------------


def test_the_contradiction_instruction_is_on_above_the_threshold(tmp_path):
    cfg, store = setup(tmp_path, contradiction_min_persons=6)

    dream = run_dream(store, cfg, object(), graph(persons=8), 1.0,
                      condense_fn=good_condense(), render_fn=good_render())

    assert dream.contradiction is True
    assert "contradiction=True" in dream.stage1_prompt
    store.close()


def test_the_contradiction_instruction_is_off_below_the_threshold(tmp_path):
    """Spec §5.1: with three interviews the model would invent an opposition."""
    cfg, store = setup(tmp_path, contradiction_min_persons=6)

    dream = run_dream(store, cfg, object(), graph(persons=3), 1.0,
                      condense_fn=good_condense(), render_fn=good_render())

    assert dream.contradiction is False
    assert "contradiction=False" in dream.stage1_prompt
    store.close()


# -- failure ----------------------------------------------------------------


def test_a_stage_1_failure_leaves_the_previous_image_up(tmp_path):
    """Spec §8, the failure mode that matters most."""
    cfg, store = setup(tmp_path)
    run_dream(store, cfg, object(), graph(), 1.0,
              condense_fn=good_condense("das gute Bild"), render_fn=good_render())

    def boom(llm, material, question, contradiction):
        raise RuntimeError("llm call failed after 2 attempts")

    result = run_dream(store, cfg, object(), graph(), 300.0,
                       condense_fn=boom, render_fn=good_render())

    assert result is None
    assert store.current_dream().sentence == "das gute Bild"
    assert store.get_dream("d2").status == "failed"
    assert "llm call failed" in store.get_dream("d2").error
    store.close()


def test_a_stage_2_failure_leaves_the_previous_image_up_and_keeps_the_sentence(tmp_path):
    cfg, store = setup(tmp_path)
    run_dream(store, cfg, object(), graph(), 1.0,
              condense_fn=good_condense("das gute Bild"), render_fn=good_render())

    def boom(prompt, **kwargs):
        raise ImageError("502 from the image model")

    result = run_dream(store, cfg, object(), graph(), 300.0,
                       condense_fn=good_condense("kam bis zum Satz"), render_fn=boom)

    assert result is None
    assert store.current_dream().sentence == "das gute Bild"
    failed = store.get_dream("d2")
    assert failed.status == "failed"
    # Spec §5.3: the prompt that produced nothing is the one worth reading.
    assert failed.sentence == "kam bis zum Satz"
    assert failed.stage2_prompt
    store.close()


def test_a_failure_with_no_previous_dream_leaves_the_screen_empty_not_broken(tmp_path):
    cfg, store = setup(tmp_path)

    def boom(llm, material, question, contradiction):
        raise RuntimeError("no connectivity at all")

    assert run_dream(store, cfg, object(), graph(), 1.0,
                     condense_fn=boom, render_fn=good_render()) is None
    assert store.current_dream() is None
    assert store.history() == []
    store.close()


def test_run_dream_never_raises_whatever_goes_wrong(tmp_path):
    """The watcher must not be one exception away from a dead poll loop."""
    cfg, store = setup(tmp_path)

    for breaker in (
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
        lambda *a, **k: (_ for _ in ()).throw(ValueError("empty sentence")),
        lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()),
    ):
        assert run_dream(store, cfg, object(), graph(), 1.0,
                         condense_fn=breaker, render_fn=good_render()) is None
    store.close()


def test_a_non_png_body_fails_the_dream_rather_than_landing_on_the_wall(tmp_path):
    cfg, store = setup(tmp_path)

    result = run_dream(store, cfg, object(), graph(), 1.0,
                       condense_fn=good_condense(), render_fn=good_render(b"<html>502</html>"))

    assert result is None
    assert store.get_dream("d1").status == "failed"
    assert not (cfg.image_dir / "d1.png").exists()
    store.close()


def test_the_row_exists_even_if_the_process_dies_mid_cycle(tmp_path):
    """The row is written before the first cloud call, so a kill leaves a
    visibly incomplete record rather than no record."""
    cfg, store = setup(tmp_path)
    seen = {}

    def note_and_die(llm, material, question, contradiction):
        seen["row"] = store.get_dream("d1")
        raise RuntimeError("killed")

    run_dream(store, cfg, object(), graph(), 1.0,
              condense_fn=note_and_die, render_fn=good_render())

    assert seen["row"] is not None
    assert seen["row"].status == "running"
    store.close()


# -- the typewriter hook ----------------------------------------------------


def test_the_sentence_is_announced_as_soon_as_stage_1_returns(tmp_path):
    """Spec §6's typewriter builds the sentence up WHILE stage 2 runs. Without
    this hook the display would only learn of the dream once it was finished,
    and the variant could not exist at all."""
    cfg, store = setup(tmp_path)
    announced = []

    def slow_render(prompt, **kwargs):
        assert announced == ["Der Beton träumt."]  # announced BEFORE the render
        return png_bytes()

    run_dream(store, cfg, object(), graph(), 1.0,
              condense_fn=good_condense("Der Beton träumt."), render_fn=slow_render,
              on_sentence=announced.append)

    assert announced == ["Der Beton träumt."]
    store.close()


def test_a_broken_on_sentence_callback_does_not_fail_the_dream(tmp_path):
    """The typewriter is decoration. It must never cost an image."""
    cfg, store = setup(tmp_path)

    def broken(sentence):
        raise RuntimeError("bus is full")

    dream = run_dream(store, cfg, object(), graph(), 1.0,
                      condense_fn=good_condense(), render_fn=good_render(),
                      on_sentence=broken)

    assert dream is not None
    assert dream.status == "done"
    store.close()


# -- against the real thing -------------------------------------------------


def test_a_dream_over_the_real_replay_graph(real_graph):
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        cfg = DreamConfig(data_dir=Path(tmp) / "dream")
        store = DreamStore.open(cfg.db_path)

        dream = run_dream(store, cfg, object(), real_graph, 1700020000.0,
                          condense_fn=good_condense(), render_fn=good_render())

        assert dream.person_count == 60
        assert dream.term_count == 163
        assert dream.edge_count == 267
        assert len(dream.absorbed_persons) == 60
        assert dream.contradiction is True  # 60 >= 6
        store.close()
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_dream_cycle.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kg2.cycle'`

- [ ] **Step 3: Implement `kg2/cycle.py`**

```python
"""One dream: condense -> render -> persist (spec §5).

Where reproducibility (§5.3) and the failure policy (§8) meet.

The order below is the design, not an implementation detail:

1. The row is written BEFORE the first cloud call, so a crash or a kill leaves
   a `running` row — visibly incomplete, which is the honest record — instead
   of no trace that a dream was ever attempted.
2. Stage 1's prompt and sentence are stored as soon as they exist.
3. Stage 2's prompt is stored BEFORE the render, so a failed render still
   leaves the prompt that failed. That is the one worth reading.
4. Only then does the row become `done` and reach the screen.

This function NEVER raises. The watcher must not be one exception away from a
dead poll loop, and the display is protected for free: `visible_dreams()` only
ever returns `done` rows, so a failure needs nothing undone — the current image
simply stays up (§8).
"""

from __future__ import annotations

import logging

from kg2.condense import condense as _condense
from kg2.imagegen import build_image_prompt, render_image as _render_image, save_image
from kg2.models import Dream
from kg2.trigger import absorbed_persons
from kg2.weighting import build_material, contradiction_enabled

log = logging.getLogger(__name__)


def run_dream(
    store,
    cfg,
    llm,
    graph: dict,
    now: float,
    *,
    condense_fn=_condense,
    render_fn=_render_image,
    on_sentence=None,
) -> Dream | None:
    """Run one full cycle. Returns the finished Dream, or None if it failed."""
    material = build_material(graph)
    contradiction = contradiction_enabled(material, cfg.contradiction_min_persons)

    dream = store.create_dream(
        created_at=now,
        graph_generated_at=material.generated_at,
        person_count=material.person_count,
        term_count=material.term_count,
        edge_count=material.edge_count,
        contradiction=contradiction,
        guiding_question=cfg.guiding_question,
        absorbed_persons=sorted(absorbed_persons(graph)),
    )

    try:
        result = condense_fn(llm, material, cfg.guiding_question, contradiction)
        store.set_stage1(
            dream.id,
            prompt=result.prompt,
            sentence=result.sentence,
            model=cfg.condense_model,
        )
        _announce(on_sentence, result.sentence)

        image_prompt = build_image_prompt(
            result.sentence, cfg.visual_register, cfg.image_aspect_ratio
        )
        store.set_stage2_prompt(dream.id, prompt=image_prompt, model=cfg.image_model)

        data = render_fn(
            image_prompt,
            model=cfg.image_model,
            api_key=cfg.openrouter_api_key,
            url=cfg.image_url,
            timeout=cfg.image_timeout_s,
        )
        filename = f"{dream.id}.png"
        save_image(data, cfg.image_dir / filename)
        store.finish_dream(dream.id, image_path=filename)
    except BaseException as exc:
        # BaseException, not Exception: a KeyboardInterrupt during the shutdown
        # of an exhibition day must still close the row honestly rather than
        # leave it stuck at `running` forever. The dream is abandoned either
        # way — spec §8 — and the current image stays up.
        log.error("dream %s failed: %s", dream.id, exc)
        store.fail_dream(dream.id, f"{type(exc).__name__}: {exc}")
        return None

    return store.get_dream(dream.id)


def _announce(on_sentence, sentence: str) -> None:
    """Tell the display the sentence exists, before the image does (spec §6).

    This is what the typewriter variant is built on: it builds the sentence up
    word by word WHILE stage 2 runs, then settles into the baseline's fixed line
    when the image arrives. A failure here is swallowed on purpose — the
    typewriter is decoration and must never cost an image.
    """
    if on_sentence is None:
        return
    try:
        on_sentence(sentence)
    except Exception as exc:
        log.warning("could not announce the sentence: %s", exc)
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_dream_cycle.py -v`
Expected: PASS (15 tests)

- [ ] **Step 5: Run every Tool 2 test written so far**

Run: `uv run pytest tests/test_dream_*.py -q`
Expected: PASS, no failures.

- [ ] **Step 6: Commit**

```bash
git add kg2/cycle.py tests/test_dream_cycle.py
git commit -m "feat: the dream cycle — condense, render, persist, never raise

The row is written before the first cloud call so a kill leaves an honest
record; the current image stays up on failure for free, because visible_dreams
only returns finished rows."
```

---

### Task 10: Tool 2's server — `/dream`, `/operator`, `/events`, the API

**Files:**
- Create: `kg2/server.py`
- Test: `tests/test_dream_server.py`

**Interfaces:**
- Consumes: Task 2 (`DreamConfig`), Task 4 (`DreamStore`), `kg.bus.EventBus` (permitted by §3 — pure asyncio, imports nothing from `kg.store`/`kg.core`/`kg.server`).
- Produces:
  - `kg2.server.dream_state(store, cfg) -> dict`
  - `kg2.server.dream_payload(dream) -> dict`
  - `kg2.server.broadcast_dream_state(store, cfg, bus) -> None`
  - `kg2.server.seed_display_settings(store, cfg) -> None`
  - `kg2.server.create_dream_app(store, cfg, bus) -> FastAPI`

Tool 2 gets its **own** interface (§7). Tool 1's operator UI keeps its deliberate sparseness and is **not** extended.

**Flow control goes through the store, not through an object handed to the app.** „Pause" and „Dream now" are both settings the watcher reads on its next tick. That is one mechanism instead of two, it survives a restart for free (§8), and it means the server needs no reference to the watcher at all — so a wedged watcher cannot take the operator UI down with it.

**Explicitly NOT in the interface** (§7): changing the guiding question, the visual register, or the weighting at runtime. Both are set in the morning, in `config2.toml`. The API must have no route that can change them, and a test asserts that.

- [ ] **Step 1: Write the failing test**

`tests/test_dream_server.py`:

```python
"""Spec §7 — Tool 2's own operator API, and what it deliberately cannot do."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from kg.bus import EventBus
from kg2.config import DreamConfig
from kg2.server import create_dream_app, dream_state, seed_display_settings
from kg2.store import DreamStore


@pytest.fixture()
def app(tmp_path):
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    seed_display_settings(store, cfg)
    bus = EventBus()
    client = TestClient(create_dream_app(store, cfg, bus))
    yield client, store, cfg, bus
    store.close()


def add_dream(store, cfg, *, at, sentence, discarded=False):
    dream = store.create_dream(
        created_at=at, graph_generated_at=at - 1, person_count=6, term_count=5,
        edge_count=9, contradiction=True, guiding_question=cfg.guiding_question,
        absorbed_persons=["p1"],
    )
    store.set_stage1(dream.id, prompt="S1", sentence=sentence, model="claude-opus-5")
    store.set_stage2_prompt(dream.id, prompt="S2", model="google/gemini-3-pro-image")
    store.finish_dream(dream.id, image_path=f"{dream.id}.png")
    (cfg.image_dir / f"{dream.id}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    if discarded:
        store.set_discarded(dream.id, True)
    return store.get_dream(dream.id)


# -- state ------------------------------------------------------------------


def test_state_carries_the_question_the_current_dream_and_the_strip(app):
    client, store, cfg, _ = app
    add_dream(store, cfg, at=1.0, sentence="erst")
    add_dream(store, cfg, at=2.0, sentence="dann")

    state = client.get("/api/state").json()

    assert state["question"] == cfg.guiding_question
    assert state["current"]["sentence"] == "dann"
    assert state["current"]["image"] == "/media/images/d2.png"
    assert [d["sentence"] for d in state["history"]] == ["erst"]


def test_state_starts_empty_on_a_fresh_machine(app):
    client, _, _, _ = app

    state = client.get("/api/state").json()

    assert state["current"] is None
    assert state["history"] == []
    assert state["paused"] is False


def test_display_settings_start_from_config_and_are_then_owned_by_the_operator(app):
    client, store, cfg, _ = app

    state = client.get("/api/state").json()
    assert state["fade_ms"] == cfg.default_fade_ms
    assert state["typewriter"] == cfg.default_typewriter
    assert state["strip_ratio"] == cfg.default_strip_ratio
    assert state["question_visible"] == cfg.default_question_visible
    assert state["question_seconds"] == cfg.default_question_seconds

    client.post("/api/display", json={"fade_ms": 400})
    seed_display_settings(store, cfg)  # a restart re-seeds; it must not win

    assert client.get("/api/state").json()["fade_ms"] == 400


# -- display controls (spec §7) --------------------------------------------


def test_every_display_setting_can_be_changed(app):
    client, _, _, _ = app

    response = client.post(
        "/api/display",
        json={
            "question_visible": False,
            "question_seconds": 20,
            "fade_ms": 800,
            "strip_ratio": 0.3,
            "typewriter": True,
        },
    )

    assert response.status_code == 200
    state = client.get("/api/state").json()
    assert state["question_visible"] is False
    assert state["question_seconds"] == 20
    assert state["fade_ms"] == 800
    assert state["strip_ratio"] == 0.3
    assert state["typewriter"] is True


def test_a_partial_display_update_leaves_the_rest_alone(app):
    client, _, _, _ = app
    client.post("/api/display", json={"fade_ms": 800, "typewriter": True})

    client.post("/api/display", json={"fade_ms": 400})

    state = client.get("/api/state").json()
    assert state["fade_ms"] == 400
    assert state["typewriter"] is True


@pytest.mark.parametrize(
    "payload",
    [
        {"fade_ms": 0},  # a 0 ms "cross-fade" is a cut, which Birk ruled out
        {"fade_ms": 20000},
        {"strip_ratio": 0.0},  # no strip at all — the evidence would vanish
        {"strip_ratio": 0.9},  # the strip would swallow the current dream
        {"question_seconds": -1},
    ],
)
def test_out_of_range_display_values_are_rejected(app, payload):
    client, _, _, _ = app

    assert client.post("/api/display", json=payload).status_code == 422


def test_a_rejected_write_does_not_move_the_stored_value(app):
    client, _, _, _ = app
    before = client.get("/api/state").json()["fade_ms"]

    client.post("/api/display", json={"fade_ms": 99999})

    assert client.get("/api/state").json()["fade_ms"] == before


# -- flow control (spec §7) -------------------------------------------------


def test_dream_now_raises_a_flag_the_watcher_will_pick_up(app):
    """Needed the moment someone from the organiser stands in front of the
    screen and wants to see how it works."""
    client, store, _, _ = app

    assert client.post("/api/dream_now").status_code == 200

    assert store.get_setting("dream_requested", "0") == "1"


def test_pause_and_resume_round_trip(app):
    client, store, _, _ = app

    client.post("/api/pause", json={"paused": True})
    assert client.get("/api/state").json()["paused"] is True
    assert store.get_setting("paused", "0") == "1"

    client.post("/api/pause", json={"paused": False})
    assert client.get("/api/state").json()["paused"] is False


def test_discard_removes_the_dream_from_the_screen_and_the_strip(app):
    """Spec §7, Birk: one step, both places."""
    client, store, cfg, _ = app
    add_dream(store, cfg, at=1.0, sentence="erst")
    add_dream(store, cfg, at=2.0, sentence="peinlich")

    assert client.post("/api/discard", json={"dream_id": "d2", "discarded": True}).status_code == 200

    state = client.get("/api/state").json()
    assert state["current"]["sentence"] == "erst"  # the previous one returns
    assert state["history"] == []


def test_discard_is_reversible(app):
    client, store, cfg, _ = app
    add_dream(store, cfg, at=1.0, sentence="doch nicht")

    client.post("/api/discard", json={"dream_id": "d1", "discarded": True})
    client.post("/api/discard", json={"dream_id": "d1", "discarded": False})

    assert client.get("/api/state").json()["current"]["sentence"] == "doch nicht"


def test_discarding_an_unknown_dream_is_a_400_not_a_500(app):
    client, _, _, _ = app

    assert client.post("/api/discard", json={"dream_id": "d99", "discarded": True}).status_code == 400


# -- what the interface must NOT be able to do (spec §7) --------------------


def test_no_route_can_change_the_guiding_question_or_the_register():
    """Spec §7: changing the question mid-day destroys exactly the
    comparability the strip exists for. Both are morning settings, in
    config2.toml, and the API must have no way to touch them."""
    import kg2.server
    from pathlib import Path

    source = Path(kg2.server.__file__).read_text(encoding="utf-8")

    assert "guiding_question=" not in source.replace("cfg.guiding_question", "")
    assert "visual_register" not in source


def test_the_state_payload_never_exposes_the_image_prompt(app):
    """Spec §5.2: showing stage 2's prompt would put lighting instructions on
    the wall. It belongs in the operator UI, and reaches it through /api/dreams."""
    client, store, cfg, _ = app
    add_dream(store, cfg, at=1.0, sentence="ein Satz")

    state = client.get("/api/state").json()

    assert "stage2_prompt" not in json.dumps(state)
    assert "S2" not in json.dumps(state)


def test_the_operator_can_read_the_full_record(app):
    """Spec §5.3 / §7: the image prompt is stored for reproducibility and shown
    ONLY in the operator UI."""
    client, store, cfg, _ = app
    add_dream(store, cfg, at=1.0, sentence="ein Satz")

    dreams = client.get("/api/dreams").json()["dreams"]

    assert dreams[0]["stage1_prompt"] == "S1"
    assert dreams[0]["stage2_prompt"] == "S2"
    assert dreams[0]["condense_model"] == "claude-opus-5"


def test_the_operator_sees_failed_and_discarded_dreams_too(app):
    """The record stays honest (spec §7). The DISPLAY filters; the record does not."""
    client, store, cfg, _ = app
    add_dream(store, cfg, at=1.0, sentence="verworfen", discarded=True)
    broken = store.create_dream(
        created_at=2.0, graph_generated_at=1.0, person_count=1, term_count=1,
        edge_count=1, contradiction=False, guiding_question="Q", absorbed_persons=["p2"],
    )
    store.fail_dream(broken.id, "timeout")

    dreams = client.get("/api/dreams").json()["dreams"]

    assert {d["id"] for d in dreams} == {"d1", "d2"}
    assert [d for d in dreams if d["id"] == "d1"][0]["discarded"] is True
    assert [d for d in dreams if d["id"] == "d2"][0]["status"] == "failed"


# -- pages and assets -------------------------------------------------------


def test_the_two_pages_are_served(app):
    client, _, _, _ = app

    assert client.get("/dream").status_code == 200
    assert client.get("/operator").status_code == 200
    assert client.get("/", follow_redirects=False).status_code in (307, 302)


def test_images_are_served_from_the_dream_machines_own_directory(app):
    client, store, cfg, _ = app
    add_dream(store, cfg, at=1.0, sentence="x")

    response = client.get("/media/images/d1.png")

    assert response.status_code == 200
    assert response.content.startswith(b"\x89PNG")


# -- SSE --------------------------------------------------------------------


def test_a_control_change_is_pushed_to_every_subscriber(app):
    client, store, cfg, bus = app
    queue = bus.subscribe()

    client.post("/api/display", json={"fade_ms": 700})

    event = queue.get_nowait()
    assert event["type"] == "state"
    assert event["state"]["fade_ms"] == 700


def test_the_event_stream_opens_with_the_current_state(app):
    client, store, cfg, _ = app
    add_dream(store, cfg, at=1.0, sentence="beim Verbinden schon da")

    with client.stream("GET", "/events") as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line.startswith("data:"):
                payload = json.loads(line[5:])
                assert payload["type"] == "state"
                assert payload["state"]["current"]["sentence"] == "beim Verbinden schon da"
                break


# -- restart ----------------------------------------------------------------


def test_every_setting_and_the_whole_strip_come_back_after_a_restart(tmp_path):
    """Spec §8: the screen comes back exactly as it stood."""
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    seed_display_settings(store, cfg)
    client = TestClient(create_dream_app(store, cfg, EventBus()))
    for index in range(3):
        add_dream(store, cfg, at=float(index), sentence=f"traum {index}")
    client.post("/api/display", json={"fade_ms": 400, "typewriter": True})
    client.post("/api/pause", json={"paused": True})
    before = client.get("/api/state").json()
    store.close()

    reopened = DreamStore.open(cfg.db_path)
    seed_display_settings(reopened, cfg)  # startup re-seeds; must not overwrite
    after = TestClient(create_dream_app(reopened, cfg, EventBus())).get("/api/state").json()

    assert after == before
    reopened.close()
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_dream_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kg2.server'`

- [ ] **Step 3: Implement `kg2/server.py`**

```python
"""Tool 2's own web server: two pages, one SSE stream, its own operator API.

Tool 1's operator UI keeps its deliberate sparseness („the one live control",
T1§7) and is NOT extended — Tool 2 gets its own interface (spec §7).

Flow control („pause", „dream now") goes through the STORE, not through a
controller object handed to this app. One mechanism instead of two: it survives
a restart for free (spec §8), and this server needs no reference to the watcher
at all, so a wedged watcher cannot take the operator UI down with it.

`kg.bus.EventBus` is imported rather than copied — spec §3 permits pure helpers
from `kg`, and EventBus is pure asyncio with no store, core or server
dependency. Each process instantiates its own.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

FRONTEND = Path(__file__).resolve().parent.parent / "frontend2"


class DisplaySettings(BaseModel):
    """Spec §7's display settings. Every field optional — the operator UI sends
    one control at a time, and a partial update must not reset its neighbours."""

    question_visible: bool | None = None
    # 0 = permanent. The upper bound is a whole exhibition day: anything larger
    # is a typo, and a question that hides after 30 hours never hides.
    question_seconds: int | None = Field(default=None, ge=0, le=36000)
    # Never 0: a 0 ms "cross-fade" is a cut, and Birk ruled out anything but a
    # fade (spec §6). The upper bound keeps a stray value from leaving the wall
    # mid-dissolve for half a minute.
    fade_ms: int | None = Field(default=None, ge=100, le=10000)
    # Never 0 (the strip is the evidence and may not vanish) and never so large
    # that the strip swallows the dream it is evidence for (spec §6: asymmetric
    # by design).
    strip_ratio: float | None = Field(default=None, ge=0.05, le=0.5)
    typewriter: bool | None = None


class PauseFlag(BaseModel):
    paused: bool


class DiscardFlag(BaseModel):
    dream_id: str
    discarded: bool = True


_DEFAULTS = {
    "question_visible": ("default_question_visible", bool),
    "question_seconds": ("default_question_seconds", int),
    "fade_ms": ("default_fade_ms", int),
    "strip_ratio": ("default_strip_ratio", float),
    "typewriter": ("default_typewriter", bool),
}


def seed_display_settings(store, cfg) -> None:
    """Apply config's start values on a fresh database only.

    On a restart the operator's live setting is already stored and must win —
    the same rule Tool 1 holds for `min_mentions` (T1§7, §10.5).
    """
    for key, (attribute, kind) in _DEFAULTS.items():
        value = getattr(cfg, attribute)
        store.set_setting_default(key, "1" if kind is bool and value else
                                  "0" if kind is bool else str(value))
    store.set_setting_default("paused", "0")
    store.set_setting_default("dream_requested", "0")


def dream_payload(dream) -> dict | None:
    """What screen B needs, and nothing more.

    Deliberately WITHOUT the prompts: showing stage 2's prompt would put
    lighting instructions on the wall (spec §5.2). The operator UI reads the
    full record from /api/dreams instead.
    """
    if dream is None:
        return None
    return {
        "id": dream.id,
        "created_at": dream.created_at,
        "sentence": dream.sentence,
        "image": f"/media/images/{dream.image_path}" if dream.image_path else None,
    }


def dream_state(store, cfg) -> dict:
    return {
        "question": cfg.guiding_question,
        "question_visible": store.get_setting("question_visible", "1") == "1",
        "question_seconds": int(store.get_setting("question_seconds", "0")),
        "fade_ms": int(store.get_setting("fade_ms", str(cfg.default_fade_ms))),
        "strip_ratio": float(store.get_setting("strip_ratio", str(cfg.default_strip_ratio))),
        "typewriter": store.get_setting("typewriter", "0") == "1",
        "paused": store.get_setting("paused", "0") == "1",
        "current": dream_payload(store.current_dream()),
        "history": [dream_payload(dream) for dream in store.history()],
    }


def broadcast_dream_state(store, cfg, bus) -> None:
    bus.publish({"type": "state", "state": dream_state(store, cfg)})


def create_dream_app(store, cfg, bus) -> FastAPI:
    app = FastAPI(title="Kollektivtraum")
    app.mount("/static", StaticFiles(directory=FRONTEND / "static"), name="static")
    app.mount("/media/images", StaticFiles(directory=cfg.image_dir), name="images")

    @app.get("/")
    def index() -> RedirectResponse:
        return RedirectResponse("/dream")

    @app.get("/dream")
    def dream_page() -> FileResponse:
        return FileResponse(FRONTEND / "dream.html")

    @app.get("/operator")
    def operator_page() -> FileResponse:
        return FileResponse(FRONTEND / "operator.html")

    @app.get("/api/state")
    def api_state() -> dict:
        return dream_state(store, cfg)

    @app.get("/api/dreams")
    def api_dreams() -> JSONResponse:
        """The full record, for the operator UI only (spec §5.3, §7).

        Includes failed and discarded rows: the display filters, the record
        does not.
        """
        return JSONResponse(
            {
                "dreams": [
                    {
                        "id": d.id,
                        "created_at": d.created_at,
                        "sentence": d.sentence,
                        "image": f"/media/images/{d.image_path}" if d.image_path else None,
                        "status": d.status,
                        "discarded": d.discarded,
                        "error": d.error,
                        "person_count": d.person_count,
                        "term_count": d.term_count,
                        "edge_count": d.edge_count,
                        "contradiction": d.contradiction,
                        "stage1_prompt": d.stage1_prompt,
                        "stage2_prompt": d.stage2_prompt,
                        "condense_model": d.condense_model,
                        "image_model": d.image_model,
                    }
                    for d in store.all_dreams()
                ]
            }
        )

    @app.post("/api/display")
    def api_display(payload: DisplaySettings) -> dict:
        for key, value in payload.model_dump(exclude_none=True).items():
            store.set_setting(key, "1" if value is True else "0" if value is False else str(value))
        broadcast_dream_state(store, cfg, bus)
        return {"ok": True}

    @app.post("/api/dream_now")
    def api_dream_now() -> dict:
        """Spec §7. A flag, not a call: the watcher owns the cycle, and this
        server must stay usable even when the watcher is wedged."""
        store.set_setting("dream_requested", "1")
        return {"ok": True}

    @app.post("/api/pause")
    def api_pause(payload: PauseFlag) -> dict:
        store.set_setting("paused", "1" if payload.paused else "0")
        broadcast_dream_state(store, cfg, bus)
        return {"ok": True}

    @app.post("/api/discard")
    def api_discard(payload: DiscardFlag) -> dict:
        """Spec §7: removes the dream from the large screen AND from the strip
        in one step. The row is kept — the record stays honest."""
        if store.get_dream(payload.dream_id) is None:
            raise HTTPException(status_code=400, detail=f"no dream {payload.dream_id}")
        store.set_discarded(payload.dream_id, payload.discarded)
        broadcast_dream_state(store, cfg, bus)
        return {"ok": True}

    @app.get("/events")
    async def events() -> StreamingResponse:
        queue = bus.subscribe()

        async def stream():
            try:
                yield _sse({"type": "state", "state": dream_state(store, cfg)})
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

- [ ] **Step 4: Create placeholder pages so the routes resolve**

`create_dream_app` mounts `frontend2/static` and serves two HTML files at import time; Tasks 12 and 13 build them properly. Create the minimum now so this task's tests can pass:

```bash
mkdir -p frontend2/static
printf '<!doctype html>\n<html lang="de"><meta charset="utf-8"><title>Kollektivtraum</title>\n' > frontend2/dream.html
printf '<!doctype html>\n<html lang="de"><meta charset="utf-8"><title>Kollektivtraum — Operator</title>\n' > frontend2/operator.html
printf '/* Task 12 */\n' > frontend2/static/dream.css
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_dream_server.py -v`
Expected: PASS (22 tests)

- [ ] **Step 6: Commit**

```bash
git add kg2/server.py frontend2/ tests/test_dream_server.py
git commit -m "feat: Tool 2's own server, SSE and operator API

Flow control goes through the store rather than an object handed to the app, so
pause and 'dream now' survive a restart and a wedged watcher cannot take the
operator UI down with it. No route can change the guiding question or the
register — spec 7 makes both morning settings, and a test asserts the absence."
```

---

### Task 11: The watcher and the entrypoint

**Files:**
- Create: `kg2/watcher.py`, `kg2/__main__.py`
- Test: `tests/test_dream_watcher.py`

**Interfaces:**
- Consumes: Tasks 2, 3, 4, 5, 9, 10.
- Produces:
  - `kg2.watcher.DreamWatcher(cfg, store, bus, llm, *, fetch=fetch_graph, cycle=run_dream, clock=time.time)` with `async tick() -> Dream | None` and `async run()`
  - CLI: `uv run python -m kg2 [--config config2.toml]`

The integration point. Spec §11's integration requirement lands here: **one dream per absorbed interview, floor respected, none during silence.**

Two ordering decisions that are bugs if reversed:

- **Fetch before consuming the „dream now" flag.** If the flag were read first and Tool 1 happened to be unreachable on that tick, the operator's button press would be consumed and silently lost. Fetch first; if there is no graph, do nothing at all and leave the flag standing.
- **Adopt the floor stamp before running the cycle, and the seen set only after it succeeds.** That is §8's „retry at the next trigger — never a retry storm" expressed exactly.

The cycle runs in a thread (two cloud calls, up to minutes), so the `on_sentence` callback must reach the bus through `loop.call_soon_threadsafe` — the bus's queues belong to the server's event loop, and poking them from another thread is not thread-safe. `sim/prerender.py` hit and documented this exact hazard.

- [ ] **Step 1: Write the failing test**

`tests/test_dream_watcher.py`:

```python
"""Spec §11's integration requirements: one dream per absorbed interview, the
floor respected, and nothing at all during silence."""

from __future__ import annotations

import pytest

from kg.bus import EventBus
from kg2.config import DreamConfig
from kg2.models import Dream
from kg2.server import seed_display_settings
from kg2.store import DreamStore
from kg2.watcher import DreamWatcher


def graph(persons_with_edges, bare_persons=(), generated_at=1000.0) -> dict:
    nodes = [
        {"id": pid, "type": "person", "portrait": None, "created_at": 1.0,
         "hidden": False, "x": None, "y": None}
        for pid in list(persons_with_edges) + list(bare_persons)
    ] + [
        {"id": "t1", "type": "term", "label": "Weiterbauen im Bestand",
         "mentions": max(1, len(persons_with_edges)), "created_at": 2.0,
         "hidden": False, "x": None, "y": None}
    ]
    return {
        "version": 1, "generated_at": generated_at, "min_mentions": 1, "nodes": nodes,
        "edges": [
            {"id": f"e{i}", "source": pid, "target": "t1"}
            for i, pid in enumerate(persons_with_edges, 1)
        ],
        "quotes": [],
    }


class Harness:
    """A watcher wired to a fake clock, a fake Tool 1 and a counting cycle."""

    def __init__(self, tmp_path, **cfg_overrides):
        self.cfg = DreamConfig(data_dir=tmp_path / "dream", **cfg_overrides)
        self.store = DreamStore.open(self.cfg.db_path)
        seed_display_settings(self.store, self.cfg)
        self.bus = EventBus()
        self.now = 1000.0
        self.graph = graph([])
        self.fail_next = False
        self.cycles: list[tuple[float, tuple]] = []
        self.watcher = DreamWatcher(
            self.cfg, self.store, self.bus, llm=object(),
            fetch=self._fetch, cycle=self._cycle, clock=lambda: self.now,
        )

    def _fetch(self, url, timeout):
        return self.graph

    def _cycle(self, store, cfg, llm, graph, now, **kwargs):
        from kg2.trigger import absorbed_persons
        from kg2.weighting import build_material

        material = build_material(graph)
        self.cycles.append((now, tuple(sorted(absorbed_persons(graph)))))
        dream = store.create_dream(
            created_at=now, graph_generated_at=material.generated_at,
            person_count=material.person_count, term_count=material.term_count,
            edge_count=material.edge_count, contradiction=False,
            guiding_question=cfg.guiding_question,
            absorbed_persons=sorted(absorbed_persons(graph)),
        )
        if self.fail_next:
            store.fail_dream(dream.id, "stubbed failure")
            return None
        store.set_stage1(dream.id, prompt="S1", sentence=f"Traum {dream.id}", model="m")
        store.finish_dream(dream.id, image_path=f"{dream.id}.png")
        return store.get_dream(dream.id)

    def close(self):
        self.store.close()


@pytest.fixture()
def harness(tmp_path):
    h = Harness(tmp_path)
    yield h
    h.close()


# -- the core requirement ---------------------------------------------------


async def test_one_dream_per_absorbed_interview(harness):
    for index in range(1, 5):
        harness.graph = graph([f"p{i}" for i in range(1, index + 1)])
        harness.now += 300.0
        await harness.watcher.tick()

    assert len(harness.cycles) == 4
    assert len(harness.store.visible_dreams()) == 4


async def test_a_bare_person_node_produces_no_dream(harness):
    """Spec §4.1, end to end: Tool 1 published the photo, not the interview."""
    harness.graph = graph([], bare_persons=["p1"])

    assert await harness.watcher.tick() is None
    assert harness.cycles == []


async def test_the_dream_arrives_once_the_pipeline_has_run(harness):
    harness.graph = graph([], bare_persons=["p1"])
    await harness.watcher.tick()

    harness.now += 30.0
    harness.graph = graph(["p1"])
    dream = await harness.watcher.tick()

    assert dream is not None
    assert harness.cycles == [(1030.0, ("p1",))]


async def test_nothing_happens_during_silence(harness):
    harness.graph = graph(["p1"])
    await harness.watcher.tick()

    for _ in range(20):
        harness.now += 300.0
        assert await harness.watcher.tick() is None

    assert len(harness.cycles) == 1


async def test_the_floor_is_respected(harness):
    harness.graph = graph(["p1"])
    await harness.watcher.tick()

    harness.now += 100.0
    harness.graph = graph(["p1", "p2"])
    assert await harness.watcher.tick() is None

    harness.now += 141.0  # total 241 s > 240 s floor
    assert await harness.watcher.tick() is not None
    assert len(harness.cycles) == 2


async def test_interviews_inside_the_floor_collapse_into_one_dream(harness):
    harness.graph = graph(["p1"])
    await harness.watcher.tick()

    for index in (2, 3, 4):
        harness.now += 30.0
        harness.graph = graph([f"p{i}" for i in range(1, index + 1)])
        assert await harness.watcher.tick() is None

    harness.now += 200.0
    await harness.watcher.tick()

    assert len(harness.cycles) == 2
    assert harness.cycles[1][1] == ("p1", "p2", "p3", "p4")


# -- Tool 1 unreachable -----------------------------------------------------


async def test_a_dead_tool_1_produces_no_dream_and_no_exception(harness):
    """Spec §8: „Poll keeps failing quietly." Correct — nothing new was said."""
    harness.watcher.fetch = lambda url, timeout: None

    for _ in range(5):
        harness.now += 300.0
        assert await harness.watcher.tick() is None

    assert harness.cycles == []


async def test_a_dead_tool_1_does_not_swallow_a_pending_dream_now(harness):
    """Fetch BEFORE consuming the flag. Otherwise an outage on the very tick
    the operator pressed the button loses the press silently."""
    harness.graph = graph(["p1"])
    harness.store.set_setting("dream_requested", "1")
    harness.watcher.fetch = lambda url, timeout: None

    await harness.watcher.tick()
    assert harness.store.get_setting("dream_requested", "0") == "1"

    harness.watcher.fetch = lambda url, timeout: harness.graph
    assert await harness.watcher.tick() is not None


async def test_the_display_is_untouched_while_tool_1_is_gone(harness):
    harness.graph = graph(["p1"])
    await harness.watcher.tick()
    harness.watcher.fetch = lambda url, timeout: None

    harness.now += 5000.0
    await harness.watcher.tick()

    assert harness.store.current_dream().sentence == "Traum d1"


# -- flow control -----------------------------------------------------------


async def test_pause_stops_new_dreams(harness):
    harness.store.set_setting("paused", "1")
    harness.graph = graph(["p1"])

    harness.now += 300.0
    assert await harness.watcher.tick() is None
    assert harness.cycles == []


async def test_resume_picks_the_pending_interview_back_up(harness):
    """Pausing must not lose material, for the same reason the floor must not."""
    harness.store.set_setting("paused", "1")
    harness.graph = graph(["p1"])
    harness.now += 300.0
    await harness.watcher.tick()

    harness.store.set_setting("paused", "0")
    assert await harness.watcher.tick() is not None
    assert harness.cycles[0][1] == ("p1",)


async def test_dream_now_ignores_the_floor(harness):
    harness.graph = graph(["p1"])
    await harness.watcher.tick()

    harness.now += 5.0
    harness.store.set_setting("dream_requested", "1")

    assert await harness.watcher.tick() is not None
    assert len(harness.cycles) == 2


async def test_dream_now_works_while_paused(harness):
    """The operator pressed it deliberately (spec §7)."""
    harness.store.set_setting("paused", "1")
    harness.graph = graph(["p1"])
    harness.store.set_setting("dream_requested", "1")

    assert await harness.watcher.tick() is not None


async def test_dream_now_fires_only_once_per_press(harness):
    harness.graph = graph(["p1"])
    harness.store.set_setting("dream_requested", "1")
    await harness.watcher.tick()

    harness.now += 1.0
    assert await harness.watcher.tick() is None
    assert len(harness.cycles) == 1


# -- failures ---------------------------------------------------------------


async def test_a_failed_dream_retries_at_the_next_trigger_not_immediately(harness):
    """Spec §8: „Retry at the next trigger — never a retry storm."""
    harness.graph = graph(["p1"])
    harness.fail_next = True
    await harness.watcher.tick()
    assert len(harness.cycles) == 1

    harness.now += 10.0
    assert await harness.watcher.tick() is None  # inside the floor
    assert len(harness.cycles) == 1

    harness.now += 240.0
    harness.fail_next = False
    assert await harness.watcher.tick() is not None
    assert harness.cycles[1][1] == ("p1",)  # the SAME material, retried


async def test_a_crashing_cycle_does_not_kill_the_poll_loop(harness):
    def boom(*args, **kwargs):
        raise RuntimeError("unexpected")

    harness.watcher.cycle = boom
    harness.graph = graph(["p1"])

    assert await harness.watcher.tick() is None

    harness.watcher.cycle = harness._cycle
    harness.now += 300.0
    assert await harness.watcher.tick() is not None


# -- restart ----------------------------------------------------------------


async def test_a_restart_does_not_re_dream_the_whole_day(tmp_path):
    """Spec §8: everything needed is in SQLite; nothing lives only in memory."""
    first = Harness(tmp_path)
    first.graph = graph(["p1", "p2", "p3"])
    await first.watcher.tick()
    assert len(first.cycles) == 1
    first.close()

    second = Harness(tmp_path)
    second.now = 99999.0
    second.graph = graph(["p1", "p2", "p3"])

    assert await second.watcher.tick() is None
    assert second.cycles == []
    second.close()


async def test_a_restart_still_dreams_for_an_interview_that_arrived_meanwhile(tmp_path):
    first = Harness(tmp_path)
    first.graph = graph(["p1"])
    await first.watcher.tick()
    first.close()

    second = Harness(tmp_path)
    second.now = 99999.0
    second.graph = graph(["p1", "p2"])

    assert await second.watcher.tick() is not None
    assert second.cycles[0][1] == ("p1", "p2")
    second.close()


# -- the SSE push -----------------------------------------------------------


async def test_a_finished_dream_is_pushed_to_the_display(harness):
    queue = harness.bus.subscribe()
    harness.graph = graph(["p1"])

    await harness.watcher.tick()

    event = queue.get_nowait()
    assert event["type"] == "state"
    assert event["state"]["current"]["sentence"] == "Traum d1"


async def test_a_failed_dream_pushes_nothing_new_to_the_display(harness):
    """Spec §8: the screen looks calm, not broken. A push with an unchanged
    current dream is harmless but pointless; a push is only made on success."""
    harness.fail_next = True
    harness.graph = graph(["p1"])
    queue = harness.bus.subscribe()

    await harness.watcher.tick()

    assert queue.empty()
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_dream_watcher.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kg2.watcher'`

- [ ] **Step 3: Implement `kg2/watcher.py`**

```python
"""The poll loop: Tool 1's graph in, one dream out (spec §4.1).

Polling a complete-state endpoint rather than subscribing to Tool 1's `/events`
(spec §4.1): it survives a Tool 1 restart with no reconnect logic, it is the
pattern CR-1 already chose, and at a 240 s floor a 5 s detection lag is
invisible. SSE stays available as a later optimisation; nothing here depends on
it.
"""

from __future__ import annotations

import asyncio
import logging
import time

from kg2.cycle import run_dream
from kg2.graph_client import fetch_graph
from kg2.server import broadcast_dream_state
from kg2.trigger import evaluate, resume_state

log = logging.getLogger(__name__)


class DreamWatcher:
    def __init__(self, cfg, store, bus, llm, *, fetch=fetch_graph, cycle=run_dream,
                 clock=time.time) -> None:
        self.cfg = cfg
        self.store = store
        self.bus = bus
        self.llm = llm
        self.fetch = fetch
        self.cycle = cycle
        self.clock = clock
        # A restart is a resume, not a reset (spec §8). Without this the
        # watcher would either dream once for all 40 interviews of the day or
        # never dream again, depending on which way the mistake went.
        self.state = resume_state(store.all_dreams())

    async def tick(self):
        """One poll. Returns the finished Dream, or None."""
        graph = await asyncio.to_thread(
            self.fetch, self.cfg.graph_url, self.cfg.fetch_timeout_s
        )
        if graph is None:
            # Tool 1 unreachable. Quiet, and deliberately BEFORE the flag is
            # read: consuming „dream now" on a tick that cannot fetch would
            # swallow the operator's button press with nothing on screen to
            # say so (spec §8).
            return None

        forced = self.store.get_setting("dream_requested", "0") == "1"
        if forced:
            self.store.set_setting("dream_requested", "0")
        elif self.store.get_setting("paused", "0") == "1":
            # Paused blocks the automatic cycle only. „Dream now" was pressed
            # deliberately and works regardless (spec §7).
            return None

        decision = evaluate(
            self.state, graph, self.clock(), self.cfg.min_interval_s, force=forced
        )
        if not decision.fire:
            return None

        # The floor stamp is adopted BEFORE the cycle and whatever its outcome:
        # a failure must still space out its retry (spec §8).
        self.state = self.state.with_dream_started(decision.started_at)

        loop = asyncio.get_running_loop()

        def announce(sentence: str) -> None:
            # The bus's queues belong to the server's event loop; poking them
            # from this worker thread is not thread-safe. Same hazard, same fix
            # as sim/prerender.py's `publish`.
            loop.call_soon_threadsafe(
                self.bus.publish, {"type": "dreaming", "sentence": sentence}
            )

        try:
            dream = await asyncio.to_thread(
                self.cycle,
                self.store, self.cfg, self.llm, graph, decision.started_at,
                on_sentence=announce,
            )
        except Exception as exc:  # run_dream does not raise; a stub might
            log.error("dream cycle raised: %s", exc)
            return None

        if dream is None:
            # Failed. The seen set is NOT advanced, so the same material is
            # retried at the next trigger past the floor (spec §8).
            return None

        self.state = self.state.with_absorbed(decision.absorbed)
        broadcast_dream_state(self.store, self.cfg, self.bus)
        return dream

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception as exc:  # a bad poll must never kill the station
                log.error("watcher tick failed: %s", exc)
            await asyncio.sleep(self.cfg.poll_interval_s)
```

- [ ] **Step 4: Implement `kg2/__main__.py`**

```python
"""Entrypoint: one process, two concerns (the poll loop and the HTTP server)."""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

import uvicorn

from kg.__main__ import resolved_host
from kg.bus import EventBus
from kg.llm import LLMClient
from kg2.config import load_dream_config
from kg2.server import create_dream_app, seed_display_settings
from kg2.store import DreamStore
from kg2.watcher import DreamWatcher


async def main_async(args) -> None:
    cfg = load_dream_config(Path(args.config) if args.config else None)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    store = DreamStore.open(cfg.db_path)
    seed_display_settings(store, cfg)
    bus = EventBus()
    # kg.llm is a pure client wrapper — no store, no core, no server (spec §3).
    llm = LLMClient(
        model=cfg.condense_model,
        effort=cfg.condense_effort,
        max_tokens=cfg.condense_max_tokens,
        api_key=cfg.anthropic_api_key,
    )

    app = create_dream_app(store, cfg, bus)
    server = uvicorn.Server(
        uvicorn.Config(app, host=cfg.server_host, port=cfg.server_port, log_level="info")
    )

    tasks = [asyncio.create_task(server.serve())]
    if not args.no_watch:
        watcher = DreamWatcher(cfg, store, bus, llm)
        tasks.append(asyncio.create_task(watcher.run()))

    shown = resolved_host(cfg.server_host)
    print(f"dream:     http://{shown}:{cfg.server_port}/dream")
    print(f"operator:  http://{shown}:{cfg.server_port}/operator")
    print(f"tool 1:    {cfg.graph_url}")
    await asyncio.gather(*tasks)


def main() -> None:
    parser = argparse.ArgumentParser(prog="kg2")
    parser.add_argument("--config", default=None)
    parser.add_argument(
        "--no-watch",
        action="store_true",
        help="serve the pages without polling Tool 1 — for a smoke test with "
        "no exhibition machine and no credentials",
    )
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_dream_watcher.py -v`
Expected: PASS (20 tests)

- [ ] **Step 6: Smoke-test the entrypoint with no Tool 1 and no credentials**

```bash
timeout 5 uv run python -m kg2 --config config2.example.toml --no-watch
```
Expected: prints the three URLs and serves until the timeout kills it. No traceback.

- [ ] **Step 7: Commit**

```bash
git add kg2/watcher.py kg2/__main__.py tests/test_dream_watcher.py
git commit -m "feat: the watcher and the kg2 entrypoint

One dream per absorbed interview, floor respected, none during silence. Fetches
before consuming the 'dream now' flag so an outage cannot swallow the operator's
press, and adopts the floor stamp before the cycle but the seen set only after
it succeeds — which is spec 8's retry rule expressed exactly."
```

---

### Task 12: Screen B — the page

**Files:**
- Create: `frontend2/dream.html`, `frontend2/static/dream.js`, `frontend2/static/dream.css`, `frontend2/static/dream-harness.html`
- Test: `tests/test_dream_page.py`

**Interfaces:**
- Consumes: Task 10 (`/api/state`, `/events`, `/media/images`).
- Produces: `frontend2/static/dream.js` exporting `createDreamView(root)`, which returns a handle with `applyState(state)`, `showDreaming(sentence)`, and the read-only properties `current`, `historyLength`, `fading`. The page sets `window.kgDream` and `window.kgDreamReady`.

Layout (§6), top to bottom: the **guiding question**, the **current image** (large, dominant), the **sentence** as a fixed line beneath it, then the **history strip** — every earlier dream of the day, smaller and dimmer, oldest to newest.

Four rules that are each a test below:

- **Asymmetric by design.** The current dream is the subject; the strip is the evidence. Not a gallery of equals.
- **Cross-fades, explicitly not morphs** (Birk). Two stacked images, opacity only. Default 1.2 s.
- **The typewriter is an animation layer over the baseline, not a second layout.** While stage 2 runs, the sentence builds up word by word in a larger centred position; when the image arrives it settles into the same fixed line the baseline uses. Turning it off is a switch, not a rebuild — and the „generation takes 60 s" risk is carried by the baseline either way.
- **No dashboard** (§6): no counters, no progress bars, no „generating…" spinner. The only motion is the fade and, optionally, the typewriter.

**Sizing follows Tool 1's rule** (§6, T1§11): everything in viewport-relative units, so the strip's thumbnail size is a fraction of screen height and a different screen changes nothing.

- [ ] **Step 1: Write the failing test**

`tests/test_dream_page.py`:

```python
"""Spec §6 — screen B. Driven through the harness, exactly as Tool 1 drives
its renderer: no server, no EventSource, just the view and a state object."""

from __future__ import annotations

import pytest


def state(current=None, history=(), **overrides):
    base = {
        "question": "Wie leben und bauen wir in zehn Jahren?",
        "question_visible": True,
        "question_seconds": 0,
        "fade_ms": 1200,
        "strip_ratio": 0.22,
        "typewriter": False,
        "paused": False,
        "current": current,
        "history": list(history),
    }
    base.update(overrides)
    return base


def dream(index, sentence=None):
    return {
        "id": f"d{index}",
        "created_at": 1000.0 + index,
        "sentence": sentence or f"Traum {index}",
        # A 1x1 transparent GIF: a real, decodable image with no network.
        "image": "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7",
    }


@pytest.fixture()
def view(page, static_server):
    page.goto(f"{static_server}/frontend2/static/dream-harness.html")
    page.wait_for_function("window.kgDream !== undefined")
    return page


def apply(page, value):
    page.evaluate("(s) => window.kgDream.applyState(s)", value)
    page.wait_for_function("() => window.kgDream.fading === false", timeout=10000)


# -- the baseline layout ----------------------------------------------------


def test_the_question_the_image_the_sentence_and_the_strip_are_all_present(view):
    apply(view, state(current=dream(3), history=[dream(1), dream(2)]))

    assert view.locator("#question").inner_text() == "Wie leben und bauen wir in zehn Jahren?"
    assert view.locator("#sentence").inner_text() == "Traum 3"
    assert view.locator("#strip li").count() == 2


def test_the_strip_runs_oldest_to_newest(view):
    """Spec §6. The strip is a time axis, not a stack of most-recent-first."""
    apply(view, state(current=dream(3), history=[dream(1), dream(2)]))

    labels = view.locator("#strip li img").evaluate_all("els => els.map(e => e.alt)")
    assert labels == ["Traum 1", "Traum 2"]


def test_the_current_dream_is_not_repeated_in_the_strip(view):
    apply(view, state(current=dream(3), history=[dream(1), dream(2)]))

    assert view.locator("#strip li").count() == 2
    assert view.locator("#strip").inner_html().count("Traum 3") == 0


def test_the_current_image_dominates_the_strip(view):
    """Spec §6: asymmetric by design — the current dream is the subject."""
    apply(view, state(current=dream(3), history=[dream(i) for i in range(1, 6)]))

    stage = view.locator("#stage").bounding_box()
    thumb = view.locator("#strip li").first.bounding_box()
    assert stage["height"] > thumb["height"] * 3


def test_the_page_is_readable_with_no_dreams_at_all(view):
    """09:00, before the first interview. Empty, not broken."""
    apply(view, state())

    assert view.locator("#sentence").inner_text() == ""
    assert view.locator("#strip li").count() == 0
    assert view.locator("#question").is_visible() is True


def test_a_full_strip_of_forty_dreams_still_fits_on_screen(view):
    """The end of the festival day is the hard case (spec §11's visual series)."""
    apply(view, state(current=dream(41), history=[dream(i) for i in range(1, 41)]))

    assert view.locator("#strip li").count() == 40
    strip = view.locator("#strip").bounding_box()
    assert strip["y"] + strip["height"] <= 1081  # inside a 1080-high viewport


# -- sizing (spec §6 / T1§11) ----------------------------------------------


def test_every_size_is_viewport_relative(view):
    """Tool 1's rule: model units scaled to the viewport, so a different screen
    changes nothing. Measured by resizing rather than by reading the CSS."""
    apply(view, state(current=dream(1), history=[dream(0)]))
    small = view.locator("#strip li").first.bounding_box()["height"]

    view.set_viewport_size({"width": 3840, "height": 2160})
    view.wait_for_timeout(200)
    large = view.locator("#strip li").first.bounding_box()["height"]

    assert large == pytest.approx(small * 2, rel=0.05)


def test_the_strip_ratio_control_changes_the_thumbnail_height(view):
    apply(view, state(current=dream(1), history=[dream(0)], strip_ratio=0.15))
    thin = view.locator("#strip li").first.bounding_box()["height"]

    apply(view, state(current=dream(1), history=[dream(0)], strip_ratio=0.35))
    thick = view.locator("#strip li").first.bounding_box()["height"]

    assert thick > thin * 1.8


# -- the guiding question (spec §7) ----------------------------------------


def test_the_question_can_be_switched_off(view):
    apply(view, state(current=dream(1), question_visible=False))

    assert view.locator("#question").is_visible() is False


def test_the_question_auto_hides_after_the_configured_seconds(view):
    apply(view, state(current=dream(1), question_visible=True, question_seconds=1))

    assert view.locator("#question").is_visible() is True
    view.wait_for_function(
        "() => !document.getElementById('question').checkVisibility()", timeout=5000
    )


def test_zero_seconds_means_permanent(view):
    apply(view, state(current=dream(1), question_visible=True, question_seconds=0))
    view.wait_for_timeout(1500)

    assert view.locator("#question").is_visible() is True


# -- the cross-fade (spec §6, Birk: not a morph) ---------------------------


def test_a_new_dream_cross_fades_rather_than_cutting(view):
    apply(view, state(current=dream(1)))

    view.evaluate("(s) => window.kgDream.applyState(s)", state(current=dream(2), history=[dream(1)]))
    view.wait_for_timeout(150)  # mid-fade

    opacities = view.locator("#stage .frame").evaluate_all(
        "els => els.map(e => Number(getComputedStyle(e).opacity))"
    )
    # Both frames on screen at once is what makes it a fade and not a cut.
    assert sum(1 for value in opacities if 0 < value < 1) >= 1
    view.wait_for_function("() => window.kgDream.fading === false", timeout=10000)


def test_the_fade_duration_follows_the_operator_setting(view):
    apply(view, state(current=dream(1), fade_ms=400))

    duration = view.locator("#stage .frame").first.evaluate(
        "e => getComputedStyle(e).transitionDuration"
    )

    assert duration.startswith("0.4")


def test_the_transition_is_opacity_only_never_a_transform(view):
    """Birk ruled out morphs explicitly (spec §6, brainstorm §2). A transform
    in the transition list is how a morph sneaks back in."""
    apply(view, state(current=dream(1)))

    properties = view.locator("#stage .frame").first.evaluate(
        "e => getComputedStyle(e).transitionProperty"
    )

    assert "opacity" in properties
    assert "transform" not in properties


def test_re_applying_the_same_state_does_not_re_fade(view):
    """The state push arrives on every control change too. Re-fading the image
    each time an operator nudges the strip ratio would be visible on the wall."""
    apply(view, state(current=dream(1)))
    first = view.evaluate("() => window.kgDream.current")

    apply(view, state(current=dream(1), strip_ratio=0.3))

    assert view.evaluate("() => window.kgDream.current") == first
    assert view.evaluate("() => window.kgDream.fading") is False


# -- the typewriter (spec §6) ----------------------------------------------


def test_the_typewriter_builds_the_sentence_up_while_stage_2_runs(view):
    apply(view, state(current=dream(1), typewriter=True))

    view.evaluate("() => window.kgDream.showDreaming('Der Beton träumt von Wald')")
    view.wait_for_timeout(120)
    partial = view.locator("#typewriter").inner_text()
    view.wait_for_function(
        "() => document.getElementById('typewriter').innerText.includes('Wald')", timeout=10000
    )

    assert partial != "Der Beton träumt von Wald"
    assert view.locator("#typewriter").is_visible() is True


def test_the_typewriter_settles_into_the_baseline_line_when_the_image_arrives(view):
    """Spec §6: one layout with an optional animation, not a second layout."""
    apply(view, state(current=dream(1), typewriter=True))
    view.evaluate("() => window.kgDream.showDreaming('Der Beton träumt von Wald')")
    view.wait_for_timeout(300)

    apply(view, state(current=dream(2, "Der Beton träumt von Wald"), history=[dream(1)],
                      typewriter=True))

    assert view.locator("#typewriter").is_visible() is False
    assert view.locator("#sentence").inner_text() == "Der Beton träumt von Wald"


def test_the_typewriter_switch_off_leaves_the_baseline_intact(view):
    """Turning it off is a switch, not a rebuild (spec §6)."""
    apply(view, state(current=dream(1), typewriter=False))

    view.evaluate("() => window.kgDream.showDreaming('sollte nichts tun')")
    view.wait_for_timeout(300)

    assert view.locator("#typewriter").is_visible() is False
    assert view.locator("#sentence").inner_text() == "Traum 1"


def test_the_baseline_carries_the_sixty_second_risk_either_way(view):
    """Spec §6 / brainstorm §3: while a dream is generating, the PREVIOUS image
    and sentence stay up. Nothing blanks, with or without the typewriter."""
    for typewriter in (False, True):
        apply(view, state(current=dream(1), typewriter=typewriter))
        view.evaluate("() => window.kgDream.showDreaming('unterwegs')")
        view.wait_for_timeout(200)

        assert view.locator("#sentence").inner_text() == "Traum 1"
        assert view.locator("#stage .frame.visible").count() == 1


# -- no dashboard (spec §6) ------------------------------------------------


def test_there_is_no_counter_no_progress_bar_and_no_spinner(view):
    apply(view, state(current=dream(3), history=[dream(1), dream(2)]))

    html = view.locator("body").inner_html()
    for forbidden in ("progress", "spinner", "loading", "generiert", "Traum 3 von"):
        assert forbidden not in html.lower()
    assert view.locator("progress").count() == 0
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_dream_page.py -v`
Expected: FAIL — the harness page 404s, so `window.kgDream` never appears.

- [ ] **Step 3: Write `frontend2/static/dream.css`**

```css
/* Screen B. Every size is viewport-relative (spec §6, T1§11): the 65" screen's
   resolution is organiser-provided and still open, so nothing may be in
   pixels. --strip-ratio and --fade-ms are set from the operator's state. */

:root {
  --strip-ratio: 0.22;
  --fade-ms: 1200ms;
  --ink: #f2efe9;
  --ground: #0d0e10;
  --dim: 0.55;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

html, body {
  height: 100%;
  background: var(--ground);
  color: var(--ink);
  font-family: "Inter", "Helvetica Neue", system-ui, sans-serif;
  overflow: hidden;
  /* A display, never a control surface (spec §12: no interaction on B). */
  cursor: none;
  user-select: none;
}

#page {
  height: 100vh;
  display: grid;
  /* question / image / sentence / strip. The image row takes what is left,
     which is what makes the layout asymmetric by construction rather than by
     a magic number. */
  grid-template-rows: auto 1fr auto calc(var(--strip-ratio) * 100vh);
  gap: 1.4vh;
  padding: 2.2vh 3vw;
}

#question {
  font-size: 2.6vh;
  font-weight: 500;
  letter-spacing: 0.02em;
  opacity: 0.72;
  text-align: center;
  transition: opacity var(--fade-ms) ease;
}

#question[hidden] { display: none; }

#stage {
  position: relative;
  min-height: 0;
  display: grid;
  place-items: center;
}

/* Two stacked frames, opacity only. A cross-fade, explicitly NOT a morph
   (Birk, spec §6): between two independently generated images a morph is
   either this, or an img2img chain that converges to mush. */
#stage .frame {
  position: absolute;
  inset: 0;
  margin: auto;
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  opacity: 0;
  transition-property: opacity;
  transition-duration: var(--fade-ms);
  transition-timing-function: ease-in-out;
}

#stage .frame.visible { opacity: 1; }

#sentence {
  font-size: 3.1vh;
  line-height: 1.35;
  text-align: center;
  min-height: 4.2vh;
  max-width: 74vw;
  justify-self: center;
}

/* The typewriter is an ANIMATION LAYER over the baseline, not a second layout
   (spec §6): larger, centred, over the stage — and when the image arrives the
   text settles into #sentence, the same fixed line the baseline always uses. */
#typewriter {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 0 8vw;
  font-size: 4.4vh;
  line-height: 1.3;
  text-align: center;
  pointer-events: none;
}

#typewriter[hidden] { display: none; }

#strip {
  list-style: none;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 0.8vw;
  min-height: 0;
  overflow: hidden;
}

/* Smaller and dimmer: the strip is the evidence, not a second gallery. */
#strip li {
  height: calc(var(--strip-ratio) * 100vh - 1.2vh);
  flex: 0 1 auto;
  min-width: 0;
  opacity: var(--dim);
}

#strip li img {
  height: 100%;
  width: 100%;
  object-fit: cover;
  display: block;
}
```

- [ ] **Step 4: Write `frontend2/static/dream.js`**

```javascript
// Screen B (spec §6). One layout, one optional animation, no dashboard.
//
// The page is a pure function of the state the server pushes: applyState()
// is idempotent, so the state event that arrives on every operator control
// change does not re-fade the image. That matters on a wall — a re-fade each
// time someone nudges the strip ratio would be visible from across the room.

const TYPE_MS = 55; // per word, the typewriter's own pace

export function createDreamView(root) {
  const question = root.querySelector('#question');
  const stage = root.querySelector('#stage');
  const sentence = root.querySelector('#sentence');
  const typewriter = root.querySelector('#typewriter');
  const strip = root.querySelector('#strip');
  const frames = [stage.querySelector('#frame-a'), stage.querySelector('#frame-b')];

  let currentId = null;
  let visibleFrame = 0;
  let fading = false;
  let fadeTimer = null;
  let questionTimer = null;
  let typeTimer = null;
  let typewriterEnabled = false;

  function setFade(ms) {
    root.style.setProperty('--fade-ms', `${ms}ms`);
  }

  function applyQuestion(state) {
    question.textContent = state.question || '';
    clearTimeout(questionTimer);
    if (!state.question_visible) {
      question.hidden = true;
      return;
    }
    question.hidden = false;
    // 0 means permanent (spec §7). Anything else hides it after N seconds —
    // Birk's explicit request, so the question can introduce the piece in the
    // morning and then get out of the image's way.
    if (state.question_seconds > 0) {
      questionTimer = setTimeout(() => {
        question.hidden = true;
      }, state.question_seconds * 1000);
    }
  }

  function showImage(url, alt) {
    const next = 1 - visibleFrame;
    const incoming = frames[next];
    incoming.alt = alt || '';
    incoming.src = url;
    // Force a style flush so the browser has the new src laid out before the
    // opacity flip; without it the first fade of a session is a cut.
    void incoming.offsetWidth;
    incoming.classList.add('visible');
    frames[visibleFrame].classList.remove('visible');
    visibleFrame = next;

    fading = true;
    clearTimeout(fadeTimer);
    const ms = parseFloat(getComputedStyle(root).getPropertyValue('--fade-ms')) || 0;
    fadeTimer = setTimeout(() => {
      fading = false;
    }, ms + 40);
  }

  function renderStrip(history) {
    strip.replaceChildren();
    // Oldest to newest (spec §6): the strip is a time axis. It is also the
    // evidence that there was never ONE vision of the future, which only
    // reads if it runs in the direction the day ran.
    history.forEach((dream) => {
      const item = document.createElement('li');
      const image = document.createElement('img');
      image.src = dream.image;
      image.alt = dream.sentence || '';
      item.appendChild(image);
      strip.appendChild(item);
    });
  }

  function stopTypewriter() {
    clearInterval(typeTimer);
    typewriter.hidden = true;
    typewriter.textContent = '';
  }

  function applyState(state) {
    setFade(state.fade_ms);
    root.style.setProperty('--strip-ratio', String(state.strip_ratio));
    typewriterEnabled = Boolean(state.typewriter);
    applyQuestion(state);
    renderStrip(state.history || []);

    const dream = state.current;
    if (!dream) {
      sentence.textContent = '';
      currentId = null;
      return;
    }
    // Idempotent: the same dream re-applied is a no-op for the image, so a
    // control change never re-fades the wall.
    if (dream.id !== currentId) {
      currentId = dream.id;
      stopTypewriter();
      showImage(dream.image, dream.sentence);
    }
    sentence.textContent = dream.sentence || '';
  }

  function showDreaming(text) {
    // Stage 1 has returned and stage 2 is running. The BASELINE carries this
    // moment either way — the previous image and sentence stay exactly where
    // they are (spec §6, brainstorm §3), so a 60 s generation shows nothing
    // unusual. The typewriter is the optional layer on top.
    if (!typewriterEnabled) return;
    const words = String(text).split(/\s+/).filter(Boolean);
    let index = 0;
    typewriter.hidden = false;
    typewriter.textContent = '';
    clearInterval(typeTimer);
    typeTimer = setInterval(() => {
      if (index >= words.length) {
        clearInterval(typeTimer);
        return;
      }
      typewriter.textContent = words.slice(0, ++index).join(' ');
    }, TYPE_MS);
  }

  return {
    applyState,
    showDreaming,
    get current() {
      return currentId;
    },
    get historyLength() {
      return strip.children.length;
    },
    get fading() {
      return fading;
    },
  };
}
```

- [ ] **Step 5: Write `frontend2/dream.html`**

```html
<!doctype html>
<html lang="de">
<meta charset="utf-8">
<title>Kollektivtraum</title>
<!-- Relative asset paths, like Tool 1's pages: served at /dream these resolve
     to /static/… and the harness can load the same module from a file server. -->
<link rel="stylesheet" href="static/dream.css">
<div id="page">
  <div id="question"></div>
  <div id="stage">
    <img class="frame" id="frame-a" alt="">
    <img class="frame" id="frame-b" alt="">
    <div id="typewriter" hidden></div>
  </div>
  <div id="sentence"></div>
  <ul id="strip"></ul>
</div>
<script type="module">
  import { createDreamView } from './static/dream.js';

  const view = createDreamView(document.documentElement);
  window.kgDream = view;
  window.kgDreamReady = false;

  // The state push is complete state, like Tool 1's graph event — there is no
  // delta to miss, so a dropped event costs nothing and a reconnect needs no
  // catch-up logic.
  const events = new EventSource('/events');
  events.onmessage = (message) => {
    const payload = JSON.parse(message.data);
    if (payload.type === 'state') {
      view.applyState(payload.state);
      window.kgDreamReady = true;
    } else if (payload.type === 'dreaming') {
      view.showDreaming(payload.sentence);
    }
  };
</script>
</html>
```

- [ ] **Step 6: Write `frontend2/static/dream-harness.html`**

```html
<!doctype html>
<html lang="de">
<meta charset="utf-8">
<title>dream harness</title>
<!--
  The same markup and the same module as dream.html, WITHOUT the EventSource.
  Tool 1 uses exactly this pattern (frontend/static/render-harness.html): the
  tests drive the view directly, so nothing in them depends on a running
  server, and the thing under test is the real renderer rather than a copy.
-->
<link rel="stylesheet" href="dream.css">
<div id="page">
  <div id="question"></div>
  <div id="stage">
    <img class="frame" id="frame-a" alt="">
    <img class="frame" id="frame-b" alt="">
    <div id="typewriter" hidden></div>
  </div>
  <div id="sentence"></div>
  <ul id="strip"></ul>
</div>
<script type="module">
  import { createDreamView } from './dream.js';
  window.kgDream = createDreamView(document.documentElement);
</script>
</html>
```

- [ ] **Step 7: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_dream_page.py -v`
Expected: PASS (22 tests)

- [ ] **Step 8: Commit**

```bash
git add frontend2/dream.html frontend2/static/dream.js frontend2/static/dream.css \
        frontend2/static/dream-harness.html tests/test_dream_page.py
git commit -m "feat: screen B — question, image, sentence, history strip

Cross-fade only, never a morph (opacity is the sole transition property, and a
test asserts transform is absent). The typewriter is an animation layer over the
baseline, so switching it off is a switch and not a rebuild. applyState is
idempotent, so an operator nudging a control does not re-fade the wall."
```

---

### Task 13: Tool 2's operator UI

**Files:**
- Create: `frontend2/operator.html`, `frontend2/static/operator.js`, `frontend2/static/operator.css`
- Test: `tests/test_dream_operator.py`

**Interfaces:**
- Consumes: Task 10 (`/api/state`, `/api/dreams`, `/api/display`, `/api/dream_now`, `/api/pause`, `/api/discard`, `/events`).
- Produces: `frontend2/static/operator.js` setting `window.kgDreamOperator = { render, renderDreams }`.

Spec §7's interface, and only that:

- **Display settings:** guiding question on / off / auto-hide after N seconds; fade duration; image ↔ history-strip size ratio; typewriter on / off.
- **Flow control:** Dream now · Discard current dream · Pause / resume.
- **Explicitly NOT here:** changing the guiding question, the visual register, or the weighting at runtime. The page displays the question read-only so the operator can *see* what is set, with no control to change it.

Failed writes revert the control to the last state the server actually confirmed — Tool 1's `post()` pattern, copied deliberately: this is a human control surface at an exhibition, and a control showing a change that did not happen is worse than no feedback.

- [ ] **Step 1: Write the failing test**

`tests/test_dream_operator.py`:

```python
"""Spec §7 — Tool 2's own operator interface, and its deliberate limits."""

from __future__ import annotations

import json

import pytest


def state(**overrides):
    base = {
        "question": "Wie leben und bauen wir in zehn Jahren?",
        "question_visible": True,
        "question_seconds": 0,
        "fade_ms": 1200,
        "strip_ratio": 0.22,
        "typewriter": False,
        "paused": False,
        "current": None,
        "history": [],
    }
    base.update(overrides)
    return base


def record(index, status="done", discarded=False):
    return {
        "id": f"d{index}",
        "created_at": 1000.0 + index,
        "sentence": f"Traum {index}",
        "image": "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7",
        "status": status,
        "discarded": discarded,
        "error": None if status != "failed" else "read timeout",
        "person_count": 6,
        "term_count": 5,
        "edge_count": 9,
        "contradiction": True,
        "stage1_prompt": f"S1 für d{index}",
        "stage2_prompt": f"S2 für d{index}",
        "condense_model": "claude-opus-5",
        "image_model": "google/gemini-3-pro-image",
    }


@pytest.fixture()
def ui(page, static_server):
    """The real page, with fetch stubbed so nothing needs a server."""
    page.goto(f"{static_server}/frontend2/operator.html")
    page.evaluate(
        """() => {
             window.__posts = [];
             window.__failNext = false;
             window.fetch = (url, options) => {
               if (!options || options.method !== 'POST') {
                 return Promise.resolve({ ok: true, json: () => Promise.resolve({ dreams: [] }) });
               }
               window.__posts.push([url, JSON.parse(options.body || '{}')]);
               const ok = !window.__failNext;
               window.__failNext = false;
               return Promise.resolve({ ok, status: ok ? 200 : 500, statusText: 'x' });
             };
           }"""
    )
    page.wait_for_function("window.kgDreamOperator !== undefined")
    return page


def render(page, value, dreams=()):
    page.evaluate("(a) => window.kgDreamOperator.render(a[0])", [value])
    page.evaluate("(a) => window.kgDreamOperator.renderDreams(a[0])", [list(dreams)])


def posts(page):
    return page.evaluate("() => window.__posts")


# -- display settings (spec §7) --------------------------------------------


def test_every_display_control_is_present(ui):
    render(ui, state())

    for control in ("#question-visible", "#question-seconds", "#fade-ms",
                    "#strip-ratio", "#typewriter"):
        assert ui.locator(control).count() == 1


def test_the_controls_show_the_servers_values(ui):
    render(ui, state(question_visible=False, question_seconds=30, fade_ms=800,
                     strip_ratio=0.3, typewriter=True))

    assert ui.locator("#question-visible").is_checked() is False
    assert ui.locator("#question-seconds").input_value() == "30"
    assert ui.locator("#fade-ms").input_value() == "800"
    assert ui.locator("#strip-ratio").input_value() == "0.3"
    assert ui.locator("#typewriter").is_checked() is True


def test_changing_the_fade_posts_it(ui):
    render(ui, state())

    ui.locator("#fade-ms").fill("600")
    ui.locator("#fade-ms").dispatch_event("change")

    assert posts(ui)[-1] == ["/api/display", {"fade_ms": 600}]


def test_toggling_the_typewriter_posts_it(ui):
    render(ui, state())

    ui.locator("#typewriter").click()

    assert posts(ui)[-1] == ["/api/display", {"typewriter": True}]


def test_switching_the_question_off_posts_it(ui):
    render(ui, state())

    ui.locator("#question-visible").click()

    assert posts(ui)[-1] == ["/api/display", {"question_visible": False}]


def test_the_auto_hide_duration_posts_seconds(ui):
    render(ui, state())

    ui.locator("#question-seconds").fill("20")
    ui.locator("#question-seconds").dispatch_event("change")

    assert posts(ui)[-1] == ["/api/display", {"question_seconds": 20}]


def test_the_strip_ratio_posts_a_fraction(ui):
    render(ui, state())

    ui.locator("#strip-ratio").fill("0.35")
    ui.locator("#strip-ratio").dispatch_event("change")

    assert posts(ui)[-1] == ["/api/display", {"strip_ratio": 0.35}]


# -- flow control (spec §7) -------------------------------------------------


def test_dream_now_posts(ui):
    render(ui, state())

    ui.locator("#dream-now").click()

    assert posts(ui)[-1][0] == "/api/dream_now"


def test_pause_and_resume_are_one_button_that_says_what_it_will_do(ui):
    render(ui, state(paused=False))
    assert "Pause" in ui.locator("#pause").inner_text()

    ui.locator("#pause").click()
    assert posts(ui)[-1] == ["/api/pause", {"paused": True}]

    render(ui, state(paused=True))
    assert "Weiter" in ui.locator("#pause").inner_text()


def test_discarding_the_current_dream_posts_its_id(ui):
    render(ui, state(current=record(2)), dreams=[record(1), record(2)])

    ui.locator("#discard-current").click()

    assert posts(ui)[-1] == ["/api/discard", {"dream_id": "d2", "discarded": True}]


def test_the_discard_button_is_disabled_when_there_is_nothing_to_discard(ui):
    render(ui, state(current=None))

    assert ui.locator("#discard-current").is_disabled() is True


def test_each_dream_in_the_list_can_be_discarded_and_restored(ui):
    render(ui, state(current=record(2)), dreams=[record(1), record(2, discarded=True)])

    ui.locator("#dream-d1 button.discard").click()
    assert posts(ui)[-1] == ["/api/discard", {"dream_id": "d1", "discarded": True}]

    ui.locator("#dream-d2 button.discard").click()
    assert posts(ui)[-1] == ["/api/discard", {"dream_id": "d2", "discarded": False}]


def test_the_restore_button_says_restore(ui):
    """Same as Tool 1's hide flag: „Wieder einblenden ist derselbe Knopf"."""
    render(ui, state(), dreams=[record(1, discarded=True)])

    assert "zurückholen" in ui.locator("#dream-d1 button.discard").inner_text()


# -- the record (spec §5.3) -------------------------------------------------


def test_the_operator_sees_the_image_prompt(ui):
    """Spec §5.2: stored for reproducibility and shown ONLY here — never on the
    wall, where it would put lighting instructions in front of visitors."""
    render(ui, state(), dreams=[record(1)])

    assert "S2 für d1" in ui.locator("#dream-d1").inner_text()


def test_failed_dreams_appear_with_their_error(ui):
    render(ui, state(), dreams=[record(1, status="failed")])

    text = ui.locator("#dream-d1").inner_text()
    assert "read timeout" in text


def test_a_discarded_dream_is_marked_but_still_listed(ui):
    """The record stays honest (spec §7); only the DISPLAY filters."""
    render(ui, state(), dreams=[record(1, discarded=True)])

    assert ui.locator("#dream-d1").count() == 1
    assert "verworfen" in ui.locator("#dream-d1").inner_text()


# -- the deliberate limits (spec §7) ---------------------------------------


def test_the_guiding_question_is_shown_but_has_no_control(ui):
    """Spec §7: changing the question mid-day destroys exactly the
    comparability the strip exists for. It is set in the morning, in
    config2.toml — visible here, not editable."""
    render(ui, state())

    assert "Wie leben und bauen wir in zehn Jahren?" in ui.locator("#the-question").inner_text()
    assert ui.locator("#the-question input").count() == 0
    assert ui.locator("#the-question textarea").count() == 0


def test_there_is_no_control_for_the_register_or_the_weighting(ui):
    render(ui, state(), dreams=[record(1)])

    html = ui.locator("body").inner_html().lower()
    for forbidden in ("register", "bildsprache", "gewichtung", "min_mentions"):
        assert f'id="{forbidden}' not in html
        assert f"name={forbidden}" not in html


# -- failure feedback -------------------------------------------------------


def test_a_failed_write_snaps_the_control_back_to_the_servers_value(ui):
    """Tool 1's rule, copied deliberately: this is the exhibition's only human
    control surface, and a control showing a change that did not happen is
    worse than no feedback at all."""
    render(ui, state(fade_ms=1200))
    ui.evaluate("() => { window.__failNext = true; }")

    ui.locator("#fade-ms").fill("600")
    ui.locator("#fade-ms").dispatch_event("change")
    ui.wait_for_function("() => document.getElementById('fade-ms').value === '1200'", timeout=5000)

    assert ui.locator("#fade-ms").input_value() == "1200"
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_dream_operator.py -v`
Expected: FAIL — `window.kgDreamOperator` never appears (the placeholder page from Task 10 has no script).

- [ ] **Step 3: Write `frontend2/static/operator.css`**

```css
/* Tool 2's operator window. A laptop UI, not a wall — pixels are fine here. */

* { box-sizing: border-box; }

body {
  margin: 0;
  padding: 16px;
  background: #16181c;
  color: #e8e6e1;
  font-family: "Inter", system-ui, sans-serif;
  font-size: 14px;
}

h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em; opacity: 0.55; margin: 20px 0 8px; }

#the-question {
  padding: 10px 12px;
  border-left: 3px solid #4a5568;
  background: #1d2026;
  font-size: 15px;
  line-height: 1.4;
}

#the-question .note { display: block; margin-top: 6px; font-size: 12px; opacity: 0.5; }

.controls { display: flex; flex-wrap: wrap; gap: 18px; align-items: center; }
.controls label { display: flex; gap: 7px; align-items: center; }
.controls input[type="number"] { width: 84px; }

button {
  font: inherit;
  padding: 7px 14px;
  border: 1px solid #3d434d;
  border-radius: 4px;
  background: #22262d;
  color: inherit;
  cursor: pointer;
}

button:hover:not(:disabled) { background: #2c313a; }
button:disabled { opacity: 0.35; cursor: default; }
#discard-current { border-color: #7a3b3b; }

#dreams { list-style: none; margin: 0; padding: 0; }

#dreams li {
  display: grid;
  grid-template-columns: 96px 1fr auto;
  gap: 12px;
  align-items: start;
  padding: 10px 0;
  border-top: 1px solid #262a31;
}

#dreams li.discarded { opacity: 0.45; }
#dreams li.failed { border-left: 3px solid #7a3b3b; padding-left: 9px; }
#dreams img { width: 96px; aspect-ratio: 16 / 9; object-fit: cover; display: block; }
#dreams .sentence { font-size: 14px; line-height: 1.4; }
#dreams .meta { font-size: 12px; opacity: 0.5; margin-top: 4px; }
#dreams .prompt { font-size: 11px; opacity: 0.42; margin-top: 5px; white-space: pre-wrap; word-break: break-word; }
#dreams .error { font-size: 12px; color: #d98a8a; margin-top: 4px; }
```

- [ ] **Step 4: Write `frontend2/static/operator.js`**

```javascript
// Spec §7. Display settings and flow control — and nothing that could change
// the guiding question, the visual register or the weighting at runtime.

// The last state the server actually CONFIRMED, not merely what we tried to
// send. post() reverts to this on failure, which is this exhibition's only
// feedback for a write the server never acknowledged: no toast, no banner,
// just the control snapping back to the truth. Copied from Tool 1's operator
// UI on purpose — same surface, same stakes.
let lastState = null;
let lastDreams = [];

function post(url, body) {
  return fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body || {}),
  })
    .then((response) => {
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    })
    .catch((error) => {
      console.warn(`request to ${url} failed`, error);
      if (lastState) render(lastState);
    });
}

function display(patch) {
  return post('/api/display', patch);
}

function dreamRow(dream) {
  const item = document.createElement('li');
  item.id = `dream-${dream.id}`;
  item.className = [dream.discarded ? 'discarded' : '', dream.status].filter(Boolean).join(' ');

  const image = document.createElement('img');
  if (dream.image) image.src = dream.image;
  image.alt = '';
  item.appendChild(image);

  const body = document.createElement('div');
  const sentence = document.createElement('div');
  sentence.className = 'sentence';
  sentence.textContent = dream.sentence || '—';
  body.appendChild(sentence);

  const meta = document.createElement('div');
  meta.className = 'meta';
  const when = new Date(dream.created_at * 1000).toLocaleTimeString('de-DE');
  meta.textContent =
    `${when} · ${dream.person_count} Menschen, ${dream.term_count} Begriffe · ` +
    `${dream.contradiction ? 'mit Widerspruch' : 'ohne Widerspruch'}` +
    `${dream.discarded ? ' · verworfen' : ''}`;
  body.appendChild(meta);

  if (dream.error) {
    const error = document.createElement('div');
    error.className = 'error';
    error.textContent = dream.error;
    body.appendChild(error);
  }

  // The image prompt lives HERE and only here (spec §5.2): showing it on the
  // wall would put lighting instructions in front of visitors.
  if (dream.stage2_prompt) {
    const prompt = document.createElement('div');
    prompt.className = 'prompt';
    prompt.textContent = dream.stage2_prompt;
    body.appendChild(prompt);
  }
  item.appendChild(body);

  const button = document.createElement('button');
  button.className = 'discard';
  button.textContent = dream.discarded ? 'zurückholen' : 'verwerfen';
  button.addEventListener('click', () =>
    post('/api/discard', { dream_id: dream.id, discarded: !dream.discarded }),
  );
  item.appendChild(button);
  return item;
}

function render(state) {
  lastState = state;

  document.getElementById('the-question').firstElementChild.textContent = state.question;
  document.getElementById('question-visible').checked = Boolean(state.question_visible);
  document.getElementById('question-seconds').value = String(state.question_seconds ?? 0);
  document.getElementById('fade-ms').value = String(state.fade_ms);
  document.getElementById('strip-ratio').value = String(state.strip_ratio);
  document.getElementById('typewriter').checked = Boolean(state.typewriter);

  // One button that says what it will DO, not what the state IS — the operator
  // is reaching for it in a hurry.
  document.getElementById('pause').textContent = state.paused ? 'Weiter' : 'Pause';

  const discard = document.getElementById('discard-current');
  discard.disabled = !state.current;
  discard.dataset.dreamId = state.current ? state.current.id : '';
}

function renderDreams(dreams) {
  lastDreams = dreams;
  const list = document.getElementById('dreams');
  list.replaceChildren();
  // Newest first: the operator reaches for the dream that is on screen NOW.
  // (The WALL runs oldest-first — that is a time axis, this is a work list.)
  dreams
    .slice()
    .sort((a, b) => b.created_at - a.created_at)
    .forEach((dream) => list.appendChild(dreamRow(dream)));
}

function refreshDreams() {
  return fetch('/api/dreams')
    .then((response) => response.json())
    .then((payload) => renderDreams(payload.dreams || []))
    .catch((error) => console.warn('could not load the dream record', error));
}

document
  .getElementById('question-visible')
  .addEventListener('change', (event) => display({ question_visible: event.target.checked }));
document
  .getElementById('question-seconds')
  .addEventListener('change', (event) => display({ question_seconds: Number(event.target.value) }));
document
  .getElementById('fade-ms')
  .addEventListener('change', (event) => display({ fade_ms: Number(event.target.value) }));
document
  .getElementById('strip-ratio')
  .addEventListener('change', (event) => display({ strip_ratio: Number(event.target.value) }));
document
  .getElementById('typewriter')
  .addEventListener('change', (event) => display({ typewriter: event.target.checked }));

document.getElementById('dream-now').addEventListener('click', () => post('/api/dream_now'));
document
  .getElementById('pause')
  .addEventListener('click', () => post('/api/pause', { paused: !(lastState && lastState.paused) }));
document.getElementById('discard-current').addEventListener('click', (event) => {
  const id = event.currentTarget.dataset.dreamId;
  if (id) post('/api/discard', { dream_id: id, discarded: true });
});

window.kgDreamOperator = { render, renderDreams, refreshDreams };

const events = new EventSource('/events');
events.onmessage = (message) => {
  const payload = JSON.parse(message.data);
  if (payload.type === 'state') {
    render(payload.state);
    refreshDreams();
  }
};
```

- [ ] **Step 5: Write `frontend2/operator.html`**

```html
<!doctype html>
<html lang="de">
<meta charset="utf-8">
<title>Kollektivtraum — Operator</title>
<link rel="stylesheet" href="static/operator.css">

<h2>Leitfrage</h2>
<!-- Read-only ON PURPOSE (spec §7). Changing the question mid-day destroys
     exactly the comparability the history strip exists for. It is set in the
     morning, in config2.toml. Shown here so the operator can see what is set. -->
<div id="the-question">
  <span></span>
  <span class="note">Wird morgens in config2.toml gesetzt und läuft den ganzen Tag durch — hier bewusst nicht änderbar.</span>
</div>

<h2>Anzeige</h2>
<div class="controls">
  <label><input type="checkbox" id="question-visible"> Leitfrage zeigen</label>
  <label>ausblenden nach <input type="number" id="question-seconds" min="0" max="36000" step="5"> s (0 = nie)</label>
  <label>Überblendung <input type="number" id="fade-ms" min="100" max="10000" step="100"> ms</label>
  <label>Streifenhöhe <input type="number" id="strip-ratio" min="0.05" max="0.5" step="0.01"></label>
  <label><input type="checkbox" id="typewriter"> Schreibmaschine</label>
</div>

<h2>Ablauf</h2>
<div class="controls">
  <button id="dream-now">Jetzt träumen</button>
  <button id="pause">Pause</button>
  <button id="discard-current">Aktuellen Traum verwerfen</button>
</div>

<h2>Alle Träume</h2>
<ul id="dreams"></ul>

<script type="module" src="static/operator.js"></script>
</html>
```

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_dream_operator.py -v`
Expected: PASS (19 tests)

- [ ] **Step 7: Commit**

```bash
git add frontend2/operator.html frontend2/static/operator.js \
        frontend2/static/operator.css tests/test_dream_operator.py
git commit -m "feat: Tool 2's operator UI — display settings and flow control

The guiding question is shown read-only: spec 7 makes it a morning setting, and
a control that could change it mid-day would destroy the comparability the strip
exists for. Failed writes snap the control back to the server's value."
```

---

### Task 14: Failure modes and crash recovery

**Files:**
- Create: `tests/test_dream_resilience.py`
- Modify: none (this task proves the behaviour already built; **any production change it forces is a finding to record in the ledger**)

**Interfaces:**
- Consumes: every task so far.
- Produces: no new module. One test per row of spec §8.

Every failure mode in §8 gets a test. The two that matter most (§11): **„cloud dead → last image stays up"** and **„restart → strip intact"**.

This is Tool 1's Task 21 discipline. If a test here fails, first ask whether the *test* encodes the requirement correctly; if the production code really is wrong, fix it and record what and why in the ledger.

- [ ] **Step 1: Write the tests**

`tests/test_dream_resilience.py`:

```python
"""Every row of spec §8, plus the crash-recovery standard of T1§14 (run 21).

| Failure (spec §8)                        | Covered by                          |
|------------------------------------------|-------------------------------------|
| Stage 1 or 2 fails / times out           | `test_a_dead_cloud_…`               |
| No connectivity at all                   | `test_a_whole_day_of_no_…`          |
| Tool 1 unreachable                       | `test_a_dead_tool_1_…`              |
| Tool 2 process dies                      | `test_a_restart_restores_…`         |
| Image model returns something unusable   | `test_an_unusable_image_…`          |
| Disk fills with images                   | documented, not engineered (below)  |

The two that matter most (spec §11): „cloud dead → last image stays up" and
„restart → strip intact".
"""

from __future__ import annotations

import struct
import zlib

import pytest
from fastapi.testclient import TestClient

from kg.bus import EventBus
from kg2.config import DreamConfig
from kg2.cycle import run_dream
from kg2.imagegen import ImageError
from kg2.server import create_dream_app, dream_state, seed_display_settings
from kg2.store import DreamStore
from kg2.watcher import DreamWatcher


def png_bytes() -> bytes:
    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
        + chunk(b"IEND", b"")
    )


def graph(persons, generated_at=1000.0) -> dict:
    nodes = [
        {"id": f"p{i}", "type": "person", "portrait": None, "created_at": 1.0,
         "hidden": False, "x": None, "y": None}
        for i in range(1, persons + 1)
    ] + [
        {"id": "t1", "type": "term", "label": "Weiterbauen im Bestand", "mentions": persons,
         "created_at": 2.0, "hidden": False, "x": None, "y": None}
    ]
    return {
        "version": 1, "generated_at": generated_at, "min_mentions": 1, "nodes": nodes,
        "edges": [{"id": f"e{i}", "source": f"p{i}", "target": "t1"}
                  for i in range(1, persons + 1)],
        "quotes": [],
    }


def good_condense(sentence="Der Beton träumt von Wald."):
    from kg2.condense import CondenseResult

    def fn(llm, material, question, contradiction):
        return CondenseResult(prompt="P", sentence=sentence)

    return fn


def good_render(prompt, **kwargs):
    return png_bytes()


def seed_one_good_dream(store, cfg, *, at=1.0, sentence="das gute Bild"):
    return run_dream(store, cfg, object(), graph(3), at,
                     condense_fn=good_condense(sentence), render_fn=good_render)


# -- „cloud dead -> last image stays up" (spec §11's first priority) --------


def test_a_dead_cloud_leaves_the_last_image_up(tmp_path):
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    seed_one_good_dream(store, cfg)

    def dead(prompt, **kwargs):
        raise ImageError("connection reset by peer")

    for index in range(1, 6):
        assert run_dream(store, cfg, object(), graph(3 + index), 300.0 * index,
                         condense_fn=good_condense(), render_fn=dead) is None

    assert store.current_dream().sentence == "das gute Bild"
    assert store.current_dream().image_path == "d1.png"
    store.close()


def test_a_whole_day_of_no_connectivity_still_shows_a_calm_screen(tmp_path):
    """Spec §8: „Screen shows the last dream and a full history strip. Looks
    calm, not broken."""
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    seed_display_settings(store, cfg)
    for index in range(1, 6):
        seed_one_good_dream(store, cfg, at=float(index), sentence=f"traum {index}")

    def dead(llm, material, question, contradiction):
        raise RuntimeError("no route to host")

    for index in range(20):
        run_dream(store, cfg, object(), graph(10), 1000.0 + index,
                  condense_fn=dead, render_fn=good_render)

    state = dream_state(store, cfg)
    assert state["current"]["sentence"] == "traum 5"
    assert len(state["history"]) == 4
    store.close()


def test_a_stage_1_timeout_leaves_the_last_image_up(tmp_path):
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    seed_one_good_dream(store, cfg)

    def timeout(llm, material, question, contradiction):
        raise TimeoutError("read timeout")

    assert run_dream(store, cfg, object(), graph(5), 300.0,
                     condense_fn=timeout, render_fn=good_render) is None
    assert store.current_dream().sentence == "das gute Bild"
    store.close()


def test_an_unusable_image_never_reaches_the_wall(tmp_path):
    """Spec §8's „image model returns something unusable" has two halves: a
    malformed body is caught here, and an ugly-but-valid image is the
    operator's discard (tested below)."""
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    seed_one_good_dream(store, cfg)

    assert run_dream(store, cfg, object(), graph(5), 300.0, condense_fn=good_condense(),
                     render_fn=lambda p, **k: b"<html>502 Bad Gateway</html>") is None

    assert store.current_dream().image_path == "d1.png"
    assert not (cfg.image_dir / "d2.png").exists()
    store.close()


def test_the_operator_can_pull_an_embarrassing_image_and_the_previous_returns(tmp_path):
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    seed_display_settings(store, cfg)
    seed_one_good_dream(store, cfg, at=1.0, sentence="harmlos")
    seed_one_good_dream(store, cfg, at=2.0, sentence="peinlich")
    client = TestClient(create_dream_app(store, cfg, EventBus()))

    client.post("/api/discard", json={"dream_id": "d2", "discarded": True})

    state = client.get("/api/state").json()
    assert state["current"]["sentence"] == "harmlos"
    assert state["history"] == []  # spec §7: gone from the strip too
    store.close()


# -- „restart -> strip intact" (spec §11's second priority) -----------------


def test_a_restart_restores_the_current_dream_the_whole_strip_and_the_settings(tmp_path):
    """T1§14 run 21's standard, held for Tool 2: after a restart the screen
    comes back exactly as it stood."""
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    seed_display_settings(store, cfg)
    for index in range(1, 8):
        seed_one_good_dream(store, cfg, at=float(index), sentence=f"traum {index}")
    client = TestClient(create_dream_app(store, cfg, EventBus()))
    client.post("/api/display", json={"fade_ms": 700, "typewriter": True, "strip_ratio": 0.3})
    client.post("/api/discard", json={"dream_id": "d3", "discarded": True})
    before = client.get("/api/state").json()
    store.close()  # the crash

    reopened = DreamStore.open(cfg.db_path)
    seed_display_settings(reopened, cfg)
    after = TestClient(create_dream_app(reopened, cfg, EventBus())).get("/api/state").json()

    assert after == before
    assert after["current"]["sentence"] == "traum 7"
    assert len(after["history"]) == 5  # 7 dreams, minus the current, minus d3
    assert after["fade_ms"] == 700
    reopened.close()


def test_the_image_files_survive_a_restart(tmp_path):
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    for index in range(1, 4):
        seed_one_good_dream(store, cfg, at=float(index))
    store.close()

    reopened = DreamStore.open(cfg.db_path)

    for dream in reopened.visible_dreams():
        assert (cfg.image_dir / dream.image_path).is_file()
    reopened.close()


def test_a_dream_interrupted_by_the_crash_is_visibly_incomplete_not_invisible(tmp_path):
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    seed_one_good_dream(store, cfg, sentence="das gute Bild")
    store.create_dream(created_at=300.0, graph_generated_at=299.0, person_count=5,
                       term_count=4, edge_count=6, contradiction=False,
                       guiding_question="Q", absorbed_persons=["p4"])
    store.close()  # killed mid-cycle

    reopened = DreamStore.open(cfg.db_path)

    assert reopened.current_dream().sentence == "das gute Bild"  # not the half one
    assert reopened.get_dream("d2").status == "running"  # honest record
    assert len(reopened.all_dreams()) == 2
    reopened.close()


async def test_a_restart_mid_day_neither_re_dreams_nor_stops_dreaming(tmp_path):
    """The two ways this goes wrong, both in one test."""
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    seed_display_settings(store, cfg)
    for index in range(1, 4):
        seed_one_good_dream(store, cfg, at=float(index))
    store.close()

    reopened = DreamStore.open(cfg.db_path)
    cycles = []

    def counting_cycle(store_, cfg_, llm, g, now, **kwargs):
        cycles.append(now)
        return run_dream(store_, cfg_, llm, g, now,
                         condense_fn=good_condense(), render_fn=good_render)

    watcher = DreamWatcher(cfg, reopened, EventBus(), llm=object(),
                           fetch=lambda url, timeout: graph(3), cycle=counting_cycle,
                           clock=lambda: 99999.0)

    assert await watcher.tick() is None  # nothing new was said
    assert cycles == []

    watcher.fetch = lambda url, timeout: graph(4)  # a fourth interview lands
    assert await watcher.tick() is not None
    assert len(cycles) == 1
    reopened.close()


# -- Tool 1 unreachable (spec §8) -------------------------------------------


async def test_a_dead_tool_1_leaves_the_display_completely_untouched(tmp_path):
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    seed_display_settings(store, cfg)
    seed_one_good_dream(store, cfg, sentence="das gute Bild")
    before = dream_state(store, cfg)

    watcher = DreamWatcher(cfg, store, EventBus(), llm=object(),
                           fetch=lambda url, timeout: None, clock=lambda: 99999.0)
    for _ in range(10):
        assert await watcher.tick() is None

    assert dream_state(store, cfg) == before
    store.close()


def test_a_half_written_graph_json_is_ignored_rather_than_dreamt_about(tmp_path):
    """Tool 1 writes graph.json atomically (`os.replace`), but a proxy or a
    truncated HTTP body can still deliver half a document."""
    from kg2.graph_client import fetch_graph

    def truncated(url, timeout):
        raise ValueError("Expecting ',' delimiter")

    assert fetch_graph("http://x/graph.json", get=truncated) is None


# -- the operator surface stays usable in every failure ---------------------


def test_the_operator_ui_still_works_while_the_cloud_is_dead(tmp_path):
    """Spec §7's controls must not depend on the thing that is broken."""
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    seed_display_settings(store, cfg)
    seed_one_good_dream(store, cfg)
    client = TestClient(create_dream_app(store, cfg, EventBus()))

    assert client.post("/api/pause", json={"paused": True}).status_code == 200
    assert client.post("/api/display", json={"fade_ms": 500}).status_code == 200
    assert client.post("/api/dream_now").status_code == 200
    assert client.get("/api/state").status_code == 200
    store.close()


# -- documented, not engineered around (spec §8) ---------------------------


def test_a_days_worth_of_images_is_a_non_issue(tmp_path):
    """Spec §8: „~40 images/day at a few hundred KB — a non-issue for one day;
    documented, not engineered around." This test states the assumption so a
    future change that breaks it is visible."""
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    store = DreamStore.open(cfg.db_path)
    for index in range(1, 41):
        seed_one_good_dream(store, cfg, at=float(index))

    written = list(cfg.image_dir.glob("*.png"))
    assert len(written) == 40
    # One file per dream, never overwritten (spec §5.2).
    assert len({path.name for path in written}) == 40
    store.close()
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/test_dream_resilience.py -v`
Expected: PASS (14 tests).

If any fail, work out whether the test or the production code is wrong before touching either. Record the answer in the ledger.

- [ ] **Step 3: Run the whole suite, Tool 1 included**

Run: `uv run pytest tests/ -q`
Expected: PASS. Tool 1's 277 tests plus Tool 2's. Note the total in the ledger.

- [ ] **Step 4: Commit**

```bash
git add tests/test_dream_resilience.py
git commit -m "test: every failure mode of spec 8, plus crash recovery

The two that matter: cloud dead leaves the last image up, and a restart brings
back the current dream, the whole strip and every operator setting."
```

---

### Task 15: Visual register samples — Birk picks at images, not in words

**Files:**
- Create: `sim/dream_register.py`
- Test: `tests/test_dream_register.py`

**Interfaces:**
- Consumes: Task 8 (`build_image_prompt`, `render_image`, `save_image`).
- Produces:
  - `sim.dream_register.REGISTERS` — an ordered dict of 4 named register strings
  - `sim.dream_register.FICTIONAL_SENTENCE` — the one sentence every sample renders
  - `sim.dream_register.render_samples(out_dir, cfg, registers=REGISTERS, render_fn=render_image) -> list[Sample]`
  - CLI: `uv run python -m sim.dream_register --out out/register1`

**Standing rule: BUILD the artefacts, never pick.** Spec §10 and brainstorm §10 are explicit — the register is decided **at images, not in words**. This task's job is to produce three or four samples on *identical* fictional content and print them with no recommendation and no ordering that implies one. Birk chooses; the chosen string then goes into `config2.toml`.

Two things that make the comparison honest:

- **Identical content.** One fictional sentence, four registers. The only variable is the register — the same discipline the history strip itself is built on (§5.2).
- **Fictional content.** The sentence must not come from the real corpus. A sample built on real interview material invites judging the *content*, which is not what is being decided, and it would put a half-formed dream of real people's words into a review directory.

- [ ] **Step 1: Write the failing test**

`tests/test_dream_register.py`:

```python
"""Spec §10 / brainstorm §10 — the register is decided at images, not in words.

These tests pin the comparison's honesty (identical content, one variable) and
the standing rule that this module recommends nothing.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from kg2.config import DreamConfig
from sim.dream_register import FICTIONAL_SENTENCE, REGISTERS, render_samples


def png_bytes() -> bytes:
    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
        + chunk(b"IEND", b"")
    )


def test_there_are_three_or_four_registers():
    """Brainstorm §10: „three or four samples". More is not a better decision,
    it is a worse one — nobody compares eight images fairly."""
    assert 3 <= len(REGISTERS) <= 4


def test_the_registers_are_genuinely_different_and_none_is_marked_as_preferred():
    names = list(REGISTERS)
    assert len(set(names)) == len(names)
    assert len(set(REGISTERS.values())) == len(REGISTERS)
    for name in names:
        for forbidden in ("empfohlen", "recommended", "best", "default", "favorit"):
            assert forbidden not in name.lower()


def test_every_register_forbids_text_in_the_image():
    """The sentence is a separate displayed artefact (spec §5.2). Text rendered
    inside the picture would compete with it, in every register."""
    for register in REGISTERS.values():
        assert "keine Schrift" in register


def test_the_sample_content_is_fictional_and_not_from_the_corpus(real_graph):
    """A sample built on real interview material invites judging the CONTENT,
    which is not what is being decided here."""
    labels = {
        node["label"] for node in real_graph["nodes"] if node.get("type") == "term"
    }
    for label in labels:
        assert label not in FICTIONAL_SENTENCE


def test_every_sample_renders_the_identical_sentence(tmp_path):
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    prompts = []

    def fake_render(prompt, **kwargs):
        prompts.append(prompt)
        return png_bytes()

    render_samples(tmp_path / "out", cfg, render_fn=fake_render)

    assert len(prompts) == len(REGISTERS)
    # One variable only: strip each register out and the remainder is identical.
    stripped = {
        prompt.replace(register, "<REGISTER>")
        for prompt, register in zip(prompts, REGISTERS.values())
    }
    assert len(stripped) == 1
    assert all(FICTIONAL_SENTENCE in prompt for prompt in prompts)


def test_the_filenames_say_which_register_they_are(tmp_path):
    cfg = DreamConfig(data_dir=tmp_path / "dream")

    samples = render_samples(tmp_path / "out", cfg, render_fn=lambda p, **k: png_bytes())

    for sample, name in zip(samples, REGISTERS):
        assert name in sample.path.name
        assert sample.path.is_file()


def test_the_filenames_carry_no_ranking(tmp_path):
    """Not `1-…`, `2-…`: a numbered series is an implied ordering, and Birk is
    supposed to read them cold."""
    cfg = DreamConfig(data_dir=tmp_path / "dream")

    samples = render_samples(tmp_path / "out", cfg, render_fn=lambda p, **k: png_bytes())

    for sample in samples:
        assert not sample.path.name[0].isdigit()


def test_one_failing_register_does_not_lose_the_others(tmp_path):
    """A rate limit on sample three must not throw away samples one and two —
    they cost real money."""
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    calls = {"n": 0}

    def flaky(prompt, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("429 rate limited")
        return png_bytes()

    samples = render_samples(tmp_path / "out", cfg, render_fn=flaky)

    assert len(samples) == len(REGISTERS) - 1
    assert calls["n"] == len(REGISTERS)


def test_a_rerun_does_not_overwrite_an_earlier_round(tmp_path):
    """Spec §5.2's rule holds here too: an overwritten sample is a lost
    comparison, and these cost money to make."""
    cfg = DreamConfig(data_dir=tmp_path / "dream")
    render_samples(tmp_path / "out", cfg, render_fn=lambda p, **k: png_bytes())

    second = render_samples(tmp_path / "out", cfg, render_fn=lambda p, **k: png_bytes())

    assert second == []  # every target already existed; nothing was clobbered
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_dream_register.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sim.dream_register'`

- [ ] **Step 3: Implement `sim/dream_register.py`**

```python
"""Register samples: identical content, one variable (spec §10, brainstorm §10).

**This module recommends nothing.** The register is decided by Birk AT IMAGES,
not in words — that is the whole reason it exists rather than a paragraph in the
spec. The names below are descriptive, the order is alphabetical, and no output
line marks a favourite.

Why fictional content: a sample built on real interview material invites judging
the CONTENT, which is not what is being decided, and it would leave a half-formed
dream of real people's words sitting in a review directory.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path

from kg2.imagegen import build_image_prompt, render_image, save_image

log = logging.getLogger(__name__)

# One sentence, four registers. Invented outright: a courtyard that is both
# poured and planted is exactly the kind of held contradiction stage 1 is
# instructed to produce (spec §5.1), so the samples are judged on the register
# doing the job it will really have to do.
FICTIONAL_SENTENCE = (
    "In einem Hof, der gleichzeitig gegossen und bepflanzt wird, "
    "warten zwei Generationen darauf, dass die jeweils andere zuerst aufgibt."
)

#: Alphabetical, deliberately. Any other order is an implied ranking.
#: „keine Schrift im Bild" is in every one of them, not decoration: the sentence
#: is a separate displayed artefact (spec §5.2) and text inside the picture
#: would compete with it.
REGISTERS: dict[str, str] = {
    "aquarell": (
        "Aquarell auf rauem Papier, laufende Ränder, viel unbemaltes Weiß, "
        "wenige gebrochene Farben, zarte Konturen. Kein Fotorealismus, kein "
        "Architektur-Rendering, keine Schrift im Bild."
    ),
    "malerisch-atmosphaerisch": (
        "Malerisch und atmosphärisch, weiche Übergänge, gedämpfte Farbigkeit, "
        "diffuses Licht, sichtbarer Pinselduktus. Kein Fotorealismus, kein "
        "Architektur-Rendering, keine Schrift im Bild."
    ),
    "radierung": (
        "Radierung, feine Schraffuren in Schwarz auf warmem Papierton, harte "
        "Linien, tiefe Schatten, kein Farbauftrag. Kein Fotorealismus, kein "
        "Architektur-Rendering, keine Schrift im Bild."
    ),
    "siebdruck": (
        "Reduzierter Siebdruck, drei bis vier flache Farbflächen, sichtbarer "
        "Passerversatz, grobes Raster, kräftige Kontraste. Kein Fotorealismus, "
        "kein Architektur-Rendering, keine Schrift im Bild."
    ),
}


@dataclass(frozen=True)
class Sample:
    name: str
    path: Path
    register: str


def render_samples(out_dir, cfg, registers=None, render_fn=render_image) -> list[Sample]:
    """One image per register, same sentence, same aspect ratio.

    A register that fails is logged and skipped: the others already cost real
    money and must not be thrown away with it.

    Existing files are never overwritten — an overwritten sample is a lost
    comparison, and re-running the CLI to add a fifth register must not silently
    remake the first four.
    """
    registers = REGISTERS if registers is None else registers
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    samples: list[Sample] = []
    for name, register in registers.items():
        target = out_dir / f"register-{name}.png"
        if target.exists():
            log.info("%s already exists, left alone", target)
            continue
        prompt = build_image_prompt(FICTIONAL_SENTENCE, register, cfg.image_aspect_ratio)
        try:
            data = render_fn(
                prompt,
                model=cfg.image_model,
                api_key=cfg.openrouter_api_key,
                url=cfg.image_url,
                timeout=cfg.image_timeout_s,
            )
            save_image(data, target)
        except Exception as exc:
            log.error("register %s failed: %s", name, exc)
            continue
        samples.append(Sample(name=name, path=target, register=register))
    return samples


def main() -> None:
    from kg2.config import load_dream_config

    parser = argparse.ArgumentParser(prog="sim.dream_register")
    parser.add_argument("--out", default="out/register1")
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_dream_config(Path(args.config) if args.config else None)

    print(f"Ein Satz, {len(REGISTERS)} Register. Nur das Register ändert sich.\n")
    print(f"Satz (frei erfunden): {FICTIONAL_SENTENCE}\n")

    samples = render_samples(Path(args.out), cfg)

    for sample in samples:
        print(sample.path.resolve())
        print(f"    {sample.register}\n")
    # No recommendation, no ranking, no "we suggest". Birk decides at the
    # images (spec §10) and puts the string he picks into config2.toml.
    print(
        f"{len(samples)} von {len(REGISTERS)} Registern gerendert. "
        "Ausgewähltes Register als `visual_register` in config2.toml eintragen."
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_dream_register.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Render the real samples**

Needs `OPENROUTER_API_KEY`. Four real image calls.

```bash
uv run python -m sim.dream_register --out out/register1
```

Report the four paths to Birk **with no recommendation**. His pick goes into `config2.toml` as `visual_register` and is recorded in `docs/operations.md` at Task 18.

- [ ] **Step 6: Commit**

```bash
git add sim/dream_register.py tests/test_dream_register.py
git commit -m "feat: four visual register samples on identical fictional content

The register is decided at images, not in words (spec 10). This module renders
and recommends nothing: alphabetical order, no ranking in the filenames, no
favourite in the output."
```

---

### Task 16: The calibration run

**Files:**
- Create: `sim/dream_calibrate.py`
- Test: `tests/test_dream_calibrate.py`

**Interfaces:**
- Consumes: Task 3 (`sim/data/graph-19c.json`), Tasks 6, 7.
- Produces:
  - `sim.dream_calibrate.prefix_graph(graph: dict, persons: int) -> dict`
  - `sim.dream_calibrate.QUESTIONS` — 4 candidate wordings
  - `sim.dream_calibrate.SIZES` — `(3, 10, 30, 60)`
  - `sim.dream_calibrate.floor_table(interview_count, day_seconds, floors) -> list[dict]`
  - CLI: `uv run python -m sim.dream_calibrate {questions,contradiction,floor}`

Spec §10's four values, produced the way Tool 1's density values were (its §14.4, run 19c): **by the simulation, then recorded in `docs/operations.md`**, never guessed here.

Three sub-runs, because the three values are calibrated by different evidence:

- **`questions`** — 4 candidate wordings × 4 graph sizes, sentences printed. **Birk picks. No recommendation, no ordering that implies one.** Every candidate must be wide enough to carry all three interview themes (future of building / AI in building / new forms of living together); a candidate that only fits one is not a candidate (§10, brainstorm §7).
- **`contradiction`** — at each size, stage 1 run with and without the contradiction clause, printed side by side. The threshold is read off where the clause stops producing an *invented* opposition and starts naming a real one.
- **`floor`** — no LLM at all. A table of assumed interview cadence × candidate `min_interval_s` → dreams per day and how many interviews collapse into a shared dream. The floor is an arithmetic question about the day, not a question about the model.

`prefix_graph` derives an earlier state from the real run-19c graph: the first N persons by `created_at`, the edges that touch them, the terms that survive, mentions recomputed. That is genuinely what the graph looked like at N persons, modulo later label renames — and it is derived from real data rather than invented.

- [ ] **Step 1: Write the failing test**

`tests/test_dream_calibrate.py`:

```python
"""Spec §10 — the values are produced by the simulation, not guessed."""

from __future__ import annotations

from sim.dream_calibrate import QUESTIONS, SIZES, floor_table, prefix_graph


def test_the_sizes_span_an_empty_morning_to_a_full_day():
    assert SIZES == (3, 10, 30, 60)


# -- prefix_graph -----------------------------------------------------------


def test_prefix_graph_keeps_the_first_n_persons(real_graph):
    small = prefix_graph(real_graph, 10)

    persons = [n for n in small["nodes"] if n["type"] == "person"]
    assert len(persons) == 10
    order = [n["id"] for n in sorted(persons, key=lambda n: (n["created_at"], n["id"]))]
    assert order[0] == "p1"


def test_prefix_graph_drops_edges_to_persons_who_are_not_there_yet(real_graph):
    small = prefix_graph(real_graph, 10)

    persons = {n["id"] for n in small["nodes"] if n["type"] == "person"}
    assert all(edge["source"] in persons for edge in small["edges"])


def test_prefix_graph_drops_terms_nobody_left_has_mentioned(real_graph):
    small = prefix_graph(real_graph, 5)

    mentioned = {edge["target"] for edge in small["edges"]}
    terms = {n["id"] for n in small["nodes"] if n["type"] == "term"}
    assert terms == mentioned


def test_prefix_graph_recomputes_mentions_for_the_smaller_graph(real_graph):
    """Carrying the 60-person counts into a 5-person graph would make the
    weighting describe a day that has not happened yet."""
    small = prefix_graph(real_graph, 5)

    counts = {}
    for edge in small["edges"]:
        counts[edge["target"]] = counts.get(edge["target"], 0) + 1
    for node in small["nodes"]:
        if node["type"] == "term":
            assert node["mentions"] == counts[node["id"]]
            assert node["mentions"] <= 5


def test_prefix_graph_keeps_only_the_quotes_of_the_people_present(real_graph):
    small = prefix_graph(real_graph, 5)

    persons = {n["id"] for n in small["nodes"] if n["type"] == "person"}
    assert all(quote["person_id"] in persons for quote in small["quotes"])
    assert small["quotes"]


def test_prefix_graph_grows_monotonically(real_graph):
    sizes = [prefix_graph(real_graph, n) for n in SIZES]

    counts = [len(g["edges"]) for g in sizes]
    assert counts == sorted(counts)
    assert all(counts[i] < counts[i + 1] for i in range(len(counts) - 1))


def test_the_full_prefix_is_the_whole_graph(real_graph):
    full = prefix_graph(real_graph, 60)

    assert len(full["edges"]) == len(real_graph["edges"])
    assert len(full["quotes"]) == len(real_graph["quotes"])


def test_prefix_graph_still_looks_like_a_graph_json(real_graph):
    """It goes straight into build_material, so it has to keep the contract."""
    small = prefix_graph(real_graph, 3)

    assert set(small) == set(real_graph)
    assert small["version"] == 1


# -- the guiding-question candidates ---------------------------------------


def test_there_are_three_or_four_candidate_wordings():
    assert 3 <= len(QUESTIONS) <= 4


def test_every_candidate_is_a_german_question():
    for question in QUESTIONS:
        assert question.strip().endswith("?")
        assert len(question.split()) >= 4


def test_no_candidate_is_marked_as_recommended():
    """Standing rule: Birk reads them cold."""
    for question in QUESTIONS:
        for forbidden in ("empfohlen", "recommended", "*", "(a)", "1."):
            assert forbidden not in question


def test_no_candidate_narrows_to_a_single_theme():
    """Spec §10 / brainstorm §7: wide enough to carry the future of building,
    AI in building, AND new forms of living together. A question naming one
    material or one technology cannot carry the other two."""
    narrow = ("beton", "holz", "dämmung", "ziegel", "photovoltaik", "roboter", "drohne")
    for question in QUESTIONS:
        assert not any(word in question.lower() for word in narrow)


def test_the_candidates_are_distinct():
    assert len(set(QUESTIONS)) == len(QUESTIONS)


# -- the floor --------------------------------------------------------------


def test_the_floor_table_reports_dreams_per_day_for_each_candidate():
    rows = floor_table(interview_count=60, day_seconds=8 * 3600, floors=(120, 240, 480))

    assert [row["min_interval_s"] for row in rows] == [120, 240, 480]
    assert all(row["dreams"] <= 60 for row in rows)


def test_a_floor_below_the_cadence_never_binds():
    """60 interviews over 8 h is one every 480 s. A 120 s floor cannot collapse
    anything, so every interview gets its own dream."""
    rows = floor_table(interview_count=60, day_seconds=8 * 3600, floors=(120,))

    assert rows[0]["dreams"] == 60
    assert rows[0]["collapsed"] == 0


def test_a_floor_above_the_cadence_collapses_interviews():
    rows = floor_table(interview_count=60, day_seconds=8 * 3600, floors=(1200,))

    assert rows[0]["dreams"] < 60
    assert rows[0]["collapsed"] > 0
    assert rows[0]["dreams"] + rows[0]["collapsed"] == 60


def test_the_floor_table_reports_the_cadence_it_assumed():
    """The number that actually decides the answer must be visible, or the
    table reads as a fact about the floor when it is a fact about the day."""
    rows = floor_table(interview_count=60, day_seconds=8 * 3600, floors=(240,))

    assert rows[0]["cadence_s"] == 480.0


def test_a_day_with_no_interviews_produces_no_dreams():
    rows = floor_table(interview_count=0, day_seconds=8 * 3600, floors=(240,))

    assert rows[0]["dreams"] == 0
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_dream_calibrate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sim.dream_calibrate'`

- [ ] **Step 3: Implement `sim/dream_calibrate.py`**

```python
"""Spec §10's four values, produced by the simulation and not guessed.

The same discipline Tool 1's density values were produced under (T1§14.4, run
19c): run it, read the output, write the answer into `docs/operations.md`.

Three sub-commands, because the three values need different evidence:

* `questions`    — 4 wordings × 4 graph sizes, sentences printed. BIRK PICKS.
* `contradiction`— each size with and without the clause, side by side. The
                   threshold is where the clause stops inventing an opposition.
* `floor`        — arithmetic, no LLM. The floor is a question about the day's
                   cadence, not about the model.

**This module recommends nothing** (standing rule, 2026-08-25). Reading the
sentences cold is the point.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kg2.condense import condense
from kg2.weighting import build_material, contradiction_enabled

FIXTURE = Path(__file__).resolve().parent / "data" / "graph-19c.json"

#: Empty morning, mid-morning, afternoon, end of the day.
SIZES = (3, 10, 30, 60)

#: Candidate wordings. Every one must carry all three interview themes — future
#: of building, AI in building, new forms of living together (spec §10,
#: brainstorm §7). A question naming one material or one technology cannot, and
#: is therefore not a candidate.
#:
#: Order is arbitrary and means nothing. None is marked.
QUESTIONS = (
    "Wie leben und bauen wir in zehn Jahren?",
    "Wie wollen wir in zehn Jahren zusammen wohnen und bauen?",
    "Was soll in zehn Jahren anders sein an dem Ort, an dem Sie leben?",
    "Wer baut in zehn Jahren unsere Häuser, und wer entscheidet darüber?",
)


def prefix_graph(graph: dict, persons: int) -> dict:
    """The graph as it stood after the first `persons` interviews.

    Derived from the real run-19c artefact rather than invented: the first N
    persons by creation time, the edges that touch them, the terms that survive,
    and mentions recomputed for the smaller graph.

    Honest about its one limitation: Tool 1's merge judge renames a node when it
    absorbs a label, and this reconstruction carries the FINAL labels back into
    an earlier state. So the terms are what those interviews really produced;
    their wording is the wording they ended the day with. For calibrating a
    threshold and a question that is the right trade — the alternative is 60
    live LLM runs per candidate.
    """
    people = sorted(
        (n for n in graph["nodes"] if n.get("type") == "person"),
        key=lambda n: (n.get("created_at", 0.0), n["id"]),
    )[:persons]
    kept = {n["id"] for n in people}

    edges = [e for e in graph["edges"] if e["source"] in kept]
    counts: dict[str, int] = {}
    for edge in edges:
        counts[edge["target"]] = counts.get(edge["target"], 0) + 1

    terms = [
        {**n, "mentions": counts[n["id"]]}
        for n in graph["nodes"]
        if n.get("type") == "term" and n["id"] in counts
    ]

    return {
        "version": graph["version"],
        "generated_at": graph["generated_at"],
        "min_mentions": graph["min_mentions"],
        "nodes": list(people) + terms,
        "edges": edges,
        "quotes": [q for q in graph["quotes"] if q.get("person_id") in kept],
    }


def floor_table(interview_count: int, day_seconds: float, floors) -> list[dict]:
    """How many dreams each candidate floor would have produced.

    No model involved: at an even cadence, a floor only binds when it is longer
    than the gap between interviews, and then it merges whole runs of them into
    one dream. `cadence_s` is reported because it, not the floor, is what
    decides the answer — a table that hid it would read as a fact about the
    floor when it is a fact about the day.
    """
    rows = []
    cadence = day_seconds / interview_count if interview_count else 0.0
    for floor in floors:
        if not interview_count:
            rows.append({"min_interval_s": floor, "cadence_s": cadence,
                         "dreams": 0, "collapsed": 0, "per_dream": 0.0})
            continue
        dreams = 0
        last: float | None = None
        for index in range(interview_count):
            at = index * cadence
            if last is None or at - last >= floor:
                dreams += 1
                last = at
        rows.append(
            {
                "min_interval_s": floor,
                "cadence_s": cadence,
                "dreams": dreams,
                "collapsed": interview_count - dreams,
                "per_dream": round(interview_count / dreams, 2) if dreams else 0.0,
            }
        )
    return rows


def _llm(cfg):
    from kg.llm import LLMClient  # pure wrapper — permitted by spec §3

    return LLMClient(
        model=cfg.condense_model,
        effort=cfg.condense_effort,
        max_tokens=cfg.condense_max_tokens,
        api_key=cfg.anthropic_api_key,
    )


def run_questions(graph: dict, cfg) -> None:
    llm = _llm(cfg)
    print("Vier Formulierungen, vier Graphgrößen. Nur die Frage ändert sich.\n")
    for question in QUESTIONS:
        print(f"=== {question}")
        for size in SIZES:
            material = build_material(prefix_graph(graph, size))
            enabled = contradiction_enabled(material, cfg.contradiction_min_persons)
            try:
                result = condense(llm, material, question, enabled)
                print(f"  {size:>2} Menschen: {result.sentence}")
            except Exception as exc:
                print(f"  {size:>2} Menschen: FEHLER — {exc}")
        print()
    # No recommendation (standing rule): reading them cold is the point.
    print("Gewählte Formulierung als `guiding_question` in config2.toml eintragen.")


def run_contradiction(graph: dict, cfg) -> None:
    llm = _llm(cfg)
    print(
        "Jede Größe zweimal: einmal mit der Widerspruchs-Anweisung, einmal ohne.\n"
        "Gesucht ist die Größe, ab der der Widerspruch im Material WIRKLICH da "
        "ist statt erfunden zu werden.\n"
    )
    for size in SIZES:
        material = build_material(prefix_graph(graph, size))
        print(f"=== {size} Menschen, {material.term_count} Begriffe")
        for enabled in (False, True):
            label = "mit Widerspruch " if enabled else "ohne Widerspruch"
            try:
                result = condense(llm, material, QUESTIONS[0], enabled)
                print(f"  {label}: {result.sentence}")
            except Exception as exc:
                print(f"  {label}: FEHLER — {exc}")
        print()
    print("Gewählte Schwelle als `contradiction_min_persons` in config2.toml eintragen.")


def run_floor(args) -> None:
    rows = floor_table(args.interviews, args.hours * 3600, tuple(args.floors))
    print(
        f"{args.interviews} Interviews über {args.hours} h "
        f"= alle {rows[0]['cadence_s']:.0f} s eines.\n"
    )
    print(f"{'min_interval_s':>15} {'Träume':>8} {'zusammengefasst':>16} {'Interviews/Traum':>18}")
    for row in rows:
        print(
            f"{row['min_interval_s']:>15} {row['dreams']:>8} "
            f"{row['collapsed']:>16} {row['per_dream']:>18}"
        )
    print(
        "\nEin Boden unterhalb der Taktung greift nie. Gewählten Wert als "
        "`min_interval_s` in config2.toml eintragen."
    )


def main() -> None:
    from kg2.config import load_dream_config

    parser = argparse.ArgumentParser(prog="sim.dream_calibrate")
    parser.add_argument("mode", choices=("questions", "contradiction", "floor"))
    parser.add_argument("--graph", default=str(FIXTURE))
    parser.add_argument("--config", default=None)
    parser.add_argument("--interviews", type=int, default=60)
    parser.add_argument("--hours", type=float, default=8.0)
    parser.add_argument("--floors", type=int, nargs="+", default=[120, 240, 360, 480, 900])
    args = parser.parse_args()

    if args.mode == "floor":
        run_floor(args)
        return

    cfg = load_dream_config(Path(args.config) if args.config else None)
    graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    if args.mode == "questions":
        run_questions(graph, cfg)
    else:
        run_contradiction(graph, cfg)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_dream_calibrate.py -v`
Expected: PASS (18 tests)

- [ ] **Step 5: Run the floor calibration (free, no credentials)**

```bash
uv run python -m sim.dream_calibrate floor
uv run python -m sim.dream_calibrate floor --interviews 40 --hours 6
```

Record the tables. They answer `min_interval_s` on their own.

- [ ] **Step 6: Run the question and contradiction calibrations**

Needs `ANTHROPIC_API_KEY`. 16 + 8 = 24 stage-1 calls, no images.

```bash
uv run python -m sim.dream_calibrate questions      | tee out/calibrate-questions.txt
uv run python -m sim.dream_calibrate contradiction  | tee out/calibrate-contradiction.txt
```

Report both outputs to Birk **with no recommendation**. His picks go into `config2.toml` and are recorded in `docs/operations.md` at Task 18.

- [ ] **Step 7: Commit**

```bash
git add sim/dream_calibrate.py tests/test_dream_calibrate.py
git commit -m "feat: calibrate the floor, the contradiction threshold and the question

Graph states at 3/10/30/60 persons are derived from the real run-19c artefact,
not invented. The floor is arithmetic over the day's cadence and needs no model
at all. Nothing in the output is marked as recommended — Birk reads it cold."
```

---

### Task 17: Pre-render series at 1 / 5 / 20 / 40 dreams

**Files:**
- Create: `sim/seed_dreams.py`, `sim/dream_prerender.py`
- Test: `tests/test_dream_prerender.py`

**Interfaces:**
- Consumes: Tasks 4, 10, 12, 15.
- Produces:
  - `sim.seed_dreams.SENTENCES` — 40 fictional German sentences
  - `sim.seed_dreams.seed_dreams(data_dir, count, images, *, start_at=..., sentences=SENTENCES) -> Path`
  - `sim.dream_prerender.render_series(dbs, out_dir, sizes=(1, 5, 20, 40)) -> list[Shot]`
  - CLI: `uv run python -m sim.dream_prerender --out out/dream-prerender1`

Tool 1's Task 20, held for Tool 2: **the page is judged full, not empty.** A strip at one dream tells you nothing about the strip at forty, and forty is what the wall looks like at 17:00 — the state Birk actually has to approve.

**Build order matters, and it is the cheap path first** (Birk, 2026-08-25): get the harness working end-to-end on the ~6-image pool, so the 40 real images are spent on a page that is already correct rather than on debugging Playwright. `--generate` is the last step before the visual review, and its cost is stated in the task text so the spend is deliberate.

- [ ] **Step 1: Write the failing test**

`tests/test_dream_prerender.py`:

```python
"""Tool 1's Task 20 discipline for Tool 2: judge the strip full, not empty."""

from __future__ import annotations

import struct
import zlib

import pytest

from kg2.config import DreamConfig
from kg2.store import DreamStore
from sim.seed_dreams import SENTENCES, seed_dreams


def png_bytes() -> bytes:
    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
        + chunk(b"IEND", b"")
    )


@pytest.fixture()
def pool(tmp_path):
    directory = tmp_path / "pool"
    directory.mkdir()
    paths = []
    for index in range(6):
        path = directory / f"pool-{index}.png"
        path.write_bytes(png_bytes())
        paths.append(path)
    return paths


def test_there_are_enough_sentences_for_a_full_day():
    assert len(SENTENCES) >= 40
    assert len(set(SENTENCES)) == len(SENTENCES)


def test_the_sentences_are_german_and_roughly_the_right_length():
    """Spec §5.1's target. A seeded strip judged on 8-word sentences would not
    tell Birk whether a real 30-word one fits."""
    for sentence in SENTENCES:
        assert 15 <= len(sentence.split()) <= 45


def test_seed_dreams_writes_the_requested_number(tmp_path, pool):
    db_path = seed_dreams(tmp_path / "state", count=20, images=pool)

    store = DreamStore.open(db_path)
    assert len(store.visible_dreams()) == 20
    store.close()


def test_every_seeded_dream_has_a_real_image_file(tmp_path, pool):
    db_path = seed_dreams(tmp_path / "state", count=12, images=pool)

    cfg = DreamConfig(data_dir=db_path.parent)
    store = DreamStore.open(db_path)
    for dream in store.visible_dreams():
        assert (cfg.image_dir / dream.image_path).read_bytes().startswith(b"\x89PNG")
    store.close()


def test_the_pool_is_cycled_when_it_is_smaller_than_the_count(tmp_path, pool):
    """The cheap path. Faked variety, and the CLI says so — but the harness is
    correct before the 40 real images are spent on it."""
    db_path = seed_dreams(tmp_path / "state", count=20, images=pool)

    store = DreamStore.open(db_path)
    assert len(store.visible_dreams()) == 20
    store.close()


def test_the_dreams_are_spaced_like_a_real_day(tmp_path, pool):
    """A strip whose timestamps all collide would not exercise the ordering."""
    db_path = seed_dreams(tmp_path / "state", count=10, images=pool)

    store = DreamStore.open(db_path)
    times = [d.created_at for d in store.visible_dreams()]
    assert times == sorted(times)
    assert len(set(times)) == 10
    store.close()


def test_a_smaller_seed_is_a_prefix_of_a_larger_one(tmp_path, pool):
    """Same discipline as Tool 1's seed_graph: 1, 5, 20 and 40 must be the same
    day at four points, not four different days."""
    small = seed_dreams(tmp_path / "a", count=5, images=pool)
    large = seed_dreams(tmp_path / "b", count=40, images=pool)

    store_a, store_b = DreamStore.open(small), DreamStore.open(large)
    first_five = [d.sentence for d in store_b.visible_dreams()][:5]
    assert [d.sentence for d in store_a.visible_dreams()] == first_five
    store_a.close()
    store_b.close()


def test_seeding_needs_no_credentials_and_no_network(tmp_path, pool):
    """The whole point of the cheap path: the harness is debuggable offline."""
    db_path = seed_dreams(tmp_path / "state", count=40, images=pool)

    assert db_path.is_file()


def test_the_page_renders_at_every_size(tmp_path, pool, page, static_server):
    """The series' own assertion, without Playwright driving a server: the view
    is fed the same state shape the server produces."""
    from kg.bus import EventBus
    from kg2.server import create_dream_app, dream_state, seed_display_settings

    page.goto(f"{static_server}/frontend2/static/dream-harness.html")
    page.wait_for_function("window.kgDream !== undefined")

    for size in (1, 5, 20, 40):
        db_path = seed_dreams(tmp_path / f"state-{size}", count=size, images=pool)
        cfg = DreamConfig(data_dir=db_path.parent)
        store = DreamStore.open(db_path)
        seed_display_settings(store, cfg)
        state = dream_state(store, cfg)
        # The images are file paths under a temp dir the browser cannot read,
        # so swap in an inline pixel; the layout question is unaffected.
        pixel = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
        state["current"]["image"] = pixel
        for entry in state["history"]:
            entry["image"] = pixel

        page.evaluate("(s) => window.kgDream.applyState(s)", state)
        page.wait_for_function("() => window.kgDream.fading === false", timeout=10000)

        assert page.locator("#strip li").count() == size - 1
        assert page.locator("#sentence").inner_text() != ""
        strip = page.locator("#strip").bounding_box()
        assert strip["y"] + strip["height"] <= 1081
        store.close()
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_dream_prerender.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sim.seed_dreams'`

- [ ] **Step 3: Implement `sim/seed_dreams.py`**

```python
"""Seed a dreams.sqlite3 directly, with no model calls (Tool 1's Task 20 rule).

The point of the pre-render series is LAYOUT — how a strip of forty reads at the
bottom of a 65″ screen, whether a 30-word sentence still fits under the image.
None of that needs real generation, and making it need real generation would
mean debugging Playwright at a euro a frame.

So: fictional sentences of realistic length, and images from a pool. The `--generate`
path in `sim/dream_prerender.py` swaps the pool for forty real ones once the
harness is known to be correct.
"""

from __future__ import annotations

from pathlib import Path

from kg2.config import DreamConfig
from kg2.store import DreamStore

#: Forty fictional dreams of one fictional festival day. Written to spec §5.1's
#: 20-40 word target, so the layout is judged against sentences the real system
#: would actually produce — a strip judged on eight-word captions proves nothing
#: about a thirty-word one.
#:
#: Invented outright, and deliberately not drawn from the corpus: these end up
#: in a review directory, and a half-formed dream of real people's words does
#: not belong there.
SENTENCES = [
    "In einem Hof, der gleichzeitig gegossen und bepflanzt wird, warten zwei Generationen darauf, dass die jeweils andere zuerst aufgibt.",
    "Die Bagger halten an, weil jemand vergessen hat, wem der Boden gehört, und die Baugrube füllt sich langsam mit Schilf.",
    "Ein Haus lernt sprechen und benutzt sein erstes Wort, um nach der Miete zu fragen, die niemand mehr aufbringen kann.",
    "Über der Umgehungsstraße hängt ein Dorf an Seilen, und die, die es gebaut haben, dürfen nicht darin wohnen.",
    "Hundert Klebepunkte auf einem Plan ergeben zusammen ein Gesicht, das niemand wiedererkennt und alle unterschrieben haben.",
    "Der Beton atmet zum ersten Mal aus, und was er ausatmet, ist der Staub aller Häuser, die vorher hier standen.",
    "In der Tiefgarage wächst ein Wald, dessen Bäume nach oben durch die Decke wollen und dabei sehr höflich bleiben.",
    "Eine Maschine plant ein Zuhause, das perfekt ist, bis auf den Geruch, und genau daran erkennt es jeder sofort.",
    "Die Fassade wird jeden Morgen neu gedruckt, und jeden Abend sammelt jemand die alte auf und trägt sie fort.",
    "Zwei Nachbarn teilen sich eine Wand und streiten seit zwölf Jahren darüber, auf welcher Seite sie eigentlich steht.",
    "Der Kran über dem Quartier dreht sich weiter, obwohl unten längst niemand mehr baut, und niemand traut sich, ihn abzustellen.",
    "Aus dem Leerstand im Erdgeschoss wächst nachts ein Marktplatz, der morgens wieder verschwindet und Krümel hinterlässt.",
    "Ein Dach aus Solarzellen wirft einen Schatten, in dem nichts mehr wächst, und alle finden das trotzdem richtig.",
    "Die Wohnung ist so klug geworden, dass sie ihre Bewohner beim Namen nennt und dabei jedes Mal zögert.",
    "Im Modell steht schon der Park, im Maßstab eins zu fünfhundert, wo draußen noch der Parkplatz auf sein Ende wartet.",
    "Ein Bagger und eine Buche stehen sich gegenüber, und beide warten darauf, dass eine Behörde endlich zurückschreibt.",
    "Die Bauakte wird so schwer, dass sie durch den Boden des Amtes bricht und im Archiv darunter weiterwächst.",
    "Hinter der Dämmung wohnt seit Jahren ein Vogel, den niemand entfernen darf und niemand füttern will.",
    "Ein Neubau steht fertig da und wartet auf Menschen, die sich ihn ausgerechnet deshalb nicht leisten können.",
    "Der Fluss holt sich die Uferstraße zurück, sehr langsam, und die Stadt nennt es einen Naturerlebnisraum.",
    "In der Mitte des Quartiers steht ein Haus, das allen gehört und deshalb von niemandem repariert wird.",
    "Die Ziegel erinnern sich an die Hand, die sie gelegt hat, und geben das Wissen an keine Maschine weiter.",
    "Ein Aufzug fährt durch ein Gebäude, das es nicht mehr gibt, und hält weiter zuverlässig im vierten Stock.",
    "Die neue Siedlung ist aus dem Abbruch der alten gebaut, und nachts hört man, dass das Material sich nicht einig ist.",
    "Ein Balkon wächst so weit über die Straße, dass er dem Balkon gegenüber die Hand geben könnte, wenn er dürfte.",
    "Die Bewohner planen ihr Haus gemeinsam und finden nach vier Jahren heraus, dass alle etwas anderes gezeichnet haben.",
    "Auf dem Dach steht ein Feld, unten steht ein Supermarkt, und dazwischen redet niemand miteinander.",
    "Der Rechner schlägt vor, die Straße zu verschmälern, und schlägt gleichzeitig vor, mehr Autos hineinzulassen.",
    "Ein Fenster wird jeden Winter kleiner, weil die Dämmung von innen wächst, und irgendwann ist es eine Erinnerung.",
    "Zwei Bauträger bauen dasselbe Grundstück, jeder ohne den anderen zu sehen, und die Häuser stehen ineinander.",
    "Der Hof ist versiegelt, damit nichts wächst, und die Kinder tragen jeden Tag ein bisschen Erde hinein.",
    "Ein Kalksandstein träumt davon, wieder Sand zu sein, und wartet darauf, dass die Abrissbirne endlich kommt.",
    "Die Beteiligung war vorbildlich, das Protokoll ist zweihundert Seiten lang, und gebaut wird der erste Entwurf.",
    "Im Treppenhaus hängt ein Plan des Gebäudes, auf dem eine Wohnung eingezeichnet ist, die niemand finden kann.",
    "Der Rohbau steht seit sieben Jahren offen, und Efeu hat entschieden, dass er jetzt die Fassade macht.",
    "Ein Dorf zieht in die Stadt und die Stadt zieht aufs Land, und sie begegnen sich auf halber Strecke am Bahnhof.",
    "Die Wärmepumpe summt so laut, dass die Nachbarn ausziehen, und danach ist die Bilanz endlich ausgeglichen.",
    "Auf der Brache steht ein Schild, das eine Zukunft ankündigt, und das Schild ist inzwischen älter als die Brache.",
    "Ein Haus aus Lehm steht neben einem Haus aus Beton, und beide behaupten, das jeweils andere sei die Vergangenheit.",
    "Die letzte Baugenehmigung des Jahres wird erteilt für ein Gebäude, das seine eigene Grundfläche wieder freigeben soll.",
]

#: A realistic festival-day cadence: one dream every eight minutes.
SPACING_S = 480.0
START_AT = 1_700_000_000.0


def seed_dreams(data_dir, count: int, images, *, start_at=START_AT, sentences=None) -> Path:
    """Write `count` finished dreams into a fresh store. Returns the db path.

    `images` is a list of source PNGs, cycled if it is shorter than `count`.
    Sentences are taken in order, so a 5-dream seed is a strict PREFIX of a
    40-dream one — the same day at two points, not two different days. Tool 1's
    `seed_graph` holds the same property for the same reason.
    """
    sentences = SENTENCES if sentences is None else sentences
    if count > len(sentences):
        raise ValueError(f"only {len(sentences)} sentences available, {count} requested")
    images = list(images)
    if not images:
        raise ValueError("seed_dreams needs at least one source image")

    cfg = DreamConfig(data_dir=Path(data_dir))
    store = DreamStore.open(cfg.db_path)
    for index in range(count):
        at = start_at + index * SPACING_S
        persons = 3 + index * 2  # the graph grows through the day
        dream = store.create_dream(
            created_at=at,
            graph_generated_at=at - 30.0,
            person_count=persons,
            term_count=persons * 3,
            edge_count=persons * 4,
            contradiction=persons >= 6,
            guiding_question=cfg.guiding_question,
            absorbed_persons=[f"p{n}" for n in range(1, persons + 1)],
        )
        store.set_stage1(
            dream.id,
            prompt="(seeded — no model call)",
            sentence=sentences[index],
            model=cfg.condense_model,
        )
        store.set_stage2_prompt(
            dream.id, prompt="(seeded — no model call)", model=cfg.image_model
        )
        filename = f"{dream.id}.png"
        (cfg.image_dir / filename).write_bytes(
            Path(images[index % len(images)]).read_bytes()
        )
        store.finish_dream(dream.id, image_path=filename)
    store.close()
    return cfg.db_path
```

- [ ] **Step 4: Implement `sim/dream_prerender.py`**

```python
"""The page at 1 / 5 / 20 / 40 dreams (spec §11's visual series).

Tool 1's Task 20 rule, held here: **the strip is judged FULL, not empty.** One
dream tells you nothing about forty, and forty is what the wall looks like at
17:00 — the state that actually has to be approved.

Build order, decided 2026-08-25: the cheap path FIRST. `--pool` seeds from a
handful of images so the harness can be made correct offline and for free; only
then is `--generate` run, so forty real images are spent on a page that already
works rather than on debugging a screenshot loop.
"""

from __future__ import annotations

import argparse
import shutil
import socket
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import uvicorn

from kg.bus import EventBus
from kg2.config import DreamConfig
from kg2.server import create_dream_app, seed_display_settings
from kg2.store import DreamStore

SIZES = (1, 5, 20, 40)


@dataclass(frozen=True)
class Shot:
    path: Path
    description: str
    coverage: dict = field(default_factory=dict)


# What the layout is judged by. Measured in the page, not guessed from the CSS.
MEASURE = """
() => {
  const strip = document.getElementById('strip');
  const stage = document.getElementById('stage');
  const sentence = document.getElementById('sentence');
  const thumbs = Array.from(strip.children);
  const box = (el) => el.getBoundingClientRect();
  return {
    strip_items: thumbs.length,
    strip_height_fraction: box(strip).height / window.innerHeight,
    stage_height_fraction: box(stage).height / window.innerHeight,
    // Asymmetric by design (spec §6): the current dream is the subject.
    stage_to_thumb: thumbs.length ? box(stage).height / box(thumbs[0]).height : null,
    thumb_width_px: thumbs.length ? box(thumbs[0]).width : null,
    sentence_px: parseFloat(getComputedStyle(sentence).fontSize),
    sentence_lines: Math.round(box(sentence).height /
      parseFloat(getComputedStyle(sentence).lineHeight)),
    // Everything must be inside the viewport, at every size.
    overflows: box(strip).bottom > window.innerHeight + 1,
  };
}
"""


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _serve(store, cfg):
    """The REAL app on an ephemeral port — same pattern as sim/prerender.py."""
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_dream_app(store, cfg, EventBus()),
                       host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        raise RuntimeError("dream prerender server did not start")

    def shutdown():
        server.should_exit = True
        thread.join(timeout=10)

    return f"http://127.0.0.1:{port}", shutdown


def _launch_chromium(playwright):
    # Same fallback as tests/conftest.py and sim/prerender.py: this host cannot
    # `playwright install` the pinned revision, but a compatible build is
    # cached. Reused rather than reinvented, or this breaks on this machine.
    try:
        return playwright.chromium.launch()
    except Exception:
        candidates = sorted(
            Path.home().glob(".cache/ms-playwright/chromium-*/chrome-linux64/chrome")
        )
        if not candidates:
            raise
        return playwright.chromium.launch(executable_path=str(candidates[-1]))


def render_series(dbs: dict[int, Path], out_dir, sizes=SIZES) -> list[Shot]:
    """One screenshot per size, through the real page and the real server."""
    from playwright.sync_api import sync_playwright

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    shots: list[Shot] = []

    with tempfile.TemporaryDirectory(prefix="dream-prerender-") as tmp, sync_playwright() as pw:
        scratch = Path(tmp)
        browser = _launch_chromium(pw)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        for size in sizes:
            # A throwaway copy per size, for the same reason Tool 1's series
            # takes one: a series must be reproducible from its seed alone.
            copy = scratch / f"size-{size:02d}"
            shutil.copytree(dbs[size].parent, copy)
            cfg = DreamConfig(data_dir=copy)
            store = DreamStore.open(cfg.db_path)
            seed_display_settings(store, cfg)
            base_url, shutdown = _serve(store, cfg)
            try:
                page.goto(f"{base_url}/dream")
                page.wait_for_function("window.kgDreamReady === true", timeout=30000)
                page.wait_for_function(
                    "() => window.kgDream.fading === false", timeout=30000
                )
                # Let every thumbnail decode before the shot, or a cold cache
                # produces a strip of empty boxes — Tool 1 hit exactly this
                # with portraits.
                page.evaluate(
                    "() => Promise.all(Array.from(document.images)"
                    ".filter((i) => !i.complete)"
                    ".map((i) => new Promise((r) => { i.onload = r; i.onerror = r; })))"
                )
                page.wait_for_timeout(400)
                coverage = page.evaluate(MEASURE)
                target = out_dir / f"dream-{size:02d}-dreams.png"
                page.screenshot(path=str(target))
                shots.append(
                    Shot(
                        target,
                        f"Der Traum-Schirm bei {size} Träumen: "
                        f"{coverage['strip_items']} im Streifen, Streifen "
                        f"{coverage['strip_height_fraction']:.0%} der Bildhöhe, "
                        f"aktuelles Bild {coverage['stage_height_fraction']:.0%}. "
                        f"Der Satz steht in {coverage['sentence_lines']} Zeile(n) "
                        f"bei {coverage['sentence_px']:.0f}px.",
                        coverage,
                    )
                )
            finally:
                shutdown()
                store.close()
        browser.close()
    return shots


def _pool_images(source: Path) -> list[Path]:
    images = sorted(Path(source).glob("*.png"))
    if not images:
        raise SystemExit(
            f"no PNGs in {source}. Run `python -m sim.dream_register --out {source}` "
            "first, or point --pool at a directory that has some."
        )
    return images


def _generate_images(count: int, out: Path, cfg) -> list[Path]:
    """The expensive path: `count` real images in the configured register.

    COST: one image-model call per image. At 40 that is 40 calls. Run this ONLY
    once the series is known to render correctly from --pool.
    """
    from kg2.imagegen import build_image_prompt, render_image, save_image
    from sim.seed_dreams import SENTENCES

    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for index in range(count):
        target = out / f"generated-{index:02d}.png"
        if target.exists():
            paths.append(target)
            continue
        prompt = build_image_prompt(
            SENTENCES[index], cfg.visual_register, cfg.image_aspect_ratio
        )
        data = render_image(
            prompt, model=cfg.image_model, api_key=cfg.openrouter_api_key,
            url=cfg.image_url, timeout=cfg.image_timeout_s,
        )
        save_image(data, target)
        print(f"  {index + 1}/{count} {target.name}")
        paths.append(target)
    return paths


def main() -> None:
    from kg2.config import load_dream_config
    from sim.seed_dreams import seed_dreams

    parser = argparse.ArgumentParser(prog="sim.dream_prerender")
    parser.add_argument("--out", default="out/dream-prerender1")
    parser.add_argument("--state", default="out/dream-prerender1-state")
    parser.add_argument("--config", default=None)
    parser.add_argument("--sizes", type=int, nargs="+", default=list(SIZES))
    parser.add_argument(
        "--pool",
        default="out/register1",
        help="directory of PNGs to cycle through (the cheap path, and the "
        "default: the harness must be correct before real images are spent)",
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="render one REAL image per dream in the configured register. "
        "COSTS one image-model call per dream — 40 calls for the full series. "
        "Run this only once --pool has proved the page renders correctly.",
    )
    args = parser.parse_args()

    cfg = load_dream_config(Path(args.config) if args.config else None)
    largest = max(args.sizes)

    if args.generate:
        print(f"Generating {largest} real images — {largest} calls to {cfg.image_model}.")
        images = _generate_images(largest, Path(args.state) / "generated", cfg)
    else:
        images = _pool_images(Path(args.pool))
        print(
            f"Pool path: {len(images)} images cycled across up to {largest} dreams. "
            "The variety in the strip is FAKE — use --generate before judging it."
        )

    dbs = {}
    for size in sorted(args.sizes):
        state = Path(args.state) / f"dreams-{size:02d}"
        shutil.rmtree(state, ignore_errors=True)
        dbs[size] = seed_dreams(state, count=size, images=images)

    for shot in render_series(dbs, Path(args.out), tuple(sorted(args.sizes))):
        print(shot.path.resolve())
        print(f"    {shot.description}")
        if shot.coverage.get("overflows"):
            print("    WARNUNG: der Streifen läuft unten aus dem Bild.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_dream_prerender.py -v`
Expected: PASS (9 tests)

- [ ] **Step 6: Run the cheap path and fix the harness against it**

```bash
uv run python -m sim.dream_prerender --out out/dream-prerender1 --pool out/register1
```

Look at all four PNGs. The strip must not overflow at 40, the sentence must be readable, and the asymmetry must be obvious. **Fix anything wrong here, before spending on real images.**

- [ ] **Step 7: Run the real 40-image series**

**COST: 40 image-model calls.** Run this only once Step 6's output is correct, and only once Birk's register is in `config2.toml`.

```bash
uv run python -m sim.dream_prerender --out out/dream-prerender2 --generate
```

Report all four PNGs to Birk for the visual review.

- [ ] **Step 8: Commit**

```bash
git add sim/seed_dreams.py sim/dream_prerender.py tests/test_dream_prerender.py
git commit -m "feat: pre-render the dream page at 1, 5, 20 and 40 dreams

The strip is judged full, not empty — 40 is what the wall looks like at 17:00.
The pool path is the default so the harness is made correct offline and for
free; --generate spends 40 real calls only once the page already works."
```

---

### Task 18: The dream machine's runbook and the calibrated values

**Files:**
- Modify: `docs/operations.md`, `config2.example.toml`
- Test: `tests/test_dream_runbook.py`

**Interfaces:**
- Consumes: every task. Records the outputs of Tasks 15, 16 and 17.
- Produces: no module. `docs/operations.md` gains a Tool 2 section.

Tool 1's Task 21 rule, and the brief check it answered: **the runbook documents nothing that cannot be reached from the operator UI.** Every claim below must be checked against the code before it is written.

`min_interval_s`, `contradiction_min_persons`, `guiding_question` and `visual_register` are recorded here as **calibrated values with the run that produced them**, exactly as Tool 1's density values are — not as guesses, and not with a recommendation attached to a choice that was Birk's.

- [ ] **Step 1: Write the failing test**

`tests/test_dream_runbook.py`:

```python
"""The runbook must not describe a control that does not exist, and must not
carry placeholders into the exhibition day. Tool 1's Task 21 rule."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RUNBOOK = Path("docs/operations.md").read_text(encoding="utf-8")
EXAMPLE = Path("config2.example.toml").read_text(encoding="utf-8")


def tool2_section() -> str:
    start = RUNBOOK.index("## Kollektivtraum")
    return RUNBOOK[start:]


def test_the_runbook_has_a_tool_2_section():
    assert "## Kollektivtraum" in RUNBOOK


def test_the_runbook_carries_no_placeholders():
    section = tool2_section()
    for placeholder in ("TODO", "TBD", "XXX", "<hier", "…tragen", "PLATZHALTER"):
        assert placeholder not in section


def test_every_calibrated_value_is_recorded_with_its_run():
    section = tool2_section()
    for key in ("min_interval_s", "contradiction_min_persons",
                "guiding_question", "visual_register"):
        assert key in section


def test_the_recorded_values_match_the_example_config():
    """A runbook that disagrees with the file the operator copies is worse than
    no runbook."""
    section = tool2_section()
    for key in ("min_interval_s", "contradiction_min_persons"):
        in_config = re.search(rf"^{key}\s*=\s*(\d+)", EXAMPLE, re.M)
        assert in_config, f"{key} missing from config2.example.toml"
        assert in_config.group(1) in section, (
            f"{key} = {in_config.group(1)} in config2.example.toml "
            f"but that value does not appear in the runbook"
        )


def test_the_guiding_question_in_the_runbook_is_the_one_in_the_config():
    question = re.search(r'^guiding_question\s*=\s*"([^"]+)"', EXAMPLE, re.M)
    assert question
    assert question.group(1) in tool2_section()


def test_the_runbook_describes_only_controls_that_exist():
    """Every control named must be reachable in the operator UI."""
    operator = Path("frontend2/operator.html").read_text(encoding="utf-8")
    section = tool2_section()

    if "Jetzt träumen" in section:
        assert "Jetzt träumen" in operator
    if "Schreibmaschine" in section:
        assert "Schreibmaschine" in operator
    if "verwerfen" in section:
        assert "verwerfen" in operator


@pytest.mark.parametrize(
    "claim,evidence",
    [
        # Every command the runbook tells the operator to type must exist.
        ("python -m kg2", "kg2/__main__.py"),
        ("--no-watch", "kg2/__main__.py"),
    ],
)
def test_every_command_the_runbook_names_really_exists(claim, evidence):
    section = tool2_section()
    if claim not in section:
        pytest.skip(f"{claim} is not mentioned")
    assert claim.split()[-1] in Path(evidence).read_text(encoding="utf-8")


def test_the_cross_machine_check_is_run_from_the_other_box():
    """The pitfall CR-1 names: a curl on the server succeeds even when the bind
    is wrong, and therefore proves nothing."""
    assert "Traum-Maschine" in RUNBOOK
    assert "nicht auf dem Ausstellungsrechner" in RUNBOOK


def test_the_runbook_says_what_a_restart_preserves():
    section = tool2_section()

    assert "Neustart" in section
    for preserved in ("Streifen", "Einstellung"):
        assert preserved in section
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/test_dream_runbook.py -v`
Expected: FAIL — `ValueError: substring not found` (no `## Kollektivtraum` section yet).

- [ ] **Step 3: Write the runbook section**

Append to `docs/operations.md`. **Every value marked `‹…›` below must be replaced with the real result of Tasks 15, 16 and 17 before this task is complete** — the test above fails on placeholders, deliberately.

```markdown
## Kollektivtraum — Screen B (Tool 2)

Läuft auf einer **eigenen kleinen Maschine** neben dem Ausstellungsrechner
(Spec §9). Tool 1 und Tool 2 hängen nicht voneinander ab: Fällt Tool 2 aus,
bleibt die Wand unberührt; fällt Tool 1 aus, zeigt Screen B seinen letzten
Traum und den vollen Verlaufsstreifen weiter.

### Vor dem Festival, auf der Traum-Maschine

1. Zwei Geheimnisse exportieren (nie in `config2.toml`, nie aus `~/.hermes/.env`):

   ```bash
   export ANTHROPIC_API_KEY=...      # Stufe 1: Graph -> Satz
   export OPENROUTER_API_KEY=...     # Stufe 2: Satz -> Bild
   ```

2. `cp config2.example.toml config2.toml`, dann `tool1_url` auf die Adresse
   setzen, die der Core beim Start ausgibt.

3. **Netzprüfung, von DIESER Maschine aus** (siehe „Netzwerk für Screen B und
   Screen C" oben — auf dem Ausstellungsrechner selbst gelingt sie auch bei
   falschem Bind und beweist deshalb nichts):

   ```bash
   curl -s http://<adresse>:8800/graph.json | head -c 200
   ```

4. Rauchtest ohne Ausstellungsrechner und ohne Modelle:

   ```bash
   uv run python -m kg2 --no-watch
   ```

   Danach `http://<traum-maschine>:8810/dream` und `/operator` öffnen.

### Der Rhythmus

Ein Traum entsteht, **wenn ein Interview fertig verarbeitet ist** — nicht nach
der Uhr, nie während der Stille. Der Watcher fragt alle
`poll_interval_s` Sekunden `graph.json` ab und erkennt ein fertiges Interview
daran, dass ein Personenknoten **Kanten hat**. Ein Personenknoten ohne Kanten
ist erst das Foto; die Begriffe kommen Sekunden bis Minuten später (Spec §4.1).

Zwischen zwei Träumen liegen mindestens `min_interval_s` Sekunden. Landen
mehrere Interviews in diesem Fenster, werden sie zu **einem** Traum
zusammengefasst — der Traum ist der des ganzen Graphen, nicht der einer Person.

### Die Regler (alle im Operator-Fenster der Traum-Maschine)

**Anzeige** — Leitfrage zeigen/verbergen und nach N Sekunden ausblenden;
Überblenddauer; Streifenhöhe; Schreibmaschine an/aus.

**Ablauf** — „Jetzt träumen" (ignoriert den Mindestabstand; für den Moment, in
dem jemand vom Veranstalter vor dem Schirm steht), „Pause", „Aktuellen Traum
verwerfen".

> **Verwerfen ist der einzige Notausgang** (Spec §7). Es nimmt das Bild in
> einem Schritt vom großen Schirm **und** aus dem Verlaufsstreifen; der
> vorherige Traum rückt wieder nach vorn. Der Datensatz bleibt erhalten —
> „zurückholen" ist derselbe Knopf. Kein Freigabeprozess, keine Kuratierung.

**Nicht im Interface, absichtlich:** Leitfrage, Bildregister und Gewichtung.
Alle drei werden morgens in `config2.toml` gesetzt. Eine wandernde Leitfrage
macht genau die Vergleichbarkeit kaputt, für die der Verlaufsstreifen da ist.

### Wenn etwas ausfällt

| Symptom | Bedeutung | Maßnahme |
|---|---|---|
| Bild wechselt nicht mehr, Streifen steht | Cloud oder Netz weg | Nichts tun. Das letzte Bild bleibt stehen, der nächste Trigger versucht es erneut. Kein Retry-Sturm, keine Zusatzkosten. |
| Nie ein neuer Traum, obwohl Interviews laufen | Tool 1 nicht erreichbar | `curl http://<adresse>:8800/graph.json` **von der Traum-Maschine**. Danach Bind und Firewall prüfen. |
| Screen B ist schwarz | Tool-2-Prozess tot | Neu starten. Wand und zweiter Raum sind unberührt. |
| Bild ist unbrauchbar oder peinlich | Bildmodell | „Aktuellen Traum verwerfen". Der vorherige kommt zurück. |
| Traum steht auf „läuft" und wird nicht fertig | Absturz mitten im Zyklus | Nichts tun — er erscheint nie auf dem Schirm. Der nächste Trigger macht einen neuen. |
| Platte voll | ~40 Bilder am Tag zu einigen hundert KB | Für einen Tag kein Thema (Spec §8). Bewusst nicht wegprogrammiert. |

**Physischer Rückfallweg:** LTE-Stick. Beide Cloud-Aufrufe hängen am Uplink,
und Messe-WLAN ist genau dort um 14 Uhr am schwächsten.

**Was ein Neustart erhält:** den aktuellen Traum, den vollständigen
Verlaufsstreifen inklusive der verworfenen Einträge (als verworfen), jede
Anzeige-Einstellung, den Pausenzustand — und die Information, welche Interviews
schon geträumt wurden, sodass nach dem Neustart weder alles noch einmal geträumt
wird noch gar nichts mehr. Alles liegt in `dreams.sqlite3`; nichts nur im
Speicher.

### Kalibrierte Werte (Tool 2)

Diese Werte stehen in `config2.toml` und werden im Betrieb **nicht** verändert.

- `min_interval_s` = **‹Wert›** — ‹aus `sim.dream_calibrate floor`: bei 60
  Interviews über 8 h liegt die Taktung bei 480 s; hier die Tabellenzeile
  eintragen, die den gewählten Wert begründet›.
- `contradiction_min_persons` = **‹Wert›** — ‹aus
  `sim.dream_calibrate contradiction`: die Größe, ab der der Widerspruch im
  Material wirklich vorhanden war statt erfunden zu werden›.
- `guiding_question` = **„‹Wortlaut›"** — von Birk aus vier Kandidaten gewählt
  (`sim.dream_calibrate questions`, Sätze bei 3/10/30/60 Menschen).
- `visual_register` = **‹Name›** — von Birk an den Bildern gewählt
  (`sim.dream_register`, vier Register auf identischem erfundenem Satz).
- `poll_interval_s` = **5** — bei diesem Mindestabstand ist eine
  Erkennungsverzögerung von 5 s unsichtbar (Spec §4.1).

**Vorab-Renderings:** `out/dream-prerender2/` zeigt die Seite bei 1, 5, 20 und
40 Träumen. Der Streifen wird voll beurteilt, nicht leer — 40 ist der Zustand um
17 Uhr.
```

- [ ] **Step 4: Fill in every ‹…› from the real runs**

Replace each `‹…›` with the actual result of Tasks 15, 16 and 17, and set the same values in `config2.example.toml`. The test in Step 1 fails while any placeholder remains — that is deliberate.

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_dream_runbook.py -v`
Expected: PASS (9 tests)

- [ ] **Step 6: Run the whole suite**

Run: `uv run pytest tests/ -q`
Expected: PASS. Record the total in the ledger, alongside Tool 1's 277.

- [ ] **Step 7: Commit**

```bash
git add docs/operations.md config2.example.toml tests/test_dream_runbook.py
git commit -m "docs: on-site runbook for the dream machine, with calibrated values

Tool 1's Task 21 rule holds here: nothing is documented that cannot be reached
from the operator UI, and every calibrated value is recorded with the run that
produced it. A test fails on placeholders so none can reach the festival."
```

---

## Self-review

Run through this before declaring the plan finished.

**Spec coverage.** Every section has a task:

| Spec | Task |
|---|---|
| §1 what this builds | 7 (the stance in the prompt), 12 (the page) |
| §2 hard constraints | 3 (read-only client), Global Constraints |
| §3 architecture / `kg2` beside `kg` | 2, and the §3 import rule in every task |
| §3.1 the one Tool 1 change | 1 (spec corrected; only `kg/__main__.py` touched) |
| §4 / §4.1 the trigger and its race | 5, integrated in 11 |
| §4.2 `interview_absorbed` event | **out of scope** (§12) — not built |
| §5.1 stage 1, weighting, contradiction | 6, 7 |
| §5.2 stage 2, fixed register, no overwrite | 8 |
| §5.3 reproducibility | 4 (schema), 9 (write order), 10 (`/api/dreams`) |
| §6 screen B, cross-fade, typewriter, no dashboard | 12 |
| §7 operator UI, discard, what is NOT in it | 10, 13 |
| §8 failure modes, crash recovery | 9, 11, 14 |
| §9 machine and network | 1 (cross-machine check), 18 (runbook) |
| §10 values to calibrate | 15 (register), 16 (question, threshold, floor) |
| §11 testing & verification | every task; 14 (failure modes), 17 (visual series) |
| §12 out of scope | nothing built; §12 items named in Global Constraints |
| §13 what Tool 1 must not lose | 3 (four properties pinned), 5 (the fifth, timing) |

**Placeholder scan.** The only intentional placeholders are the `‹…›` markers in Task 18's runbook template and the two `DEFAULT_*` constants in `kg2/config.py`. All three are guarded: `tests/test_dream_runbook.py` fails while a `‹…›` remains, and the config defaults are explicitly labelled as Birk's decisions from Tasks 15/16.

**Type consistency.** `DreamStore.finish_dream(dream_id, *, image_path)` and `set_stage1(dream_id, *, prompt, sentence, model)` are used with those exact keywords in Tasks 9, 11, 14 and 17. `TriggerState`/`Decision` field names match between Tasks 5 and 11. `dream_payload` keys (`id`, `created_at`, `sentence`, `image`) match what `dream.js` reads in Task 12 and what the tests construct in Tasks 12, 13 and 17. `render_image(prompt, *, model, api_key, url, timeout)` is called with those keywords in Tasks 9, 15 and 17.

**Two known limitations, stated rather than hidden.**

1. `prefix_graph` (Task 16) carries the *final* merged labels back into earlier graph states, because Tool 1's store keeps no rename history. Documented in the function's own docstring. The alternative — 60 live pipeline runs per candidate wording — buys precision that a threshold and a question wording do not need.
2. The register and question calibrations cost real API calls and cannot run in CI. They are CLI runs whose *outputs* are recorded in `docs/operations.md`, exactly as Tool 1's run 19c is.
