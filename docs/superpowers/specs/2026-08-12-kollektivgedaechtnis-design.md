# Design Spec: Kollektivgedächtnis (Tool 1 — Live-Interview-Graph)

- **Status:** APPROVED by Birk 2026-08-12 — ready for phase 2 (writing-plans)
- **Phase:** 1 of 3 (brainstorm → plan → execute). Next: `superpowers:writing-plans` in a fresh Claude Code session.
- **Project:** Station „Kollektivgedächtnis", Festival NEW bauhaus, Sept 2026 (on-site build/test from 01.09.)
- **Repo:** `birkschmithuesen/kollektivgedaechtnis` (private)
- **Source documents (context, not duplicated here):**
  - `entities/artesmobiles/projekte/NewBauhaus/stationen/interview-graph-photobooth/konzept-live-interview-graph.md`
  - `.../brainstorming-briefing-tech-stack.md`
  - `.../pitch-live-graph-photobooth.md` (the 5 interview questions)

This spec is the ONLY interface to phase 2. Everything decided in the
brainstorming dialogue that matters is written down here. Phase 2 starts cold.

---

## 1. What this builds

A live installation backend + renderer. Visitors at a conference are
interviewed in a photo booth. Speech is transcribed continuously, an LLM
extracts concrete terms from each interview, and a relationship graph grows on
a whiteboard projection over the course of the festival.

**Scope of THIS spec: Tool 1 only** — capture, extraction, graph state,
rendering, operator UI.

