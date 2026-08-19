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

## Open questions for Birk (do not guess these)

1. Does "anders dargestellt" mean only a different theme/zoom/animation, or a
   genuinely different visual (e.g. a different layout, only terms, no portraits)?
   The former is a settings split; the latter is a second renderer.
2. Should the second screen show the SAME live graph, or is it allowed to lag /
   show a curated subset?
3. Who operates the second machine — is there a second operator UI, or is it set
   once at the start of the day and left alone?
4. Venue network: is there internet at the second machine's position, and are the
   two machines on the same local network?

## Sequencing recommendation

Do **not** interleave this with Tasks 18/19/21. Those close out the approved Tool
1 plan and are nearly done. This is a scope addition with real architectural
consequences (per-client view state, a read-only client role, a network-reachable
bind) and deserves its own brainstorm → spec → plan cycle, exactly as Tool 2 got.
Finish Tool 1, then run CR-1 as its own cycle with the venue's network facts and
the touchscreen model in hand.

The one thing worth doing EARLY, because it is cheap and de-risks the rest:
bring both machines onto the tailnet and prove a plain HTTP GET of `/graph.json`
from the second box. That single test answers the networking half before any
design work starts.
