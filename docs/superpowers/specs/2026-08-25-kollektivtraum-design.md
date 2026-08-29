# Tool 2 „Kollektivtraum" — design spec (2026-08-25)

Status: **SPEC. Ready for a plan cycle.**

Predecessor: `2026-08-25-kollektivtraum-brainstorm.md` — ten structural
decisions by Birk. That document holds the *reasoning*; this one holds the
*build*. Where this spec is silent, the brainstorm decides; where the brainstorm
is silent, this spec does.

Tool 1 (`2026-08-12-kollektivgedaechtnis-design.md`) is **complete** — tasks 1–21
built, on-site runbook and calibrated values in `docs/operations.md`. Tool 2 sits
on top of its finished `graph.json` and adds nothing to it except one event
(§4.2) and one bind-address change (§3.1).

## 1. What this builds

A screen standing **directly beside the graph wall** that, whenever a new
interview has been absorbed, condenses the entire current graph into one
sentence and one image — and keeps every earlier dream visible as a strip
beneath.

Not an illustration of the future. A **dream**: condensation, displacement, and
contradiction preserved rather than averaged away (brainstorm §1). An LLM that
smooths 40 contradictory interviews into a glossy render *is* the thing the work
criticises.

**Three surfaces exist. This spec builds only B:**

| | Surface | Content | Machine | Built by |
|---|---|---|---|---|
| A | Touchscreen, main station | the graph | exhibition machine | Tool 1 ✔ |
| **B** | Screen **beside A** | **Kollektivtraum** | **own machine** | **this spec** |
| C | Screen, separate room | graph mirror | second machine | CR-1, open |

**A and B stand side by side.** The single load-bearing fact: a visitor reads
the terms on the left and what became of them on the right. Every decision below
that looks aesthetic is really this fact — the translation chain is *checkable*,
so it must not lie.

## 2. Hard constraints

- **Read-only against Tool 1.** Tool 2 never writes to Tool 1's SQLite, never
  POSTs positions, never mutates `graph.json`. Its own state lives in its own
  directory.
- **Runs on its own machine** (brainstorm §9). No shared filesystem is assumed —
  everything arrives over HTTP.
- **Tool 1 must keep working when Tool 2 is dead**, and vice versa. Neither is
  in the other's critical path. If Tool 2 is off, the station degrades to what
  is already sold as the core (the graph); if Tool 1 is off, Tool 2 shows its
  last dream and its history.
- **US cloud is acceptable here** (Birk, 2026-08-25) — consistent with Tool 1's
  `claude-opus-5` extraction.
- **The station is sold.** AG1014 position 8, 1.000 €, screen provided by the
  organiser. This is not a sketch; it has to survive an exhibition day.
- **No secrets in config.** Same rule as Tool 1: API keys from the environment,
  `config.toml` carries no credentials.

## 3. Architecture

```
exhibition machine                          dream machine (own, §9)
┌───────────────────────────┐               ┌──────────────────────────────┐
│ Tool 1                    │               │ Tool 2                       │
│  core → store (SQLite)    │               │                              │
│  server :8800             │◄── HTTP ──────│ watcher   polls /graph.json  │
│    /graph.json  (state)   │               │           + /events (opt.)   │
│    /events      (SSE)     │               │      │                       │
│                           │               │      ▼ new interview absorbed│
│  screen A: /projection    │               │  dream cycle                 │
└───────────────────────────┘               │   1 condense → sentence      │
                                            │   2 sentence → image         │
                                            │   3 persist + broadcast      │
                                            │      │                       │
                                            │      ├─ screen B: /dream     │
                                            │      └─ /operator (own UI)   │
                                            │  store: dreams.sqlite3       │
                                            │         images/*.png         │
                                            └──────────────────────────────┘
```

Tool 2 is a **separate process with its own web server, its own store and its
own operator UI**. It reuses Tool 1's *shape* (FastAPI + SSE + a static page +
a small settings table) because that shape is proven in this codebase and the
on-site runbook already teaches it — but it shares no code path that could let a
Tool 2 fault reach Tool 1.

**Repository layout.** Same repo, new package — `kg2/` beside `kg/`, tests in
`tests/` with a `test_dream_*` prefix. Rationale: the two tools share the
`graph.json` contract and must be versioned together; a separate repo would let
them drift apart silently. Tool 2 may import *pure* helpers from `kg` (dataclass
shapes, the SSE encoder) but never `kg.store`, `kg.core` or `kg.server`.

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