**Explicitly a separate spec (Tool 2, „Kollektivtraum"):** the periodic
image-generation companion that condenses the whole graph into an image prompt
every ~5 minutes and displays prompt + generated image on a second screen
(organiser-provided). It is a **read-only consumer of `graph.json`** and shares
nothing else with Tool 1. It gets its own brainstorm → spec → plan cycle, after
Tool 1 is built. See §11 for what Tool 1 must provide so Tool 2 needs no
retrofit.

## 2. Hard constraints

| Constraint | Value | Source |
|---|---|---|
| Output format | 1920×1080, 16:9 landscape | Birk 2026-08-12 |
| Projection surface | whiteboard (additive projection, black is not black) | organiser call 2026-08-11 |
| Expected scale | **~50 person nodes max** over the whole festival (day 2 is half-length) | Birk 2026-08-12 |
| Aesthetics | no legend, no filters, no cluster hubs, no statistics bar — bare organic net | Konzept |
| GDPR | **not a selection criterion** for this installation; cloud services permitted | Birk 2026-08-12 |
| Machine | laptop on site, no GPU assumed | Birk 2026-08-12 |
| Credentials | the exhibition machine gets ONLY the keys it needs (LLM, embeddings, ElevenLabs, bot token) — never `~/.hermes/.env` | Briefing §5a |
| No agent in the live loop | deterministic pipeline, plain Python process, no Hermes runtime, no token spend | Briefing §5a + AGENTS.md house rule |

### Decided earlier, do NOT reopen
- Obsidian as a **display surface** is out (Briefing §4: no reliable external-change
  refresh, no growth animation, no multitouch, no kiosk mode).
- No dedicated Hermes profile for this project (Briefing §5a).
- Microphone/audio chain for the *booth* is a hardware matter settled in the Konzept.

## 3. Architecture

Four processes on the on-site laptop:

1. **STT server** — EXTERNAL, pre-existing, supplied by Birk (see §4).
2. **Telegram poller** — receives photos and stop commands. A slim bot poller
   (e.g. `python-telegram-bot`), NOT the Hermes gateway.
3. **Core** — the only writer. Segments transcripts, extracts, merges,
   persists, exports `graph.json`.
4. **Browser** — two windows: the projection (fullscreen on the beamer) and the
   operator UI (on the laptop display). Never the same window.

```
                 mic (VA hand-held radio mic, rented)
                          │  continuous audio
                          ▼
                  ┌───────────────┐
                  │  STT server   │  ElevenLabs realtime backend,
                  │  (external)   │  runs continuously
                  └───────┬───────┘
                          │ SSE /events  (TranscriptionEvent)
                          ▼
 Telegram ──photo/stop──► ┌───────────────┐ ──► SQLite (truth)
                          │     Core      │ ──► graph.json (full state)
                          └───────┬───────┘
                                  │ SSE
                    ┌─────────────┴─────────────┐
                    ▼                           ▼
            projection (1920×1080)        operator UI
            Cytoscape.js, kiosk           transcript / slider / hide
```

### 3.1 Why from scratch (Backend option D)

Options A (Hindsight), B (LLM-wiki pattern) and C (combination) were researched
and **lose deliberately**:

- **Hindsight** would have contributed entity resolution. But its consolidation
  is LLM-driven and asynchronous inside a foreign system, i.e. not controllable
  from our side — and we need the merge behaviour to be OUR dial (§6). It also
  means a Postgres deployment in the critical path of a live installation, for
  ~50 nodes.
- **LLM-wiki pattern** would have contributed the curation gate and lint net.
  The gate was deliberately dropped (§8); what remains is a file layout for a
  five-entity data model.
- Our data model is tiny and fully known: person, term, edge, quote, photo.
  That is a SQLite table plus a JSON export, not a knowledge architecture.
- The renderer was always going to be custom. With D the whole station is our
  code, with no third-party system in the live path and no version risk one
  week before the festival.

**Accepted cost:** we build entity merging ourselves (§6).

## 4. STT server — external dependency

**Status: SET, supplied, not part of this build.**

Birk has an existing STT server (from the „Versuch über" / Fundus project) that
already includes an **ElevenLabs realtime backend**. It runs **continuously**
for the entire exhibition day — cost is negligible at ElevenLabs realtime
pricing (Birk 2026-08-12), and a continuous transcript is wanted for monitoring.

### ✅ VERIFIED against the current source (2026-08-12)
Source of truth: **`meredityman/fundusbot`** (private; accessible with Birk's
`birkschmithuesen` gh login), branch **`win_fundusfantasma-dev-clean`**, path
`fundusapps/stt_server/`. The backend is
`backends/elevenlabs_scribe_backend.py`, backend name `"elevenlabs-scribe"`.

Run as: `python -m fundusapps.stt_server elevenlabs-scribe`
CLI options (from `args.py`): `--model` (default `scribe_v2_realtime`),
`--language` (default `de`), `--commit-strategy` (`vad` | `manual`, default
`vad`), `--silence-timeout` (default 0.7), `--api-key-env` (default
`ELEVENLABS_API_KEY`).

**🔴 The event contract CHANGED versus the older Nextcloud copy** — it now has a
TENTH field, `extending`. A consumer written against nine fields is wrong.

### The contract we depend on
From `stt_server/events.py` (verified in the current branch):

```python
TranscriptionEvent(
    recognizer_id: str,
    type: "partial" | "final",
    text: str,
    timestamp: float,     # wall clock, epoch seconds
    backend: "vosk" | "whisper" | "whisper-streaming" | "elevenlabs-scribe",
    status: str | None,
    confidence: float | None,
    turn_id: str | None,      # stable per utterance
    partial_seq: int | None,
    extending: bool | None,   # NEW — see below
)
```
Delivered as SSE over `GET /events` (JSON per event, `: keep-alive` comments
between). Other endpoints: `/status`, `/pause`, `/resume`, `/operator`.

**`extending` exists because Scribe REVISES partials mid-utterance** (unlike the
LocalAgreement-2 whisper path, whose partials are strictly growing prefixes):
`True` = this partial extends the previous one, `False` = it is a revision,
`None` = backend doesn't distinguish (legacy whisper/vosk).

**We consume `type == "final"` only** — so `extending` never affects our logic;
the consumer must merely tolerate the field. Partials go to the operator
display, where revision is fine.

**Utterance boundaries are the provider's, not ours.** With the default
`--commit-strategy vad`, a `final` is emitted exactly when ElevenLabs' server
VAD sends `committed_transcript`. We do not implement silence detection.

### Integration rule
**Do NOT fork or modify the STT server.** The Core is an independent SSE
consumer. It appends every `final` event to a local JSONL transcript log
(text + wall-clock timestamp + turn_id) and does its own segmentation. This
keeps the STT server a pure supplier and survives internal changes on its side.

## 5. Capture (Weg 2 — radio mic + photo trigger)

**Decision: Weg 2.** Rationale (Birk 2026-08-12): a rented professional
hand-held radio mic is a different reliability class than a consumer USB mic on
a phone, and Telegram voice messages require holding the record button for the
entire interview — untenable for a multi-minute interview.

Audio runs permanently into the STT server; **Telegram carries only the photo
and the control commands.**

### Interview lifecycle
1. **Start** — a photo arrives via Telegram. Its arrival time is the start
   marker. The person node with the portrait appears in the graph
   **immediately**.
2. **Running** — the continuous transcript accumulates. Nothing else happens
   visually.
3. **Stop** — whichever comes first:
   - any **text message** in the Telegram channel (no keyword to memorise), OR
   - a **spoken stop command** picked up in the transcript, OR
   - a **safety timeout** (default 15 min) so a forgotten stop cannot swallow
     the next interview.
4. **Processing** — the Core cuts the transcript between the markers and runs
   extraction (§6).

**Settle delay — only on the text-message path** (revised 2026-08-14, Birk).
The only real problem here is STT *delivery* latency, not doubt about where the
interview ended:
- **spoken stop** → process immediately. The command arrived *as* a transcript
  final, so by construction every earlier utterance has already been delivered
  (finals are ordered). Waiting gains nothing.
- **timeout** → process immediately. 15 minutes have passed; nothing is in
  flight.
- **text message** → wait **up to 3 s**, but proceed as soon as a final arrives
  whose timestamp is after the stop marker (typically ~1 s). This is the one
  path where a human keypress races an in-flight utterance: the last spoken
  sentence may still be inside ElevenLabs' server VAD when the marker is set.
  The cut end moves to that final's timestamp. Not a fixed sleep.

### Spoken stop command
Cheap because the transcript is already flowing: a string match on text we
already receive. No wake-word engine, no extra model, no extra latency or cost.

- Configurable **list** of phrases (so they can be adjusted on site if STT
  reliably mangles one). Defaults in the spirit of „Interview beendet" /
  „Aufnahme beenden" — phrases nobody says in passing. Never „danke"/„fertig".
- Matching is tolerant: case-insensitive, punctuation-insensitive, several
  accepted variants (STT delivers „beended" as well as „beendet").
- **The matched command text is stripped before extraction**, otherwise the LLM
  may derive a term from it.
- Failure to recognise is the harmless direction — the timeout and the LLM
  end-detection (§6.1) catch it.

### Serial interviews only
One microphone ⇒ exactly one interview can be running at a time. Parallel
interviews are out of scope. If a new photo arrives while an interview is still
open, that photo **implicitly closes the running interview** (its arrival time
becomes the previous interview's stop marker) and opens the new one. This is the
same forgiving behaviour as the timeout: it can never leave two interviews open.

### Pre-roll
The raw audio is written to disk continuously regardless of STT. If a photo
arrives late, the ~60 s preceding the photo are available and MAY be
transcribed after the fact. Nice-to-have; not required for v1.

## 6. Condensation — the artistic core

**Timing: mixed mode.** Person node + portrait appear **immediately** on the
photo trigger; term nodes grow **after the stop**, from a single extraction over
the complete transcript.

Rejected: pure streaming (terms from half a sentence are systematically worse,
and a term node that has to disappear again is *visible* on a projection and
reads as a bug, not as dramaturgy). Rejected: pure batch (nothing happens on
the wall while an interview is visibly running). Growing terms *during* the
interview is **explicitly out of scope, kept for a later iteration** (Birk).

### 6.1 Pipeline per interview

1. **Cut** — all `final` events between the start and stop markers. On the
   text-message stop path only, the end extends to the final that landed inside
   the ≤3 s settle window (§5). There is **no configurable tail** beyond that:
   a tail past a timeout only moves an already-arbitrary cut later — if 15
   minutes is too short, raise `interview_timeout_s` instead
   (revised 2026-08-14, Birk).
2. **Find the end** — the LLM is explicitly tasked with locating the actual end
   of the interview inside the text (Birk's requirement). This is what makes a
   forgotten stop harmless.
3. **Extract** — terms + quotes, one LLM call, fixed JSON schema.
4. **Merge** — see §6.2.
5. **Persist** — SQLite, then re-export `graph.json`.

### 6.2 Merging: embedding filter + LLM judge

Merging is an all-pairs problem (~150 term nodes ⇒ >10,000 pairs) — too many to
ask an LLM pair by pair. Split by capability:

- **Embedding = preselection.** For each new term, find nearest neighbours among
  existing terms. Milliseconds, negligible cost.
  **Provider: OpenRouter's embeddings endpoint** (`/api/v1/embeddings`,
  OpenAI-compatible, live since Nov 2025; models filterable by
  `output_modalities=embeddings`). Decision by Birk 2026-08-12 — a cloud
  embedding model is explicitly fine, no local `sentence-transformers`
  requirement. Separate key from the extraction LLM is acceptable.
  **Embeddings MUST be cached by term text** (one embedding per distinct term,
  ever). Otherwise every simulation re-run costs money and needs the network,
  which would make the §9 regression runs slow and online-only. With the cache,
  the second run is free and offline.
- **LLM = judgement + naming.** The candidate group goes out as **one single LLM
  call per interview** (~50 calls over the whole festival): which of these mean
  the same thing, and what is the resulting node called?

An embedding **cannot** choose the name — and the name is exactly the content
work that decides the quality of the picture („Betonspritzen mit Drohnen" /
„3D-Druck vor Ort" / „Roboter auf der Baustelle" → what goes on the wall?).
Seeing the whole candidate group at once also resolves the transitivity problem
that pure thresholds have (A~B, B~C, A≁C).

**Merge decisions are persisted, never re-derived.** Once it is decided that
these three terms are one node named X, that is stored and not touched again.
Consequences: the graph never wobbles in live operation regardless of model
variance, and in simulation two runs are comparable by freezing the decisions.

**Merge aggressiveness is controlled by the prompt**, not a similarity
threshold („only merge what really means the same" ↔ "merge generously by
theme"), and is calibrated in simulation (§9) — not a live control.

### 6.3 Extraction quality
The prompt optimises for **concreteness, not frequency**. Good: „Betonspritzen
mit Drohnen" (concrete, vivid, surprising). Bad: „Nachhaltigkeit" (says
nothing, connects everything to everything). The good/bad examples from the
briefing go into the prompt verbatim, plus a hard cap of terms per interview.

The **number of terms per interview is fixed** (calibrated in simulation), NOT
runtime-adjustable — a runtime extraction change makes graph density depend on
the time of day, which is visible in the final picture.

### 6.4 Edges
**Person↔term only.** Term↔term co-occurrence edges are deliberately NOT built:
they create the "connects everything to everything" soup the briefing warns
about and add density without insight — the connection between two terms is
already visible when the same person touches both. Recorded here as a rejected
option so it is not re-proposed.

## 7. The one live control

**Exactly one runtime dial: minimum mention count. A pure display filter.**

„Show a term only once at least N people have mentioned it."
N=1 → everything visible, maximum density. N=2/3 → only what is shared; the net
becomes calmer and more legible.

Why this one: it is the only dial that makes a **statement** rather than merely
tidying up — *what many say becomes visible* is the core thesis of a station
called Kollektivgedächtnis. And it is safe: it discards nothing, applies
instantly to the entire existing stock, is fully reversible, and can be turned
in front of an audience.

Display filter (instant, reversible, safe) vs. extraction setting (only affects
future interviews, has a tail) — this distinction is load-bearing. **Only
display filters are exposed at runtime.**

## 8. Curation: no gate, an emergency exit

**No approval gate in the normal flow.** Terms and quotes appear automatically.

Rationale: a real gate needs a human on it continuously; the moment that person
is interviewing, getting coffee, or talking to the organiser, the graph stops
growing. A stalled graph is the worse failure — the station visibly lives on
growing. Under pressure a gate gets waved through anyway: cost without benefit.

**Instead: a hide button.** The operator UI lists incoming entries with exactly
one action per entry — **hide**. No editing, no approving, no queue. Because the
density dial is a display filter anyway, hiding is the same mechanism, just
another flag.

**Accepted residual risk, stated honestly:** between appearing and being hidden,
an unfortunate term may be visible for a few minutes.

## 9. Test scenario / user simulation (§3b)

Prerequisite for judging anything. **STT is out of scope** — the test starts
from finished interview **text**.

- **~60 synthetic interviews**, generated from the **5 real guiding questions**
  in `pitch-live-graph-photobooth.md` (otherwise the wrong text genre is tested).
- **Realistic spoken language**: filler words, broken sentences, repetitions,
  digressions. An STT transcript is not clean prose and extraction must cope.
- **Range of speaker types**: terse (2 sentences) to rambling (5 minutes),
  jargon to everyday language, clear position to undecided.
- **Controlled overlap**: ~1/3 of interviews deliberately contain formulations
  that mean the same as another interview. These **expected merges are
  documented in a separate expectations file** — otherwise "good result" is
  unfalsifiable.
- **Time-lapse mode**: feeds interviews in original order and relative spacing,
  accelerated. Shows growth behaviour, not just the end state. Can pause at any
  point and shoot a PNG.
- **Reproducible**: same data set + same seed + frozen merge decisions = same
  result, so two renderings are comparable.
- **Usable as a regression net**: after changing the extraction prompt it must
  be visible whether the result got better or worse.

The simulation is also the instrument for calibrating: the density dial at
three settings, the fixed term count per interview, and the beamer/legibility
test (§10.3) with real label lengths instead of fixtures.

## 10. Frontend

### 10.1 Renderer
**Cytoscape.js.** Nodes are image circles with a ring plus short labels;
Cytoscape ships graph layouts and CSS-like selectors. D3 would be more manual
work with no gain here.

### 10.2 Node design
- **Person node: portrait photo + golden ring. No name, no quote.** The Konzept
  never places a name at the node, and the quote was explicitly dropped from the
  default display (Birk 2026-08-12: a quote would only make the graph more
  chaotic). Terms carry text, people carry face.
- **Term node:** the term label. This is the only text in the net.
- Portraits are normalised to a uniform edge length and circle-masked, face
  centred. Arbitrary phone resolution in, normalised out.

### 10.3 Camera / legibility — decided at the pre-render, not at the desk
Whether ~50 person nodes plus terms fit legibly at 1920×1080 is an empirical
question. Three named outcomes (Birk): (1) everything is sensibly displayable at
once, (2) font size would have to become too small → a zoom function is needed,
(3) an automatic animation pans across the graph once it exceeds the frame.

**Therefore the camera is its own component from the start**, even if everything
ends up fitting — otherwise zoom/pan is a rebuild later instead of a setting. It
has three modes: fit-all, manual zoom/pan, slow automatic pan. Switchable in the
operator UI.

**The panning camera IS the touch fallback.** If touch does not work on the day,
it runs permanently — exactly the "non-interactive auto animation" the Konzept
requires as a fallback. The fallback is a mode, not an extra.

**Outcome (1) is reached by construction, not by luck (revised 2026-08-14,
Birk).** "Font size would have to become too small" was posed as a property of
the graph; it is a property of a *fixed scale*, and there is none. Node and
font sizes are model-unit values, so the camera's fit sets how large they reach
the wall: fewer nodes → a smaller cloud → a higher zoom → larger type. The
placement is normalised to a constant ink density before it is framed, so this
is monotone rather than accidental. Measured 2026-08-15 on the seeded graph at
theme B, fit-all, 32px model type: **26px on the wall at 5 persons, 16px at 20,
13px at 50** (person discs 63 / 38 / 30px) — with zero overlapping label pairs
and zero labels on portrait discs at all three, and 89% × 89% of the canvas
covered in every case.

So the wall is always full and never crowded. What 50 persons costs is
absolute size, and that is what the other two levers are for: the `min_mentions`
dial (§7) raises the type by removing terms (13 → 14 → 18px at 1 → 2 → 3), and
the camera's zoom/pan reaches the rest. Which of them the wall uses stays an
on-site decision.

**The migration is part of the camera's job too.** A graph change re-lays the
whole net out and glides it into place (§11); the fit animates with it, so the
type grows or shrinks smoothly across the transition rather than snapping at
the end of it.

### 10.4 Pre-render (independent of everything else, §7 of the briefing)
Headless PNGs at exactly 1920×1080, **with the same renderer that later runs
live** — otherwise a look is tested that must be rebuilt afterwards.

**Decoupled from the simulation (revised 2026-08-14, Birk).** The series is
needed before the simulation exists. What it measures is legibility, stroke
weight and black level on a whiteboard, and that needs realistic *density* and
realistic *label lengths* — not real LLM extraction. The graph state is
therefore seeded directly through the Store (~50 person nodes plus terms, long
German term labels, a realistic edge distribution, placeholder portraits). The
renderer is still the live one; only the data source changed.

Comparison series (the projection is onto a **whiteboard**, where black is
whatever ambient light sits on the surface — a dark-mode design collapses most
strongly there).

**Second pre-render review (revised 2026-08-14, Birk, binding): white on
black stays.** The inverted, light-ground variant (the old B) is rejected
outright and is gone from the series; its slot became a legibility variant
instead. The three graph variants are now dark-mode only and differ **only**
in type size and stroke/outline weight — palette and background identical
across all three, so the series answers "is it the size?", nothing else:
- **A:** dark mode as in the concept rendering (reference) — 22px labels,
  5px rings
- **B:** larger type — 32px labels, 7px rings, dots/edges/outline scaled to
  match
- **C:** much larger type, heaviest strokes — 44px labels, 10px rings, the
  upper end of the legibility ladder
- **D:** test pattern with greyscale wedge + font-size ladder (measures the
  legibility limit and the real black level on site) — unchanged

A, B and C share one background and palette (`--bg #000000`, person fill
`#242424`, golden ring `#C9A227`, label `#FFFFFF` on Georgia/"Times New
Roman"/serif, `#858585` edges) — a variant that also moved the palette would
not answer the legibility question.

**Colour correction — decision by Birk, 2026-08-15 (binding).** The palette
above is **pure black and pure white**, in all three graph themes. It used to
be `--bg #101014` (a blue-tinted near-black) under `--label-color #F5F1E6` (a
cream near-white). *Projection is additive and the surface is a whiteboard, so
on-site black is whatever ambient light sits on it* — a tint gains nothing
there and costs contrast, while pure values give the projector its whole
range. White-on-black goes from 16.8:1 to 21:1.

Every other token was re-checked against the new extremes rather than left
where an old ground had put it:

| token | was | is | why |
|---|---|---|---|
| `--bg` | `#101014` | `#000000` | the decision |
| `--label-color` | `#F5F1E6` | `#FFFFFF` | the decision |
| `--label-outline-color` | `#101014` | `#000000` | must equal `--bg`, or the outline reads as a halo |
| `--term-dot-color` | `#EDE7D8` | `#FFFFFF` | the dot and its caption are one node; nothing asks them to differ |
| `--edge-color` | `#8A8578` | `#858585` | the neutral grey of the *same relative luminance* (L = 0.235 either way), so edges stay exactly as subordinate to the labels as they were tuned to be |
| `--person-fill` | `#23232a` | `#242424` | same luminance, no cast; only ever seen when a portrait is missing |
| `--ring-color` | `#C9A227` | `#C9A227` | **stays gold.** The concept's signature, and the one element that is not greyscale |

The seeded placeholder portrait went the same way (`#3A3A42` → `#3B3B3B`, same
luminance): it is a stand-in for a photograph, not a theme token, but on a pure
black ground it would otherwise have been the only tinted thing on the wall.
Theme D (the test pattern) follows theme A's ground as it always has, so its
page and its wedge's own 0% step are now the same value — which is the point of
the pattern on site: whatever the whiteboard shows there *is* the black level.

**Layout now fills the 16:9 canvas (found at the same review).** A force layout
is isotropic, so its settled cloud is round and a 16:9 fit leaves the sides
empty. `frameToAspect()` (`projection.js`) stretches the short axis to the
canvas aspect, iteratively and capped. Measured at 50 persons / 125 nodes: the
node cloud went from 30% of the canvas width (34% counting the labels) to 83%
(88% counting the labels). *(The quarter turn this pass used to begin with was
deleted at the fourth review: it existed because Cytoscape's `cose` measures
repulsion with each node's width and height swapped and so settled portrait,
and fcose does not have that bug. The "only ever touches a from-scratch
placement" restriction went with the §11 rule it served — the pass now runs on
every migration.)*

~~**Open, deliberately:** live the net grows one person at a time, so the
from-scratch framing fires on the first person and never again — a live
evening therefore drifts back towards a round cloud.~~ **Closed by the fourth
round (below):** every graph change now re-lays the whole net out and glides it
into place, so the framing runs on every person who joins, not only the first.

**The camera gained a zoom factor and a focus method.** Fit-all at 50 persons
is settled as illegible, so this is a setting of the existing camera
component, not a second implementation: `setZoomFactor(f)` (f ≥ 1; 1 =
fit-all, f = that many times tighter, re-framed in every non-manual mode) and
`focus(eles, padding)` (point the camera at a subset — e.g. one person with
their terms, the frame an automatic traversal dwells on — without changing
the mode).

**Third pre-render review (2026-08-14, Birk, binding).** Theme **B** (32px
labels) is the settled choice and is what the series renders; A and C stay
regenerable for the on-site projector call, which only a real projector can
make. Three decisions:

1. **Placeholder portraits are one colour and smaller.** The per-person hue
   was misleading — the colours meant nothing — and it fought the term text.
   All placeholders are now the same muted slate at a smaller disc size,
   with the golden ring kept at full weight: the ring, not the fill, is the
   concept's carrier. Real photographs will bring their own structure
   through the same path.
2. **A term node is its dot PLUS its label, and the layout now knows it.**
   `settlePlacement()` separates the *measured* dot+label boxes after the
   16:9 framing, and `declutterLabels()` then nudges label offsets — never
   node positions — apart, treating portrait discs as fixed obstacles. Text
   on a person bubble is worse than text on text, because that disc becomes
   a real photograph later. Both passes are deterministic under the same
   seed. Measured on the seeded 50-person / 75-term graph at theme B: 43
   overlapping label pairs and 30 labels on discs from the force layout
   alone, 24 / 14 after the placement, **18 / 4** after the declutter pass.
   *(The "never re-shape an already-placed net" restriction fell with the §11
   rule it served at the fourth review; both passes now run on every
   migration. The numbers here are cose's — see the fourth review for
   fcose's.)*
3. **The `min_mentions` dial (§7) gets its own series**, since it may solve
   much of the crowding by itself: the same graph and the same placement at
   1, 2 and 3 — 75, 50 and 31 term nodes, 253, 228 and 190 edges — through
   the real display filter, never a second renderer.

**Fourth pre-render review — spec change by Birk, 2026-08-14 (binding).** §11's
"existing nodes stay put" is replaced by "the whole net migrates" and §10.3's
legibility question is answered by construction rather than by tuning (both
rewritten above). Birk's instruction for the implementation was explicit — *use
the library, do not hand-build this* — so the layout is now **cytoscape-fcose**
(`quality: "proof"`, `randomize: false`, `nodeDimensionsIncludeLabels`,
`packComponents`), vendored offline alongside Cytoscape itself, and the glide is
Cytoscape's own `preset` layout. Three series in `out/prerender4/`:

1. **Fill the screen** — the same seeded graph at 5 / 20 / 50 persons. Type on
   the wall: **26px / 16px / 13px**, person discs 63 / 38 / 30px, canvas fill
   89% × 89% and **zero** overlapping label pairs and zero labels on portrait
   discs at all three. Nothing in the theme changed between them.
2. **The density dial** at 1 / 2 / 3 — 75 / 50 / 31 terms — now re-lays the net
   out at every step. Third round: the survivors stayed in their old holes and
   the picture shrank (93% → 80% → 73% of the canvas width) at a constant type
   size, with 6 / 1 / 0 overlapping label pairs left over. Fourth round: **89%
   at every step, 0 / 0 / 0 pairs**, and the type *grows* as the dial rises —
   **13 → 14 → 18px** — because the freed space is used.
3. **The migration** — a numbered four-frame sequence through one transition
   (the dial going 1 → 2), timestamps measured and carried in the filenames,
   with the glide slowed to 8s so four frames span it. The wall's own default
   is 2.5s.

**What the measurement settled, against the brief's expectation.** fcose's
`nodeDimensionsIncludeLabels` does *not* replace the hand-built label work. On
the seeded 50-person / 75-term graph at theme B, from an identical start: fcose
alone leaves **42 overlapping pairs, 26 labels on discs, 59% of the canvas
width**; with the option off, 156 / 65 / 43%. So the option earns its keep and
does not finish the job. Both hand-built passes are kept, each on its own
number: `settlePlacement()` takes that to 8 / 1 / 89%, and `declutterLabels()`
clears the rest to **0 / 0 / 89%** — and because moving a label is free where
spreading the net costs type size, asking the declutter pass *before* loosening
the packing is worth 12.7px of type instead of 11.4px. Only what fcose really
did make redundant was deleted: the quarter-turn (it existed for a cose bug
fcose does not have) and the node locking the old §11 rule required.

**Still open after this round:** fit-all at 50 persons is now *clean* but small
— 13px type on a 1920px wall. The layout has given all it can; the levers that
remain are the dial (18px at `min_mentions=3`) and the camera, and which of them
the wall uses is still an on-site decision.

**Fifth pre-render review — Birk, 2026-08-15 (binding).** The migration was
delivered as four stills, and four stills cannot show a glide: played back they
look exactly like the jumping the whole rule exists to disprove. The deliverable
for a *motion* claim is **motion**, so the series now also renders frame
sequences at **25 fps over the wall's own 2.5s glide** plus a 0.5s settled tail
— 76 frames, 3.04s, one directory per transition, each also encoded to H.264 /
yuv420p so it plays inline. Three of them, all at theme B over the seeded graph:
the dial going 1 → 2 (25 terms vanish), the dial coming back 2 → 1 (the harder
direction — the one that used to re-shuffle), and one new person with their
terms joining a settled 30-person net, which is the transition the audience
actually sees most often.

Two things this required, and one it found:

- **The frames are captured on a clock the driver owns**, not by screenshotting
  a running animation. A 1920×1080 screenshot costs a fifth of a 2.5s glide, so
  real-time sampling would bunch the frames at one end and would land them
  differently on every run. `sim/prerender.py` replaces `requestAnimationFrame`
  and `performance.now()` *after* the page has settled and advances them by
  exactly 40ms per frame; the renderer is not patched and does not know.
  Determinism, which every round of this series has required of the placement,
  now covers the motion as well — **of the model, not of the pixels**. Measured
  on two cold runs of the 50-person graph: identical node positions, identical
  label offsets, identical measured label boxes, identical zoom — and PNGs that
  still differ in ~0.5% of pixels, confined to a handful of captions, each
  within 0.2px of the other's ink centroid. Cytoscape rasterises a label into
  its texture cache at a sub-pixel phase that depends on how that cache was
  packed, and that packing follows the redraw timing. The difference is
  invisible and it is not the layout, so each sequence ships a `motion.json`
  (per frame: elapsed time, zoom, pan, every node position) and *that* is what
  carries the determinism claim.
- **A person arrives the way a person arrives**: written through the Store and
  pushed as a complete `graph` event over SSE (§11), not injected into the
  renderer. `sim.seed_graph.person_specs`/`write_person` exist for that — the
  joiner is the next person of the same seed.
- **Found: the glide is preceded by a freeze, and it is not short.** The fcose
  run plus `settlePlacement()` hold the picture still before anything moves —
  on the development machine **2.3s** (dial 1 → 2), **3.3s** (new person) and
  **6.6s** (dial 2 → 1, 125 nodes to place); it is real CPU time and it moves
  with load (an earlier run under a parallel job: 2.6 / 3.4 / 9.9s). On the wall
  that is a stall, then a glide. It is a *computation* cost, not an animation
  setting, so it is carried to §14 rather than fixed here. `Sequence.compute_s`
  reports it per sequence so it cannot be lost again.

What the sequences show, measured from their `motion.json`: every frame lands on
the 40ms grid exactly (t = 0 … 3000ms), every one of the 63 glide frames is a
different picture, the arrangement is reached exactly at the end (frames 64-76
identical), and **no single frame carries more than 4.4% of the transition's
total travel** in any of the three — a cut would put 100% in one frame. The
landing is not a snap either: the last step (the animation ending plus the
`declutterLabels()` pass that runs after it) changes *fewer* pixels than the
second-to-last step of the glide, in all three sequences.

### 10.5 Kiosk operation
Browser fullscreen, auto-restart, crash recovery. State is fully reconstructible
from SQLite after a crash, including node positions.

### 10.6 Touch
Pointer Events. The device must register as an **HID multitouch digitizer**, not
an HID mouse (mouse emulation = one contact point, no gestures). Hardware
procurement and the on-site verification (`dmesg | grep -i hid`,
`libinput list-devices` → `ABS_MT_*` axes) are covered in the Konzept, not here.
If touch is absent, §10.3 mode 3 carries the station.

## 11. Data model & flow

**SQLite is the truth.** Entities: person, term, edge (person↔term), quote,
photo, merge decision, node position, hidden flag.

- **Quotes are extracted and stored even though the wall does not display
  them.** Tool 2 will need them for the prompt, and the touch-summary feature
  (§12) must not require re-collection.
- After every change the Core writes a **complete `graph.json`** — no delta
  mechanism; at this scale it is needless complexity. This file is also the
  read-only interface for Tool 2.
- The frontend learns of changes via **SSE** (same technique the STT server
  already uses).
- **Node positions are persisted** — for **crash recovery**. After a restart the
  wall must come back exactly as it stood (§10.5), so the first paint of a
  session whose every node already carries a position restores it and lays
  nothing out. That is the only case that does not re-arrange.

- **Every other graph change makes the whole net MIGRATE** (revised
  2026-08-14, Birk — this REPLACES the earlier "existing nodes stay put, the
  layout must never re-shuffle"). When a person joins, or the density dial
  hides or reveals terms, **all** nodes move slowly to a new,
  better-distributed arrangement that fills the space the change freed. This
  is also the transition a visitor watches when their own node joins the wall.

  **The anti-jump requirement is unchanged, and it is the whole point.** What
  the Obsidian analysis (§4) ruled out was the JUMP — a periodic reload that
  re-rolled the force layout and teleported every node — not movement. So the
  re-layout must be:
  - **incremental** — it starts from the positions currently on the wall and
    improves them (`randomize: false`, which fCoSE only supports at
    `quality: "proof"`). Never a re-roll from random, ever.
  - **animated** — the net glides into the new arrangement over ~2.5s
    (Cytoscape's own `preset` layout does the interpolation), never cuts to it.
  - **deterministic** — the same graph and the same starting state settle on
    the same picture, so the pre-render series stays a fair comparison.

- **Node and font sizes are never fixed to the wall.** Everything is sized in
  MODEL units and the viewport fit scales it: a handful of nodes come out
  large, a hundred come out small, and the graph always fills the screen
  without overcrowding. The settled placement is normalised to a constant ink
  fraction of its own bounding box so that this holds *monotonically* — a
  force layout on its own does not scale with how much is in it (measured
  2026-08-15: labels reached the wall at 17 / 21 / 15 / 15 px across graphs of
  3 / 6 / 20 / 50 persons, flat and non-monotone).
- **Second screen** is foreseen as an independent output (organiser-provided;
  type/connector/resolution still to be clarified with the organiser).

## 12. Explicitly out of scope (named, so it is not re-proposed as new)

- **Tool 2 „Kollektivtraum"** — graph→prompt→image on its own screen beside the
  wall. **Brainstorm DONE (`specs/2026-08-25-kollektivtraum-brainstorm.md`) and
  SPEC WRITTEN (`specs/2026-08-25-kollektivtraum-design.md`); plan cycle
  pending.** It is a separate process on a separate machine, reading this tool's
  `graph.json` over HTTP.

  **Five properties of THIS tool are now load-bearing for it — do not refactor
  them away** (Tool 2 spec §13): (1) `graph.json` stays complete state, no delta
  mechanism; (2) `quotes[]` stays in the payload though the wall never renders
  it; (3) `mentions` per term stays — it is Tool 2's weighting input;
  (4) `hidden` stays — it is Tool 2's exclusion input; (5) **`broadcast_graph()`
  keeps firing AFTER the pipeline, not at the stop (`kg/core.py:198`)** — moving
  it to `_close()` would silently make every dream one interview stale, because
  at stop time the new person has no terms yet.

  One change lands *in* this tool, and it is smaller than Tool 2's spec first
  claimed: `server_host` was **already** LAN-bindable (`kg/config.py:48`,
  `config.example.toml:59`) — corrected 2026-08-25, see Tool 2 spec §3.1. All
  that lands here is `kg/__main__.py` printing the *resolved* interface address
  instead of the literal `0.0.0.0`, so the URL the runbook tells the operator to
  open is one the dream machine can actually open. Nothing else in `kg/` is
  touched by the Tool 2 build.
- **Quote on touch** — tapping a person node reveals a summarising quote. Birk
  finds this attractive; kept as nice-to-have for later. Data is already stored,
  so this is a pure frontend feature later.
- **Terms growing during the interview** (streaming extraction) — kept for a
  later iteration.
- **Term↔term edges** (§6.4).
- **Runtime-adjustable extraction settings** (§6.3, §7).
- **Pre-roll transcription** of audio before the photo (§5) — optional.
- **Diarisation / parallel interviews** — one mic, serial by construction.

## 13. Testing & verification

- Unit level: segmentation (marker logic, timeout, spoken-command matching incl.
  the strip-before-extraction rule), merge persistence, `graph.json` export,
  display-filter semantics.
- Integration: the simulation (§9) is the primary harness — text in, graph
  state out, PNG out.
- Contract: the SSE consumer against the STT server's event shape (§4) —
  re-verify against the current repo first.
- Visual: the pre-render comparison series (§10.4), judged by Birk.
- Failure modes to cover explicitly: STT server unreachable, Telegram offline,
  LLM call fails or returns invalid JSON, photo without stop, stop without
  photo, crash + restart (state must reconstruct incl. positions).

## 14. Open items carried into phase 2

1. ~~Verify the current STT server repo~~ — **RESOLVED 2026-08-12.** Source,
   branch, run command and the changed 10-field event contract are recorded in
   §4. Not blocking any more.
2. **Second screen specs** from the organiser (type/connector/resolution) —
   affects Tool 2, not Tool 1's core.
3. **Touch hardware decision** (IR frame vs. interactive UST beamer) — Konzept,
   procurement track, does not block this build.
4. **Density calibration values** — produced BY the simulation, not before it.
5. **The freeze before the glide** (found at the fifth pre-render review,
   2026-08-15). Every graph change computes its new arrangement before anything
   moves — fcose at `quality: "proof"` plus `settlePlacement()`'s rounds — and
   on the development machine that took 2.6s / 3.4s / 9.9s for the three filmed
   transitions. A visitor watching their own node join therefore sees a stall
   and then a glide. It is CPU time on the exhibition laptop, so the honest
   levers are measurement on that machine first, then either cheaper settings
   (`numIter`, `PLACEMENT_ROUNDS`) or moving the computation off the frame the
   change lands on. Not a §10.3 legibility question and not an animation
   setting; deliberately not tuned against one machine's numbers here.
