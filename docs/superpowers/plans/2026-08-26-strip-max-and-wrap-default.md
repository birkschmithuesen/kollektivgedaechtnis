# Streifen-Obergrenze (`strip_max`) und `wrap` als Standard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new operator-controlled display setting `strip_max` (default 10) that caps the Kollektivtraum history strip to the N newest dreams without ever deleting data, and make `wrap` the default history-strip layout instead of `cover`.

**Architecture:** `strip_max` follows the exact pattern already used for `fade_ms` / `strip_ratio` / `typewriter` / `question_seconds`: a `default_*` field in `kg2/config.py` seeds the store on a fresh database (`seed_display_settings`), the operator UI owns it afterwards through `POST /api/display`, and `dream_state()` reads the live value back out of the store on every request. The one addition beyond that pattern: `dream_state()` slices `store.history()` (already oldest→newest) down to the last `strip_max` entries before it goes into the `history` payload — display-only, the store and `dreams.sqlite3` are untouched. `wrap` becomes the default by flipping the `data-strip-mode` attribute in the two frontend HTML files and the `--strip-mode` CLI default in `sim/dream_prerender.py`; the `?strip_mode=` URL override is untouched.

**Tech Stack:** Python (FastAPI, pydantic, sqlite3), vanilla JS/HTML/CSS, pytest, Playwright (via existing `page`/`static_server` fixtures).

## Global Constraints

