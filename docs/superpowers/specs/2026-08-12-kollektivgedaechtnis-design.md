# Design Spec: Kollektivgedächtnis (Tool 1 — Live-Interview-Graph)

- **Status:** awaiting Birk's review (all design decisions taken in dialogue 2026-08-12)
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
| Credentials | the exhibition machine gets ONE LLM key + one bot token — never `~/.hermes/.env` | Briefing §5a |
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

### 🔴 Open verification (assumption, unproven at spec time)
The version inspected during brainstorming was an **older copy** from
`Nextcloud:Hermes-Agent/RoboCloud/stt_server/` and contains only local backends
(Vosk, faster-whisper, faster-whisper-streaming) — **no cloud provider**. Birk
confirmed the current GitHub version has the ElevenLabs backend but could not
pull it during the session.

**Phase 2 MUST re-verify against the current repo before implementing the
consumer.** What matters is only the event contract below; if it changed,
adapt the consumer, not the server.

### The contract we depend on
From `stt_server/events.py` (inspected, old version):

```python
TranscriptionEvent(
    recognizer_id: str,
    type: "partial" | "final",
    text: str,
    timestamp: float,     # wall clock, epoch seconds
    backend: str,
    status: str | None,
    confidence: float | None,
    turn_id: str | None,      # stable per utterance
    partial_seq: int | None,
)
```
Delivered as SSE over `GET /events` (JSON per event, `: keep-alive` comments
between). Other endpoints observed: `/status`, `/pause`, `/resume`.

**We consume `type == "final"` only.** Partials are for the operator display.

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

1. **Cut** — all `final` events between start and stop marker, plus a generous
   tail beyond the stop marker.
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

### 10.4 Pre-render (independent of everything else, §7 of the briefing)
Headless PNGs at exactly 1920×1080, **with the same renderer that later runs
live** — otherwise a look is tested that must be rebuilt afterwards. Fed by
real graph states from the simulation, not fixtures.

Comparison series (the projection is onto a **whiteboard**, where black is
whatever ambient light sits on the surface — a dark-mode design collapses most
strongly there):
- **A:** dark mode as in the concept rendering (reference)
- **B:** inverted — light ground, dark lines/labels
- **C:** dark mode with markedly heavier strokes + larger minimum font
- **D:** test pattern with greyscale wedge + font-size ladder (measures the
  legibility limit and the real black level on site)

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
- **Node positions are persisted.** Existing nodes stay put; only new nodes are
  assigned a place. The layout must never re-shuffle — that would destroy
  exactly the aesthetic the concept rests on (Briefing §4).
- **Second screen** is foreseen as an independent output (organiser-provided;
  type/connector/resolution still to be clarified with the organiser).

## 12. Explicitly out of scope (named, so it is not re-proposed as new)

- **Tool 2 „Kollektivtraum"** — periodic graph→prompt→image on the second
  screen. Own brainstorm + spec + plan cycle, after Tool 1.
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

1. **Verify the current STT server repo** (§4) — event contract, ElevenLabs
   backend, how to run it. Blocking for the consumer implementation.
2. **Second screen specs** from the organiser (type/connector/resolution) —
   affects Tool 2, not Tool 1's core.
3. **Touch hardware decision** (IR frame vs. interactive UST beamer) — Konzept,
   procurement track, does not block this build.
4. **Density calibration values** — produced BY the simulation, not before it.
