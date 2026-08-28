# Tool 2 „Kollektivtraum" — brainstorm outcome (Birk, 2026-08-25)

Status: **BRAINSTORM CLOSED, ALL STRUCTURAL AXES DECIDED. Spec not written yet.**

This is the cycle that spec §12 called for („Tool 2 — own brainstorm + spec +
plan cycle, after Tool 1"). It records the decisions and, for each, the reason
they were taken — so the spec that follows argues from here instead of
re-opening settled ground.

Everything below is Birk's decision. Where a recommendation was followed
verbatim, that is noted; the reasoning is kept because it is what the spec has
to stay consistent with.

## 0. Screen topology — corrected first (Birk, 2026-08-25)

A contradiction between CR-1 and the pitch deck was resolved before any design
question. There are **three surfaces**, not two:

| | Surface | Content | Machine |
|---|---|---|---|
| **A** | Touchscreen, main station | the graph (Tool 1) | exhibition machine |
| **B** | Screen, **directly beside A** | Kollektivtraum (Tool 2) | **own machine** (§9) |
| **C** | Screen, **separate room** | mirror of the graph | second machine (CR-1 player client) |

CR-1 is unchanged and remains correct as written — it describes **C**, the
graph mirror. It was never about the Kollektivtraum. `docs/decisions/cr1-second-screen-player.md`
needs no revision, only the awareness that a third surface exists.

**A and B stand side by side.** This is the single most consequential fact in
this document: the translation chain is not asserted, it is *checkable* — a
visitor reads the terms on the left and what became of them on the right. It
drives decisions 2, 6, 7 and 10.

## 1. What the image is — **dream, not illustration**

Chosen: **condensation in the literal sense.** Displacement and contradiction
stay in; the image may be impossible. Not a plausible architectural vision.

The visual register of the approved rendering
(`kollektivtraum-screen_v2_2026-08-16.png` — painterly, atmospheric, soft) is
kept as the *register*, not as the motif.

Reasoning: the deck promises „das Gedächtnis träumt sein eigenes Bild" — not a
rendered brochure. An LLM that averages 40 contradictory interviews into one
glossy render *is* the critique ArtesMobiles otherwise formulates. The friction
is the subject matter.

## 2. Rhythm and memory — **growing series, cross-fade, no morph**

- Current dream **large**, the earlier ones as a **history strip** (smaller /
  dimmer) — asymmetric.
- Transition is a **fade**. Explicitly **not** a morph (Birk).

Reasoning: the graph next door visibly *grows*; a dream that merely replaces has
no time axis and looks the same at 17:00 as at 10:00 despite 40 interviews.
The strip is also the evidence that there was never *one* vision of the future.

Morph was ruled out on its merits: between two independently generated images it
is either a cross-fade (then use the simple case) or an img2img chain that
converges to mush.

## 3. Prompt visibility — **(a) is the baseline, (c) is an attempt on top**

- **Baseline / fallback (a):** the prompt sits as a line **under the image**.
- **On top (c):** during generation the text builds up word by word, and once
  the image arrives it settles into that same fixed line.
- Birk decides **visually on site** whether (c) stays.

Birk's framing, and it is the right one: (c) *contains* (a) — it is an animation
layer over the baseline, not a second layout branch. Consequence for the build:
one layout, one optional animation. The „generation takes 60 s" risk is carried
by the baseline.

## 4. How the sentence is built — **(b) + (c) together, two-stage**

- **(b) Weighted by graph structure.** Frequently mentioned terms dominate;
  single mentions appear as marginal detail. The numbers (mention count,
  connectedness) already exist in the graph.
- **(c) Contradiction as construction principle.** The two most distant
  positions in the graph must occupy *one* image without being resolved.
- **Two stages:** first condensation *into language* (including the fault line)
  — this is the sentence shown on screen — then translation of that condensation
  into image language.
- **Threshold:** below N persons, (b) alone. With three interviews there are no
  real oppositions and (c) would look contrived.

Reasoning: (b) is the mechanism and it is cheap; it also makes the relation
between the two screens legible — what is thick on the left is large on the
right. (c) is the stance: without an explicit counter-instruction every LLM
smooths, and the result drifts back to the consensus brochure that decision 1
rejected.

## 5. Connectivity failure — **(a) ride it out, no local model**

- Last image **stays up**, the cycle keeps retrying. The station looks calm, not
  broken.
- The history strip is the safety net — it is full anyway (decision 2).
- **LTE stick** as the physical fallback path.
- **US cloud is acceptable for this station** (Birk, 2026-08-25). Consistent
  with Tool 1, which already runs extraction on `claude-opus-5`.

A local image model (SDXL on the exhibition machine) was explicitly rejected as
a *fallback*: it would mean maintaining two visual languages, and it needs a GPU
in the show laptop. If a local model is ever wanted, it is a matter of principle
(no US cloud), not a failover — and then it is its own decision.

## 6. Trigger — **(c) event-driven with a floor**

- A **completed interview** triggers a new dream.
- **Not before** N minutes after the previous image.
- **Nothing happens** during silence — no dreams without new material.

Reasoning: A and B stand side by side, so causality is *visible*. A new image
appearing while nothing happened on the left exposes the station as a random
generator. Conversely „a person just spoke, and the dream changed" is the
strongest moment the station has, and it is free if the trigger hangs on the
interview instead of the clock. The floor only guards against staccato and cost.

Side benefit: the interviewee is usually still standing there and gets to see
their own dream.

## 7. Guiding question — **(a) one fixed question, all day**

All dreams answer the same question. It must be **wide enough to carry all three
interview themes** (future of building / AI in building / new forms of living
together) — closer to „Wie leben und bauen wir in zehn Jahren?" than to a narrow
material question. Exact wording is decided when the spec is written.

Reasoning: decision 2 made the history strip the centrepiece, and it only works
if exactly one variable changes — the material. If the question travels too, a
different image might just mean a different question, and the strip becomes
unreadable. With a fixed question every change in the strip means: *people said
something different.*

**The question is configuration, not a live control** (see 8).

## 8. Operator interface for Tool 2 — **(b) display settings + flow control**

Tool 2 gets its **own** operator interface (Birk, 2026-08-25). Tool 1's operator
UI keeps its deliberate sparseness (spec §7, „the one live control") and is not
extended.

**Display settings:** guiding question on/off and its display duration (Birk's
explicit request), fade length, size ratio image ↔ history strip.

**Flow control:** trigger a dream now · discard the current dream · pause.

- „Trigger now" is needed the moment someone from the organiser stands in front
  of the screen and wants to see how it works.
- „Discard" is the only emergency exit if the image model produces something
  unusable or embarrassing. Same logic as Tool 1 spec §8: *no gate, an emergency
  exit.*
- **Discard removes the image from the large screen AND from the history strip
  in one step** — an image pulled for embarrassment must not live on below.

**Explicitly NOT in the interface:** changing the guiding question live, or
adjusting weighting/prompt at runtime. Changing the question mid-day destroys
exactly the comparability decision 7 made central. It is set in the morning, in
configuration.

## 9. Machine — **(c) its own machine for screen B**

The Kollektivtraum runs on a **dedicated small machine** driving screen B.
(Considered and rejected: sharing the exhibition machine, or hanging B off the
second-room machine.)

Two consequences that follow directly and belong in the spec:

- **The Tool 1 server must bind network-reachable.** Today `server_host =
  "127.0.0.1"` (`kg/config.py`, `config.example.toml`) — localhost only. This is
  the same change CR-1 already requires for screen C, so it lands once and serves
  both.
- **Tool 2 fetches `graph.json` over the network**, not from the filesystem —
  using the read-only interface exactly as spec §11 intended. Clean cut: the
  exhibition machine does memory, the small machine does dream, they share one
  file.

## 10. Visual register — **(a) fixed all day, revised 2026-08-28**

**The machart (photography vs. painting vs. rendering) is fixed, every image,
all day, set in the morning like the guiding question.** That part of the
original reasoning stands unchanged: the history strip is a measurement
series and needs exactly one variable travelling at a time, and a machart
that changed mid-day would make the strip show style changes and bury the
content drift behind them.

**Revised 2026-08-28: mood and tension are no longer folded into "style".**
They are now their own channel — two more values from the SAME stage-1 call
that produced the sentence (`kg2/condense.py`'s `mood`/`tension`,
`kg2/imagegen.py`'s `MOOD_LIGHT`/`TENSION_COHERENCE`), each with five FIXED
formulations picked by the stage-1 output, never phrased by the model itself.
This is deliberately NOT graph-driven style in the sense this section
originally rejected: mood/tension describe only light, colour, and the degree
of coherence — never a change in machart, subject choice, or composition
rule. The objection this section originally raised against graph-driven style
— „unprovable in the room, nobody can verify the image is harsher *because*
the conversation was more contentious" — **still holds for a single image**,
and is deliberately left standing rather than argued away: nobody standing in
front of one picture can verify it. What changed is the unit of judgement.
Across the SERIES — the whole point of the history strip — the development
becomes visible: a strip where images visibly warm and cool with the day's
material is exactly the kind of drift the strip exists to show. A fixed style
the whole day would have hidden that; the material's temperature would have
had nowhere to register at all.

**Open, deliberately decided at images not in words:** the machart's exact
wording. When the spec stands, generate three or four register samples with
identical fictional content and let Birk pick.

## Carried forward into the spec

1. **Wording of the guiding question** (7) — wide enough for all three interview
   themes.
2. **Register samples** (10) — three or four, same content, decided visually.
3. **Threshold N for contradiction mode** and **minimum interval N** (4, 6) —
   calibrated from the synthetic corpus, like Tool 1's density values, not
   guessed up front.
4. **Screen B hardware** — size/connector; the deck already lists a 65″ screen
   plus floor stand as an organiser-provided item.
5. **Spec dependency:** the network-reachable bind (9) is shared with CR-1 and
   should be built once, for both consumers.

## Unverified — flagged, not assumed

- Whether the venue's uplink carries two cloud calls per cycle all day. Same open
  question CR-1 already records for the player client; both now depend on it.
- Whether the dedicated machine's hardware suffices for image display plus the
  fetch/generation loop — a measurement on the actual machine, not an estimate
  (the same caution spec §14.5 demands).
