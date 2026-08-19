# Change request CR-1 — second screen as an independent player client (Birk, 2026-08-19)

Status: **REQUIREMENT CAPTURED, NOT YET SPECIFIED.** This is deliberately not a
plan task yet — it needs its own brainstorm/spec cycle. Written down so it is not
lost between sessions and so Task 21's runbook does not get built as if the
station were a single machine.

## What Birk asked for

1. **Touchscreen is confirmed.** It will exist. Spec §14.3 ("touch hardware
   decision — procurement track") can be closed as YES once the model
   description arrives. Birk is sending it later. Consequence: camera mode
   `manual` is a genuinely reachable on-site mode, and the `pan` fallback stops
   being the load-bearing plan.

2. **A second monitor shows the graph too**, driven by a **second computer**
   Birk will set up. On that machine:
   - zoom and animation are set **independently** of the main projection,
   - the rendering may deliberately **differ** from the wall outside.

3. **The second machine pulls its data over the network / internet**, not from a
   local file. Birk's own proposal: put **both machines on Tailscale** and have
   the player client fetch from the main machine.

## Why this is NOT just "open /projection on the second box"

The current architecture makes the second screen look free — it is a web page,
so a second browser could point at the same server. Three things break that:

- **The camera state is GLOBAL, not per-client.** `camera_mode` is a row in the
  Store's settings table; `broadcast_state` pushes it to every SSE subscriber and
  `projection.html` applies it unconditionally. Two screens on one server today
  are forced into the same mode. Birk explicitly wants them different, so this
  needs a per-client view state — the first genuine architecture change since the
  spec was approved.
- **Same for the theme and the density dial.** `?theme=` is already per-URL (good,
  that part carries), but `min_mentions` arrives through the same global state
  push. "Anders dargestellt" may or may not mean a different density — worth
  asking rather than assuming.
- **Node positions are written back by the renderer** (`/api/positions`, a POST
  from `projection.html`). A second renderer with its own zoom would be a SECOND
  WRITER into the persisted-position table, racing the wall's own writes. Right
  now that would corrupt crash recovery. The player client must be **read-only**
  by construction — no position POSTs.

## Networking — what needs verifying, not assuming

Birk's Tailscale instinct is sound and there is an in-house skill for the
bootstrap (`mlops/tailscale-home-gpu-access` — tailnet bootstrap, the
`sudo tailscale up` human-auth step, the per-box sudo check).

But two things are NOT yet true and must not be assumed:

- The server currently binds **`server_host = "127.0.0.1"`** (`kg/config.py`,
  `config.example.toml`). Localhost-only. A tailnet peer cannot reach it at all
  until that bind changes. This is exactly the pitfall the LM Studio skill
  documents for `lms server` — same shape, same fix, and the same rule applies:
  verify the cross-machine path with a real request from the OTHER box, never
  from localhost on the server.
- **The festival venue's connectivity is unknown.** "Übers Internet ziehen" is
  fine over Tailscale, but if both machines sit on the same table, a direct
  LAN/tailnet link is the robust path and the internet is only the coordination
  channel. If the venue has no usable uplink at all, Tailscale needs either a
  pre-authenticated tailnet or a local fallback. **Do not design this until the
  venue's network situation is known** — it decides between "pull over tailnet"
  and "the two boxes need their own local link".

## Answers from Birk (2026-08-19) — these close the open questions

1. **Same graph.** Real-time is the ideal, but **lag is explicitly acceptable**.
   No curated subset, no different content — the same net.
2. **Completely separate room.** So the two screens are never seen side by side.
   Nobody can compare them, which means "anders dargestellt" is about suiting
   that room, not about a deliberate contrast between the two.
3. **No operator UI on the second machine.** It is **set once in the morning and
   left alone** for the rest of the day.
4. **Internet is available** at the second machine's position.

## What those answers change — the design gets much smaller

Taken together these remove most of the architecture risk identified above:

- **Lag is acceptable + no operator UI ⇒ the player does not need the SSE state
  channel at all.** It can simply **poll `GET /graph.json`** on an interval
  (say every 5–15 s). That endpoint already exists, is already complete-state
  (no delta mechanism, spec §11), and is already documented as the read-only
  interface for Tool 2. Nothing server-side has to be invented.
- **Set-once-in-the-morning ⇒ per-client view state needs no plumbing.** Zoom,
  theme and animation can be **URL parameters** on the player page, exactly like
  the existing `?theme=` and `?migration=` parameters `projection.html` already
  supports. No settings table, no broadcast split, no second operator API. The
  global `camera_mode` push is simply not subscribed to by the player.
- **The second-writer hazard disappears by construction** if the player never
  POSTs positions. `createGraphView` already takes `onPositions` as an injected
  callback defaulting to a no-op (`projection.js:704`), so a player page that
  omits it is read-only with no code change to the renderer.
- **Separate room ⇒ the two screens' arrangements need not match**, which is
  what makes the polling approach viable: the player lays out the graph itself
  from `graph.json` (which carries persisted x/y), and small divergence from the
  wall is invisible to everyone.

**Remaining real work, now modest:** a `/player` page (a trimmed
`projection.html` — poll instead of SSE, no position POST, view settings from
URL params), and making the server reachable from the second machine (bind
address + tailnet). That is plausibly a single task rather than a spec cycle.

**Still to verify, not assume:** whether the venue's uplink is good enough that
polling over the tailnet is reliable all day, and whether the two machines can
reach each other directly or fall back to a DERP relay (the tailscale skill
notes DERP adds ~150–250 ms — irrelevant at a 5–15 s poll interval, worth
knowing anyway).

## Sequencing recommendation (revised after Birk's answers)

The answers above shrink this from a spec cycle to a **single implementable
task**, because nothing server-side has to be redesigned: the player polls an
endpoint that already exists, and configures itself from URL parameters the page
already knows how to read.

Recommendation: finish Tool 1's remaining plan tasks (18, 19, 21) plus the
zoom-control update (21b), then add CR-1 as **Task 22 — player client and
network-reachable bind**. No brainstorm cycle needed; a short brief suffices.

The one thing worth doing EARLY, because it is cheap and de-risks the rest:
bring both machines onto the tailnet and prove a plain HTTP GET of `/graph.json`
from the second box. That single test answers the networking half before any
implementation starts, and it is also the exact thing the player will do in
production.
