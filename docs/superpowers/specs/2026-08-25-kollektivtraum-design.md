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

`server_host = "127.0.0.1"` (`config.example.toml:59`, `kg/config.py`) is
localhost-only, so no other machine can reach it at all. It must become
bindable to the LAN interface.

**This is the same change CR-1 needs for screen C.** Build it once, for both
consumers. Scope strictly:

- `server_host` configurable, documented default stays `127.0.0.1`; the
  exhibition value goes into `config.toml` on site.
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
- **`min_mentions` is NOT applied.** That dial is the wall's legibility filter,
  not a statement about what was said. The dream reads everything — the
  weighting already handles prominence.

**Contradiction as construction principle** (brainstorm §4c): the model is
instructed to locate the two most distant positions in the material and hold
them in one image **without resolving them**. This is the instruction that
prevents the consensus brochure; without it every model smooths.

**Threshold:** below `contradiction_min_persons` (default **6**, calibrated in
§10) this instruction is dropped and stage 1 runs on weighting alone. With three
interviews there are no real oppositions and the model would invent one.

**Output:** a short German sentence — the answer to the guiding question, in the
dream's own logic. This is what appears on screen. Length target ~20–40 words:
long enough to carry the fault line, short enough to read at a glance from
standing distance.

**Model:** `claude-opus-5`, same as Tool 1's extraction. One model to reason
about, one credential, and it is the model the merge judge is already tuned on.

### 5.2 Stage 2 — sentence → image

The sentence is translated into an image prompt and rendered.

- **Fixed visual register** (brainstorm §10), set in the morning like the
  guiding question. Held in config as a style suffix appended to every prompt,
  never model-chosen, never graph-driven. The history strip is a measurement
  series: exactly one variable may change, and that is the material.
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
- `contradiction_min_persons` — threshold for §5.1's contradiction instruction.
  Start 6.
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