Nothing else in Tool 1 changes. Not the renderer, not the pipeline, not the
schema.

## 4. The trigger — event-driven with a floor

Decision: a **completed interview** starts a dream; never a timer; nothing during
silence (brainstorm §6). Because A and B stand side by side, causality is
*visible* — an image appearing while nothing happened on the left exposes the
station as a random generator.

### 4.1 What „completed" means — and the trap in it

Tool 1's own timing (`kg/core.py:159-199`, verified 2026-08-25):

1. `_close()` — the person is closed, `broadcast_state` fires. **The terms do
   not exist yet.**
2. `_process()` runs the pipeline in a thread: settle, transcribe, extract,
   embed, merge.
3. **Only then** `broadcast_graph()` fires — now the new terms are in
   `graph.json`.

**A dream must be triggered by step 3, never step 1.** A dream started at the
stop would condense a graph the interviewee contributed nothing to yet, and the
visitor standing there would watch their own interview *not* arrive. The
pipeline takes seconds to tens of seconds, so this is a real race, not a
theoretical one.

Tool 2 has no access to that call. It detects step 3 from the data:

- Poll `GET /graph.json` every **5 s** (cheap: complete state, no delta
  mechanism, spec §11).
- The payload carries `generated_at` and every node's `created_at`.
- **A dream is due when the set of `type:"person"` node ids has grown *and* that
  new person has at least one edge** — i.e. the pipeline has run. A person node
  with no edges is step 1 and is explicitly ignored until its edges appear.
- **Floor:** at least `min_interval_s` since the last dream *started*. Default
  **240 s**, calibrated later (§10).
- If several interviews land inside the floor, they collapse into **one** dream
  when it opens — the dream is of the whole graph, not of one person, so there
  is nothing to queue.

**Polling, not SSE.** Tool 1 offers `/events`, and subscribing would be more
immediate — but polling a complete-state endpoint is the pattern CR-1 already
chose for the same reason, it survives a Tool 1 restart with no reconnect logic,
and at a 240 s floor a 5 s detection lag is invisible. SSE stays available as a
later optimisation; nothing in the design depends on it.

### 4.2 Optional: a nicer trigger, later

If the 5 s poll ever proves unsatisfying, Tool 1 could publish an
`interview_absorbed` event on its existing bus at `kg/core.py:198`. That is a
three-line change and a genuine improvement, but it is **not** in this build:
the poll works, and touching Tool 1's core after it is finished needs a better
reason than elegance.

## 5. The dream cycle — two stages

The artistic core (brainstorm §4). Two LLM calls, not one, because the sentence
is itself a displayed artefact and must be readable on its own.

### 5.1 Stage 1 — graph → sentence

**Input:** the whole graph, weighted.

- **Weight by structure** (brainstorm §4b). `graph.json` already carries
  `mentions` per term and all edges — no new computation on Tool 1's side.
  Frequently mentioned terms enter the prompt as dominant; single mentions enter
  as marginal detail, explicitly labelled as such so the model can place them as
  a detail rather than a theme.
- **Quotes are included.** They exist in `graph.json` (`quotes[]` with
  `person_id`) precisely for this — Tool 1's spec §11 stores them for Tool 2's
  benefit even though the wall never shows them.
- **Hidden nodes are excluded.** `hidden: true` is the operator's emergency exit
  on the wall (Tool 1 spec §8); something pulled from the wall must not
  reappear in the dream.
- **Term selection, revised 2026-08-28/29.** The original rule was
  „`min_mentions` is NOT applied — the dream reads everything, the weighting
  already handles prominence." That is superseded. The dream now takes **all
  shared terms (≥2 mentions), topped up with the newest single mentions on a
  gliding budget** that shrinks to zero as the shared terms grow
  (`SINGLE_MENTION_BUDGET`/`SHARED_TERMS_SATURATION`, `kg2/weighting.py`), plus
  a separate „Zuletzt gesagt" block carrying the `RECENT_TERMS` newest terms
  regardless of count. Reason: Birk wants the picture built from what more than
  one person said, without losing the interview that just finished.

  **Tool 1's wall dial remains uncoupled from this.** Since 2026-08-29 that
  dial is `max_terms` (how many labels fit on the wall) rather than
  `min_mentions`, and both tools now follow the *same selection rule* with
  their own limits — but the wall's limit must never steer the dream's content.
  An operator raising the cap because the type got small would otherwise
  silently change what the images are made of, and two exhibition days would
  stop being comparable. See
  `docs/superpowers/specs/2026-08-29-wand-anzeigeregler-begriffsobergrenze.md` §5.