- Follow the existing `default_*` display-setting pattern exactly — do not invent a new mechanism (brief, section 1).
- `strip_max` bounds: sensible operator range 1–40 (brief, section 1).
- Semantics: `strip_max` limits DISPLAY ONLY. Never deletes rows, never touches `dreams.sqlite3`. Raising it later must make older (still-stored) dreams visible again (brief, section 1's "Wichtig — Semantik").
- No change-detector tests, no tests that read source as text (brief, "Tests").
- `docs/operations.md` must describe only controls that really exist in `frontend2/operator.html` — enforced by `tests/test_dream_runbook.py::test_the_runbook_describes_only_controls_that_exist`.
- Tone for all German prose (config comments, docs, operator labels): nüchtern, keine Werbesprache, in der bestehenden Tonlage des Repos.
- Full suite (`uv run pytest -q`) must be green at the end (currently 648 passed).
- One commit at the end, German commit message in the repo's style.

---

### Task 1: `strip_max` in config

**Files:**
- Modify: `kg2/config.py:76` (near `default_strip_ratio`), and its `_FIELD_NAMES` set (`kg2/config.py:107-129`)
- Modify: `config2.example.toml:60` (near `default_strip_ratio`)

**Interfaces:**
- Produces: `DreamConfig.default_strip_max: int = 10`, and `"default_strip_max"` present in `_FIELD_NAMES` so `load_dream_config` picks it up from a real `config2.toml`.

- [ ] **Step 1: Add the field to `DreamConfig`**

In `kg2/config.py`, right after `default_strip_ratio: float = 0.22`:

```python
    default_strip_ratio: float = 0.22
    # 40 gleichzeitige Träume erwiesen sich als zu viel (Birk, 2026-08-26, an
    # den gerenderten Vergleichen aus sim.dream_prerender): der Streifen zeigt
    # ab hier nur noch die N NEUESTEN, der Rest bleibt in dreams.sqlite3.
    default_strip_max: int = 10
    default_typewriter: bool = False  # spec §6: Birk decides visually on site
```

- [ ] **Step 2: Add it to `_FIELD_NAMES`**

In the `_FIELD_NAMES` set, add `"default_strip_max",` next to `"default_strip_ratio",`.

- [ ] **Step 3: Add it to `config2.example.toml`**

Right after `default_strip_ratio = 0.22`:

```toml
default_strip_ratio = 0.22
# Obergrenze für den Streifen: nur die letzten N Träume werden gezeigt, der
# Rest bleibt in dreams.sqlite3 und wird sichtbar, sobald der Wert wieder
# hochgesetzt wird. 40 gleichzeitig auf dem Schirm waren zu viel (Birk,
# 2026-08-26, an den gerenderten Vergleichen).
default_strip_max = 10
default_typewriter = false       # Birk entscheidet vor Ort
```

- [ ] **Step 4: Sanity check**

Run: `uv run pytest tests/test_dream_config.py -q`
Expected: all pass (existing tests already load the full example config and don't enumerate fields, so nothing should break).

---

### Task 2: `strip_max` as a live display setting in `kg2/server.py`

**Files:**
- Modify: `kg2/server.py` (`DisplaySettings`, `_DEFAULTS`, `dream_state`)
- Test: `tests/test_dream_server.py`

**Interfaces:**
- Consumes: `cfg.default_strip_max` (Task 1), `store.get_setting`/`set_setting`/`set_setting_default` (existing, `kg2/store.py:245-276`), `store.history()` (existing, oldest→newest, `kg2/store.py:227-229`).
- Produces: `dream_state(store, cfg)["strip_max"]: int` and a `dream_state(...)["history"]` list capped to the newest `strip_max` entries, still oldest→newest ordered.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dream_server.py` (near the other display-setting tests, after `test_display_settings_start_from_config_and_are_then_owned_by_the_operator`):

```python
def test_strip_max_defaults_to_ten_when_nothing_is_set(app):
    client, _, cfg, _ = app

    state = client.get("/api/state").json()

    assert cfg.default_strip_max == 10
    assert state["strip_max"] == 10


def test_strip_max_survives_a_restart(app):
    client, store, cfg, _ = app

    client.post("/api/display", json={"strip_max": 5})
    seed_display_settings(store, cfg)  # a restart re-seeds; it must not win

    assert client.get("/api/state").json()["strip_max"] == 5


def test_the_strip_keeps_the_newest_dreams_not_the_oldest(app):
    client, store, cfg, _ = app
    for index in range(1, 6):
        add_dream(store, cfg, at=float(index), sentence=f"traum {index}")
    # d6 is "current" (the newest visible dream); history is d1..d5.
    add_dream(store, cfg, at=6.0, sentence="traum 6")

    client.post("/api/display", json={"strip_max": 3})

    state = client.get("/api/state").json()
    assert [d["sentence"] for d in state["history"]] == ["traum 3", "traum 4", "traum 5"]


def test_raising_strip_max_makes_older_dreams_visible_again_nothing_deleted(app):
    client, store, cfg, _ = app
    for index in range(1, 6):
        add_dream(store, cfg, at=float(index), sentence=f"traum {index}")
    add_dream(store, cfg, at=6.0, sentence="traum 6")

    client.post("/api/display", json={"strip_max": 2})
    assert len(client.get("/api/state").json()["history"]) == 2

    client.post("/api/display", json={"strip_max": 5})

    state = client.get("/api/state").json()
    assert [d["sentence"] for d in state["history"]] == \
        ["traum 1", "traum 2", "traum 3", "traum 4", "traum 5"]
    assert len(store.all_dreams()) == 6  # nothing was ever removed from the record
```

Also extend the existing out-of-range parametrize list in `test_out_of_range_display_values_are_rejected` with two new cases:

```python
        {"strip_max": 0},  # an empty strip is not what this control is for
        {"strip_max": 41},  # above the largest count the wall design was judged at
```

And extend `test_every_display_setting_can_be_changed`'s payload/assertions with `"strip_max": 7` / `assert state["strip_max"] == 7`.

- [ ] **Step 2: Run the new tests to see them fail**

Run: `uv run pytest tests/test_dream_server.py -k strip_max -q`
Expected: FAIL (`strip_max` not a recognised field / KeyError `'strip_max'`).

- [ ] **Step 3: Implement in `kg2/server.py`**

In `DisplaySettings`, right after the `strip_ratio` field:

```python
    strip_ratio: float | None = Field(default=None, ge=0.05, le=0.25)
    # Never 0 (the strip is the evidence and this control only trims it —
    # discarding a single dream already exists for removing one). The upper
    # bound is the largest count the wall design has ever been judged at
    # (sim.dream_prerender's four-point series stops at 40; spec §6, Birk
    # 2026-08-26 on the rendered comparisons).
    strip_max: int | None = Field(default=None, ge=1, le=40)
    typewriter: bool | None = None
```

In `_DEFAULTS`, right after the `strip_ratio` entry:

```python
    "strip_ratio": ("default_strip_ratio", float),
    "strip_max": ("default_strip_max", int),
    "typewriter": ("default_typewriter", bool),
```

In `dream_state`, cap history to the newest `strip_max` entries and expose the value:

```python
def dream_state(store, cfg) -> dict:
    strip_max = int(store.get_setting("strip_max", str(cfg.default_strip_max)))
    return {
        "question": cfg.guiding_question,
        "question_visible": store.get_setting("question_visible", "1") == "1",
        "question_seconds": int(store.get_setting("question_seconds", "0")),
        "fade_ms": int(store.get_setting("fade_ms", str(cfg.default_fade_ms))),
        "strip_ratio": float(store.get_setting("strip_ratio", str(cfg.default_strip_ratio))),
        # Display only: the strip's newest `strip_max` entries. Nothing is
        # deleted from the store — history() already returns everything
        # oldest-first, this only slices what goes out over the wire.
        "strip_max": strip_max,
        "typewriter": store.get_setting("typewriter", "0") == "1",
        "paused": store.get_setting("paused", "0") == "1",
        "current": dream_payload(store.current_dream()),
        "history": [dream_payload(dream) for dream in store.history()[-strip_max:]],
    }
```

- [ ] **Step 4: Run the tests again**

Run: `uv run pytest tests/test_dream_server.py -q`
Expected: PASS, all of them (including the pre-existing ones — `seed_display_settings` iterates `_DEFAULTS` generically so no other touch point is needed).

- [ ] **Step 5: Commit**

Do not commit yet — the brief asks for exactly ONE commit at the very end (after Task 6).

---

### Task 3: Operator UI control

**Files:**
- Modify: `frontend2/operator.html` (control markup)
- Modify: `frontend2/static/operator.js` (render + change handler)

**Interfaces:**
- Consumes: `state.strip_max` (Task 2's `dream_state()` output).
- Produces: an operator control that `POST`s `{strip_max: <int>}` to `/api/display`, exactly like the existing `strip-ratio` control.

- [ ] **Step 1: Add the control markup**

In `frontend2/operator.html`, inside the `Anzeige` `.controls` block, right after the Streifenhöhe label:

```html
  <label>Streifenhöhe <input type="number" id="strip-ratio" min="0.05" max="0.25" step="0.01"></label>
  <label>Streifenlänge <input type="number" id="strip-max" min="1" max="40" step="1"> Träume</label>
  <label><input type="checkbox" id="typewriter"> Schreibmaschine</label>
```

- [ ] **Step 2: Wire it up in `operator.js`**

In `render(state)`, right after the `strip-ratio` line:

```javascript
  document.getElementById('strip-ratio').value = String(state.strip_ratio);
  document.getElementById('strip-max').value = String(state.strip_max);
```

Next to the other `addEventListener` registrations, right after the `strip-ratio` one:

```javascript
document
  .getElementById('strip-ratio')
  .addEventListener('change', (event) => display({ strip_ratio: Number(event.target.value) }));
document
  .getElementById('strip-max')
  .addEventListener('change', (event) => display({ strip_max: Number(event.target.value) }));
```

- [ ] **Step 3: Verify by hand**

Run: `uv run python -m kg2 --no-watch &` (or the project's usual dev-run recipe) and open `/operator` — confirm the "Streifenlänge" field shows `10` on a fresh database and that changing it round-trips (persists across a page reload). Stop the server afterwards.

- [ ] **Step 4: Run the operator test file**

Run: `uv run pytest tests/test_dream_operator.py tests/test_dream_runbook.py -q`
Expected: PASS (no existing test names the new control, so nothing should already be broken; this just confirms the HTML still parses/serves fine).

---

### Task 4: `wrap` becomes the default strip mode

**Files:**
- Modify: `frontend2/dream.html:2` (`data-strip-mode="cover"` → `"wrap"`)
- Modify: `frontend2/static/dream-harness.html:2` (same)
- Modify: `sim/dream_prerender.py:347` (`default="cover"` → `default="wrap"` on `--strip-mode`)
- Modify: `tests/test_dream_prerender.py` (update the one test whose hard-coded expectation this plan's Task 2 already invalidated — see rationale below)

**Interfaces:** none beyond existing ones — this task only flips default values, the `?strip_mode=` override and `data-strip-mode` CSS selectors are untouched.

- [ ] **Step 1: Flip the two HTML defaults**

In `frontend2/dream.html:2`: `<html lang="de" data-strip-mode="cover">` → `<html lang="de" data-strip-mode="wrap">`.
In `frontend2/static/dream-harness.html:2`: same change.

Leave the inline-script comments as they are (they already describe `cover` as "set on `<html>` above", not as a claim about which mode that is — re-read them after the edit to confirm no comment says "cover" specifically as the chosen default; if one does, reword it to say "wrap" / "the current default").

- [ ] **Step 2: Flip the CLI default**

In `sim/dream_prerender.py`, the `--strip-mode` argument:

```python
    parser.add_argument(
        "--strip-mode",
        choices=["aspect", "cover", "wrap"],
        default="wrap",
        help="which history-strip layout dream.css renders. 'wrap' is Birk's "
        "choice from the rendered comparison (docs/operations.md, "
        "2026-08-26) and stays the default; 'cover' and 'aspect' remain "
        "selectable for future comparisons.",
    )
```

- [ ] **Step 3: Run the full page/prerender test files to find breakage**

Run: `uv run pytest tests/test_dream_page.py tests/test_dream_prerender.py -q`
Expected: `tests/test_dream_prerender.py::test_the_page_renders_at_every_size` FAILS on the `count() == size - 1` assertion for `size` 20 and 40 — but **not because of this task's `wrap` change**. It fails because Task 2 made `dream_state()` cap `history` to `cfg.default_strip_max` (10) newest entries, and this test calls `dream_state()` directly and still expects the old uncapped count. Confirm by temporarily reverting just the `wrap` edits and re-running: the failure persists, proving `wrap` is not the cause.

This is a real invariant, just an outdated one: the test's job is "the strip fits on screen and holds every history entry", and displaying every entry unconditionally is now a deliberately removed behaviour (the whole point of this feature is that 40 at once was too many). Rewrite the assertion to the new invariant — bounded by whichever is smaller, the day's dream count or the cap — rather than deleting or weakening the test:

```python
        assert page.locator("#strip li").count() == min(size - 1, cfg.default_strip_max)
```

- [ ] **Step 4: Apply that one-line fix and re-run**

Run: `uv run pytest tests/test_dream_page.py tests/test_dream_prerender.py -q`
Expected: PASS.

---

### Task 5: Documentation

**Files:**
- Modify: `docs/operations.md`
  - "### Die Regler" (Tool-2 section, around line 378-381)
  - "### Offene Entscheidungen", point 4 (around line 544-556)

**Interfaces:** none — prose only, checked by `tests/test_dream_runbook.py` (must still pass: no placeholders, no recommendation language in the strip-mode block, no reference to a control absent from `operator.html`).

- [ ] **Step 1: Update "Die Regler"**

Change:

```markdown
**Anzeige** — Leitfrage zeigen/verbergen und nach N Sekunden ausblenden;
Überblenddauer; Streifenhöhe; Schreibmaschine an/aus.
```

to:

```markdown
**Anzeige** — Leitfrage zeigen/verbergen und nach N Sekunden ausblenden;
Überblenddauer; Streifenhöhe; Streifenlänge (nur die letzten N Träume, Rest
bleibt in `dreams.sqlite3` und wird beim Hochsetzen wieder sichtbar);
Schreibmaschine an/aus.
```

- [ ] **Step 2: Rewrite point 4 of "Offene Entscheidungen" as decided**

Change the heading and closing sentence of point 4 from "gerendert, Wahl offen" / "Keiner der drei Modi ist hier empfohlen..." to record the decision, while keeping the measurement table (it is the evidence, not a stale claim):

```markdown
4. **Modus des Verlaufsstreifens** — **entschieden von Birk am 2026-08-26**,
   an den gerenderten Vergleichen. Sechs Dateien in
   `out/dream-strip-comparison/` (Dateinamen tragen den Modus), dazu zwei
   gestapelte Vergleichskarten `UEBERSICHT-20-traeume.png` und
   `UEBERSICHT-40-traeume.png` — drei Modi übereinander, gleiche Breite.

   | Modus | 20 Träume | 40 Träume | Beobachtung |
   |---|---|---|---|
   | `cover` (bisheriger Standard) | 80×210 px | 31×210 px | Zuschnitt auf einen mittigen Streifen; bei 40 nahezu vollständiger Verlust von links/rechts. |
   | `aspect` | 80×45 px | 31×18 px | Kein Zuschnitt, aber beide Maße schrumpfen bis zur Unleserlichkeit; das reservierte Streifenband bleibt bei 40 größtenteils leer. |
   | `wrap` (**gewählt**) | 372×210 px | 372×210 px (pro Bild) | Kein Zuschnitt einzelner Bilder — der von Birk genannte Grund. |

   **Entscheidung:** `wrap`, Standardwert jetzt in `frontend2/dream.html` und
   `frontend2/static/dream-harness.html` (`data-strip-mode`) sowie in
   `sim.dream_prerender`'s `--strip-mode`. Der `?strip_mode=`-URL-Parameter
   bleibt für Vergleichsrenderings erhalten.

   Zusammen mit dieser Wahl eingeführt: eine Obergrenze `strip_max` im
   Operator-UI ("Streifenlänge", Default 10), die genau das ursprüngliche
   Problem der `wrap`-Zeile adressiert — bei 40 gleichzeitigen Träumen wäre
   ein umbrechender Streifen unten stillschweigend abgeschnitten worden
   (siehe die alte Beobachtung dazu, jetzt durch die Obergrenze entschärft:
   in der Praxis laufen nie mehr als `strip_max` Bilder gleichzeitig auf).
```

- [ ] **Step 3: Run the runbook tests**

Run: `uv run pytest tests/test_dream_runbook.py -q`
Expected: PASS. In particular `test_the_history_strip_modes_are_reported_without_a_recommendation` (still all three mode names present, and the word "empfehl"/"Empfehl" must not appear anywhere in that block — double check the new prose doesn't accidentally contain it) and `test_the_runbook_describes_only_controls_that_exist` / `..._names_no_control_absent...` (the new "Streifenlänge" mention has no hard-coded check, but re-read to be safe: it must correspond to the real `id="strip-max"` control added in Task 3).

---

### Task 6: Full verification and the single commit

**Files:** none new — this task only runs and commits.

- [ ] **Step 1: Run the entire suite**

Run: `cd /home/birk/projekte/kollektivgedaechtnis && uv run pytest -q`
Expected: all tests pass (648 before this change, plus the 4+ new ones from Task 2 minus/plus whatever `-k strip_max` added — the count will be a few higher than 648, all green).

- [ ] **Step 2: Review the full diff**

Run: `git status` and `git diff` — confirm only the files listed across Tasks 1-5 changed, nothing stray.

- [ ] **Step 3: Commit**

```bash
git add config2.example.toml kg2/config.py kg2/server.py \
  frontend2/dream.html frontend2/static/dream-harness.html \
  frontend2/operator.html frontend2/static/operator.js \
  sim/dream_prerender.py docs/operations.md \
  tests/test_dream_server.py tests/test_dream_prerender.py \
  docs/superpowers/plans/2026-08-26-strip-max-and-wrap-default.md
git commit -m "$(cat <<'EOF'
feat(kollektivtraum): Streifen-Obergrenze strip_max, wrap wird Standard

Birk hat an den gerenderten Vergleichen entschieden: der Verlaufsstreifen
läuft künftig im wrap-Modus (kein Zuschnitt einzelner Bilder), und eine neue
Anzeige-Einstellung strip_max (Default 10, im Operator-UI regelbar)
begrenzt ihn auf die letzten N Träume. Nichts wird aus dreams.sqlite3
gelöscht; ein Hochsetzen macht ältere Träume wieder sichtbar.
EOF
)"
git status
```

- [ ] **Step 4: Report**

Summarize for the user: changed files, final test count/result, and the operator control's exact label ("Streifenlänge").
