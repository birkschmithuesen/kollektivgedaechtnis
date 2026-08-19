# Decision D4 — camera default and on-site adjustment (Birk, 2026-08-19)

Binding. Feeds `docs/operations.md` (plan Task 21, "Kalibrierte Werte") and the
spec §10.3 open question "which of them the wall uses stays an on-site decision".

## The decision

**Default camera mode = `fit` (whole net in frame).** Camera 1 of the
prerender8 series: 86 % canvas fill, all 125 nodes in frame, 13 px labels on a
1920-wide wall.

**Zoom level, pan and mode are NOT decided at the desk.** Birk: the modes —
whether an automatic pan runs, zooming in and out — get set interactively on
site against the real screen and the real room. The pre-render series answered
the legibility question it was built for; it cannot answer the projector-and-
distance question.

Rationale for `fit` as the default: the station's subject is the collective
net, so the opening state must show the whole of it. Zooming in is the
on-demand move, not the resting state.

## Consequence — a real gap this exposes (NOT yet fixed)

`Camera.setZoomFactor(f)` exists and works (camera.js), but it is reachable
**only through the constructor**. It is not in the server's state payload
(`kg/server.py` `broadcast_state` sends `camera_mode` and `min_mentions` only),
not in `projection.html`'s `state` branch, and not in the operator UI
(`frontend/operator.html` has the density select and a three-way camera select,
no zoom control).

So today, "bei Bedarf reinzoomen" on site is possible **only** by switching the
camera to `manual` and using touch/mouse on the projection machine. If touch
hardware does not arrive — which is still an open procurement item, spec §14.3 —
there is no way to zoom at all from the operator laptop.

Two ways to close it, Birk's call before the event:

1. **Expose the zoom factor as a second operator control** (a small select:
   1× / 1.5× / 2×), carried in the same settings/state path as `camera_mode`.
   Touches `kg/server.py`, `frontend/operator.html`, `frontend/static/operator.js`,
   `projection.html`. Small and mechanical — the Camera side already exists.
   Note against spec §7: §7's "exactly one runtime dial" governs controls that
   change **extraction or merging**; the camera select is already a display-only
   control alongside it, so a zoom select is the same class, not a new one. Worth
   stating explicitly in the spec if this is built.
2. **Leave it**, and treat `manual` mode plus touch as the only zoom path,
   accepting that no-touch means fit-only.

Not resolved here. Logged so Task 21's runbook does not silently document a
control that cannot be reached.