- **Quotes are no longer part of the material (2026-08-28).** They were the
  bulk of it — 117 quotes, 76 % of the block at 60 persons. On the wall only
  the *terms* are visible; a quote appears only when a visitor taps a portrait.
  Building three quarters of the image prompt from something invisible in the
  room breaks the link between the two screens — the same argument §10 uses to
  reject graph-driven style. `Material.quotes` still exists and
  `render_material(include_quotes=True)` still renders them, for the
  side-by-side comparison run only.

**Contradiction as construction principle (retired 2026-08-28).** The
original design instructed the model to locate the two most distant positions
in the material and hold them in one image without resolving them, below a
`contradiction_min_persons` threshold this instruction was dropped. Removed
without replacement-by-threshold: it forced an „aber/oder" into the sentence
and invited hallucination, and the sentences are absurd enough without it.
Replaced by a plain evidence clause instead (`kg2/condense.py`): everything in
the sentence must trace back to a delivered term, nothing invented that is
not in the material. `contradiction_min_persons` no longer exists as a value
to calibrate (see §10, now superseded).

**Output:** a short German sentence — condensed from the material in the
dream's own logic (no longer an "answer to the guiding question": see below).
This is what appears on screen. **Form target, revised 2026-08-28:** one main
clause, at most 16 words, no comma. Measured against the real frontend
(1920x1080, `#sentence` at 3.1vh = 33.5px, `docs/operations.md`): the
original target of „~20–40 words: long enough to carry the fault line, short
enough to read at a glance from standing distance" is contradicted by the
material itself — 36 words made 4 lines and ~11s to read, 50 words made 5.
At ≤16 words a sentence is 1-2 lines, which is what „read at a glance while
walking past" actually requires.

**The guiding question no longer enters stage 1's prompt at all** (neither
system nor user message, `kg2/condense.py`, 2026-08-28). It was a sixth
question nobody in the room was actually asked, and imposing it forced a
reading direction the material may not contain — the same failure mode the
contradiction clause had. `DreamConfig.guiding_question` still exists but
steers only the on-screen headline (`kg2/server.py`) from here on.

**Model:** `claude-opus-5`, same as Tool 1's extraction. One model to reason
about, one credential, and it is the model the merge judge is already tuned on.

### 5.2 Stage 2 — sentence → image

