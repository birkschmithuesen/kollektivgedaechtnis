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
