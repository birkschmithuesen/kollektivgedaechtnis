# `graph-20a.json` — where this file comes from

**Not a fixture. A real artefact.** Spec §11 of the Kollektivtraum design
requires Tool 2's contract tests to run against a real `graph.json` produced by
`sim/replay.py`, never a hand-written one — because a hand-written fixture
encodes today's assumption about the format and then passes forever while the
real file drifts away from it.

| | |
|---|---|
| Produced by | `uv run python -m sim.replay --db out/sim20.db` |
| Run | **20a** — der erste Replay ueber das Drei-Fragen-Korpus (2026-08-30) |
| Corpus | `sim/data/interviews/*.json`, all 60 synthetic interviews |
| Settings of that run | `terms_per_interview = 5`, `merge_neighbours = 12`, name lock D5 active |
| Contents | 60 persons, 131 terms, 231 edges |
| Copied into the repo | 2026-08-30 |

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


## Warum 20a und nicht mehr 19c (2026-08-30)

`graph-19c.json` stammt aus dem alten Korpus mit FUENF Leitfragen. Seit die
Station nur noch drei stellt (`kg/extraction.py`), beschreibt es ein Material,
das so nie wieder entsteht — sichtbar an den Begriffen: 19c traegt
„Klebepunkte-Workshop" und „Betonspritzende Maschinen", 20a traegt
„Pseudo-Abstimmung vor Baubeginn" und „Zwanzigtausend DIN-Normen".

Ausserdem kennt 19c die Felder `in_dream`/`dream_role` nicht, die
`kg.export.build_graph` seit dem 2026-08-30 schreibt. Ein Vertragstest gegen
ein Artefakt ohne diese Felder prueft den Vertrag von gestern.

19c bleibt liegen: Die frueheren Bildreihen unter `out/tagesverlauf*` und
`out/vgl-*` sind daraus entstanden und ohne es nicht mehr nachvollziehbar.