The English sentence (`sentence_en`, a literal translation of the German one
produced in the SAME stage-1 call) becomes an image prompt and is rendered.
**Revised 2026-08-28: the whole image prompt is English prose, five blocks in
order** (`kg2/imagegen.py::build_image_prompt`): the English sentence (motif),
mood (from `mood`, five FIXED light/colour formulations), tension (from
`tension`, five FIXED coherence formulations — see brainstorm §10's revision),
the register, and the format. English and connected prose rather than a
keyword list per Google's own guidance for this model.

- **Fixed visual register (machart only)** (brainstorm §10), set in the
  morning like the guiding question. Held in config as a style suffix
  appended to every prompt, never model-chosen, never graph-driven — mood and
  tension are graph-driven now, but the machart itself (photography vs.
  painting vs. rendering) is not and never travels mid-day. The history strip
  is a measurement series: the register holds the machart constant so that
  mood/tension and the sentence remain the variables the strip actually shows.
- **Model:** `google/gemini-3-pro-image` via OpenRouter — the model the approved
  rendering `kollektivtraum-screen_v2_2026-08-16.png` was made with, so the
  register is already known to be reachable. OpenRouter is already a dependency
  (embeddings) with a key in the environment.
- **Aspect ratio landscape**, matching the 65″ screen.
- The image is written to `images/<dream_id>.png` and never overwritten.

**The sentence shown on screen is stage 1's output, not stage 2's prompt.** The
image prompt is a technical artefact with style boilerplate; showing it would
put lighting instructions on the wall. Stage 1's sentence is the honest one —
it is what the collective dreamed. Stage 2's prompt is stored for
reproducibility and shown only in the operator UI.

### 5.3 Reproducibility

Per dream, persisted: id, timestamp, the graph's `generated_at` it was built
from, person/term/edge counts, stage 1 prompt + sentence, stage 2 prompt, model
names, image path, discarded flag. This is the house rule (SOUL: file +
parameters + machine-readable record) and it is what makes a post-festival
retrospective possible at all.

## 6. Screen B — the display

One page, `/dream`. Layout:

- **The guiding question** — top, permanent by default. Toggleable and
  duration-configurable from the operator UI (Birk's explicit request, §7).
- **The current image** — large, dominant.
- **The sentence** — a fixed line beneath the image. This is the **baseline**
  (brainstorm §3a) and also the fallback.
- **The history strip** — beneath that: every earlier dream of the day, smaller
  and dimmer, oldest to newest. Asymmetric by design: the current dream is the
  subject, the strip is the evidence.

**Transitions are cross-fades.** Explicitly not morphs (Birk). Default 1.2 s.

**The typewriter variant** (brainstorm §3c) is built as an **animation layer over
the baseline, not a second layout**: while stage 2 runs, the sentence builds up
word by word in a larger centred position; when the image arrives, it settles
into the same fixed line the baseline uses. Enabled by a flag; **Birk decides
visually on site**. Because it is one layout with an optional animation, turning
it off is a switch, not a rebuild — and the „generation takes 60 s" risk is
carried by the baseline either way.

**Sizing follows Tool 1's rule** (spec §11): everything in model units, scaled to
the viewport. The strip's thumbnail size is a fraction of screen height, so a
different screen changes nothing.

**No dashboard.** Same discipline as the wall (Tool 1 spec §10): no counters, no
progress bars, no „generating…" spinner competing with the image. The only
motion is the fade and, optionally, the typewriter.

## 7. Operator UI — `/operator` on the dream machine

Tool 2 gets its **own** interface (Birk). Tool 1's operator UI keeps its
deliberate sparseness („the one live control", spec §7) and is **not** extended.

**Display settings:**
- guiding question: on / off / auto-hide after N seconds
- fade duration
- image ↔ history-strip size ratio
- typewriter variant on / off (§6)

**Flow control:**
- **Dream now** — ignores the floor, starts a cycle. Needed the moment someone
  from the organiser stands in front of the screen and wants to see how it works.
- **Discard current dream** — the emergency exit if the model produces something
  unusable or embarrassing. Same logic as Tool 1 spec §8: *no gate, an emergency
  exit* — no approval workflow, but a rip-cord.
- **Pause / resume** the cycle.

**Discard removes the dream from the large screen AND from the history strip in
one step** (Birk). An image pulled for embarrassment must not live on below. The
row is kept with `discarded: true` (never deleted — the record stays honest);
the display filters it out. When the current dream is discarded, the previous
one returns to the large position.

**Explicitly NOT in the interface:** changing the guiding question, the visual
register, or the weighting at runtime. Changing the question mid-day destroys
exactly the comparability the strip exists for (brainstorm §7). Both are set in
the morning, in `config.toml`.

## 8. Failure modes

The station hangs on two cloud calls per cycle. Conference wifi on a trade-fair
day is exactly where that stops working at 14:00.

**Ride it out** (brainstorm §5). The rules:

| Failure | Behaviour |
|---|---|
| Stage 1 or 2 fails / times out | Dream is abandoned, marked `failed`, **the current image stays up**. Retry at the next trigger — never a retry storm. |
| No connectivity at all | Same. Screen shows the last dream and a full history strip. Looks calm, not broken. |
| Tool 1 unreachable | Poll keeps failing quietly; no new dreams (correct — nothing new was said). Display unaffected. |
| Tool 2 process dies | Screen B goes blank; **A and C are untouched**. Restart restores everything from `dreams.sqlite3` incl. the strip. |
| Image model returns something unusable | Operator discards (§7). |
| Disk fills with images | ~40 images/day at a few hundred KB — a non-issue for one day; documented, not engineered around. |

**No local image model.** Explicitly rejected as a fallback (brainstorm §5): two
visual languages to maintain and a GPU requirement in the show laptop. If a local
model is ever wanted it is a matter of principle, not a failover, and then it is
its own decision.

**LTE stick** as the physical fallback path — the cheapest insurance and it
belongs in the runbook, not in the code.

**Crash recovery is the same standard Tool 1 holds** (Tool 1 §14, run 21): after
a restart the screen must come back exactly as it stood — current dream, full
strip, settings. Everything needed for that is in SQLite; nothing lives only in
memory.

## 9. Machine and network

**A dedicated small machine** drives screen B (brainstorm §9). Considered and
rejected: sharing the exhibition machine (which already spends 2.6–9.9 s of CPU
on layout, Tool 1 spec §14.5) and hanging B off the second-room machine (cable
run).

Clean cut: **the exhibition machine does memory, the dream machine does dream,
they share one file.**

**Unverified, flagged, must be measured on the actual machine — not estimated:**

1. Whether the venue's uplink carries two cloud calls per cycle all day. CR-1
   already records this for screen C; both now depend on it.
2. Whether the dream machine's hardware drives a 65″ display plus the fetch and
   generation loop. Same caution Tool 1 spec §14.5 demands.
3. Screen B's size/connector/resolution — organiser-provided, still open
   (Tool 1 spec §14.2, deck lists 65″ + floor stand).

The cheap de-risking test, worth running early and identical to CR-1's:
**a plain HTTP GET of `/graph.json` from the dream machine.** That answers the
networking half before any implementation, and it is exactly what the watcher
does in production.

## 10. Values to calibrate — not guessed here

Produced by the simulation, the way Tool 1's density values were (its spec §14.4
and the run-19c section of `docs/operations.md`), then recorded in
`docs/operations.md`:

- `min_interval_s` — floor between dreams. Start 240 s.
- `SINGLE_MENTION_BUDGET` / `SHARED_TERMS_SATURATION` (`kg2/weighting.py`) —
  superseded §5.1's contradiction threshold (2026-08-28, the clause itself is
  retired). The two parameters of the gliding single-mention selection
  (`sim.dream_calibrate terms`). Provisional start values 20 / 25.
- **Stage 1's `mood`/`tension` scale** — whether the 1-5 range is actually
  used on built extremes and whether real material varies it at all
  (`sim.dream_calibrate mood`, added 2026-08-28).
- **The guiding question's wording** — wide enough to carry all three interview
  themes (future of building / AI in building / living together): closer to
  „Wie leben und bauen wir in zehn Jahren?" than a narrow material question.
- **The visual register** — decided **at images, not in words** (brainstorm §10):
  three or four samples on identical fictional content, Birk picks.

`sim/replay.py` already produces realistic graph states from the synthetic
corpus, so all four can be exercised without a single live interview.

## 11. Testing & verification

- **Unit:** trigger logic (person-with-edges vs. bare person node — the §4.1
  race, which is the defect most likely to ship), floor and collapsing,
  weighting, hidden-node exclusion, discard semantics incl. removal from the
  strip, restart reconstruction.
- **Contract:** against a **real** `graph.json` from `sim/replay.py`, not a
  hand-written fixture. A fixture would encode today's assumption about the
  format and pass forever while the real file drifts.
- **Integration:** replay drives graph states; the cycle runs with stubbed model
  calls; assert one dream per absorbed interview, floor respected, none during
  silence.
- **Visual:** a pre-render series like Tool 1's — the page at 1, 5, 20, 40 dreams
  so the strip is judged full, not empty. Judged by Birk.
- **Failure modes:** every row of §8 gets a test. The two that matter most are
  „cloud dead → last image stays up" and „restart → strip intact".
- **Cross-machine:** the §9 GET, run from the dream machine. Never from
  localhost.

## 12. Explicitly out of scope

- **Reacting to the wall's camera or density dial.** B is not a second view of
  A; it has its own logic.
- **Interaction on B.** No touch, no controls on the screen itself. It is a
  display; everything is set from the operator UI.
- **Dreams that reference specific people by name.** The dream is collective;
  quotes feed it, attribution does not. This is also the quieter answer to
  „where do my statements end up".
- **Carrying dreams across days.** Each festival day starts empty — the strip
  tells the story of *one* day. Multi-day is a later question.
- **Curated or approved dreams.** Discard is the only intervention (§7).
- **Local image generation** (§8).
- **An `interview_absorbed` event in Tool 1** (§4.2) — possible, deliberately not
  now.

## 13. What Tool 1 must not lose

For Tool 2 to keep working, these properties of the finished Tool 1 are now
load-bearing and must not be refactored away:

1. `graph.json` stays **complete state**, no delta mechanism.
2. `quotes[]` stays in the payload, even though the wall never renders it.
3. `mentions` per term stays — it is the weighting input.
4. `hidden` stays in the payload — it is the exclusion input.
5. `broadcast_graph()` keeps firing **after** the pipeline, not at the stop
   (`kg/core.py:198`). This is the §4.1 contract; moving it would silently make
   every dream one interview stale.

These belong in Tool 1's spec as a note, so a later refactor sees them.
