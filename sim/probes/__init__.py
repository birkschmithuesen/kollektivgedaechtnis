"""Ad-hoc measurement probes — kept because their NUMBERS are cited elsewhere.

These are not part of the station and are not covered by the test suite. They
exist so that a claim in a spec or runbook ("14,7 px at 32 terms", "the mood
channel moves colour temperature by 80 points") can be re-checked instead of
believed. Each one is written for a single question, run once or twice, and
then referenced from the document that uses its result.

If a probe's result becomes a permanent part of how the station is tuned, it
belongs in `sim/dream_calibrate.py` (the maintained calibration tool) instead
of here.

- `wall_legibility.py` — how many term labels stay legible on the projection
  at 1920x1080. Cited by
  `docs/superpowers/specs/2026-08-29-wand-anzeigeregler-begriffsobergrenze.md`.
- `moodgrid.py` — renders one sentence at five (mood, tension) pairs to check
  the two analysis channels actually change the image. Costs ~0,70 USD per
  run: five image calls. Cited by `docs/operations.md`.
"""
